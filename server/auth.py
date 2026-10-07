"""Users, roles, session permissions. Passwords are bcrypt (legacy SHA-256 accepted)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Iterable

from fastapi import Cookie, HTTPException, Request

from vay.passwords import (
    bootstrap_must_change,
    bootstrap_password,
    hash_password,
    needs_rehash,
    password_ok,
)

from server.settings import SESSION_COOKIE

ALL_PERMISSIONS = (
    "sales.view",
    "sales.upload",
    "sales.map",
    "receipt.view",
    "receipt.upload",
    "receipt.map",
    "credit_note.view",
    "credit_note.upload",
    "credit_note.map",
    "arr.view",
    "arr.upload",
    "arr.map",
    "payments.view",
    "payments.upload",
    "payments.map",
    "party.view",
    "party.upload",
    "party.map",
    "customer.view",
    "items.view",
    "items.upload",
    "items.map",
    "stock.view",
    "stock.upload",
    "stock.map",
    "reservation.view",
    "reservation.upload",
    "reservation.map",
    "incoming.view",
    "incoming.upload",
    "incoming.map",
    "item_cost.view",
    "item_cost.upload",
    "item_cost.map",
    "opening_cash.view",
    "opening_cash.upload",
    "opening_cash.map",
    "payable.view",
    "payable.upload",
    "payable.map",
    "reports.create",
    "reports.view.performance",
    "reports.view.followup",
    "reports.view.monthly",
    "reports.view.items",
    "reports.view.profit",
    "reports.view.issues",
    "reports.view.scorecard",
    "reports.view.quality",
    "actions.manage",
    "reports.manage",
    "settings.import",
    "settings.advanced",
    "users.view",
    "users.manage",
    "roles.view",
    "roles.manage",
)

SEED_ROLE_NAMES = ("Admin", "Sales", "Finance", "Warehouse", "Viewer")
_ROLE_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9 _-]{0,38}[A-Za-z0-9])?$")

TYPE_PERM = {
    "sales": "sales",
    "receipt": "receipt",
    "credit_note": "credit_note",
    "arr": "arr",
    "payments": "payments",
    "party": "party",
    "customer": "customer",
    "items": "items",
    "stock": "stock",
    "reservation": "reservation",
    "incoming": "incoming",
    "item_cost": "item_cost",
    "opening_cash": "opening_cash",
    "payable": "payable",
}

REPORT_GROUP_PERM = {
    "Performance": "reports.view.performance",
    "Follow-up": "reports.view.followup",
    "Monthly": "reports.view.monthly",
    "Items": "reports.view.items",
    "Profit": "reports.view.profit",
    "Data issues": "reports.view.issues",
    "Scorecard": "reports.view.scorecard",
}

# Step id or workbook id -> permission. A tuple means any one of those permissions.
REPORT_ACCESS = {
    "Sales rep performance": "reports.view.performance",
    "Account performance": "reports.view.performance",
    "Group performance": "reports.view.performance",
    "sales_rep_performance_report": "reports.view.performance",
    "account_performance_report": "reports.view.performance",
    "group_performance_report": "reports.view.performance",
    "Sales follow-up": "reports.view.followup",
    "Collection follow-up": "reports.view.followup",
    "Fiscal monthly sales and collection": "reports.view.monthly",
    "Fiscal monthly account performance": "reports.view.monthly",
    "Fiscal monthly group performance": "reports.view.monthly",
    "fiscal_monthly_sales_rep_performance_report": "reports.view.monthly",
    "fiscal_monthly_account_performance_report": "reports.view.monthly",
    "fiscal_monthly_group_performance_report": "reports.view.monthly",
    "Item-wise sales": "reports.view.items",
    "Item cost exceptions": "reports.view.items",
    "Item monthly quantity": "reports.view.items",
    "item_wise_sales": "reports.view.items",
    "item_cost_exceptions": "reports.view.items",
    "item_wise_monthly_qty": "reports.view.items",
    "Item-wise profit": "reports.view.profit",
    "Item monthly profit": "reports.view.profit",
    "Monthly profit": "reports.view.profit",
    "Expense by category": "reports.view.profit",
    "Unmapped payment accounts": "reports.view.profit",
    "Expense by account": "reports.view.profit",
    "item_wise_profit": "reports.view.profit",
    "item_wise_monthly_profit": "reports.view.profit",
    "monthly_profit_report": "reports.view.profit",
    "expense_by_category": "reports.view.profit",
    "unmapped_payment_accounts": "reports.view.profit",
    "expense_by_account": "reports.view.profit",
    "Source data warnings": "reports.view.issues",
    "source_data_warnings": "reports.view.issues",
    "phase2_scorecard": "reports.view.scorecard",
    "phase2_sales_change": "reports.view.scorecard",
    "phase2_customer_movement": "reports.view.scorecard",
    "phase2_collection": "reports.view.followup",
    "phase2_stock": "reports.view.items",
    "phase2_quality": "reports.view.quality",
    "360-customers": "customer.view",
    "360-groups": "customer.view",
    "360-reps": "customer.view",
    "360-business": "customer.view",
    "360-items": "stock.view",
    "360-category": "stock.view",
    "360-item_group": "stock.view",
    "360-brand": "stock.view",
    "360-supplier": "stock.view",
    "360-repurchase": ("customer.view", "stock.view"),
}

CHECK_STEPS = {"reconcile", "analytics", "dashboard", "save-reports", "weekly-sheets"}


def can_generate(perms, report_id: str) -> bool:
    """True when this role may ask Create to build that report."""
    name = str(report_id or "")
    if name in CHECK_STEPS:
        return True
    if name.startswith("sales_follow_up_") or name.startswith("collection_follow_up_"):
        needed = REPORT_GROUP_PERM["Follow-up"]
        return needed in set(perms or [])
    needed = REPORT_ACCESS.get(name)
    if not needed:
        return False
    if isinstance(needed, str):
        needed = (needed,)
    have = set(perms or [])
    return any(perm in have for perm in needed)


def filter_report_ids(ids, perms):
    return [str(name) for name in (ids or []) if name and can_generate(perms, str(name))]


def report_view_perm(report):
    """Permission required to read a saved sheet. Empty means it is not gated."""
    rid = str((report or {}).get("id") or "")
    if rid.startswith("sales_follow_up_") or rid.startswith("collection_follow_up_"):
        return REPORT_GROUP_PERM["Follow-up"]
    needed = REPORT_ACCESS.get(rid)
    if isinstance(needed, str):
        return needed
    title = str((report or {}).get("title") or "")
    needed = REPORT_ACCESS.get(title)
    if isinstance(needed, str):
        return needed
    return REPORT_GROUP_PERM.get((report or {}).get("group") or "")


def report_allowed(report, perms) -> bool:
    perm = report_view_perm(report)
    if not perm:
        return True
    return perm in set(perms or [])

_VIEW_PREFIX = "reports.view."


def _is_view_perm(name: str) -> bool:
    return name.endswith(".view") or name.startswith(_VIEW_PREFIX)


def seed_role_permissions() -> dict[str, list[str]]:
    sales = [
        "sales.view",
        "sales.upload",
        "sales.map",
        "receipt.view",
        "receipt.upload",
        "receipt.map",
        "credit_note.view",
        "party.view",
        "customer.view",
        "items.view",
        "reports.view.performance",
        "reports.view.followup",
        "reports.view.monthly",
        "reports.view.scorecard",
        "actions.manage",
        "reports.manage",
    ]
    finance = [
        "arr.view",
        "arr.upload",
        "arr.map",
        "receipt.view",
        "receipt.upload",
        "receipt.map",
        "credit_note.view",
        "credit_note.upload",
        "credit_note.map",
        "payments.view",
        "payments.upload",
        "payments.map",
        "opening_cash.view",
        "opening_cash.upload",
        "opening_cash.map",
        "payable.view",
        "payable.upload",
        "payable.map",
        "party.view",
        "party.upload",
        "party.map",
        "customer.view",
        "reports.create",
        "reports.view.profit",
        "reports.view.issues",
        "reports.view.monthly",
        "reports.view.scorecard",
        "reports.view.quality",
        "actions.manage",
        "reports.manage",
    ]
    warehouse = [
        "items.view",
        "items.upload",
        "items.map",
        "stock.view",
        "stock.upload",
        "stock.map",
        "reservation.view",
        "reservation.upload",
        "reservation.map",
        "incoming.view",
        "incoming.upload",
        "incoming.map",
        "item_cost.view",
        "item_cost.upload",
        "item_cost.map",
        "reports.view.items",
    ]
    viewer = [
        p for p in ALL_PERMISSIONS
        if _is_view_perm(p) and p not in ("reports.view.profit", "users.view", "roles.view")
    ]
    return {
        "Admin": list(ALL_PERMISSIONS),
        "Sales": sales,
        "Finance": finance,
        "Warehouse": warehouse,
        "Viewer": viewer,
    }


def public_user(doc, permissions=None):
    if not doc:
        return None
    return {
        "username": doc.get("username"),
        "role": doc.get("role"),
        "enabled": bool(doc.get("enabled", True)),
        "permissions": list(permissions or []),
        "must_change_password": bool(doc.get("must_change_password")),
        "org_id": (doc.get("org_id") or "default"),
        "sales_reps": [str(name) for name in (doc.get("sales_reps") or []) if str(name).strip()],
    }


def public_role(doc):
    if not doc:
        return None
    return {
        "name": doc.get("name") or doc.get("_id"),
        "permissions": list(doc.get("permissions") or []),
    }


def normalize_role_name(name: str) -> str:
    return " ".join(str(name or "").split())


def listed_role_names(store) -> list[str]:
    names = []
    for doc in store.list_roles():
        name = str(doc.get("name") or doc.get("_id") or "").strip()
        if name:
            names.append(name)
    return names


def resolve_role_name(store, name: str) -> str | None:
    wanted = normalize_role_name(name)
    if not wanted:
        return None
    key = wanted.lower()
    for existing in listed_role_names(store):
        if existing.lower() == key:
            return existing
    return None


def parse_new_role_name(store, name: str) -> str:
    cleaned = normalize_role_name(name)
    if not cleaned:
        raise ValueError("Name is required")
    if len(cleaned) > 40:
        raise ValueError("Name is too long")
    if not _ROLE_NAME_RE.fullmatch(cleaned):
        raise ValueError("Use letters, numbers, spaces, hyphens, or underscores")
    if resolve_role_name(store, cleaned):
        raise ValueError("Role already exists")
    return cleaned


def public_roles(store):
    seed_order = {name: i for i, name in enumerate(SEED_ROLE_NAMES)}
    roles = [public_role(d) for d in store.list_roles() if d]
    roles.sort(key=lambda r: (seed_order.get(r["name"], len(seed_order)), (r.get("name") or "").lower()))
    return roles


def permissions_of(store, user) -> list[str]:
    if not user:
        return []
    role = store.get_role(user.get("role") or "")
    perms = list((role or {}).get("permissions") or [])
    return [p for p in perms if p in ALL_PERMISSIONS]


def has_perm(user_perms: Iterable[str], *needed: str) -> bool:
    have = set(user_perms or [])
    return any(name in have for name in needed)


def type_perm(type_name: str, action: str) -> str:
    prefix = TYPE_PERM.get(type_name)
    if not prefix:
        return ""
    return "%s.%s" % (prefix, action)


def seed_store(store):
    roles = seed_role_permissions()
    existing = {(r.get("name") or r.get("_id")): r for r in store.list_roles()}
    if not existing:
        for name in SEED_ROLE_NAMES:
            store.put_role(name, {"name": name, "permissions": list(roles[name])})
    else:
        for name in SEED_ROLE_NAMES:
            wanted = list(roles[name])
            current = existing.get(name)
            if not current:
                store.put_role(name, {"name": name, "permissions": wanted})
                continue
            have = list(current.get("permissions") or [])
            extra = list(ALL_PERMISSIONS) if name == "Admin" else wanted
            changed = False
            for perm in extra:
                if perm not in have:
                    have.append(perm)
                    changed = True
            if changed:
                store.put_role(name, {"name": name, "permissions": have})
    if not store.get_user("admin"):
        store.put_user({
            "username": "admin",
            "password_hash": hash_password(bootstrap_password()),
            "role": "Admin",
            "enabled": True,
            "must_change_password": bootstrap_must_change(),
        })


def session_expiry():
    return datetime.utcnow() + timedelta(days=7)


def current_user_from_request(store, token: str | None):
    if not token:
        return None
    session = store.get_session(token)
    if not session:
        return None
    expires = session.get("expires_at")
    if expires and expires < datetime.utcnow():
        store.delete_session(token)
        return None
    user = store.get_user(session.get("username") or "")
    if not user or not user.get("enabled", True):
        return None
    from server.tenant import doc_org, set_org
    set_org(doc_org(user))
    perms = permissions_of(store, user)
    return public_user(user, perms)


async def require_user(request: Request, vay_session: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
    from server.store import get_store

    store = get_store()
    token = vay_session
    user = current_user_from_request(store, token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    request.state.user = user
    return user


def assert_perm(user, *needed: str):
    if not has_perm(user.get("permissions") or [], *needed):
        raise HTTPException(status_code=403, detail="Forbidden")


def can_upload_type(user, type_name: str) -> bool:
    return has_perm(user.get("permissions") or [], type_perm(type_name, "upload"), "settings.import")


def can_import_any(user) -> bool:
    perms = user.get("permissions") or []
    if "settings.import" in perms:
        return True
    return any(str(p).endswith(".upload") for p in perms)


def metric_visible(perms, metric_id: str) -> bool:
    """True when this role may see that governed metric's figures."""
    have = set(perms or [])
    if "reports.manage" in have:
        return True
    from vay.phase4 import METRIC_META

    family = (METRIC_META.get(metric_id) or {}).get("family") or ""
    allowed = {
        "scorecard": ("reports.view.scorecard", "reports.view.performance"),
        "followup": ("reports.view.followup", "reports.view.scorecard", "reports.view.performance"),
        "items": ("reports.view.items", "stock.view"),
        "quality": ("reports.view.quality", "reports.view.issues"),
    }.get(family, ())
    if metric_id == "gross_margin":
        allowed = tuple(allowed) + ("reports.view.profit",)
    return any(name in have for name in allowed)


