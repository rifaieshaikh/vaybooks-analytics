"""Core reports: sales-rep, account, group, follow-ups, warnings.

Compare goldens by entity key (Sales Rep / Account Name / Group / Customer), not row index.
Sales-rep sorted by YTD; total label is TOTAL. Account sorted by YTD. Group sorted by MTD.
arr.Days optional → AR Days 0. INVESTMENT receipts excluded from collection everywhere.
Collection only counts receipt Account Names in ctx['customer_accounts'] when that set is provided.
"""

from vay.credit_notes import rep_index, rep_on_or_before
from vay.config import (
    DEFAULT_GROUP,
    DEFAULT_PARTY,
    DEFAULT_RECEIPT_REP,
    DEFAULT_SALES_REP,
    MAX_WARNING_ROWS,
    WARNING_KEY_LIMIT,
)
from vay.dates import (
    add_period_amount,
    clean_text,
    fiscal_year_start,
    new_period_summary,
    number_,
    parse_date,
    total_row,
)
from vay.settlement import (
    BUCKET_KEYS,
    allocate_collections,
    allocate_open,
    band_keys,
    collection_header_keys,
    empty_buckets,
    is_collection_customer,
    normalize_mode,
    owe_header_keys,
    sales_age_bucket_index,
)


def _sales_rep_lookup(sales):
    pairs = []
    if sales is None or "Date" not in sales.index:
        return rep_index([])
    for r in sales.rows:
        pairs.append((sales.get(r, "Party Name"), _d(r, sales, "Date"), sales.get(r, "Sales Rep")))
    return rep_index(pairs)


def _d(row, table, header):
    raw = table.get(row, header)
    if hasattr(raw, "year") and hasattr(raw, "month"):
        return raw
    return parse_date(raw)


def _sales_bucket_fields(ctx=None):
    bands = (ctx or {}).get("aging_bands")
    n = len(bands) if bands else 6
    return {
        "salesBands": [0.0] * n,
        "salesLast10": 0, "salesLast15": 0, "salesLast20": 0, "salesLast25": 0, "salesLast30": 0,
        "bal10Plus": 0, "bal15Plus": 0, "bal20Plus": 0, "bal25Plus": 0, "bal30Plus": 0,
        "invoices": [],
        "receipts": [],
        "credits": [],
        "salesperson": "",
    }


def _apply_sales_aging(a, amount, d, ctx):
    idx = sales_age_bucket_index(d, ctx)
    while len(a["salesBands"]) <= idx:
        a["salesBands"].append(0.0)
    a["salesBands"][idx] += amount
    if d >= ctx["last10Start"]:
        a["salesLast10"] += amount
    if d >= ctx["last15Start"]:
        a["salesLast15"] += amount
    if d >= ctx["last20Start"]:
        a["salesLast20"] += amount
    if d >= ctx["last25Start"]:
        a["salesLast25"] += amount
    if d >= ctx["last30Start"]:
        a["salesLast30"] += amount


