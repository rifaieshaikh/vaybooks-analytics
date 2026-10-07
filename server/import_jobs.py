"""Async workbook import: enqueue, worker, progress updates."""

from __future__ import annotations

import logging
import os
import threading

from server.auth import can_upload_type, type_perm
from server.files import frame_values, frames_from_bytes
from server.mappers import validate_mapper
from server.persist import persist_type
from server.preview import (
    UPLOAD_TYPES,
    effective_mapper,
    guess_type,
    header_drift,
    is_sheet_plan,
    mapper_override,
    override_for_sheet,
)
from server.provenance import (
    EVENT_MODES,
    file_sha256,
    infer_max_event_date,
    normalize_event_mode,
    parse_effective_date,
)
from server.ingest import prepare_rows
from server.settings import DEFAULT_UNIQUE_KEYS, SNAPSHOT_TYPES, SOURCE_TYPES
from server.store import now_utc

log = logging.getLogger("vay.import_jobs")
_import_lock = threading.Lock()


class Cancelled(Exception):
    pass


def _remember_event_mode(store, type_name, event_mode):
    if type_name in SNAPSHOT_TYPES:
        return
    current = dict(store.get_mapper(type_name) or {})
    current["event_mode"] = normalize_event_mode(event_mode)
    current.setdefault("column_map", {})
    current.setdefault("extra_types", {})
    if not current.get("unique_key"):
        current["unique_key"] = list(DEFAULT_UNIQUE_KEYS.get(type_name) or [])
    store.put_mapper(type_name, current)


def process_frame(
    store,
    type_name,
    frame,
    upload_id,
    per_type,
    override=None,
    save_map=False,
    event_mode="skip",
    dry_run=False,
    effective_date=None,
):
    clean_ov = mapper_override(override) if isinstance(override, dict) else None
    mapper = effective_mapper(store, type_name, clean_ov)
    if not mapper.get("unique_key"):
        per_type[type_name] = {"error": "Mapper unique_key is required for %s" % type_name}
        return
    headers, values = frame_values(frame)
    saved_map = (store.get_mapper(type_name) or {}).get("column_map") or {}
    drift = header_drift(saved_map, headers)
    confirmed = bool(isinstance(override, dict) and override.get("mapping_confirmed"))
    if drift["changed"] and not confirmed and not dry_run:
        per_type[type_name] = {"error": "Headers changed. Confirm the mapping before import."}
        return
    if save_map and clean_ov and not dry_run:
        err = validate_mapper(type_name, mapper)
        if not err:
            payload = {
                "column_map": mapper.get("column_map") or {},
                "unique_key": mapper.get("unique_key") or [],
                "extra_types": mapper.get("extra_types") or {},
            }
            prior_mode = (store.get_mapper(type_name) or {}).get("event_mode")
            if type_name not in SNAPSHOT_TYPES:
                payload["event_mode"] = normalize_event_mode(event_mode)
            elif prior_mode:
                payload["event_mode"] = prior_mode
            store.put_mapper(type_name, payload)
    counts = persist_type(
        store,
        type_name,
        headers,
        values,
        mapper,
        upload_id,
        event_mode=event_mode,
        dry_run=dry_run,
        effective_date=effective_date,
    )
    per_type[type_name] = counts
    if not dry_run and not (counts or {}).get("error"):
        _remember_event_mode(store, type_name, event_mode)


def merge_type_counts(dst, src):
    if not src:
        return dst or {}
    if not dst:
        # Drop preview payloads from type aggregates
        out = {
            k: v for k, v in src.items()
            if k not in ("preview_rows", "preview_truncated")
        }
        return out
    if src.get("error") and not any(isinstance(v, int) and v for k, v in src.items() if k != "error"):
        if dst.get("error"):
            return dst
        out = dict(dst)
        out["error"] = src["error"]
        return out
    out = dict(dst)
    out.pop("preview_rows", None)
    out.pop("preview_truncated", None)
    if out.get("error") and any(isinstance(v, int) and v for k, v in src.items() if k != "error"):
        out.pop("error", None)
    for key, val in src.items():
        if key in ("error", "preview_rows", "preview_truncated"):
            continue
        if isinstance(val, int):
            out[key] = int(out.get(key) or 0) + val
        elif key in ("mapper_version", "event_mode") and val and not out.get(key):
            out[key] = val
    return out


