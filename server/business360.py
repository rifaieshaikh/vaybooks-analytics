"""Company 360. Frozen on the report snapshot. Does not feed generate()."""

from __future__ import annotations

from vay.config import OPERATING_EXPENSE_CATEGORIES
from vay.dates import fiscal_year_start, parse_date

OPERATING = tuple(OPERATING_EXPENSE_CATEGORIES)
COST_NOTE = "Item cost is the current stock purchase price times quantity."
EMPTY_MESSAGE = "Create the report again. The Business view is saved with that report."
BLOCK = 13  # 12 months plus the fiscal-year total
OVERDUE_KEYS = ("d30_45", "d45_60", "d60_90", "d90")
AGE_KEYS = ("d0_15", "d15_30", "d30_45", "d45_60", "d60_90", "d90")
AGE_LABELS = {
    "d0_15": "0–15",
    "d15_30": "15–30",
    "d30_45": "30–45",
    "d45_60": "45–60",
    "d60_90": "60–90",
    "d90": "90+",
}


def empty_business():
    return {"empty": True, "name": "Business", "message": EMPTY_MESSAGE}


def _round(value, places=2):
    if value is None or value == "":
        return None
    try:
        return round(float(value), places)
    except (TypeError, ValueError):
        return None


def _find(reports, report_id):
    for report in reports or []:
        if (report or {}).get("id") == report_id:
            return report
    return None


def _line_map(report):
    out = {}
    for row in (report or {}).get("rows") or []:
        if not row:
            continue
        label = str(row[0] or "").strip()
        if label:
            out[label] = row
    return out


def _at(row, col):
    if not row or col is None or col < 0 or col >= len(row):
        return None
    value = row[col]
    if value == "" or value is None:
        return None
    return _round(value)


def _cell(value, unavailable=False, reason=""):
    if unavailable:
        return {"value": None, "unavailable": True, "reason": reason or "Unavailable"}
    return {"value": _round(value), "unavailable": False, "reason": ""}


def _flow(value, prior=None, prior_year=None, target=None):
    return {
        "value": _round(value),
        "prior": _round(prior),
        "prior_year": _round(prior_year),
        "target": _round(target),
    }


def _profit_layout(report):
    headers = list((report or {}).get("headers") or [])
    n = int((report or {}).get("n_fy") or 0)
    label_cols = int((report or {}).get("label_cols") or 1)
    if (report or {}).get("wide") != "month" or n < 1:
        return None
    overall = label_cols + n * BLOCK
    if len(headers) <= overall:
        return None
    months = []
    fy_totals = []
    for yi in range(n):
        base = label_cols + yi * BLOCK
        for mi in range(12):
            months.append((yi, mi, base + mi))
        fy_totals.append(base + 12)
    return {"headers": headers, "n": n, "months": months, "fy_totals": fy_totals, "overall": overall}


def _current_month(layout, sale_row):
    current_fy = layout["n"] - 1
    found = None
    for yi, mi, col in layout["months"]:
        if yi != current_fy:
            continue
        header = str(layout["headers"][col] if col < len(layout["headers"]) else "")
        if "[after report date]" in header.lower():
            continue
        if _at(sale_row, col) is None:
            continue
        found = (yi, mi, col)
    return found


def _prior_month(layout, current):
    if not current:
        return None
    prev = None
    for slot in layout["months"]:
        if slot == current:
            return prev
        prev = slot
    return None


def _month_last_year(layout, current):
    if not current or current[0] < 1:
        return None
    yi, mi, _col = current
    for slot in layout["months"]:
        if slot[0] == yi - 1 and slot[1] == mi:
            return slot
    return None


