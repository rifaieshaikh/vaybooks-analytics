"""Dry-run file preview and mapper defaults. Does not write rows."""

from __future__ import annotations

from vay.dates import clean_text

from server.files import frame_values
from server.mappers import apply_column_map, is_skip_dest
from server.serialize import json_cell
from server.settings import (
    DEFAULT_UNIQUE_KEYS,
    REQUIRED_FIELDS,
    SOURCE_TYPES,
    TYPE_LABELS,
)

UPLOAD_TYPES = tuple(t for t in SOURCE_TYPES if t != "customer")

# Common workbook tab names → import type (after clean/lower).
SHEET_TYPE_ALIASES = {
    "sales": "sales",
    "sale": "sales",
    "bills": "sales",
    "bill register": "sales",
    "invoice": "sales",
    "invoices": "sales",
    "receipt": "receipt",
    "receipts": "receipt",
    "credit note": "credit_note",
    "credit notes": "credit_note",
    "creditnote": "credit_note",
    "sales return": "credit_note",
    "sales returns": "credit_note",
    "collection": "receipt",
    "collections": "receipt",
    "arr": "arr",
    "outstanding": "arr",
    "outstandings": "arr",
    "receivable": "arr",
    "receivables": "arr",
    "items": "items",
    "item": "items",
    "item wise": "items",
    "itemwise": "items",
    "item-wise": "items",
    "item wise sales": "items",
    "itemwise sales": "items",
    "item-wise sales": "items",
    "stock": "stock",
    "inventory": "stock",
    "payments": "payments",
    "payment": "payments",
    "party": "party",
    "parties": "party",
}

HEADER_ALIASES = {
    "bill date": "Date",
    "invoice date": "Date",
    "voucher date": "Date",
    "date": "Date",
    "party": "Party Name",
    "party name": "Party Name",
    "customer": "Party Name",
    "customer name": "Party Name",
    "account": "Account Name",
    "account name": "Account Name",
    "sales person": "Sales Rep",
    "salesperson": "Sales Rep",
    "sales rep": "Sales Rep",
    "rep": "Sales Rep",
    "net amount": "Net Amount",
    "net amt": "Net Amount",
    "invoice": "Invoice No",
    "invoice no": "Invoice No",
    "invoice number": "Invoice No",
    "bill no": "Invoice No",
    "bill number": "Invoice No",
    "voucher": "Invoice No",
    "voucher no": "Invoice No",
    "voucher number": "Invoice No",
    "vch no": "Invoice No",
    "vch no.": "Invoice No",
    "inv no": "Invoice No",
    "inv no.": "Invoice No",
    "inv. no": "Invoice No",
    "inv. no.": "Invoice No",
    "reference": "Invoice No",
    "ref no": "Invoice No",
    "ref. no": "Invoice No",
    "item": "Item Name",
    "item name": "Item Name",
    "sku": "Item Name",
    "qty": "Qty",
    "quantity": "Qty",
    "rate": "Rate",
    "price": "P.Price",
    "p.price": "P.Price",
    "p price": "P.Price",
    "group": "Group",
    "balance": "Balance",
    "days": "Days",
    "amount": "Amount",
    "taxable amount": "Taxable Amount",
    "taxable": "Taxable Amount",
    "taxable value": "Taxable Amount",
    "assessable value": "Taxable Amount",
    "amount before tax": "Taxable Amount",
    "before tax": "Taxable Amount",
    "tax amount": "Tax Amount",
    "tax": "Tax Amount",
    "gst amount": "Tax Amount",
    "gst": "Tax Amount",
    "sl no": "SlNo",
    "slno": "SlNo",
    "s no": "SlNo",
    "sales amount": "Sales Amount",
    "sgst": "SGST",
    "cgst": "CGST",
    "igst": "IGST",
}


def effective_mapper(store, type_name, override=None):
    doc = dict(store.get_mapper(type_name) or {})
    override = override or {}
    if override.get("column_map") is not None:
        doc["column_map"] = dict(override.get("column_map") or {})
    if override.get("unique_key") is not None:
        doc["unique_key"] = list(override.get("unique_key") or [])
    if override.get("extra_types") is not None:
        doc["extra_types"] = dict(override.get("extra_types") or {})
    doc.setdefault("column_map", {})
    doc.setdefault("extra_types", {})
    if not doc.get("unique_key"):
        doc["unique_key"] = list(DEFAULT_UNIQUE_KEYS.get(type_name) or [])
    return doc


