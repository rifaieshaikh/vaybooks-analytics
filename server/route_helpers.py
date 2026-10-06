"""Shared, framework-adjacent helpers for API routers."""

from __future__ import annotations

import json
import threading

from vay.export_excel import workbook_bytes_keep_ids

from server.auth import filter_snapshot, redact_manifest
from server.import_jobs import run_import_job
from server.jobs import run_export_job, run_job
from server.run_views import import_newer_than, load_run_views
from server.settings import SESSION_COOKIE, cookie_secure
from server.store import get_store


def cookie_kwargs():
    kwargs = {
        "key": SESSION_COOKIE,
        "httponly": True,
        "samesite": "lax",
        "path": "/",
        "max_age": 7 * 24 * 60 * 60,
    }
    if cookie_secure():
        kwargs["secure"] = True
    return kwargs


def parse_maps(raw):
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k).lower(): v for k, v in data.items() if isinstance(v, dict)}


def pick_frame(frames, type_name):
    if type_name in frames:
        return frames[type_name]
    if "data" in frames and len(frames) == 1:
        return frames["data"]
    if len(frames) == 1:
        return list(frames.values())[0]
    return frames.get(type_name)


def views_for_request(store, params):
    run_id = (params or {}).get("run") or (params or {}).get("run_id") or ""
    run, views = load_run_views(store, run_id or None)
    stale = import_newer_than(store, run) if run else False
    return run, views, stale


def with_stale(payload, stale, run):
    out = dict(payload or {})
    out["import_newer"] = bool(stale)
    if run:
        out["run_id"] = str(run.get("_id") or run.get("id") or "")
        out["report_date"] = run.get("report_date") or ""
    return out


def start_import_job(job_id: str):
    threading.Thread(target=run_import_job, args=(get_store(), job_id), daemon=True).start()


def start_job(run_id: str):
    threading.Thread(target=run_job, args=(get_store(), run_id), daemon=True).start()


def start_export_job(run_id: str):
    threading.Thread(target=run_export_job, args=(get_store(), run_id), daemon=True).start()


def filtered_run_xlsx(store, doc, perms):
    blob = store.get_blob(doc.get("xlsx_id"))
    if not blob or not blob.get("data"):
        return None, "missing"
    json_blob = store.get_blob(doc.get("json_id"))
    if not json_blob or not json_blob.get("data"):
        return None, "forbidden"
    try:
        snapshot = json.loads(json_blob["data"].decode("utf-8"))
    except (TypeError, ValueError, AttributeError, json.JSONDecodeError):
        return None, "forbidden"
    all_reports = snapshot.get("reports") or []
    visible = (filter_snapshot(snapshot, perms) or {}).get("reports") or []
    if not visible:
        return None, "forbidden"
    if len(visible) >= len(all_reports):
        return blob["data"], ""
    data = workbook_bytes_keep_ids(blob["data"], all_reports, [row.get("id") for row in visible])
    if not data:
        return None, "forbidden"
    return data, ""


def _created_iso(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        text = value.isoformat()
        if getattr(value, "tzinfo", None) is None and not text.endswith("Z"):
            text += "Z"
        return text
    return str(value or "")


def run_summary(doc, perms=None):
    manifest = doc.get("manifest") or None
    if manifest is not None and perms is not None:
        manifest = redact_manifest(manifest, perms)
    return {
        "id": str(doc.get("_id")),
        "status": doc.get("status"),
        "message": doc.get("message") or "",
        "packs": doc.get("packs") or {},
        "report_date": doc.get("report_date"),
        "created_at": _created_iso(doc.get("created_at")),
        "fy_label": doc.get("fy_label") or "",
        "report_count": doc.get("report_count") or 0,
        "book_json_id": doc.get("book_json_id") or "",
        "views_split": bool(doc.get("views_split")),
        "generate_progress": doc.get("generate_progress") or None,
        "pdf_catalog": doc.get("pdf_catalog") or [],
        "manifest": manifest,
    }
