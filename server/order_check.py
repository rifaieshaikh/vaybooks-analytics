"""Configurable prospective order-creation check.

Defaults live in app settings; customers / groups / reps can override thresholds.
Premium and blacklist flags are stored on the customer row.
"""

from __future__ import annotations

from vay.dates import clean_text, number_, parse_date, today_ist
from vay.settlement import oldest_due_invoice

from server.due_days import ENTITIES

SETTING_TYPE = "app_setting"
SETTING_UK = "order_check"
OVERRIDE_TYPE = "order_check"

ACTIONS = (
    "create_order",
    "reduce_volume",
    "follow_up",
    "push_back",
    "strong_push_back",
)

ACTION_LABELS = {
    "create_order": "Create order",
    "reduce_volume": "Reduce order volume",
    "follow_up": "Follow up",
    "push_back": "Push back",
    "strong_push_back": "Strong push back",
}

REASON_GROUP = {
    "blacklisted": "credit",
    "urgent_age": "credit",
    "past_due_days": "credit",
    "followup_age": "credit",
    "credit_limit": "credit",
    "max_order_value": "size",
    "order_vs_avg": "size",
    "order_vs_usual_qty": "size",
    "ordering_frequency": "frequency",
    "ordering_pattern": "behavior",
    "ordered_overdue_recent": "behavior",
    "settlement_pattern": "behavior",
    "premium_demote": "premium",
    "ok": "ok",
}

REASON_GROUP_LABELS = {
    "credit": "Credit & due",
    "size": "Order size",
    "frequency": "Frequency",
    "behavior": "Behavior",
    "premium": "Premium",
    "ok": "OK",
}

# Higher = more severe
_ACTION_RANK = {name: i for i, name in enumerate(ACTIONS)}

DEFAULT_POLICY = {
    "followup_age_days": 15,
    "urgent_age_days": 30,
    "overdue_grace_days": 0,
    "credit_limit": 0,
    "max_order_value": 0,
    "max_order_value_vs_avg": 1.5,
    "avg_sales_window": 5,
    "max_order_qty_vs_usual": 1.3,
    "min_gap_factor": 0.7,
    "flagged_ratio_push": 0.25,
    "settlement_old_share_push": 0.45,
    "premium_limit_factor": 1.5,
    "premium_demote": True,
    "reduce_vs_usual": 1.0,
}

# Keys editable in defaults / overrides (booleans stay bool)
_NUMERIC_KEYS = {
    "followup_age_days",
    "urgent_age_days",
    "overdue_grace_days",
    "credit_limit",
    "max_order_value",
    "max_order_value_vs_avg",
    "avg_sales_window",
    "max_order_qty_vs_usual",
    "min_gap_factor",
    "flagged_ratio_push",
    "settlement_old_share_push",
    "premium_limit_factor",
    "reduce_vs_usual",
}
_BOOL_KEYS = {"premium_demote"}
# 0 means unlimited for these caps
_UNLIMITED_ZERO = {"credit_limit", "max_order_value"}


def _invalidate_book(store):
    if hasattr(store, "_360_book"):
        store._360_book = None


def _truthy(raw):
    if isinstance(raw, bool):
        return raw
    return clean_text(raw).lower() in ("1", "y", "yes", "true", "on")


def _clamp_nonneg(raw, fallback=0):
    try:
        val = float(number_(raw))
    except (TypeError, ValueError):
        return fallback
    if val < 0:
        return fallback
    return val


