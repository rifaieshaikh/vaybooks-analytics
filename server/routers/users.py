"""User and role administration routes."""

from fastapi import APIRouter, Depends, HTTPException

from vay.passwords import hash_password

from server.auth import (
    ALL_PERMISSIONS,
    assert_perm,
    count_admins,
    parse_new_role_name,
    permissions_of,
    public_role,
    public_roles,
    public_user,
    require_user,
    resolve_role_name,
    set_password,
    valid_permissions,
)
from server.schemas import RoleBody, RoleCreateBody, UserCreateBody, UserPatchBody
from server.store import get_store
from server.tenant import in_org

router = APIRouter()


@router.get("/api/users")
def list_users(user=Depends(require_user)):
    assert_perm(user, "users.view", "users.manage")
    store = get_store()
    return {"users": [public_user(doc, permissions_of(store, doc)) for doc in store.list_users()]}


@router.post("/api/users")
def create_user(body: UserCreateBody, user=Depends(require_user)):
    assert_perm(user, "users.manage")
    store = get_store()
    username = (body.username or "").strip()
    password = body.password or ""
    role = resolve_role_name(store, body.role)
    if not username or not password:
        raise HTTPException(400, "Username and password are required")
    if not role:
        raise HTTPException(400, "Unknown role")
    if store.get_user(username):
        raise HTTPException(400, "User already exists")
    stored = store.put_user({
        "username": username,
        "password_hash": hash_password(password),
        "role": role,
        "enabled": True,
    })
    return public_user(stored, permissions_of(store, stored))


@router.patch("/api/users/{username}")
def patch_user(username: str, body: UserPatchBody, user=Depends(require_user)):
    assert_perm(user, "users.manage")
    store = get_store()
    doc = store.get_user(username)
    if not doc or not in_org(doc):
        raise HTTPException(404, "Not found")
    last_admin = count_admins(store) <= 1 and doc.get("role") == "Admin" and doc.get("enabled", True)
    if body.role is not None:
        role = resolve_role_name(store, body.role)
        if not role:
            raise HTTPException(400, "Unknown role")
        if last_admin and role != "Admin":
            raise HTTPException(400, "Cannot change the last Admin")
        doc["role"] = role
    if body.enabled is not None:
        if last_admin and not body.enabled:
            raise HTTPException(400, "Cannot disable the last Admin")
        doc["enabled"] = bool(body.enabled)
        if not doc["enabled"]:
            store.delete_sessions_for(username)
    if body.sales_reps is not None:
        names = []
        for name in body.sales_reps:
            text = " ".join(str(name or "").split())
            if text and text not in names:
                names.append(text)
        doc["sales_reps"] = names
    if body.password:
        doc = set_password(store, doc, body.password, clear_must_change=True)
        return public_user(doc, permissions_of(store, doc))
    store.put_user(doc)
    return public_user(doc, permissions_of(store, doc))


@router.delete("/api/users/{username}")
def delete_user(username: str, user=Depends(require_user)):
    assert_perm(user, "users.manage")
    store = get_store()
    doc = store.get_user(username)
    if not doc or not in_org(doc):
        raise HTTPException(404, "Not found")
    if doc.get("role") == "Admin" and count_admins(store) <= 1:
        raise HTTPException(400, "Cannot delete the last Admin")
    store.delete_user(username)
    return {"ok": True}


@router.get("/api/roles")
def list_roles(user=Depends(require_user)):
    assert_perm(user, "roles.view", "roles.manage", "users.manage")
    permissions = user.get("permissions") or []
    show_matrix = "roles.view" in permissions or "roles.manage" in permissions
    return {
        "roles": public_roles(get_store()),
        "all_permissions": list(ALL_PERMISSIONS) if show_matrix else [],
    }


@router.post("/api/roles")
def create_role(body: RoleCreateBody, user=Depends(require_user)):
    assert_perm(user, "roles.manage")
    store = get_store()
    try:
        name = parse_new_role_name(store, body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return public_role(store.put_role(name, {"name": name, "permissions": valid_permissions(body.permissions)}))


@router.put("/api/roles/{name}")
def put_role(name: str, body: RoleBody, user=Depends(require_user)):
    assert_perm(user, "roles.manage")
    store = get_store()
    existing = resolve_role_name(store, name)
    if not existing:
        raise HTTPException(404, "Not found")
    return public_role(store.put_role(existing, {
        "name": existing,
        "permissions": valid_permissions(body.permissions),
    }))
