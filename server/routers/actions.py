"""Phase 3 actions, weekly review, and reorder proposals."""

from fastapi import APIRouter, Depends, HTTPException, Request

from server.actions import (
    _owners,
    attach_outcomes,
    create_action,
    default_due,
    list_action_rows,
    set_status,
    suggestions,
)
from server.auth import assert_perm, require_user
from server.org_policy import get_org_policy
from server.phase2 import build_bundle, open_review_count
from server.reorder import build_reorder, save_proposal, _load
from server.schemas import ActionBody, ActionStatusBody, ReorderBody
from server.store import get_store
from server.weekly import ensure_weekly_run_once

router = APIRouter()

_READ = (
    "actions.manage",
    "reports.view.followup",
    "reports.view.scorecard",
    "reports.view.items",
    "reports.view.quality",
    "reports.view.performance",
)


def _can_read(user):
    perms = set(user.get("permissions") or [])
    return any(name in perms for name in _READ)


def _run(store, run_id):
    run = store.get_run(run_id) if run_id else None
    if not run:
        runs = [row for row in (store.list_runs() or []) if row.get("status") == "succeeded"]
        run = runs[0] if runs else None
    if not run or not run.get("report_date"):
        raise HTTPException(400, "Create a report first")
    return run


def _bundle(store, run):
    recon = ((run.get("manifest") or {}).get("reconciliation") or {})
    return build_bundle(
        store,
        run.get("report_date"),
        exceptions=recon.get("exceptions") or [],
        review_count=open_review_count(store),
    )


def _with_outcomes(store, report_date, bundle=None):
    rows = list_action_rows(store)
    messages = []
    if any(row.get("action_type") == "data_fix" for row in rows):
        if bundle is None and report_date:
            try:
                bundle = build_bundle(store, report_date)
            except (TypeError, ValueError):
                bundle = None
        messages = [row.get("message") or "" for row in ((bundle or {}).get("quality") or {}).get("rows") or []]
    return attach_outcomes(store, rows, messages, report_date=report_date)


@router.get("/api/actions")
def api_list_actions(request: Request, user=Depends(require_user)):
    if not _can_read(user):
        raise HTTPException(403, "Forbidden")
    store = get_store()
    report_date = request.query_params.get("report_date") or ""
    return {"actions": _with_outcomes(store, report_date), "owners": _owners(store)}


@router.post("/api/actions")
def api_create_action(body: ActionBody, user=Depends(require_user)):
    assert_perm(user, "actions.manage")
    try:
        row = create_action(get_store(), body.model_dump(), user.get("username") or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return row


@router.post("/api/actions/{action_id}/status")
def api_action_status(action_id: str, body: ActionStatusBody, user=Depends(require_user)):
    assert_perm(user, "actions.manage")
    try:
        return set_status(get_store(), action_id, body.status)
    except ValueError as exc:
        message = str(exc)
        raise HTTPException(404 if message == "Action not found" else 400, message) from exc


@router.get("/api/review")
def api_review(request: Request, user=Depends(require_user)):
    if not _can_read(user):
        raise HTTPException(403, "Forbidden")
    store = get_store()
    ensure_weekly_run_once(store)
    run = _run(store, request.query_params.get("run") or "")
    bundle = _bundle(store, run)
    policy = get_org_policy(store)
    ideas = suggestions(bundle, policy.get("thresholds") or {})
    report_date = str(run.get("report_date") or "")[:10]
    actions = _with_outcomes(store, report_date, bundle)
    week = [row for row in actions if str(row.get("report_date") or "")[:10] == report_date or not row.get("report_date")]
    return {
        "report_date": report_date,
        "suggestions": ideas,
        "actions": week,
        "owners": _owners(store),
        "default_due": default_due(report_date),
        "can_manage": "actions.manage" in (user.get("permissions") or []),
    }


@router.get("/api/reorder")
def api_reorder(request: Request, user=Depends(require_user)):
    assert_perm(user, "reports.view.items", "actions.manage")
    store = get_store()
    run = _run(store, request.query_params.get("run") or "")
    bundle = _bundle(store, run)
    if (bundle.get("stock") or {}).get("status") == "unavailable":
        return {
            "report_date": run.get("report_date"),
            "status": "unavailable",
            "reason": (bundle.get("stock") or {}).get("reason") or "Unavailable",
            "lines": [],
        }
    policy = get_org_policy(store)
    limit = (policy.get("thresholds") or {}).get("cover_days")
    if limit in ("", None):
        limit = 30
    costs = {}
    for doc in store.rows_of_type("stock") or []:
        fields = doc.get("fields") or {}
        name = str(fields.get("Item Name") or "").strip()
        raw = fields.get("P.Price")
        if not name or raw in ("", None):
            continue
        try:
            costs[name] = float(str(raw).replace(",", ""))
        except (TypeError, ValueError):
            continue
    proposal = _load(store)
    built = build_reorder((bundle.get("stock") or {}).get("rows") or [], costs, proposal, cover_limit=limit)
    built["report_date"] = str(run.get("report_date") or "")[:10]
    built["status"] = "eligible"
    built["owners"] = _owners(store)
    built["can_manage"] = "actions.manage" in (user.get("permissions") or [])
    return built


@router.put("/api/reorder")
def api_save_reorder(body: ReorderBody, user=Depends(require_user)):
    assert_perm(user, "actions.manage")
    store = get_store()
    from vay.phase3 import apply_budget, round_pack
    rounded = []
    for line in body.lines or []:
        name = str(line.get("name") or "").strip()
        if not name:
            continue
        qty = round_pack(line.get("qty"), line.get("pack_size"), line.get("minimum"))
        rounded.append({
            "name": name,
            "qty": qty,
            "pack_size": line.get("pack_size") or 0,
            "minimum": line.get("minimum") or 0,
            "lead_days": int(line.get("lead_days") or 0),
            "supplier": str(line.get("supplier") or "").strip(),
            "unit_cost": line.get("unit_cost") or 0,
        })
    kept, spent = apply_budget(rounded, body.budget)
    try:
        saved = save_proposal(store, {"budget": body.budget, "lines": kept})
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "Reorder values must be numbers") from exc
    report_date = body.report_date
    if not report_date:
        try:
            report_date = _run(store, "")["report_date"]
        except HTTPException:
            report_date = ""
    payload = {
        "saved": saved,
        "lines": kept,
        "spent": spent,
        "stopped": len(kept) < len(rounded),
    }
    if body.assign and report_date:
        from datetime import timedelta
        from vay.dates import parse_date
        base = parse_date(report_date)
        for line in kept:
            lead = int(line.get("lead_days") or 0)
            due = (base + timedelta(days=lead or 7)).strftime("%Y-%m-%d") if base else default_due(report_date, lead or 7)
            create_action(store, {
                "action_type": "purchase",
                "subject_kind": "item",
                "subject_name": line.get("name"),
                "proposal": "Reorder %s" % line.get("name"),
                "owner": body.owner or user.get("username") or "",
                "due_date": due,
                "amount": line.get("qty"),
                "report_date": str(report_date)[:10],
            }, user.get("username") or "")
        payload["assigned"] = True
    return payload
