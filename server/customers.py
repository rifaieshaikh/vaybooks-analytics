"""Customer 360 helpers. Does not feed generate()."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from io import BytesIO

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from vay.dates import (
    DEFAULT_FY_START_MONTH,
    clean_text,
    fiscal_year_start,
    fy_label,
    iter_fiscal_years,
    normalize_fy_start_month,
    number_,
    parse_date,
    today_ist,
)
from vay.settlement import (
    BUCKET_KEYS,
    DEFAULT_SETTLEMENT_MODE,
    allocate_collections,
    allocate_open as settlement_allocate_open,
    bucket_key as settlement_bucket_key,
    default_aging_bands,
    empty_buckets,
    flatten_collection,
    flatten_owe,
    normalize_aging_bands,
    normalize_mode,
    oldest_due_invoice,
)


def account_uk(name):
    return clean_text(name)


def parse_report_date(text):
    if hasattr(text, "year"):
        return datetime(text.year, text.month, text.day, 12)
    parts = str(text or "").split("-")
    if len(parts) >= 3:
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            return datetime(y, m, d, 12)
        except (TypeError, ValueError):
            pass
    parsed = parse_date(text)
    if parsed:
        return datetime(parsed.year, parsed.month, parsed.day, 12)
    return today_ist()


NOTE_TYPE = "customer_note"
KIND_TYPE = "activity_kind"
KIND_SEEDED_UK = "__seeded__"
SETTLEMENT_TYPE = "app_setting"
SETTLEMENT_UK = "settlement"
DEFAULT_NOTE_KINDS = {
    "visit": "Sales rep visit",
    "sales_followup": "Sales follow-up",
    "collection_followup": "Collection follow-up",
}
ACTIVITY_LABELS = {
    "sale": "Sale",
    "collection": "Collection",
    "credit_note": "Credit note",
}
_NOTE_KIND_ALIASES = {
    "visit": "visit",
    "sales_rep_visit": "visit",
    "salesrepvisit": "visit",
    "sales_followup": "sales_followup",
    "sales_follow_up": "sales_followup",
    "salesfollowup": "sales_followup",
    "collection_followup": "collection_followup",
    "collection_follow_up": "collection_followup",
    "collectionfollowup": "collection_followup",
}


def _kind_slug(raw):
    s = clean_text(raw).lower().replace("-", "_")
    compact = []
    for ch in s:
        if ch.isalnum() or ch == "_":
            compact.append(ch)
        elif ch in " .":
            compact.append("_")
    out = "".join(compact)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")[:48]


def _note_kind(raw, kinds=None):
    kinds = kinds or DEFAULT_NOTE_KINDS
    compact = _kind_slug(raw)
    if compact in kinds:
        return compact
    if compact in _NOTE_KIND_ALIASES and _NOTE_KIND_ALIASES[compact] in kinds:
        return _NOTE_KIND_ALIASES[compact]
    nospace = compact.replace("_", "")
    if nospace in _NOTE_KIND_ALIASES and _NOTE_KIND_ALIASES[nospace] in kinds:
        return _NOTE_KIND_ALIASES[nospace]
    lowered = clean_text(raw).lower()
    for key, label in kinds.items():
        if label.lower() == lowered:
            return key
    return compact if compact in kinds else ""


def _kind_maps(store):
    kinds = {}
    for item in list_activity_kinds(store):
        kinds[item["id"]] = item["label"]
    return kinds


def _ensure_activity_kinds(store):
    if store.find_row(KIND_TYPE, KIND_SEEDED_UK):
        return
    for i, (uk, label) in enumerate(DEFAULT_NOTE_KINDS.items()):
        store.upsert_row({
            "type": KIND_TYPE,
            "uk": uk,
            "source_upload_id": "",
            "fields": {"Label": label, "Sort": i, "Builtin": "Yes"},
        })
    store.upsert_row({
        "type": KIND_TYPE,
        "uk": KIND_SEEDED_UK,
        "source_upload_id": "",
        "fields": {"Label": "", "Sort": -1},
    })


def list_activity_kinds(store):
    _ensure_activity_kinds(store)
    rows = []
    for row in store.rows_of_type(KIND_TYPE):
        uk = row.get("uk") or ""
        if uk == KIND_SEEDED_UK:
            continue
        fields = row.get("fields") or {}
        label = clean_text(fields.get("Label")) or uk
        rows.append({
            "id": uk,
            "label": label,
            "builtin": uk in DEFAULT_NOTE_KINDS or clean_text(fields.get("Builtin")).lower() == "yes",
            "sort": number_(fields.get("Sort")),
        })
    rows.sort(key=lambda r: (r["sort"], r["label"].lower()))
    return [{"id": r["id"], "label": r["label"], "builtin": r["builtin"]} for r in rows]


ASSIGNEE_TYPE = "activity_assignee"


def list_activity_assignees(store):
    rows = []
    for row in store.rows_of_type(ASSIGNEE_TYPE):
        uk = row.get("uk") or ""
        if not uk:
            continue
        fields = row.get("fields") or {}
        label = clean_text(fields.get("Label") or fields.get("Name")) or uk
        rows.append({
            "id": uk,
            "label": label,
            "sort": number_(fields.get("Sort")),
        })
    rows.sort(key=lambda r: (r["sort"], r["label"].lower()))
    return [{"id": r["id"], "label": r["label"]} for r in rows]


def _settlement_fields(store):
    row = store.find_row(SETTLEMENT_TYPE, SETTLEMENT_UK)
    return (row.get("fields") or {}) if row else {}


def get_settlement_mode(store):
    fields = _settlement_fields(store)
    return normalize_mode(fields.get("Mode") or fields.get("settlement_mode"))


def get_aging_bands(store):
    fields = _settlement_fields(store)
    raw = fields.get("AgingBands") or fields.get("aging_bands")
    if not raw:
        return default_aging_bands()
    try:
        return normalize_aging_bands(raw)
    except ValueError:
        return default_aging_bands()


def get_settlement_setup_complete(store):
    fields = _settlement_fields(store)
    flag = clean_text(fields.get("SetupComplete") or fields.get("setup_complete")).lower()
    return flag in ("yes", "true", "1")


def get_settlement_settings(store):
    return {
        "mode": get_settlement_mode(store),
        "aging_bands": get_aging_bands(store),
        "setup_complete": get_settlement_setup_complete(store),
    }


def save_settlement_settings(store, mode=None, aging_bands=None, setup_complete=True):
    existing = _settlement_fields(store)
    mode = normalize_mode(mode if mode is not None else (
        existing.get("Mode") or existing.get("settlement_mode") or DEFAULT_SETTLEMENT_MODE
    ))
    if aging_bands is None:
        raw = existing.get("AgingBands") or existing.get("aging_bands")
        bands = normalize_aging_bands(raw) if raw else default_aging_bands()
    else:
        bands = normalize_aging_bands(aging_bands)
    import json
    complete = bool(setup_complete)
    fields = {
        "Mode": mode,
        "AgingBands": json.dumps(bands),
        "SetupComplete": "Yes" if complete else "No",
    }
    store.upsert_row({
        "type": SETTLEMENT_TYPE,
        "uk": SETTLEMENT_UK,
        "source_upload_id": "",
        "fields": fields,
    })
    if hasattr(store, "_360_book"):
        store._360_book = None
    return {
        "mode": mode,
        "aging_bands": bands,
        "setup_complete": complete,
    }


PARTY_TYPE_TYPE = "party_type"
PARTY_TYPE_SEEDED_UK = "__party_type_seeded__"
CUSTOMER_PARTY_TYPE = "customer"
DEFAULT_PARTY_TYPES = {
    CUSTOMER_PARTY_TYPE: "Customer",
}
RESERVED_PARTY_TYPE_IDS = {PARTY_TYPE_SEEDED_UK}


def _ensure_party_types(store):
    if store.find_row(PARTY_TYPE_TYPE, PARTY_TYPE_SEEDED_UK):
        return
    for i, (uk, label) in enumerate(DEFAULT_PARTY_TYPES.items()):
        store.upsert_row({
            "type": PARTY_TYPE_TYPE,
            "uk": uk,
            "source_upload_id": "",
            "fields": {"Label": label, "Sort": i, "Builtin": "Yes"},
        })
    store.upsert_row({
        "type": PARTY_TYPE_TYPE,
        "uk": PARTY_TYPE_SEEDED_UK,
        "source_upload_id": "",
        "fields": {"Label": "", "Sort": -1},
    })


def list_party_types(store):
    _ensure_party_types(store)
    rows = []
    for row in store.rows_of_type(PARTY_TYPE_TYPE):
        uk = row.get("uk") or ""
        if uk == PARTY_TYPE_SEEDED_UK:
            continue
        fields = row.get("fields") or {}
        label = clean_text(fields.get("Label")) or uk
        rows.append({
            "id": uk,
            "label": label,
            "builtin": uk in DEFAULT_PARTY_TYPES or clean_text(fields.get("Builtin")).lower() == "yes",
            "sort": number_(fields.get("Sort")),
        })
    rows.sort(key=lambda r: (r["sort"], r["label"].lower()))
    return [{"id": r["id"], "label": r["label"], "builtin": r["builtin"]} for r in rows]


def _party_type_maps(store):
    return {item["id"]: item["label"] for item in list_party_types(store)}


def _party_type_id(raw, types):
    compact = _kind_slug(raw)
    if compact in types:
        return compact
    lowered = clean_text(raw).lower()
    for key, label in types.items():
        if label.lower() == lowered:
            return key
    return ""


def resolve_party_type(store, raw, allow_empty=True):
    name = clean_text(raw)
    if not name:
        if allow_empty:
            return ""
        raise ValueError("Party type is required")
    types = _party_type_maps(store)
    found = _party_type_id(name, types)
    if found:
        return found
    raise ValueError("Unknown party type")


def party_type_label(store, type_id):
    type_id = clean_text(type_id)
    if not type_id:
        return ""
    return _party_type_maps(store).get(type_id) or type_id


def add_party_type(store, label):
    label = clean_text(label)
    if not label:
        raise ValueError("Name is required")
    _ensure_party_types(store)
    types = _party_type_maps(store)
    if _party_type_id(label, types):
        raise ValueError("That type already exists")
    uk = _kind_slug(label)
    if not uk or uk in RESERVED_PARTY_TYPE_IDS:
        raise ValueError("That name is not valid")
    if store.find_row(PARTY_TYPE_TYPE, uk):
        raise ValueError("That type already exists")
    store.insert_row({
        "type": PARTY_TYPE_TYPE,
        "uk": uk,
        "source_upload_id": "",
        "fields": {
            "Label": label[:80],
            "Sort": 100 + len(types),
            "Builtin": "No",
        },
    })
    return list_party_types(store)


def delete_party_type(store, uk):
    uk = _kind_slug(uk)
    if not uk or uk in RESERVED_PARTY_TYPE_IDS:
        raise ValueError("That type cannot be removed")
    row = store.find_row(PARTY_TYPE_TYPE, uk)
    if not row:
        return None
    if uk in DEFAULT_PARTY_TYPES or clean_text((row.get("fields") or {}).get("Builtin")).lower() == "yes":
        raise ValueError("Built-in types stay")
    store.delete_row(PARTY_TYPE_TYPE, uk)
    return list_party_types(store)


def _set_party_type_if_empty(fields, type_id=CUSTOMER_PARTY_TYPE):
    if not clean_text((fields or {}).get("Party Type")):
        fields["Party Type"] = type_id
    return fields


def preserve_party_fields(store, uk, fields):
    incoming = dict(fields or {})
    existing = store.find_row("party", uk)
    prev = dict((existing or {}).get("fields") or {})
    mapped = clean_text(incoming.get("Party Type"))
    if mapped:
        try:
            incoming["Party Type"] = resolve_party_type(store, mapped, allow_empty=False)
        except ValueError:
            if prev.get("Party Type"):
                incoming["Party Type"] = prev.get("Party Type")
            else:
                incoming.pop("Party Type", None)
    elif prev.get("Party Type"):
        incoming["Party Type"] = prev.get("Party Type")
    if not incoming.get("customer_uk") and prev.get("customer_uk"):
        incoming["customer_uk"] = prev.get("customer_uk")
    return incoming


def ensure_party(store, name, upload_id, group="", party_type=""):
    """Create party if missing. Never change an existing balance or type."""
    name = clean_text(name)
    if not name:
        return 0
    uk = account_uk(name)
    group = clean_text(group)
    existing = store.find_row("party", uk)
    if existing:
        pfields = dict(existing.get("fields") or {})
        if group and not clean_text(pfields.get("Group")):
            pfields["Group"] = group
            store.upsert_row({
                "type": "party",
                "uk": uk,
                "source_upload_id": existing.get("source_upload_id") or str(upload_id),
                "fields": pfields,
            })
        return 0
    fields = {
        "Account Name": name,
        "Group": group,
        "Balance": 0.0,
    }
    if party_type:
        fields["Party Type"] = party_type
    store.upsert_row({
        "type": "party",
        "uk": uk,
        "source_upload_id": str(upload_id),
        "fields": fields,
    })
    return 1


def patch_party_type(store, uk, party_type):
    uk = account_uk(uk)
    row = store.find_row("party", uk)
    if not row:
        return None
    resolved = resolve_party_type(store, party_type, allow_empty=True)
    fields = dict(row.get("fields") or {})
    fields["Party Type"] = resolved
    store.upsert_row({
        "type": "party",
        "uk": uk,
        "source_upload_id": row.get("source_upload_id") or "",
        "fields": fields,
    })
    name = clean_text(fields.get("Account Name"))
    if resolved == CUSTOMER_PARTY_TYPE and name:
        ensure_customer_and_party(store, name, row.get("source_upload_id") or "", clean_text(fields.get("Group")))
    return {
        "uk": uk,
        "party": name,
        "party_type": resolved,
        "party_type_label": party_type_label(store, resolved),
        "fields": fields,
    }


def sync_from_payments(store, prepared, upload_id):
    created_p = 0
    seen = set()
    for fields, _uk in prepared:
        name = _party_name(fields, "payments") or clean_text(fields.get("Account Name") or fields.get("Party Name"))
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        created_p += ensure_party(store, name, upload_id, clean_text(fields.get("Group")))
    return {"parties_created": created_p}


def _note_matches(fields, name_l):
    party = _party_name(fields).lower()
    cust = account_uk(fields.get("customer_uk") or "").lower()
    return party == name_l or cust == name_l or cust == account_uk(name_l).lower()


_PARTY_HEADERS = {
    "party name",
    "party",
    "account name",
    "customer",
    "customer name",
    "buyer",
    "buyer name",
}


def _header_key(name):
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum() or ch.isspace()).strip()


def _party_from_fields(fields):
    for src, val in (fields or {}).items():
        if val in ("", None):
            continue
        if _header_key(src) in _PARTY_HEADERS:
            return clean_text(val)
    return clean_text((fields or {}).get("Party Name") or (fields or {}).get("Account Name"))


def _party_name(fields, type_name=None):
    if type_name in ("sales", "items", "credit_note"):
        return _party_from_fields(fields) or clean_text(fields.get("Party Name") or fields.get("Account Name"))
    return clean_text(fields.get("Account Name") or fields.get("Party Name")) or _party_from_fields(fields)


def _matches(fields, type_name, name_l):
    return _party_name(fields, type_name).lower() == name_l


def sync_from_arr(store, prepared, upload_id):
    created_c = 0
    created_p = 0
    updated = 0
    for fields, _arr_uk in prepared:
        name = clean_text(fields.get("Account Name"))
        if not name:
            continue
        uk = account_uk(name)
        group = clean_text(fields.get("Group"))
        balance = number_(fields.get("Balance"))
        days = fields.get("Days")
        existing_c = store.find_row("customer", uk)
        if not existing_c:
            created_c += 1
        else:
            updated += 1
        cfields = dict((existing_c or {}).get("fields") or {})
        cfields["Account Name"] = name
        cfields["Group"] = group
        cfields["Balance"] = balance
        cfields["party_uk"] = uk
        if days not in ("", None):
            cfields["Days"] = number_(days)
        store.upsert_row({
            "type": "customer",
            "uk": uk,
            "source_upload_id": str(upload_id),
            "fields": cfields,
        })
        existing_p = store.find_row("party", uk)
        if not existing_p:
            created_p += 1
        pfields = dict((existing_p or {}).get("fields") or {})
        pfields["Account Name"] = name
        pfields["Group"] = group
        pfields["Balance"] = balance
        if not pfields.get("customer_uk"):
            pfields["customer_uk"] = uk
        _set_party_type_if_empty(pfields)
        store.upsert_row({
            "type": "party",
            "uk": uk,
            "source_upload_id": str(upload_id),
            "fields": pfields,
        })
    return {
        "customers_created": created_c,
        "parties_created": created_p,
        "balances_updated": updated,
    }


def ensure_customer_and_party(store, name, upload_id, group=""):
    """Create customer and party if missing. Never change an existing balance."""
    name = clean_text(name)
    if not name:
        return 0, 0
    uk = account_uk(name)
    group = clean_text(group)
    created_c = 0
    created_p = 0
    existing_c = store.find_row("customer", uk)
    if not existing_c:
        created_c = 1
        store.upsert_row({
            "type": "customer",
            "uk": uk,
            "source_upload_id": str(upload_id),
            "fields": {
                "Account Name": name,
                "Group": group,
                "Balance": 0.0,
                "party_uk": uk,
            },
        })
    elif group and not clean_text((existing_c.get("fields") or {}).get("Group")):
        fields = dict(existing_c.get("fields") or {})
        fields["Group"] = group
        store.upsert_row({
            "type": "customer",
            "uk": uk,
            "source_upload_id": existing_c.get("source_upload_id") or str(upload_id),
            "fields": fields,
        })
    existing_p = store.find_row("party", uk)
    if not existing_p:
        created_p = 1
        store.upsert_row({
            "type": "party",
            "uk": uk,
            "source_upload_id": str(upload_id),
            "fields": {
                "Account Name": name,
                "Group": group,
                "Balance": 0.0,
                "customer_uk": uk,
                "Party Type": CUSTOMER_PARTY_TYPE,
            },
        })
    else:
        pfields = dict(existing_p.get("fields") or {})
        changed = False
        if not pfields.get("customer_uk"):
            pfields["customer_uk"] = uk
            changed = True
        if not clean_text(pfields.get("Party Type")):
            pfields["Party Type"] = CUSTOMER_PARTY_TYPE
            changed = True
        if changed:
            store.upsert_row({
                "type": "party",
                "uk": uk,
                "source_upload_id": existing_p.get("source_upload_id") or str(upload_id),
                "fields": pfields,
            })
    return created_c, created_p


def sync_from_sales(store, prepared, upload_id):
    created_c = 0
    created_p = 0
    seen = set()
    for fields, _uk in prepared:
        name = _party_name(fields, "sales") or clean_text(fields.get("Account Name") or fields.get("Party Name"))
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        c, p = ensure_customer_and_party(store, name, upload_id, clean_text(fields.get("Group")))
        created_c += c
        created_p += p
    return {
        "customers_created": created_c,
        "parties_created": created_p,
    }


def _as_of(store):
    force = getattr(store, "_force_as_of", None)
    if force is not None:
        return force
    for run in store.list_runs() or []:
        if run.get("status") == "succeeded" and run.get("report_date"):
            try:
                return parse_report_date(run.get("report_date"))
            except Exception:
                parsed = parse_date(run.get("report_date"))
                if parsed:
                    return parsed
    return today_ist()


def _fmt_day(d):
    if not d:
        return ""
    return d.strftime("%d %b %Y")


def _iso(d):
    if not d:
        return ""
    return d.strftime("%Y-%m-%d")


def _rows_for_name(store, type_name, name_l, book=None):
    if book is None:
        book = getattr(store, "_360_book", None)
    if book:
        if type_name == "sales":
            return book["sales_by_party"].get(name_l, [])
        if type_name == "receipt":
            return book["receipts_by_party"].get(name_l, [])
        if type_name == "items":
            return [
                {"fields": {"Date": line.get("date"), "Item Name": line.get("name"), "Qty": line.get("qty"), "Rate": line.get("rate")}}
                for line in book["buying_lines_by_party"].get(name_l, [])
            ]
        if type_name == "credit_note":
            return (book.get("credit_notes_by_party") or {}).get(name_l, [])
    out = []
    for row in store.rows_of_type(type_name):
        fields = row.get("fields") or {}
        if _matches(fields, type_name, name_l):
            out.append(row)
    return out


def _fields(row):
    return (row or {}).get("fields") or {}


def _salespeople(store, extra=(), book=None):
    names = set()
    book = book or getattr(store, "_360_book", None)
    if book:
        for key, rows in (book.get("sales_by_rep") or {}).items():
            if rows:
                names.add(clean_text((rows[0].get("fields") or {}).get("Sales Rep")) or key)
        for key, rows in (book.get("receipts_by_rep") or {}).items():
            if rows:
                names.add(clean_text((rows[0].get("fields") or {}).get("Sales Rep")) or key)
    else:
        for type_name in ("sales", "receipt"):
            for row in store.rows_of_type(type_name):
                name = clean_text((row.get("fields") or {}).get("Sales Rep"))
                if name:
                    names.add(name)
    for name in extra or ():
        name = clean_text(name)
        if name:
            names.add(name)
    return sorted(names, key=str.lower)


def _fy_month(store=None, book=None, start_month=None):
    """Org fiscal-year start. Book copy wins so a loaded 360 index stays consistent."""
    if start_month is not None:
        return normalize_fy_start_month(start_month)
    if book is None and store is not None:
        book = getattr(store, "_360_book", None)
    if isinstance(book, dict) and book.get("fiscal_year_start_month") not in (None, ""):
        return normalize_fy_start_month(book.get("fiscal_year_start_month"))
    if store is not None:
        from server.org_policy import get_org_policy
        return get_org_policy(store)["fiscal_year_start_month"]
    return DEFAULT_FY_START_MONTH


def _opening_dt(dates, as_of, start_month=None):
    sm = normalize_fy_start_month(start_month)
    if not dates:
        return fiscal_year_start(as_of, sm)
    return min(fiscal_year_start(d, sm) for d in dates)


def _opening_from_invoices(invoices, as_of, start_month=None):
    return _opening_dt(
        [inv["date"] for inv in invoices or [] if inv.get("date")],
        as_of,
        start_month,
    )


def _invoice_id(fields, uk, start_month=None):
    from server.invoices import _invoice_no, invoice_id_for_sale
    return _invoice_no(fields), invoice_id_for_sale(fields, uk, start_month=start_month)


def _group_sales_invoices(rows, start_month=None):
    from server.invoices import invoice_scope_key

    grouped = {}
    order = []
    for row in rows or []:
        fields = _fields(row)
        d = parse_date(fields.get("Date"))
        if not d:
            continue
        inv, iid = _invoice_id(fields, row.get("uk"), start_month=start_month)
        if inv:
            key = invoice_scope_key(inv, d, start_month)
        else:
            key = str(row.get("uk") or "")
        if not key:
            key = "%s|%s|%s" % (
                _iso(d),
                clean_text(fields.get("Sales Rep")).lower(),
                "{:.4f}".format(number_(fields.get("Net Amount"))),
            )
        if key not in grouped:
            grouped[key] = {
                "date": d,
                "invoice": inv,
                "invoice_id": iid,
                "amount": 0.0,
                "rep": clean_text(fields.get("Sales Rep")),
            }
            order.append(key)
        grouped[key]["amount"] += number_(fields.get("Net Amount"))
        if d < grouped[key]["date"]:
            grouped[key]["date"] = d
        if not grouped[key]["invoice_id"] and iid:
            grouped[key]["invoice_id"] = iid
    lines = [grouped[k] for k in order]
    lines.sort(key=lambda x: x["date"])
    return lines


def _age_days(as_of, d):
    from vay.settlement import age_days
    return age_days(as_of, d)


def _bucket_key(days, bands=None):
    return settlement_bucket_key(days, bands)


def due_status(days, due):
    if due < 0:
        return "credit"
    if due <= 0:
        return "ontrack"
    if days >= 30:
        return "urgent"
    if days >= 15:
        return "followup"
    return "ontrack"


def _status_from_open(due, open_lines):
    if due < 0:
        return "credit"
    if due <= 0:
        return "ontrack"
    # Same rule as Due / order check: oldest open *invoice*, not ARR opening.
    oldest = oldest_due_invoice(open_lines).get("age_days") or 0
    return due_status(oldest, due)


def _allocate_open(invoices, due, as_of, opening_dt=None, mode=None, receipts=None, bands=None, credits=None):
    return settlement_allocate_open(
        invoices,
        due,
        as_of,
        opening_dt=opening_dt,
        mode=mode or DEFAULT_SETTLEMENT_MODE,
        fmt_day=_fmt_day,
        iso=_iso,
        receipts=receipts,
        bands=bands,
        credits=credits,
    )


def _receipts_for_party(store, name_l, book=None):
    out = []
    for row in _rows_for_name(store, "receipt", name_l, book=book):
        fields = _fields(row)
        d = parse_date(fields.get("Date"))
        if not d:
            continue
        amount = number_(fields.get("Amount"))
        if amount <= 0:
            continue
        out.append({
            "date": d,
            "amount": amount,
            "invoice": clean_text(
                fields.get("Invoice No")
                or fields.get("Invoice")
                or fields.get("Invoice Number")
                or ""
            ),
        })
    return out


def ar_mismatch_for_party(store, name_l, due, as_of, book=None, tolerance=None, start_month=None):
    """Period sales, collection, credit notes, and closing balance for one customer."""
    from server.ar_balance import build_ar_statement, opening_from_gap
    from server.org_policy import get_org_policy

    if tolerance is None or start_month is None:
        policy = get_org_policy(store)
        if tolerance is None:
            tolerance = policy["ar_balance_tolerance"]
        if start_month is None:
            start_month = policy["fiscal_year_start_month"]
    sales = []
    receipts = []
    credits = []
    for row in _rows_for_name(store, "sales", name_l, book=book):
        fields = _fields(row)
        d = parse_date(fields.get("Date"))
        if not d:
            continue
        sales.append((d, number_(fields.get("Net Amount"))))
    for row in _rows_for_name(store, "receipt", name_l, book=book):
        fields = _fields(row)
        d = parse_date(fields.get("Date"))
        if not d:
            continue
        receipts.append((d, number_(fields.get("Amount"))))
    for row in _rows_for_name(store, "credit_note", name_l, book=book):
        fields = _fields(row)
        d = parse_date(fields.get("Date"))
        if not d:
            continue
        amount = number_(fields.get("Net Amount"))
        if amount <= 0:
            continue
        credits.append((d, amount))

    def _sum_in_period(rows):
        total = 0.0
        for day, amount in rows:
            if as_of is not None and day > as_of:
                continue
            total += amount
        return total

    gap = _sum_in_period(sales) - _sum_in_period(receipts) - _sum_in_period(credits)
    opening = opening_from_gap(due, gap)
    return build_ar_statement(
        sales, receipts, credits, due, as_of,
        start_month=start_month, tolerance=tolerance, opening=opening,
    )


def _credits_for_party(store, name_l, book=None):
    out = []
    for row in _rows_for_name(store, "credit_note", name_l, book=book):
        fields = _fields(row)
        d = parse_date(fields.get("Date"))
        if not d:
            continue
        amount = number_(fields.get("Net Amount"))
        if amount <= 0:
            continue
        out.append({
            "date": d,
            "amount": amount,
            "invoice": clean_text(fields.get("Invoice No") or ""),
        })
    return out


def _buckets_from_alloc_slice(allocs, bands=None):
    buckets = empty_buckets(bands)
    total = 0.0
    for a in allocs or []:
        amt = max(0.0, number_(a.get("amount")))
        if amt <= 0:
            continue
        total += amt
        buckets[_bucket_key(a.get("age_days") or 0, bands)] += amt
    return buckets, total


def _settlement_lines(allocs, bands=None):
    lines = []
    for a in allocs or []:
        amt = max(0.0, number_(a.get("amount")))
        if amt <= 0:
            continue
        receipt = a.get("receipt_date")
        invoice_date = a.get("target_date")
        age = int(number_(a.get("age_days") or 0))
        lines.append({
            "date_iso": _iso(receipt) if receipt else "",
            "date_label": _fmt_day(receipt) if receipt else "",
            "invoice_date_iso": _iso(invoice_date) if invoice_date else "",
            "invoice_date_label": _fmt_day(invoice_date) if invoice_date else "",
            "amount": round(amt, 2),
            "age_days": age,
            "bucket": _bucket_key(age, bands),
            "kind": a.get("kind") or "",
            "invoice": a.get("invoice") or "",
            "invoice_id": a.get("invoice_id") or "",
            "party": a.get("party") or "",
            "customer_uk": a.get("customer_uk") or "",
        })
    lines.sort(key=lambda row: ((row.get("date_iso") or ""), (row.get("invoice") or "")), reverse=True)
    return lines


def _stamp_settlement_party(summary, name, uk):
    if not isinstance(summary, dict):
        return summary
    periods = [summary.get("overall")]
    periods.extend(summary.get("by_fy") or [])
    periods.extend(summary.get("months") or [])
    for period in periods:
        if not isinstance(period, dict):
            continue
        for line in period.get("lines") or []:
            if not isinstance(line, dict):
                continue
            if name and not line.get("party"):
                line["party"] = name
            if uk and not line.get("customer_uk"):
                line["customer_uk"] = uk
    return summary


def settlements_ready(summary):
    if not isinstance(summary, dict):
        return False
    if not isinstance(summary.get("by_fy"), list) or not isinstance(summary.get("months"), list):
        return False
    if not (summary.get("by_fy") or summary.get("months") or summary.get("overall")):
        return False
    overall = summary.get("overall")
    return isinstance(overall, dict) and isinstance(overall.get("lines"), list)


def _copy_settlement_lines(rows, party="", uk=""):
    copied = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        line = dict(row)
        if party and not line.get("party"):
            line["party"] = party
        if uk and not line.get("customer_uk"):
            line["customer_uk"] = uk
        copied.append(line)
    copied.sort(key=lambda row: ((row.get("date_iso") or ""), (row.get("invoice") or "")), reverse=True)
    return copied


def fill_settlement_lines(summary, sources):
    """Attach invoice lines onto an existing settlement summary without changing totals."""
    if not isinstance(summary, dict):
        return summary
    if settlements_ready(summary):
        return summary
    overall_lines = []
    fy_lines = {}
    month_lines = {}
    for src in sources or []:
        if not isinstance(src, dict):
            continue
        overall_lines.extend(_copy_settlement_lines((src.get("overall") or {}).get("lines")))
        for row in src.get("by_fy") or []:
            fy_lines.setdefault(row.get("key") or "", []).extend(_copy_settlement_lines(row.get("lines")))
        for row in src.get("months") or []:
            month_lines.setdefault(row.get("key") or "", []).extend(_copy_settlement_lines(row.get("lines")))
    out = dict(summary)
    overall = dict(out.get("overall") or {})
    overall["lines"] = _copy_settlement_lines(overall_lines)
    out["overall"] = overall
    out["by_fy"] = []
    for row in summary.get("by_fy") or []:
        slot = dict(row)
        slot["lines"] = _copy_settlement_lines(fy_lines.get(row.get("key") or "", []))
        out["by_fy"].append(slot)
    out["months"] = []
    for row in summary.get("months") or []:
        slot = dict(row)
        slot["lines"] = _copy_settlement_lines(month_lines.get(row.get("key") or "", []))
        out["months"].append(slot)
    return out


def attach_customer_settlement_lines(store, detail, book=None):
    if not detail or settlements_ready(detail.get("settlements")):
        return detail
    return ensure_detail_settlements(store, dict(detail), book=book)


def _peer_customer(peers, uk):
    peers = peers or {}
    if uk in peers:
        return peers.get(uk)
    want = (uk or "").lower()
    for key, value in peers.items():
        if str(key).lower() == want or str((value or {}).get("uk") or "").lower() == want:
            return value
    return None


def attach_rollup_settlement_lines(store, detail, peers, book=None):
    if not detail or settlements_ready(detail.get("settlements")):
        return detail
    if book is None:
        from server.book import load_book
        book = load_book(store)
    sources = []
    ready = {}
    for member in detail.get("customers") or []:
        uk = member.get("uk") or ""
        peer = _peer_customer(peers, uk)
        if not peer:
            continue
        filled = attach_customer_settlement_lines(store, peer, book=book)
        if not filled:
            continue
        ready[filled.get("uk") or uk] = filled
        sources.append(filled.get("settlements"))
    out = dict(detail)
    if detail.get("settlements"):
        out["settlements"] = fill_settlement_lines(detail.get("settlements"), sources)
        return out
    from server.business360 import company_settlements
    out["settlements"] = company_settlements(ready)
    return out


def _month_label(d):
    return d.strftime("%b %Y")


def build_settlements_summary(allocs, as_of, bands=None, credit=0.0, start_month=None):
    """Roll settlement allocations into overall / FY / month views.

    Aging uses age_days already set on each allocation (invoice age at receipt date).
    Period filters use receipt_date.
    """
    bands = bands or default_aging_bands()
    overall_buckets, overall_total = _buckets_from_alloc_slice(allocs, bands)

    by_fy = {}
    by_month = {}
    for a in allocs or []:
        rd = a.get("receipt_date")
        if not rd:
            continue
        fy_start = fiscal_year_start(rd, start_month)
        fy_key = _iso(fy_start)
        slot = by_fy.setdefault(fy_key, {"start": fy_start, "label": fy_label(fy_start), "allocs": []})
        slot["allocs"].append(a)
        mk = "%04d-%02d" % (rd.year, rd.month)
        mslot = by_month.setdefault(mk, {"key": mk, "year": rd.year, "month": rd.month, "label": _month_label(rd), "allocs": []})
        mslot["allocs"].append(a)

    fy_rows = []
    for fy_key in sorted(by_fy.keys(), reverse=True):
        slot = by_fy[fy_key]
        buckets, total = _buckets_from_alloc_slice(slot["allocs"], bands)
        fy_rows.append({
            "key": fy_key,
            "start": fy_key,
            "label": slot["label"],
            "total": total,
            "buckets": buckets,
            "lines": _settlement_lines(slot["allocs"], bands),
        })

    # Continuous months from earliest receipt (else as_of) through report month.
    current_key = "%04d-%02d" % (as_of.year, as_of.month)
    if by_month:
        start_key = min(by_month.keys())
        if start_key > current_key:
            start_key = current_key
    else:
        start_key = current_key
    start_y, start_m = int(start_key[:4]), int(start_key[5:7])
    month_keys = []
    y, m = start_y, start_m
    while (y, m) <= (as_of.year, as_of.month):
        month_keys.append("%04d-%02d" % (y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1

    month_rows = []
    for mk in reversed(month_keys):
        slot = by_month.get(mk)
        if slot:
            buckets, total = _buckets_from_alloc_slice(slot["allocs"], bands)
            month_rows.append({
                "key": slot["key"],
                "year": slot["year"],
                "month": slot["month"],
                "label": slot["label"],
                "total": total,
                "buckets": buckets,
                "lines": _settlement_lines(slot["allocs"], bands),
            })
        else:
            yy, mm = int(mk[:4]), int(mk[5:7])
            month_rows.append({
                "key": mk,
                "year": yy,
                "month": mm,
                "label": _month_label(datetime(yy, mm, 1, 12)),
                "total": 0.0,
                "buckets": empty_buckets(bands),
                "lines": [],
            })

    return {
        "overall": {
            "total": overall_total,
            "buckets": overall_buckets,
            "credit": max(0.0, number_(credit)),
            "lines": _settlement_lines(allocs, bands),
        },
        "by_fy": fy_rows,
        "months": month_rows,
        "default_month": current_key,
    }


def _settle_party(invoices, receipts, as_of, opening_dt, mode, due, bands=None, credits=None, start_month=None):
    buckets, allocs, credit, rem, op = allocate_collections(
        invoices, receipts, as_of, opening_dt=opening_dt, mode=mode, due=due, bands=bands,
        credits=credits,
    )
    settlements = build_settlements_summary(
        allocs, as_of, bands=bands, credit=credit, start_month=start_month,
    )
    return buckets, settlements, credit, rem, op


def _empty_ordering_period():
    return {
        "sales_count": 0,
        "sales_value": 0.0,
        "flagged_count": 0,
        "flagged_value": 0.0,
        "events": [],
    }


def _ordering_period_from_sales(sales_events, flagged_events):
    period = _empty_ordering_period()
    for ev in sales_events or []:
        period["sales_count"] += 1
        period["sales_value"] += number_(ev.get("amount"))
    for ev in flagged_events or []:
        period["flagged_count"] += 1
        period["flagged_value"] += number_(ev.get("amount"))
        period["events"].append(ev)
    period["sales_value"] = round(period["sales_value"], 2)
    period["flagged_value"] = round(period["flagged_value"], 2)
    return period


def _open_before_sale(prior_invoices, receipts, sale_date, mode, bands, opening0=0.0, opening_dt=None, credits=None, start_month=None):
    """Open outstanding as of sale_date (prior invoices + implied opening).

    opening0 is the brought-forward balance implied by ARR
    (estimate_opening_amount), so Ordering can flag sales placed while
    opening was already past due — not only prior invoices.
    """
    receipts_to_d = [r for r in (receipts or []) if r.get("date") and r["date"] <= sale_date]
    credits_to_d = [c for c in (credits or []) if c.get("date") and c["date"] <= sale_date]
    sales_total = sum(number_(inv.get("amount")) for inv in (prior_invoices or []))
    receipt_total = sum(number_(r.get("amount")) for r in receipts_to_d)
    credit_total = sum(number_(c.get("amount")) for c in credits_to_d)
    due = number_(opening0) + sales_total - receipt_total - credit_total
    if due <= 0.005:
        return [], due
    if opening_dt is None:
        opening_dt = _opening_from_invoices(prior_invoices, sale_date, start_month)
    open_lines, _buckets, _opening, _opened = _allocate_open(
        prior_invoices or [],
        due,
        sale_date,
        opening_dt,
        mode=mode,
        receipts=receipts_to_d,
        bands=bands,
        credits=credits_to_d,
    )
    return open_lines, due


def _gap_band_rows(bands):
    bands = bands or default_aging_bands()
    rows = [{"key": "first", "label": "First order", "count": 0, "value": 0.0}]
    for band in bands:
        rows.append({
            "key": band["key"],
            "label": band.get("label") or band["key"],
            "count": 0,
            "value": 0.0,
        })
    return rows


def _blank_gap_period(bands):
    return {"orders": 0, "value": 0.0, "buckets": _gap_band_rows(bands), "lines": []}


def _add_gap_line(period, line, bucket_key):
    period["orders"] += 1
    period["value"] = round(period["value"] + line["amount"], 2)
    for bucket in period["buckets"]:
        if bucket["key"] == bucket_key:
            bucket["count"] += 1
            bucket["value"] = round(bucket["value"] + line["amount"], 2)
            break
    period["lines"].append(line)


def _sort_gap_lines(period):
    period["lines"].sort(key=lambda row: row.get("date_iso") or "", reverse=True)


def empty_sales_gaps(bands=None):
    bands = bands or default_aging_bands()
    band_meta = [{"key": "first", "label": "First order"}]
    band_meta.extend({"key": band["key"], "label": band.get("label") or band["key"]} for band in bands)
    return {
        "bands": band_meta,
        "overall": _blank_gap_period(bands),
        "fy": _blank_gap_period(bands),
        "month": _blank_gap_period(bands),
        "by_fy": [],
        "months": [],
    }


def _gap_slot(store, key, bands, label, extra=None):
    slot = store.get(key)
    if slot is None:
        slot = _blank_gap_period(bands)
        slot["key"] = key
        slot["label"] = label
        if extra:
            slot.update(extra)
        store[key] = slot
    return slot


def sales_gap_periods(orders, as_of, bands=None, start_month=None):
    """Bucket each order by days since that customer's previous order.

    Invoices on the same day are already one order. The first order has no
    previous order. Later orders keep that gap even when the previous order
    falls in an earlier year or month. Every fiscal year and every month is
    kept, not only the current ones.
    """
    bands = bands or default_aging_bands()
    summary = empty_sales_gaps(bands)
    if not as_of:
        return summary
    current_fy = _iso(fiscal_year_start(as_of, start_month))
    current_month = "%04d-%02d" % (as_of.year, as_of.month)
    by_fy = {}
    by_month = {}
    dated = [order for order in (orders or []) if order.get("date") and order["date"] <= as_of]
    dated.sort(key=lambda order: order["date"])
    prev = None
    for order in dated:
        if prev is None:
            key = "first"
            gap = None
        else:
            gap = max(0, (order["date"] - prev).days)
            key = _bucket_key(gap, bands)
        prev = order["date"]
        when = order["date"]
        line = {
            "date_iso": order.get("date_iso") or _iso(when),
            "date_label": order.get("date_label") or _fmt_day(when),
            "amount": round(number_(order.get("amount")), 2),
            "gap_days": gap,
            "bucket": key,
            "invoice": order.get("invoice") or "",
            "invoice_id": order.get("invoice_id") or "",
            "party": order.get("party") or "",
            "customer_uk": order.get("customer_uk") or "",
        }
        fy_start = fiscal_year_start(when, start_month)
        fy_key = _iso(fy_start)
        month_key = "%04d-%02d" % (when.year, when.month)
        targets = [
            summary["overall"],
            _gap_slot(by_fy, fy_key, bands, fy_label(fy_start)),
            _gap_slot(by_month, month_key, bands, _month_label(when), {"year": when.year, "month": when.month}),
        ]
        for period in targets:
            _add_gap_line(period, line, key)
    summary["by_fy"] = [by_fy[key] for key in sorted(by_fy.keys(), reverse=True)]
    summary["months"] = [by_month[key] for key in sorted(by_month.keys(), reverse=True)]
    summary["fy"] = by_fy.get(current_fy) or _blank_gap_period(bands)
    summary["month"] = by_month.get(current_month) or _blank_gap_period(bands)
    for period in [summary["overall"], summary["fy"], summary["month"], *summary["by_fy"], *summary["months"]]:
        _sort_gap_lines(period)
    return summary


def _merge_gap_period(dest, src):
    by_key = {bucket["key"]: bucket for bucket in dest["buckets"]}
    dest["orders"] += src.get("orders") or 0
    dest["value"] = round(dest["value"] + number_(src.get("value")), 2)
    for bucket in src.get("buckets") or []:
        slot = by_key.get(bucket.get("key"))
        if not slot:
            continue
        slot["count"] += bucket.get("count") or 0
        slot["value"] = round(slot["value"] + number_(bucket.get("value")), 2)
    dest["lines"].extend(src.get("lines") or [])


def _merge_gap_rows(rows, bands):
    out = {}
    for row in rows or []:
        key = row.get("key") or ""
        if not key:
            continue
        slot = out.get(key)
        if slot is None:
            slot = _blank_gap_period(bands)
            slot["key"] = key
            slot["label"] = row.get("label") or key
            if row.get("year") is not None:
                slot["year"] = row.get("year")
            if row.get("month") is not None:
                slot["month"] = row.get("month")
            out[key] = slot
        _merge_gap_period(slot, row)
    for slot in out.values():
        _sort_gap_lines(slot)
    return [out[key] for key in sorted(out.keys(), reverse=True)]


def merge_sales_gaps(parts, bands=None):
    """Add per-customer gap buckets. Does not recompute gaps across customers."""
    parts = [part for part in (parts or []) if part]
    if not parts:
        return empty_sales_gaps(bands)
    band_rows = bands or _bands_from_gap_meta(parts[0].get("bands"))
    merged = empty_sales_gaps(band_rows)
    for key in ("overall", "fy", "month"):
        for part in parts:
            _merge_gap_period(merged[key], part.get(key) or {})
        _sort_gap_lines(merged[key])
    merged["by_fy"] = _merge_gap_rows([row for part in parts for row in (part.get("by_fy") or [])], band_rows)
    merged["months"] = _merge_gap_rows([row for part in parts for row in (part.get("months") or [])], band_rows)
    return merged


def _bands_from_gap_meta(meta):
    rows = []
    for band in meta or []:
        if band.get("key") == "first":
            continue
        rows.append({"key": band.get("key"), "label": band.get("label") or band.get("key"), "max_days": None})
    return rows or None


def _sales_gaps_ready(stored):
    return bool(stored) and "by_fy" in stored and "months" in stored


def sales_gaps_from_detail(detail):
    """Use the stored summary, or rebuild it from this customer's sale activity."""
    if not detail:
        return empty_sales_gaps()
    stored = ((detail.get("ordering") or {}).get("sales_gaps"))
    if _sales_gaps_ready(stored):
        return stored
    grouped = {}
    for event in detail.get("activity") or []:
        if event.get("kind") != "sale":
            continue
        when = parse_date(event.get("date"))
        if not when:
            continue
        slot = grouped.setdefault(when.strftime("%Y-%m-%d"), {
            "date": when,
            "date_iso": event.get("date") or _iso(when),
            "date_label": event.get("date_label") or _fmt_day(when),
            "amount": 0.0,
            "invoice": [],
            "invoice_id": event.get("invoice_id") or "",
            "party": detail.get("name") or "",
            "customer_uk": detail.get("uk") or "",
        })
        slot["amount"] = round(slot["amount"] + number_(event.get("amount")), 2)
        if event.get("invoice"):
            slot["invoice"].append(event.get("invoice"))
        if not slot["invoice_id"] and event.get("invoice_id"):
            slot["invoice_id"] = event.get("invoice_id")
    orders = []
    for slot in grouped.values():
        slot["invoice"] = ", ".join(slot["invoice"])
        orders.append(slot)
    as_of = parse_date(detail.get("as_of")) or today_ist()
    rebuilt = sales_gap_periods(
        orders,
        as_of,
        detail.get("aging_bands") or default_aging_bands(),
        detail.get("fiscal_year_start_month"),
    )
    if rebuilt["overall"]["orders"] or not stored:
        return rebuilt
    return stored