def _period_profit(lines, col, margin_ok, payments_ok, margin_reason, payments_reason):
    sale = _at(lines.get("Sale before tax"), col)
    cogs_row = lines.get("Less: Cost of items sold")
    cogs = _at(cogs_row, col) if cogs_row else None
    opex = 0.0
    opex_seen = False
    for name in OPERATING:
        row = lines.get("Less: " + name)
        if not row:
            continue
        opex_seen = True
        amount = _at(row, col)
        if amount is not None:
            opex += amount
    if not opex_seen:
        opex = None
    else:
        opex = round(opex, 2)
    sales_profit = _at(lines.get("Sales profit"), col)
    gross = None
    if sale is not None and cogs is not None:
        gross = round(sale - cogs, 2)
    margin_reason = margin_reason or "Missing item cost"
    pay_reason = payments_reason or "Payments were not imported"
    gross_cell = _cell(gross, not margin_ok or cogs is None, margin_reason if not margin_ok or cogs is None else "")
    if margin_ok and cogs is None:
        gross_cell = _cell(None, True, "Cost of items sold is not on the profit report")
    opex_cell = _cell(opex, not payments_ok, pay_reason)
    ebitda_reason = ""
    ebitda_bad = False
    if not margin_ok or cogs is None:
        ebitda_bad = True
        ebitda_reason = gross_cell["reason"]
    elif not payments_ok:
        ebitda_bad = True
        ebitda_reason = pay_reason
    ebitda = None
    if not ebitda_bad and gross is not None and opex is not None:
        ebitda = round(gross - opex, 2)
    margin = None
    if gross is not None and sale:
        margin = round(100.0 * gross / sale, 1)
    margin_cell = _cell(margin, gross_cell["unavailable"], gross_cell["reason"])
    ratio = None
    if opex is not None and sale:
        ratio = round(100.0 * opex / sale, 1)
    ratio_cell = _cell(ratio, opex_cell["unavailable"], opex_cell["reason"])
    return {
        "sale_before_tax": sale,
        "gross_profit": gross_cell,
        "operating_expenses": opex_cell,
        "ebitda": _cell(ebitda, ebitda_bad, ebitda_reason),
        "sales_profit": sales_profit,
        "gross_margin_pct": margin_cell,
        "expense_ratio_pct": ratio_cell,
    }


def profit_periods(report, margin_status="eligible", margin_reason="", payments_present=True):
    """Overall, current fiscal year, and current month from a monthly P&L grid."""
    layout = _profit_layout(report)
    if not layout:
        reason = "Profit report was not created"
        blank = _period_profit({}, None, False, False, reason, reason)
        return {"cost_note": COST_NOTE, "overall": blank, "fy": blank, "month": blank, "available": False}
    lines = _line_map(report)
    margin_ok = margin_status == "eligible"
    current = _current_month(layout, lines.get("Sale before tax"))
    prior_m = _prior_month(layout, current)
    year_m = _month_last_year(layout, current)
    fy_col = layout["fy_totals"][-1]
    prior_fy = layout["fy_totals"][-2] if layout["n"] >= 2 else None

    def at(slot):
        if not slot:
            return None
        return _period_profit(lines, slot[2], margin_ok, payments_present, margin_reason, "")

    overall = _period_profit(lines, layout["overall"], margin_ok, payments_present, margin_reason, "")
    fy = _period_profit(lines, fy_col, margin_ok, payments_present, margin_reason, "")
    month = at(current) or _period_profit({}, None, margin_ok, payments_present, margin_reason, "")
    fy["prior"] = _period_profit(lines, prior_fy, margin_ok, payments_present, margin_reason, "") if prior_fy is not None else None
    month["prior"] = at(prior_m)
    month["prior_year"] = at(year_m)
    overall["prior"] = None
    overall["prior_year"] = None
    fy["prior_year"] = None
    return {
        "cost_note": COST_NOTE,
        "available": True,
        "overall": overall,
        "fy": fy,
        "month": month,
    }


def _header_index(headers, name):
    try:
        return list(headers).index(name)
    except ValueError:
        return -1


def _total_amount(report, header):
    if not report:
        return None
    idx = _header_index(report.get("headers") or [], header)
    total = report.get("total") or []
    if idx < 0 or idx >= len(total):
        return None
    return _round(total[idx])


def _score_value(scorecard, metric_id, field):
    for row in (scorecard or {}).get("rows") or []:
        if row.get("id") != metric_id:
            continue
        cell = row.get(field) or {}
        return _round(cell.get("value"))
    return None


