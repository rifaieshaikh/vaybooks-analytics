"""Forecast, scenarios, consolidation, and composed metrics."""

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from server.auth import assert_perm, require_user
from server.consolidation import company_figures
from server.custom_metrics import approve_metric, create_metric, list_metrics, update_metric
from server.store import get_store
from vay.phase5 import apply_scenario, consolidate_companies, forecast_sales

router = APIRouter()


def _can_see(user):
    perms = set(user.get("permissions") or [])
    return "reports.manage" in perms or "reports.view.scorecard" in perms or "*" in perms


@router.get("/api/forecast")
def api_forecast(request: Request, user=Depends(require_user)):
    if not _can_see(user):
        raise HTTPException(403, "Forbidden")
    store = get_store()
    report_date = (request.query_params.get("report_date") or "").strip()
    if not report_date:
        from server.routers.saved_reports import _report_date
        report_date = _report_date(store, request)
    from server.phase2 import _dated_sales, _prepare_tables
    tables = _prepare_tables(store)
    forecast = forecast_sales(_dated_sales(tables, report_date), report_date)
    factor = (request.query_params.get("sales_factor") or "").strip()
    if factor:
        forecast["scenario"] = apply_scenario(forecast, {
            "name": request.query_params.get("scenario") or "Scenario",
            "sales_factor": factor,
        })
    return forecast


@router.get("/api/consolidation")
def api_consolidation(request: Request, user=Depends(require_user)):
    if not _can_see(user):
        raise HTTPException(403, "Forbidden")
    store = get_store()
    report_date = (request.query_params.get("report_date") or "").strip()
    if not report_date:
        from server.routers.saved_reports import _report_date
        report_date = _report_date(store, request)
    body = consolidate_companies(company_figures(store, report_date))
    body["official"] = False
    body["label"] = "Consolidation · blank where a company has no eligible figure"
    return body


@router.get("/api/custom-metrics")
def api_list_metrics(user=Depends(require_user)):
    assert_perm(user, "reports.manage")
    return {"metrics": list_metrics(get_store())}


@router.post("/api/custom-metrics")
def api_create_metric(body: dict = Body(...), user=Depends(require_user)):
    assert_perm(user, "reports.manage")
    try:
        return create_metric(get_store(), body, user.get("username") or "")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.put("/api/custom-metrics/{metric_id}")
def api_update_metric(metric_id: str, body: dict = Body(...), user=Depends(require_user)):
    assert_perm(user, "reports.manage")
    try:
        row = update_metric(get_store(), metric_id, body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not row:
        raise HTTPException(404, "Not found")
    return row


@router.post("/api/custom-metrics/{metric_id}/approve")
def api_approve_metric(metric_id: str, user=Depends(require_user)):
    assert_perm(user, "reports.manage")
    try:
        row = approve_metric(get_store(), metric_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not row:
        raise HTTPException(404, "Not found")
    return row
