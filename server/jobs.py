"""Async official Create: enqueue, worker thread. Profit packs are not password-gated."""

import json
import logging
import os
import threading
from datetime import datetime

from vay.dates import normalize_date, today_ist
from vay.engine import generate, planned_report_steps
from vay.export_excel import write_workbook

from server.pdf_export import catalog_entries, catalog_rows, dated_folder, export_reports, visible_reports
from server.run_views import build_views_snapshot, invalidate_views_cache
from server.serialize import serialize_result
from server.settings import PACK_PHASES, PACK_TYPES
from server.tables import tables_from_store

log = logging.getLogger("vay.jobs")
_job_lock = threading.Lock()
_exporting_ids = set()
_exporting_lock = threading.Lock()
EXPORT_STALE_AFTER = 15


def phases_from_packs(packs):
    phases = []
    for pack, on in (packs or {}).items():
        if on:
            phases.extend(PACK_PHASES.get(pack) or [])
    out = []
    for p in phases:
        if p not in out:
            out.append(p)
    return out


def types_for_packs(packs):
    names = []
    for pack, on in (packs or {}).items():
        if on:
            for t in PACK_TYPES.get(pack) or []:
                if t not in names:
                    names.append(t)
    return names


def parse_report_date(text):
    if hasattr(text, "year"):
        return normalize_date(datetime(text.year, text.month, text.day, 12))
    parts = str(text).split("-")
    if len(parts) >= 3:
        y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        return datetime(y, m, d, 12)
    return today_ist()


def _restrict_views(views, chosen, perms):
    """Drop 360 pages that were not selected or that this role cannot generate."""
    if not isinstance(views, dict):
        return views
    from server.auth import can_generate

    chosen_set = {str(name) for name in (chosen or []) if name}
    explicit = bool(chosen_set)
    out = dict(views)
    fields = {
        "360-customers": ("directory", "customers"),
        "360-groups": ("groups", "group_details", "group_options"),
        "360-reps": ("reps", "rep_details", "rep_options"),
        "360-items": (
            "items", "item_details", "item_options", "default_min", "default_max_days",
            "low_count", "soon_count", "under_count", "over_count", "dead_count",
            "out_of_stock_count", "buy_count", "buy_qty_sum", "buy_value_sum",
        ),
        "360-business": ("business",),
    }
    for step_id, names in fields.items():
        dropped = explicit and step_id not in chosen_set
        if perms is not None and not can_generate(perms, step_id):
            dropped = True
        if dropped:
            for name in names:
                out.pop(name, None)
    dims = dict(out.get("item_dims") or {})
    for key in list(dims):
        step_id = "360-" + key
        dropped = explicit and step_id not in chosen_set
        if perms is not None and not can_generate(perms, step_id):
            dropped = True
        if dropped:
            dims.pop(key, None)
    out["item_dims"] = dims
    return out


def enqueue_run(store, packs, report_date, reports=None, from_run="", perms=None):
    recover_stale_exports(store)
    active = store.active_run()
    if active:
        return None, "A report is already running."
    if store.active_export():
        return None, "A PDF export is already running."
    doc = store.insert_run({
        "status": "queued",
        "packs": dict(packs or {}),
        "reports": [str(name) for name in (reports or []) if name],
        "from_run": str(from_run or ""),
        "report_perms": list(perms) if perms is not None else None,
        "report_date": str(report_date),
        "message": "",
    })
    return str(doc["_id"]), ""


def _generate_progress(store, run_id, steps, step_id, title, group, state, fraction=0, message=""):
    try:
        frac = float(fraction or 0)
    except (TypeError, ValueError):
        frac = 0
    if state != "running":
        frac = 0
    frac = max(0.0, min(0.99, frac))
    rows = [dict(row) for row in steps]
    found = False
    previous = ""
    prev_title = ""
    prev_fraction = None
    for row in rows:
        if row.get("id") == step_id:
            previous = row.get("state") or ""
            prev_title = row.get("title") or ""
            prev_fraction = row.get("fraction")
            row["state"] = state
            row["title"] = title or row.get("title") or step_id
            row["group"] = group or row.get("group") or ""
            if state == "running":
                row["fraction"] = frac
            else:
                row.pop("fraction", None)
            if state == "failed" and message:
                row["message"] = message
            elif state == "done":
                row.pop("message", None)
            found = True
            break
    if (
        previous == "running"
        and state == "running"
        and (title or step_id) == prev_title
        and frac == prev_fraction
    ):
        return steps
    if not found:
        extra = {"id": step_id, "title": title or step_id, "group": group or "", "state": state}
        if state == "failed" and message:
            extra["message"] = message
        rows.append(extra)
    done = sum(1 for row in rows if row.get("state") in ("done", "failed"))
    current = step_id if state == "running" else ""
    store.update_run(run_id, {
        "generate_progress": {
            "current": current,
            "done": done,
            "total": len(rows),
            "fraction": frac,
            "steps": rows,
        }
    })
    return rows


