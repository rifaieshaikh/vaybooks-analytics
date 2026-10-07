"""Phase 3 actions, weekly review, and reorder proposals."""

from fastapi import APIRouter, Depends, HTTPException, Request

from server.actions import (
    _owners,
    attach_outcomes,
    build_results,
    create_action,
    default_due,
    list_action_rows,
    record_review_open,
    set_status,
    suggestions,
    _scoped_actions,
    _rep_map,
)
from server.auth import assert_perm, require_user
from server.collection import (
    clear_allocation,
    confirm_allocation,
    create_contact,
    create_dispute,
    create_promise,
    customer_follow_up,
    follow_up_queues,
    reminder_context,
    update_contact,
    update_dispute,
    update_promise,
)
from server.org_policy import get_org_policy
from server.phase2 import build_bundle, open_review_count
from server.reorder import build_reorder, item_pack_rules, save_proposal, _load
from server.schemas import (
    ActionBody,
    ActionStatusBody,
    CollectionAllocationBody,
    CollectionContactBody,
    CollectionDisputeBody,
    CollectionPromiseBody,
    ReorderBody,
)
from server.store import get_store
from server.weekly import ensure_weekly_run_once
from server.worklist import build_worklist, customer_in_scope, resolve_scope

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


def _can_read_customer(user):
    if _can_read(user):
        return True
    return "customer.view" in (user.get("permissions") or [])


def _collection_error(exc):
    message = str(exc)
    status = 404 if "not found" in message.lower() else 400
    raise HTTPException(status, message) from exc


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


@router.get("/api/worklist")
def api_worklist(request: Request, user=Depends(require_user)):
    if not _can_read(user):
        raise HTTPException(403, "Forbidden")
    store = get_store()
    staff = request.query_params.get("staff") or ""
    try:
        scope = resolve_scope(store, user, staff)
    except PermissionError as exc:
        raise HTTPException(403, "Forbidden") from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    runs = [row for row in (store.list_runs() or []) if row.get("status") == "succeeded"]
    report_date = str((runs[0].get("report_date") if runs else "") or "")[:10]
    from server.explain import annotate_today
    payload = build_worklist(
        store,
        scope,
        report_date,
        kind=request.query_params.get("kind") or "",
        due=request.query_params.get("due") or "",
    )
    return annotate_today(store, payload, user.get("permissions") or [])


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


def _scoped_collection(store, user, payload):
    from server.worklist import customers_in_scope
    if customers_in_scope(store, user) is None:
        return payload
    def keep(row):
        return customer_in_scope(store, user, (row or {}).get("customer_name") or "")
    payload = dict(payload)
    for key in ("due_follow_ups", "missed_promises", "pending_refresh"):
        if key in payload:
            payload[key] = [row for row in payload[key] if keep(row)]
    return payload


def _require_customer_scope(store, user, customer_name):
    if not customer_in_scope(store, user, customer_name):
        raise HTTPException(403, "Forbidden")


@router.get("/api/collection/queues")
def api_collection_queues(user=Depends(require_user)):
    if not _can_read(user):
        raise HTTPException(403, "Forbidden")
    store = get_store()
    return _scoped_collection(store, user, follow_up_queues(store))


@router.get("/api/collection/reminder")
def api_collection_reminder(request: Request, user=Depends(require_user)):
    if not _can_read_customer(user):
        raise HTTPException(403, "Forbidden")
    store = get_store()
    name = request.query_params.get("customer") or ""
    _require_customer_scope(store, user, name)
    try:
        return reminder_context(store, name)
    except ValueError as exc:
        _collection_error(exc)


@router.get("/api/collection")
def api_collection_customer(request: Request, user=Depends(require_user)):
    if not _can_read_customer(user):
        raise HTTPException(403, "Forbidden")
    store = get_store()
    name = request.query_params.get("customer") or ""
    _require_customer_scope(store, user, name)
    try:
        return customer_follow_up(store, name)
    except ValueError as exc:
        _collection_error(exc)


@router.post("/api/collection/contacts")
def api_create_contact(body: CollectionContactBody, user=Depends(require_user)):
    assert_perm(user, "actions.manage")
    try:
        return create_contact(get_store(), body.model_dump(), user.get("username") or "")
    except ValueError as exc:
        _collection_error(exc)


@router.patch("/api/collection/contacts/{contact_id}")
def api_update_contact(contact_id: str, body: CollectionContactBody, user=Depends(require_user)):
    assert_perm(user, "actions.manage")
    try:
        return update_contact(get_store(), contact_id, body.model_dump(exclude_unset=True), user.get("username") or "")
    except ValueError as exc:
        _collection_error(exc)


@router.post("/api/collection/promises")
def api_create_promise(body: CollectionPromiseBody, user=Depends(require_user)):
    assert_perm(user, "actions.manage")
    try:
        return create_promise(get_store(), body.model_dump(), user.get("username") or "")
    except ValueError as exc:
        _collection_error(exc)


@router.patch("/api/collection/promises/{promise_id}")
def api_update_promise(promise_id: str, body: CollectionPromiseBody, user=Depends(require_user)):
    assert_perm(user, "actions.manage")
    try:
        return update_promise(get_store(), promise_id, body.model_dump(exclude_unset=True), user.get("username") or "")
    except ValueError as exc:
        _collection_error(exc)


@router.post("/api/collection/disputes")
def api_create_dispute(body: CollectionDisputeBody, user=Depends(require_user)):
    assert_perm(user, "actions.manage")
    try:
        return create_dispute(get_store(), body.model_dump(), user.get("username") or "")
    except ValueError as exc:
        _collection_error(exc)


