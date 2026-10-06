"""Saved source → destination account names, and a one-time row rewrite."""

from __future__ import annotations

import json

from vay.dates import clean_text, number_

from server.keys import RowFail, build_uk
from server.org_policy import SETTING_TYPE, _parse_json
from server.settings import EVENT_TYPES

ALIAS_UK = "account_aliases"

_EVENT_TYPES = ("sales", "receipt", "items", "payments")
_NAME_KEYS = {
    "sales": ("Party Name", "Account Name"),
    "items": ("Party Name", "Account Name"),
    "receipt": ("Account Name", "Party Name"),
    "payments": ("Account Name", "Party Name"),
    "arr": ("Account Name", "Party Name"),
    "party": ("Account Name", "Party Name"),
    "customer": ("Account Name", "Party Name"),
}
_FILL_KEYS = ("Group", "Party Type", "Premium", "Blacklisted")


def _load_pairs(store):
    from server.org_policy import _fields

    raw = _parse_json(_fields(store, ALIAS_UK).get("Aliases"), [])
    if not isinstance(raw, list):
        return []
    pairs = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        source = clean_text(item.get("source"))
        destination = clean_text(item.get("destination"))
        if source and destination:
            pairs.append({"source": source, "destination": destination})
    return pairs


def get_aliases(store):
    return {"aliases": _load_pairs(store)}


def alias_lookup(store):
    """Lowercase source name → destination display name."""
    return {pair["source"].lower(): pair["destination"] for pair in _load_pairs(store)}


def apply_alias_fields(fields, lookup):
    if not lookup:
        return fields
    fields = dict(fields or {})
    for key in ("Party Name", "Account Name"):
        name = clean_text(fields.get(key))
        if name and name.lower() in lookup:
            fields[key] = lookup[name.lower()]
    return fields


def _validate_pair(pairs, source, destination):
    src = clean_text(source)
    dst = clean_text(destination)
    if not src or not dst:
        raise ValueError("Source and destination names are required")
    if src.lower() == dst.lower():
        raise ValueError("Source and destination must be different accounts")
    sources = {pair["source"].lower() for pair in pairs}
    destinations = {pair["destination"].lower() for pair in pairs}
    current = next((pair for pair in pairs if pair["source"].lower() == src.lower()), None)
    if current and current["destination"].lower() != dst.lower():
        raise ValueError("This source name is already mapped to another account")
    if src.lower() in destinations:
        raise ValueError("That name is already a destination, so it cannot also be a source")
    if dst.lower() in sources and dst.lower() != src.lower():
        raise ValueError("That name is already a source, so it cannot also be a destination")
    return src, dst


def _account_exists(store, name):
    return bool(_find_named(store, "customer", name) or _find_named(store, "party", name))


def _save_pairs(store, pairs):
    store.upsert_row({
        "type": SETTING_TYPE,
        "uk": ALIAS_UK,
        "source_upload_id": "",
        "fields": {"Aliases": json.dumps(pairs)},
    })
    return {"aliases": pairs}


def remove_alias(store, source):
    src = clean_text(source).lower()
    if not src:
        raise ValueError("Source name is required")
    pairs = [pair for pair in _load_pairs(store) if pair["source"].lower() != src]
    return _save_pairs(store, pairs)


def _find_named(store, type_name, name):
    from server.customers import account_uk

    want = account_uk(name).lower()
    direct = store.find_row(type_name, account_uk(name))
    if direct:
        return direct
    for row in store.rows_of_type(type_name):
        fields = row.get("fields") or {}
        got = account_uk(fields.get("Account Name") or fields.get("Party Name")).lower()
        if got == want or str(row.get("uk") or "").lower() == want:
            return row
    return None


def _rename_fields(fields, source_key, dest_name, keys):
    fields = dict(fields or {})
    for key in keys:
        if clean_text(fields.get(key)).lower() == source_key:
            fields[key] = dest_name
    return fields


def _row_doc(row, fields, uk):
    doc = {
        "type": row.get("type"),
        "uk": uk,
        "source_upload_id": row.get("source_upload_id") or "",
        "fields": fields,
    }
    if fields.get("Date") not in ("", None):
        doc["Date"] = fields.get("Date")
    if row.get("effective_date"):
        doc["effective_date"] = row.get("effective_date")
    return doc


def _move_row(store, row, fields, new_uk):
    old_uk = row.get("uk")
    if new_uk != old_uk and store.find_row(row.get("type"), new_uk):
        store.delete_row(row.get("type"), old_uk)
        return "dropped"
    if new_uk != old_uk:
        store.delete_row(row.get("type"), old_uk)
    store.upsert_row(_row_doc(row, fields, new_uk))
    return "moved"


