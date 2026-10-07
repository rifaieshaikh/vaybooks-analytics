"""Hosted-tenant controls. Desktop installs leave hosted mode off."""

from __future__ import annotations

import os
from datetime import datetime

HOURS_TYPE = "support_hours"


def hosted_mode():
    return (os.environ.get("VAY_HOSTED") or "").strip().lower() in ("1", "true", "yes")


_buckets = {}


def allow_request(ip):
    if not hosted_mode():
        return True
    minute = datetime.utcnow().strftime("%Y%m%d%H%M")
    key = "%s|%s" % (ip or "", minute)
    _buckets[key] = _buckets.get(key, 0) + 1
    if len(_buckets) > 5000:
        for old in list(_buckets):
            if not old.endswith(minute):
                _buckets.pop(old, None)
    return _buckets[key] <= rate_limit_per_minute()


def rate_limit_per_minute():
    try:
        return max(1, int(os.environ.get("VAY_RATE_LIMIT") or "600"))
    except (TypeError, ValueError):
        return 600


def license_view(store):
    """What this install can show before a commercial policy exists."""
    from server.org_policy import get_org_policy
    policy = get_org_policy(store)
    hosted = hosted_mode()
    return {
        "hosted": hosted,
        "mode": "hosted" if hosted else "local",
        "message": "Hosted install. Packs follow the saved entitlements." if hosted else "Local install. Every pack is enabled.",
        "packs": {
            "wholesale": pack_enabled(store, "wholesale"),
            "retail": pack_enabled(store, "retail"),
        },
        "company_name": policy.get("company_name") or "",
        "version": (os.environ.get("VAY_VERSION") or "dev").strip() or "dev",
        "support_contact": (os.environ.get("VAY_SUPPORT_CONTACT") or "").strip(),
        "renewal": None,
        "renewal_note": "Trial, renewal, and expiry stay unset until a commercial policy is written.",
    }


def diagnostics_view(store):
    """Support bundle without credentials."""
    counts = {}
    for row in store.list_rows() or []:
        kind = row.get("type") or ""
        if kind in ("user", "session"):
            continue
        counts[kind] = counts.get(kind, 0) + 1
    view = license_view(store)
    view["row_counts"] = counts
    view["uploads"] = sum(1 for item in (store.list_uploads() or []) if not item.get("dry_run"))
    return view


def pack_enabled(store, pack):
    """Desktop can adopt a pack. A hosted tenant needs the entitlement turned on."""
    if not hosted_mode():
        return True
    from server.org_policy import get_org_policy
    ent = (get_org_policy(store).get("entitlements") or {})
    return bool(ent.get(pack))


def set_entitlement(store, pack, enabled):
    from server.org_policy import get_org_policy, save_org_policy
    current = get_org_policy(store)
    ent = dict(current.get("entitlements") or {})
    ent[str(pack)] = bool(enabled)
    return save_org_policy(store, {"entitlements": ent})


def record_support_hours(store, hours, note=""):
    try:
        amount = round(float(hours), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError("hours must be a number") from exc
    if amount < 0:
        raise ValueError("hours must be 0 or more")
    uk = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    store.upsert_row({
        "type": HOURS_TYPE,
        "uk": uk,
        "source_upload_id": "",
        "fields": {"hours": amount, "note": str(note or ""), "recorded_at": uk},
    })
    return {"hours": amount, "note": str(note or "")}


def support_gate(store):
    """The Phase 5 gate is met only when hours per tenant fall as tenants grow.

    One install cannot show that decline, so the gate stays open.
    """
    total = 0.0
    points = 0
    for row in store.rows_of_type(HOURS_TYPE) or []:
        try:
            total += float((row.get("fields") or {}).get("hours") or 0)
        except (TypeError, ValueError):
            continue
        points += 1
    return {
        "met": False,
        "reason": "Support hours per tenant are recorded. The gate stays open until hours fall as the tenant count grows.",
        "points": points,
        "hours": round(total, 2),
    }