def _finalize_account_aging(a, ctx):
    mode = normalize_mode(ctx.get("settlement_mode"))
    as_of = ctx["reportDate"]
    aging_bands = ctx.get("aging_bands")
    keys = band_keys(aging_bands) if aging_bands else BUCKET_KEYS
    invoices = a.get("invoices") or []
    opening_dt = fiscal_year_start(as_of, ctx.get("fiscalYearStartMonth"))
    if invoices:
        opening_dt = min(
            fiscal_year_start(inv["date"], ctx.get("fiscalYearStartMonth"))
            for inv in invoices if inv.get("date")
        )
    bands = a["salesBands"]
    open_lines, owe_buckets, _opening, _odt = allocate_open(
        invoices,
        a.get("balance"),
        as_of,
        opening_dt=opening_dt,
        mode=mode,
        receipts=a.get("receipts") or [],
        bands=aging_bands,
        credits=a.get("credits") or [],
    )
    for key in keys:
        a["owe_" + key] = owe_buckets.get(key) or 0.0
    col, _allocs, _credit, _rem, _op = allocate_collections(
        invoices, a.get("receipts") or [], as_of, opening_dt=opening_dt, mode=mode,
        due=a.get("balance"), bands=aging_bands, credits=a.get("credits") or [],
    )
    for key in keys:
        a["col_" + key] = col.get(key) or 0.0
    # Compat aliases used by follow-up reports (assume default 6-band layout when present)
    a["d0to15Sales"] = bands[0] if len(bands) > 0 else 0
    a["d16to30Sales"] = bands[1] if len(bands) > 1 else 0
    a["d31to60Sales"] = (bands[2] if len(bands) > 2 else 0) + (bands[3] if len(bands) > 3 else 0)
    a["olderSales"] = sum(bands[4:]) if len(bands) > 4 else 0
    a["newCredit"] = a.get("owe_d0_15") or (owe_buckets.get(keys[0]) if keys else 0) or 0
    a["overdue15"] = a.get("owe_d15_30") or 0
    a["overdue30"] = sum(
        a.get("owe_" + k) or 0
        for k in keys
        if k not in ("d0_15", "d15_30") and k != (keys[0] if keys else None)
    )
    if "owe_d30_45" in a or "d30_45" in keys:
        a["overdue30"] = (
            (a.get("owe_d30_45") or 0)
            + (a.get("owe_d45_60") or 0)
            + (a.get("owe_d60_90") or 0)
            + (a.get("owe_d90") or 0)
        )
    outstanding = max(0.0, a["balance"])
    a["bal10Plus"] = max(0.0, outstanding - a["salesLast10"])
    a["bal15Plus"] = max(0.0, outstanding - a["salesLast15"])
    a["bal20Plus"] = max(0.0, outstanding - a["salesLast20"])
    a["bal25Plus"] = max(0.0, outstanding - a["salesLast25"])
    a["bal30Plus"] = max(0.0, outstanding - a["salesLast30"])
    a["_open_lines"] = open_lines
    a["_aging_keys"] = keys


def sales_rep_performance(tables, ctx):
    sales = tables["sales"]
    receipts = tables["receipt"]
    summaries = {}
    owe = {}
    col = {}
    aging_bands = ctx.get("aging_bands")
    keys = band_keys(aging_bands) if aging_bands else BUCKET_KEYS
    owe_headers = owe_header_keys(aging_bands)
    col_headers = collection_header_keys(aging_bands)

    def add(rep, amount, date, typ):
        rep = clean_text(rep) or (DEFAULT_SALES_REP if typ == "sales" else DEFAULT_RECEIPT_REP)
        if rep == DEFAULT_RECEIPT_REP:
            return
        if not date or date > ctx["reportDate"]:
            return
        if rep not in summaries:
            summaries[rep] = new_period_summary()
            owe[rep] = empty_buckets(aging_bands)
            col[rep] = empty_buckets(aging_bands)
        add_period_amount(summaries[rep], typ, amount, date, ctx)

    for r in sales.rows:
        add(sales.get(r, "Sales Rep"), number_(sales.get(r, "Net Amount")), _d(r, sales, "Date"), "sales")
    for r in receipts.rows:
        account = receipts.get(r, "Account Name")
        if not is_collection_customer(account, ctx):
            continue
        add(receipts.get(r, "Sales Rep"), number_(receipts.get(r, "Amount")), _d(r, receipts, "Date"), "collection")
    notes = tables.get("credit_note")
    if notes is not None and "Date" in notes.index and "Net Amount" in notes.index:
        lookup = _sales_rep_lookup(sales)
        for r in notes.rows:
            d = _d(r, notes, "Date")
            amount = number_(notes.get(r, "Net Amount"))
            if not d or d > ctx["reportDate"] or amount <= 0:
                continue
            party = clean_text(notes.get(r, "Party Name"))
            rep = rep_on_or_before(lookup, party, d) or DEFAULT_SALES_REP
            add(rep, -amount, d, "sales")

    # Roll up account aging onto last salesperson when accounts already computed
    for a in ctx.get("accounts") or []:
        rep = clean_text(a.get("salesperson"))
        if not rep or rep == DEFAULT_RECEIPT_REP:
            continue
        if rep not in summaries:
            summaries[rep] = new_period_summary()
            owe[rep] = empty_buckets(aging_bands)
            col[rep] = empty_buckets(aging_bands)
        for key in keys:
            owe[rep][key] += number_(a.get("owe_" + key))
            col[rep][key] += number_(a.get("col_" + key))

    rows = []
    for rep, s in summaries.items():
        row = [
            rep, s["mtdSales"], s["mtdCollection"], s["d15Sales"], s["d15Collection"],
            s["m2Sales"], s["m2Collection"], s["m3Sales"], s["m3Collection"],
            s["ytdSales"], s["ytdCollection"],
        ]
        for key in keys:
            row.append((owe.get(rep) or empty_buckets(aging_bands)).get(key) or 0)
        for key in keys:
            row.append((col.get(rep) or empty_buckets(aging_bands)).get(key) or 0)
        rows.append(row)
    rows.sort(key=lambda a: -a[9])
    headers = [
        "Sales Rep", "MTD Sales", "MTD Collection", "15 Days Sales", "15 Days Collection",
        "2 Months Sales", "2 Months Collection", "3 Months Sales", "3 Months Collection",
        "YTD Sales", "YTD Collection",
    ] + [h for _k, h in owe_headers] + [h for _k, h in col_headers]
    width = len(headers)
    return {
        "id": "sales_rep_performance_report",
        "title": "Sales rep performance",
        "headers": headers,
        "rows": rows,
        "total": total_row(rows, width, "TOTAL", 1),
        "key_col": 0,
    }


