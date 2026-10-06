"""All-FY fiscal monthly reports. Key (fy, monthIndex). Do not reuse a 12-slot array."""

from datetime import datetime

from vay.credit_notes import rep_index, rep_on_or_before
from vay.config import DEFAULT_GROUP, DEFAULT_PARTY, DEFAULT_RECEIPT_REP, DEFAULT_SALES_REP
from vay.dates import (
    clean_text,
    fiscal_month_index_dt,
    fy_label,
    number_,
    parse_date,
    total_row,
)
from vay.settlement import is_collection_customer


def _d(row, table, header):
    raw = table.get(row, header)
    if hasattr(raw, "year") and hasattr(raw, "month"):
        return raw
    return parse_date(raw)


def _fy_month(ctx=None):
    from vay.dates import normalize_fy_start_month
    return normalize_fy_start_month((ctx or {}).get("fiscalYearStartMonth"))


def fy_slot(fy_years, d, start_month=None):
    from vay.dates import fiscal_year_start
    fy_start = fiscal_year_start(d, start_month)
    try:
        return fy_years.index(fy_start)
    except ValueError:
        return None


def pair_width(n_fy):
    return n_fy * 26 + 2  # 12*2 + 2 totals per FY, then All FYs pair


def blank_current_fy_pairs(values, fy_index, report_fiscal_index, n_fy):
    """Blank months after report date only in the current (last) FY."""
    if fy_index != n_fy - 1:
        return
    for i in range(report_fiscal_index + 1, 12):
        values[i * 2] = ""
        values[i * 2 + 1] = ""


def fiscal_block_headers(fy_years, report_date, pair=True, start_month=None):
    """Return (row1, row2, merges) for Excel. pair=True → Sales/Collection columns."""
    from vay.dates import fiscal_month_numbers, normalize_fy_start_month

    sm = normalize_fy_start_month(start_month)
    months_cycle = fiscal_month_numbers(sm)
    report_fy_index = len(fy_years) - 1
    report_mi = fiscal_month_index_dt(report_date, sm)
    row1 = []
    row2 = []
    merges = []  # (start_col, end_col, text) 0-based among value cols
    col = 0
    for yi, fy in enumerate(fy_years):
        months = 12
        if pair:
            n = months * 2 + 2
            label_total_a, label_total_b = "Total Sales", "Total Collection"
        else:
            n = months + 1
            label_total_a, label_total_b = "Total", None
        merges.append((col, col + n - 1, fy_label(fy)))
        row1.extend([fy_label(fy)] * n)
        for m in range(12):
            month = months_cycle[m]
            year = fy.year if month >= sm else fy.year + 1
            stamp = datetime(year, month, 1, 12).strftime("%B %Y")
            after = yi == report_fy_index and m > report_mi
            suffix = " [after report date]" if after else ""
            if pair:
                row2.append(stamp + " Sales" + suffix)
                row2.append(stamp + " Collection" + suffix)
            else:
                row2.append(stamp + suffix)
        if pair:
            row2.extend([label_total_a, label_total_b])
        else:
            row2.append(label_total_a)
        col += n
    if pair:
        merges.append((col, col + 1, "All FYs"))
        row1.extend(["All FYs", "All FYs"])
        row2.extend(["Total Sales", "Total Collection"])
    else:
        merges.append((col, col, "All FYs"))
        row1.append("All FYs")
        row2.append("Total")
    return row1, row2, merges


