"""Report run and PDF export routes."""

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from vay.engine import planned_report_steps

from server.auth import assert_perm, filter_report_ids, filter_snapshot, require_user
from server.jobs import enqueue_export, enqueue_run, export_payload, run_export_job, run_job, snapshot_reports
from server.pdf_export import pdf_filename, visible_reports, zip_keep_names
from server.route_helpers import filtered_run_xlsx, run_summary, start_export_job, start_job
from server.schemas import ExportPdfBody, RunBody
from server.settings import sync_jobs
from server.store import get_store

router = APIRouter()


@router.get("/api/runs")
def list_runs(request: Request, user=Depends(require_user)):
    if not any(p.startswith("reports.") for p in user["permissions"]):
        raise HTTPException(403, "Forbidden")
    docs = get_store().list_runs()
    try:
        limit = int(request.query_params.get("limit") or 50)
        page = int(request.query_params.get("page") or 1)
    except (TypeError, ValueError):
        limit, page = 50, 1
    limit = max(1, min(limit, 200))
    page = max(1, page)
    start = (page - 1) * limit
    page_docs = docs[start:start + limit]
    return {
        "runs": [_list_summary(doc, user["permissions"]) for doc in page_docs],
        "total": len(docs),
        "page": page,
        "limit": limit,
    }


@router.post("/api/runs")
def create_run(body: RunBody, background_tasks: BackgroundTasks, user=Depends(require_user)):
    assert_perm(user, "reports.create")
    store = get_store()
    requested = [str(name) for name in (body.reports or []) if name]
    reports = filter_report_ids(requested, user["permissions"]) if requested else []
    if requested and not reports:
        raise HTTPException(403, "No reports you can create")
    steps = planned_report_steps(body.packs, reports or None)
    progress = {
        "current": "",
        "done": 0,
        "total": len(steps),
        "fraction": 0,
        "steps": steps,
    }
    status = "queued"
    run_id, err = enqueue_run(
        store, body.packs, body.report_date, reports, body.from_run, perms=user["permissions"],
    )
    if err:
        raise HTTPException(409, err)
    if sync_jobs():
        run_job(store, run_id)
        doc = store.get_run(run_id) or {}
        status = doc.get("status") or status
        if doc.get("generate_progress"):
            progress = doc.get("generate_progress")
    else:
        background_tasks.add_task(start_job, run_id)
    from server.audit import record
    record(store, "create", user.get("username") or "", "Create %s" % body.report_date)
    return JSONResponse(
        {"id": run_id, "status": status, "generate_progress": progress},
        status_code=202,
    )


@router.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str, user=Depends(require_user)):
    assert_perm(user, "reports.create")
    store = get_store()
    doc = store.get_run(run_id)
    if not doc:
        raise HTTPException(404, "Not found")
    if doc.get("status") not in ("queued", "running"):
        raise HTTPException(409, "Report is not running")
    store.update_run(run_id, {"status": "cancelled", "message": "Cancelled"})
    from server.audit import record
    record(store, "cancel", user.get("username") or "", run_id)
    return {"status": "cancelled"}


def _list_summary(doc, perms):
    """Run list for the snapshot picker. Upload hashes stay on the single-run read."""
    summary = run_summary(doc, perms)
    manifest = summary.get("manifest")
    if isinstance(manifest, dict):
        version = manifest.get("data_version")
        if isinstance(version, dict) and version.get("uploads"):
            manifest = dict(manifest)
            version = dict(version)
            version.pop("uploads", None)
            manifest["data_version"] = version
            summary["manifest"] = manifest
    return summary


def _wants_snapshot(request: Request):
    flag = (request.query_params.get("snapshot") or "1").lower()
    return flag not in ("0", "false", "no")


