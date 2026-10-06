"""In-memory 360 indexes. Built once per store until rows or report date change."""

from __future__ import annotations

from vay.config import DEFAULT_GROUP, DEFAULT_RECEIPT_REP, DEFAULT_SALES_REP
from vay.credit_notes import credit_party, rep_index, rep_on_or_before, resolve_credit_party
from vay.dates import clean_text, fiscal_year_start, number_, parse_date


def load_book(store):
    book = getattr(store, "_360_book", None)
    if book is None:
        book = build_book(store)
        store._360_book = book
    return book


def build_book(store):
    from server.customers import (
        NOTE_TYPE,
        _as_of,
        _party_from_fields,
        _party_name,
        account_uk,
    )
    from server.invoices import _invoice_no, invoice_scope_key
    from server.items360 import _hold_map, _item_lines_from_rows, _stock_rows_from_docs
    from server.org_policy import get_org_policy

    as_of = _as_of(store)
    start_month = get_org_policy(store)["fiscal_year_start_month"]
    sales = store.rows_of_type("sales")
    receipts = store.rows_of_type("receipt")
    credit_notes = store.rows_of_type("credit_note")
    items = store.rows_of_type("items")
    arr = store.rows_of_type("arr")
    customers = store.rows_of_type("customer")
    stock = store.rows_of_type("stock")
    notes = store.rows_of_type(NOTE_TYPE)
    parties = store.rows_of_type("party")

    sales_by_party = {}
    sales_by_rep = {}
    invoice_to_party = {}
    for row in sales:
        fields = row.get("fields") or {}
        party = (_party_from_fields(fields) or _party_name(fields, "sales")).lower()
        if party:
            sales_by_party.setdefault(party, []).append(row)
        rep = clean_text(fields.get("Sales Rep"))
        if rep:
            sales_by_rep.setdefault(rep.lower(), []).append(row)
        inv = _invoice_no(fields)
        if inv and party:
            invoice_to_party.setdefault(invoice_scope_key(inv, fields.get("Date"), start_month), party)

    rep_pairs = []
    for row in sales:
        fields = row.get("fields") or {}
        rep_pairs.append((
            credit_party(fields) or _party_name(fields, "sales"),
            parse_date(fields.get("Date")),
            fields.get("Sales Rep"),
        ))
    reps_by_party = rep_index(rep_pairs)

    known_parties = set(sales_by_party)
    groups = {}
    for row in list(arr) + list(customers):
        fields = row.get("fields") or {}
        name = clean_text(fields.get("Account Name") or fields.get("Party Name")).lower()
        group = clean_text(fields.get("Group"))
        if name:
            known_parties.add(name)
            if group and group != "NO_GROUP" and name not in groups:
                groups[name] = group

    credit_notes_by_party = {}
    credit_notes_by_rep = {}
    for row in credit_notes:
        fields = row.get("fields") or {}
        raw = (credit_party(fields) or _party_name(fields, "credit_note")).lower()
        party = resolve_credit_party(raw, known_parties)
        note_date = parse_date(fields.get("Date"))
        rep = clean_text(fields.get("Sales Rep")) or rep_on_or_before(reps_by_party, party, note_date) or DEFAULT_SALES_REP
        group = clean_text(fields.get("Group")) or groups.get(party) or DEFAULT_GROUP
        stored = dict(row)
        stored["fields"] = dict(fields)
        stored["fields"]["Sales Rep"] = rep
        stored["fields"]["Group"] = group
        if party:
            credit_notes_by_party.setdefault(party, []).append(stored)
        credit_notes_by_rep.setdefault(rep.lower(), []).append(stored)

    receipts_by_party = {}
    receipts_by_rep = {}
    for row in receipts:
        fields = row.get("fields") or {}
        party = _party_name(fields, "receipt").lower()
        if party:
            receipts_by_party.setdefault(party, []).append(row)
        rep = clean_text(fields.get("Sales Rep")) or DEFAULT_SALES_REP
        if rep == DEFAULT_RECEIPT_REP:
            continue
        receipts_by_rep.setdefault(rep.lower(), []).append(row)

    buying_lines_by_party = {}
    for row in items:
        fields = row.get("fields") or {}
        party = (_party_from_fields(fields) or _party_name(fields, "items")).lower()
        inv = _invoice_no(fields)
        if not party and inv:
            party = invoice_to_party.get(invoice_scope_key(inv, fields.get("Date"), start_month), "")
        if not party:
            continue
        buying_lines_by_party.setdefault(party, []).append({
            "date": parse_date(fields.get("Date")),
            "name": clean_text(fields.get("Item Name")),
            "qty": number_(fields.get("Qty")),
            "rate": number_(fields.get("Rate")),
        })

    group_map = {}
    for row in list(arr) + list(parties) + list(customers):
        fields = row.get("fields") or {}
        name = clean_text(fields.get("Account Name") or fields.get("Party Name")).lower()
        group = clean_text(fields.get("Group"))
        if name and group:
            group_map[name] = group

    item_lines_by_uk = _item_lines_from_rows(items, sales, group_map, start_month=start_month)
    holds, default_min, default_max_days = _hold_map(store)
    from server.item_attrs import attr_map
    stock_rows = _stock_rows_from_docs(stock)
    item_attrs = attr_map(store)

    arr_due = {}
    arr_by_uk = {}
    for row in arr:
        fields = row.get("fields") or {}
        name_l = clean_text(fields.get("Account Name")).lower()
        if name_l:
            arr_due[name_l] = number_(fields.get("Balance"))
            arr_by_uk[account_uk(name_l).lower()] = row
        uk = account_uk(row.get("uk") or "")
        if uk:
            arr_by_uk[uk.lower()] = row

    stock_qty = {}
    for row in stock:
        fields = row.get("fields") or {}
        n = clean_text(fields.get("Item Name"))
        if n:
            stock_qty[n.lower()] = number_(fields.get("Qty"))

    notes_by_party = {}
    for row in notes:
        fields = row.get("fields") or {}
        keys = set()
        party = _party_name(fields).lower()
        if party:
            keys.add(party)
        cust = account_uk(fields.get("customer_uk") or "").lower()
        if cust:
            keys.add(cust)
            keys.add(account_uk(party).lower() if party else cust)
        for key in keys:
            if key:
                notes_by_party.setdefault(key, []).append(row)

    fy = fiscal_year_start(as_of, start_month)
    return {
        "as_of": as_of,
        "fy_start": fy,
        "sales_by_party": sales_by_party,
        "credit_notes_by_party": credit_notes_by_party,
        "credit_notes_by_rep": credit_notes_by_rep,
        "receipts_by_party": receipts_by_party,
        "sales_by_rep": sales_by_rep,
        "receipts_by_rep": receipts_by_rep,
        "buying_lines_by_party": buying_lines_by_party,
        "item_lines_by_uk": item_lines_by_uk,
        "invoice_to_party": invoice_to_party,
        "customers": customers,
        "arr_due": arr_due,
        "arr_by_uk": arr_by_uk,
        "stock_qty": stock_qty,
        "stock_rows": stock_rows,
        "item_attrs": item_attrs,
        "notes_by_party": notes_by_party,
        "group_map": group_map,
        "holds": holds,
        "default_min": default_min,
        "default_max_days": default_max_days,
        "notes": notes,
        "fiscal_year_start_month": start_month,
    }