def resolve_sheet_target(sheet_name, headers, plan, forced_type=None):
    if is_sheet_plan(plan):
        if plan.get("skip") or plan.get("include") is False:
            return None, True
        t = str(plan.get("type") or "").strip().lower()
        if t in UPLOAD_TYPES:
            return t, False
    if forced_type in UPLOAD_TYPES:
        return forced_type, False
    if sheet_name in UPLOAD_TYPES:
        return sheet_name, False
    guessed = guess_type(sheet_name, headers, None)
    return guessed, False


def _user_from_perms(permissions):
    return {"permissions": list(permissions or [])}


def plan_sheet_steps(frames, overrides, forced=None):
    """Build initial progress rows from workbook sheets + maps."""
    steps = []
    for name in frames.keys():
        headers, _values = frame_values(frames[name])
        plan = override_for_sheet(overrides, name)
        target, skipped = resolve_sheet_target(name, headers, plan, forced)
        if skipped or not target:
            steps.append({
                "id": name,
                "sheet": name,
                "type": target or None,
                "state": "skipped",
                "title": name,
            })
            continue
        steps.append({
            "id": name,
            "sheet": name,
            "type": target,
            "state": "waiting",
            "title": name,
        })
    return steps


def _sheet_mode(plan, default_mode):
    mode = normalize_event_mode(default_mode)
    if is_sheet_plan(plan):
        plan_mode = str(plan.get("event_mode") or "").strip().lower()
        if plan_mode in EVENT_MODES:
            mode = plan_mode
    return mode


def process_combined_frames(
    store,
    frames,
    upload_id,
    overrides,
    mode="skip",
    permissions=None,
    forced=None,
    only=None,
    on_progress=None,
    dry_run=False,
    effective_date=None,
):
    """Process all (or one) sheets. on_progress(steps, done, total, current, per_type) optional."""
    per_type = {}
    sheet_results = []
    user = _user_from_perms(permissions)
    steps = plan_sheet_steps(frames, overrides, forced)
    work = [s for s in steps if s.get("state") != "skipped"]
    total = len(work)
    done = 0
    effective_dates = {}

    def emit(current=""):
        if on_progress:
            on_progress({
                "current": current,
                "done": done,
                "total": total,
                "sheets": [dict(s) for s in steps],
            }, per_type)

    emit("")

    by_id = {s["id"]: s for s in steps}
    for name, frame in frames.items():
        if only and name != only:
            continue
        step = by_id.get(name)
        if not step:
            continue
        if step.get("state") == "skipped":
            sheet_results.append({"sheet": name, "skipped": True})
            continue

        headers, values = frame_values(frame)
        plan = override_for_sheet(overrides, name)
        target, skipped = resolve_sheet_target(name, headers, plan, forced)
        if skipped or not target:
            step["state"] = "skipped"
            sheet_results.append({"sheet": name, "skipped": True})
            emit(name)
            continue

        step["state"] = "running"
        step["type"] = target
        emit(name)

        if not can_upload_type(user, target):
            info = {"error": "No permission"}
            step["state"] = "failed"
            step["error"] = info["error"]
            sheet_results.append({"sheet": name, "type": target, **info})
            per_type[target] = merge_type_counts(per_type.get(target), info)
            done += 1
            emit(name)
            continue

        save_map = type_perm(target, "map") in (user.get("permissions") or [])
        holder = {}
        if is_sheet_plan(plan):
            ov = plan
        else:
            ov = overrides.get(target) if target else None
        sheet_mode = _sheet_mode(plan, mode)

        # Infer effective date for snapshots when not provided
        sheet_eff = effective_date
        if not sheet_eff and target in ("arr", "stock"):
            mapper = effective_mapper(store, target, mapper_override(ov) if isinstance(ov, dict) else None)
            from server.account_aliases import alias_lookup
            prepared, _c, _rejects = prepare_rows(
                target, headers, values, mapper, aliases=alias_lookup(store),
            )
            sheet_eff = infer_max_event_date(prepared)  # may be None for snapshots without Date
            if not sheet_eff:
                sheet_eff = parse_effective_date(effective_date)
            if not sheet_eff:
                from vay.dates import today_ist
                sheet_eff = today_ist().strftime("%Y-%m-%d")

        process_frame(
            store, target, frame, upload_id, holder, ov, save_map,
            event_mode=sheet_mode, dry_run=dry_run, effective_date=sheet_eff or effective_date,
        )
        info = dict(holder.get(target) or {})
        if sheet_eff:
            effective_dates[target] = sheet_eff
            info["effective_date"] = sheet_eff
        sheet_results.append({"sheet": name, "type": target, **info})
        per_type[target] = merge_type_counts(per_type.get(target), info)
        if info.get("error"):
            step["state"] = "failed"
            step["error"] = info["error"]
        else:
            step["state"] = "done"
            for key in ("added", "updated", "upserted", "skipped", "deleted", "would_delete", "skipped_total"):
                if info.get(key):
                    step[key] = info[key]
        done += 1
        emit(name)

    emit("")
    return per_type, sheet_results, effective_dates


