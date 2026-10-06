"""Startup housekeeping for background jobs left behind by a previous process."""

from __future__ import annotations

import os
from datetime import datetime, timedelta


# A create that was just queued may not have recorded an owner yet.
_FRESH_SECONDS = 20


def pid_alive(pid) -> bool:
    """True when `pid` is a running process this user can see."""
    try:
        pid = int(pid or 0)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes
        handle = ctypes.windll.kernel32.OpenProcess(0x00100000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


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


def _fresh(value, now):
    stamp = _as_dt(value)
    if stamp is None:
        return False
    return now - stamp < timedelta(seconds=_FRESH_SECONDS)


def fail_orphaned_jobs(store) -> dict:
    """Resume work whose owner process is dead. Leave a live owner's job alone.

    A second API on the same database must not fail a create that is still running.
    """
    from server.tenant import unscoped
    with unscoped():
        return _resume_orphaned_jobs(store)


def _claim(store, updater, doc_id, match, fields):
    claim = getattr(store, updater, None)
    if not callable(claim):
        return False
    return bool(claim(doc_id, match, fields))


def _resume_orphaned_jobs(store) -> dict:
    now = datetime.utcnow()
    my = os.getpid()
    run_ids = []
    export_ids = []
    import_ids = []

    for doc in list(store.list_runs() or []):
        rid = str(doc.get("_id") or doc.get("id") or "")
        if not rid:
            continue
        status = doc.get("status")
        if status in ("queued", "running"):
            if _claim_run(store, doc, rid, my, now):
                run_ids.append(rid)
            continue
        if doc.get("pdf_export_status") in ("queued", "running") and _claim_export(store, doc, rid, my, now):
            export_ids.append(rid)

    list_fn = getattr(store, "list_import_jobs", None)
    docs = list(list_fn() or []) if callable(list_fn) else []
    if not docs:
        active = store.active_import_job() if hasattr(store, "active_import_job") else None
        if active:
            docs = [active]
    for doc in docs:
        if doc.get("status") not in ("queued", "running"):
            continue
        jid = str(doc.get("_id") or doc.get("id") or "")
        if jid and _claim_import(store, doc, jid, my, now):
            import_ids.append(jid)

    return {
        "runs": len(run_ids),
        "exports": len(export_ids),
        "imports": len(import_ids),
        "run_ids": run_ids,
        "export_ids": export_ids,
        "import_ids": import_ids,
    }


def _should_take(owner, status, created_at, now):
    """Take a job only when its worker is gone. A live pid, or a create that just queued, stays put."""
    if owner and pid_alive(owner):
        return False
    if owner:
        return True
    if status == "running":
        return False
    return not _fresh(created_at, now)


def _claim_run(store, doc, rid, my, now):
    status = doc.get("status")
    owner = doc.get("owner_pid")
    if not _should_take(owner, status, doc.get("created_at"), now):
        return False
    return _claim(store, "update_run_if", rid, {"status": status, "owner_pid": owner}, {
        "status": "queued",
        "owner_pid": my,
        "message": "",
    })


def _claim_export(store, doc, rid, my, now):
    status = doc.get("pdf_export_status")
    owner = doc.get("pdf_export_owner_pid")
    if not _should_take(owner, status, doc.get("pdf_export_heartbeat") or doc.get("created_at"), now):
        return False
    return _claim(store, "update_run_if", rid, {"pdf_export_status": status, "pdf_export_owner_pid": owner}, {
        "pdf_export_status": "queued",
        "pdf_export_owner_pid": my,
        "pdf_export_message": "",
    })


def _claim_import(store, doc, jid, my, now):
    status = doc.get("status")
    owner = doc.get("owner_pid")
    if not _should_take(owner, status, doc.get("created_at"), now):
        return False
    return _claim(store, "update_import_job_if", jid, {"status": status, "owner_pid": owner}, {
        "status": "queued",
        "owner_pid": my,
        "message": "",
    })