def account_performance(tables, ctx):
    sales = tables["sales"]
    receipts = tables["receipt"]
    arr = tables["arr"]
    accounts = {}
    aging_bands = ctx.get("aging_bands")
    keys = band_keys(aging_bands) if aging_bands else BUCKET_KEYS
    owe_headers = owe_header_keys(aging_bands)
    col_headers = collection_header_keys(aging_bands)
    from vay.settlement import band_labels
    labels = band_labels(aging_bands)

    def ensure(name):
        name = clean_text(name) or DEFAULT_PARTY
        key = name.lower()
        if key not in accounts:
            base = {
                "name": name, "group": DEFAULT_GROUP, "arDays": 0, "balance": 0,
                "summary": new_period_summary(),
            }
            base.update(_sales_bucket_fields(ctx))
            accounts[key] = base
        return accounts[key]

    for r in arr.rows:
        name = clean_text(arr.get(r, "Account Name"))
        if not name:
            continue
        a = ensure(name)
        a["group"] = clean_text(arr.get(r, "Group")) or DEFAULT_GROUP
        a["balance"] = number_(arr.get(r, "Balance"))
        a["arDays"] = number_(arr.get(r, "Days")) if "Days" in arr.index else 0

    for r in sales.rows:
        d = _d(r, sales, "Date")
        if not d or d > ctx["reportDate"]:
            continue
        a = ensure(sales.get(r, "Party Name"))
        amount = number_(sales.get(r, "Net Amount"))
        add_period_amount(a["summary"], "sales", amount, d, ctx)
        _apply_sales_aging(a, amount, d, ctx)
        inv = clean_text(sales.get(r, "Invoice No"))
        a["invoices"].append({"date": d, "amount": amount, "invoice": inv, "invoice_id": ""})
        rep = clean_text(sales.get(r, "Sales Rep"))
        if rep:
            a["salesperson"] = rep

    for r in receipts.rows:
        rep = clean_text(receipts.get(r, "Sales Rep")) or DEFAULT_RECEIPT_REP
        if rep == DEFAULT_RECEIPT_REP:
            continue
        account = receipts.get(r, "Account Name")
        if not is_collection_customer(account, ctx):
            continue
        d = _d(r, receipts, "Date")
        if not d or d > ctx["reportDate"]:
            continue
        a = ensure(account)
        amount = number_(receipts.get(r, "Amount"))
        add_period_amount(a["summary"], "collection", amount, d, ctx)
        inv = clean_text(receipts.get(r, "Invoice No"))
        a["receipts"].append({"date": d, "amount": amount, "invoice": inv})

    notes = tables.get("credit_note")
    if notes is not None and "Date" in notes.index and "Net Amount" in notes.index:
        for r in notes.rows:
            d = _d(r, notes, "Date")
            amount = number_(notes.get(r, "Net Amount"))
            if not d or d > ctx["reportDate"] or amount <= 0:
                continue
            a = ensure(notes.get(r, "Party Name"))
            add_period_amount(a["summary"], "sales", -amount, d, ctx)
            _apply_sales_aging(a, -amount, d, ctx)
            a["credits"].append({
                "date": d,
                "amount": amount,
                "invoice": clean_text(notes.get(r, "Invoice No")),
            })

    account_list = []
    for a in accounts.values():
        _finalize_account_aging(a, ctx)
        account_list.append(a)
    account_list.sort(key=lambda a: -a["summary"]["ytdSales"])
    ctx["accounts"] = account_list

    rows = []
    for a in account_list:
        s = a["summary"]
        bands = a["salesBands"]
        while len(bands) < len(keys):
            bands.append(0.0)
        row = [
            a["name"], a["group"], a["arDays"], s["mtdSales"], s["mtdCollection"],
            s["m2Sales"], s["m2Collection"], s["m3Sales"], s["m3Collection"],
            s["ytdSales"], s["ytdCollection"], a["balance"],
        ]
        for key in keys:
            row.append(a.get("owe_" + key) or 0)
        for key in keys:
            row.append(a.get("col_" + key) or 0)
        for i in range(len(keys)):
            row.append(bands[i] if i < len(bands) else 0)
        rows.append(row)
    sales_headers = []
    for i, key in enumerate(keys):
        label = labels.get(key) or key
        if i == 0:
            sales_headers.append("Sales in Last %s Days" % label)
        elif i == len(keys) - 1:
            sales_headers.append("Sales Before %s Days" % (labels.get(keys[i - 1]) or label))
        else:
            sales_headers.append("Sales Between %s Days" % label)
    headers = [
        "Account Name", "Group", "AR Days", "MTD Sales", "MTD Collection",
        "2 Months Sales", "2 Months Collection", "3 Months Sales", "3 Months Collection",
        "YTD Sales", "YTD Collection", "Balance",
    ] + [h for _k, h in owe_headers] + [h for _k, h in col_headers] + sales_headers
    width = len(headers)
    return {
        "id": "account_performance_report",
        "title": "Account performance",
        "headers": headers,
        "rows": rows,
        "total": total_row(rows, width, "Total", 3),
        "key_col": 0,
    }


