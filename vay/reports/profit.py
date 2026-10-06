"""P&L and expense reports. Aggregators do not read a single ctx.phase.

P&L uses all-FY month columns. Expenses stay MTD / 2m / 3m / report-FY YTD.
Operating P&L lines only; Purchase / Bank Inward / RD stay on expense sheets.
Mapped payment names win (Carriage inward and AMAL_TRADERS are Office).
"""

import re

from vay.config import (
    EXPENSE_CATEGORIES,
    OPERATING_EXPENSE_CATEGORIES,
    SALES_TAX_INCLUSIVE_RATE,
)
from vay.dates import (
    between_,
    clean_text,
    fiscal_month_index_dt,
    fiscal_year_start,
    inclusive_tax,
    normalize_fy_start_month,
    number_,
    parse_date,
    total_row,
)
from vay.reports.fiscal import fiscal_block_headers

NON_OPERATING_CATEGORIES = frozenset({
    "Investment Returns", "Purchase", "Bank Inward", "RD",
})


def active_expense_categories(payment_categories=None):
    """Default category order, then any extra keys from org/pack map."""
    keys = list(EXPENSE_CATEGORIES)
    for name in (payment_categories or {}):
        label = clean_text(name)
        if label and label not in keys:
            keys.append(label)
    if "Other" not in keys:
        keys.append("Other")
    return keys


def active_operating_categories(all_cats=None):
    cats = list(all_cats) if all_cats is not None else list(OPERATING_EXPENSE_CATEGORIES)
    return [c for c in cats if c not in NON_OPERATING_CATEGORIES]


def payment_key(name):
    return re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", clean_text(name).lower())).strip()


def payment_key_compact(name):
    return re.sub(r"\s+", "", payment_key(name))


def payment_category_map(categories=None):
    """Build lookup from category → account names map (org/pack config)."""
    mapping = {}
    for category, names in (categories or {}).items():
        for name in names or []:
            mapping[payment_key(name)] = category
            mapping[payment_key_compact(name)] = category
    return mapping


def payment_category(name, categories=None):
    key = payment_key(name)
    mapping = payment_category_map(categories)
    if key in mapping:
        return mapping[key]
    compact = payment_key_compact(name)
    if compact in mapping:
        return mapping[compact]
    if re.search(r"(^|\s)salary$", key):
        return "Salary"
    if re.search(r"\binvestment\b", key):
        return "Investment Returns"
    if re.search(r"(^|\s)(vendor|traders)$", key) or key == "carriage inward":
        return "Purchase"
    return "Other"


def _fy_month(ctx=None):
    return normalize_fy_start_month((ctx or {}).get("fiscalYearStartMonth"))


def _d(row, table, header):
    raw = table.get(row, header)
    if hasattr(raw, "year") and hasattr(raw, "month"):
        return raw
    return parse_date(raw)


def fy_slot(fy_years, d, start_month=None):
    fy_start = fiscal_year_start(d, start_month)
    try:
        return fy_years.index(fy_start)
    except ValueError:
        return None


def _new_expense():
    return {"mtd": 0.0, "m2": 0.0, "m3": 0.0, "ytd": 0.0}


def _add_expense(summary, amount, d, ctx):
    if between_(d, ctx["monthStart"], ctx["reportDate"]):
        summary["mtd"] += amount
    if between_(d, ctx["last2MonthsStart"], ctx["reportDate"]):
        summary["m2"] += amount
    if between_(d, ctx["last3MonthsStart"], ctx["reportDate"]):
        summary["m3"] += amount
    if between_(d, ctx["fiscalYearStart"], ctx["reportDate"]):
        summary["ytd"] += amount


def payment_summaries(tables, ctx, include_cogs=True):
    """include_cogs True for P&L; False not used for expenses (expenses don't need monthly COGS)."""
    fy_years = ctx["fiscalYears"]
    sm = _fy_month(ctx)
    categories = ctx.get("payment_categories") or {}
    cat_list = active_expense_categories(categories)
    n = len(fy_years)
    monthly = {c: [[0.0] * 12 for _ in range(n)] for c in cat_list}
    by_category = {c: _new_expense() for c in cat_list}
    by_account = {}
    sales_monthly = [[0.0] * 12 for _ in range(n)]
    cogs_monthly = [[0.0] * 12 for _ in range(n)]

    if include_cogs:
        sales = tables["sales"]
        for r in sales.rows:
            d = _d(r, sales, "Date")
            if not d or d > ctx["reportDate"]:
                continue
            yi = fy_slot(fy_years, d, sm)
            if yi is None:
                continue
            sales_monthly[yi][fiscal_month_index_dt(d, sm)] += number_(sales.get(r, "Net Amount"))
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
                sales_monthly[yi][fiscal_month_index_dt(d, sm)] -= amount
        inventory = ctx["inventory"]
        items = tables["items"]
        for r in items.rows:
            name = clean_text(items.get(r, "Item Name"))
            qty = number_(items.get(r, "Qty"))
            d = _d(r, items, "Date")
            if not name or not d or qty <= 0 or d > ctx["reportDate"]:
                continue
            yi = fy_slot(fy_years, d, sm)
            if yi is None:
                continue
            inv = inventory.get(name)
            if not inv or inv["cost"] is None:
                continue
            cogs_monthly[yi][fiscal_month_index_dt(d, sm)] += qty * inv["cost"]

    payments = tables["payments"]
    for r in payments.rows:
        d = _d(r, payments, "Date")
        name = clean_text(payments.get(r, "Account Name"))
        amount = number_(payments.get(r, "Amount"))
        if not name or not d or d > ctx["reportDate"]:
            continue
        category = payment_category(name, categories)
        if category not in by_category:
            by_category[category] = _new_expense()
            monthly[category] = [[0.0] * 12 for _ in range(n)]
            if category not in cat_list:
                cat_list.append(category)
        if name not in by_account:
            by_account[name] = {"name": name, "category": category, "summary": _new_expense()}
        _add_expense(by_account[name]["summary"], amount, d, ctx)
        _add_expense(by_category[category], amount, d, ctx)
        yi = fy_slot(fy_years, d, sm)
        if yi is not None:
            monthly[category][yi][fiscal_month_index_dt(d, sm)] += amount

    return {
        "monthly": monthly,
        "byCategory": by_category,
        "byAccount": by_account,
        "salesMonthly": sales_monthly,
        "cogsMonthly": cogs_monthly,
        "n_fy": n,
        "categories": cat_list,
        "operatingCategories": active_operating_categories(cat_list),
    }