def attach_sales_gaps(detail):
    if not detail:
        return detail
    ordering = detail.get("ordering") or {}
    if _sales_gaps_ready(ordering.get("sales_gaps")):
        return detail
    out = dict(detail)
    ordering = dict(ordering)
    ordering["sales_gaps"] = sales_gaps_from_detail(detail)
    out["ordering"] = ordering
    return out


def attach_rollup_sales_gaps(detail, peers):
    if not detail:
        return detail
    ordering = detail.get("ordering") or {}
    if _sales_gaps_ready(ordering.get("sales_gaps")):
        return detail
    parts = []
    peers = peers or {}
    for member in detail.get("customers") or []:
        uk = member.get("uk") or ""
        peer = peers.get(uk)
        if peer is None and uk:
            for key, value in peers.items():
                if str(key).lower() == uk.lower():
                    peer = value
                    break
        if peer:
            parts.append(sales_gaps_from_detail(peer))
    out = dict(detail)
    ordering = dict(ordering)
    ordering["sales_gaps"] = merge_sales_gaps(parts, detail.get("aging_bands"))
    out["ordering"] = ordering
    return out


def build_ordering_summary(
    invoices,
    receipts,
    as_of,
    due_days,
    due_days_source="default",
    mode=None,
    bands=None,
    party_name="",
    customer_uk="",
    arr_due=None,
    credits=None,
    start_month=None,
):
    """Flag sales placed while prior open age exceeded due_days (as of sale date).

    Prior open includes brought-forward opening implied by ARR due, not only
    earlier sales invoices.
    """
    from server.due_days import DEFAULT_DUE_DAYS
    from vay.settlement import estimate_opening_amount

    mode = mode or DEFAULT_SETTLEMENT_MODE
    bands = bands or default_aging_bands()
    due_days = int(due_days if due_days is not None else DEFAULT_DUE_DAYS)
    invoices = list(invoices or [])
    invoices.sort(key=lambda x: x["date"])
    receipts = list(receipts or [])
    credits = list(credits or [])
    # Constant opening that reconciles current ARR with sales, receipts, and credit notes.
    if arr_due is None:
        opening0 = 0.0
    else:
        opening0 = estimate_opening_amount(arr_due, invoices, receipts, credits)
    opening_dt = _opening_from_invoices(invoices, as_of, start_month)

    sales_events = []
    flagged_events = []
    prior = []
    gap_orders = []
    i = 0
    n = len(invoices)
    while i < n:
        sale_date = invoices[i]["date"]
        cohort = []
        while i < n and invoices[i]["date"] == sale_date:
            cohort.append(invoices[i])
            i += 1
        for inv in cohort:
            amount = number_(inv.get("amount"))
            sale_ev = {
                "date": inv["date"],
                "date_iso": _iso(inv["date"]),
                "date_label": _fmt_day(inv["date"]),
                "amount": amount,
                "invoice": inv.get("invoice") or "",
                "invoice_id": inv.get("invoice_id") or "",
                "rep": inv.get("rep") or "",
                "party": party_name or "",
                "customer_uk": customer_uk or "",
            }
            sales_events.append(sale_ev)
            open_lines, _due = _open_before_sale(
                prior, receipts, sale_date, mode, bands,
                opening0=opening0, opening_dt=opening_dt, credits=credits, start_month=start_month,
            )
            overdue_lines = [ln for ln in open_lines if (ln.get("age_days") or 0) > due_days]
            if overdue_lines:
                oldest = max((ln.get("age_days") or 0) for ln in overdue_lines)
                overdue_amount = sum(
                    number_(ln.get("due") if ln.get("due") is not None else ln.get("amount"))
                    for ln in overdue_lines
                )
                flagged_events.append({
                    **sale_ev,
                    "oldest_age": oldest,
                    "overdue_amount": round(overdue_amount, 2),
                    "due_days": due_days,
                    "due_days_source": due_days_source,
                    "open_count": len(open_lines),
                })
        gap_orders.append({
            "date": sale_date,
            "date_iso": _iso(sale_date),
            "date_label": _fmt_day(sale_date),
            "amount": round(sum(number_(inv.get("amount")) for inv in cohort), 2),
            "invoice": ", ".join(inv.get("invoice") or "" for inv in cohort if inv.get("invoice")),
            "invoice_id": (cohort[0].get("invoice_id") if cohort else "") or "",
            "party": party_name or "",
            "customer_uk": customer_uk or "",
        })
        prior.extend(cohort)

    overall = _ordering_period_from_sales(sales_events, flagged_events)

    by_fy = {}
    by_month = {}
    for ev in sales_events:
        d = ev["date"]
        if d > as_of:
            continue
        fy_start = fiscal_year_start(d, start_month)
        fy_key = _iso(fy_start)
        by_fy.setdefault(fy_key, {"start": fy_start, "label": fy_label(fy_start), "sales": [], "flagged": []})
        by_fy[fy_key]["sales"].append(ev)
        mk = "%04d-%02d" % (d.year, d.month)
        by_month.setdefault(mk, {"key": mk, "year": d.year, "month": d.month, "label": _month_label(d), "sales": [], "flagged": []})
        by_month[mk]["sales"].append(ev)

    for ev in flagged_events:
        d = ev["date"]
        if d > as_of:
            continue
        fy_key = _iso(fiscal_year_start(d, start_month))
        if fy_key in by_fy:
            by_fy[fy_key]["flagged"].append(ev)
        mk = "%04d-%02d" % (d.year, d.month)
        if mk in by_month:
            by_month[mk]["flagged"].append(ev)

    fy_rows = []
    for fy_key in sorted(by_fy.keys(), reverse=True):
        slot = by_fy[fy_key]
        row = _ordering_period_from_sales(slot["sales"], slot["flagged"])
        row.update({"key": fy_key, "start": fy_key, "label": slot["label"]})
        fy_rows.append(row)

    current_key = "%04d-%02d" % (as_of.year, as_of.month)
    if by_month:
        start_key = min(by_month.keys())
        if start_key > current_key:
            start_key = current_key
    elif sales_events:
        first = min(ev["date"] for ev in sales_events)
        start_key = "%04d-%02d" % (first.year, first.month)
        if start_key > current_key:
            start_key = current_key
    else:
        start_key = current_key

    start_y, start_m = int(start_key[:4]), int(start_key[5:7])
    month_keys = []
    y, m = start_y, start_m
    while (y, m) <= (as_of.year, as_of.month):
        month_keys.append("%04d-%02d" % (y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1

    month_rows = []
    for mk in reversed(month_keys):
        slot = by_month.get(mk)
        if slot:
            row = _ordering_period_from_sales(slot["sales"], slot["flagged"])
            row.update({
                "key": slot["key"],
                "year": slot["year"],
                "month": slot["month"],
                "label": slot["label"],
            })
        else:
            yy, mm = int(mk[:4]), int(mk[5:7])
            row = _empty_ordering_period()
            row.update({
                "key": mk,
                "year": yy,
                "month": mm,
                "label": _month_label(datetime(yy, mm, 1, 12)),
            })
        month_rows.append(row)

    fy_start_as_of = fiscal_year_start(as_of, start_month)
    fy_key_as_of = _iso(fy_start_as_of)
    current_fy_row = next((r for r in fy_rows if r["key"] == fy_key_as_of), None)
    current_month_row = next((r for r in month_rows if r["key"] == current_key), None)

    badge = {
        "current_month": bool(current_month_row and current_month_row["flagged_count"]),
        "current_fy": bool(current_fy_row and current_fy_row["flagged_count"]),
    }

    # Strip raw date objects from events for JSON
    def _clean_events(period):
        cleaned = []
        for ev in period.get("events") or []:
            row = dict(ev)
            row.pop("date", None)
            cleaned.append(row)
        period["events"] = cleaned
        return period

    overall = _clean_events(overall)
    for row in fy_rows:
        _clean_events(row)
    for row in month_rows:
        _clean_events(row)

    return {
        "overall": overall,
        "by_fy": fy_rows,
        "months": month_rows,
        "default_month": current_key,
        "due_days": due_days,
        "due_days_source": due_days_source or "default",
        "badge": badge,
        "sales_gaps": sales_gap_periods(gap_orders, as_of, bands, start_month),
    }


def empty_ordering_summary(as_of, due_days=30, due_days_source="default"):
    current_key = "%04d-%02d" % (as_of.year, as_of.month)
    return {
        "overall": _empty_ordering_period(),
        "by_fy": [],
        "months": [{
            **_empty_ordering_period(),
            "key": current_key,
            "year": as_of.year,
            "month": as_of.month,
            "label": _month_label(as_of),
        }],
        "default_month": current_key,
        "due_days": due_days,
        "due_days_source": due_days_source,
        "badge": {"current_month": False, "current_fy": False},
        "sales_gaps": empty_sales_gaps(),
    }


def merge_ordering_summaries(summaries, as_of, due_days=None, due_days_source="default", start_month=None):
    """Merge per-customer ordering into group/rep rollup."""
    from server.due_days import DEFAULT_DUE_DAYS

    due_days = int(due_days if due_days is not None else DEFAULT_DUE_DAYS)
    overall = _empty_ordering_period()
    flagged = []
    earliest = None
    for summary in summaries or []:
        o = summary.get("overall") or {}
        overall["sales_count"] += o.get("sales_count") or 0
        overall["sales_value"] += number_(o.get("sales_value"))
        overall["flagged_count"] += o.get("flagged_count") or 0
        overall["flagged_value"] += number_(o.get("flagged_value"))
        for ev in o.get("events") or []:
            flagged.append(dict(ev))
            d = parse_date(ev.get("date_iso") or ev.get("date"))
            if d and (earliest is None or d < earliest):
                earliest = d
        for row in summary.get("months") or []:
            if row.get("sales_count"):
                mk = row.get("key")
                if mk:
                    y, m = int(mk[:4]), int(mk[5:7])
                    d = datetime(y, m, 1, 12)
                    if earliest is None or d < earliest:
                        earliest = d

    overall["sales_value"] = round(overall["sales_value"], 2)
    overall["flagged_value"] = round(overall["flagged_value"], 2)
    overall["events"] = flagged
    flagged.sort(key=lambda e: e.get("date_iso") or "", reverse=True)

    by_fy = {}
    by_month = {}
    for summary in summaries or []:
        for row in summary.get("by_fy") or []:
            key = row.get("key")
            if not key:
                continue
            slot = by_fy.setdefault(key, {
                "key": key,
                "start": row.get("start") or key,
                "label": row.get("label") or "",
                "sales_count": 0,
                "sales_value": 0.0,
                "flagged_count": 0,
                "flagged_value": 0.0,
                "events": [],
            })
            slot["sales_count"] += row.get("sales_count") or 0
            slot["sales_value"] += number_(row.get("sales_value"))
            slot["flagged_count"] += row.get("flagged_count") or 0
            slot["flagged_value"] += number_(row.get("flagged_value"))
            slot["events"].extend(row.get("events") or [])
        for row in summary.get("months") or []:
            key = row.get("key")
            if not key:
                continue
            slot = by_month.setdefault(key, {
                "key": key,
                "year": row.get("year"),
                "month": row.get("month"),
                "label": row.get("label") or "",
                "sales_count": 0,
                "sales_value": 0.0,
                "flagged_count": 0,
                "flagged_value": 0.0,
                "events": [],
            })
            slot["sales_count"] += row.get("sales_count") or 0
            slot["sales_value"] += number_(row.get("sales_value"))
            slot["flagged_count"] += row.get("flagged_count") or 0
            slot["flagged_value"] += number_(row.get("flagged_value"))
            slot["events"].extend(row.get("events") or [])

    fy_rows = []
    for key in sorted(by_fy.keys(), reverse=True):
        slot = by_fy[key]
        slot["sales_value"] = round(slot["sales_value"], 2)
        slot["flagged_value"] = round(slot["flagged_value"], 2)
        fy_rows.append(slot)

    current_key = "%04d-%02d" % (as_of.year, as_of.month)
    if by_month:
        start_key = min(by_month.keys())
        if start_key > current_key:
            start_key = current_key
    elif earliest:
        start_key = "%04d-%02d" % (earliest.year, earliest.month)
        if start_key > current_key:
            start_key = current_key
    else:
        start_key = current_key

    start_y, start_m = int(start_key[:4]), int(start_key[5:7])
    month_rows = []
    y, m = start_y, start_m
    keys = []
    while (y, m) <= (as_of.year, as_of.month):
        keys.append("%04d-%02d" % (y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    for mk in reversed(keys):
        if mk in by_month:
            slot = by_month[mk]
            slot["sales_value"] = round(slot["sales_value"], 2)
            slot["flagged_value"] = round(slot["flagged_value"], 2)
            month_rows.append(slot)
        else:
            yy, mm = int(mk[:4]), int(mk[5:7])
            row = _empty_ordering_period()
            row.update({
                "key": mk,
                "year": yy,
                "month": mm,
                "label": _month_label(datetime(yy, mm, 1, 12)),
            })
            month_rows.append(row)

    fy_key_as_of = _iso(fiscal_year_start(as_of, start_month))
    current_fy_row = next((r for r in fy_rows if r["key"] == fy_key_as_of), None)
    current_month_row = next((r for r in month_rows if r["key"] == current_key), None)
    badge = {
        "current_month": bool(current_month_row and current_month_row["flagged_count"]),
        "current_fy": bool(current_fy_row and current_fy_row["flagged_count"]),
    }
    return {
        "overall": overall,
        "by_fy": fy_rows,
        "months": month_rows,
        "default_month": current_key,
        "due_days": due_days,
        "due_days_source": due_days_source,
        "badge": badge,
        "sales_gaps": merge_sales_gaps([summary.get("sales_gaps") for summary in (summaries or [])]),
    }


def ordering_for_party(store, name_l, as_of, *, party_name="", customer_uk="", group="", rep="", book=None, mode=None, bands=None, overrides=None, default_due=None, arr_due=None):
    from server.due_days import get_default_due_days, resolve_due_days

    book = book or getattr(store, "_360_book", None)
    mode = mode or get_settlement_mode(store)
    bands = bands or get_aging_bands(store)
    sm = _fy_month(store, book)
    default_due = get_default_due_days(store) if default_due is None else default_due
    resolved = resolve_due_days(
        store,
        customer_uk=customer_uk or party_name,
        group=group,
        rep=rep,
        overrides=overrides,
        default=default_due,
    )
    invoices = _group_sales_invoices(_rows_for_name(store, "sales", name_l, book=book), start_month=sm)
    receipts = _receipts_for_party(store, name_l, book=book)
    credits = _credits_for_party(store, name_l, book=book)
    if arr_due is None and book is not None:
        arr_map = book.get("arr_due") or {}
        if name_l in arr_map:
            arr_due = arr_map[name_l]
        else:
            uk_l = account_uk(customer_uk or party_name).lower()
            if uk_l in arr_map:
                arr_due = arr_map[uk_l]
    if not invoices:
        return empty_ordering_summary(as_of, resolved["due_days"], resolved["source"])
    return build_ordering_summary(
        invoices,
        receipts,
        as_of,
        resolved["due_days"],
        due_days_source=resolved["source"],
        mode=mode,
        bands=bands,
        party_name=party_name,
        customer_uk=customer_uk or account_uk(party_name),
        arr_due=arr_due,
        credits=credits,
        start_month=sm,
    )


def _activity(store, name_l, as_of, book=None, bands=None, start_month=None):
    events = []
    sales = []
    receipts = []
    credits = []
    bands = bands or default_aging_bands()
    sale_rows = _rows_for_name(store, "sales", name_l, book=book)
    for row in sale_rows:
        fields = _fields(row)
        d = parse_date(fields.get("Date"))
        if not d:
            continue
        amount = number_(fields.get("Net Amount"))
        sales.append((d, amount, fields))
    for inv in _group_sales_invoices(sale_rows, start_month=_fy_month(store, book, start_month)):
        events.append({
            "kind": "sale",
            "date": _iso(inv["date"]),
            "date_label": _fmt_day(inv["date"]),
            "amount": inv["amount"],
            "label": ACTIVITY_LABELS["sale"],
            "rep": inv.get("rep") or "",
            "invoice": inv.get("invoice") or "",
            "invoice_id": inv.get("invoice_id") or "",
            "note": "",
            "logged": False,
            "id": "",
            "_d": inv["date"],
        })
    for row in _rows_for_name(store, "receipt", name_l, book=book):
        fields = _fields(row)
        d = parse_date(fields.get("Date"))
        if not d:
            continue
        amount = number_(fields.get("Amount"))
        receipts.append((d, amount, fields))
        events.append({
            "kind": "collection",
            "date": _iso(d),
            "date_label": _fmt_day(d),
            "amount": amount,
            "label": ACTIVITY_LABELS["collection"],
            "rep": clean_text(fields.get("Sales Rep")),
            "invoice": "",
            "invoice_id": "",
            "note": "",
            "logged": False,
            "id": "",
            "_d": d,
        })
    for row in _rows_for_name(store, "credit_note", name_l, book=book):
        fields = _fields(row)
        d = parse_date(fields.get("Date"))
        if not d:
            continue
        amount = number_(fields.get("Net Amount"))
        if amount <= 0:
            continue
        credits.append((d, amount, fields))
        events.append({
            "kind": "credit_note",
            "date": _iso(d),
            "date_label": _fmt_day(d),
            "amount": amount,
            "label": ACTIVITY_LABELS["credit_note"],
            "rep": clean_text(fields.get("Sales Rep")),
            "invoice": clean_text(fields.get("Invoice No")),
            "invoice_id": "",
            "note": clean_text(fields.get("Invoice No")),
            "logged": False,
            "id": "",
            "_d": d,
        })
    kinds = _kind_maps(store)
    if book is not None:
        notes_idx = book.get("notes_by_party") or {}
        note_rows = list(notes_idx.get(name_l) or [])
        uk_key = account_uk(name_l).lower()
        if uk_key and uk_key != name_l:
            seen = {id(r) for r in note_rows}
            for row in notes_idx.get(uk_key) or []:
                if id(row) not in seen:
                    note_rows.append(row)
    else:
        note_rows = store.rows_of_type(NOTE_TYPE)
    for row in note_rows:
        fields = _fields(row)
        if not _note_matches(fields, name_l):
            continue
        d = parse_date(fields.get("Date"))
        if not d:
            continue
        kind = _note_kind(fields.get("Kind"), kinds) or _kind_slug(fields.get("Kind"))
        if not kind:
            continue
        events.append({
            "kind": kind,
            "date": _iso(d),
            "date_label": _fmt_day(d),
            "amount": 0.0,
            "label": kinds.get(kind) or clean_text(fields.get("Kind Label") or fields.get("Kind")) or kind,
            "rep": clean_text(fields.get("Assignee") or fields.get("Sales Rep")),
            "invoice": "",
            "invoice_id": "",
            "note": clean_text(fields.get("Note")),
            "logged": True,
            "id": row.get("uk") or "",
            "_d": d,
        })
    events.sort(key=lambda e: e["_d"], reverse=True)
    sm = _fy_month(store, book, start_month)
    fy_start = fiscal_year_start(as_of, sm)
    ytd_sales = sum(a for d, a, _ in sales if d >= fy_start and d <= as_of)
    ytd_sales -= sum(a for d, a, _ in credits if d >= fy_start and d <= as_of)
    ytd_collection = sum(a for d, a, _ in receipts if d >= fy_start and d <= as_of)
    dated = [d for d, _a, _f in sales] + [d for d, _a, _f in receipts] + [d for d, _a, _f in credits]
    min_d = min(dated) if dated else as_of
    fy_years = []
    for start in iter_fiscal_years(min_d, as_of, sm):
        next_start = datetime(start.year + 1, sm, 1, 12)
        s_amt = sum(a for d, a, _ in sales if d >= start and d < next_start and d <= as_of)
        s_amt -= sum(a for d, a, _ in credits if d >= start and d < next_start and d <= as_of)
        c_amt = sum(a for d, a, _ in receipts if d >= start and d < next_start and d <= as_of)
        fy_years.append({
            "label": fy_label(start),
            "start": _iso(start),
            "sales": s_amt,
            "collection": c_amt,
        })
    fy_years.reverse()
    last_sale = max((d for d, _a, _f in sales), default=None)
    last_receipt = max((d for d, _a, _f in receipts), default=None)
    last_rep = ""
    if last_sale:
        for d, _a, fields in sales:
            if d == last_sale:
                last_rep = clean_text(fields.get("Sales Rep"))
                break
    mix = empty_buckets(bands)
    for d, amount, _f in sales:
        mix[_bucket_key(_age_days(as_of, d), bands)] += amount
    for d, amount, _f in credits:
        mix[_bucket_key(_age_days(as_of, d), bands)] -= amount
    cleaned = []
    for e in events:
        row = dict(e)
        row.pop("_d", None)
        cleaned.append(row)
    return {
        "events": cleaned,
        "ytd_sales": ytd_sales,
        "ytd_collection": ytd_collection,
        "last_sale": _iso(last_sale),
        "last_sale_label": _fmt_day(last_sale),
        "last_collection": _iso(last_receipt),
        "last_collection_label": _fmt_day(last_receipt),
        "salesperson": last_rep,
        "sales_mix": mix,
        "fy_years": fy_years,
        "sales_rows": [(d, a) for d, a, _fields in sales],
        "credit_rows": [(d, a) for d, a, _fields in credits],
    }


def _month_start(d):
    return datetime(d.year, d.month, 1, 12)


def _shift_month(d, months):
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    return datetime(y, m, 1, 12)


def _period_bounds(as_of, start_month=None):
    sm = normalize_fy_start_month(start_month)
    this_m = _month_start(as_of)
    last_m = _shift_month(this_m, -1)
    last_end = this_m - timedelta(days=1)
    last_end = datetime(last_end.year, last_end.month, last_end.day, 12)
    fy = fiscal_year_start(as_of, sm)
    prev_fy = datetime(fy.year - 1, sm, 1, 12)
    prev_fy_end = fy - timedelta(days=1)
    prev_fy_end = datetime(prev_fy_end.year, prev_fy_end.month, prev_fy_end.day, 12)
    return {
        "this_month": (this_m, as_of, "This month"),
        "last_month": (last_m, last_end, "Last month"),
        "last_3m": (_shift_month(this_m, -2), as_of, "Last 3 months"),
        "this_year": (fy, as_of, "This year"),
        "last_year": (prev_fy, prev_fy_end, "Last year"),
        "all": (None, as_of, "All time"),
    }


def attach_fy_qty(fy_years, lines, has_item_rows):
    """Stamp item-line quantity onto each fiscal-year row. No lines stay blank, not zero."""
    years = fy_years or []
    if not has_item_rows:
        for row in years:
            row["qty"] = None
        return years
    for row in years:
        start = row.get("start")
        if isinstance(start, str):
            start = parse_date(start)
        if not start:
            row["qty"] = None
            continue
        next_start = datetime(start.year + 1, start.month, 1, 12)
        total = 0.0
        for line in lines or []:
            when = line.get("date")
            if not when or when < start or when >= next_start:
                continue
            total += float(line.get("qty") or 0)
        row["qty"] = round(total, 2)
    return years


def attach_party_fy_qty(store, name_ls, fy_years, book=None):
    """Quantity for a customer, group, or salesperson from the buying lines already on the book."""
    book = book or getattr(store, "_360_book", None)
    if book is None:
        from server.book import load_book
        book = load_book(store)
    lines = []
    by_party = (book or {}).get("buying_lines_by_party") or {}
    for name_l in name_ls or []:
        lines.extend(by_party.get((name_l or "").lower()) or [])
    return attach_fy_qty(fy_years, lines, bool(lines))


def _in_period(d, start, end):
    if not d:
        return False
    if start and d < start:
        return False
    if end and d > end:
        return False
    return True


def _rank_items(items, start, end, as_of, stock=None):
    grouped = {}
    for i in items:
        d = i.get("date")
        name = i.get("name")
        if not name or not _in_period(d, start, end if end else as_of):
            continue
        if d > as_of:
            continue
        row = grouped.setdefault(name, {"name": name, "qty": 0.0, "amount": 0.0, "dates": []})
        row["qty"] += i.get("qty") or 0
        row["amount"] += (i.get("qty") or 0) * (i.get("rate") or 0)
        row["dates"].append(d)
    out = []
    for row in grouped.values():
        days = sorted(set(row["dates"]))
        gaps = []
        for a, b in zip(days, days[1:]):
            gaps.append(_age_days(b, a) or (b - a).days)
        avg_gap = int(sum(gaps) / len(gaps)) if gaps else 0
        last = days[-1] if days else None
        name = row["name"]
        out.append({
            "name": name,
            "qty": row["qty"],
            "amount": row["amount"],
            "times": len(days),
            "last_date": _iso(last),
            "last_label": _fmt_day(last),
            "avg_gap_days": avg_gap,
            "age_days": _age_days(as_of, last) if last else 0,
            "item_uk": account_uk(name) if stock and name.lower() in stock else "",
        })
    out.sort(key=lambda r: (-r["amount"], -r["qty"], r["name"]))
    return out


def _in_stock(stock, name):
    if not stock:
        return True
    qty = stock.get(name.lower())
    return qty is None or qty > 0


def _item_lines_for_customer(store, name_l, book=None):
    book = book or getattr(store, "_360_book", None)
    if book is not None:
        return list(book.get("buying_lines_by_party", {}).get(name_l) or [])
    from server.invoices import _invoice_no, invoice_scope_key
    from server.org_policy import get_org_policy

    start_month = get_org_policy(store)["fiscal_year_start_month"]
    sales_by_no = {}
    for row in store.rows_of_type("sales"):
        fields = row.get("fields") or {}
        inv = _invoice_no(fields)
        if not inv:
            continue
        party = (_party_from_fields(fields) or _party_name(fields, "sales")).lower()
        if party:
            sales_by_no[invoice_scope_key(inv, fields.get("Date"), start_month)] = party
    out = []
    for row in store.rows_of_type("items"):
        fields = row.get("fields") or {}
        party = (_party_from_fields(fields) or _party_name(fields, "items")).lower()
        inv = _invoice_no(fields)
        if not party and inv:
            party = sales_by_no.get(invoice_scope_key(inv, fields.get("Date"), start_month), "")
        if party != name_l:
            continue
        out.append({
            "date": parse_date(fields.get("Date")),
            "name": clean_text(fields.get("Item Name")),
            "qty": number_(fields.get("Qty")),
            "rate": number_(fields.get("Rate")),
        })
    return out


def _buying(store, name_l, as_of, book=None, start_month=None):
    book = book or getattr(store, "_360_book", None)
    sm = _fy_month(store, book, start_month)
    items = _item_lines_for_customer(store, name_l, book=book)
    last_date = max((i["date"] for i in items if i["date"]), default=None)
    last_order = []
    if last_date:
        for i in items:
            if i["date"] == last_date and i["name"]:
                last_order.append({
                    "name": i["name"],
                    "qty": i["qty"],
                    "rate": i["rate"],
                    "amount": (i["qty"] or 0) * (i["rate"] or 0),
                    "date_label": _fmt_day(i["date"]),
                })
    last_names = {x["name"] for x in last_order}
    if book is not None:
        stock = book.get("stock_qty") or {}
    else:
        stock = {}
        for row in store.rows_of_type("stock"):
            fields = row.get("fields") or {}
            n = clean_text(fields.get("Item Name"))
            if n:
                stock[n.lower()] = number_(fields.get("Qty"))
    for item in last_order:
        item["item_uk"] = account_uk(item["name"]) if item["name"].lower() in stock else ""
    bounds = _period_bounds(as_of, sm)
    periods = {}
    for key, (start, end, label) in bounds.items():
        periods[key] = {
            "id": key,
            "label": label,
            "items": _rank_items(items, start, end, as_of, stock),
        }
    year_items = {r["name"]: r for r in periods["this_year"]["items"]}
    all_items = periods["all"]["items"]
    by_name = {r["name"]: r for r in all_items}
    suggested = []
    seen = set()

    def add_sug(row, reason):
        if not row or not row.get("name") or row["name"] in seen or not _in_stock(stock, row["name"]):
            return
        seen.add(row["name"])
        suggested.append({
            "name": row["name"],
            "qty": row.get("qty") or 0,
            "amount": row.get("amount") or 0,
            "reason": reason,
            "item_uk": row.get("item_uk") or (account_uk(row["name"]) if row["name"].lower() in stock else ""),
        })

    for row in all_items:
        gap = row.get("avg_gap_days") or 0
        if row.get("times", 0) >= 2 and gap and row.get("age_days", 0) >= max(14, int(gap * 1.3)):
            add_sug(row, "Usually every about %s days, last bought %s days ago." % (gap, row.get("age_days")))
        if len(suggested) >= 5:
            break
    for row in all_items:
        if row["name"] in last_names:
            continue
        if row.get("times", 0) >= 2:
            add_sug(row, "Often bought, missing from the last order.")
        if len(suggested) >= 8:
            break
    for row in periods["last_year"]["items"][:8]:
        now = year_items.get(row["name"])
        if not now or now["qty"] < row["qty"] * 0.4:
            add_sug(row, "Bought a lot last year, quiet this year.")
        if len(suggested) >= 8:
            break
    for item in last_order:
        row = by_name.get(item["name"]) or item
        add_sug(row, "On the last order.")
        if len(suggested) >= 8:
            break
    for row in (periods["this_year"]["items"] or all_items):
        add_sug(row, "Bought this year." if row["name"] in year_items else "Bought before.")
        if len(suggested) >= 8:
            break
    usual = [r["name"] for r in periods["this_year"]["items"][:5]] or [r["name"] for r in all_items[:5]]
    period_order = ("this_month", "last_month", "last_3m", "this_year", "last_year", "all")
    default_period = next((key for key in period_order if periods[key]["items"]), "all")
    return {
        "last_order_date": _fmt_day(last_date),
        "last_order": last_order,
        "periods": periods,
        "suggested": suggested[:8],
        "usual": usual,
        "has_item_rows": bool(items),
        "default_period": default_period,
    }


def _health_label(status):
    if status == "urgent":
        return "Urgent"
    if status == "followup":
        return "Follow up"
    if status == "credit":
        return "Advance"
    return "On track"


def _insight(name, due, status, buckets, ytd_sales, ytd_collection, last_sale_label, last_sale, as_of, buying):
    health = _health_label(status)
    due_txt = money(due)
    if status == "credit":
        money_bit = "Advance %s." % money(abs(due) if due else 0)
    elif due > 0:
        from vay.settlement import BUCKET_LABELS
        oldest = "0–15"
        for key in ("d90", "d60_90", "d45_60", "d30_45", "d15_30", "d0_15"):
            if (buckets or {}).get(key):
                oldest = BUCKET_LABELS.get(key) or key
                break
        money_bit = "Due %s, mostly %s days." % (due_txt, oldest)
    else:
        money_bit = "Nothing due."
    year_bit = "This year sales %s, collected %s." % (money(ytd_sales), money(ytd_collection))
    usual = buying.get("usual") or []
    buy_bit = ""
    if usual:
        buy_bit = "Usually buys %s." % ", ".join(usual[:3])
    elif last_sale_label:
        buy_bit = "Last sale %s." % last_sale_label
    else:
        buy_bit = "No sales yet."
    sug = buying.get("suggested") or []
    next_bit = ""
    if sug:
        next_bit = "Suggest %s." % ", ".join(s["name"] for s in sug[:3])
    elif due > 0 and status in ("urgent", "followup"):
        next_bit = "Call this week about the amount due."
    headline = " ".join([p for p in ("%s · %s" % (name, health), money_bit, year_bit, buy_bit, next_bit) if p])
    action = "Collect now." if status == "urgent" else ("Follow up on due." if status == "followup" else ("Ready for the next order." if usual else "Keep in touch."))
    return {
        "headline": headline,
        "health": status,
        "health_label": health,
        "action": action,
        "money_bit": money_bit,
    }


def summarize_customer(store, doc, as_of=None):
    from server.book import load_book
    book = load_book(store)
    as_of = as_of or book["as_of"]
    fields = (doc or {}).get("fields") or {}
    name = clean_text(fields.get("Account Name"))
    name_l = name.lower()
    due = number_(fields.get("Balance"))
    arr = book.get("arr_by_uk", {}).get(account_uk(name).lower()) or book.get("arr_by_uk", {}).get(account_uk((doc or {}).get("uk") or "").lower())
    if arr:
        due = number_((arr.get("fields") or {}).get("Balance"))
    elif name_l in book["arr_due"]:
        due = book["arr_due"][name_l]
    ar_days = number_(fields.get("Days"))
    if arr and (arr.get("fields") or {}).get("Days") not in ("", None):
        ar_days = number_((arr.get("fields") or {}).get("Days"))
    mode = get_settlement_mode(store)
    bands = get_aging_bands(store)
    sm = _fy_month(store, book)
    act = _activity(store, name_l, as_of, book=book, bands=bands, start_month=sm)
    invoices = _group_sales_invoices(_rows_for_name(store, "sales", name_l, book=book), start_month=sm)
    opening_dt = _opening_from_invoices(invoices, as_of, sm)
    receipts = _receipts_for_party(store, name_l, book=book)
    credits = _credits_for_party(store, name_l, book=book)
    open_lines, buckets, opening_amount, opening_dt = _allocate_open(
        invoices, due, as_of, opening_dt, mode=mode, receipts=receipts, bands=bands, credits=credits,
    )
    collection_buckets, settlements, _credit, _rem, _op = _settle_party(
        invoices, receipts, as_of, opening_dt, mode, due, bands=bands, credits=credits, start_month=sm,
    )
    status = _status_from_open(due, open_lines)
    buying = _buying(store, name_l, as_of, book=book, start_month=sm)
    insight = _insight(
        name, due, status, buckets,
        act["ytd_sales"], act["ytd_collection"],
        act["last_sale_label"], act["last_sale"], as_of, buying,
    )
    from server.due_days import _override_map, get_default_due_days, resolve_entity_due_days

    overrides = _override_map(store)
    default_due = get_default_due_days(store)
    ordering = ordering_for_party(
        store,
        name_l,
        as_of,
        party_name=name,
        customer_uk=(doc or {}).get("uk") or account_uk(name),
        group=clean_text(fields.get("Group")),
        rep=act["salesperson"],
        book=book,
        mode=mode,
        bands=bands,
        overrides=overrides,
        default_due=default_due,
        arr_due=due,
    )
    due_meta = resolve_entity_due_days(
        store,
        "customer",
        (doc or {}).get("uk") or account_uk(name),
        group=clean_text(fields.get("Group")),
        rep=act["salesperson"],
    )
    from server.order_check import policy_meta_for_customer

    due_oldest = oldest_due_invoice(open_lines)
    item_lines = _item_lines_for_customer(store, name_l, book=book)
    attach_fy_qty(act.get("fy_years") or [], item_lines, bool(item_lines))
    from server.ar_balance import annotate_customer

    balance = annotate_customer(store, name, tolerance=None)
    base = {
        "uk": (doc or {}).get("uk") or account_uk(name),
        "name": name,
        "group": clean_text(fields.get("Group")),
        "due": due,
        "ar_days": ar_days,
        "due_days": due_meta["due_days"],
        "due_days_source": due_meta["source"],
        "due_days_own": due_meta.get("own"),
        "status": status,
        "ledger_gap": balance["ledger_gap"],
        "ledger_opening": balance.get("ledger_opening") or 0,
        "arr_balance": balance["arr_balance"],
        "balance_diff": balance["balance_diff"],
        "balance_issue": balance["balance_issue"],
        "salesperson": act["salesperson"],
        "last_sale": act["last_sale"],
        "last_sale_label": act["last_sale_label"],
        "last_collection": act["last_collection"],
        "last_collection_label": act["last_collection_label"],
        "ytd_collection": act["ytd_collection"],
        "ytd_sales": act["ytd_sales"],
        "invoices_waiting": len(open_lines),
        "opening_balance": opening_amount,
        "opening_date": _iso(opening_dt),
        "opening_date_label": _fmt_day(opening_dt),
        "open_invoices": open_lines,
        "oldest_due_age": due_oldest["age_days"],
        "oldest_due_kind": due_oldest["kind"],
        "oldest_due_what": due_oldest["what"],
        "owe_buckets": buckets,
        "due_buckets": buckets,
        "collection_buckets": collection_buckets,
        "settlements": settlements,
        "settlement_mode": mode,
        "aging_bands": bands,
        "ordering": ordering,
        "ordered_overdue": bool((ordering.get("badge") or {}).get("current_month") or (ordering.get("badge") or {}).get("current_fy")),
        "sales_mix": act["sales_mix"],
        "fy_years": act.get("fy_years") or [],
        "ar_mismatch": ar_mismatch_for_party(store, name_l, due, as_of, book=book),
        "activity": act["events"],
        "activity_kinds": list_activity_kinds(store),
        "assignees": list_activity_assignees(store),
        "salespeople": _salespeople(store, extra=[act["salesperson"]], book=book),
        "buying": buying,
        "insight": insight,
        "as_of": _iso(as_of),
        "as_of_label": _fmt_day(as_of),
        "fiscal_year_start_month": sm,
        "credit": due < 0,
        "health_label": insight.get("health_label"),
    }
    base.update(policy_meta_for_customer(store, base))
    _stamp_settlement_party(base.get("settlements"), base.get("name"), base.get("uk"))
    return base


_STATUS_LABELS = {
    "urgent": "Urgent",
    "followup": "Follow up",
    "credit": "Advance",
    "ontrack": "On track",
}
_STATUS_IDS = {
    "urgent": "urgent",
    "followup": "followup",
    "follow up": "followup",
    "credit": "credit",
    "advance": "credit",
    "ontrack": "ontrack",
    "on track": "ontrack",
}


def _eq(value, want):
    if not clean_text(want):
        return True
    return clean_text(value).lower() == clean_text(want).lower()


def _status_label(status):
    return _STATUS_LABELS.get(status, status or "")


def _status_id(value):
    return _STATUS_IDS.get(clean_text(value).lower(), clean_text(value).lower())


_DIR_VER = 5


def _directory_ready(cached):
    if not cached or cached.get("ver") != _DIR_VER:
        return False
    rows = cached.get("rows") or []
    return not rows or (
        "collection_buckets" in rows[0]
        and ("d0_15" in rows[0] or "owe_buckets" in rows[0])
        and "ordered_overdue" in rows[0]
    )


def customer_directory_rows(store):
    from server.book import load_book
    book = load_book(store)
    cached = book.get("directory")
    if _directory_ready(cached):
        return cached
    book.pop("directory", None)
    as_of = book["as_of"]
    last_sale = {}
    last_rep = {}
    last_label = {}
    sales_by_party = book["sales_by_party"]
    for name_l, sale_rows in sales_by_party.items():
        for row in sale_rows:
            fields = row.get("fields") or {}
            d = parse_date(fields.get("Date"))
            if not d:
                continue
            prev = last_sale.get(name_l)
            if not prev or d > prev:
                last_sale[name_l] = d
                last_rep[name_l] = clean_text(fields.get("Sales Rep"))
                last_label[name_l] = _fmt_day(d)
    arr_due = book["arr_due"]
    mode = get_settlement_mode(store)
    bands = get_aging_bands(store)
    from server.due_days import _override_map, get_default_due_days

    overrides = _override_map(store)
    default_due = get_default_due_days(store)
    receipts_by_party = book.get("receipts_by_party") or {}
    sm = _fy_month(store, book)
    rows = []
    for doc in book["customers"]:
        fields = (doc or {}).get("fields") or {}
        name = clean_text(fields.get("Account Name"))
        name_l = name.lower()
        due = arr_due[name_l] if name_l in arr_due else number_(fields.get("Balance"))
        group_name = clean_text(fields.get("Group"))
        salesperson = last_rep.get(name_l) or ""
        sale_d = last_sale.get(name_l)
        invoices = _group_sales_invoices(sales_by_party.get(name_l) or [], start_month=sm)
        opening_dt = _opening_from_invoices(invoices, as_of, sm)
        receipt_rows = []
        for row in receipts_by_party.get(name_l) or []:
            fields_r = row.get("fields") or {}
            d = parse_date(fields_r.get("Date"))
            if not d:
                continue
            amount = number_(fields_r.get("Amount"))
            if amount <= 0:
                continue
            receipt_rows.append({
                "date": d,
                "amount": amount,
                "invoice": clean_text(
                    fields_r.get("Invoice No")
                    or fields_r.get("Invoice")
                    or fields_r.get("Invoice Number")
                    or ""
                ),
            })
        credit_rows = _credits_for_party(store, name_l, book=book)
        open_lines, buckets, _opening, _opened = _allocate_open(
            invoices,
            due,
            as_of,
            opening_dt,
            mode=mode,
            receipts=receipt_rows,
            bands=bands,
            credits=credit_rows,
        )
        collection_buckets, _a, _c, _rem, _op = allocate_collections(
            invoices, receipt_rows, as_of, opening_dt=opening_dt, mode=mode, due=due, bands=bands,
            credits=credit_rows,
        )
        status = _status_from_open(due, open_lines)
        flat_owe = flatten_owe(buckets)
        flat_col = flatten_collection(collection_buckets)
        cust_uk = (doc or {}).get("uk") or account_uk(name)
        ordering = ordering_for_party(
            store,
            name_l,
            as_of,
            party_name=name,
            customer_uk=cust_uk,
            group=group_name,
            rep=salesperson,
            book=book,
            mode=mode,
            bands=bands,
            overrides=overrides,
            default_due=default_due,
            arr_due=due,
        )
        badge = ordering.get("badge") or {}
        ordered_overdue = bool(badge.get("current_month") or badge.get("current_fy"))
        from server.order_check import read_customer_flags

        flags = read_customer_flags((doc or {}).get("fields") or {})
        rows.append({
            "uk": cust_uk,
            "name": name,
            "party": name,
            "group": group_name,
            "due": due,
            **flat_owe,
            **flat_col,
            "owe_buckets": buckets,
            "collection_buckets": collection_buckets,
            "status": status,
            "status_label": _status_label(status),
            "salesperson": salesperson,
            "rep": salesperson,
            "last_sale": _iso(sale_d),
            "last_sale_label": last_label.get(name_l) or "",
            "credit": due < 0,
            "due_days": ordering.get("due_days"),
            "due_days_source": ordering.get("due_days_source"),
            "ordering_badge": badge,
            "ordered_overdue": ordered_overdue,
            "premium": flags["premium"],
            "blacklisted": flags["blacklisted"],
        })
    counts = {
        "urgent": 0,
        "followup": 0,
        "credit": 0,
        "ontrack": 0,
        "due_total": 0.0,
    }
    attention = []
    for row in rows:
        st = row.get("status") or "ontrack"
        if st in counts:
            counts[st] += 1
        due_amt = row.get("due") or 0
        if due_amt > 0:
            counts["due_total"] += due_amt
        if st in ("urgent", "followup"):
            attention.append(row)
    attention.sort(key=lambda r: (0 if r.get("status") == "urgent" else 1, -(r.get("due") or 0)))
    options = {
        "party": sorted({r["name"] for r in rows if r["name"]}, key=str.lower),
        "group": sorted({r["group"] for r in rows if r["group"]}, key=str.lower),
        "rep": sorted({r["salesperson"] for r in rows if r["salesperson"]}, key=str.lower),
        "status": [_status_label(s) for s in ("urgent", "followup", "credit", "ontrack") if any(r["status"] == s for r in rows)],
    }
    data = {
        "ver": _DIR_VER,
        "rows": rows,
        "counts": counts,
        "attention": attention[:5],
        "options": options,
        "as_of": as_of,
    }
    book["directory"] = data
    return data


def list_customers(store, params):
    q = clean_text(params.get("q") or "").lower()
    party = clean_text(params.get("party") or params.get("name"))
    group = clean_text(params.get("group"))
    rep = clean_text(params.get("rep"))
    status_want = _status_id(params.get("status"))
    try:
        page = max(1, int(params.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    limit = 50
    data = customer_directory_rows(store)
    rows = data["rows"]
    if rows and "d0_15" not in rows[0]:
        book = getattr(store, "_360_book", None)
        if book is not None:
            book.pop("directory", None)
        data = customer_directory_rows(store)
        rows = data["rows"]
    options = dict(data["options"])
    options["balance_issue"] = ["Mismatch", "Missing ARR"]
    from server.ar_balance import annotate_customer, party_ledgers
    from server.org_policy import get_org_policy

    ledgers = party_ledgers(store)
    tolerance = get_org_policy(store)["ar_balance_tolerance"]
    enriched = []
    for row in rows:
        item = dict(row)
        item.update(annotate_customer(store, row.get("name"), ledgers=ledgers, tolerance=tolerance))
        enriched.append(item)
    rows = enriched
    filtered = []
    flag_want = clean_text(params.get("balance_issue")).lower()
    flag_code = {
        "1": "",
        "true": "",
        "yes": "",
        "balance issues": "",
        "mismatch": "mismatch",
        "mismatched": "mismatch",
        "missing arr": "missing_arr",
        "missing_arr": "missing_arr",
    }.get(flag_want, flag_want)
    for row in rows:
        if q and q not in row["name"].lower() and q not in row["group"].lower() and q not in row["salesperson"].lower():
            continue
        if not _eq(row["name"], party):
            continue
        if not _eq(row["group"], group):
            continue
        if not _eq(row["salesperson"], rep):
            continue
        if status_want and row["status"] != status_want:
            continue
        if flag_want:
            issue = row.get("balance_issue") or ""
            if flag_code and issue != flag_code:
                continue
            if not flag_code and not issue:
                continue
        filtered.append(row)
    requested = clean_text(params.get("sort") or "due").lower()
    key = requested
    if key in ("ar_diff", "ar diff", "ardiff"):
        key = "balance_diff"
    if flag_code == "mismatch" and key == "due":
        key = "balance_diff"
    if key in ("party", "customer"):
        key = "name"
    if key in ("rep",):
        key = "salesperson"
    if key == "status":
        key = "status_label"
    if key in ("0-15", "0–15"):
        key = "d0_15"
    if key in ("15-30", "15–30", "16-30", "16–30"):
        key = "d15_30"
    if key in ("30-45", "30–45"):
        key = "d30_45"
    if key in ("45-60", "45–60", "31-60", "31–60"):
        key = "d45_60"
    if key in ("60-90", "60–90"):
        key = "d60_90"
    if key in ("90+", "d90_plus", "60+", "d60_plus", "d60"):
        key = "d90"
    direction = clean_text(params.get("dir") or "desc").lower()
    if direction not in ("asc", "desc"):
        direction = "desc"
    numeric = {"due", "balance_diff", "ledger_gap", *BUCKET_KEYS, *("c_" + k for k in BUCKET_KEYS)}
    def sort_val(row):
        if key == "balance_diff":
            val = row.get("balance_diff")
            if val is None:
                return float("-inf") if direction == "desc" else float("inf")
            return abs(val)
        val = row.get(key)
        if val is None:
            return float("-inf") if key in numeric else ""
        if isinstance(val, (int, float)):
            return val
        return str(val).lower()
    filtered.sort(key=sort_val, reverse=(direction == "desc"))
    total = len(filtered)
    start = (page - 1) * limit
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "customers": filtered[start:start + limit],
        "options": options,
        "sort": clean_text(params.get("sort") or "due"),
        "dir": direction,
        "counts": data["counts"],
        "attention": data["attention"],
    }


def _customer_doc(store, uk, book=None):
    uk = account_uk(uk)
    book = book or getattr(store, "_360_book", None)
    if book:
        for row in book.get("customers") or []:
            if (row.get("uk") or "").lower() == uk.lower():
                return row
            if account_uk((row.get("fields") or {}).get("Account Name")).lower() == uk.lower():
                return row
    doc = store.find_row("customer", uk)
    if doc:
        return doc
    for row in store.rows_of_type("customer"):
        if account_uk((row.get("fields") or {}).get("Account Name")).lower() == uk.lower():
            return row
    return None


def ensure_detail_settlements(store, detail, book=None, force=False):
    """Attach settlements (overall / FY / month) during 360 snapshot build."""
    if not detail:
        return detail
    existing = detail.get("settlements")
    if not force and settlements_ready(existing):
        return detail
    from server.book import load_book
    book = book or load_book(store)
    as_of = book.get("as_of") or book["as_of"]
    name = clean_text(detail.get("name"))
    name_l = name.lower()
    due = number_(detail.get("due"))
    mode = detail.get("settlement_mode") or get_settlement_mode(store)
    bands = detail.get("aging_bands") or get_aging_bands(store)
    sm = _fy_month(store, book, detail.get("fiscal_year_start_month"))
    invoices = _group_sales_invoices(_rows_for_name(store, "sales", name_l, book=book), start_month=sm)
    opening_dt = _opening_from_invoices(invoices, as_of, sm)
    receipts = _receipts_for_party(store, name_l, book=book)
    credits = _credits_for_party(store, name_l, book=book)
    collection_buckets, settlements, _credit, _rem, _op = _settle_party(
        invoices, receipts, as_of, opening_dt, mode, due, bands=bands,
        credits=credits, start_month=sm,
    )
    out = detail
    out["collection_buckets"] = collection_buckets
    out["settlements"] = _stamp_settlement_party(settlements, name, detail.get("uk") or "")
    out["settlement_mode"] = normalize_mode(mode)
    out["aging_bands"] = bands
    out["fiscal_year_start_month"] = sm
    return out


def get_customer(store, uk):
    from server.book import load_book
    book = load_book(store)
    doc = _customer_doc(store, uk, book=book)
    if not doc:
        return None
    detail = summarize_customer(store, doc)
    if not detail:
        return None
    from server.repurchase import attach_repurchase
    return attach_repurchase(store, detail, party=detail.get("uk") or detail.get("name"))


def _safe_pdf(text):
    return str(text or "")


def money(n):
    try:
        return "{:,.2f}".format(float(n or 0))
    except (TypeError, ValueError):
        return "0.00"


def _pdf_family(pdf):
    pairs = [
        (r"C:\Windows\Fonts\Nirmala.ttf", r"C:\Windows\Fonts\NirmalaB.ttf"),
        (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for regular, bold in pairs:
        if os.path.isfile(regular):
            pdf.add_font("Ui", "", regular)
            pdf.add_font("Ui", "B", bold if os.path.isfile(bold) else regular)
            return "Ui"
    return "Helvetica"


def _pdf_line(pdf, family, text, size=10, bold=False, h=6, color=(28, 25, 23)):
    pdf.set_text_color(*color)
    pdf.set_font(family, "B" if bold else "", size)
    pdf.multi_cell(0, h, _safe_pdf(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _pdf_table(pdf, family, headers, rows, widths):
    pdf.set_font(family, "B", 9)
    pdf.set_fill_color(15, 61, 46)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers):
        pdf.cell(widths[i], 7, _safe_pdf(h), border=0, fill=True)
    pdf.ln()
    pdf.set_text_color(28, 25, 23)
    pdf.set_font(family, "", 9)
    fill = False
    for row in rows:
        pdf.set_fill_color(248, 250, 249) if fill else pdf.set_fill_color(255, 255, 255)
        for i, val in enumerate(row):
            pdf.cell(widths[i], 6, _safe_pdf(val), border=0, fill=True)
        pdf.ln()
        fill = not fill
    pdf.set_fill_color(255, 255, 255)


def _normalize_pdf_view(view):
    key = str(view or "rep").strip().lower()
    if key == "reminder":
        return "reminder"
    if key in ("customer", "statement", "share"):
        return "customer"
    return "rep"


def _pdf_pct(part, whole):
    try:
        w = float(whole or 0)
        if w <= 0:
            return "—"
        return "%.0f%%" % (100.0 * float(part or 0) / w)
    except (TypeError, ValueError):
        return "—"


def _pdf_delta(cur, prev):
    try:
        c, p = float(cur or 0), float(prev or 0)
    except (TypeError, ValueError):
        return "—"
    if p == 0:
        return "new" if c else "—"
    return "%+.0f%%" % (100.0 * (c - p) / abs(p))


def _pdf_days_since(as_of_iso, when_iso):
    a = parse_date(as_of_iso)
    b = parse_date(when_iso)
    if not a or not b:
        return None
    return max(0, (a.date() - b.date()).days if hasattr(a, "date") else (a - b).days)


def _pdf_header(pdf, family, title, subtitle, *, fill=(15, 61, 46), badge=""):
    pdf.set_fill_color(*fill)
    pdf.rect(0, 0, 210, 26 if badge else 22, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(family, "B", 12)
    pdf.set_xy(16, 5)
    pdf.cell(120, 7, title, new_x=XPos.RIGHT, new_y=YPos.TOP)
    if badge:
        pdf.set_font(family, "B", 9)
        pdf.cell(0, 7, badge, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    else:
        pdf.ln(7)
    pdf.set_font(family, "", 9)
    pdf.set_x(16)
    pdf.cell(0, 5, _safe_pdf(subtitle), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_y(30 if badge else 28)
    pdf.set_text_color(28, 25, 23)


def _pdf_kpi_row(pdf, family, cells):
    """cells: list of (label, value) — up to 4 across."""
    n = max(1, min(4, len(cells)))
    w = 178.0 / n
    y0 = pdf.get_y()
    for i, (label, value) in enumerate(cells[:n]):
        x = 16 + i * w
        pdf.set_xy(x, y0)
        pdf.set_fill_color(248, 250, 249)
        pdf.rect(x, y0, w - 2, 16, "F")
        pdf.set_xy(x + 2, y0 + 1)
        pdf.set_font(family, "", 7)
        pdf.set_text_color(120, 113, 108)
        pdf.cell(w - 6, 4, _safe_pdf(label), new_x=XPos.LEFT, new_y=YPos.NEXT)
        pdf.set_x(x + 2)
        pdf.set_font(family, "B", 10)
        pdf.set_text_color(28, 25, 23)
        pdf.cell(w - 6, 8, _safe_pdf(value)[:22], new_x=XPos.LMARGIN, new_y=YPos.TOP)
    pdf.set_y(y0 + 18)


def _customer_statement_pdf(pdf, family, detail):
    _pdf_header(
        pdf, family,
        "Vay  ·  Account statement",
        detail.get("as_of_label") or "",
        fill=(15, 61, 46),
    )
    _pdf_line(pdf, family, detail.get("name") or "Customer", 18, True, 9)
    if detail.get("group"):
        _pdf_line(pdf, family, detail.get("group") or "", 10, False, 5, (120, 113, 108))
    due_label = "Advance" if detail.get("credit") else "Amount due"
    due_value = abs(detail.get("due") or 0) if detail.get("credit") else detail.get("due")
    _pdf_line(pdf, family, "%s  %s" % (due_label, money(due_value)), 16, True, 9)
    waiting = detail.get("invoices_waiting")
    if waiting:
        _pdf_line(pdf, family, "%s open invoice%s" % (waiting, "" if waiting == 1 else "s"), 10, False, 5, (120, 113, 108))
    pdf.ln(3)
    _pdf_line(pdf, family, "Outstanding by age", 12, True, 7)
    buckets = detail.get("owe_buckets") or {}
    _pdf_table(pdf, family, ["0–15", "15–30", "30–45", "45–60", "60–90", "90+"], [[
        money(buckets.get("d0_15")), money(buckets.get("d15_30")),
        money(buckets.get("d30_45")), money(buckets.get("d45_60")),
        money(buckets.get("d60_90")), money(buckets.get("d90")),
    ]], [30, 30, 30, 30, 29, 29])
    opens = detail.get("open_invoices") or []
    if opens:
        pdf.ln(3)
        _pdf_line(pdf, family, "Open invoices", 12, True, 7)
        _pdf_table(
            pdf, family,
            ["Date", "Invoice", "What", "Still due", "Age"],
            [[
                x.get("date_label") or "",
                (x.get("invoice") or "—")[:16],
                x.get("what") or "",
                money(x.get("due")),
                "%s days" % x.get("age_days"),
            ] for x in opens[:20]],
            [32, 36, 42, 36, 32],
        )
    pdf.ln(6)
    _pdf_line(
        pdf, family,
        "For your records. Generated by Vay.",
        8, False, 5, (120, 113, 108),
    )


def _collection_reminder_pdf(pdf, family, detail):
    reminder = detail.get("collection_reminder") or {}
    pdf.ln(4)
    _pdf_line(pdf, family, "Payment reminder", 12, True, 7)
    due_label = "Advance" if detail.get("credit") else "Amount due"
    due_value = abs(detail.get("due") or 0) if detail.get("credit") else detail.get("due")
    _pdf_line(pdf, family, "%s  %s" % (due_label, money(due_value)), 11, True, 6)
    promises = reminder.get("promises") or []
    if promises:
        _pdf_table(
            pdf, family,
            ["Promised", "Date", "Remaining", "Status"],
            [[
                money(row.get("amount")),
                row.get("promised_on") or "",
                money(row.get("remaining")),
                row.get("message") or (row.get("payment_status") or "").replace("_", " "),
            ] for row in promises[:8]],
            [40, 36, 40, 62],
        )
    else:
        _pdf_line(pdf, family, "No open payment promise is recorded.", 10, False, 6)
    if reminder.get("next_step"):
        _pdf_line(pdf, family, "Next step  " + reminder.get("next_step"), 10, True, 6)
    if reminder.get("next_follow_up"):
        _pdf_line(pdf, family, "Follow up on  " + reminder.get("next_follow_up"), 10, False, 6)
    pdf.ln(2)
    _pdf_line(
        pdf, family,
        "Review this reminder before sending it. Vay does not send it.",
        8, False, 5, (120, 113, 108),
    )


def _rep_brief_pdf(pdf, family, detail, *, title="Vay  ·  Sales brief"):
    _pdf_header(
        pdf, family,
        title,
        detail.get("as_of_label") or "",
        fill=(30, 41, 59),
        badge="INTERNAL",
    )
    _pdf_line(pdf, family, detail.get("name") or "Customer", 18, True, 9)
    bits = [detail.get("group") or "", detail.get("salesperson") or "", detail.get("health_label") or ""]
    if detail.get("customer_count"):
        bits.insert(0, "%s customers" % detail.get("customer_count"))
    _pdf_line(pdf, family, "  ·  ".join([b for b in bits if b]), 10, False, 5, (120, 113, 108))

    flags = []
    if detail.get("health_label"):
        flags.append(detail.get("health_label"))
    if detail.get("ordered_overdue"):
        flags.append("Ordered overdue")
    if detail.get("premium"):
        flags.append("Premium")
    if detail.get("blacklisted"):
        flags.append("Blacklisted")
    if flags:
        pdf.set_fill_color(254, 243, 199) if detail.get("ordered_overdue") or detail.get("blacklisted") or detail.get("status") == "urgent" else pdf.set_fill_color(241, 245, 249)
        pdf.set_x(16)
        pdf.set_font(family, "B", 9)
        pdf.set_text_color(28, 25, 23)
        pdf.multi_cell(178, 6, _safe_pdf("  ·  ".join(flags)), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

    insight = detail.get("insight") or {}
    if insight.get("headline"):
        pdf.set_fill_color(240, 253, 244)
        pdf.set_x(16)
        pdf.set_font(family, "", 10)
        pdf.set_text_color(28, 25, 23)
        pdf.multi_cell(178, 6, _safe_pdf(insight.get("headline")), fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)
    if insight.get("action"):
        _pdf_line(pdf, family, "Next: " + insight.get("action"), 10, True, 6, (31, 107, 74))

    due_label = "Advance" if detail.get("credit") else "Amount due"
    due_value = abs(detail.get("due") or 0) if detail.get("credit") else detail.get("due")
    days_since_sale = _pdf_days_since(detail.get("as_of"), detail.get("last_sale"))
    _pdf_line(pdf, family, "Performance", 12, True, 7)
    _pdf_kpi_row(pdf, family, [
        (due_label, money(due_value)),
        ("YTD sales", money(detail.get("ytd_sales"))),
        ("YTD collected", money(detail.get("ytd_collection"))),
        ("Open invoices", str(detail.get("invoices_waiting") or 0)),
    ])
    _pdf_kpi_row(pdf, family, [
        ("Last sale", detail.get("last_sale_label") or "—"),
        ("Last collection", detail.get("last_collection_label") or "—"),
        ("Days since sale", "—" if days_since_sale is None else str(days_since_sale)),
        ("Credit days", str(detail.get("due_days") if detail.get("due_days") is not None else "—")),
    ])

    ytd_sales = float(detail.get("ytd_sales") or 0)
    ytd_col = float(detail.get("ytd_collection") or 0)
    gap = ytd_sales - ytd_col
    collect_rate = _pdf_pct(ytd_col, ytd_sales)
    _pdf_line(
        pdf, family,
        "YTD collection rate %s  ·  Uncollected gap %s" % (collect_rate, money(gap)),
        9, False, 5, (120, 113, 108),
    )

    fys = detail.get("fy_years") or []
    if len(fys) >= 1:
        pdf.ln(1)
        _pdf_line(pdf, family, "Year-on-year", 12, True, 7)
        cur, prev = fys[0], (fys[1] if len(fys) > 1 else None)
        rows = [[
            cur.get("label") or "This FY",
            money(cur.get("sales")),
            money(cur.get("collection")),
            _pdf_pct(cur.get("collection"), cur.get("sales")),
            "",
        ]]
        if prev:
            rows.append([
                prev.get("label") or "Prior FY",
                money(prev.get("sales")),
                money(prev.get("collection")),
                _pdf_pct(prev.get("collection"), prev.get("sales")),
                "Sales %s  Coll %s" % (_pdf_delta(cur.get("sales"), prev.get("sales")), _pdf_delta(cur.get("collection"), prev.get("collection"))),
            ])
        _pdf_table(
            pdf, family,
            ["Year", "Sales", "Collection", "Rate", "vs prior"],
            rows,
            [36, 34, 34, 22, 52],
        )

    ordering = detail.get("ordering") or {}
    overall = ordering.get("overall") or {}
    by_fy = ordering.get("by_fy") or []
    fy_ord = None
    if by_fy:
        as_of_d = parse_date(detail.get("as_of") or "")
        if as_of_d:
            fy_start = _iso(fiscal_year_start(as_of_d, detail.get("fiscal_year_start_month")))
            fy_ord = next((y for y in by_fy if y.get("key") == fy_start), None)
        if not fy_ord:
            fy_ord = next((y for y in by_fy if (y.get("flagged_count") or 0) > 0), by_fy[0])
    pdf.ln(2)
    _pdf_line(pdf, family, "Ordering discipline", 12, True, 7)
    o_sales = overall.get("sales_value") or 0
    o_flag = overall.get("flagged_value") or 0
    lines = [
        "All time  %s of %s sales while overdue (%s)  ·  %s orders flagged"
        % (money(o_flag), money(o_sales), _pdf_pct(o_flag, o_sales), overall.get("flagged_count") or 0)
    ]
    if fy_ord:
        lines.append(
            "%s  %s of %s (%s)  ·  %s flagged"
            % (
                fy_ord.get("label") or "This FY",
                money(fy_ord.get("flagged_value")),
                money(fy_ord.get("sales_value")),
                _pdf_pct(fy_ord.get("flagged_value"), fy_ord.get("sales_value")),
                fy_ord.get("flagged_count") or 0,
            )
        )
    for line in lines:
        _pdf_line(pdf, family, line, 9, False, 5, (120, 113, 108))

    pdf.ln(2)
    _pdf_line(pdf, family, "What they owe", 12, True, 7)
    buckets = detail.get("owe_buckets") or {}
    _pdf_table(pdf, family, ["0–15", "15–30", "30–45", "45–60", "60–90", "90+"], [[
        money(buckets.get("d0_15")), money(buckets.get("d15_30")),
        money(buckets.get("d30_45")), money(buckets.get("d45_60")),
        money(buckets.get("d60_90")), money(buckets.get("d90")),
    ]], [30, 30, 30, 30, 29, 29])

    col = (detail.get("settlements") or {}).get("overall", {}).get("buckets") or detail.get("collection_buckets") or {}
    if any(col.get(k) for k in BUCKET_KEYS):
        pdf.ln(2)
        _pdf_line(pdf, family, "Settlements by age", 12, True, 7)
        overall_total = (detail.get("settlements") or {}).get("overall", {}).get("total")
        old_share = 0.0
        try:
            total_s = sum(float(col.get(k) or 0) for k in BUCKET_KEYS)
            old_share = (float(col.get("d60_90") or 0) + float(col.get("d90") or 0)) / total_s if total_s else 0
        except (TypeError, ValueError, ZeroDivisionError):
            old_share = 0
        bits_s = []
        if overall_total:
            bits_s.append("Overall %s" % money(overall_total))
        if old_share:
            bits_s.append("60+ days %.0f%%" % (100 * old_share))
        if bits_s:
            _pdf_line(pdf, family, "  ·  ".join(bits_s), 9, False, 5, (120, 113, 108))
        _pdf_table(pdf, family, ["0–15", "15–30", "30–45", "45–60", "60–90", "90+"], [[
            money(col.get("d0_15")), money(col.get("d15_30")),
            money(col.get("d30_45")), money(col.get("d45_60")),
            money(col.get("d60_90")), money(col.get("d90")),
        ]], [30, 30, 30, 30, 29, 29])

    opens = detail.get("open_invoices") or []
    if opens:
        pdf.ln(2)
        _pdf_line(pdf, family, "Open amounts", 12, True, 7)
        has_party = any(x.get("party") for x in opens[:15])
        if has_party:
            _pdf_table(
                pdf, family,
                ["Date", "Customer", "Invoice", "Still due", "Age"],
                [[
                    x.get("date_label") or "",
                    (x.get("party") or "—")[:18],
                    (x.get("invoice") or "—")[:14],
                    money(x.get("due")),
                    "%s days" % x.get("age_days"),
                ] for x in opens[:15]],
                [28, 44, 36, 36, 34],
            )
        else:
            _pdf_table(
                pdf, family,
                ["Date", "Invoice", "What", "Still due", "Age"],
                [[
                    x.get("date_label") or "",
                    (x.get("invoice") or "—")[:16],
                    x.get("what") or "",
                    money(x.get("due")),
                    "%s days" % x.get("age_days"),
                ] for x in opens[:15]],
                [32, 36, 42, 36, 32],
            )

    if len(fys) > 2:
        pdf.ln(2)
        _pdf_line(pdf, family, "Sales and collection by year", 12, True, 7)
        _pdf_table(
            pdf, family,
            ["Year", "Sales", "Collection", "Rate"],
            [[
                y.get("label") or "",
                money(y.get("sales")),
                money(y.get("collection")),
                _pdf_pct(y.get("collection"), y.get("sales")),
            ] for y in fys],
            [50, 44, 44, 40],
        )

    notes = [e for e in (detail.get("activity") or []) if e.get("logged")][:8]
    if notes:
        pdf.ln(2)
        _pdf_line(pdf, family, "Recent notes", 12, True, 7)
        _pdf_table(
            pdf, family,
            ["Date", "Type", "Note"],
            [[
                x.get("date_label") or "",
                (x.get("label") or "")[:22],
                (x.get("note") or "—")[:48],
            ] for x in notes],
            [36, 48, 94],
        )

    buying = detail.get("buying") or {}
    sug = buying.get("suggested") or []
    pdf.ln(2)
    _pdf_line(pdf, family, "Suggest next", 12, True, 7)
    if sug:
        _pdf_table(
            pdf, family,
            ["Item", "Why"],
            [[s.get("name"), s.get("reason") or ""] for s in sug[:6]],
            [55, 123],
        )
    else:
        _pdf_line(pdf, family, "Nothing to suggest yet.", 9, False, 5, (120, 113, 108))

    year_items = ((buying.get("periods") or {}).get("this_year") or {}).get("items") or []
    pdf.ln(2)
    _pdf_line(pdf, family, "Buying this year", 12, True, 7)
    if year_items:
        _pdf_table(
            pdf, family,
            ["Item", "Qty", "Amount", "Times", "Last bought"],
            [[i.get("name"), "{:g}".format(i.get("qty") or 0), money(i.get("amount")), str(i.get("times") or 0), i.get("last_label") or ""] for i in year_items[:12]],
            [62, 22, 32, 22, 40],
        )
    else:
        _pdf_line(pdf, family, "No item lines for this customer. Import item-wise sales with the customer name.", 9, False, 5, (120, 113, 108))


def customer_pdf(detail, view="rep"):
    """Build a customer PDF. view='customer' is shareable; view='rep' is internal."""
    view = _normalize_pdf_view(view)
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(16, 16, 16)
    pdf.add_page()
    family = _pdf_family(pdf)
    if view == "reminder":
        _customer_statement_pdf(pdf, family, detail)
        _collection_reminder_pdf(pdf, family, detail)
    elif view == "customer":
        _customer_statement_pdf(pdf, family, detail)
    else:
        _rep_brief_pdf(pdf, family, detail)
    raw = pdf.output()
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else raw.encode("latin-1")


def entity_brief_pdf(detail, entity="group"):
    """Internal brief PDF for a customer group or sales rep rollup."""
    entity = (entity or "group").lower()
    title = "Vay  ·  Group brief" if entity == "group" else "Vay  ·  Sales rep brief"
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(16, 16, 16)
    pdf.add_page()
    family = _pdf_family(pdf)
    _rep_brief_pdf(pdf, family, detail, title=title)
    raw = pdf.output()
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else raw.encode("latin-1")