def _merge_reports(previous, fresh):
    fresh = list(fresh or [])
    by_title = {row.get("title"): row for row in fresh if row.get("title")}
    out = []
    used = set()
    for row in previous or []:
        title = row.get("title")
        if title in by_title:
            out.append(by_title[title])
            used.add(title)
        else:
            out.append(row)
    for row in fresh:
        if row.get("title") not in used:
            out.append(row)
    return out


class _LedgerStore:
    """Read source rows from one preload. Writes still go to the real store."""

    def __init__(self, store, docs):
        self._store = store
        self._docs = docs

    def rows_of_type(self, type_name):
        if type_name in self._docs:
            return list(self._docs[type_name])
        return self._store.rows_of_type(type_name)

    def __getattr__(self, name):
        return getattr(self._store, name)


def _ledger_store(store, types):
    from server.customers import NOTE_TYPE
    names = set(types or [])
    names.update(["sales", "receipt", "credit_note", "arr", "items", "stock", "customer", "party", "payments", NOTE_TYPE])
    docs = {}
    for name in names:
        docs[name] = store.rows_of_type(name)
    return _LedgerStore(store, docs)


class Cancelled(Exception):
    pass


def run_job(store, run_id):
    from server.tenant import DEFAULT_ORG, bind_org
    peeked = store.peek_run(run_id) if hasattr(store, "peek_run") else None
    org = (peeked or {}).get("org_id") or DEFAULT_ORG
    with bind_org(org):
        _run_job(store, run_id)


def _own_run(store, run_id):
    """Claim this create for the current process. A live owner keeps it."""
    from server.startup import pid_alive

    my = os.getpid()
    run = store.get_run(run_id) or {}
    if run.get("status") in ("cancelled", "succeeded", "failed"):
        return False
    owner = run.get("owner_pid")
    if owner == my:
        return True
    if owner and pid_alive(owner):
        return False
    claim = getattr(store, "update_run_if", None)
    if not callable(claim):
        store.update_run(run_id, {"owner_pid": my, "message": ""})
        return True
    return bool(claim(
        run_id,
        {"status": run.get("status"), "owner_pid": owner},
        {"owner_pid": my, "message": ""},
    ))


