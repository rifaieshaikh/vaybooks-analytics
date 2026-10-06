"""Customer group 360. Does not feed generate()."""

from __future__ import annotations

from datetime import datetime

from vay.dates import clean_text, fy_label, iter_fiscal_years, number_, parse_date

from vay.settlement import BUCKET_KEYS, allocate_collections, empty_buckets, flatten_collection, flatten_owe

from server.customers import (
    _allocate_open,
    _eq,
    _fmt_day,
    _group_sales_invoices,
    _insight,
    _iso,
    _fy_month,
    _opening_from_invoices,
    _period_bounds,
    _rank_items,
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


def match_uk(name, uk):
    return account_uk(name).lower() == account_uk(uk).lower()


def page_limit(params):
    try:
        page = max(1, int(params.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    return page, 50


def rollup_status(statuses, due):
    if "urgent" in statuses:
        return "urgent"
    if "followup" in statuses:
        return "followup"
    if due < 0:
        return "credit"
    return "ontrack"


def buying_for_names(store, name_ls, as_of):
    from server.book import load_book
    book = load_book(store)
    items = []
    for name_l in name_ls:
        items.extend(book.get("buying_lines_by_party", {}).get(name_l) or [])
    last_date = max((i["date"] for i in items if i["date"]), default=None)
    stock = book.get("stock_qty") or {}
    bounds = _period_bounds(as_of, _fy_month(store, book))
    periods = {}
    for key, (start, end, label) in bounds.items():
        periods[key] = {
            "id": key,
            "label": label,
            "items": _rank_items(items, start, end, as_of, stock),
        }
    period_order = ("this_month", "last_month", "last_3m", "this_year", "last_year", "all")
    default_period = next((key for key in period_order if periods[key]["items"]), "all")
    usual = [r["name"] for r in periods["this_year"]["items"][:5]] or [r["name"] for r in periods["all"]["items"][:5]]
    return {
        "last_order_date": _fmt_day(last_date),
        "periods": periods,
        "usual": usual,
        "has_item_rows": bool(items),
        "default_period": default_period,
    }


COL_KEYS = tuple("c_" + k for k in BUCKET_KEYS)


def sum_due_buckets(members):
    out = empty_buckets()
    for member in members or []:
        nested = member.get("owe_buckets") or {}
        for key in out:
            val = member.get(key)
            if val is None:
                val = nested.get(key) or 0
            out[key] += val or 0
    return out


def sum_collection_buckets(members):
    out = empty_buckets()
    for member in members or []:
        nested = member.get("collection_buckets") or {}
        for key in out:
            flat = member.get("c_" + key)
            val = flat if flat is not None else (nested.get(key) or 0)
            out[key] += val or 0
    return out


def _rollup_slot(name, uk=None):
    return {
        "uk": uk or account_uk(name),
        "name": name,
        "customers": 0,
        "due": 0.0,
        "statuses": set(),
        "urgent_count": 0,
        "followup_count": 0,
        "ordered_overdue": False,
        "last_sale": "",
        "last_sale_label": "",
        "ytd_sales": 0.0,
        "ytd_collection": 0.0,
        "owe_buckets": empty_buckets(),
    }


def add_member_to_rollup(slot, member):
    """Accumulate one directory member into a group/rep rollup row."""
    slot["customers"] += 1
    slot["due"] += member.get("due") or 0
    st = member.get("status") or "ontrack"
    slot["statuses"].add(st)
    if st == "urgent":
        slot["urgent_count"] += 1
    elif st == "followup":
        slot["followup_count"] += 1
    if member.get("ordered_overdue"):
        slot["ordered_overdue"] = True
    ls = member.get("last_sale") or ""
    if ls > (slot.get("last_sale") or ""):
        slot["last_sale"] = ls
        slot["last_sale_label"] = member.get("last_sale_label") or ""
    nested = member.get("owe_buckets") or {}
    for key in slot["owe_buckets"]:
        val = member.get(key)
        if val is None:
            val = nested.get(key) or 0
        slot["owe_buckets"][key] += val or 0


def finish_rollups(slots):
    out = []
    for slot in slots:
        statuses = slot.pop("statuses", set()) or set()
        status = rollup_status(statuses, slot.get("due") or 0)
        slot["status"] = status
        slot["status_label"] = _status_label(status)
        slot["credit"] = (slot.get("due") or 0) < 0
        flat = flatten_owe(slot.get("owe_buckets") or {})
        slot.update(flat)
        slot["ytd_sales"] = round(number_(slot.get("ytd_sales")), 2)
        slot["ytd_collection"] = round(number_(slot.get("ytd_collection")), 2)
        out.append(slot)
    out.sort(key=lambda r: (-(r.get("due") or 0), (r.get("name") or "").lower()))
    return out


def sort_rows(rows, params, default, numeric):
    key = clean_text(params.get("sort") or default).lower()
    if key == "status":
        key = "status_label"
    if key == "rep":
        key = "rep_count"
    if key == "group":
        key = "group_count"
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
    numeric = set(numeric or ()) | set(BUCKET_KEYS) | set(COL_KEYS)
    direction = clean_text(params.get("dir") or "desc").lower()
    if direction not in ("asc", "desc"):
        direction = "desc"
    if key not in (rows[0] if rows else {}) and key not in numeric and key != "name":
        key = default

    def sort_val(row):
        val = row.get(key)
        if val is None:
            return float("-inf") if key in numeric else ""
        if isinstance(val, (int, float)):
            return val
        if isinstance(val, list):
            return len(val)
        return str(val).lower()

    rows.sort(key=sort_val, reverse=(direction == "desc"))
    return key, direction


def _group_rows(store):
    from server.book import load_book
    book = getattr(store, "_360_book", None) or None
    try:
        book = load_book(store)
    except Exception:
        book = None
    cached = (book or {}).get("_group_rows_cache") if isinstance(book, dict) else None
    if cached:
        return cached
    data = customer_directory_rows(store)
    by_name = {}
    for row in data["rows"]:
        name = clean_text(row.get("group"))
        if not name:
            continue
        bucket = by_name.setdefault(name.lower(), {"name": name, "members": []})
        bucket["name"] = name
        bucket["members"].append(row)
    rows = []
    for bucket in by_name.values():
        members = bucket["members"]
        due = sum(m.get("due") or 0 for m in members)
        statuses = {m.get("status") for m in members}
        last = max(members, key=lambda m: m.get("last_sale") or "")
        reps = sorted({m.get("salesperson") for m in members if m.get("salesperson")}, key=str.lower)
        status = rollup_status(statuses, due)
        buckets = sum_due_buckets(members)
        col = sum_collection_buckets(members)
        ordered_overdue = any(m.get("ordered_overdue") for m in members)
        badge = {
            "current_month": any((m.get("ordering_badge") or {}).get("current_month") for m in members),
            "current_fy": any((m.get("ordering_badge") or {}).get("current_fy") for m in members),
        }
        rows.append({
            "uk": account_uk(bucket["name"]),
            "name": bucket["name"],
            "customers": len(members),
            "reps": reps,
            "rep_count": len(reps),
            "last_sale": last.get("last_sale") or "",
            "last_sale_label": last.get("last_sale_label") or "",
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
    packed = (data, rows)
    if isinstance(book, dict):
        book["_group_rows_cache"] = packed
    return packed


def list_groups(store, params):
    q = clean_text(params.get("q") or "").lower()
    rep = clean_text(params.get("rep"))
    status_want = _status_id(params.get("status"))
    page, limit = page_limit(params)
    data, rows = _group_rows(store)
    filtered = []
    for row in rows:
        if q and q not in row["name"].lower() and not any(q in r.lower() for r in row["reps"]):
            continue
        if rep and not any(_eq(r, rep) for r in row["reps"]):
            continue
        if status_want and row["status"] != status_want:
            continue
        filtered.append(row)
    sort_rows(filtered, params, "due", {"due", "customers", "rep_count", *BUCKET_KEYS, *COL_KEYS})
    options = {
        "rep": sorted({r for row in rows for r in row["reps"]}, key=str.lower),
        "status": [_status_label(s) for s in ("urgent", "followup", "credit", "ontrack") if any(row["status"] == s for row in rows)],
    }
    start = (page - 1) * limit
    return {
        "total": len(filtered),
        "page": page,
        "limit": limit,
        "groups": filtered[start:start + limit],
        "options": options,
        "sort": clean_text(params.get("sort") or "due"),
        "dir": clean_text(params.get("dir") or "desc") or "desc",
    }


def get_group(store, uk):
    from server.book import load_book
    uk = account_uk(uk)
    if not uk:
        return None
    book = load_book(store)
    data, rows = _group_rows(store)
    listed = next((row for row in rows if match_uk(row["name"], uk)), None)
    if not listed:
        return None
    members = [row for row in data["rows"] if match_uk(row.get("group"), listed["name"])]
    as_of = book["as_of"]
    fy_start = book["fy_start"]
    sm = _fy_month(store, book)
    ytd_sales = 0.0
    ytd_collection = 0.0
    sales = []
    receipts = []
    last_collection = None
    open_invoices = []
    invoices_waiting = 0
    mode = get_settlement_mode(store)
    bands = get_aging_bands(store)
    from server.view_workers import apply_settled_aging

    rolled = apply_settled_aging(book, members, bands)
    if rolled is not None:
        owe = rolled["owe"]
        collection = rolled["collection"]
        open_invoices = rolled["open_invoices"]
        invoices_waiting = rolled["invoices_waiting"]
        all_allocs = []
        credit_total = 0.0
    else:
        owe = empty_buckets(bands)
        collection = empty_buckets(bands)
        all_allocs = []
        credit_total = 0.0
    for member in members:
        name_l = (member.get("name") or "").lower()
        sale_rows = book["sales_by_party"].get(name_l, [])
        rec_rows = book["receipts_by_party"].get(name_l, [])
        note_rows = (book.get("credit_notes_by_party") or {}).get(name_l, [])
        if rolled is None:
            invoices = _group_sales_invoices(sale_rows, start_month=sm)
            opening_dt = _opening_from_invoices(invoices, as_of, sm)
            receipt_list = []
            for row in rec_rows:
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
            for row in note_rows:
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
            open_lines, buckets, _opening, _opened = _allocate_open(
                invoices,
                member.get("due") or 0,
                as_of,
                opening_dt,
                mode=mode,
                receipts=receipt_list,
                bands=bands,
                credits=credit_list,
            )
            col_buckets, allocs, credit, _rem, _op = allocate_collections(
                invoices, receipt_list, as_of, opening_dt=opening_dt, mode=mode,
                due=member.get("due") or 0, bands=bands, credits=credit_list,
            )
            for alloc in allocs:
                alloc["party"] = member.get("name") or ""
                alloc["customer_uk"] = member.get("uk") or ""
            all_allocs.extend(allocs)
            credit_total += credit or 0
            invoices_waiting += len(open_lines)
            for line in open_lines:
                row = dict(line)
                row["party"] = member.get("name")
                row["customer_uk"] = member.get("uk")
                open_invoices.append(row)
            for key in owe:
                owe[key] += buckets.get(key) or 0
                collection[key] += col_buckets.get(key) or 0
        for row in sale_rows:
            fields = row.get("fields") or {}
            d = parse_date(fields.get("Date"))
            if not d:
                continue
            amount = number_(fields.get("Net Amount"))
            sales.append((d, amount))
            if fy_start <= d <= as_of:
                ytd_sales += amount
        for row in rec_rows:
            fields = row.get("fields") or {}
            d = parse_date(fields.get("Date"))
            if not d:
                continue
            amount = number_(fields.get("Amount"))
            receipts.append((d, amount))
            if fy_start <= d <= as_of:
                ytd_collection += amount
            if last_collection is None or d > last_collection:
                last_collection = d
        for row in note_rows:
            fields = row.get("fields") or {}
            d = parse_date(fields.get("Date"))
            if not d:
                continue
            amount = number_(fields.get("Net Amount"))
            if amount <= 0:
                continue
            sales.append((d, -amount))
            if fy_start <= d <= as_of:
                ytd_sales -= amount
    if rolled is not None:
        settlements = rolled["settlements"]
    else:
        settlements = build_settlements_summary(all_allocs, as_of, bands=bands, credit=credit_total, start_month=sm)
    open_invoices.sort(key=lambda r: r.get("age_days") or 0, reverse=True)
    dated = [d for d, _a in sales] + [d for d, _a in receipts]
    fy_years = []
    if dated:
        for start in iter_fiscal_years(min(dated), as_of, sm):
            next_start = datetime(start.year + 1, sm, 1, 12)
            fy_years.append({
                "label": fy_label(start),
                "start": _iso(start),
                "sales": sum(a for d, a in sales if d >= start and d < next_start and d <= as_of),
                "collection": sum(a for d, a in receipts if d >= start and d < next_start and d <= as_of),
            })
        fy_years.reverse()
    people = {}
    for member in members:
        name = member.get("salesperson")
        if not name:
            continue
        slot = people.setdefault(name.lower(), _rollup_slot(name))
        slot["name"] = name
        add_member_to_rollup(slot, member)
    for member in members:
        name_l = (member.get("name") or "").lower()
        assigned = clean_text(member.get("salesperson") or "")
        for row in book["sales_by_party"].get(name_l, []):
            fields = row.get("fields") or {}
            d = parse_date(fields.get("Date"))
            if not d or not (fy_start <= d <= as_of):
                continue
            amount = number_(fields.get("Net Amount"))
            rep = clean_text(fields.get("Sales Rep")) or assigned
            if not rep:
                continue
            slot = people.get(rep.lower())
            if not slot and assigned:
                slot = people.get(assigned.lower())
            if slot:
                slot["ytd_sales"] += amount
        for row in (book.get("credit_notes_by_party") or {}).get(name_l, []):
            fields = row.get("fields") or {}
            d = parse_date(fields.get("Date"))
            if not d or not (fy_start <= d <= as_of):
                continue
            amount = number_(fields.get("Net Amount"))
            if amount <= 0:
                continue
            rep = clean_text(fields.get("Sales Rep")) or assigned
            if not rep:
                continue
            slot = people.get(rep.lower())
            if not slot and assigned:
                slot = people.get(assigned.lower())
            if slot:
                slot["ytd_sales"] -= amount
        for row in book["receipts_by_party"].get(name_l, []):
            fields = row.get("fields") or {}
            d = parse_date(fields.get("Date"))
            if not d or not (fy_start <= d <= as_of):
                continue
            amount = number_(fields.get("Amount"))
            rep = clean_text(fields.get("Sales Rep")) or assigned
            if not rep:
                continue
            slot = people.get(rep.lower())
            if not slot and assigned:
                slot = people.get(assigned.lower())
            if slot:
                slot["ytd_collection"] += amount
    salespeople = finish_rollups(people.values())
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
                group=listed["name"],
                rep=member.get("salesperson") or "",
                book=book,
                mode=mode,
                bands=bands,
                arr_due=member.get("due"),
            ))
    due_meta = resolve_entity_due_days(store, "group", listed["name"])
    ordering = merge_ordering_summaries(
        member_orderings,
        as_of,
        due_days=due_meta["due_days"],
        due_days_source=due_meta["source"],
        start_month=sm,
    )
    buying = buying_for_names(store, [m["name"].lower() for m in members], as_of)
    insight = _insight(
        listed["name"],
        listed["due"],
        listed["status"],
        owe,
        ytd_sales,
        ytd_collection,
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
        "reps": listed["reps"],
        "salespeople": salespeople,
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
        "ytd_sales": ytd_sales,
        "ytd_collection": ytd_collection,
        "invoices_waiting": invoices_waiting,
        "open_invoices": open_invoices,
        "owe_buckets": owe,
        "due_buckets": owe,
        "collection_buckets": collection,
        "settlements": settlements,
        "settlement_mode": mode,
        "aging_bands": bands,
        "ordering": ordering,
        "due_days": due_meta["due_days"],
        "due_days_source": due_meta["source"],
        "due_days_own": due_meta.get("own"),
        "ordered_overdue": bool((ordering.get("badge") or {}).get("current_month") or (ordering.get("badge") or {}).get("current_fy")),
        "fy_years": attach_party_fy_qty(store, [m["name"].lower() for m in members], fy_years),
        "buying": buying,
        "as_of": _iso(as_of),
        "as_of_label": _fmt_day(as_of),
        "fiscal_year_start_month": sm,
    }
    from server.repurchase import attach_repurchase
    return attach_repurchase(store, detail, group=detail.get("uk") or detail.get("name"))
