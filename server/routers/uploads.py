"""Upload and import-job routes."""

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import JSONResponse

from server.auth import assert_perm, can_import_any, can_upload_type, require_user, type_perm
from server.files import frames_from_bytes
from server.import_jobs import (
    enqueue_import_job,
    import_job_payload,
    process_combined_frames,
    process_frame,
    run_import_job,
)
from server.preview import UPLOAD_TYPES, is_sheet_plan, preview_frames
from server.provenance import file_sha256, normalize_event_mode, parse_effective_date
from server.reconcile import parse_recon_sidecar
from server.route_helpers import parse_maps, pick_frame, start_import_job
from server.settings import MAX_UPLOAD_BYTES, SOURCE_TYPES, sync_jobs
from server.store import get_store
from server.uploads_io import read_upload_limited

router = APIRouter()


@router.post("/api/uploads/preview")
async def preview_upload(
    user=Depends(require_user),
    file: UploadFile = File(...),
    type: str | None = Form(default=None),
    maps: str | None = Form(default=None),
):
    if not can_import_any(user):
        raise HTTPException(403, "Forbidden")
    type_name = (type or "").strip().lower()
    if type_name and type_name not in UPLOAD_TYPES:
        type_name = ""
    if type_name and not can_upload_type(user, type_name):
        raise HTTPException(403, "Forbidden")
    data = await read_upload_limited(file)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    out = preview_frames(get_store(), frames_from_bytes(data, file.filename or ""), type_name or None, parse_maps(maps))
    for sheet in out.get("sheets") or []:
        target = sheet.get("type")
        if sheet.get("skip"):
            sheet["allowed"] = True
            sheet["ready"] = True
            sheet["missing"] = []
            continue
        sheet["allowed"] = bool(target) and can_upload_type(user, target)
        if target and not sheet["allowed"]:
            sheet["ready"] = False
            extra = list(sheet.get("missing") or [])
            if "No permission to import this" not in extra:
                extra.append("No permission to import this")
            sheet["missing"] = extra
    return out


@router.post("/api/uploads")
async def upload(
    user=Depends(require_user),
    file: UploadFile = File(...),
    type: str | None = Form(default=None),
    maps: str | None = Form(default=None),
    event_mode: str | None = Form(default="skip"),
    only_sheet: str | None = Form(default=None),
    effective_date: str | None = Form(default=None),
    dry_run: str | None = Form(default=None),
):
    type_name = (type or "").strip().lower()
    mode = normalize_event_mode(event_mode)
    is_dry = str(dry_run or "").strip().lower() in ("1", "true", "yes")
    overrides = parse_maps(maps)
    only = (only_sheet or "").strip().lower()
    eff = parse_effective_date(effective_date)
    if type_name in SOURCE_TYPES:
        if not can_upload_type(user, type_name):
            raise HTTPException(403, "Forbidden")
    elif not can_import_any(user):
        raise HTTPException(403, "Forbidden")
    data = await read_upload_limited(file)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    store = get_store()
    sha = file_sha256(data)
    frames = frames_from_bytes(data, file.filename or "")
    blob_id = store.put_blob(data, file.filename or "upload.xlsx", file.content_type or "application/octet-stream")
    upload_id = store.insert_upload({
        "filename": file.filename or "upload.xlsx",
        "gridfs_id": blob_id,
        "type": type_name if type_name in SOURCE_TYPES else "combined",
        "file_sha256": sha,
        "effective_date": eff,
        "dry_run": is_dry,
    })
    per_type = {}
    sheet_results = []
    effective_dates = {}
    if type_name in SOURCE_TYPES and not any(is_sheet_plan(v) for v in overrides.values()) and not only:
        frame = pick_frame(frames, type_name)
        if frame is None:
            per_type[type_name] = {"error": "No matching sheet"}
            sheet_results.append({"sheet": type_name, "type": type_name, "error": "No matching sheet"})
        else:
            save_map = type_perm(type_name, "map") in (user.get("permissions") or []) and not is_dry
            process_frame(
                store, type_name, frame, upload_id, per_type, overrides.get(type_name),
                save_map, mode, dry_run=is_dry, effective_date=eff,
            )
            sheet_results.append({"sheet": type_name, "type": type_name, **dict(per_type.get(type_name) or {})})
            if eff:
                effective_dates[type_name] = eff
    else:
        forced = type_name if type_name in UPLOAD_TYPES else None
        per_type, sheet_results, effective_dates = process_combined_frames(
            store, frames, upload_id, overrides, mode=mode,
            permissions=user.get("permissions") or [], forced=forced, only=only or None,
            dry_run=is_dry, effective_date=eff,
        )
    mapper_versions = {}
    row_counts = {}
    types_out = {}
    for t, info in (per_type or {}).items():
        if not isinstance(info, dict):
            types_out[t] = info
            continue
        # Keep preview on sheets only; types stay counts/errors
        types_out[t] = {
            k: v for k, v in info.items()
            if k not in ("preview_rows", "preview_truncated")
        }
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
    store.update_upload(upload_id, {
        "row_counts": row_counts,
        "mapper_versions": mapper_versions,
        "effective_dates": effective_dates,
        "effective_date": eff or effective_dates.get("arr") or effective_dates.get("stock"),
    })
    stored = store.get_upload(upload_id) or {}
    return {
        "id": upload_id,
        "filename": stored.get("filename"),
        "types": types_out,
        "sheets": sheet_results,
        "event_mode": mode,
        "file_sha256": sha,
        "row_counts": row_counts,
        "mapper_versions": mapper_versions,
        "effective_date": stored.get("effective_date") or "",
        "effective_dates": effective_dates,
        "dry_run": is_dry,
    }