def _fy_pair_totals(report):
    """Per fiscal-year and all-years sales and collection from a pair report total row."""
    if not report:
        return [], None
    headers = report.get("headers") or []
    row1 = report.get("header_row1") or []
    total = report.get("total") or []
    blocks = {}
    order = []
    overall = None
    for i, name in enumerate(headers):
        if i >= len(total):
            break
        label = str(name or "")
        fy = str(row1[i] if i < len(row1) else "")
        if label not in ("Total Sales", "Total Collection"):
            continue
        amount = _round(total[i])
        if fy == "All FYs":
            overall = overall or {"sales": None, "collection": None}
            if label == "Total Sales":
                overall["sales"] = amount
            else:
                overall["collection"] = amount
            continue
        if fy not in blocks:
            blocks[fy] = {"sales": None, "collection": None}
            order.append(fy)
        if label == "Total Sales":
            blocks[fy]["sales"] = amount
        else:
            blocks[fy]["collection"] = amount
    return [blocks[fy] for fy in order], overall


def _month_pairs(report):
    if not report:
        return []
    headers = report.get("headers") or []
    total = report.get("total") or []
    pairs = []
    i = 0
    while i < len(headers) - 1:
        sales_h = str(headers[i] or "")
        coll_h = str(headers[i + 1] or "")
        if sales_h.endswith(" Sales") and "Total" not in sales_h and coll_h.endswith(" Collection"):
            if "[after report date]" not in sales_h.lower():
                pairs.append({
                    "sales": _round(total[i] if i < len(total) else None),
                    "collection": _round(total[i + 1] if i + 1 < len(total) else None),
                })
            i += 2
            continue
        i += 1
    return pairs


def _gap_rate(sales, collection):
    if sales is None and collection is None:
        return None, None
    sales_n = 0.0 if sales is None else sales
    coll_n = 0.0 if collection is None else collection
    gap = round(sales_n - coll_n, 2)
    rate = round(100.0 * coll_n / sales_n, 1) if sales_n else None
    return gap, rate


def _flow_periods(reports, scorecard):
    perf = _find(reports, "sales_rep_performance_report")
    fiscal = _find(reports, "fiscal_monthly_sales_rep_performance_report")
    mtd_sales = _total_amount(perf, "MTD Sales")
    mtd_coll = _total_amount(perf, "MTD Collection")
    ytd_sales = _total_amount(perf, "YTD Sales")
    ytd_coll = _total_amount(perf, "YTD Collection")
    fy_rows, overall_pair = _fy_pair_totals(fiscal)
    if ytd_sales is None and fy_rows:
        ytd_sales = fy_rows[-1]["sales"]
        ytd_coll = fy_rows[-1]["collection"]
    prior_fy = fy_rows[-2] if len(fy_rows) >= 2 else {"sales": None, "collection": None}
    months = _month_pairs(fiscal)
    if mtd_sales is None and months:
        mtd_sales = months[-1]["sales"]
        mtd_coll = months[-1]["collection"]
    prior_month = months[-2] if len(months) >= 2 else {"sales": None, "collection": None}
    overall_sales = (overall_pair or {}).get("sales")
    overall_coll = (overall_pair or {}).get("collection")
    sales_target = _score_value(scorecard, "sales_mtd", "target")
    coll_target = _score_value(scorecard, "collections_mtd", "target")
    month_sales_prior_year = _score_value(scorecard, "sales_mtd", "prior_year")
    month_coll_prior_year = _score_value(scorecard, "collections_mtd", "prior_year")
    if _score_value(scorecard, "sales_mtd", "current") is not None:
        mtd_sales = _score_value(scorecard, "sales_mtd", "current")
    if _score_value(scorecard, "collections_mtd", "current") is not None:
        mtd_coll = _score_value(scorecard, "collections_mtd", "current")
    if _score_value(scorecard, "sales_mtd", "prior") is not None:
        prior_month = {
            "sales": _score_value(scorecard, "sales_mtd", "prior"),
            "collection": _score_value(scorecard, "collections_mtd", "prior"),
        }

    def pack(sales, collection, prior_sales=None, prior_coll=None, year_sales=None, year_coll=None, sales_t=None, coll_t=None):
        gap, rate = _gap_rate(sales, collection)
        prior_gap, prior_rate = _gap_rate(prior_sales, prior_coll)
        year_gap, year_rate = _gap_rate(year_sales, year_coll)
        return {
            "sales": _flow(sales, prior_sales, year_sales, sales_t),
            "collection": _flow(collection, prior_coll, year_coll, coll_t),
            "gap": _flow(gap, prior_gap, year_gap),
            "rate": _flow(rate, prior_rate, year_rate),
        }

    return {
        "overall": pack(overall_sales, overall_coll),
        "fy": pack(ytd_sales, ytd_coll, prior_fy.get("sales"), prior_fy.get("collection")),
        "month": pack(
            mtd_sales, mtd_coll,
            prior_month.get("sales"), prior_month.get("collection"),
            month_sales_prior_year, month_coll_prior_year,
            sales_target, coll_target,
        ),
        "ytd_sales": ytd_sales,
    }