def _accumulate_rep_pairs(tables, ctx, fy_years):
    n = len(fy_years)
    sales = tables["sales"]
    receipts = tables["receipt"]
    reps = {}

    def ensure(rep):
        if rep not in reps:
            reps[rep] = [[0.0] * 24 for _ in range(n)]
        return reps[rep]

    def add(rep, amount, d, kind):
        rep = clean_text(rep) or (DEFAULT_SALES_REP if kind == 0 else DEFAULT_RECEIPT_REP)
        if rep == DEFAULT_RECEIPT_REP:
            return
        if not d or d > ctx["reportDate"]:
            return
        sm = _fy_month(ctx)
        yi = fy_slot(fy_years, d, sm)
        if yi is None:
            return
        ensure(rep)[yi][fiscal_month_index_dt(d, sm) * 2 + kind] += amount

    for r in sales.rows:
        add(sales.get(r, "Sales Rep"), number_(sales.get(r, "Net Amount")), _d(r, sales, "Date"), 0)
    for r in receipts.rows:
        if not is_collection_customer(receipts.get(r, "Account Name"), ctx):
            continue
        add(receipts.get(r, "Sales Rep"), number_(receipts.get(r, "Amount")), _d(r, receipts, "Date"), 1)
    notes = tables.get("credit_note")
    if notes is not None and "Date" in notes.index and "Net Amount" in notes.index:
        lookup = rep_index([
            (sales.get(r, "Party Name"), _d(r, sales, "Date"), sales.get(r, "Sales Rep"))
            for r in sales.rows
        ])
        for r in notes.rows:
            d = _d(r, notes, "Date")
            amount = number_(notes.get(r, "Net Amount"))
            if not d or amount <= 0:
                continue
            rep = rep_on_or_before(lookup, notes.get(r, "Party Name"), d) or DEFAULT_SALES_REP
            add(rep, -amount, d, 0)
    return reps


def _row_from_fy_pairs(label_cells, fy_values, report_mi, n_fy):
    out = list(label_cells)
    all_sales = 0.0
    all_coll = 0.0
    for yi, values in enumerate(fy_values):
        next_vals = list(values)
        tot_s = 0.0
        tot_c = 0.0
        for i in range(0, 24, 2):
            tot_s += next_vals[i]
            tot_c += next_vals[i + 1]
        blank_current_fy_pairs(next_vals, yi, report_mi, n_fy)
        out.extend(next_vals)
        out.extend([tot_s, tot_c])
        all_sales += tot_s
        all_coll += tot_c
    out.extend([all_sales, all_coll])
    return out


def fiscal_sales_rep(tables, ctx):
    fy_years = ctx["fiscalYears"]
    n = len(fy_years)
    sm = _fy_month(ctx)
    report_mi = fiscal_month_index_dt(ctx["reportDate"], sm)
    reps = _accumulate_rep_pairs(tables, ctx, fy_years)
    rows = [_row_from_fy_pairs([rep], reps[rep], report_mi, n) for rep in reps]
    all_s_col = len(rows[0]) - 2 if rows else 0
    rows.sort(key=lambda a: -number_(a[all_s_col]))
    h1, h2, merges = fiscal_block_headers(fy_years, ctx["reportDate"], pair=True, start_month=sm)
    headers = ["Sales Rep"] + h2
    header_row1 = [""] + h1
    total = total_row(rows, 1 + pair_width(n), "Total", 1)
    _blank_total_pairs(total, 1, report_mi, n)
    return {
        "id": "fiscal_monthly_sales_rep_performance_report",
        "title": "Fiscal monthly sales-rep",
        "headers": headers,
        "header_row1": header_row1,
        "merges": [(0, 0, "")] + [(a + 1, b + 1, t) for a, b, t in merges],
        "rows": rows,
        "total": total,
        "key_col": 0,
        "wide": "pair",
        "label_cols": 1,
    }


def _account_months(tables, ctx, fy_years):
    n = len(fy_years)
    sm = _fy_month(ctx)
    arr = tables["arr"]
    group_map = {}
    for r in arr.rows:
        name = clean_text(arr.get(r, "Account Name"))
        if name:
            group_map[name.lower()] = clean_text(arr.get(r, "Group")) or DEFAULT_GROUP
    sales = tables["sales"]
    receipts = tables["receipt"]
    accounts = {}

    def ensure(name):
        name = clean_text(name) or DEFAULT_PARTY
        key = name.lower()
        if key not in accounts:
            accounts[key] = {
                "name": name,
                "group": group_map.get(key, DEFAULT_GROUP),
                "values": [[0.0] * 24 for _ in range(n)],
            }
        return accounts[key]

    for r in sales.rows:
        d = _d(r, sales, "Date")
        if not d or d > ctx["reportDate"]:
            continue
        yi = fy_slot(fy_years, d, sm)
        if yi is None:
            continue
        ensure(sales.get(r, "Party Name"))["values"][yi][fiscal_month_index_dt(d, sm) * 2] += number_(sales.get(r, "Net Amount"))
    notes = tables.get("credit_note")
    if notes is not None and "Date" in notes.index and "Net Amount" in notes.index:
        for r in notes.rows:
            d = _d(r, notes, "Date")
            amount = number_(notes.get(r, "Net Amount"))
            if not d or d > ctx["reportDate"] or amount <= 0:
                continue
            yi = fy_slot(fy_years, d, sm)
            if yi is None:
                continue
            ensure(notes.get(r, "Party Name"))["values"][yi][fiscal_month_index_dt(d, sm) * 2] -= amount
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
        yi = fy_slot(fy_years, d, sm)
        if yi is None:
            continue
        ensure(account)["values"][yi][fiscal_month_index_dt(d, sm) * 2 + 1] += number_(receipts.get(r, "Amount"))
    return list(accounts.values())