@router.post("/api/import-jobs")
async def create_import_job(
    background_tasks: BackgroundTasks,
    user=Depends(require_user),
    file: UploadFile = File(...),
    maps: str | None = Form(default=None),
    event_mode: str | None = Form(default="skip"),
    effective_date: str | None = Form(default=None),
    dry_run: str | None = Form(default=None),
):
    if not can_import_any(user):
        raise HTTPException(403, "Forbidden")
    mode = normalize_event_mode(event_mode)
    is_dry = str(dry_run or "").strip().lower() in ("1", "true", "yes")
    data = await read_upload_limited(file)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    store = get_store()
    sha = file_sha256(data)
    blob_id = store.put_blob(data, file.filename or "upload.xlsx", file.content_type or "application/octet-stream")
    job_id, err = enqueue_import_job(
        store,
        filename=file.filename or "upload.xlsx",
        blob_id=blob_id,
        content_type=file.content_type or "application/octet-stream",
        maps=parse_maps(maps),
        event_mode=mode,
        permissions=user.get("permissions") or [],
        file_sha256_hex=sha,
        effective_date=effective_date,
        dry_run=is_dry,
    )
    if err:
        raise HTTPException(409, err)
    if sync_jobs() or is_dry:
        run_import_job(store, job_id)
        return JSONResponse(import_job_payload(store.get_import_job(job_id)) or {"id": job_id, "status": "succeeded"}, status_code=202)
    background_tasks.add_task(start_import_job, job_id)
    return JSONResponse({"id": job_id, "status": "queued"}, status_code=202)


@router.get("/api/import-jobs/{job_id}")
def get_import_job(job_id: str, user=Depends(require_user)):
    if not can_import_any(user):
        raise HTTPException(403, "Forbidden")
    doc = get_store().get_import_job(job_id)
    if not doc:
        raise HTTPException(404, "Not found")
    return import_job_payload(doc)


@router.post("/api/import-jobs/{job_id}/cancel")
def cancel_import_job(job_id: str, user=Depends(require_user)):
    if not can_import_any(user):
        raise HTTPException(403, "Forbidden")
    store = get_store()
    doc = store.get_import_job(job_id)
    if not doc:
        raise HTTPException(404, "Not found")
    if doc.get("status") not in ("queued", "running"):
        raise HTTPException(409, "Import is not running")
    store.update_import_job(job_id, {"status": "cancelled", "message": "Cancelled"})
    return {"status": "cancelled"}