def _normalize_policy_patch(raw, *, partial=False):
    """Return cleaned policy fields. If partial, only include provided keys."""
    src = raw or {}
    out = {}
    keys = list(DEFAULT_POLICY.keys()) if not partial else [
        k for k in DEFAULT_POLICY.keys() if k in src
    ]
    for key in keys:
        if key not in src and partial:
            continue
        if key in _BOOL_KEYS:
            out[key] = _truthy(src.get(key) if key in src else DEFAULT_POLICY[key])
            continue
        fallback = DEFAULT_POLICY[key]
        # Legacy null → default (0 for unlimited caps)
        raw_val = src.get(key) if key in src else fallback
        if raw_val is None and key in _UNLIMITED_ZERO:
            out[key] = 0.0
            continue
        if key in ("avg_sales_window", "followup_age_days", "urgent_age_days", "overdue_grace_days"):
            out[key] = int(_clamp_nonneg(raw_val, fallback))
        else:
            out[key] = float(_clamp_nonneg(raw_val, fallback))
    return out


def get_default_policy(store):
    row = store.find_row(SETTING_TYPE, SETTING_UK) or {}
    fields = row.get("fields") or {}
    merged = dict(DEFAULT_POLICY)
    if fields:
        merged.update(_normalize_policy_patch(fields, partial=True))
    return merged


def save_default_policy(store, patch):
    current = get_default_policy(store)
    updates = _normalize_policy_patch(patch or {}, partial=True)
    current.update(updates)
    store.upsert_row({
        "type": SETTING_TYPE,
        "uk": SETTING_UK,
        "source_upload_id": "",
        "fields": current,
    })
    _invalidate_book(store)
    return {"policy": current}


def get_order_check_settings(store):
    return {"policy": get_default_policy(store), "defaults": dict(DEFAULT_POLICY)}


def override_uk(entity, name):
    entity = clean_text(entity).lower()
    if entity not in ENTITIES:
        raise ValueError("Entity must be customer, group, or rep")
    uk = clean_text(name)
    if not uk:
        raise ValueError("Name required")
    return "%s:%s" % (entity, uk.lower())


def _override_map(store):
    out = {}
    for row in store.rows_of_type(OVERRIDE_TYPE):
        fields = dict(row.get("fields") or {})
        entity = clean_text(fields.get("Entity")).lower()
        name = clean_text(fields.get("Name") or fields.get("Account Name"))
        if entity not in ENTITIES or not name:
            uk = clean_text(row.get("uk"))
            if ":" in uk:
                entity, name = uk.split(":", 1)
                entity = entity.lower()
                name = clean_text(name)
            else:
                continue
        if entity not in ENTITIES or not name:
            continue
        patch = _normalize_policy_patch(fields, partial=True)
        if patch:
            out[(entity, name.lower())] = patch
    return out


def get_override(store, entity, name, overrides=None):
    entity = clean_text(entity).lower()
    name_l = clean_text(name).lower()
    if not name_l or entity not in ENTITIES:
        return None
    overrides = overrides if overrides is not None else _override_map(store)
    return overrides.get((entity, name_l))


def save_policy_override(store, entity, name, patch=None, clear=False):
    """Set partial override; clear=True or patch=None removes it."""
    entity = clean_text(entity).lower()
    name = clean_text(name)
    uk = override_uk(entity, name)
    if clear or patch is None:
        store.delete_row(OVERRIDE_TYPE, uk)
        _invalidate_book(store)
        return {"cleared": True, "entity": entity, "name": name, "override": None}
    cleaned = _normalize_policy_patch(patch, partial=True)
    if not cleaned:
        store.delete_row(OVERRIDE_TYPE, uk)
        _invalidate_book(store)
        return {"cleared": True, "entity": entity, "name": name, "override": None}
    fields = {"Entity": entity, "Name": name}
    fields.update(cleaned)
    store.upsert_row({
        "type": OVERRIDE_TYPE,
        "uk": uk,
        "source_upload_id": "",
        "fields": fields,
    })
    _invalidate_book(store)
    return {"cleared": False, "entity": entity, "name": name, "override": cleaned}


def _merge_policy(base, patch):
    out = dict(base)
    if patch:
        out.update(patch)
    return out