def _import_rows_remain(store, job):
    """True when a previous import of this file still has rows loaded."""
    seen = set()
    current = job
    while current:
        rid = str(current.get("_id") or "")
        if rid in seen:
            break
        if rid:
            seen.add(rid)
        upload_id = current.get("upload_id")
        if upload_id and store.count_rows_for_upload(upload_id) > 0:
            return True
        reused = current.get("reused_job_id")
        if not reused or not hasattr(store, "get_import_job"):
            break
        current = store.get_import_job(reused)
    return False


def enqueue_import_job(
    store,
    *,
    filename,
    blob_id,
    content_type,
    maps,
    event_mode,
    permissions,
    file_sha256_hex=None,
    effective_date=None,
    dry_run=False,
):
    active = store.active_import_job()
    if active and not dry_run:
        return None, "An import is already running."
    upload_id = store.insert_upload({
        "filename": filename or "upload.xlsx",
        "gridfs_id": blob_id,
        "type": "combined",
        "content_type": content_type or "application/octet-stream",
        "file_sha256": file_sha256_hex or "",
        "effective_date": parse_effective_date(effective_date),
        "dry_run": bool(dry_run),
    })
    doc = store.insert_import_job({
        "status": "queued",
        "upload_id": upload_id,
        "filename": filename or "upload.xlsx",
        "maps": dict(maps or {}),
        "event_mode": normalize_event_mode(event_mode),
        "permissions": list(permissions or []),
        "progress": {"current": "", "done": 0, "total": 0, "sheets": []},
        "types": {},
        "sheets": [],
        "message": "",
        "file_sha256": file_sha256_hex or "",
        "effective_date": parse_effective_date(effective_date),
        "dry_run": bool(dry_run),
        "row_counts": {},
        "mapper_versions": {},
    })
    return str(doc["_id"]), ""


def run_import_job(store, job_id):
    from server.tenant import DEFAULT_ORG, bind_org
    peeked = store.peek_import_job(job_id) if hasattr(store, "peek_import_job") else None
    org = (peeked or {}).get("org_id") or DEFAULT_ORG
    with bind_org(org):
        _run_import_job(store, job_id)


def _own_import(store, job_id):
    from server.startup import pid_alive

    my = os.getpid()
    job = store.get_import_job(job_id) or {}
    if job.get("status") in ("cancelled", "succeeded", "failed"):
        return False
    owner = job.get("owner_pid")
    if owner == my:
        return True
    if owner and pid_alive(owner):
        return False
    claim = getattr(store, "update_import_job_if", None)
    if not callable(claim):
        store.update_import_job(job_id, {"owner_pid": my, "message": ""})
        return True
    return bool(claim(
        job_id,
        {"status": job.get("status"), "owner_pid": owner},
        {"owner_pid": my, "message": ""},
    ))


