"""Item reports. Item Name vs stock is case-sensitive after trim.

Period reports (sales/profit/exceptions) stay report-date windows.
Monthly qty/profit are all-FY wide. New rule: any SKU with qty (or valid-cost profit)
through the report date appears. Avg/Stock/Status is one trailing block.
"""

from datetime import datetime

from vay.dates import (
    between_,
    clean_text,
    fiscal_month_index_dt,
    normalize_fy_start_month,
    number_,
    parse_date,
    total_row,
)
from vay.reports.fiscal import fiscal_block_headers


def _d(row, table, header):
    raw = table.get(row, header)
    if hasattr(raw, "year") and hasattr(raw, "month"):
        return raw
    return parse_date(raw)


def stock_map(tables):
    """Item names are case-sensitive after trim (do not lowercase)."""
    stock = tables["stock"]
    mapping = {}
    for r in stock.rows:
        name = clean_text(stock.get(r, "Item Name"))
        if not name:
            continue
        qty = number_(stock.get(r, "Qty"))
        raw_cost = stock.get(r, "P.Price")
        try:
            parsed_cost = float(str(raw_cost).replace(",", "").strip())
            if parsed_cost != parsed_cost:
                parsed_cost = None
        except (TypeError, ValueError):
            parsed_cost = None
        if name not in mapping:
            mapping[name] = {"qty": 0.0, "value": 0.0, "pricedQty": 0.0, "fallbackCost": None, "cost": None}
        mapping[name]["qty"] += qty
        if parsed_cost is not None:
            mapping[name]["fallbackCost"] = parsed_cost
            if qty > 0:
                mapping[name]["value"] += qty * parsed_cost
                mapping[name]["pricedQty"] += qty
    for name, data in mapping.items():
        if data["pricedQty"] > 0:
            data["cost"] = data["value"] / data["pricedQty"]
        else:
            data["cost"] = data["fallbackCost"]
    return mapping


def fy_slot(fy_years, d, start_month=None):
    from vay.dates import fiscal_year_start
    fy_start = fiscal_year_start(d, start_month)
    try:
        return fy_years.index(fy_start)
    except ValueError:
        return None