def _sum_buckets(rows):
    totals = {key: 0.0 for key in AGE_KEYS}
    for row in rows or []:
        nested = row.get("owe_buckets") or {}
        for key in AGE_KEYS:
            value = row.get(key)
            if value is None:
                value = nested.get(key) or 0
            totals[key] += float(value or 0)
    return {key: round(value, 2) for key, value in totals.items()}


def _receivables(views, ytd_sales, report_date, targets, eligibility, start_month=None):
    directory = (views or {}).get("directory") or {}
    counts = directory.get("counts") or {}
    buckets = _sum_buckets(directory.get("rows") or [])
    overdue = round(sum(buckets[key] for key in OVERDUE_KEYS), 2)
    ar_state = (eligibility or {}).get("ar_balance") or {}
    ar_ok = ar_state.get("status") == "eligible"
    ar_reason = ar_state.get("reason") or "Unavailable"
    due = _round(counts.get("due_total"))
    ar_cell = _cell(due, not ar_ok, ar_reason)
    if ar_cell["unavailable"]:
        ar_cell["target"] = None
    else:
        ar_cell["target"] = _round((targets or {}).get("ar_balance"))
    dso = None
    as_of = parse_date(report_date) if report_date else None
    if ar_ok and due is not None and ytd_sales and as_of:
        start = fiscal_year_start(as_of, start_month)
        days = max(1, (as_of - start).days + 1)
        daily = float(ytd_sales) / days
        if daily > 0:
            dso = round(float(due) / daily, 1)
    return {
        "ar_balance": ar_cell,
        "aging": [{"id": key, "label": AGE_LABELS[key], "value": buckets[key]} for key in AGE_KEYS],
        "overdue_30": _cell(overdue, not ar_ok, ar_reason),
        "dso": _cell(dso, not ar_ok or dso is None, ar_reason if not ar_ok else ""),
        "urgent": int(counts.get("urgent") or 0),
        "followup": int(counts.get("followup") or 0),
        "credit": int(counts.get("credit") or 0),
        "ontrack": int(counts.get("ontrack") or 0),
    }


def _stock_block(views, phase2):
    stock = (phase2 or {}).get("stock") or {}
    cover_state = stock if stock.get("status") else {}
    return {
        "low_count": int((views or {}).get("low_count") or 0),
        "soon_count": int((views or {}).get("soon_count") or 0),
        "buy_qty_sum": _round((views or {}).get("buy_qty_sum")) or 0,
        "buy_value_sum": _round((views or {}).get("buy_value_sum")) or 0,
        "cover_days": _cell(
            stock.get("cover_days"),
            stock.get("status") == "unavailable",
            stock.get("reason") or "",
        ),
        "slow_value": _cell(
            stock.get("slow_value"),
            stock.get("status") == "unavailable",
            stock.get("reason") or "",
        ),
        "cover_label": cover_state.get("cover_label") or "",
    }


def _top_groups(views):
    details = list(((views or {}).get("group_details") or {}).values())
    if details:
        details.sort(key=lambda row: -float(row.get("ytd_sales") or 0))
        picked = []
        for row in details[:6]:
            count = row.get("customer_count")
            if count is None:
                members = row.get("customers")
                count = len(members) if isinstance(members, list) else (members or 0)
            picked.append({
                "uk": row.get("uk") or "",
                "name": row.get("name") or "",
                "ytd_sales": _round(row.get("ytd_sales")) or 0,
                "due": _round(row.get("due")) or 0,
                "customers": count or 0,
            })
        return picked
    rows = list((views or {}).get("groups") or [])
    rows.sort(key=lambda row: -float(row.get("due") or 0))
    return [{
        "uk": row.get("uk") or "",
        "name": row.get("name") or "",
        "ytd_sales": None,
        "due": _round(row.get("due")) or 0,
        "customers": row.get("customers") or 0,
    } for row in rows[:6]]