def _can_see_upload(user, doc):
    kind = doc.get("type") or "combined"
    if kind == "combined":
        return any(p.endswith(".view") or p.endswith(".upload") or p == "settings.import" for p in user["permissions"])
    return type_perm(kind, "view") in user["permissions"] or type_perm(kind, "upload") in user["permissions"]


@router.get("/api/uploads")
def list_uploads(user=Depends(require_user)):
    rows = []
    for doc in get_store().list_uploads():
        if _can_see_upload(user, doc):
            rows.append({
                "id": str(doc.get("_id")),
                "filename": doc.get("filename"),
                "type": doc.get("type"),
                "created_at": str(doc.get("created_at") or ""),
                "file_sha256": doc.get("file_sha256") or "",
                "row_counts": doc.get("row_counts") or {},
                "mapper_versions": doc.get("mapper_versions") or {},
                "effective_date": doc.get("effective_date") or "",
                "effective_dates": doc.get("effective_dates") or {},
            })
    return {"uploads": rows}


@router.get("/api/uploads/{upload_id}/file")
def download_upload(upload_id: str, user=Depends(require_user)):
    store = get_store()
    doc = store.get_upload(upload_id)
    if not doc:
        raise HTTPException(404, "Not found")
    if not _can_see_upload(user, doc):
        raise HTTPException(403, "Forbidden")
    blob = store.get_blob(doc.get("gridfs_id"))
    if not blob:
        raise HTTPException(404, "File missing")
    return Response(
        content=blob["data"],
        media_type=blob.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=%s" % (blob.get("filename") or "file")},
    )


@router.delete("/api/uploads/{upload_id}")
def delete_upload(upload_id: str, user=Depends(require_user)):
    store = get_store()
    doc = store.get_upload(upload_id)
    if not doc:
        raise HTTPException(404, "Not found")
    kind = doc.get("type") or "combined"
    if kind in SOURCE_TYPES:
        assert_perm(user, type_perm(kind, "upload"))
    elif not can_import_any(user):
        raise HTTPException(403, "Forbidden")
    store.delete_upload(upload_id)
    return {"ok": True, "id": upload_id}


@router.post("/api/recon/sidecars")
async def upload_recon_sidecar(
    user=Depends(require_user),
    file: UploadFile = File(...),
):
    """Upload a *.recon.json expected-totals sidecar (no manual amount entry)."""
    if not can_import_any(user):
        raise HTTPException(403, "Forbidden")
    name = (file.filename or "").lower()
    if not name.endswith(".recon.json") and not name.endswith(".json"):
        raise HTTPException(400, "Expected a .recon.json file")
    data = await read_upload_limited(file)
    try:
        payload = parse_recon_sidecar(data)
    except (ValueError, Exception) as exc:
        raise HTTPException(400, str(exc) or "Invalid recon sidecar") from exc
    store = get_store()
    blob_id = store.put_blob(data, file.filename or "expected.recon.json", "application/json")
    doc = store.insert_recon_sidecar({
        "filename": file.filename or "expected.recon.json",
        "blob_id": blob_id,
        "report_date": payload["report_date"],
        "file_sha256": file_sha256(data),
    })
    return {
        "id": str(doc.get("_id")),
        "report_date": payload["report_date"],
        "filename": doc.get("filename"),
        "file_sha256": doc.get("file_sha256"),
    }


@router.get("/api/recon/sidecars")
def list_recon_sidecars(user=Depends(require_user)):
    if not can_import_any(user):
        raise HTTPException(403, "Forbidden")
    rows = []
    for doc in get_store().list_recon_sidecars():
        rows.append({
            "id": str(doc.get("_id")),
            "filename": doc.get("filename"),
            "report_date": doc.get("report_date"),
            "file_sha256": doc.get("file_sha256") or "",
            "created_at": str(doc.get("created_at") or ""),
        })
    return {"sidecars": rows}