def item_summaries(tables, ctx, compute_profit=True):
    """Always compute profit when asked; do not read ctx.phase."""
    items = tables["items"]
    inventory = ctx["inventory"]
    fy_years = ctx["fiscalYears"]
    sm = normalize_fy_start_month(ctx.get("fiscalYearStartMonth"))
    n = len(fy_years)
    report_mi = fiscal_month_index_dt(ctx["reportDate"], sm)
    recent_start = datetime(ctx["reportDate"].year, ctx["reportDate"].month, 1, 12)
    # last 3 completed calendar months: month-3 first day through previousMonthEnd
    rm = ctx["reportDate"].month - 3
    ry = ctx["reportDate"].year
    while rm <= 0:
        rm += 12
        ry -= 1
    recent_start = datetime(ry, rm, 1, 12)

    sales = {}
    profit = {}
    missing = {}
    monthly_profit = {}
    monthly_qty = {}

    for r in items.rows:
        name = clean_text(items.get(r, "Item Name"))
        qty = number_(items.get(r, "Qty"))
        rate = number_(items.get(r, "Rate"))
        d = _d(r, items, "Date")
        if not name or not d or qty <= 0 or d > ctx["reportDate"]:
            continue

        yi = fy_slot(fy_years, d, sm)
        in_recent = between_(d, recent_start, ctx["previousMonthEnd"])
        if yi is not None or in_recent:
            if name not in monthly_qty:
                monthly_qty[name] = {"monthly": [[0.0] * 12 for _ in range(n)], "recentQty": 0.0}
            if yi is not None:
                monthly_qty[name]["monthly"][yi][fiscal_month_index_dt(d, sm)] += qty
            if in_recent:
                monthly_qty[name]["recentQty"] += qty

        if rate < 0:
            continue
        if name not in sales:
            sales[name] = {"mtdQty": 0.0, "mtd": 0.0, "lastMonth": 0.0, "m3": 0.0, "ytd": 0.0}
        amount = qty * rate
        if between_(d, ctx["monthStart"], ctx["reportDate"]):
            sales[name]["mtdQty"] += qty
            sales[name]["mtd"] += amount
        if between_(d, ctx["previousMonthStart"], ctx["previousMonthEnd"]):
            sales[name]["lastMonth"] += amount
        if between_(d, ctx["last3MonthsStart"], ctx["reportDate"]):
            sales[name]["m3"] += amount
        if between_(d, ctx["fiscalYearStart"], ctx["reportDate"]):
            sales[name]["ytd"] += amount

        if name not in inventory or inventory[name]["cost"] is None:
            missing[name] = "Missing valid P.Price in stock"
            continue
        if not compute_profit:
            continue
        profit_amount = (rate - inventory[name]["cost"]) * qty
        if name not in profit:
            profit[name] = {"mtdQty": 0.0, "mtd": 0.0, "lastMonth": 0.0, "m3": 0.0, "ytd": 0.0}
        if between_(d, ctx["monthStart"], ctx["reportDate"]):
            profit[name]["mtdQty"] += qty
            profit[name]["mtd"] += profit_amount
        if between_(d, ctx["previousMonthStart"], ctx["previousMonthEnd"]):
            profit[name]["lastMonth"] += profit_amount
        if between_(d, ctx["last3MonthsStart"], ctx["reportDate"]):
            profit[name]["m3"] += profit_amount
        if yi is not None:
            profit[name]["ytd_all"] = profit[name].get("ytd_all", 0.0) + profit_amount
        if between_(d, ctx["fiscalYearStart"], ctx["reportDate"]):
            profit[name]["ytd"] += profit_amount
        if yi is not None:
            if name not in monthly_profit:
                monthly_profit[name] = [[0.0] * 12 for _ in range(n)]
            monthly_profit[name][yi][fiscal_month_index_dt(d, sm)] += profit_amount

    sales_rows = [[name, s["mtdQty"], s["mtd"], s["lastMonth"], s["m3"], s["ytd"]] for name, s in sales.items()]
    sales_rows.sort(key=lambda a: -a[5])
    profit_rows = [[name, s["mtdQty"], s["mtd"], s["lastMonth"], s["m3"], s["ytd"]] for name, s in profit.items()]
    profit_rows.sort(key=lambda a: -a[5])

    def wide_month_row(name, fy_months, extra=None):
        out = [name]
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
        if extra:
            out.extend(extra)
        return out

    monthly_profit_rows = []
    for name, fy_months in monthly_profit.items():
        monthly_profit_rows.append(wide_month_row(name, fy_months))
    monthly_profit_rows.sort(key=lambda a: -number_(a[-1]))
    profit_width = 1 + n * 13 + 1
    monthly_profit_total = total_row(monthly_profit_rows, profit_width, "Total", 1)
    last_base = 1 + (n - 1) * 13
    for i in range(report_mi + 1, 12):
        monthly_profit_total[last_base + i] = ""

    monthly_qty_rows = []
    for name, data in monthly_qty.items():
        average = data["recentQty"] / 3.0
        stock_qty = inventory[name]["qty"] if name in inventory else 0.0
        status = "OK"
        if average > 0 and stock_qty > average:
            status = "EXCESS STOCK"
        elif average > 0 and stock_qty < average:
            status = "LOW STOCK"
        monthly_qty_rows.append(wide_month_row(name, data["monthly"], [average, stock_qty, status]))
    # sort by overall total (before avg/stock/status)
    monthly_qty_rows.sort(key=lambda a: -number_(a[-4]))

    h1, h2, merges = fiscal_block_headers(fy_years, ctx["reportDate"], pair=False, start_month=sm)
    qty_h2 = h2 + ["Avg Last 3 Completed Months", "Current Stock", "Stock Status"]
    qty_h1 = [""] + h1 + ["", "", ""]
    profit_h1 = [""] + h1
    profit_h2 = ["Item Name"] + h2
    qty_headers = ["Item Name"] + qty_h2

    return {
        "salesRows": sales_rows,
        "profitRows": profit_rows,
        "missingRows": [[n, missing[n]] for n in missing],
        "monthlyProfitRows": monthly_profit_rows,
        "monthlyProfitTotal": monthly_profit_total,
        "monthlyQtyRows": monthly_qty_rows,
        "profit_headers": profit_h2,
        "profit_header_row1": profit_h1,
        "profit_merges": [(0, 0, "")] + [(a + 1, b + 1, t) for a, b, t in merges],
        "qty_headers": qty_headers,
        "qty_header_row1": qty_h1,
        "qty_merges": [(0, 0, "")] + [(a + 1, b + 1, t) for a, b, t in merges],
        "n_fy": n,
    }


def item_wise_sales(data):
    rows = data["salesRows"]
    return {
        "id": "item_wise_sales",
        "title": "Item-wise sales",
        "headers": ["Item Name", "MTD Qty", "MTD Sales", "Last Month Sales", "Last 3 Months Sales", "YTD Sales"],
        "rows": rows,
        "total": total_row(rows, 6, "Total", 1),
        "key_col": 0,
    }


def item_wise_profit(data):
    rows = data["profitRows"]
    return {
        "id": "item_wise_profit",
        "title": "Item-wise profit",
        "headers": ["Item Name", "MTD Qty", "MTD Profit", "Last Month Profit", "Last 3 Months Profit", "YTD Profit"],
        "rows": rows,
        "total": total_row(rows, 6, "Total", 1),
        "key_col": 0,
    }


def item_cost_exceptions(data):
    return {
        "id": "item_cost_exceptions",
        "title": "Item cost exceptions",
        "headers": ["Item Name", "Issue"],
        "rows": data["missingRows"],
        "total": None,
        "key_col": 0,
    }


def item_monthly_profit(data):
    return {
        "id": "item_wise_monthly_profit",
        "title": "Item monthly profit",
        "headers": data["profit_headers"],
        "header_row1": data["profit_header_row1"],
        "merges": data["profit_merges"],
        "rows": data["monthlyProfitRows"],
        "total": data["monthlyProfitTotal"],
        "key_col": 0,
        "wide": "month",
        "label_cols": 1,
        "n_fy": data["n_fy"],
    }


def item_monthly_qty(data):
    return {
        "id": "item_wise_monthly_qty",
        "title": "Item monthly quantity",
        "headers": data["qty_headers"],
        "header_row1": data["qty_header_row1"],
        "merges": data["qty_merges"],
        "rows": data["monthlyQtyRows"],
        "total": None,
        "key_col": 0,
        "wide": "month",
        "label_cols": 1,
        "status_header": "Stock Status",
        "n_fy": data["n_fy"],
        "trailing": 3,
    }