def _top_reps(views):
    rows = list((views or {}).get("reps") or [])
    rows.sort(key=lambda row: -float(row.get("ytd_sales") or 0))
    return [{
        "uk": row.get("uk") or "",
        "name": row.get("name") or "",
        "ytd_sales": _round(row.get("ytd_sales")) or 0,
        "due": _round(row.get("due")) or 0,
        "customers": row.get("customers") or 0,
    } for row in rows[:6]]


def _expenses(reports):
    report = _find(reports, "expense_by_category")
    if not report:
        return []
    headers = report.get("headers") or []
    ytd_i = _header_index(headers, "YTD")
    rows = []
    for row in report.get("rows") or []:
        name = str(row[0] if row else "").strip()
        if not name or name.lower() == "total":
            continue
        amount = _round(row[ytd_i] if ytd_i >= 0 and ytd_i < len(row) else None) or 0
        if amount:
            rows.append({"name": name, "amount": amount})
    rows.sort(key=lambda row: -row["amount"])
    return rows[:8]


def _open_invoices(views):
    found = []
    for detail in ((views or {}).get("customers") or {}).values():
        name = detail.get("name") or ""
        uk = detail.get("uk") or ""
        for line in detail.get("open_invoices") or []:
            due = _round(line.get("due"))
            if not due:
                continue
            found.append({
                "party": name,
                "customer_uk": uk,
                "invoice": line.get("invoice") or line.get("what") or "",
                "due": due,
                "age_days": int(line.get("age_days") or 0),
            })
    found.sort(key=lambda row: (-row["due"], -row["age_days"]))
    return found[:8]


def _buy_items(views):
    rows = []
    for card in (views or {}).get("items") or []:
        qty = float(card.get("buy_qty") or 0)
        if qty <= 0:
            continue
        value = round(qty * float(card.get("rate") or 0), 2)
        rows.append({
            "uk": card.get("uk") or "",
            "name": card.get("name") or "",
            "buy_qty": round(qty, 2),
            "buy_value": value,
            "status_label": card.get("status_label") or "",
        })
    rows.sort(key=lambda row: -row["buy_value"])
    return rows[:6]


def _movement(phase2):
    change = (phase2 or {}).get("sales_change") or {}
    customers = []
    for row in (change.get("customers") or [])[:5]:
        customers.append({
            "name": row.get("name") or "",
            "uk": row.get("customer_id") or "",
            "change": _round(row.get("change")) or 0,
            "current": _round(row.get("current")),
        })
    products = []
    for row in (change.get("products") or [])[:5]:
        products.append({
            "name": row.get("name") or "",
            "uk": row.get("product_id") or "",
            "change": _round(row.get("change")) or 0,
            "current": _round(row.get("current")),
        })
    counts = {"new": 0, "repeat": 0, "inactive": 0, "reactivated": 0}
    for row in ((phase2 or {}).get("customer_movement") or {}).get("rows") or []:
        key = row.get("movement")
        if key in counts:
            counts[key] += 1
    return {"customers": customers, "products": products, "counts": counts}


def _exceptions(receivables, stock, reports):
    rows = []
    if receivables.get("urgent"):
        rows.append({
            "id": "urgent",
            "label": "Urgent customers",
            "value": receivables["urgent"],
            "section": "customers",
            "nav": ["customers", "customers"],
        })
    if receivables.get("followup"):
        rows.append({
            "id": "followup",
            "label": "Follow-up customers",
            "value": receivables["followup"],
            "section": "customers",
            "nav": ["customers", "customers"],
        })
    overdue = (receivables.get("overdue_30") or {}).get("value")
    if overdue:
        rows.append({
            "id": "overdue_30",
            "label": "Overdue 30+",
            "value": overdue,
            "section": "customers",
            "nav": ["customers", "customers"],
        })
    if stock.get("low_count"):
        rows.append({
            "id": "low_stock",
            "label": "Items below minimum",
            "value": stock["low_count"],
            "section": "stock",
            "nav": ["customers", "items"],
        })
    unmapped = _find(reports, "unmapped_payment_accounts")
    unmapped_n = len((unmapped or {}).get("rows") or [])
    if unmapped_n:
        rows.append({
            "id": "unmapped",
            "label": "Unmapped payments",
            "value": unmapped_n,
            "section": "profit",
            "nav": ["reports", "profit"],
        })
    missing = _find(reports, "item_cost_exceptions")
    missing_n = len((missing or {}).get("rows") or [])
    if missing_n:
        rows.append({
            "id": "missing_cost",
            "label": "Items missing cost",
            "value": missing_n,
            "section": "profit",
            "nav": ["reports", "items"],
        })
    return rows