def resolve_policy(store, *, customer_uk="", group="", rep="", overrides=None, default=None):
    """customer → group → sales rep → global default."""
    overrides = overrides if overrides is not None else _override_map(store)
    default = dict(default if default is not None else get_default_policy(store))
    layers = [("default", default, False)]
    policy = dict(default)
    source = "default"
    own = False

    for entity, value, is_own in (
        ("rep", rep, False),
        ("group", group, False),
        ("customer", customer_uk, True),
    ):
        patch = get_override(store, entity, value, overrides)
        if patch:
            policy = _merge_policy(policy, patch)
            source = entity
            own = is_own
            layers.append((entity, patch, is_own))

    return {
        "policy": policy,
        "source": source,
        "own": own,
        "layers": [{"entity": e, "patch": p if e != "default" else None, "own": o} for e, p, o in layers],
    }


def resolve_entity_policy(store, entity, name, *, group="", rep="", customer_uk=""):
    entity = clean_text(entity).lower()
    name = clean_text(name)
    overrides = _override_map(store)
    default = get_default_policy(store)
    if entity == "customer":
        return resolve_policy(
            store,
            customer_uk=name or customer_uk,
            group=group,
            rep=rep,
            overrides=overrides,
            default=default,
        )
    if entity == "group":
        own = get_override(store, "group", name, overrides)
        policy = _merge_policy(default, own) if own else dict(default)
        return {
            "policy": policy,
            "source": "group" if own else "default",
            "own": bool(own),
            "override": own,
        }
    if entity == "rep":
        own = get_override(store, "rep", name, overrides)
        policy = _merge_policy(default, own) if own else dict(default)
        return {
            "policy": policy,
            "source": "rep" if own else "default",
            "own": bool(own),
            "override": own,
        }
    return {"policy": dict(default), "source": "default", "own": False, "override": None}


def read_customer_flags(fields):
    fields = fields or {}
    return {
        "premium": _truthy(fields.get("Premium")),
        "blacklisted": _truthy(fields.get("Blacklisted")),
    }


def save_customer_flags(store, uk, *, premium=None, blacklisted=None):
    from server.customers import account_uk, ensure_customer_and_party

    uk = account_uk(uk)
    row = store.find_row("customer", uk)
    if not row:
        party = store.find_row("party", uk)
        if not party:
            return None
        name = clean_text((party.get("fields") or {}).get("Account Name"))
        if not name:
            return None
        ensure_customer_and_party(store, name, "", clean_text((party.get("fields") or {}).get("Group")))
        row = store.find_row("customer", uk)
        if not row:
            return None
    fields = dict(row.get("fields") or {})
    if premium is not None:
        fields["Premium"] = "Yes" if _truthy(premium) else "No"
    if blacklisted is not None:
        fields["Blacklisted"] = "Yes" if _truthy(blacklisted) else "No"
    store.upsert_row({
        "type": "customer",
        "uk": uk,
        "source_upload_id": row.get("source_upload_id") or "",
        "fields": fields,
    })
    _invalidate_book(store)
    flags = read_customer_flags(fields)
    return {"uk": uk, **flags}


def _oldest_open_meta(detail):
    """Reuse Due's oldest_due_* when present; else same helper on open_invoices."""
    if detail.get("oldest_due_age") is not None:
        kind = clean_text(detail.get("oldest_due_kind") or "").lower()
        return {
            "oldest_open_age": int(number_(detail.get("oldest_due_age") or 0)),
            "oldest_open_kind": kind,
            "oldest_open_what": clean_text(detail.get("oldest_due_what") or kind),
        }
    meta = oldest_due_invoice(detail.get("open_invoices") or [])
    return {
        "oldest_open_age": int(meta.get("age_days") or 0),
        "oldest_open_kind": clean_text(meta.get("kind") or ""),
        "oldest_open_what": clean_text(meta.get("what") or meta.get("invoice") or ""),
    }