@router.get("/api/runs/{run_id}")
def get_run(run_id: str, request: Request, user=Depends(require_user)):
    if not any(p.startswith("reports.") for p in user["permissions"]):
        raise HTTPException(403, "Forbidden")
    store = get_store()
    doc = store.get_run(run_id)
    if not doc:
        raise HTTPException(404, "Not found")
    out = run_summary(doc, user["permissions"])
    if "password" in doc:
        raise HTTPException(500, "password leaked")
    if _wants_snapshot(request) and doc.get("status") == "succeeded" and doc.get("json_id"):
        blob = store.get_blob(doc["json_id"])
        if blob:
            out["snapshot"] = filter_snapshot(json.loads(blob["data"].decode("utf-8")), user["permissions"])
    return out


@router.get("/api/runs/{run_id}/file")
def get_run_file(run_id: str, user=Depends(require_user)):
    store = get_store()
    doc = store.get_run(run_id)
    if not doc:
        raise HTTPException(404, "Not found")
    if not any(p.startswith("reports.view.") or p == "reports.create" for p in user["permissions"]):
        raise HTTPException(403, "Forbidden")
    if doc.get("status") != "succeeded":
        raise HTTPException(409, "Report is not ready")
    data, err = filtered_run_xlsx(store, doc, user["permissions"])
    if err == "missing" or not data:
        if err == "forbidden":
            raise HTTPException(403, "No reports you can download in this run")
        raise HTTPException(404, "File missing")
    blob = store.get_blob(doc.get("xlsx_id")) or {}
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=%s" % (blob.get("filename") or "reports.xlsx")},
    )


@router.get("/api/runs/{run_id}/export-pdf")
def get_run_export(run_id: str, user=Depends(require_user)):
    if not any(p.startswith("reports.") for p in user["permissions"]):
        raise HTTPException(403, "Forbidden")
    store = get_store()
    doc = store.get_run(run_id)
    if not doc:
        raise HTTPException(404, "Not found")
    return export_payload(store, doc, user["permissions"])


@router.post("/api/runs/{run_id}/export-pdf")
def post_run_export(run_id: str, payload: ExportPdfBody, user=Depends(require_user)):
    assert_perm(user, "reports.create")
    store = get_store()
    result, needs_job, err = enqueue_export(store, run_id, ids=payload.ids, perms=user["permissions"])
    if err == "not_found":
        raise HTTPException(404, "Not found")
    if err == "not_ready":
        raise HTTPException(409, "Report is not ready")
    if err == "no_reports":
        raise HTTPException(400, "Select at least one report you can view.")
    if err:
        raise HTTPException(409, err)
    if needs_job:
        if sync_jobs():
            run_export_job(store, run_id)
            return JSONResponse(export_payload(store, store.get_run(run_id), user["permissions"]), status_code=202)
        start_export_job(run_id)
        return JSONResponse(result, status_code=202)
    return result


@router.get("/api/runs/{run_id}/export-pdf/file")
def get_run_export_file(run_id: str, user=Depends(require_user)):
    store = get_store()
    doc = store.get_run(run_id)
    if not doc:
        raise HTTPException(404, "Not found")
    if not any(p.startswith("reports.view.") or p == "reports.create" for p in user["permissions"]):
        raise HTTPException(403, "Forbidden")
    if doc.get("status") != "succeeded":
        raise HTTPException(409, "Report is not ready")
    if doc.get("pdf_export_status") != "succeeded":
        raise HTTPException(409, "PDF export is not ready")
    blob = store.get_blob(doc.get("pdf_zip_id"))
    if not blob:
        raise HTTPException(404, "File missing")
    data = blob["data"]
    try:
        reports = snapshot_reports(store, doc)
    except (TypeError, ValueError, AttributeError, json.JSONDecodeError):
        raise HTTPException(403, "No reports you can download in this run")
    if not reports:
        raise HTTPException(403, "No reports you can download in this run")
    visible = visible_reports(reports, user["permissions"])
    selected_ids = list(doc.get("pdf_export_ids") or [])
    if selected_ids:
        wanted = set(selected_ids)
        visible = [report for report in visible if report.get("id") in wanted]
    if not visible:
        raise HTTPException(403, "No reports you can download in this run")
    data = zip_keep_names(data, {pdf_filename(report.get("id")) for report in visible})
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=%s" % (blob.get("filename") or "vay_reports.zip")},
    )
