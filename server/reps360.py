"""Sales rep 360. Does not feed generate()."""

from __future__ import annotations

from datetime import datetime

from vay.dates import clean_text, fiscal_year_start, fy_label, iter_fiscal_years, normalize_fy_start_month, number_, parse_date

from vay.settlement import BUCKET_KEYS, allocate_collections, empty_buckets, flatten_collection, flatten_owe

from server.customers import (
    ACTIVITY_LABELS,
    _allocate_open,
    _eq,
    _fmt_day,
    _group_sales_invoices,
    _insight,
    _iso,
    _fy_month,
    _opening_from_invoices,
    _status_id,
    _status_label,
    account_uk,
    build_settlements_summary,
    customer_directory_rows,
    get_aging_bands,
    get_settlement_mode,
    merge_ordering_summaries,
    ordering_for_party,
    attach_party_fy_qty,
)
from server.groups360 import (
    COL_KEYS,
    add_member_to_rollup,
    buying_for_names,
    finish_rollups,
    match_uk,
    page_limit,
    rollup_status,
    sort_rows,
    sum_collection_buckets,
    sum_due_buckets,
    _rollup_slot,
)


def _rep_books(store, as_of=None):
    from server.book import load_book
    src = load_book(store)
    cached = src.get("rep_books")
    if cached is not None:
        return cached
    as_of = as_of or src["as_of"]
    fy = src.get("fy_start") or fiscal_year_start(as_of, src.get("fiscal_year_start_month"))
    books = {}

    def book(name):
        key = name.lower()
        rec = books.get(key)
        if rec is None:
            rec = {
                "name": name,
                "sales": [],
                "receipts": [],
                "credits": [],
                "ytd_sales": 0.0,
                "ytd_collection": 0.0,
                "last_sale": None,
                "last_collection": None,
            }
            books[key] = rec
        else:
            rec["name"] = name or rec["name"]
        return rec

    for key, rows in (src.get("sales_by_rep") or {}).items():
        for row in rows:
            fields = row.get("fields") or {}
            name = clean_text(fields.get("Sales Rep")) or key
            rec = book(name)
            d = parse_date(fields.get("Date"))
            if not d:
                continue
            amount = number_(fields.get("Net Amount"))
            rec["sales"].append((d, amount, fields, row))
            if fy <= d <= as_of:
                rec["ytd_sales"] += amount
            if rec["last_sale"] is None or d > rec["last_sale"]:
                rec["last_sale"] = d

    for key, rows in (src.get("receipts_by_rep") or {}).items():
        for row in rows:
            fields = row.get("fields") or {}
            name = clean_text(fields.get("Sales Rep")) or key
            rec = book(name)
            d = parse_date(fields.get("Date"))
            if not d:
                continue
            amount = number_(fields.get("Amount"))
            rec["receipts"].append((d, amount, fields))
            if fy <= d <= as_of:
                rec["ytd_collection"] += amount
            if rec["last_collection"] is None or d > rec["last_collection"]:
                rec["last_collection"] = d

    for key, rows in (src.get("credit_notes_by_rep") or {}).items():
        for row in rows:
            fields = row.get("fields") or {}
            name = clean_text(fields.get("Sales Rep")) or key
            rec = book(name)
            d = parse_date(fields.get("Date"))
            if not d:
                continue
            amount = number_(fields.get("Net Amount"))
            if amount <= 0:
                continue
            rec["credits"].append((d, amount, fields, row))
            if fy <= d <= as_of:
                rec["ytd_sales"] -= amount
    src["rep_books"] = books
    return books


def _fy_years(sales, receipts, as_of, credits=None, start_month=None):
    sm = normalize_fy_start_month(start_month)
    credit_rows = credits or []
    dated = [d for d, _a, *_rest in sales] + [d for d, _a, _f in receipts] + [d for d, _a, *_rest in credit_rows]
    if not dated:
        return []
    years = []
    for start in iter_fiscal_years(min(dated), as_of, sm):
        next_start = datetime(start.year + 1, sm, 1, 12)
        s_amt = sum(a for d, a, *_rest in sales if d >= start and d < next_start and d <= as_of)
        s_amt -= sum(a for d, a, *_rest in credit_rows if d >= start and d < next_start and d <= as_of)
        c_amt = sum(a for d, a, _f in receipts if d >= start and d < next_start and d <= as_of)
        years.append({
            "label": fy_label(start),
            "start": _iso(start),
            "sales": s_amt,
            "collection": c_amt,
        })
    years.reverse()
    return years


