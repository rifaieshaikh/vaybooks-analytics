"""Open and reset the labeled demo dataset."""

from fastapi import APIRouter, Depends, HTTPException

from server.auth import assert_perm, require_user
from server.demo import demo_status, open_demo
from server.store import get_store

router = APIRouter()


@router.get("/api/demo")
def api_demo_status(user=Depends(require_user)):
    assert_perm(user, "reports.view.followup")
    return demo_status(get_store())


@router.post("/api/demo")
def api_open_demo(user=Depends(require_user)):
    assert_perm(user, "reports.create")
    try:
        return open_demo(get_store(), user.get("username") or "")
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
