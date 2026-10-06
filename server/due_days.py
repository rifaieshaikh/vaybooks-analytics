"""Configurable credit / due days for Ordering (ordered while overdue)."""

from __future__ import annotations

from vay.dates import clean_text, number_

DEFAULT_DUE_DAYS = 30
SETTING_TYPE = "app_setting"
SETTING_UK = "due_days"
OVERRIDE_TYPE = "due_days"
ENTITIES = ("customer", "group", "rep")


def _invalidate_book(store):
    if hasattr(store, "_360_book"):
        store._360_book = None


def _clamp_days(raw, fallback=DEFAULT_DUE_DAYS):
    try:
        days = int(number_(raw))
    except (TypeError, ValueError):
        return int(fallback)
    if days < 0:
        return int(fallback)
    return days


def override_uk(entity, name):
    entity = clean_text(entity).lower()
    if entity not in ENTITIES:
        raise ValueError("Entity must be customer, group, or rep")
    uk = clean_text(name)
    if not uk:
        raise ValueError("Name required")
    return "%s:%s" % (entity, uk.lower())


def get_default_due_days(store):
    row = store.find_row(SETTING_TYPE, SETTING_UK) or {}
    fields = row.get("fields") or {}
    raw = fields.get("Due Days")
    if raw in ("", None):
        return DEFAULT_DUE_DAYS
    return _clamp_days(raw, DEFAULT_DUE_DAYS)


def save_default_due_days(store, days):
    days = _clamp_days(days, DEFAULT_DUE_DAYS)
    store.upsert_row({
        "type": SETTING_TYPE,
        "uk": SETTING_UK,
        "source_upload_id": "",
        "fields": {"Due Days": days},
    })
    _invalidate_book(store)
    return {"due_days": days}


def get_due_days_settings(store):
    return {"due_days": get_default_due_days(store)}


def _override_map(store):
    out = {}
    for row in store.rows_of_type(OVERRIDE_TYPE):
        fields = row.get("fields") or {}
        entity = clean_text(fields.get("Entity")).lower()
        name = clean_text(fields.get("Name") or fields.get("Account Name"))
        if entity not in ENTITIES or not name:
            # Fall back to uk prefix customer:foo
            uk = clean_text(row.get("uk"))
            if ":" in uk:
                entity, name = uk.split(":", 1)
                entity = entity.lower()
                name = clean_text(name)
            else:
                continue
        if entity not in ENTITIES or not name:
            continue
        raw = fields.get("Due Days")
        if raw in ("", None):
            continue
        out[(entity, name.lower())] = _clamp_days(raw)
    return out


def get_override(store, entity, name, overrides=None):
    entity = clean_text(entity).lower()
    name_l = clean_text(name).lower()
    if not name_l or entity not in ENTITIES:
        return None
    overrides = overrides if overrides is not None else _override_map(store)
    if (entity, name_l) in overrides:
        return overrides[(entity, name_l)]
    return None


def save_due_days_override(store, entity, name, days=None):
    """Set override; pass days=None to clear."""
    entity = clean_text(entity).lower()
    name = clean_text(name)
    uk = override_uk(entity, name)
    if days is None:
        store.delete_row(OVERRIDE_TYPE, uk)
        _invalidate_book(store)
        return {"due_days": None, "cleared": True, "entity": entity, "name": name}
    days = _clamp_days(days)
    store.upsert_row({
        "type": OVERRIDE_TYPE,
        "uk": uk,
        "source_upload_id": "",
        "fields": {
            "Entity": entity,
            "Name": name,
            "Due Days": days,
        },
    })
    _invalidate_book(store)
    return {"due_days": days, "cleared": False, "entity": entity, "name": name}


def resolve_due_days(store, *, customer_uk="", group="", rep="", overrides=None, default=None):
    """customer → group → sales rep → global default."""
    overrides = overrides if overrides is not None else _override_map(store)
    default = DEFAULT_DUE_DAYS if default is None else _clamp_days(default)
    cust = get_override(store, "customer", customer_uk, overrides)
    if cust is not None:
        return {"due_days": cust, "source": "customer", "own": True}
    grp = get_override(store, "group", group, overrides)
    if grp is not None:
        return {"due_days": grp, "source": "group", "own": False}
    salesperson = get_override(store, "rep", rep, overrides)
    if salesperson is not None:
        return {"due_days": salesperson, "source": "rep", "own": False}
    return {"due_days": default if default is not None else get_default_due_days(store), "source": "default", "own": False}


def resolve_entity_due_days(store, entity, name, *, group="", rep="", customer_uk=""):
    """Effective days when viewing a customer/group/rep profile."""
    entity = clean_text(entity).lower()
    name = clean_text(name)
    overrides = _override_map(store)
    default = get_default_due_days(store)
    if entity == "customer":
        return resolve_due_days(
            store,
            customer_uk=name or customer_uk,
            group=group,
            rep=rep,
            overrides=overrides,
            default=default,
        )
    if entity == "group":
        own = get_override(store, "group", name, overrides)
        if own is not None:
            return {"due_days": own, "source": "group", "own": True}
        return {"due_days": default, "source": "default", "own": False}
    if entity == "rep":
        own = get_override(store, "rep", name, overrides)
        if own is not None:
            return {"due_days": own, "source": "rep", "own": True}
        return {"due_days": default, "source": "default", "own": False}
    return {"due_days": default, "source": "default", "own": False}