def _rewrite_events(store, source_key, dest_name):
    from server.preview import effective_mapper

    moved = 0
    dropped = 0
    for type_name in _EVENT_TYPES:
        if type_name not in EVENT_TYPES and type_name not in _EVENT_TYPES:
            continue
        keys = _NAME_KEYS[type_name]
        mapper = effective_mapper(store, type_name)
        unique_key = mapper.get("unique_key") or []
        extra = mapper.get("extra_types") or {}
        for row in store.rows_of_type(type_name):
            fields = row.get("fields") or {}
            if not any(clean_text(fields.get(key)).lower() == source_key for key in keys):
                continue
            fields = _rename_fields(fields, source_key, dest_name, keys)
            try:
                new_uk = build_uk(fields, unique_key, extra) if unique_key else row.get("uk")
            except RowFail:
                new_uk = row.get("uk")
            result = _move_row(store, row, fields, new_uk)
            if result == "dropped":
                dropped += 1
            else:
                moved += 1
    return moved, dropped


def _fill_blank(dest_fields, source_fields):
    from vay.row_defaults import real_group

    dest_fields = dict(dest_fields or {})
    source_fields = source_fields or {}
    for key in _FILL_KEYS:
        dest_val = dest_fields.get(key)
        src_val = source_fields.get(key)
        dest_blank = not real_group(dest_val) if key == "Group" else not clean_text(dest_val)
        src_ok = bool(real_group(src_val)) if key == "Group" else bool(clean_text(src_val))
        if dest_blank and src_ok:
            dest_fields[key] = source_fields.get(key)
    return dest_fields


def _merge_snapshot(store, type_name, source_key, dest_name, sum_balance=False):
    from server.customers import account_uk

    source = _find_named(store, type_name, source_key)
    if not source:
        return
    dest = _find_named(store, type_name, dest_name)
    keys = _NAME_KEYS[type_name]
    if dest and (dest.get("uk") or "") != (source.get("uk") or ""):
        fields = _fill_blank(dest.get("fields"), source.get("fields"))
        fields = _rename_fields(fields, source_key, dest_name, keys)
        if sum_balance:
            fields["Balance"] = round(
                number_(fields.get("Balance")) + number_((source.get("fields") or {}).get("Balance")),
                2,
            )
        fields["Account Name"] = dest_name
        store.upsert_row(_row_doc(dest, fields, dest.get("uk") or account_uk(dest_name)))
        store.delete_row(type_name, source.get("uk"))
        return
    fields = _rename_fields(source.get("fields"), source_key, dest_name, keys)
    fields["Account Name"] = dest_name
    new_uk = account_uk(dest_name)
    _move_row(store, source, fields, new_uk)


def _rewrite_notes(store, source_key, dest_name):
    from server.customers import NOTE_TYPE, account_uk

    dest_uk = account_uk(dest_name)
    for row in store.rows_of_type(NOTE_TYPE):
        fields = dict(row.get("fields") or {})
        party = clean_text(fields.get("Account Name")).lower()
        cust = clean_text(fields.get("customer_uk")).lower()
        if party != source_key and cust != source_key:
            continue
        if party == source_key:
            fields["Account Name"] = dest_name
        if cust == source_key or party == source_key:
            fields["customer_uk"] = dest_uk
        store.upsert_row(_row_doc(row, fields, row.get("uk")))


def _rewrite_override(store, type_name, source_key, dest_name):
    from server.customers import account_uk

    dest_uk = "customer:%s" % account_uk(dest_name).lower()
    for row in store.rows_of_type(type_name):
        fields = dict(row.get("fields") or {})
        entity = clean_text(fields.get("Entity")).lower()
        name = clean_text(fields.get("Name") or fields.get("Account Name")).lower()
        uk = str(row.get("uk") or "")
        if entity and entity != "customer":
            continue
        if name != source_key and uk.lower() != "customer:%s" % source_key:
            continue
        if store.find_row(type_name, dest_uk) and uk != dest_uk:
            store.delete_row(type_name, uk)
            continue
        if name == source_key or not name:
            fields["Name"] = dest_name
        if clean_text(fields.get("Account Name")).lower() == source_key:
            fields["Account Name"] = dest_name
        if not fields.get("Entity"):
            fields["Entity"] = "customer"
        _move_row(store, row, fields, dest_uk)


def migrate_account(store, source, destination):
    pairs = _load_pairs(store)
    src, dst = _validate_pair(pairs, source, destination)
    if not _account_exists(store, src):
        raise ValueError("Old account was not found")
    if not _account_exists(store, dst):
        raise ValueError("New account was not found. Choose an existing account.")
    source_key = src.lower()
    moved, dropped = _rewrite_events(store, source_key, dst)
    _merge_snapshot(store, "arr", source_key, dst, sum_balance=True)
    _merge_snapshot(store, "party", source_key, dst)
    _merge_snapshot(store, "customer", source_key, dst)
    _rewrite_notes(store, source_key, dst)
    _rewrite_override(store, "order_check", source_key, dst)
    _rewrite_override(store, "due_days", source_key, dst)
    if not any(pair["source"].lower() == source_key for pair in pairs):
        pairs.append({"source": src, "destination": dst})
    saved = _save_pairs(store, pairs)
    saved.update({
        "source": src,
        "destination": dst,
        "rows_moved": moved,
        "rows_dropped": dropped,
    })
    return saved