def _avg_sale_amount(detail, window):
    ordering = detail.get("ordering") or {}
    overall = ordering.get("overall") or {}
    count = int(number_(overall.get("sales_count") or 0))
    value = float(number_(overall.get("sales_value") or 0))
    if count > 0 and value > 0:
        return value / count
    ytd = float(number_(detail.get("ytd_sales") or 0))
    if ytd > 0:
        return ytd
    return 0.0


def _usual_qty(detail):
    buying = detail.get("buying") or {}
    last = buying.get("last_order") or []
    if last:
        return sum(float(number_(x.get("qty") or 0)) for x in last)
    periods = buying.get("periods") or {}
    for key in ("this_year", "last_year", "all"):
        items = (periods.get(key) or {}).get("items") or []
        if items:
            # Typical basket ≈ top usual items once
            usual_names = set(buying.get("usual") or [])
            picked = [i for i in items if i.get("name") in usual_names] or items[:5]
            times = max((int(number_(i.get("times") or 1)) for i in picked), default=1)
            total = sum(float(number_(i.get("qty") or 0)) for i in picked)
            return total / max(times, 1)
    return 0.0


def _avg_gap_days(detail):
    buying = detail.get("buying") or {}
    periods = buying.get("periods") or {}
    gaps = []
    for key in ("this_year", "all", "last_year"):
        for item in (periods.get(key) or {}).get("items") or []:
            g = int(number_(item.get("avg_gap_days") or 0))
            if g > 0:
                gaps.append(g)
        if gaps:
            break
    if not gaps:
        return 0
    return int(sum(gaps) / len(gaps))


def _as_date(value):
    from datetime import date, datetime

    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = parse_date(value)
    if isinstance(parsed, datetime):
        return parsed.date()
    return parsed


def _days_since_last_sale(detail):
    as_of = _as_date(detail.get("as_of")) or _as_date(today_ist())
    last = _as_date(detail.get("last_sale"))
    if not last or not as_of:
        return None
    return max(0, (as_of - last).days)


def _flagged_ratio(detail):
    overall = (detail.get("ordering") or {}).get("overall") or {}
    sales = float(number_(overall.get("sales_value") or 0))
    flagged = float(number_(overall.get("flagged_value") or 0))
    if sales <= 0:
        return 0.0
    return flagged / sales


def _settlement_old_share(detail):
    settlements = detail.get("settlements") or {}
    overall = settlements.get("overall") or {}
    buckets = overall.get("buckets") or detail.get("collection_buckets") or {}
    total = float(number_(overall.get("total") or 0))
    if isinstance(buckets, dict):
        if total <= 0:
            total = sum(float(number_(v) or 0) for v in buckets.values())
        if total <= 0:
            return 0.0
        bands = detail.get("aging_bands") or []
        if bands:
            oldest_key = bands[-1].get("key")
            amt = float(number_(buckets.get(oldest_key) or 0))
        else:
            # Last key by typical band order
            keys = list(buckets.keys())
            amt = float(number_(buckets.get(keys[-1]) or 0)) if keys else 0.0
        return amt / total
    if isinstance(buckets, list):
        if total <= 0:
            total = sum(float(number_(b.get("amount") or b.get("total") or 0)) for b in buckets)
        if total <= 0 or not buckets:
            return 0.0
        oldest = buckets[-1]
        amt = float(number_(oldest.get("amount") or oldest.get("total") or 0))
        return amt / total
    return 0.0


def _escalate(current, target):
    if _ACTION_RANK[target] > _ACTION_RANK[current]:
        return target
    return current


def _demote(action):
    # Follow-up is advisory — premium clears it to create.
    # reduce_volume stays when size rules fired; one-step demote otherwise.
    if action == "follow_up":
        return "create_order"
    if action == "push_back":
        return "follow_up"
    if action == "strong_push_back":
        return "push_back"
    if action == "reduce_volume":
        return "create_order"
    return action