def group_performance(ctx):
    if not ctx.get("accounts"):
        raise ValueError("Account performance data is not available")
    aging_bands = ctx.get("aging_bands")
    owe_headers = owe_header_keys(aging_bands)
    col_headers = collection_header_keys(aging_bands)
    metric_keys = [
        ("mtdSales", "MTD Sales"), ("mtdCollection", "MTD Collection"),
        ("m2Sales", "2 Months Sales"), ("m2Collection", "2 Months Collection"),
        ("m3Sales", "3 Months Sales"), ("m3Collection", "3 Months Collection"),
        ("ytdSales", "YTD Sales"), ("ytdCollection", "YTD Collection"),
        ("balance", "Balance"),
    ]
    for key, label in owe_headers:
        metric_keys.append((key, label))
    for key, label in col_headers:
        metric_keys.append((key, label))
    groups = {}
    for a in ctx["accounts"]:
        group = a["group"] or DEFAULT_GROUP
        if group not in groups:
            groups[group] = [0.0] * len(metric_keys)
        for i, metric in enumerate(metric_keys):
            value = a["summary"][metric[0]] if metric[0] in a["summary"] else a.get(metric[0])
            groups[group][i] += number_(value)
    rows = [[g] + groups[g] for g in groups]
    rows.sort(key=lambda a: -a[1])
    headers = ["Group"] + [m[1] for m in metric_keys]
    width = len(headers)
    return {
        "id": "group_performance_report",
        "title": "Group performance",
        "headers": headers,
        "rows": rows,
        "total": total_row(rows, width, "Total", 1),
        "key_col": 0,
    }