def _payments_present(store):
    try:
        return bool(store.rows_of_type("payments"))
    except Exception:
        return False


def _fmt_day(value):
    parsed = parse_date(value) if value else None
    if not parsed:
        return str(value or "")
    return parsed.strftime("%d %b %Y").lstrip("0")


def _add_buckets(dest, src):
    for key, value in (src or {}).items():
        try:
            amount = float(value or 0)
        except (TypeError, ValueError):
            continue
        dest[key] = round(float(dest.get(key) or 0) + amount, 2)


def _copy_lines(rows, party="", uk=""):
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


def company_settlements(customers):
    """Company rollup of customer settlement summaries already on the snapshot."""
    from vay.settlement import default_aging_bands, empty_buckets

    bands = None
    overall_total = 0.0
    credit = 0.0
    overall_buckets = None
    overall_lines = []
    fy_map = {}
    month_map = {}
    default_month = ""
    for detail in (customers or {}).values():
        if not isinstance(detail, dict):
            continue
        if bands is None and detail.get("aging_bands"):
            bands = detail.get("aging_bands")
        summary = detail.get("settlements") or {}
        if not summary:
            continue
        month_key = summary.get("default_month") or ""
        if month_key and (not default_month or month_key > default_month):
            default_month = month_key
        overall = summary.get("overall") or {}
        overall_total += float(overall.get("total") or 0)
        credit += float(overall.get("credit") or 0)
        if overall_buckets is None:
            overall_buckets = empty_buckets(bands)
        _add_buckets(overall_buckets, overall.get("buckets"))
        party = detail.get("name") or ""
        customer_uk = detail.get("uk") or ""
        overall_lines.extend(_copy_lines(overall.get("lines"), party, customer_uk))
        for row in summary.get("by_fy") or []:
            key = row.get("key") or ""
            if not key:
                continue
            slot = fy_map.setdefault(key, {
                "key": key,
                "label": row.get("label") or key,
                "total": 0.0,
                "buckets": empty_buckets(bands),
                "lines": [],
            })
            slot["total"] = round(slot["total"] + float(row.get("total") or 0), 2)
            _add_buckets(slot["buckets"], row.get("buckets"))
            slot["lines"].extend(_copy_lines(row.get("lines"), party, customer_uk))
        for row in summary.get("months") or []:
            key = row.get("key") or ""
            if not key:
                continue
            slot = month_map.setdefault(key, {
                "key": key,
                "year": row.get("year"),
                "month": row.get("month"),
                "label": row.get("label") or key,
                "total": 0.0,
                "buckets": empty_buckets(bands),
                "lines": [],
            })
            slot["total"] = round(slot["total"] + float(row.get("total") or 0), 2)
            _add_buckets(slot["buckets"], row.get("buckets"))
            slot["lines"].extend(_copy_lines(row.get("lines"), party, customer_uk))
    if bands is None:
        bands = default_aging_bands()
    if overall_buckets is None:
        overall_buckets = empty_buckets(bands)
    for slot in list(fy_map.values()) + list(month_map.values()):
        slot["lines"] = _copy_lines(slot.get("lines"))
    return {
        "overall": {
            "total": round(overall_total, 2),
            "buckets": overall_buckets,
            "credit": round(max(0.0, credit), 2),
            "lines": _copy_lines(overall_lines),
        },
        "by_fy": sorted(fy_map.values(), key=lambda row: row["key"], reverse=True),
        "months": sorted(month_map.values(), key=lambda row: row["key"], reverse=True),
        "default_month": default_month,
        "aging_bands": bands,
    }


def company_sales_gaps(customers):
    """Company rollup of each customer's own order-to-order gaps."""
    from server.customers import merge_sales_gaps, sales_gaps_from_detail

    parts = []
    bands = None
    for detail in (customers or {}).values():
        if not isinstance(detail, dict):
            continue
        if bands is None and detail.get("aging_bands"):
            bands = detail.get("aging_bands")
        parts.append(sales_gaps_from_detail(detail))
    return merge_sales_gaps(parts, bands)