def _reason(code, message, **extra):
    row = {"code": code, "message": message, "group": REASON_GROUP.get(code, "behavior")}
    row.update(extra)
    return row


def evaluate_order_check(detail, *, order_value=None, order_qty=None, policy=None, flags=None):
    """Pure evaluation against a customer 360 detail + proposed order."""
    detail = detail or {}
    policy = dict(policy or DEFAULT_POLICY)
    flags = flags or {
        "premium": bool(detail.get("premium")),
        "blacklisted": bool(detail.get("blacklisted")),
    }
    premium = bool(flags.get("premium"))
    blacklisted = bool(flags.get("blacklisted"))

    limit_factor = float(policy.get("premium_limit_factor") or 1.0) if premium else 1.0
    due = float(number_(detail.get("due") or 0))
    due_days = int(number_(detail.get("due_days") if detail.get("due_days") is not None else 30))
    due_days_source = clean_text(detail.get("due_days_source") or "default") or "default"

    open_meta = _oldest_open_meta(detail)
    oldest = int(open_meta.get("oldest_open_age") or 0)
    oldest_kind = clean_text(open_meta.get("oldest_open_kind") or "")
    oldest_what = clean_text(open_meta.get("oldest_open_what") or "")
    avg_sale = _avg_sale_amount(detail, int(policy.get("avg_sales_window") or 5))
    usual_qty = _usual_qty(detail)
    avg_gap = _avg_gap_days(detail)
    days_since = _days_since_last_sale(detail)
    flagged_ratio = _flagged_ratio(detail)
    settle_old = _settlement_old_share(detail)

    proposed_value = None if order_value in ("", None) else float(_clamp_nonneg(order_value, 0))
    proposed_qty = None if order_qty in ("", None) else float(_clamp_nonneg(order_qty, 0))

    # Defaults for suggested inputs when caller omitted them
    if proposed_value is None and avg_sale > 0:
        proposed_value = round(avg_sale, 2)
    if proposed_qty is None and usual_qty > 0:
        proposed_qty = round(usual_qty, 2)

    action = "create_order"
    reasons = []
    suggested_value = proposed_value
    suggested_qty = proposed_qty

    def signals_now():
        return _signals(
            due, due_days, due_days_source, oldest, oldest_kind, oldest_what,
            avg_sale, usual_qty, avg_gap,
            days_since, flagged_ratio, settle_old, proposed_value, proposed_qty,
        )

    if blacklisted:
        action = "strong_push_back"
        reasons.append(_reason("blacklisted", "Customer is blacklisted — do not create an order."))
        return _result(
            action, reasons, suggested_value, suggested_qty, policy, flags,
            signals=signals_now(),
        )

    followup_age = int(policy.get("followup_age_days") or 15)
    urgent_age = int(policy.get("urgent_age_days") or 30)
    grace = int(policy.get("overdue_grace_days") or 0)
    age_label = "opening balance" if oldest_kind == "opening" else "open invoice"

    if due > 0 and oldest >= urgent_age:
        action = _escalate(action, "strong_push_back")
        reasons.append(_reason(
            "urgent_age",
            "Oldest %s is %sd (urgent at %sd). Due days %s from %s." % (
                age_label, oldest, urgent_age, due_days, due_days_source,
            ),
            oldest_age=oldest, threshold=urgent_age, due_days=due_days, due_days_source=due_days_source,
            oldest_kind=oldest_kind,
        ))
    elif due > 0 and oldest > due_days + grace:
        action = _escalate(action, "push_back")
        reasons.append(_reason(
            "past_due_days",
            "Oldest %s is %sd vs due days %s from %s (+%s grace)." % (
                age_label, oldest, due_days, due_days_source, grace,
            ),
            oldest_age=oldest, due_days=due_days, due_days_source=due_days_source, grace=grace,
            oldest_kind=oldest_kind,
        ))
    elif due > 0 and oldest >= followup_age:
        action = _escalate(action, "follow_up")
        reasons.append(_reason(
            "followup_age",
            "Oldest %s is %sd (follow up at %sd). Due days %s from %s." % (
                age_label, oldest, followup_age, due_days, due_days_source,
            ),
            oldest_age=oldest, threshold=followup_age, due_days=due_days, due_days_source=due_days_source,
            oldest_kind=oldest_kind,
        ))

    credit_limit = policy.get("credit_limit")
    if credit_limit not in (None, "") and float(number_(credit_limit) or 0) > 0:
        effective_limit = float(credit_limit) * limit_factor
        exposure = max(0.0, due) + float(proposed_value or 0)
        if exposure > effective_limit:
            room = max(0.0, effective_limit - max(0.0, due))
            action = _escalate(action, "strong_push_back" if room <= 0 else "reduce_volume")
            reasons.append(_reason(
                "credit_limit",
                "Open + proposed %s exceeds credit limit %s." % (
                    round(exposure, 2), round(effective_limit, 2),
                ),
                exposure=round(exposure, 2), limit=round(effective_limit, 2),
            ))
            if room > 0 and (suggested_value is None or suggested_value > room):
                suggested_value = round(room, 2)

    max_abs = policy.get("max_order_value")
    if max_abs not in (None, "") and float(number_(max_abs) or 0) > 0 and proposed_value is not None:
        cap = float(max_abs) * limit_factor
        if proposed_value > cap:
            action = _escalate(action, "reduce_volume")
            reasons.append(_reason(
                "max_order_value",
                "Proposed value %s exceeds max order value %s." % (round(proposed_value, 2), round(cap, 2)),
                proposed=proposed_value, cap=round(cap, 2),
            ))
            suggested_value = round(cap, 2)

    vs_avg = float(policy.get("max_order_value_vs_avg") or 0)
    if vs_avg > 0 and avg_sale > 0 and proposed_value is not None:
        cap = avg_sale * vs_avg * limit_factor
        if proposed_value > cap:
            action = _escalate(action, "reduce_volume")
            reasons.append(_reason(
                "order_vs_avg",
                "Proposed value %s is above %.0f%% of average sale %s." % (
                    round(proposed_value, 2), vs_avg * 100, round(avg_sale, 2),
                ),
                proposed=proposed_value, avg_sale=round(avg_sale, 2), cap=round(cap, 2),
            ))
            if suggested_value is None or suggested_value > cap:
                suggested_value = round(cap, 2)

    vs_qty = float(policy.get("max_order_qty_vs_usual") or 0)
    if vs_qty > 0 and usual_qty > 0 and proposed_qty is not None:
        cap = usual_qty * vs_qty * limit_factor
        if proposed_qty > cap:
            action = _escalate(action, "reduce_volume")
            reasons.append(_reason(
                "order_vs_usual_qty",
                "Proposed qty %s is above %.0f%% of usual basket %s." % (
                    round(proposed_qty, 2), vs_qty * 100, round(usual_qty, 2),
                ),
                proposed=proposed_qty, usual_qty=round(usual_qty, 2), cap=round(cap, 2),
            ))
            reduce_factor = float(policy.get("reduce_vs_usual") or 1.0)
            sug = usual_qty * reduce_factor * limit_factor
            if suggested_qty is None or suggested_qty > sug:
                suggested_qty = round(sug, 2)

    gap_factor = float(policy.get("min_gap_factor") or 0)
    if gap_factor > 0 and avg_gap > 0 and days_since is not None:
        min_gap = avg_gap * gap_factor
        # Premium can reorder sooner
        if premium:
            min_gap = min_gap / max(limit_factor, 1.0)
        if days_since < min_gap:
            action = _escalate(action, "follow_up")
            reasons.append(_reason(
                "ordering_frequency",
                "Last sale was %sd ago; usual gap is ~%sd (min %.0f%%)." % (
                    days_since, avg_gap, gap_factor * 100,
                ),
                days_since=days_since, avg_gap=avg_gap, min_gap=round(min_gap, 1),
            ))

    flagged_push = float(policy.get("flagged_ratio_push") or 0)
    if flagged_push > 0 and flagged_ratio >= flagged_push:
        action = _escalate(action, "push_back")
        reasons.append(_reason(
            "ordering_pattern",
            "%.0f%% of sales value was ordered while overdue (threshold %.0f%%)." % (
                flagged_ratio * 100, flagged_push * 100,
            ),
            flagged_ratio=round(flagged_ratio, 3),
        ))
    elif detail.get("ordered_overdue"):
        action = _escalate(action, "follow_up")
        reasons.append(_reason(
            "ordered_overdue_recent",
            "Customer has recent orders placed while overdue.",
        ))

    settle_push = float(policy.get("settlement_old_share_push") or 0)
    if settle_push > 0 and settle_old >= settle_push:
        action = _escalate(action, "follow_up")
        reasons.append(_reason(
            "settlement_pattern",
            "%.0f%% of settlements fall in the oldest aging band (threshold %.0f%%)." % (
                settle_old * 100, settle_push * 100,
            ),
            settlement_old_share=round(settle_old, 3),
        ))

    if premium and policy.get("premium_demote") and action != "create_order":
        before = action
        # Never demote below follow_up when still overdue past urgent — but demote one step otherwise
        if action != "strong_push_back" or oldest < urgent_age:
            action = _demote(action)
            if action != before:
                reasons.append(_reason(
                    "premium_demote",
                    "Premium customer: severity eased from %s to %s." % (
                        ACTION_LABELS.get(before, before),
                        ACTION_LABELS.get(action, action),
                    ),
                ))

    if action == "create_order" and not reasons:
        reasons.append(_reason("ok", "No policy flags — safe to create the order."))

    if action == "reduce_volume":
        if suggested_value is None and proposed_value is not None:
            suggested_value = proposed_value
        if suggested_qty is None and usual_qty > 0:
            suggested_qty = round(usual_qty * float(policy.get("reduce_vs_usual") or 1.0), 2)

    return _result(
        action, reasons, suggested_value, suggested_qty, policy, flags,
        signals=signals_now(),
    )


