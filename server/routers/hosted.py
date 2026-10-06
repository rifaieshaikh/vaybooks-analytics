"""Audit, backup, entitlements, and support-hour records."""

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from server.audit import list_events, record
from server.auth import assert_perm, require_user
from server.backup import restore_org, snapshot_org
from server.hosted import record_support_hours, set_entitlement, support_gate
from server.store import get_store

router = APIRouter()


@router.get("/api/audit")
def api_audit(request: Request, user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    try:
        limit = int(request.query_params.get("limit") or 50)
        offset = int(request.query_params.get("offset") or 0)
    except (TypeError, ValueError):
        limit, offset = 50, 0
    rows, total = list_events(get_store(), limit=limit, offset=offset)
    events = []
    for row in rows:
        events.append({
            "id": str(row.get("_id") or ""),
            "action": row.get("action") or "",
            "actor": row.get("actor") or "",
            "detail": row.get("detail") or "",
            "created_at": str(row.get("created_at") or ""),
        })
    return {"total": total, "events": events}


@router.get("/api/backup")
def api_backup(user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    return snapshot_org(get_store())


@router.post("/api/backup/restore")
def api_restore(body: dict = Body(...), user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    store = get_store()
    result = restore_org(store, body or {})
    record(store, "restore", user.get("username") or "", "Restored %s rows" % result.get("restored"))
    return result


@router.post("/api/entitlements")
def api_entitlement(body: dict = Body(...), user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    pack = str((body or {}).get("pack") or "").strip()
    if pack not in ("wholesale", "retail"):
        raise HTTPException(400, "pack must be wholesale or retail")
    policy = set_entitlement(get_store(), pack, bool((body or {}).get("enabled")))
    record(get_store(), "entitlement", user.get("username") or "", "%s %s" % (pack, "on" if body.get("enabled") else "off"))
    return {"entitlements": policy.get("entitlements") or {}}


@router.post("/api/support-hours")
def api_support_hours(body: dict = Body(...), user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    try:
        record_support_hours(get_store(), (body or {}).get("hours"), (body or {}).get("note") or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return support_gate(get_store())


@router.get("/api/support-hours")
def api_support_gate(user=Depends(require_user)):
    assert_perm(user, "settings.advanced")
    return support_gate(get_store())