def fiscal_account(tables, ctx):
    fy_years = ctx["fiscalYears"]
    n = len(fy_years)
    sm = _fy_month(ctx)
    report_mi = fiscal_month_index_dt(ctx["reportDate"], sm)
    accounts = _account_months(tables, ctx, fy_years)
    ctx["fiscalAccounts"] = accounts
    rows = [_row_from_fy_pairs([a["name"], a["group"]], a["values"], report_mi, n) for a in accounts]
    all_s_col = len(rows[0]) - 2 if rows else 0
    rows.sort(key=lambda a: -number_(a[all_s_col]))
    h1, h2, merges = fiscal_block_headers(fy_years, ctx["reportDate"], pair=True, start_month=sm)
    headers = ["Account Name", "Group"] + h2
    header_row1 = ["", ""] + h1
    total = total_row(rows, 2 + pair_width(n), "Total", 2)
    _blank_total_pairs(total, 2, report_mi, n)
    return {
        "id": "fiscal_monthly_account_performance_report",
        "title": "Fiscal monthly account",
        "headers": headers,
        "header_row1": header_row1,
        "merges": [(0, 1, "")] + [(a + 2, b + 2, t) for a, b, t in merges],
        "rows": rows,
        "total": total,
        "key_col": 0,
        "wide": "pair",
        "label_cols": 2,
    }


def fiscal_group(ctx):
    fy_years = ctx["fiscalYears"]
    n = len(fy_years)
    sm = _fy_month(ctx)
    report_mi = fiscal_month_index_dt(ctx["reportDate"], sm)
    groups = {}
    for a in ctx["fiscalAccounts"]:
        group = a["group"] or DEFAULT_GROUP
        if group not in groups:
            groups[group] = [[0.0] * 24 for _ in range(n)]
        for yi in range(n):
            for i in range(24):
                groups[group][yi][i] += a["values"][yi][i]
    rows = [_row_from_fy_pairs([g], groups[g], report_mi, n) for g in groups]
    all_s_col = len(rows[0]) - 2 if rows else 0
    rows.sort(key=lambda a: -number_(a[all_s_col]))
    h1, h2, merges = fiscal_block_headers(fy_years, ctx["reportDate"], pair=True, start_month=sm)
    headers = ["Group"] + h2
    header_row1 = [""] + h1
    total = total_row(rows, 1 + pair_width(n), "Total", 1)
    _blank_total_pairs(total, 1, report_mi, n)
    return {
        "id": "fiscal_monthly_group_performance_report",
        "title": "Fiscal monthly group",
        "headers": headers,
        "header_row1": header_row1,
        "merges": [(0, 0, "")] + [(a + 1, b + 1, t) for a, b, t in merges],
        "rows": rows,
        "total": total,
        "key_col": 0,
        "wide": "pair",
        "label_cols": 1,
    }


def _blank_total_pairs(row, offset, report_mi, n_fy):
    last_fy = n_fy - 1
    base = offset + last_fy * 26
    for i in range(report_mi + 1, 12):
        row[base + i * 2] = ""
        row[base + i * 2 + 1] = ""


def current_fy_pair_slice(row, label_cols, n_fy):
    """Extract the last FY's 24 month cells + that FY totals (for golden compare)."""
    last = n_fy - 1
    start = label_cols + last * 26
    return row[:label_cols] + row[start:start + 26]