def _signals(due, due_days, due_days_source, oldest, oldest_kind, oldest_what, avg_sale, usual_qty, avg_gap, days_since, flagged_ratio, settle_old, proposed_value, proposed_qty):
    return {
        "due": round(float(due or 0), 2),
        "due_days": due_days,
        "due_days_source": due_days_source or "default",
        "oldest_open_age": oldest,
        "oldest_open_kind": oldest_kind or "",
        "oldest_open_what": oldest_what or "",
        "avg_sale": round(float(avg_sale or 0), 2),
        "usual_qty": round(float(usual_qty or 0), 2),
        "avg_gap_days": avg_gap,
        "days_since_last_sale": days_since,
        "flagged_ratio": round(float(flagged_ratio or 0), 4),
        "settlement_old_share": round(float(settle_old or 0), 4),
        "proposed_value": None if proposed_value is None else round(float(proposed_value), 2),
        "proposed_qty": None if proposed_qty is None else round(float(proposed_qty), 2),
    }


def _result(action, reasons, suggested_value, suggested_qty, policy, flags, signals):
    grouped = {}
    for r in reasons or []:
        g = r.get("group") or "behavior"
        grouped.setdefault(g, []).append(r)
    return {
        "action": action,
        "action_label": ACTION_LABELS.get(action, action),
        "create": action == "create_order",
        "reasons": reasons,
        "reason_groups": [
            {"id": gid, "label": REASON_GROUP_LABELS.get(gid, gid), "reasons": items}
            for gid, items in grouped.items()
        ],
        "suggested_value": None if suggested_value is None else round(float(suggested_value), 2),
        "suggested_qty": None if suggested_qty is None else round(float(suggested_qty), 2),
        "policy": policy,
        "premium": bool(flags.get("premium")),
        "blacklisted": bool(flags.get("blacklisted")),
        "signals": signals,
    }


