"""Phase 2 scorecard, decisions, saved views, and onboarding preview."""

from fastapi import APIRouter, Depends, HTTPException, Request

from server.auth import assert_perm, require_user
from server.phase2 import build_bundle, get_saved_views, onboarding, open_review_count, save_saved_view
from server.schemas import SavedViewBody
from server.store import get_store

router = APIRouter()


def _run_date(store, run_id):
    run = None
    if run_id:
        run = store.get_run(run_id)
    if not run:
        run = store.latest_succeeded_run() if hasattr(store, "latest_succeeded_run") else None
    if not run:
        runs = [r for r in (store.list_runs() or []) if r.get("status") == "succeeded"]
        run = runs[0] if runs else None
    if not run or not run.get("report_date"):
        raise HTTPException(400, "Create a report first")
    return run


@router.get("/api/analytics")
def api_analytics(request: Request, user=Depends(require_user)):
    store = get_store()
    run = _run_date(store, request.query_params.get("run") or request.query_params.get("run_id"))
    recon = ((run.get("manifest") or {}).get("reconciliation") or {})
    bundle = build_bundle(
        store,
        run.get("report_date"),
        exceptions=recon.get("exceptions") or [],
        review_count=open_review_count(store),
    )
    perms = set(user.get("permissions") or [])
    out = {"report_date": bundle["report_date"], "run_id": str(run.get("_id") or run.get("id") or "")}
    if "reports.view.scorecard" in perms:
        out["scorecard"] = bundle["scorecard"]
        out["sales_change"] = bundle["sales_change"]
        out["customer_movement"] = bundle["customer_movement"]
    if "reports.view.followup" in perms:
        out["collection"] = bundle["collection"]
    if "reports.view.items" in perms:
        out["stock"] = bundle["stock"]
    if "reports.view.quality" in perms:
        out["quality"] = bundle["quality"]
    if len(out) == 2:
        raise HTTPException(403, "Not allowed")
    return out


@router.get("/api/analytics/views")
def api_get_views(user=Depends(require_user)):
    return {"views": get_saved_views(get_store(), user.get("username") or "")}


@router.put("/api/analytics/views")
def api_save_view(body: SavedViewBody, user=Depends(require_user)):
    try:
        views = save_saved_view(get_store(), user.get("username") or "", body.page, body.filters)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"views": views}


@router.get("/api/analytics/onboarding")
def api_onboarding(request: Request, user=Depends(require_user)):
    store = get_store()
    report_date = request.query_params.get("report_date") or ""
    if not report_date:
        try:
            run = _run_date(store, request.query_params.get("run") or "")
            report_date = run.get("report_date") or ""
        except HTTPException:
            report_date = ""
    return onboarding(store, report_date)