def guess_type(sheet_name, headers, forced=None):
    if forced in UPLOAD_TYPES:
        return forced
    key = clean_text(sheet_name).lower()
    compact = " ".join(key.replace(".", " ").replace("_", " ").replace("-", " ").split())
    aliased = SHEET_TYPE_ALIASES.get(key) or SHEET_TYPE_ALIASES.get(compact)
    if aliased in UPLOAD_TYPES:
        return aliased
    if key in UPLOAD_TYPES:
        return key
    if key == "data":
        return None
    heads = {clean_text(h).lower() for h in (headers or [])}
    if "item name" in heads and "qty" in heads and "p.price" in heads:
        return "stock"
    if "item name" in heads and "qty" in heads:
        return "items"
    if "balance" in heads and "account name" in heads:
        return "arr"
    if "net amount" in heads and "sales amount" in heads and "sales rep" not in heads and (
        "sgst" in heads or "cgst" in heads or "igst" in heads
    ):
        return "credit_note"
    if "net amount" in heads:
        return "sales"
    if "amount" in heads and "account name" in heads and "sales rep" in heads:
        return "receipt"
    if "amount" in heads and "account name" in heads:
        return "payments"
    if "p.price" in heads:
        return "stock"
    return None


def is_sheet_plan(entry):
    """True when maps value is a per-sheet plan (type/skip), not a legacy type-keyed mapper."""
    return isinstance(entry, dict) and ("type" in entry or "skip" in entry or "include" in entry)


def mapper_override(entry):
    """Strip plan keys; keep only mapper fields for effective_mapper."""
    if not isinstance(entry, dict):
        return None
    out = {}
    if "column_map" in entry:
        out["column_map"] = dict(entry.get("column_map") or {})
    if "unique_key" in entry:
        out["unique_key"] = list(entry.get("unique_key") or [])
    if "extra_types" in entry:
        out["extra_types"] = dict(entry.get("extra_types") or {})
    return out or None


def override_for_sheet(overrides, sheet_name, type_name=None):
    """Prefer per-sheet plan; fall back to legacy type-keyed mapper override."""
    overrides = overrides or {}
    sheet_ov = overrides.get(sheet_name)
    if isinstance(sheet_ov, dict) and (is_sheet_plan(sheet_ov) or "column_map" in sheet_ov or "unique_key" in sheet_ov):
        return sheet_ov
    if type_name and isinstance(overrides.get(type_name), dict):
        return overrides.get(type_name)
    return sheet_ov if isinstance(sheet_ov, dict) else {}


def _alias_dest(header, type_name):
    raw = clean_text(header)
    key = raw.lower()
    compact = " ".join(key.replace(".", " ").replace("_", " ").split())
    required = REQUIRED_FIELDS.get(type_name) or []
    if raw in required:
        return raw
    dest = HEADER_ALIASES.get(key) or HEADER_ALIASES.get(compact)
    if type_name == "credit_note" and compact == "cash":
        return "__skip__"
    if dest == "Amount" and type_name == "sales":
        return "Net Amount"
    if dest == "Party Name" and type_name in ("receipt", "payments", "arr", "party"):
        return "Account Name"
    if dest == "Account Name" and type_name in ("sales", "credit_note"):
        return "Party Name"
    if dest:
        return dest
    if type_name in ("items", "stock"):
        from server.settings import ITEM_ATTR_FIELDS
        for name in ITEM_ATTR_FIELDS:
            if compact == name.lower() or key == name.lower():
                return name
        if compact in ("vendor", "supplier name"):
            return "Supplier"
        if compact in ("item group", "itemgroup"):
            return "Item Group"
    return raw


def header_drift(saved_map, headers):
    """Saved source headers that the new file added, removed, or renamed."""
    saved_keys = []
    for key in (saved_map or {}):
        text = str(key or "").strip()
        if text and text not in saved_keys:
            saved_keys.append(text)
    if not saved_keys:
        return {"added": [], "removed": [], "changed": False}
    have = []
    for header in headers or []:
        text = str(header or "").strip()
        if text and text not in have:
            have.append(text)
    have_set = set(have)
    saved_set = set(saved_keys)
    removed = [key for key in saved_keys if key not in have_set]
    added = [header for header in have if header not in saved_set]
    return {"added": added, "removed": removed, "changed": bool(removed or added)}