def run_customer_order_check(store, uk, *, order_value=None, order_qty=None, detail=None):
    """Load customer (if needed), resolve policy/flags, evaluate."""
    from server.customers import account_uk, get_customer

    uk = account_uk(uk)
    detail = detail or get_customer(store, uk)
    if not detail:
        return None

    doc = store.find_row("customer", uk) or {}
    flags = read_customer_flags((doc or {}).get("fields") or {})
    # Prefer flags already on detail if present
    if "premium" in detail:
        flags["premium"] = bool(detail.get("premium"))
    if "blacklisted" in detail:
        flags["blacklisted"] = bool(detail.get("blacklisted"))

    resolved = resolve_policy(
        store,
        customer_uk=uk,
        group=detail.get("group") or "",
        rep=detail.get("salesperson") or "",
    )
    result = evaluate_order_check(
        detail,
        order_value=order_value,
        order_qty=order_qty,
        policy=resolved["policy"],
        flags=flags,
    )
    result["policy_source"] = resolved["source"]
    result["policy_own"] = resolved.get("own")
    result["uk"] = uk
    result["name"] = detail.get("name") or ""
    return result


def policy_meta_for_customer(store, detail):
    """Attach resolved policy + flags for customer detail payloads."""
    from server.customers import account_uk

    uk = account_uk(detail.get("uk") or "")
    doc = store.find_row("customer", uk) or {}
    flags = read_customer_flags((doc or {}).get("fields") or {})
    resolved = resolve_policy(
        store,
        customer_uk=uk,
        group=detail.get("group") or "",
        rep=detail.get("salesperson") or "",
    )
    own_override = get_override(store, "customer", uk)
    return {
        "premium": flags["premium"],
        "blacklisted": flags["blacklisted"],
        "order_check_policy": resolved["policy"],
        "order_check_source": resolved["source"],
        "order_check_own": resolved.get("own"),
        "order_check_override": own_override,
    }


