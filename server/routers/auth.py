"""Authentication routes."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from server.auth import (
    check_password,
    permissions_of,
    public_user,
    require_user,
    session_expiry,
    set_password,
    upgrade_password_hash,
)
from server.rate_limit import check_login_allowed, clear_login_failures, client_ip, record_login_failure
from server.route_helpers import cookie_kwargs
from server.schemas import ChangePasswordBody, LoginBody
from server.settings import SESSION_COOKIE, login_rate_limit, login_rate_window_sec
from server.store import get_store

router = APIRouter()


@router.post("/api/auth/login")
def login(body: LoginBody, request: Request, response: Response):
    ip = client_ip(request)
    if not check_login_allowed(ip, window=login_rate_window_sec(), limit=login_rate_limit()):
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    store = get_store()
    username = (body.username or "").strip()
    user = store.get_user(username)
    if not user or not user.get("enabled", True) or not check_password(user, body.password):
        record_login_failure(ip)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    clear_login_failures(ip)
    from server.audit import record
    from server.tenant import doc_org, set_org
    set_org(doc_org(user))
    user = upgrade_password_hash(store, user, body.password)
    record(store, "login", username, "Signed in")
    token = secrets.token_urlsafe(32)
    store.put_session(token, {"username": username, "expires_at": session_expiry()})
    response.set_cookie(value=token, **cookie_kwargs())
    return public_user(user, permissions_of(store, user))


@router.post("/api/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        get_store().delete_session(token)
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@router.get("/api/auth/me")
def me(user=Depends(require_user)):
    return user


@router.post("/api/auth/change-password")
def change_password(body: ChangePasswordBody, user=Depends(require_user)):
    new_password = body.new_password or ""
    if len(new_password) < 8:
        raise HTTPException(400, "New password must be at least 8 characters")
    store = get_store()
    doc = store.get_user(user["username"])
    if not doc or not check_password(doc, body.current_password or ""):
        raise HTTPException(400, "Current password is incorrect")
    doc = set_password(store, doc, new_password, clear_must_change=True)
    return public_user(doc, permissions_of(store, doc))
