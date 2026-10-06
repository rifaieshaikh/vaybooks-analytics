"""Canonical customer and product ids, plus a near-match review queue.

Account aliases still rewrite names before this runs. A normalized exact match
auto-links. Near-matches are queued and still import under their own id until
someone merges or rejects them.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re

from vay.dates import clean_text

from server.org_policy import SETTING_TYPE, _fields, _parse_json

ENTITIES_UK = "entities"
REVIEW_UK = "entity_review"
NEAR_RATIO = 0.92

CUSTOMER_NAME_KEYS = ("Party Name", "Account Name")
PRODUCT_NAME_KEYS = ("Item Name",)


def normalize_name(name):
    text = clean_text(name).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _token_key(normalized):
    return " ".join(sorted(part for part in normalized.split() if part))


def _entity_id(kind, normalized):
    prefix = "cus_" if kind == "customer" else "prd_"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return prefix + digest


def _load_entities(store):
    raw = _parse_json(_fields(store, ENTITIES_UK).get("Entities"), [])
    return list(raw) if isinstance(raw, list) else []


def _load_queue(store):
    raw = _parse_json(_fields(store, REVIEW_UK).get("Queue"), [])
    return list(raw) if isinstance(raw, list) else []


def _save_entities(store, entities):
    store.upsert_row({
        "type": SETTING_TYPE,
        "uk": ENTITIES_UK,
        "source_upload_id": "",
        "fields": {"Entities": json.dumps(entities)},
    })


def _save_queue(store, queue):
    store.upsert_row({
        "type": SETTING_TYPE,
        "uk": REVIEW_UK,
        "source_upload_id": "",
        "fields": {"Queue": json.dumps(queue)},
    })


def _name_from(fields, keys):
    for key in keys:
        name = clean_text((fields or {}).get(key))
        if name:
            return name
    return ""


def _near_score(left_norm, right_norm):
    if not left_norm or not right_norm or left_norm == right_norm:
        return None
    if _token_key(left_norm) == _token_key(right_norm):
        return 0.99
    ratio = difflib.SequenceMatcher(None, left_norm, right_norm).ratio()
    if ratio >= NEAR_RATIO:
        return round(ratio, 4)
    return None


def _pair_state(queue, kind, left_norm, right_id):
    for item in queue:
        if item.get("kind") != kind:
            continue
        if item.get("left_norm") != left_norm:
            continue
        if item.get("right_entity_id") != right_id:
            continue
        return item.get("state") or ""
    return ""


def _follow_id(entities, entity_id):
    seen = set()
    current = entity_id
    while current and current not in seen:
        seen.add(current)
        ent = next((row for row in entities if row.get("id") == current), None)
        if not ent:
            return current
        if ent.get("status") == "merged" and ent.get("merged_into"):
            current = ent.get("merged_into")
            continue
        return ent.get("id")
    return entity_id


def _ensure_entity(entities, kind, display_name, normalized):
    for ent in entities:
        if ent.get("kind") == kind and ent.get("normalized_name") == normalized and ent.get("status") != "merged":
            return ent, False
    ent = {
        "id": _entity_id(kind, normalized),
        "kind": kind,
        "display_name": display_name,
        "normalized_name": normalized,
        "status": "active",
    }
    entities.append(ent)
    return ent, True


def resolve_name(kind, display_name, entities, queue):
    """Return (entity_id, entities_changed, queue_changed)."""
    display_name = clean_text(display_name)
    normalized = normalize_name(display_name)
    if not normalized:
        return "", False, False
    for ent in entities:
        if ent.get("kind") != kind or ent.get("normalized_name") != normalized:
            continue
        return _follow_id(entities, ent.get("id")), False, False

    best = None
    best_score = None
    for ent in entities:
        if ent.get("kind") != kind or ent.get("status") == "merged":
            continue
        score = _near_score(normalized, ent.get("normalized_name") or "")
        if score is None:
            continue
        if _pair_state(queue, kind, normalized, ent.get("id")) == "rejected":
            continue
        if best_score is None or score > best_score:
            best = ent
            best_score = score

    ent, created = _ensure_entity(entities, kind, display_name, normalized)
    queued = False
    if best is not None and best.get("id") != ent.get("id"):
        if _pair_state(queue, kind, normalized, best.get("id")) != "open":
            queue.append({
                "kind": kind,
                "left_name": display_name,
                "left_norm": normalized,
                "left_entity_id": ent.get("id"),
                "right_entity_id": best.get("id"),
                "right_name": best.get("display_name") or "",
                "score": best_score,
                "state": "open",
            })
            queued = True
    return ent.get("id") or "", created, queued


def stamp_prepared_entities(store, type_name, prepared):
    """Stamp customer_id / product_id onto prepared rows and persist new queue items."""
    wants_customer = type_name in (
        "sales", "receipt", "credit_note", "arr", "party", "customer", "payments", "items",
    )
    wants_product = type_name in ("items", "stock")
    if not wants_customer and not wants_product:
        return prepared
    entities = _load_entities(store)
    queue = _load_queue(store)
    entities_changed = False
    queue_changed = False
    out = []
    for fields, uk in prepared:
        fields = dict(fields or {})
        if wants_customer:
            name = _name_from(fields, CUSTOMER_NAME_KEYS)
            if name:
                eid, e_changed, q_changed = resolve_name("customer", name, entities, queue)
                if eid:
                    fields["customer_id"] = eid
                entities_changed = entities_changed or e_changed
                queue_changed = queue_changed or q_changed
        if wants_product:
            name = _name_from(fields, PRODUCT_NAME_KEYS)
            if name:
                eid, e_changed, q_changed = resolve_name("product", name, entities, queue)
                if eid:
                    fields["product_id"] = eid
                entities_changed = entities_changed or e_changed
                queue_changed = queue_changed or q_changed
        out.append((fields, uk))
    if entities_changed:
        _save_entities(store, entities)
    if queue_changed:
        _save_queue(store, queue)
    return out


def list_open_reviews(store):
    entities = _load_entities(store)
    by_id = {ent.get("id"): ent for ent in entities}
    items = []
    for item in _load_queue(store):
        if item.get("state") != "open":
            continue
        right = by_id.get(item.get("right_entity_id")) or {}
        items.append({
            "kind": item.get("kind") or "customer",
            "left_name": item.get("left_name") or "",
            "left_entity_id": item.get("left_entity_id") or "",
            "right_entity_id": item.get("right_entity_id") or "",
            "right_name": item.get("right_name") or right.get("display_name") or "",
            "score": item.get("score"),
            "state": "open",
        })
    items.sort(key=lambda row: -(float(row.get("score") or 0)))
    return {"items": items}


def _find_open(queue, kind, left_name, right_entity_id):
    left_norm = normalize_name(left_name)
    for item in queue:
        if item.get("state") != "open":
            continue
        if (item.get("kind") or "customer") != kind:
            continue
        if item.get("right_entity_id") != right_entity_id:
            continue
        if item.get("left_norm") == left_norm or clean_text(item.get("left_name")).lower() == clean_text(left_name).lower():
            return item
    return None


def _rewrite_ids(store, field, old_id, new_id):
    if not old_id or not new_id or old_id == new_id:
        return
    from server.settings import SOURCE_TYPES

    for type_name in SOURCE_TYPES:
        for row in list(store.rows_of_type(type_name)):
            fields = dict(row.get("fields") or {})
            if fields.get(field) != old_id:
                continue
            fields[field] = new_id
            doc = {
                "type": row.get("type") or type_name,
                "uk": row.get("uk"),
                "source_upload_id": row.get("source_upload_id") or "",
                "fields": fields,
            }
            if fields.get("Date") not in ("", None):
                doc["Date"] = fields.get("Date")
            if row.get("effective_date"):
                doc["effective_date"] = row.get("effective_date")
            store.upsert_row(doc)


def _rewrite_products(store, source_name, dest_name, dest_id):
    from server.account_aliases import _move_row
    from server.keys import RowFail, build_uk
    from server.preview import effective_mapper

    source_key = clean_text(source_name).lower()
    for type_name in ("items", "stock"):
        mapper = effective_mapper(store, type_name)
        unique_key = mapper.get("unique_key") or []
        extra = mapper.get("extra_types") or {}
        for row in list(store.rows_of_type(type_name)):
            fields = dict(row.get("fields") or {})
            if clean_text(fields.get("Item Name")).lower() != source_key:
                continue
            fields["Item Name"] = dest_name
            if dest_id:
                fields["product_id"] = dest_id
            try:
                new_uk = build_uk(fields, unique_key, extra) if unique_key else row.get("uk")
            except RowFail:
                new_uk = row.get("uk")
            _move_row(store, row, fields, new_uk)


def _mark_merged(entities, left_id, right_id):
    for ent in entities:
        if ent.get("id") == left_id:
            ent["status"] = "merged"
            ent["merged_into"] = right_id


def merge_review(store, kind, left_name, right_entity_id):
    kind = kind if kind in ("customer", "product") else "customer"
    queue = _load_queue(store)
    item = _find_open(queue, kind, left_name, right_entity_id)
    if not item:
        raise ValueError("That name pair is not waiting for review")
    entities = _load_entities(store)
    right = next((ent for ent in entities if ent.get("id") == right_entity_id), None)
    if not right:
        raise ValueError("The existing name was not found")
    dest_name = right.get("display_name") or ""
    left_id = item.get("left_entity_id") or ""
    if kind == "customer":
        from server.account_aliases import migrate_account

        migrate_account(store, item.get("left_name") or left_name, dest_name)
        _rewrite_ids(store, "customer_id", left_id, right_entity_id)
    else:
        _rewrite_products(store, item.get("left_name") or left_name, dest_name, right_entity_id)
        _rewrite_ids(store, "product_id", left_id, right_entity_id)
    entities = _load_entities(store)
    _mark_merged(entities, left_id, right_entity_id)
    for other in queue:
        if other.get("state") == "open" and other.get("right_entity_id") == left_id:
            other["right_entity_id"] = right_entity_id
            other["right_name"] = dest_name
    item["state"] = "merged"
    _save_entities(store, entities)
    _save_queue(store, queue)
    return list_open_reviews(store)


def reject_review(store, kind, left_name, right_entity_id):
    kind = kind if kind in ("customer", "product") else "customer"
    queue = _load_queue(store)
    item = _find_open(queue, kind, left_name, right_entity_id)
    if not item:
        raise ValueError("That name pair is not waiting for review")
    item["state"] = "rejected"
    _save_queue(store, queue)
    return list_open_reviews(store)
