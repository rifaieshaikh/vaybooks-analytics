"""Saved reports, preview, wholesale templates, and dataset export."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from server.auth import assert_perm, metric_visible, require_user
from server.saved_reports import (
    adopt_pack,
    approve_definition,
    create_definition,
    dataset_csv,
    execute,
    get_definition,
    list_definitions,
    update_definition,
    visible_to,
)
from server.schemas import AskBody, SavedReportBody
from server.store import get_store
from vay.metrics import metric_versions
from vay.phase4 import DIMENSIONS, METRIC_META, TEMPLATES

router = APIRouter()


def _report_date(store, request, body=None):
    raw = ""
    if body is not None:
        raw = str(body.get("report_date") or "")[:10]
    if not raw and request is not None:
        raw = str(request.query_params.get("report_date") or "")[:10]
    run_id = ""
    if request is not None:
        run_id = request.query_params.get("run") or ""
    if run_id:
        run = store.get_run(run_id)
        if run and run.get("report_date"):
            return str(run.get("report_date"))[:10]
    if raw:
        return raw
    runs = [row for row in (store.list_runs() or []) if row.get("status") == "succeeded" and row.get("report_date")]
    if runs:
        return str(runs[0].get("report_date"))[:10]
    raise HTTPException(400, "Choose a report date")


def _guard_read(user, definition):
    if not definition or not visible_to(user, definition):
        raise HTTPException(404, "Report not found")


@router.get("/api/saved-reports/catalog")
def api_catalog(user=Depends(require_user)):
    perms = set(user.get("permissions") or [])
    if "reports.manage" not in perms and not any(name.startswith("reports.view.") for name in perms):
        raise HTTPException(403, "Forbidden")
    store = get_store()
    from server.org_policy import get_org_policy
    policy = get_org_policy(store)
    return {
        "metrics": [
            {"id": mid, "label": meta["label"], "dimensions": list(meta["dimensions"])}
            for mid, meta in METRIC_META.items()
        ],
        "dimensions": list(DIMENSIONS),
        "comparisons": ["current", "prior", "prior_year"],
        "templates": list(TEMPLATES),
        "retail_templates": list(__import__("vay.packs.retail", fromlist=["TEMPLATES"]).TEMPLATES),
        "metric_versions": metric_versions(),
        "custom_columns": policy.get("custom_columns") or [],
        "wholesale_pack": bool(policy.get("wholesale_pack")),
        "retail_pack": bool(policy.get("retail_pack")),
    }


@router.get("/api/saved-reports")
def api_list(user=Depends(require_user)):
    rows = [row for row in list_definitions(get_store()) if visible_to(user, row)]
    return {"reports": rows, "can_manage": "reports.manage" in (user.get("permissions") or [])}


@router.post("/api/saved-reports")
def api_create(body: SavedReportBody, user=Depends(require_user)):
    assert_perm(user, "reports.manage")
    try:
        return create_definition(get_store(), body.model_dump(), user.get("username") or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/saved-reports/preview")
def api_preview(body: SavedReportBody, request: Request, user=Depends(require_user)):
    assert_perm(user, "reports.manage")
    store = get_store()
    report_date = _report_date(store, request, body.model_dump())
    try:
        from server.saved_reports import validate_definition
        definition = validate_definition(body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return execute(store, definition, report_date)


@router.post("/api/saved-reports/adopt-pack")
def api_adopt(user=Depends(require_user)):
    assert_perm(user, "reports.manage")
    try:
        created = adopt_pack(get_store(), user.get("username") or "")
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"created": created}


@router.post("/api/saved-reports/adopt-retail")
def api_adopt_retail(user=Depends(require_user)):
    assert_perm(user, "reports.manage")
    from server.saved_reports import adopt_retail_pack
    try:
        created = adopt_retail_pack(get_store(), user.get("username") or "")
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"created": created}


@router.post("/api/saved-reports/ask")
def api_ask(body: AskBody, request: Request, user=Depends(require_user)):
    store = get_store()
    report_date = _report_date(store, request, {"report_date": body.report_date})
    from vay.phase5 import match_question
    reports = [
        row for row in list_definitions(store)
        if row.get("status") == "approved" and visible_to(user, row)
    ]
    metrics = [{"id": mid, "label": meta["label"]} for mid, meta in METRIC_META.items()]
    hit = match_question(body.text, metrics, reports)
    if not hit:
        return {"answered": False, "value": None, "message": "Cannot answer that."}
    if hit["kind"] == "metric":
        if not metric_visible(user.get("permissions") or [], hit["id"]):
            raise HTTPException(403, "Forbidden")
        return _metric_answer(store, report_date, hit["id"])
    definition = get_definition(store, hit["id"])
    _guard_read(user, definition)
    result = execute(store, definition, report_date)
    mid = (definition.get("metric_ids") or [""])[0]
    values = []
    reason = ""
    for row in result.get("rows") or []:
        cell = (row.get("cells") or {}).get(mid) or {}
        if cell.get("status") == "unavailable":
            reason = reason or cell.get("reason") or ""
        elif cell.get("value") is not None:
            values.append(float(cell["value"]))
    value = round(sum(values), 2) if values else None
    return {
        "answered": True,
        "kind": "report",
        "name": definition.get("name") or "",
        "metric_id": mid,
        "value": value,
        "status": "eligible" if value is not None else "unavailable",
        "reason": "" if value is not None else (reason or "No rows"),
        "metric_versions": result.get("metric_versions") or {},
        "message": "",
    }


def _metric_answer(store, report_date, metric_id):
    from server.phase2 import build_bundle
    bundle = build_bundle(store, report_date)
    for row in (bundle.get("scorecard") or {}).get("rows") or []:
        if row.get("id") != metric_id:
            continue
        cell = row.get("current") or {}
        value = cell.get("value")
        return {
            "answered": True,
            "kind": "metric",
            "name": row.get("label") or metric_id,
            "metric_id": metric_id,
            "value": value,
            "status": "eligible" if value is not None else "unavailable",
            "reason": "" if value is not None else (cell.get("reason") or "No value"),
            "metric_versions": {metric_id: metric_versions().get(metric_id, 1)},
            "message": "",
        }
    return {"answered": False, "value": None, "message": "Cannot answer that."}


@router.put("/api/saved-reports/{report_id}")
def api_update(report_id: str, body: SavedReportBody, user=Depends(require_user)):
    assert_perm(user, "reports.manage")
    try:
        saved = update_definition(get_store(), report_id, body.model_dump(), user.get("username") or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not saved:
        raise HTTPException(404, "Report not found")
    return saved


@router.post("/api/saved-reports/{report_id}/approve")
def api_approve(report_id: str, user=Depends(require_user)):
    assert_perm(user, "reports.manage")
    saved = approve_definition(get_store(), report_id)
    if not saved:
        raise HTTPException(404, "Report not found")
    return saved


@router.get("/api/saved-reports/{report_id}/run")
def api_run(report_id: str, request: Request, user=Depends(require_user)):
    store = get_store()
    definition = get_definition(store, report_id)
    _guard_read(user, definition)
    report_date = _report_date(store, request)
    return execute(store, definition, report_date)


@router.get("/api/saved-reports/{report_id}/export")
def api_export(report_id: str, request: Request, user=Depends(require_user)):
    store = get_store()
    definition = get_definition(store, report_id)
    _guard_read(user, definition)
    if definition.get("status") != "approved":
        raise HTTPException(404, "Report not found")
    report_date = _report_date(store, request)
    result = execute(store, definition, report_date)
    if request.query_params.get("format") == "csv":
        return Response(dataset_csv(result), media_type="text/csv")
    return result