def redact_manifest(manifest, perms):
    """Drop headline sales and AR figures the caller cannot view."""
    if not isinstance(manifest, dict):
        return manifest
    out = dict(manifest)
    eligibility = manifest.get("eligibility") or {}
    if isinstance(eligibility, dict):
        out["eligibility"] = {
            key: value for key, value in eligibility.items() if metric_visible(perms, key)
        }
    recon = manifest.get("reconciliation")
    if isinstance(recon, dict):
        out["reconciliation"] = _redact_recon(recon, perms)
    return out


def _redact_recon(recon, perms):
    see_sales = metric_visible(perms, "sales_mtd") or metric_visible(perms, "sales_ytd")
    see_ar = metric_visible(perms, "ar_balance")
    if not see_sales and not see_ar:
        return {"status": "unavailable", "message": "", "exceptions": []}
    out = dict(recon)
    for field in ("computed", "expected", "deltas", "checks"):
        raw = recon.get(field)
        if not isinstance(raw, dict):
            continue
        kept = {}
        for key, value in raw.items():
            if key in ("report_date", "tolerance"):
                kept[key] = value
            elif key in ("sales_mtd", "sales_ytd") and see_sales:
                kept[key] = value
            elif key == "ar_balance" and see_ar:
                kept[key] = value
            elif key not in ("sales_mtd", "sales_ytd", "ar_balance") and metric_visible(perms, key):
                kept[key] = value
        out[field] = kept
    exceptions = []
    for row in recon.get("exceptions") or []:
        mid = (row or {}).get("metric_id") or ""
        if not mid or mid in ("sales_mtd", "sales_ytd"):
            if see_sales or (not mid and see_ar):
                exceptions.append(row)
        elif mid == "ar_balance":
            if see_ar:
                exceptions.append(row)
        elif metric_visible(perms, mid):
            exceptions.append(row)
    out["exceptions"] = exceptions
    return out


def filter_snapshot(snapshot, perms):
    if not snapshot:
        return snapshot
    reports = []
    for report in snapshot.get("reports") or []:
        if not report_allowed(report, perms):
            continue
        reports.append(report)
    out = dict(snapshot)
    out["reports"] = reports
    return out


def count_admins(store):
    n = 0
    for user in store.list_users():
        if user.get("role") == "Admin" and user.get("enabled", True):
            n += 1
    return n


def check_password(user, password: str) -> bool:
    return password_ok(password, (user or {}).get("password_hash") or "")


def upgrade_password_hash(store, user, password: str):
    """Re-hash with bcrypt after a successful login when the stored hash is legacy SHA-256."""
    if not user or not needs_rehash(user.get("password_hash")):
        return user
    user = dict(user)
    user["password_hash"] = hash_password(password)
    store.put_user(user)
    return user


def set_password(store, user, password: str, *, clear_must_change: bool = True):
    user = dict(user or {})
    user["password_hash"] = hash_password(password)
    if clear_must_change:
        user["must_change_password"] = False
    store.put_user(user)
    return user


def valid_permissions(names) -> list[str]:
    out = []
    for name in names or []:
        if name in ALL_PERMISSIONS and name not in out:
            out.append(name)
    return out
