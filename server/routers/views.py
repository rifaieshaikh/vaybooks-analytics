"""Dashboard, data browsing, 360-view, and entity override routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from server.auth import assert_perm, require_user, type_perm
from server.business360 import business_brief_pdf, empty_business, visible_business
from server.customers import (
    _normalize_pdf_view,
    customer_pdf,
    entity_brief_pdf,
    patch_party_type,
)
from server.dashboard import serve_dashboard
from server.due_days import resolve_entity_due_days, save_due_days_override
from server.invoices import get_invoice, list_invoices, list_item_lines
from server.items360 import get_item as live_get_item, save_default_holding, save_holding
from server.order_check import resolve_entity_policy, run_customer_order_check, run_entity_order_check, save_customer_flags, save_policy_override
from server.route_helpers import views_for_request, with_stale
from server.rows import query_rows
from server.run_views import (
    customer_profile,
    customer_section,
    customer_slice,
    slim_customer_list,
    slim_item_list,
    snapshot_get_customer,
    group_slice,
    snapshot_get_group,
    item_slice,
    snapshot_get_item,
    snapshot_get_item_dim,
    rep_slice,
    snapshot_get_rep,
    snapshot_list_customers,
    snapshot_list_groups,
    snapshot_list_item_dims,
    snapshot_list_items,
    snapshot_list_reps,
)
from server.schemas import (
    DueDaysOverrideBody,
    ItemHoldingBody,
    ItemHoldingDefaultBody,
    OrderCheckFlagsBody,
    OrderCheckOverrideBody,
    OrderCheckRunBody,
    PartyPatchBody,
)
from server.settings import SOURCE_TYPES
from server.store import get_store

router = APIRouter()


def _last_upload_at(store):
    for doc in store.list_uploads() or []:
        if doc.get("dry_run"):
            continue
        created = doc.get("created_at")
        if hasattr(created, "isoformat"):
            return created.isoformat()
        return str(created or "")
    return ""


def _business_doc(store, run, views):
    doc = (views or {}).get("business")
    if not isinstance(doc, dict):
        return None
    rid = str((run or {}).get("_id") or (run or {}).get("id") or "")
    if rid and ("settlements" in doc or "sales_gaps" in doc):
        from server.view_parts import persist_business_split
        doc = persist_business_split(store, rid, doc)
    return doc


def _business_section(store, run, doc, section, permissions):
    rid = str((run or {}).get("_id") or (run or {}).get("id") or "")
    kind = "business_settlements" if section == "settlements" else "business_gaps"
    from server.view_parts import _load_body
    part = _load_body(store.get_view_part(rid, kind, "root")) if rid else None
    stub = {
        "empty": False,
        "name": (doc or {}).get("name") or "Business",
        "as_of": (doc or {}).get("as_of") or "",
        "as_of_label": (doc or {}).get("as_of_label") or "",
        "fy_label": (doc or {}).get("fy_label") or "",
    }
    if section == "settlements":
        stub["settlements"] = part or {}
        stub["settlements_separate"] = True
    else:
        stub["sales_gaps"] = part or {}
        stub["sales_gaps_separate"] = True
    return visible_business(stub, permissions)


def _business_payload(store, params, user, heavy=False):
    run, views, stale = views_for_request(store, params)
    doc = _business_doc(store, run, views)
    permissions = user.get("permissions") or []
    section = (params.get("section") or "").strip()
    if not doc:
        payload = empty_business()
    elif section in ("settlements", "sales_gaps"):
        payload = _business_section(store, run, doc, section, permissions)
    else:
        shown = doc
        if heavy:
            shown = _business_with_heavy(store, run, doc)
        payload = visible_business(shown, permissions)
    payload["last_upload_at"] = _last_upload_at(store)
    return with_stale(payload, stale, run), run, views


def _business_with_heavy(store, run, doc):
    from server.view_parts import _load_body
    out = dict(doc)
    rid = str((run or {}).get("_id") or (run or {}).get("id") or "")
    if not rid:
        return out
    if out.get("settlements_separate") and "settlements" not in out:
        out["settlements"] = _load_body(store.get_view_part(rid, "business_settlements", "root")) or {}
    if out.get("sales_gaps_separate") and "sales_gaps" not in out:
        out["sales_gaps"] = _load_body(store.get_view_part(rid, "business_gaps", "root")) or {}
    return out


@router.get("/api/business")
def api_business(request: Request, user=Depends(require_user)):
    """Company profile saved with the report. Heavy tabs load on their own."""
    assert_perm(user, "customer.view")
    store = get_store()
    payload, _run, _views = _business_payload(store, dict(request.query_params), user)
    return payload


@router.get("/api/business/pdf")
def api_business_pdf(request: Request, user=Depends(require_user)):
    assert_perm(user, "customer.view")
    store = get_store()
    payload, _run, _views = _business_payload(store, dict(request.query_params), user, heavy=True)
    if payload.get("empty"):
        raise HTTPException(404, payload.get("message") or "Not found")
    data = business_brief_pdf(payload)
    as_of = (payload.get("as_of") or "").replace("-", "")
    filename = "Business_brief_%s.pdf" % (as_of or "today")
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=%s" % filename})


@router.get("/api/dashboard")
def api_dashboard(request: Request, user=Depends(require_user)):
    params = dict(request.query_params)
    return serve_dashboard(get_store(), user["permissions"], run_id=params.get("run") or params.get("run_id") or None)


@router.get("/api/rows")
def rows(request: Request, user=Depends(require_user)):
    params = dict(request.query_params)
    type_name = (params.get("type") or "sales").strip().lower()
    if type_name not in SOURCE_TYPES:
        raise HTTPException(400, "Unknown type")
    assert_perm(user, type_perm(type_name, "view"))
    return query_rows(get_store(), params)


@router.patch("/api/parties/{uk}")
def api_patch_party(uk: str, body: PartyPatchBody, user=Depends(require_user)):
    assert_perm(user, type_perm("party", "upload"))
    try:
        row = patch_party_type(get_store(), uk, body.party_type)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not row:
        raise HTTPException(404, "Not found")
    return row


@router.get("/api/invoices")
def api_list_invoices(request: Request, user=Depends(require_user)):
    assert_perm(user, type_perm("sales", "view"))
    return list_invoices(get_store(), dict(request.query_params))


@router.get("/api/invoices/{invoice_id}")
def api_get_invoice(invoice_id: str, user=Depends(require_user)):
    assert_perm(user, type_perm("sales", "view"))
    detail = get_invoice(get_store(), invoice_id)
    if not detail:
        raise HTTPException(404, "Invoice not found")
    return detail


@router.get("/api/item-lines")
def api_item_lines(request: Request, user=Depends(require_user)):
    assert_perm(user, type_perm("items", "view"))
    return list_item_lines(get_store(), dict(request.query_params))


@router.get("/api/customers")
def api_list_customers(request: Request, user=Depends(require_user)):
    assert_perm(user, "customer.view")
    store = get_store()
    params = dict(request.query_params)
    run, views, stale = views_for_request(store, params)
    return with_stale(slim_customer_list(snapshot_list_customers(store, params, views)), stale, run)


@router.get("/api/customers/{uk}/pdf")
def api_customer_pdf(uk: str, request: Request, user=Depends(require_user)):
    assert_perm(user, "customer.view")
    store = get_store()
    params = dict(request.query_params)
    _run, views, _stale = views_for_request(store, params)
    detail = snapshot_get_customer(store, uk, views)
    if not detail:
        raise HTTPException(404, "Not found")
    view = _normalize_pdf_view(params.get("view"))
    if view == "reminder":
        from server.collection import reminder_context
        detail = dict(detail)
        detail["collection_reminder"] = reminder_context(store, detail.get("name") or "")
    data = customer_pdf(detail, view=view)
    as_of = (detail.get("as_of") or "").replace("-", "")
    raw_name = "".join(ch if ch.isalnum() else "_" for ch in (detail.get("name") or "customer"))
    kind = {"customer": "statement", "reminder": "reminder"}.get(view, "brief")
    filename = "%s_%s_%s.pdf" % (raw_name.strip("_") or "customer", kind, as_of or "today")
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=%s" % filename})


def _entity_pdf_response(entity, detail):
    data = entity_brief_pdf(detail, entity=entity)
    as_of = (detail.get("as_of") or "").replace("-", "")
    raw_name = "".join(ch if ch.isalnum() else "_" for ch in (detail.get("name") or entity))
    filename = "%s_%s_brief_%s.pdf" % (raw_name.strip("_") or entity, entity, as_of or "today")
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=%s" % filename})


@router.get("/api/groups/{uk}/pdf")
def api_group_pdf(uk: str, request: Request, user=Depends(require_user)):
    assert_perm(user, "customer.view")
    store = get_store()
    params = dict(request.query_params)
    _run, views, _stale = views_for_request(store, params)
    detail = snapshot_get_group(store, uk, views)
    if not detail:
        raise HTTPException(404, "Not found")
    return _entity_pdf_response("group", detail)


@router.get("/api/reps/{uk}/pdf")
def api_rep_pdf(uk: str, request: Request, user=Depends(require_user)):
    assert_perm(user, "customer.view")
    store = get_store()
    params = dict(request.query_params)
    _run, views, _stale = views_for_request(store, params)
    detail = snapshot_get_rep(store, uk, views)
    if not detail:
        raise HTTPException(404, "Not found")
    return _entity_pdf_response("rep", detail)


@router.get("/api/repurchase")
def api_repurchase(request: Request, user=Depends(require_user)):
    """One saved repurchase block. Does not load the rest of the report."""
    entity = (request.query_params.get("entity") or "").strip()
    uk = request.query_params.get("uk") or ""
    if entity in ("customer", "group", "rep"):
        assert_perm(user, "customer.view")
    elif entity in ("item", "category", "item_group", "brand", "supplier"):
        assert_perm(user, type_perm("stock", "view"))
    else:
        raise HTTPException(404, "Not found")
    store = get_store()
    params = dict(request.query_params)
    run, views, stale = views_for_request(store, params)
    if not run or not getattr(views, "split", False):
        raise HTTPException(404, "Not found")
    from server.view_parts import load_repurchase, load_repurchase_lines, load_repurchase_period, load_repurchase_timeline
    rid = str(run.get("_id") or run.get("id") or "")
    part_name = (params.get("part") or "").strip()
    if part_name == "timeline":
        try:
            page = int(params.get("page") or 0)
        except (TypeError, ValueError):
            page = 0
        return with_stale(load_repurchase_timeline(store, rid, entity, uk, page), stale, run)
    if part_name == "period":
        return with_stale({
            "period": load_repurchase_period(store, rid, entity, uk, params.get("period") or "month", params.get("key") or ""),
        }, stale, run)
    if part_name == "lines":
        return with_stale({
            "lines": load_repurchase_lines(store, rid, entity, uk, params.get("period") or "overall", params.get("key") or ""),
        }, stale, run)
    part = load_repurchase(store, rid, entity, uk)
    if not part:
        raise HTTPException(404, "Not found")
    return with_stale(part, stale, run)


@router.get("/api/customers/{uk}")
def api_get_customer(uk: str, request: Request, user=Depends(require_user)):
    assert_perm(user, "customer.view")
    store = get_store()
    params = dict(request.query_params)
    run, views, stale = views_for_request(store, params)
    section = (params.get("section") or "").strip()
    want_profile = (params.get("view") or "").strip() == "profile"
    if getattr(views, "split", False) and (section or want_profile):
        payload = customer_slice(store, views, uk, section)
        if payload is None:
            raise HTTPException(404, "Not found")
        return with_stale(payload, stale, run)
    detail = snapshot_get_customer(store, uk, views)
    if not detail:
        raise HTTPException(404, "Not found")
    if section:
        payload = customer_section(detail, section)
    elif want_profile:
        payload = customer_profile(detail)
    else:
        payload = detail
    return with_stale(payload, stale, run)


@router.get("/api/groups")
def api_list_groups(request: Request, user=Depends(require_user)):
    assert_perm(user, "customer.view")
    store = get_store()
    params = dict(request.query_params)
    run, views, stale = views_for_request(store, params)
    return with_stale(snapshot_list_groups(store, params, views), stale, run)


@router.get("/api/groups/{uk}")
def api_get_group(uk: str, request: Request, user=Depends(require_user)):
    assert_perm(user, "customer.view")
    store = get_store()
    params = dict(request.query_params)
    run, views, stale = views_for_request(store, params)
    section = (params.get("section") or "").strip()
    want_profile = (params.get("view") or "").strip() == "profile"
    if getattr(views, "split", False) and (section or want_profile):
        payload = group_slice(store, views, uk, section)
        if payload is None:
            raise HTTPException(404, "Not found")
        return with_stale(payload, stale, run)
    detail = snapshot_get_group(store, uk, views)
    if not detail:
        raise HTTPException(404, "Not found")
    return with_stale(detail, stale, run)


@router.get("/api/reps")
def api_list_reps(request: Request, user=Depends(require_user)):
    assert_perm(user, "customer.view")
    store = get_store()
    params = dict(request.query_params)
    run, views, stale = views_for_request(store, params)
    return with_stale(snapshot_list_reps(store, params, views), stale, run)


@router.get("/api/reps/{uk}")
def api_get_rep(uk: str, request: Request, user=Depends(require_user)):
    assert_perm(user, "customer.view")
    store = get_store()
    params = dict(request.query_params)
    run, views, stale = views_for_request(store, params)
    section = (params.get("section") or "").strip()
    want_profile = (params.get("view") or "").strip() == "profile"
    if getattr(views, "split", False) and (section or want_profile):
        payload = rep_slice(store, views, uk, section)
        if payload is None:
            raise HTTPException(404, "Not found")
        return with_stale(payload, stale, run)
    detail = snapshot_get_rep(store, uk, views)
    if not detail:
        raise HTTPException(404, "Not found")
    return with_stale(detail, stale, run)


@router.get("/api/item-dims/{dimension}")
def api_list_item_dims(dimension: str, request: Request, user=Depends(require_user)):
    from server.item_dims import dimension_spec
    if not dimension_spec(dimension):
        raise HTTPException(404, "Not found")
    assert_perm(user, type_perm("stock", "view"))
    store = get_store()
    params = dict(request.query_params)
    run, views, stale = views_for_request(store, params)
    listed = snapshot_list_item_dims(store, dimension, params, views)
    if listed is None:
        raise HTTPException(404, "Not found")
    return with_stale(listed, stale, run)


@router.get("/api/item-dims/{dimension}/{uk}")
def api_get_item_dim(dimension: str, uk: str, request: Request, user=Depends(require_user)):
    from server.item_dims import dimension_spec
    if not dimension_spec(dimension):
        raise HTTPException(404, "Not found")
    assert_perm(user, type_perm("stock", "view"))
    store = get_store()
    params = dict(request.query_params)
    run, views, stale = views_for_request(store, params)
    detail = snapshot_get_item_dim(store, dimension, uk, views, params)
    if not detail:
        raise HTTPException(404, "Not found")
    return with_stale(detail, stale, run)


@router.get("/api/items")
def api_list_items(request: Request, user=Depends(require_user)):
    assert_perm(user, type_perm("stock", "view"))
    store = get_store()
    params = dict(request.query_params)
    run, views, stale = views_for_request(store, params)
    return with_stale(slim_item_list(snapshot_list_items(store, params, views)), stale, run)


@router.get("/api/items/{uk}")
def api_get_item(uk: str, request: Request, user=Depends(require_user)):
    assert_perm(user, type_perm("stock", "view"))
    store = get_store()
    params = dict(request.query_params)
    run, views, stale = views_for_request(store, params)
    section = (params.get("section") or "").strip()
    want_profile = (params.get("view") or "").strip() == "profile"
    if getattr(views, "split", False) and (section or want_profile):
        payload = item_slice(store, views, uk, section)
        if payload is None:
            raise HTTPException(404, "Not found")
        return with_stale(payload, stale, run)
    detail = snapshot_get_item(store, uk, views)
    if not detail:
        raise HTTPException(404, "Not found")
    return with_stale(detail, stale, run)


@router.put("/api/items/holding-default")
def api_save_item_holding_default(body: ItemHoldingDefaultBody, user=Depends(require_user)):
    assert_perm(user, type_perm("stock", "upload"))
    if body.min_hold is None and body.max_days_hold is None:
        raise HTTPException(400, "Nothing to save")
    if body.max_days_hold is not None and int(body.max_days_hold) < 1:
        raise HTTPException(400, "Max days hold must be at least 1")
    return save_default_holding(get_store(), min_hold=body.min_hold, max_days_hold=body.max_days_hold)


@router.put("/api/items/{uk}/holding")
def api_save_item_holding(uk: str, body: ItemHoldingBody, user=Depends(require_user)):
    assert_perm(user, type_perm("stock", "upload"))
    if body.max_days_hold is not None and int(body.max_days_hold) < 1:
        raise HTTPException(400, "Max days hold must be at least 1")
    store = get_store()
    saved = save_holding(
        store, uk, min_hold=body.min_hold, fill_to=body.fill_to, lead_days=body.lead_days,
        max_days_hold=body.max_days_hold, discontinued=body.discontinued,
        clear_fill=body.clear_fill, clear_max_days=body.clear_max_days,
    )
    if not saved:
        raise HTTPException(404, "Not found")
    detail = live_get_item(store, uk)
    if not detail:
        raise HTTPException(404, "Not found")
    return detail


def _put_due_days_override(entity, uk, body):
    store = get_store()
    try:
        result = save_due_days_override(store, entity, uk, body.due_days)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    meta = resolve_entity_due_days(store, entity, uk)
    result.update({"effective_due_days": meta["due_days"], "due_days_source": meta["source"], "due_days_own": meta.get("own")})
    return result


@router.put("/api/customers/{uk}/due-days")
def api_put_customer_due_days(uk: str, body: DueDaysOverrideBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced", "customer.view")
    return _put_due_days_override("customer", uk, body)


@router.put("/api/groups/{uk}/due-days")
def api_put_group_due_days(uk: str, body: DueDaysOverrideBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced", "customer.view")
    return _put_due_days_override("group", uk, body)


@router.put("/api/reps/{uk}/due-days")
def api_put_rep_due_days(uk: str, body: DueDaysOverrideBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced", "customer.view")
    return _put_due_days_override("rep", uk, body)


def _put_order_check_override(entity, uk, body):
    store = get_store()
    try:
        if body.clear or body.policy is None:
            result = save_policy_override(store, entity, uk, clear=True)
        else:
            result = save_policy_override(store, entity, uk, body.policy)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    meta = resolve_entity_policy(store, entity, uk)
    result.update({"effective_policy": meta["policy"], "policy_source": meta["source"], "policy_own": meta.get("own")})
    return result


@router.put("/api/customers/{uk}/order-check")
def api_put_customer_order_check(uk: str, body: OrderCheckOverrideBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced", "customer.view")
    return _put_order_check_override("customer", uk, body)


@router.put("/api/groups/{uk}/order-check")
def api_put_group_order_check(uk: str, body: OrderCheckOverrideBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced", "customer.view")
    return _put_order_check_override("group", uk, body)


@router.put("/api/reps/{uk}/order-check")
def api_put_rep_order_check(uk: str, body: OrderCheckOverrideBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced", "customer.view")
    return _put_order_check_override("rep", uk, body)


@router.put("/api/customers/{uk}/order-flags")
def api_put_customer_order_flags(uk: str, body: OrderCheckFlagsBody, user=Depends(require_user)):
    assert_perm(user, "settings.advanced", "customer.view")
    if body.premium is None and body.blacklisted is None:
        raise HTTPException(400, "premium or blacklisted required")
    result = save_customer_flags(get_store(), uk, premium=body.premium, blacklisted=body.blacklisted)
    if not result:
        raise HTTPException(404, "Not found")
    return result


@router.post("/api/customers/{uk}/order-check/run")
def api_run_customer_order_check(uk: str, body: OrderCheckRunBody, request: Request, user=Depends(require_user)):
    assert_perm(user, "customer.view")
    store = get_store()
    _run, views, _stale = views_for_request(store, dict(request.query_params))
    detail = snapshot_get_customer(store, uk, views)
    if not detail:
        raise HTTPException(404, "Not found")
    result = run_customer_order_check(store, uk, order_value=body.order_value, order_qty=body.order_qty, detail=detail)
    if not result:
        raise HTTPException(404, "Not found")
    return result


@router.post("/api/groups/{uk}/order-check/run")
def api_run_group_order_check(uk: str, body: OrderCheckRunBody, request: Request, user=Depends(require_user)):
    assert_perm(user, "customer.view")
    store = get_store()
    _run, views, _stale = views_for_request(store, dict(request.query_params))
    detail = snapshot_get_group(store, uk, views)
    if not detail:
        raise HTTPException(404, "Not found")
    result = run_entity_order_check(
        store, "group", uk, order_value=body.order_value, order_qty=body.order_qty, detail=detail
    )
    if not result:
        raise HTTPException(404, "Not found")
    return result


@router.post("/api/reps/{uk}/order-check/run")
def api_run_rep_order_check(uk: str, body: OrderCheckRunBody, request: Request, user=Depends(require_user)):
    assert_perm(user, "customer.view")
    store = get_store()
    _run, views, _stale = views_for_request(store, dict(request.query_params))
    detail = snapshot_get_rep(store, uk, views)
    if not detail:
        raise HTTPException(404, "Not found")
    result = run_entity_order_check(
        store, "rep", uk, order_value=body.order_value, order_qty=body.order_qty, detail=detail
    )
    if not result:
        raise HTTPException(404, "Not found")
    return result