def _rep_rows(store):
    from server.book import load_book
    full = None
    try:
        full = load_book(store)
    except Exception:
        full = None
    cached = (full or {}).get("_rep_rows_cache") if isinstance(full, dict) else None
    if cached:
        return cached
    data = customer_directory_rows(store)
    books = _rep_books(store, data["as_of"])
    by_rep = {}
    for row in data["rows"]:
        name = clean_text(row.get("salesperson"))
        if not name:
            continue
        bucket = by_rep.setdefault(name.lower(), {"name": name, "members": []})
        bucket["name"] = name
        bucket["members"].append(row)
    keys = set(books) | set(by_rep)
    rows = []
    for key in keys:
        book = books.get(key) or {}
        members = (by_rep.get(key) or {}).get("members") or []
        name = book.get("name") or (by_rep.get(key) or {}).get("name") or key
        due = sum(m.get("due") or 0 for m in members)
        statuses = {m.get("status") for m in members}
        status = rollup_status(statuses, due)
        groups = sorted({m.get("group") for m in members if m.get("group")}, key=str.lower)
        last_sale = book.get("last_sale")
        if not last_sale:
            last = max(members, key=lambda m: m.get("last_sale") or "", default=None)
            last_sale_iso = (last or {}).get("last_sale") or ""
            last_sale_label = (last or {}).get("last_sale_label") or ""
        else:
            last_sale_iso = _iso(last_sale)
            last_sale_label = _fmt_day(last_sale)
        buckets = sum_due_buckets(members)
        col = sum_collection_buckets(members)
        ordered_overdue = any(m.get("ordered_overdue") for m in members)
        badge = {
            "current_month": any((m.get("ordering_badge") or {}).get("current_month") for m in members),
            "current_fy": any((m.get("ordering_badge") or {}).get("current_fy") for m in members),
        }
        rows.append({
            "uk": account_uk(name),
            "name": name,
            "customers": len(members),
            "groups": groups,
            "group_count": len(groups),
            "last_sale": last_sale_iso,
            "last_sale_label": last_sale_label,
            "ytd_sales": book.get("ytd_sales") or 0,
            "ytd_collection": book.get("ytd_collection") or 0,
            "due": due,
            **flatten_owe(buckets),
            **flatten_collection(col),
            "owe_buckets": buckets,
            "collection_buckets": col,
            "status": status,
            "status_label": _status_label(status),
            "credit": due < 0,
            "ordered_overdue": ordered_overdue,
            "ordering_badge": badge,
        })
    packed = (data, books, by_rep, rows)
    if isinstance(full, dict):
        full["_rep_rows_cache"] = packed
    return packed


def list_reps(store, params):
    q = clean_text(params.get("q") or "").lower()
    group = clean_text(params.get("group"))
    status_want = _status_id(params.get("status"))
    page, limit = page_limit(params)
    data, _books, _by_rep, rows = _rep_rows(store)
    filtered = []
    for row in rows:
        if q and q not in row["name"].lower() and not any(q in g.lower() for g in row["groups"]):
            continue
        if group and not any(_eq(g, group) for g in row["groups"]):
            continue
        if status_want and row["status"] != status_want:
            continue
        filtered.append(row)
    sort_rows(filtered, params, "ytd_sales", {"due", "customers", "ytd_sales", "ytd_collection", "group_count", *BUCKET_KEYS, *COL_KEYS})
    options = {
        "group": sorted({g for row in rows for g in row["groups"]}, key=str.lower),
        "status": [_status_label(s) for s in ("urgent", "followup", "credit", "ontrack") if any(row["status"] == s for row in rows)],
    }
    start = (page - 1) * limit
    return {
        "total": len(filtered),
        "page": page,
        "limit": limit,
        "reps": filtered[start:start + limit],
        "options": options,
        "sort": clean_text(params.get("sort") or "ytd_sales"),
        "dir": clean_text(params.get("dir") or "desc") or "desc",
    }


def _activity_for_rep(book):
    events = []
    sale_rows = [row for _d, _a, _f, row in book.get("sales") or []]
    party_by_inv = {}
    for _d, _amount, fields, _row in book.get("sales") or []:
        inv = clean_text(fields.get("Invoice No") or fields.get("Invoice"))
        party = clean_text(fields.get("Party Name") or fields.get("Account Name"))
        if inv and party:
            party_by_inv.setdefault(inv.lower(), party)
        if party:
            party_by_inv.setdefault(_iso(_d), party)
    for inv in _group_sales_invoices(sale_rows):
        key = (inv.get("invoice") or "").lower()
        events.append({
            "kind": "sale",
            "date": _iso(inv["date"]),
            "date_label": _fmt_day(inv["date"]),
            "amount": inv["amount"],
            "label": ACTIVITY_LABELS["sale"],
            "rep": inv.get("rep") or book.get("name") or "",
            "invoice": inv.get("invoice") or "",
            "invoice_id": inv.get("invoice_id") or "",
            "note": "",
            "party": party_by_inv.get(key) or party_by_inv.get(_iso(inv["date"])) or "",
            "logged": False,
            "id": "",
        })
    for d, amount, fields in book.get("receipts") or []:
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
            "party": clean_text(fields.get("Account Name") or fields.get("Party Name")),
            "logged": False,
            "id": "",
        })
    for d, amount, fields, _row in book.get("credits") or []:
        events.append({
            "kind": "credit_note",
            "date": _iso(d),
            "date_label": _fmt_day(d),
            "amount": amount,
            "label": ACTIVITY_LABELS["credit_note"],
            "rep": clean_text(fields.get("Sales Rep")) or book.get("name") or "",
            "invoice": clean_text(fields.get("Invoice No")),
            "invoice_id": "",
            "note": clean_text(fields.get("Invoice No")),
            "party": clean_text(fields.get("Party Name") or fields.get("Account Name")),
            "logged": False,
            "id": "",
        })
    events.sort(key=lambda e: e.get("date") or "", reverse=True)
    return events