def suggest_column_map(headers, type_name, saved_map=None):
    saved_map = dict(saved_map or {})
    out = {}
    used_dest = set()
    for src, dest in saved_map.items():
        if src not in headers:
            continue
        if is_skip_dest(dest):
            out[src] = "__skip__"
            continue
        if dest:
            out[src] = dest
            used_dest.add(dest)
    for header in headers:
        if header in out:
            continue
        dest = _alias_dest(header, type_name)
        if dest in used_dest and dest != header:
            dest = header
        out[header] = dest
        used_dest.add(dest)
    return out


def mapped_headers(column_map, headers):
    dests = []
    for h in headers:
        if h in (column_map or {}):
            dest = column_map.get(h)
            if is_skip_dest(dest):
                continue
            dests.append(dest or h)
        else:
            dests.append(h)
    return dests


def missing_required(type_name, column_map, headers):
    dests = set(mapped_headers(column_map, headers))
    return [name for name in (REQUIRED_FIELDS.get(type_name) or []) if name not in dests]


def sample_rows(headers, values, column_map, limit=20):
    rows = []
    for raw in (values or [])[:limit]:
        raw_dict = {}
        for i, h in enumerate(headers):
            raw_dict[h] = json_cell(raw[i] if i < len(raw) else "")
        mapped = apply_column_map(raw_dict, column_map)
        rows.append({k: json_cell(v) for k, v in mapped.items()})
    return rows


def preview_frames(store, frames, forced_type=None, overrides=None):
    overrides = overrides or {}
    sheets = []
    names = list(frames.keys())
    for sheet_name in names:
        frame = frames.get(sheet_name)
        headers, values = frame_values(frame)
        plan = override_for_sheet(overrides, sheet_name)
        skip = bool(plan.get("skip")) if is_sheet_plan(plan) else False
        if is_sheet_plan(plan) and plan.get("include") is False:
            skip = True
        forced_sheet = None
        if is_sheet_plan(plan):
            t = clean_text(plan.get("type") or "").lower()
            if t in UPLOAD_TYPES:
                forced_sheet = t
        guessed = forced_sheet or guess_type(
            sheet_name, headers, forced_type if len(names) == 1 or forced_type else None
        )
        if not guessed and forced_type in UPLOAD_TYPES and (sheet_name == "data" or len(names) == 1):
            guessed = forced_type
        type_name = guessed
        if skip:
            type_name = forced_sheet or type_name
        override = mapper_override(plan) if plan else None
        if override is None and type_name and not is_sheet_plan(plan):
            override = mapper_override(overrides.get(type_name)) if type_name else None
        mapper = effective_mapper(store, type_name, override) if type_name else {"column_map": {}, "unique_key": []}
        stored = store.get_mapper(type_name) if type_name else None
        column_map = suggest_column_map(headers, type_name, mapper.get("column_map")) if type_name else {h: h for h in headers}
        unique_key = list((override or {}).get("unique_key") or mapper.get("unique_key") or [])
        drift = header_drift((stored or {}).get("column_map") or {}, headers) if type_name else {
            "added": [], "removed": [], "changed": False,
        }
        event_mode = str((stored or {}).get("event_mode") or "skip")
        if isinstance(plan, dict) and str(plan.get("event_mode") or "").strip():
            event_mode = str(plan.get("event_mode")).strip().lower()
        if skip:
            missing = []
            ready = False
        elif type_name:
            missing = missing_required(type_name, column_map, headers)
            ready = not missing and bool(unique_key)
        else:
            missing = ["Map this sheet to an import type, or skip it"]
            ready = False
        if drift["changed"] and not (isinstance(plan, dict) and plan.get("mapping_confirmed")):
            ready = False
        from server.settings import ITEM_ATTR_FIELDS
        extra_dests = list(ITEM_ATTR_FIELDS) if type_name in ("items", "stock") else []
        dest_fields = list(dict.fromkeys(
            (REQUIRED_FIELDS.get(type_name) or [])
            + extra_dests
            + list(column_map.values())
            + ["Invoice No", "Taxable Amount", "Tax Amount"]
        )) if type_name else list(headers)
        sheets.append({
            "sheet": sheet_name,
            "type": type_name,
            "skip": skip,
            "label": TYPE_LABELS.get(type_name) or sheet_name,
            "headers": headers,
            "row_count": len(values),
            "column_map": column_map,
            "unique_key": unique_key,
            "fields": dest_fields,
            "missing": missing,
            "ready": ready,
            "event_mode": event_mode if type_name else "skip",
            "header_changes": drift,
            "sample": sample_rows(headers, values, column_map) if type_name and not skip else sample_rows(headers, values, {h: h for h in headers}),
        })
    return {"sheets": sheets}