def _run_job(store, run_id):
    with _job_lock:
        run = store.get_run(run_id)
        if not run or run.get("status") == "cancelled":
            return
        if not _own_run(store, run_id):
            return
        packs = (run or {}).get("packs") or {}
        chosen = [str(name) for name in ((run or {}).get("reports") or []) if name]
        steps = planned_report_steps(packs, chosen or None)
        if (run or {}).get("weekly"):
            save_at = next((i for i, row in enumerate(steps) if row.get("id") == "save-reports"), len(steps))
            steps.insert(save_at, {"id": "weekly-sheets", "title": "Weekly sheets", "group": "Checks", "state": "waiting"})
        store.update_run(run_id, {
            "status": "running",
            "generate_progress": {
                "current": "",
                "done": 0,
                "total": len(steps),
                "fraction": 0,
                "steps": steps,
            },
        })
        run = store.get_run(run_id)
        try:
            packs = (run or {}).get("packs") or {}
            chosen = [str(name) for name in ((run or {}).get("reports") or []) if name]
            from_run = str((run or {}).get("from_run") or "")
            dt = parse_report_date((run or {}).get("report_date"))
            types = types_for_packs(packs)
            phases = phases_from_packs(packs)
            work = _ledger_store(store, types)

            def on_progress(step_id, title, group, state, fraction=0, message=""):
                nonlocal steps
                fresh = store.get_run(run_id) or {}
                if fresh.get("status") == "cancelled":
                    raise Cancelled()
                steps = _generate_progress(
                    store, run_id, steps, step_id, title, group, state,
                    fraction=fraction, message=message,
                )

            from server.customers import get_aging_bands, get_settlement_mode
            from server.org_policy import get_org_policy, org_policy_for_generate
            from server.reconcile import (
                arr_effective_date_warning,
                attach_snapshot_warnings,
                find_sidecar_for_date,
                reconcile,
            )
            from vay.eligibility import evaluate
            from vay.metrics import metric_versions

            org_policy = org_policy_for_generate(store)
            tables = tables_from_store(work, types)
            result = generate(
                tables, dt, phases,
                on_progress=on_progress,
                settlement_mode=get_settlement_mode(store),
                aging_bands=get_aging_bands(store),
                org_policy=org_policy,
                only_reports=chosen or None,
            )
            if from_run:
                previous = snapshot_reports(store, store.get_run(from_run) or {})
                result["reports"] = _merge_reports(previous, result.get("reports") or [])

            def on_360(step_id, title, group, state, fraction=0, message="", *_ignored):
                on_progress(step_id, title, group, state, fraction, message)

            want_360 = (not chosen) or any(str(name).startswith("360-") for name in chosen)
            report_perms = (run or {}).get("report_perms")
            from server.auth import can_generate
            include_repurchase = (not chosen) or ("360-repurchase" in chosen)
            if report_perms is not None:
                include_repurchase = include_repurchase and can_generate(report_perms, "360-repurchase")
            only_steps = set(chosen) if chosen else None
            if only_steps is None and report_perms is not None:
                only_steps = {
                    step_id for step_id in (
                        "360-customers", "360-groups", "360-reps", "360-items",
                        "360-category", "360-item_group", "360-brand", "360-supplier",
                        "360-repurchase", "360-business",
                    ) if can_generate(report_perms, step_id)
                }
            views = {}
            store._force_as_of = dt
            store._360_book = None
            try:
                if want_360:
                    views = build_views_snapshot(
                        work,
                        on_progress=on_360,
                        include_repurchase=include_repurchase,
                        only=only_steps,
                    ) or {}
                    custs = views.get("customers") or {}
                    if not custs:
                        raise RuntimeError("Create 360 snapshot has no customers")
                    missing = [
                        uk for uk, d in custs.items()
                        if not isinstance((d or {}).get("settlements"), dict)
                        or not isinstance((d.get("settlements") or {}).get("months"), list)
                    ]
                    if missing:
                        raise RuntimeError(
                            "Create 360 snapshot missing settlements for %d customers (e.g. %s)"
                            % (len(missing), missing[0])
                        )
                elif from_run and hasattr(store, "copy_view_parts"):
                    store.copy_view_parts(from_run, run_id)
                    store.update_run(run_id, {"views_split": True})
                    from server.view_parts import SnapshotViews
                    views = SnapshotViews(store, run_id)
            except Exception as exc:
                on_progress("360-customers", "Customers 360", "360 View", "failed", message=str(exc))
                views = views or {}
            finally:
                store._force_as_of = None
                store._360_book = None

            report_date_s = dt.strftime("%Y-%m-%d")
            recon_result = {"status": "unavailable", "message": "", "exceptions": []}
            eligibility = {}
            phase2 = {}
            dashboard_doc = None
            xlsx_id = ""
            json_id = ""
            run_checks = (not chosen) or any(name in ("reconcile", "analytics", "dashboard", "save-reports") for name in chosen)
            if not chosen or "reconcile" in chosen or run_checks:
                try:
                    on_progress("reconcile", "Reconciliation", "Checks", "running")
                    _sidecar_doc, sidecar_payload = find_sidecar_for_date(work, report_date_s)
                    recon_result = reconcile(work, sidecar_payload, report_date=report_date_s, org_policy=org_policy)
                    asof_warnings = arr_effective_date_warning(work, report_date_s)
                    recon_result = attach_snapshot_warnings(recon_result, asof_warnings)
                    eligibility = evaluate(work, report_date_s)
                    on_progress("reconcile", "Reconciliation", "Checks", "done")
                except Exception as exc:
                    on_progress("reconcile", "Reconciliation", "Checks", "failed", message=str(exc))
            phase2_steps = (
                ("phase2_scorecard", "Scorecard", "Scorecard"),
                ("phase2_sales_change", "Sales change", "Scorecard"),
                ("phase2_customer_movement", "Customer movement", "Scorecard"),
                ("phase2_collection", "Collection worklist", "Follow-up"),
                ("phase2_stock", "Stock decisions", "Items"),
                ("phase2_quality", "Data quality", "Data issues"),
            )
            phase2_wanted = [row for row in phase2_steps if not chosen or row[0] in chosen]
            if report_perms is not None:
                phase2_wanted = [row for row in phase2_wanted if can_generate(report_perms, row[0])]
            try:
                on_progress("analytics", "Scorecard, sales change, and data checks", "Checks", "running")
                from server.phase2 import build_bundle, excel_reports, open_review_count
                phase2 = build_bundle(
                    work,
                    report_date_s,
                    exceptions=recon_result.get("exceptions") or [],
                    review_count=open_review_count(work),
                    prepared={
                        "ctx": result.get("ctx"),
                        "tables": tables,
                        "policy": org_policy,
                        "eligibility": eligibility or None,
                    },
                )
                sheets = excel_reports(phase2)
                wanted_ids = {row[0] for row in phase2_wanted}
                if chosen or report_perms is not None:
                    sheets = [sheet for sheet in sheets if sheet.get("id") in wanted_ids]
                result.setdefault("reports", []).extend(sheets)
                for step_id, title, group in phase2_wanted:
                    on_progress(step_id, title, group, "done")
                if (store.get_run(run_id) or {}).get("weekly"):
                    on_progress("weekly-sheets", "Weekly sheets", "Checks", "running")
                    from server.saved_reports import scheduled_sheets
                    result.setdefault("reports", []).extend(scheduled_sheets(work, report_date_s))
                    on_progress("weekly-sheets", "Weekly sheets", "Checks", "done")
                on_progress("analytics", "Scorecard, sales change, and data checks", "Checks", "done")
            except Exception as exc:
                on_progress("analytics", "Scorecard, sales change, and data checks", "Checks", "failed", message=str(exc))
                for step_id, title, group in phase2_wanted:
                    on_progress(step_id, title, group, "failed", message=str(exc))
            if report_perms is not None:
                from server.auth import report_allowed
                result["reports"] = [
                    report for report in (result.get("reports") or []) if report_allowed(report, report_perms)
                ]
            keep_business = isinstance(views, dict) and (want_360 or not from_run)
            if chosen and "360-business" not in set(chosen):
                keep_business = False
            if report_perms is not None and not can_generate(report_perms, "360-business"):
                keep_business = False
            if keep_business:
                try:
                    on_progress("360-business", "Business 360", "360 View", "running")
                    from server.business360 import build_business
                    views["business"] = build_business(
                        work,
                        result.get("reports") or [],
                        phase2,
                        views,
                        report_date=report_date_s,
                        fy_label=result.get("fy_label") or "",
                    )
                    on_progress("360-business", "Business 360", "360 View", "done")
                except Exception as exc:
                    on_progress("360-business", "Business 360", "360 View", "failed", message=str(exc))
            if report_perms is not None:
                views = _restrict_views(views, chosen, report_perms)
            elif chosen:
                views = _restrict_views(views, chosen, None)
            try:
                on_progress("dashboard", "Home dashboard", "Checks", "running")
                from server.auth import ALL_PERMISSIONS
                from server.dashboard import build_dashboard
                snapshot = serialize_result(result)
                run_doc = dict(store.get_run(run_id) or {})
                run_doc["report_date"] = report_date_s
                run_doc["fy_label"] = snapshot.get("fy_label") or ""
                run_doc["status"] = "succeeded"
                run_doc["manifest"] = {
                    "eligibility": eligibility,
                    "reconciliation": recon_result,
                }
                dashboard_doc = build_dashboard(
                    work,
                    ALL_PERMISSIONS,
                    prepared={"run": run_doc, "snapshot": snapshot, "views": views},
                )
                on_progress("dashboard", "Home dashboard", "Checks", "done")
            except Exception as exc:
                snapshot = serialize_result(result)
                on_progress("dashboard", "Home dashboard", "Checks", "failed", message=str(exc))
            try:
                on_progress("save-reports", "Save workbook", "Checks", "running")
                if isinstance(views, dict) and (
                    views.get("customers") or views.get("items") or views.get("item_dims")
                    or views.get("groups") or views.get("reps") or views.get("business")
                ):
                    from server.view_parts import save_view_parts

                    def on_save(fraction, label):
                        on_progress(
                            "save-reports",
                            "Saving %s" % label,
                            "Checks",
                            "running",
                            fraction=fraction,
                        )

                    save_view_parts(store, run_id, views, on_progress=on_save)
                xlsx = write_workbook(result.get("reports") or [])
                xlsx_id = store.put_blob(
                    xlsx,
                    "vay_reports_%s.xlsx" % dt.strftime("%Y-%m-%d"),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                json_id = store.put_blob(
                    json.dumps(snapshot, default=str).encode("utf-8"),
                    "vay_reports_%s.json" % dt.strftime("%Y-%m-%d"),
                    "application/json",
                )
                on_progress("save-reports", "Save workbook", "Checks", "done")
            except Exception as exc:
                on_progress("save-reports", "Save workbook", "Checks", "failed", message=str(exc))

            upload_summaries = []
            for up in store.list_uploads():
                if up.get("dry_run"):
                    continue
                upload_summaries.append({
                    "id": str(up.get("_id")),
                    "filename": up.get("filename"),
                    "type": up.get("type"),
                    "file_sha256": up.get("file_sha256") or "",
                    "row_counts": up.get("row_counts") or {},
                    "mapper_versions": up.get("mapper_versions") or {},
                    "effective_date": up.get("effective_date") or "",
                    "effective_dates": up.get("effective_dates") or {},
                })
            policy_public = get_org_policy(store)
            manifest = {
                "report_date": report_date_s,
                "packs": dict(packs or {}),
                "data_version": {
                    "uploads": upload_summaries,
                    "types_used": list(types),
                },
                "calculation_version": {
                    "engine": "vay.engine.generate",
                    "org_policy": {
                        "fiscal_year_start_month": policy_public.get("fiscal_year_start_month"),
                        "sales_tax_inclusive_rate": policy_public.get("sales_tax_inclusive_rate"),
                        "expense_pack": policy_public.get("expense_pack"),
                        "timezone": policy_public.get("timezone"),
                        "currency_code": policy_public.get("currency_code"),
                    },
                    "metric_ids": ["sales_mtd", "sales_ytd", "ar_balance"],
                    "metrics": metric_versions(),
                },
                "eligibility": eligibility,
                "reconciliation": recon_result,
            }

            failed_steps = [row for row in steps if row.get("state") == "failed"]
            usable = bool(result.get("reports")) or bool(xlsx_id)
            summary = ""
            if failed_steps:
                summary = "%d failed: %s" % (
                    len(failed_steps),
                    "; ".join(
                        "%s — %s" % (row.get("title") or row.get("id"), row.get("message") or "failed")
                        for row in failed_steps[:6]
                    ),
                )
            store.update_run(run_id, {
                "status": "succeeded" if usable else "failed",
                "message": "" if usable and not failed_steps else (summary or "Could not create reports."),
                "dashboard": dashboard_doc,
                "xlsx_id": xlsx_id,
                "json_id": json_id,
                "book_json_id": "",
                "views_split": bool(isinstance(views, dict) and views.get("customers")) or bool(from_run and not want_360),
                "fy_label": snapshot.get("fy_label") or "",
                "report_count": len(snapshot.get("reports") or []),
                "pdf_catalog": catalog_entries(snapshot.get("reports") or []),
                "manifest": manifest,
                "generate_progress": {
                    "current": "",
                    "done": sum(1 for row in steps if row.get("state") in ("done", "failed")),
                    "total": len(steps),
                    "fraction": 0,
                    "steps": steps,
                },
            })
            invalidate_views_cache()
        except Cancelled:
            store.update_run(run_id, {"status": "cancelled", "message": "Cancelled"})
        except Exception as exc:
            log.exception("run failed")
            store.update_run(run_id, {"status": "failed", "message": str(exc)})


def snapshot_reports(store, run):
    blob = store.get_blob((run or {}).get("json_id"))
    if not blob:
        return []
    data = json.loads(blob["data"].decode("utf-8"))
    return data.get("reports") or []


def _as_dt(value):
    if value is None or value == "":
        return None
    if hasattr(value, "year"):
        if getattr(value, "tzinfo", None) is not None:
            return value.replace(tzinfo=None)
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except ValueError:
        return None


def export_is_live(run_id):
    with _exporting_lock:
        return str(run_id) in _exporting_ids


def export_is_stale(run):
    run = run or {}
    if run.get("pdf_export_status") not in ("queued", "running"):
        return False
    if export_is_live(run.get("_id")):
        return False
    hb = _as_dt(run.get("pdf_export_heartbeat"))
    if hb is None:
        return True
    return (datetime.utcnow() - hb).total_seconds() > EXPORT_STALE_AFTER


def recover_stale_exports(store):
    active = store.active_export()
    if not active or not export_is_stale(active):
        return
    store.update_run(str(active.get("_id")), {
        "pdf_export_status": "failed",
        "pdf_export_message": "Export stopped before it finished. Click Generate to try again.",
        "pdf_export_heartbeat": datetime.utcnow(),
    })


def catalog_for_run(store, run):
    run = run or {}
    catalog = list(run.get("pdf_catalog") or [])
    if catalog:
        return catalog
    progress_rows = (run.get("pdf_export_progress") or {}).get("reports") or []
    if progress_rows:
        return [{
            "id": row.get("id") or "",
            "title": row.get("title") or "",
            "group": row.get("group") or "",
        } for row in progress_rows]
    catalog = catalog_entries(snapshot_reports(store, run))
    rid = run.get("_id")
    if catalog and rid:
        store.update_run(str(rid), {"pdf_catalog": catalog})
        run["pdf_catalog"] = catalog
    return catalog


def export_payload(store, run, perms=None):
    recover_stale_exports(store)
    if store and run and run.get("_id"):
        run = store.get_run(run.get("_id")) or run
    run = run or {}
    status = run.get("pdf_export_status") or ""
    zip_id = run.get("pdf_zip_id")
    visible = visible_reports(catalog_for_run(store, run), perms)
    folder_path = None
    folder = run.get("pdf_export_folder") or ""
    try:
        dt = parse_report_date(run.get("report_date"))
        folder_path, folder_name = dated_folder(dt)
        folder = folder or ("vay_reports/%s" % folder_name)
    except Exception:
        folder_path = None
    progress = run.get("pdf_export_progress") or {}
    return {
        "status": status,
        "message": run.get("pdf_export_message") or "",
        "count": int(run.get("pdf_export_count") or 0),
        "skipped": int(run.get("pdf_export_skipped") or 0),
        "failed": int(run.get("pdf_export_failed") or 0),
        "folder": folder,
        "zip_ready": bool(zip_id) and status == "succeeded",
        "current": progress.get("current") or "",
        "done": int(progress.get("done") or 0),
        "total": int(progress.get("total") or 0),
        "reports": catalog_rows(visible, folder_path, progress),
    }


def enqueue_export(store, run_id, ids=None, perms=None):
    recover_stale_exports(store)
    run = store.get_run(run_id)
    if not run:
        return None, False, "not_found"
    if run.get("status") != "succeeded":
        return None, False, "not_ready"
    if store.active_run():
        return None, False, "A report is already running."
    if store.active_export():
        return None, False, "A PDF export is already running."
    catalog = catalog_for_run(store, run)
    visible = visible_reports(catalog, perms)
    want = set(ids or [])
    selected = [report for report in visible if report.get("id") in want]
    if not selected:
        return None, False, "no_reports"
    dt = parse_report_date(run.get("report_date"))
    folder_path, folder_name = dated_folder(dt)
    selected_ids = [report.get("id") for report in selected]
    selected_set = set(selected_ids)
    rows = catalog_rows(visible, folder_path, {})
    for row in rows:
        if row.get("id") in selected_set:
            row["state"] = "waiting"
    now = datetime.utcnow()
    store.update_run(run_id, {
        "pdf_export_status": "queued",
        "pdf_export_message": "",
        "pdf_export_replace": True,
        "pdf_export_ids": selected_ids,
        "pdf_export_heartbeat": now,
        "pdf_export_progress": {
            "current": "",
            "done": 0,
            "total": len(selected_ids),
            "reports": rows,
        },
    })
    return export_payload(store, store.get_run(run_id), perms), True, ""


def _export_progress(store, run_id, selected_ids, index, report, state):
    run = store.get_run(run_id) or {}
    progress = dict(run.get("pdf_export_progress") or {})
    rows = [dict(row) for row in (progress.get("reports") or [])]
    rid = (report or {}).get("id")
    if rid:
        for row in rows:
            if row.get("id") == rid:
                row["state"] = state
                if state == "done":
                    row["exists"] = True
                break
    wanted = set(selected_ids or [])
    done = sum(1 for row in rows if row.get("id") in wanted and row.get("state") in ("done", "failed"))
    current = "zip" if state == "zip" else (rid if state == "running" else (progress.get("current") or ""))
    store.update_run(run_id, {
        "pdf_export_heartbeat": datetime.utcnow(),
        "pdf_export_progress": {
            "current": current,
            "done": done,
            "total": len(selected_ids or []),
            "reports": rows,
        }
    })


def _own_export(store, run_id):
    from server.startup import pid_alive

    my = os.getpid()
    run = store.get_run(run_id) or {}
    if run.get("pdf_export_status") not in ("queued", "running"):
        return False
    owner = run.get("pdf_export_owner_pid")
    if owner == my:
        return True
    if owner and pid_alive(owner):
        return False
    claim = getattr(store, "update_run_if", None)
    fields = {"pdf_export_owner_pid": my, "pdf_export_message": ""}
    if not callable(claim):
        store.update_run(run_id, fields)
        return True
    return bool(claim(
        run_id,
        {"pdf_export_status": run.get("pdf_export_status"), "pdf_export_owner_pid": owner},
        fields,
    ))


def run_export_job(store, run_id):
    rid = str(run_id)
    with _exporting_lock:
        _exporting_ids.add(rid)
    try:
        with _job_lock:
            if not _own_export(store, run_id):
                return
            store.update_run(run_id, {
                "pdf_export_status": "running",
                "pdf_export_owner_pid": os.getpid(),
                "pdf_export_heartbeat": datetime.utcnow(),
            })
            run = store.get_run(run_id)
            try:
                all_reports = snapshot_reports(store, run)
                selected_ids = list((run or {}).get("pdf_export_ids") or [])
                want = set(selected_ids)
                selected = [report for report in all_reports if report.get("id") in want] if want else list(all_reports)
                if not selected:
                    raise ValueError("Select at least one report you can view.")
                if not selected_ids:
                    selected_ids = [report.get("id") for report in selected]
                dt = parse_report_date((run or {}).get("report_date"))

                def on_progress(index, report, state):
                    _export_progress(store, run_id, selected_ids, index, report, state)

                result = export_reports(
                    selected,
                    dt,
                    replace=True,
                    zip_reports=selected,
                    on_progress=on_progress,
                )
                zip_id = store.put_blob(result["zip_bytes"], result["zip_name"], "application/zip")
                run = store.get_run(run_id) or {}
                progress = dict(run.get("pdf_export_progress") or {})
                progress["current"] = ""
                progress["done"] = int(progress.get("total") or len(selected_ids))
                store.update_run(run_id, {
                    "pdf_export_status": "succeeded",
                    "pdf_export_message": result["message"],
                    "pdf_export_count": result["count"],
                    "pdf_export_skipped": result["skipped"],
                    "pdf_export_failed": result["failed"],
                    "pdf_export_folder": result["folder"],
                    "pdf_zip_id": zip_id,
                    "pdf_export_replace": False,
                    "pdf_export_heartbeat": datetime.utcnow(),
                    "pdf_export_progress": progress,
                })
            except Exception as exc:
                log.exception("pdf export failed")
                store.update_run(run_id, {
                    "pdf_export_status": "failed",
                    "pdf_export_message": str(exc),
                    "pdf_export_heartbeat": datetime.utcnow(),
                })
    finally:
        with _exporting_lock:
            _exporting_ids.discard(rid)