def qty_levels(lines, as_of, start_month):
    """Item quantity for overall, this fiscal year, and this month. No lines stay blank."""
    from datetime import datetime

    from vay.dates import fiscal_year_start, normalize_date, parse_date

    empty = {"overall": None, "fy": None, "month": None, "available": False}
    if not lines:
        return empty
    if not hasattr(as_of, "year"):
        as_of = normalize_date(parse_date(as_of) or as_of)
    if not as_of:
        return empty

    def total(start):
        value = 0.0
        for line in lines:
            when = line.get("date")
            if not when or when > as_of:
                continue
            if start and when < start:
                continue
            value += float(line.get("qty") or 0)
        return round(value, 2)

    fy = fiscal_year_start(as_of, start_month)
    month = datetime(as_of.year, as_of.month, 1, 12)
    return {"overall": total(None), "fy": total(fy), "month": total(month), "available": True}


def _company_qty(store, report_date, start_month):
    """Item quantity on the same three windows as the sales cards."""
    empty = {"overall": None, "fy": None, "month": None, "available": False}
    if not report_date:
        return empty
    try:
        from server.book import load_book
        book = load_book(store)
    except Exception:
        return empty
    lines = []
    for group in (book.get("item_lines_by_uk") or {}).values():
        lines.extend(group or [])
    return qty_levels(lines, report_date, start_month)


def build_business(store, reports, phase2, views, report_date="", fy_label=""):
    phase2 = phase2 or {}
    views = views or {}
    start_month = None
    try:
        from server.org_policy import get_org_policy
        start_month = get_org_policy(store).get("fiscal_year_start_month")
    except Exception:
        start_month = None
    eligibility = phase2.get("eligibility") or {}
    margin = eligibility.get("gross_margin") or {}
    payments_ok = _payments_present(store)
    profit = profit_periods(
        _find(reports, "monthly_profit_report"),
        margin_status=margin.get("status") or "unavailable",
        margin_reason=margin.get("reason") or "",
        payments_present=payments_ok,
    )
    scorecard = phase2.get("scorecard") or {}
    flows = _flow_periods(reports, scorecard)
    levels = _company_qty(store, report_date, start_month)
    targets = {}
    for row in scorecard.get("rows") or []:
        cell = row.get("target") or {}
        if cell.get("value") is not None:
            targets[row.get("id")] = cell.get("value")
    receivables = _receivables(views, flows.get("ytd_sales"), report_date, targets, eligibility, start_month)
    stock = _stock_block(views, phase2)
    periods = {}
    for key in ("overall", "fy", "month"):
        periods[key] = dict(flows[key])
        periods[key]["profit"] = profit[key]
        periods[key]["qty"] = levels[key]
    return {
        "empty": False,
        "name": "Business",
        "as_of": str(report_date or "")[:10],
        "as_of_label": _fmt_day(report_date),
        "fy_label": fy_label or "",
        "cost_note": COST_NOTE,
        "profit_available": bool(profit.get("available")),
        "periods": periods,
        "qty_available": bool(levels.get("available")),
        "receivables": receivables,
        "stock": stock,
        "mix": {
            "groups": _top_groups(views),
            "reps": _top_reps(views),
            "expenses": _expenses(reports),
            "invoices": _open_invoices(views),
            "buy": _buy_items(views),
        },
        "movement": _movement(phase2),
        "exceptions": _exceptions(receivables, stock, reports),
        "settlements": company_settlements((views or {}).get("customers")),
        "sales_gaps": company_sales_gaps((views or {}).get("customers")),
    }