def policy_meta_for_entity(store, entity, detail):
    """Attach resolved order-check policy for group/rep detail payloads."""
    entity = clean_text(entity).lower()
    if entity == "customer":
        return policy_meta_for_customer(store, detail)
    name = clean_text(detail.get("name") or detail.get("uk") or "")
    resolved = resolve_entity_policy(store, entity, name)
    own_override = get_override(store, entity, name)
    return {
        "order_check_policy": resolved["policy"],
        "order_check_source": resolved["source"],
        "order_check_own": resolved.get("own"),
        "order_check_override": own_override,
    }


def run_entity_order_check(store, entity, uk, *, order_value=None, order_qty=None, detail=None):
    """Evaluate order check for a group or rep rollup detail."""
    from server.customers import account_uk
    from server.groups360 import get_group
    from server.reps360 import get_rep

    entity = clean_text(entity).lower()
    uk = account_uk(uk)
    if entity == "customer":
        return run_customer_order_check(
            store, uk, order_value=order_value, order_qty=order_qty, detail=detail
        )
    if detail is None:
        if entity == "group":
            detail = get_group(store, uk)
        elif entity == "rep":
            detail = get_rep(store, uk)
        else:
            return None
    if not detail:
        return None
    name = clean_text(detail.get("name") or uk)
    resolved = resolve_entity_policy(store, entity, name)
    result = evaluate_order_check(
        detail,
        order_value=order_value,
        order_qty=order_qty,
        policy=resolved["policy"],
        flags={"premium": False, "blacklisted": False},
    )
    result["policy_source"] = resolved["source"]
    result["policy_own"] = resolved.get("own")
    result["uk"] = uk
    result["name"] = detail.get("name") or ""
    result["entity"] = entity
    return result