def _run_import_job(store, job_id):
    with _import_lock:
        job = store.get_import_job(job_id)
        if not job or job.get("status") == "cancelled":
            return
        if not _own_import(store, job_id):
            return
        dry_run = bool(job.get("dry_run"))
        store.update_import_job(job_id, {"status": "running", "owner_pid": os.getpid(), "message": ""})
        try:
            upload = store.get_upload(job.get("upload_id"))
            if not upload:
                raise RuntimeError("Upload missing")
            blob = store.get_blob(upload.get("gridfs_id"))
            if not blob or not blob.get("data"):
                raise RuntimeError("File missing")
            data = blob["data"]
            sha = upload.get("file_sha256") or file_sha256(data)
            if not upload.get("file_sha256"):
                store.update_upload(job.get("upload_id"), {"file_sha256": sha})
            if not dry_run and hasattr(store, "find_succeeded_import"):
                prior = store.find_succeeded_import(sha, exclude_job_id=job_id)
                if prior and _import_rows_remain(store, prior):
                    store.update_import_job(job_id, {
                        "status": "succeeded",
                        "message": "Already imported",
                        "reused_job_id": str(prior.get("_id")),
                        "file_sha256": sha,
                    })
                    return
            frames = frames_from_bytes(data, job.get("filename") or upload.get("filename") or "")
            overrides = dict(job.get("maps") or {})
            mode = normalize_event_mode(job.get("event_mode"))

            def on_progress(progress, per_type):
                fresh = store.get_import_job(job_id) or {}
                if fresh.get("status") == "cancelled":
                    raise Cancelled()
                store.update_import_job(job_id, {
                    "progress": progress,
                    "types": dict(per_type or {}),
                })

            per_type, sheet_results, effective_dates = process_combined_frames(
                store,
                frames,
                job.get("upload_id"),
                overrides,
                mode=mode,
                permissions=job.get("permissions") or [],
                on_progress=on_progress,
                dry_run=dry_run,
                effective_date=job.get("effective_date") or upload.get("effective_date"),
            )
            mapper_versions = {}
            row_counts = {}
            for t, info in (per_type or {}).items():
                if isinstance(info, dict):
                    if info.get("mapper_version"):
                        mapper_versions[t] = info["mapper_version"]
                    row_counts[t] = {
                        k: info.get(k, 0)
                        for k in (
                            "added", "updated", "upserted", "skipped", "deleted",
                            "would_delete", "skipped_total",
                        )
                        if k in info
                    }
            finished = None if dry_run else now_utc()
            store.update_upload(job.get("upload_id"), {
                "file_sha256": sha,
                "row_counts": row_counts,
                "mapper_versions": mapper_versions,
                "effective_dates": effective_dates,
                "effective_date": (
                    job.get("effective_date")
                    or effective_dates.get("arr")
                    or effective_dates.get("stock")
                    or upload.get("effective_date")
                ),
                **({"finished_at": finished} if finished else {}),
            })
            any_ok = any(not r.get("skipped") and not r.get("error") for r in sheet_results)
            any_fail = any(r.get("error") for r in sheet_results)
            status = "succeeded"
            message = "Dry run preview" if dry_run else ""
            if not any_ok and any_fail:
                status = "failed"
                message = "Import failed"
            elif any_fail:
                message = ("Dry run finished with errors" if dry_run else "Import finished with errors")
            latest = store.get_import_job(job_id) or {}
            progress = dict(latest.get("progress") or {})
            sheets = list(progress.get("sheets") or [])
            work_total = sum(1 for s in sheets if s.get("state") != "skipped")
            work_done = sum(1 for s in sheets if s.get("state") in ("done", "failed"))
            progress.update({"current": "", "done": work_done, "total": work_total, "sheets": sheets})
            # Dry-run must not leave an upload that would delete real rows on undo
            if dry_run:
                # Remove empty dry-run upload record but keep blob refs cleaned
                store.update_upload(job.get("upload_id"), {"dry_run": True, "row_counts": row_counts})
            store.update_import_job(job_id, {
                "status": status,
                "types": per_type,
                "sheets": sheet_results,
                "message": message,
                "progress": progress,
                "file_sha256": sha,
                "row_counts": row_counts,
                "mapper_versions": mapper_versions,
                "effective_dates": effective_dates,
                **({"finished_at": now_utc()} if status == "succeeded" and not dry_run else {}),
            })
        except Cancelled:
            store.update_import_job(job_id, {"status": "cancelled", "message": "Cancelled"})
        except Exception as exc:
            log.exception("import job %s failed", job_id)
            store.update_import_job(job_id, {
                "status": "failed",
                "message": str(exc) or "Import failed",
            })


def import_job_payload(doc):
    if not doc:
        return None
    rid = doc.get("_id")
    return {
        "id": str(rid),
        "status": doc.get("status"),
        "filename": doc.get("filename"),
        "upload_id": str(doc.get("upload_id") or ""),
        "message": doc.get("message") or "",
        "progress": doc.get("progress") or None,
        "types": doc.get("types") or {},
        "sheets": doc.get("sheets") or [],
        "event_mode": doc.get("event_mode") or "skip",
        "created_at": str(doc.get("created_at") or ""),
        "finished_at": str(doc.get("finished_at") or ""),
        "file_sha256": doc.get("file_sha256") or "",
        "row_counts": doc.get("row_counts") or {},
        "mapper_versions": doc.get("mapper_versions") or {},
        "effective_date": doc.get("effective_date") or "",
        "effective_dates": doc.get("effective_dates") or {},
        "dry_run": bool(doc.get("dry_run")),
    }