def visible_business(doc, permissions):
    if not doc or doc.get("empty"):
        return empty_business()
    have = set(permissions or [])

    def allow(*names):
        return "*" in have or any(name in have for name in names)

    out = {
        "empty": False,
        "name": doc.get("name") or "Business",
        "as_of": doc.get("as_of") or "",
        "as_of_label": doc.get("as_of_label") or "",
        "fy_label": doc.get("fy_label") or "",
        "message": "",
    }
    if doc.get("settlements_separate"):
        out["settlements_separate"] = True
    if doc.get("sales_gaps_separate"):
        out["sales_gaps_separate"] = True
    see_sales = allow("sales.view")
    see_profit = allow("reports.view.profit")
    see_customers = allow("customer.view")
    see_stock = allow("stock.view")
    periods = {}
    for key, period in (doc.get("periods") or {}).items():
        slot = {}
        if see_sales:
            for field in ("sales", "collection", "gap", "rate", "qty"):
                if field in period:
                    slot[field] = period[field]
        if see_profit and period.get("profit"):
            slot["profit"] = period["profit"]
        periods[key] = slot
    out["periods"] = periods
    if see_sales:
        out["qty_available"] = bool(doc.get("qty_available"))
    if see_profit:
        out["cost_note"] = doc.get("cost_note") or COST_NOTE
        out["profit_available"] = bool(doc.get("profit_available"))
    if see_customers:
        out["receivables"] = doc.get("receivables") or {}
        if doc.get("settlements"):
            out["settlements"] = doc.get("settlements")
    if see_sales or see_customers:
        if doc.get("sales_gaps"):
            out["sales_gaps"] = doc.get("sales_gaps")
    if see_stock:
        out["stock"] = doc.get("stock") or {}
    mix = doc.get("mix") or {}
    visible_mix = {}
    if see_customers:
        visible_mix["groups"] = mix.get("groups") or []
        visible_mix["reps"] = mix.get("reps") or []
        visible_mix["invoices"] = mix.get("invoices") or []
    if see_profit:
        visible_mix["expenses"] = mix.get("expenses") or []
    if see_stock:
        visible_mix["buy"] = mix.get("buy") or []
    out["mix"] = visible_mix
    movement = doc.get("movement") or {}
    visible_movement = {}
    if see_customers:
        visible_movement["customers"] = movement.get("customers") or []
        visible_movement["counts"] = movement.get("counts") or {}
    if see_sales:
        visible_movement["products"] = movement.get("products") or []
    out["movement"] = visible_movement
    allowed_sections = set()
    if see_customers:
        allowed_sections.add("customers")
    if see_stock:
        allowed_sections.add("stock")
    if see_profit:
        allowed_sections.add("profit")
    out["exceptions"] = [
        row for row in (doc.get("exceptions") or [])
        if row.get("section") in allowed_sections
    ]
    return out


def business_brief_pdf(detail):
    """One-page internal brief for the company profile."""
    from fpdf import FPDF

    from server.customers import _pdf_family, _pdf_line, money

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(16, 16, 16)
    pdf.add_page()
    family = _pdf_family(pdf)
    _pdf_line(pdf, family, "Vay  ·  Business brief", 16, True, 8)
    bits = [detail.get("as_of_label") or "", detail.get("fy_label") or ""]
    _pdf_line(pdf, family, "  ·  ".join(bit for bit in bits if bit), 10, False, 6, (120, 113, 108))
    periods = detail.get("periods") or {}
    labels = (("overall", "Overall"), ("fy", "This FY"), ("month", "This month"))
    for key, label in labels:
        period = periods.get(key) or {}
        sales = (period.get("sales") or {}).get("value")
        collection = (period.get("collection") or {}).get("value")
        profit = period.get("profit") or {}
        ebitda = (profit.get("ebitda") or {}).get("value")
        parts = [label]
        if sales is not None:
            parts.append("Sales " + money(sales))
        if collection is not None:
            parts.append("Collected " + money(collection))
        if ebitda is not None:
            parts.append("EBITDA " + money(ebitda))
        elif profit.get("sales_profit") is not None:
            parts.append("Sales profit " + money(profit.get("sales_profit")))
        if len(parts) > 1:
            _pdf_line(pdf, family, "  ·  ".join(parts), 11, False, 6)
    settled = ((detail.get("settlements") or {}).get("overall") or {}).get("total")
    if settled:
        _pdf_line(pdf, family, "Settled " + money(settled), 11, False, 6)
    ebitda_cell = ((periods.get("overall") or {}).get("profit") or {}).get("ebitda") or {}
    if ebitda_cell.get("unavailable") and ebitda_cell.get("reason"):
        _pdf_line(pdf, family, ebitda_cell["reason"], 9, False, 5, (120, 113, 108))
    if detail.get("cost_note"):
        _pdf_line(pdf, family, detail["cost_note"], 9, False, 5, (120, 113, 108))
    exceptions = detail.get("exceptions") or []
    if exceptions:
        _pdf_line(pdf, family, "Needs a decision", 12, True, 7)
        for row in exceptions:
            _pdf_line(pdf, family, "%s: %s" % (row.get("label") or "", row.get("value")), 10, False, 5)
    raw = pdf.output()
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else raw.encode("latin-1")