def get_rep(store, uk):
    uk = account_uk(uk)
    if not uk:
        return None
    data, books, by_rep, rows = _rep_rows(store)
    listed = next((row for row in rows if match_uk(row["name"], uk)), None)
    if not listed:
        return None
    key = listed["name"].lower()
    book = books.get(key) or {
        "name": listed["name"],
        "sales": [],
        "receipts": [],
        "ytd_sales": 0.0,
        "ytd_collection": 0.0,
        "last_sale": None,
        "last_collection": None,
    }
    members = (by_rep.get(key) or {}).get("members") or []
    groups = {}
    for member in members:
        name = member.get("group")
        if not name:
            continue
        slot = groups.setdefault(name.lower(), _rollup_slot(name))
        slot["name"] = name
        add_member_to_rollup(slot, member)
    last_collection = book.get("last_collection")
    from server.book import load_book
    full = load_book(store)
    as_of = data["as_of"]
    sm = _fy_month(store, full)
    fy_start = full.get("fy_start") or fiscal_year_start(as_of, sm)
    mode = get_settlement_mode(store)
    bands = get_aging_bands(store)
    # YTD sales/collections for this rep, attributed to each customer group
    party_group = {}
    for member in members:
        gname = clean_text(member.get("group") or "")
        if gname:
            party_group[(member.get("name") or "").lower()] = gname.lower()
    for entry in book.get("sales") or []:
        d = entry[0] if entry else None
        amount = entry[1] if len(entry) > 1 else 0
        fields = entry[2] if len(entry) > 2 else {}
        if not d or not (fy_start <= d <= as_of):
            continue
        party_l = clean_text(fields.get("Party Name") or fields.get("Account Name")).lower()
        gkey = party_group.get(party_l)
        if gkey and gkey in groups:
            groups[gkey]["ytd_sales"] += number_(amount)
    for entry in book.get("credits") or []:
        d = entry[0] if entry else None
        amount = entry[1] if len(entry) > 1 else 0
        fields = entry[2] if len(entry) > 2 else {}
        if not d or not (fy_start <= d <= as_of):
            continue
        party_l = clean_text(fields.get("Party Name") or fields.get("Account Name")).lower()
        gkey = party_group.get(party_l)
        if gkey and gkey in groups:
            groups[gkey]["ytd_sales"] -= number_(amount)
    for entry in book.get("receipts") or []:
        d = entry[0] if entry else None
        amount = entry[1] if len(entry) > 1 else 0
        fields = entry[2] if len(entry) > 2 else {}
        if not d or not (fy_start <= d <= as_of):
            continue
        party_l = clean_text(fields.get("Account Name") or fields.get("Party Name")).lower()
        gkey = party_group.get(party_l)
        if gkey and gkey in groups:
            groups[gkey]["ytd_collection"] += number_(amount)
    group_rows = finish_rollups(groups.values())
    from server.view_workers import apply_settled_aging

    rolled = apply_settled_aging(full, members, bands)
    if rolled is not None:
        open_invoices = rolled["open_invoices"]
        invoices_waiting = rolled["invoices_waiting"]
        settlements = rolled["settlements"]
    else:
        all_allocs = []
        credit_total = 0.0
        open_invoices = []
        invoices_waiting = 0
        for member in members:
            name_l = (member.get("name") or "").lower()
            invoices = _group_sales_invoices(full["sales_by_party"].get(name_l) or [], start_month=sm)
            opening_dt = _opening_from_invoices(invoices, as_of, sm)
            receipt_list = []
            for row in full.get("receipts_by_party", {}).get(name_l) or []:
                fields = row.get("fields") or {}
                d = parse_date(fields.get("Date"))
                if not d:
                    continue
                amount = number_(fields.get("Amount"))
                if amount <= 0:
                    continue
                receipt_list.append({
                    "date": d,
                    "amount": amount,
                    "invoice": clean_text(
                        fields.get("Invoice No") or fields.get("Invoice") or fields.get("Invoice Number") or ""
                    ),
                })
            credit_list = []
            for row in full.get("credit_notes_by_party", {}).get(name_l) or []:
                fields = row.get("fields") or {}
                d = parse_date(fields.get("Date"))
                if not d:
                    continue
                amount = number_(fields.get("Net Amount"))
                if amount <= 0:
                    continue
                credit_list.append({
                    "date": d,
                    "amount": amount,
                    "invoice": clean_text(fields.get("Invoice No") or ""),
                })
            open_lines, _buckets, _opening, _opened = _allocate_open(
                invoices,
                member.get("due") or 0,
                as_of,
                opening_dt,
                mode=mode,
                receipts=receipt_list,
                bands=bands,
                credits=credit_list,
            )
            invoices_waiting += len(open_lines)
            for line in open_lines:
                row = dict(line)
                row["party"] = member.get("name")
                row["customer_uk"] = member.get("uk")
                open_invoices.append(row)
            _col, allocs, credit, _rem, _op = allocate_collections(
                invoices, receipt_list, as_of, opening_dt=opening_dt, mode=mode,
                due=member.get("due") or 0, bands=bands, credits=credit_list,
            )
            for alloc in allocs:
                alloc["party"] = member.get("name") or ""
                alloc["customer_uk"] = member.get("uk") or ""
            all_allocs.extend(allocs)
            credit_total += credit or 0
        settlements = build_settlements_summary(all_allocs, as_of, bands=bands, credit=credit_total, start_month=sm)
    open_invoices.sort(key=lambda r: r.get("age_days") or 0, reverse=True)
    from server.due_days import resolve_entity_due_days

    if rolled is not None and rolled.get("orderings") is not None:
        member_orderings = rolled["orderings"]
    else:
        member_orderings = []
        for member in members:
            name_l = (member.get("name") or "").lower()
            member_orderings.append(ordering_for_party(
                store,
                name_l,
                as_of,
                party_name=member.get("name") or "",
                customer_uk=member.get("uk") or "",
                group=member.get("group") or "",
                rep=listed["name"],
                book=full,
                mode=mode,
                bands=bands,
                arr_due=member.get("due"),
            ))
    due_meta = resolve_entity_due_days(store, "rep", listed["name"])
    ordering = merge_ordering_summaries(
        member_orderings,
        as_of,
        due_days=due_meta["due_days"],
        due_days_source=due_meta["source"],
        start_month=sm,
    )
    buying = buying_for_names(store, [m["name"].lower() for m in members], data["as_of"])
    owe = listed.get("owe_buckets") or empty_buckets()
    insight = _insight(
        listed["name"],
        listed["due"],
        listed["status"],
        owe,
        listed["ytd_sales"],
        listed["ytd_collection"],
        listed["last_sale_label"],
        listed["last_sale"],
        as_of,
        buying,
    )
    detail = {
        "uk": listed["uk"],
        "name": listed["name"],
        "customers": members,
        "customer_count": listed["customers"],
        "groups": group_rows,
        "due": listed["due"],
        "status": listed["status"],
        "status_label": listed["status_label"],
        "health_label": insight.get("health_label") or listed["status_label"],
        "insight": insight,
        "credit": listed["credit"],
        "last_sale": listed["last_sale"],
        "last_sale_label": listed["last_sale_label"],
        "last_collection": _iso(last_collection),
        "last_collection_label": _fmt_day(last_collection),
        "ytd_sales": listed["ytd_sales"],
        "ytd_collection": listed["ytd_collection"],
        "invoices_waiting": invoices_waiting,
        "open_invoices": open_invoices,
        "owe_buckets": owe,
        "due_buckets": owe,
        "collection_buckets": listed.get("collection_buckets") or empty_buckets(),
        "settlements": settlements,
        "aging_bands": bands,
        "ordering": ordering,
        "due_days": due_meta["due_days"],
        "due_days_source": due_meta["source"],
        "due_days_own": due_meta.get("own"),
        "ordered_overdue": bool((ordering.get("badge") or {}).get("current_month") or (ordering.get("badge") or {}).get("current_fy")),
        "fy_years": attach_party_fy_qty(
            store,
            [m["name"].lower() for m in members],
            _fy_years(
                book.get("sales") or [], book.get("receipts") or [], data["as_of"], book.get("credits"),
                start_month=sm,
            ),
        ),
        "activity": _activity_for_rep(book),
        "buying": buying,
        "as_of": _iso(data["as_of"]),
        "as_of_label": _fmt_day(data["as_of"]),
        "fiscal_year_start_month": sm,
    }
    from server.repurchase import attach_repurchase
    return attach_repurchase(store, detail, rep=detail.get("uk") or detail.get("name"))