def sales_follow_ups(ctx):
    groups = {}
    for a in ctx["accounts"]:
        if a["summary"]["mtdSales"] != 0:
            continue
        has_history = (
            a["summary"]["ytdSales"] != 0 or a["d0to15Sales"] != 0 or a["d16to30Sales"] != 0
            or a["d31to60Sales"] != 0 or a["olderSales"] != 0
            or a["summary"]["m2Sales"] != 0 or a["summary"]["m3Sales"] != 0
        )
        if not has_history:
            continue
        group = a["group"] or DEFAULT_GROUP
        if a["d0to15Sales"] > 0:
            status = "NEWLY INACTIVE"
        elif a["d16to30Sales"] > 0:
            status = "FOLLOW UP"
        elif a["d31to60Sales"] > 0:
            status = "URGENT"
        else:
            status = "DORMANT"
        groups.setdefault(group, []).append([
            a["name"], status, a["summary"]["mtdSales"], a["d0to15Sales"], a["d16to30Sales"],
            a["d31to60Sales"], a["olderSales"], a["summary"]["m2Sales"], a["summary"]["m3Sales"],
            a["summary"]["ytdSales"], a["balance"],
        ])
    priority = {"URGENT": 4, "FOLLOW UP": 3, "NEWLY INACTIVE": 2, "DORMANT": 1}
    for group in groups:
        groups[group].sort(key=lambda a: (-priority.get(a[1], 0), -a[9]))
    headers = [
        "Customer", "Status", "MTD Sales", "Last 15 Days Sales", "15 to 30 Days Sales",
        "30 to 60 Days Sales", "Before 60 Days Sales", "2 Months Sales", "3 Months Sales",
        "YTD Sales", "Balance",
    ]
    return _followup_reports("sales_follow_up_", "Sales follow-up", groups, headers)


def collection_follow_ups(ctx):
    groups = {}
    for a in ctx["accounts"]:
        if a["balance"] <= 0:
            continue
        if a["bal30Plus"] > 0:
            status = "URGENT"
        elif a["bal15Plus"] > 0:
            status = "FOLLOW UP"
        else:
            status = "WATCH"
        group = a["group"] or DEFAULT_GROUP
        groups.setdefault(group, []).append([
            a["name"], status, a["summary"]["mtdCollection"], a["summary"]["m2Collection"],
            a["summary"]["m3Collection"], a["balance"], a["bal10Plus"], a["bal15Plus"],
            a["bal20Plus"], a["bal25Plus"], a["bal30Plus"],
        ])
    priority = {"URGENT": 3, "FOLLOW UP": 2, "WATCH": 1}
    for group in groups:
        groups[group].sort(key=lambda a: (-priority.get(a[1], 0), -a[10], -a[7], -a[5]))
    headers = [
        "Customer", "Status", "MTD Collection", "2 Months Collection", "3 Months Collection",
        "Balance", "10+ Days Balance", "15+ Days Balance", "20+ Days Balance",
        "25+ Days Balance", "30+ Days Balance",
    ]
    return _followup_reports("collection_follow_up_", "Collection follow-up", groups, headers)


def _followup_reports(prefix, title, groups, headers):
    reports = []
    for group, rows in groups.items():
        reports.append({
            "id": prefix + group,
            "title": "%s — %s" % (title, group),
            "headers": headers,
            "rows": rows,
            "total": None,
            "key_col": 0,
            "status_header": "Status",
            "followup": True,
        })
    return reports