@router.patch("/api/collection/disputes/{dispute_id}")
def api_update_dispute(dispute_id: str, body: CollectionDisputeBody, user=Depends(require_user)):
    assert_perm(user, "actions.manage")
    try:
        return update_dispute(get_store(), dispute_id, body.model_dump(exclude_unset=True), user.get("username") or "")
    except ValueError as exc:
        _collection_error(exc)


@router.post("/api/collection/allocations")
def api_confirm_allocation(body: CollectionAllocationBody, user=Depends(require_user)):
    assert_perm(user, "actions.manage")
    try:
        return confirm_allocation(get_store(), body.model_dump(), user.get("username") or "")
    except ValueError as exc:
        _collection_error(exc)


@router.delete("/api/collection/allocations/{allocation_id}")
def api_clear_allocation(allocation_id: str, user=Depends(require_user)):
    assert_perm(user, "actions.manage")
    try:
        return clear_allocation(get_store(), allocation_id, user.get("username") or "")
    except ValueError as exc:
        _collection_error(exc)


@router.get("/api/review")
def api_review(request: Request, user=Depends(require_user)):
    if not _can_read(user):
        raise HTTPException(403, "Forbidden")
    store = get_store()
    ensure_weekly_run_once(store)
    run = _run(store, request.query_params.get("run") or "")
    try:
        scope = resolve_scope(store, user, request.query_params.get("staff") or "")
    except PermissionError as exc:
        raise HTTPException(403, "Forbidden") from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    bundle = _bundle(store, run)
    policy = get_org_policy(store)
    ideas = suggestions(bundle, policy.get("thresholds") or {})
    report_date = str(run.get("report_date") or "")[:10]
    actions = _with_outcomes(store, report_date, bundle)
    week = [row for row in actions if str(row.get("report_date") or "")[:10] == report_date or not row.get("report_date")]
    week = _scoped_actions(week, scope, _rep_map(store))
    opens = record_review_open(store, user.get("username") or "", report_date)
    return {
        "report_date": report_date,
        "suggestions": ideas,
        "actions": week,
        "results": build_results(store, week, scope, report_date, run, opens),
        "owners": _owners(store),
        "default_due": default_due(report_date),
        "can_manage": "actions.manage" in (user.get("permissions") or []),
    }


@router.get("/api/cash")
def api_cash(user=Depends(require_user)):
    perms = set(user.get("permissions") or [])
    if not perms.intersection({"payments.view", "reports.view.scorecard", "actions.manage", "opening_cash.view"}):
        raise HTTPException(403, "Forbidden")
    from server.cash import build_cash
    return build_cash(get_store())


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
    from server.items360 import purchase_plans
    from vay.eligibility import latest_snapshot_date
    proposal = _load(store)
    built = build_reorder(purchase_plans(store), proposal, item_pack_rules(store))
    built["report_date"] = str(run.get("report_date") or "")[:10]
    built["stock_date"] = latest_snapshot_date(store, "stock")
    built["status"] = "eligible"
    built["owners"] = _owners(store)
    built["can_manage"] = "actions.manage" in (user.get("permissions") or [])
    from server.explain import annotate_reorder
    return annotate_reorder(built, store, user.get("permissions") or [])


@router.put("/api/reorder")
def api_save_reorder(body: ReorderBody, user=Depends(require_user)):
    assert_perm(user, "actions.manage")
    store = get_store()
    from vay.phase3 import apply_budget, round_pack
    stored = []
    rounded = []
    for line in body.lines or []:
        name = str(line.get("name") or "").strip()
        if not name:
            continue
        raw_qty = line.get("qty")
        if raw_qty not in ("", None):
            try:
                if float(raw_qty) < 0:
                    raise HTTPException(400, "Quantity must be zero or greater")
            except HTTPException:
                raise
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, "Reorder values must be numbers") from exc
        manual = bool(line.get("manual")) if "manual" in line else raw_qty not in ("", None)
        pack = line.get("pack_size") or 0
        minimum = line.get("minimum") or 0
        qty = round_pack(raw_qty, pack, minimum) if manual else None
        raw_cost = line.get("unit_cost")
        if raw_cost in ("", None):
            unit_cost = None
        else:
            try:
                unit_cost = float(raw_cost)
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, "Reorder values must be numbers") from exc
        stored.append({
            "name": name,
            "qty": qty,
            "manual": manual,
            "basis_qty": line.get("basis_qty") if manual else None,
            "pack_size": pack,
            "minimum": minimum,
            "lead_days": int(line.get("lead_days") or 0),
            "supplier": str(line.get("supplier") or "").strip(),
        })
        rounded.append({
            "name": name,
            "qty": qty if manual else round_pack(raw_qty, pack, minimum),
            "pack_size": pack,
            "minimum": minimum,
            "lead_days": int(line.get("lead_days") or 0),
            "supplier": str(line.get("supplier") or "").strip(),
            "unit_cost": unit_cost,
        })
    budget_rows = []
    zeroed = []
    for row in rounded:
        if float(row.get("qty") or 0) <= 0.009:
            zeroed.append(dict(row, included=False, defer_reason="Quantity set to zero"))
        else:
            budget_rows.append(row)
    kept, spent, deferred = apply_budget(budget_rows, body.budget)
    deferred = zeroed + deferred
    try:
        saved = save_proposal(store, {"budget": body.budget, "lines": stored})
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
        "deferred": deferred,
        "spent": spent,
        "stopped": any(row.get("defer_reason") == "Would pass the budget" for row in deferred),
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