def _wide_line(label, fy_months, report_mi, n):
    out = [label]
    overall = 0.0
    for yi, months in enumerate(fy_months):
        vals = list(months)
        tot = sum(vals)
        if yi == n - 1:
            for i in range(report_mi + 1, 12):
                vals[i] = ""
        out.extend(vals)
        out.append(tot)
        overall += tot
    out.append(overall)
    return out


def monthly_profit_report(data, ctx):
    n = data["n_fy"]
    sm = _fy_month(ctx)
    report_mi = fiscal_month_index_dt(ctx["reportDate"], sm)
    sales = data["salesMonthly"]
    tax_rate = ctx.get("sales_tax_inclusive_rate")
    if tax_rate is None:
        tax_rate = SALES_TAX_INCLUSIVE_RATE
    tax = [[inclusive_tax(v, tax_rate) for v in year] for year in sales]
    sale_before = [[sales[y][i] - tax[y][i] for i in range(12)] for y in range(n)]
    cogs = data["cogsMonthly"]
    operating_cats = data.get("operatingCategories") or active_operating_categories(
        data.get("categories") or active_expense_categories(ctx.get("payment_categories"))
    )
    # Investment Returns is always shown as its own P&L line when present
    investment = data["monthly"].get("Investment Returns") or [[0.0] * 12 for _ in range(n)]
    operating = [data["monthly"][c] for c in operating_cats if c != "Investment Returns" and c in data["monthly"]]
    sales_profit = []
    for y in range(n):
        year = []
        for i in range(12):
            expenses = sum(op[y][i] for op in operating)
            year.append(sale_before[y][i] - cogs[y][i] - expenses - investment[y][i])
        sales_profit.append(year)

    def line(label, values):
        return _wide_line(label, values, report_mi, n)

    rows = [
        line("Total Sale", sales),
        line("Tax received", tax),
        line("Sale before tax", sale_before),
        line("Less: Cost of items sold", cogs),
    ]
    for category in operating_cats:
        if category == "Investment Returns":
            continue
        if category not in data["monthly"]:
            continue
        rows.append(line("Less: " + category, data["monthly"][category]))
    rows.append(line("Less: Investment Returns", investment))
    rows.append(line("Sales profit", sales_profit))

    h1, h2, merges = fiscal_block_headers(
        ctx["fiscalYears"], ctx["reportDate"], pair=False, start_month=sm,
    )
    headers = ["Component"] + h2
    header_row1 = [""] + h1
    return {
        "id": "monthly_profit_report",
        "title": "Monthly P&L",
        "headers": headers,
        "header_row1": header_row1,
        "merges": [(0, 0, "")] + [(a + 1, b + 1, t) for a, b, t in merges],
        "rows": rows,
        "total": None,
        "key_col": 0,
        "wide": "month",
        "label_cols": 1,
        "n_fy": n,
    }


def expense_by_category(data):
    rows = []
    cats = data.get("categories") or list(data.get("byCategory") or {})
    for category in cats:
        s = data["byCategory"].get(category) or _new_expense()
        rows.append([category, s["mtd"], s["m2"], s["m3"], s["ytd"]])
    return {
        "id": "expense_by_category",
        "title": "Expense by category",
        "headers": ["Category", "MTD", "2 Months", "3 Months", "YTD"],
        "rows": rows,
        "total": total_row(rows, 5, "Total", 1),
        "key_col": 0,
    }


def expense_by_account(data):
    rows = []
    for name, a in data["byAccount"].items():
        s = a["summary"]
        rows.append([a["name"], a["category"], s["mtd"], s["m2"], s["m3"], s["ytd"]])
    rows.sort(key=lambda a: -a[5])
    return {
        "id": "expense_by_account",
        "title": "Expense by account",
        "headers": ["Account Name", "Category", "MTD", "2 Months", "3 Months", "YTD"],
        "rows": rows,
        "total": total_row(rows, 6, "Total", 2),
        "key_col": 0,
    }


def unmapped_payment_accounts(data):
    rows = []
    for name, a in data["byAccount"].items():
        if a["category"] == "Other":
            rows.append([a["name"], a["summary"]["ytd"]])
    rows.sort(key=lambda a: -a[1])
    return {
        "id": "unmapped_payment_accounts",
        "title": "Unmapped payment accounts",
        "headers": ["Account Name", "YTD Amount"],
        "rows": rows,
        "total": total_row(rows, 2, "Total", 1) if rows else None,
        "key_col": 0,
    }