def _add_count_warning(warnings, mapping, typ, source, suffix):
    keys = list(mapping.keys())
    for key in keys[:WARNING_KEY_LIMIT]:
        warnings.append([typ, source, mapping[key]["name"], str(mapping[key]["count"]) + " " + suffix])
    if len(keys) > WARNING_KEY_LIMIT:
        warnings.append([typ, source, "", str(len(keys) - WARNING_KEY_LIMIT) + " more " + suffix])


def _add_summary_warning(warnings, typ, source, count, detail):
    if count > 0:
        warnings.append([typ, source, "", str(count) + " " + detail])


def source_data_warnings(tables, ctx, selected_phases, inventory=None):
    """Faithful runner: sheet only if core and/or items selected."""
    include_core = "core" in selected_phases
    include_items = "items" in selected_phases
    if not include_core and not include_items:
        return None
    warnings = []
    report_date_label = ctx["reportDate"].strftime("%Y-%m-%d")

    arr = tables.get("arr") if include_core else None
    sales = tables.get("sales") if include_core else None
    receipts = tables.get("receipt") if include_core else None
    items = tables.get("items") if include_items else None

    if include_core:
        for name, table in (("arr", arr), ("sales", sales), ("receipt", receipts)):
            if table is None:
                warnings.append(["Missing source", name, "", "Required sheet not found: " + name])
    if include_items:
        for name in ("items", "stock"):
            if tables.get(name) is None:
                warnings.append(["Missing source", name, "", "Required sheet not found: " + name])

    arr_names = {}
    if arr:
        for r in arr.rows:
            name = clean_text(arr.get(r, "Account Name"))
            if not name:
                continue
            key = name.lower()
            if key in arr_names:
                warnings.append(["Duplicate ARR account", "arr", name, "Duplicates '%s'" % arr_names[key]])
            else:
                arr_names[key] = name
            if "Balance" in arr.index and number_(arr.get(r, "Balance")) < 0:
                warnings.append(["Negative amount", "arr", name, "Balance is negative"])

    if sales:
        unmatched = {}
        future = invalid = negative = no_rep = no_party = 0
        for r in sales.rows:
            party = clean_text(sales.get(r, "Party Name"))
            amount = number_(sales.get(r, "Net Amount"))
            d = _d(r, sales, "Date")
            rep = clean_text(sales.get(r, "Sales Rep"))
            if party == DEFAULT_PARTY or not party:
                no_party += 1
            if rep == DEFAULT_SALES_REP or not rep:
                no_rep += 1
            if party and party.lower() not in arr_names:
                unmatched.setdefault(party.lower(), {"name": party, "count": 0})
                unmatched[party.lower()]["count"] += 1
            if not d:
                invalid += 1
            elif d > ctx["reportDate"]:
                future += 1
            if amount < 0:
                negative += 1
        _add_count_warning(warnings, unmatched, "Unmatched party", "sales", "sales rows not in arr")
        _add_summary_warning(warnings, "Future dates", "sales", future, "rows after %s (excluded from reports)" % report_date_label)
        _add_summary_warning(warnings, "Invalid dates", "sales", invalid, "rows with an unreadable Date")
        _add_summary_warning(warnings, "Negative amount", "sales", negative, "rows with Net Amount < 0")
        _add_summary_warning(warnings, "Default value", "sales", no_rep, "rows using " + DEFAULT_SALES_REP)
        _add_summary_warning(warnings, "Default value", "sales", no_party, "rows using " + DEFAULT_PARTY)

    notes = tables.get("credit_note") if include_core else None
    if notes is not None and "Date" in notes.index and "Net Amount" in notes.index:
        future = invalid = negative = no_party = 0
        unmatched = {}
        for r in notes.rows:
            party = clean_text(notes.get(r, "Party Name"))
            amount = number_(notes.get(r, "Net Amount"))
            d = _d(r, notes, "Date")
            if party == DEFAULT_PARTY or not party:
                no_party += 1
            if party and party.lower() not in arr_names:
                unmatched.setdefault(party.lower(), {"name": party, "count": 0})
                unmatched[party.lower()]["count"] += 1
            if not d:
                invalid += 1
            elif d > ctx["reportDate"]:
                future += 1
            if amount < 0:
                negative += 1
        _add_count_warning(warnings, unmatched, "Unmatched party", "credit_note", "credit notes not in arr")
        _add_summary_warning(warnings, "Future dates", "credit_note", future, "rows after %s (excluded from reports)" % report_date_label)
        _add_summary_warning(warnings, "Invalid dates", "credit_note", invalid, "rows with an unreadable Date")
        _add_summary_warning(warnings, "Negative amount", "credit_note", negative, "rows with Net Amount < 0")
        _add_summary_warning(warnings, "Default value", "credit_note", no_party, "rows using " + DEFAULT_PARTY)

    if receipts:
        unmatched = {}
        non_customer = {}
        future = invalid = negative = investment = 0
        for r in receipts.rows:
            account = clean_text(receipts.get(r, "Account Name"))
            amount = number_(receipts.get(r, "Amount"))
            d = _d(r, receipts, "Date")
            rep = clean_text(receipts.get(r, "Sales Rep"))
            if rep == DEFAULT_RECEIPT_REP or not rep:
                investment += 1
            elif account and not is_collection_customer(account, ctx):
                non_customer.setdefault(account.lower(), {"name": account, "count": 0})
                non_customer[account.lower()]["count"] += 1
            if account and account.lower() not in arr_names:
                unmatched.setdefault(account.lower(), {"name": account, "count": 0})
                unmatched[account.lower()]["count"] += 1
            if not d:
                invalid += 1
            elif d > ctx["reportDate"]:
                future += 1
            if amount < 0:
                negative += 1
        _add_count_warning(warnings, unmatched, "Unmatched party", "receipt", "receipt rows not in arr")
        _add_count_warning(
            warnings, non_customer, "Non-customer receipt", "receipt",
            "receipt rows excluded from collection (not a customer)",
        )
        _add_summary_warning(warnings, "Future dates", "receipt", future, "rows after %s (excluded from reports)" % report_date_label)
        _add_summary_warning(warnings, "Invalid dates", "receipt", invalid, "rows with an unreadable Date")
        _add_summary_warning(warnings, "Negative amount", "receipt", negative, "rows with Amount < 0")
        _add_summary_warning(warnings, "Default value", "receipt", investment, "rows using " + DEFAULT_RECEIPT_REP)

    if include_items and items:
        missing_cost = {}
        future = invalid = negative = 0
        inventory = inventory or {}
        for r in items.rows:
            name = clean_text(items.get(r, "Item Name"))
            qty = number_(items.get(r, "Qty"))
            rate = number_(items.get(r, "Rate"))
            d = _d(r, items, "Date")
            if not d:
                invalid += 1
            elif d > ctx["reportDate"]:
                future += 1
            if qty < 0 or rate < 0:
                negative += 1
            if name and (name not in inventory or inventory[name].get("cost") is None):
                missing_cost[name] = True
        names = list(missing_cost.keys())
        for name in names[:50]:
            warnings.append(["Missing item cost", "items", name, "No valid P.Price in stock"])
        if len(names) > 50:
            warnings.append(["Missing item cost", "items", "", str(len(names) - 50) + " more items with no valid P.Price"])
        _add_summary_warning(warnings, "Future dates", "items", future, "rows after %s (excluded from reports)" % report_date_label)
        _add_summary_warning(warnings, "Invalid dates", "items", invalid, "rows with an unreadable Date")
        _add_summary_warning(warnings, "Negative amount", "items", negative, "rows with Qty < 0 or Rate < 0")

    if len(warnings) > MAX_WARNING_ROWS:
        omitted = len(warnings) - MAX_WARNING_ROWS
        warnings = warnings[:MAX_WARNING_ROWS]
        warnings.append(["Truncated", "", "", str(omitted) + " more warnings omitted"])

    return {
        "id": "source_data_warnings",
        "title": "Source data warnings",
        "headers": ["Type", "Source", "Key", "Detail"],
        "rows": warnings,
        "total": None,
        "key_col": 2,
    }
