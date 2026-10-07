"""Compact Home dashboard payload. Official figures are saved with the run; upload freshness is live."""

from __future__ import annotations

import copy
import json

from vay.config import DEFAULT_RECEIPT_REP
from vay.dates import clean_text, fiscal_year_start, number_, parse_date

from server.auth import ALL_PERMISSIONS, filter_snapshot, metric_visible, type_perm
from server.invoices import list_invoices
from server.settings import SOURCE_TYPES

KPI_COLS = (
    ("mtd_sales", "MTD Sales"),
    ("mtd_collection", "MTD Collection"),
    ("d15_sales", "15 Days Sales"),
    ("d15_collection", "15 Days Collection"),
    ("ytd_sales", "YTD Sales"),
    ("ytd_collection", "YTD Collection"),
)
CUSTOMER_KEYS = (
    "uk",
    "name",
    "group",
    "salesperson",
    "due",
    "status",
    "status_label",
    "credit",
    "last_sale_label",
)
STOCK_KEYS = ("uk", "name", "qty", "status", "status_label", "min_hold", "buy_qty")
INVOICE_KEYS = ("id", "invoice", "party", "date_label", "amount", "customer_uk")


def _num(value):
    if value is None or value == "":
        return None
    try:
        return round(float(str(value).replace(",", "").replace("₹", "").strip()), 2)
    except (TypeError, ValueError):
        return None


def _when(value):
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _pick(row, keys):
    return {key: row.get(key) for key in keys}


def _can_see_upload(perms, doc):
    kind = doc.get("type") or "combined"
    if kind == "combined":
        return any(p.endswith(".view") or p.endswith(".upload") or p == "settings.import" for p in perms)
    return type_perm(kind, "view") in perms or type_perm(kind, "upload") in perms


def _latest_run(store):
    for doc in store.list_runs() or []:
        if doc.get("status") == "succeeded":
            return doc
    return None


def _snapshot(store, run, perms):
    if not run or not run.get("json_id"):
        return None
    blob = store.get_blob(run.get("json_id"))
    if not blob or not blob.get("data"):
        return None
    try:
        raw = json.loads(blob["data"].decode("utf-8"))
    except (TypeError, ValueError, AttributeError, json.JSONDecodeError):
        return None
    return filter_snapshot(raw, perms)


def _find_report(snapshot, report_id):
    for report in (snapshot or {}).get("reports") or []:
        if report.get("id") == report_id:
            return report
    return None


def _total_row(report):
    if report.get("total"):
        return report["total"]
    for row in reversed(report.get("rows") or []):
        if str(row[0] if row else "").strip().lower() == "total":
            return row
    return None


def _header_index(headers, name):
    try:
        return headers.index(name)
    except ValueError:
        return -1


def _add_pair(kpis, sales, collection, gap_id, rate_id, gap_label):
    if sales is None and collection is None:
        return
    sales = 0.0 if sales is None else float(sales)
    collection = 0.0 if collection is None else float(collection)
    kpis.append({"id": gap_id, "label": gap_label, "value": round(sales - collection, 2)})
    if sales:
        kpis.append({"id": rate_id, "label": "Collected", "value": round((collection / sales) * 100, 1)})
    else:
        kpis.append({"id": rate_id, "label": "Collected", "value": None})


def _month_label(header):
    text = str(header or "")
    for suffix in (" Sales", " Collection"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    text = text.split(" [")[0].strip()
    parts = text.split()
    if len(parts) >= 2 and parts[-1].isdigit():
        return parts[0][:3] + " " + parts[-1][2:]
    return text[:8] if text else ""


def _group_chart(snapshot, sales_header="YTD Sales", coll_header="YTD Collection"):
    report = _find_report(snapshot, "group_performance_report")
    if not report:
        return []
    headers = report.get("headers") or []
    sales_i = _header_index(headers, sales_header)
    coll_i = _header_index(headers, coll_header)
    if sales_i < 0 or coll_i < 0:
        return []
    chart = []
    for row in report.get("rows") or []:
        name = str(row[0] if row else "").strip()
        if not name or name.lower() == "total":
            continue
        sales = _num(row[sales_i] if sales_i < len(row) else None) or 0
        collection = _num(row[coll_i] if coll_i < len(row) else None) or 0
        chart.append({"name": name, "sales": sales, "collection": collection})
    chart.sort(key=lambda row: -row["sales"])
    return chart[:8]


def _aging_chart(kpis):
    by_id = {row["id"]: row["value"] for row in kpis}
    keys = [
        ("due_0_15", "d0_15"),
        ("due_15_30", "d15_30"),
        ("due_30_45", "d30_45"),
        ("due_45_60", "d45_60"),
        ("due_60_90", "d60_90"),
        ("due_90", "d90"),
    ]
    if any(by_id.get(k) is not None for k, _ in keys):
        row = {"name": "Due aging"}
        for kpi_id, chart_key in keys:
            row[chart_key] = float(by_id.get(kpi_id) or 0)
        return [row]
    new_credit = by_id.get("new_credit")
    overdue_15 = by_id.get("overdue_15")
    overdue_30 = by_id.get("overdue_30")
    if new_credit is None and overdue_15 is None and overdue_30 is None:
        return []
    return [{
        "name": "Credit aging",
        "new": float(new_credit or 0),
        "d15": float(overdue_15 or 0),
        "d30": float(overdue_30 or 0),
    }]


def _rate_chart(chart_monthly):
    out = []
    for row in chart_monthly or []:
        sales = float(row.get("sales") or 0)
        collection = float(row.get("collection") or 0)
        rate = round((collection / sales) * 100, 1) if sales > 0 else None
        if rate is None:
            continue
        out.append({"name": row.get("name") or "", "rate": rate})
    return out


def _due_chart(customers):
    rows = []
    source = (customers or {}).get("top_due") or (customers or {}).get("top") or []
    for row in source:
        name = clean_text(row.get("name")) or "Customer"
        due = _num(row.get("due"))
        if due is None or float(due) <= 0:
            continue
        rows.append({"name": name[:18], "due": abs(float(due))})
    rows.sort(key=lambda r: -r["due"])
    return rows[:8]


def _active_customers(snapshot):
    report = _find_report(snapshot, "account_performance_report")
    if not report:
        return None
    headers = report.get("headers") or []
    mtd_i = _header_index(headers, "MTD Sales")
    if mtd_i < 0:
        return None
    count = 0
    for row in report.get("rows") or []:
        name = str(row[0] if row else "").strip()
        if not name or name.lower() == "total":
            continue
        sales = _num(row[mtd_i] if mtd_i < len(row) else None) or 0
        if sales > 0:
            count += 1
    return count


def _monthly_chart(snapshot):
    report = _find_report(snapshot, "fiscal_monthly_sales_rep_performance_report")
    if not report or report.get("wide") != "pair":
        return []
    headers = report.get("headers") or []
    label_cols = int(report.get("label_cols") or 1)
    total = _total_row(report) or []
    n = report.get("n_fy")
    if n is None:
        n = max(1, (len(headers) - label_cols - 2) // 26)
    yi = max(0, int(n) - 1)
    start = label_cols + yi * 26
    chart = []
    for i in range(12):
        sales_i = start + i * 2
        coll_i = sales_i + 1
        if sales_i >= len(headers) or coll_i >= len(headers):
            break
        raw = str(headers[sales_i] or "")
        if "[after report date]" in raw.lower() or "total" in raw.lower():
            continue
        sales = _num(total[sales_i] if sales_i < len(total) else None) or 0
        collection = _num(total[coll_i] if coll_i < len(total) else None) or 0
        chart.append({
            "name": _month_label(raw),
            "sales": sales,
            "collection": collection,
        })
    while chart and chart[-1]["sales"] == 0 and chart[-1]["collection"] == 0:
        chart.pop()
    while chart and chart[0]["sales"] == 0 and chart[0]["collection"] == 0:
        chart.pop(0)
    return chart


def _append_ar_kpis(snapshot, kpis):
    report = _find_report(snapshot, "group_performance_report")
    if not report:
        report = _find_report(snapshot, "account_performance_report")
    if not report:
        return
    headers = report.get("headers") or []
    total = _total_row(report) or []
    for kpi_id, label, header in (
        ("ar_balance", "AR balance", "Balance"),
        ("due_0_15", "Due 0–15 days", "Due 0–15 Days"),
        ("due_15_30", "Due 15–30 days", "Due 15–30 Days"),
        ("due_30_45", "Due 30–45 days", "Due 30–45 Days"),
        ("due_45_60", "Due 45–60 days", "Due 45–60 Days"),
        ("due_60_90", "Due 60–90 days", "Due 60–90 Days"),
        ("due_90", "Due 90+ days", "Due 90+ Days"),
    ):
        idx = _header_index(headers, header)
        if idx < 0:
            continue
        value = _num(total[idx] if idx < len(total) else None)
        if value is not None:
            kpis.append({"id": kpi_id, "label": label, "value": value})


def _append_derived_kpis(kpis, chart, chart_monthly, report_date, snapshot=None):
    by_id = {row["id"]: row["value"] for row in kpis}
    ar = by_id.get("ar_balance")
    ytd = by_id.get("ytd_sales")
    as_of = parse_date(report_date) if report_date else None
    if ar is not None and ytd and as_of and float(ytd) > 0:
        fy0 = fiscal_year_start(as_of)
        days = max(1, (as_of - fy0).days + 1)
        daily = float(ytd) / days
        if daily > 0:
            kpis.append({"id": "dso", "label": "DSO (days)", "value": round(float(ar) / daily, 1)})

    mtd = by_id.get("mtd_sales")
    mtd_gap = by_id.get("mtd_gap")
    if mtd and float(mtd) > 0 and mtd_gap is not None:
        kpis.append({
            "id": "mtd_gap_pct",
            "label": "MTD gap %",
            "value": round(100.0 * float(mtd_gap) / float(mtd), 1),
        })

    if chart and mtd and float(mtd) > 0:
        top = float(chart[0].get("sales") or 0)
        kpis.append({
            "id": "top_rep_share",
            "label": "Top rep MTD share",
            "value": round(100.0 * top / float(mtd), 1),
        })

    if chart_monthly and len(chart_monthly) >= 2:
        prev = float(chart_monthly[-2].get("sales") or 0)
        curr = float(chart_monthly[-1].get("sales") or 0)
        if prev > 0:
            kpis.append({
                "id": "mom_sales_pct",
                "label": "MoM sales",
                "value": round(100.0 * (curr - prev) / prev, 1),
            })
        prev_c = float(chart_monthly[-2].get("collection") or 0)
        curr_c = float(chart_monthly[-1].get("collection") or 0)
        if prev_c > 0:
            kpis.append({
                "id": "mom_collection_pct",
                "label": "MoM collection",
                "value": round(100.0 * (curr_c - prev_c) / prev_c, 1),
            })

    active = _active_customers(snapshot)
    if active is not None:
        kpis.append({"id": "active_customers_mtd", "label": "Active customers MTD", "value": active})


def _followup_kpis(snapshot):
    if not snapshot:
        return []
    sales_n = 0
    coll_n = 0
    found = False
    for report in snapshot.get("reports") or []:
        rid = report.get("id") or ""
        n = len(report.get("rows") or [])
        if rid.startswith("sales_follow_up_"):
            found = True
            sales_n += n
        elif rid.startswith("collection_follow_up_"):
            found = True
            coll_n += n
    if not found:
        return []
    return [
        {"id": "inactive_mtd", "label": "Inactive customers", "value": sales_n},
        {"id": "collection_followups", "label": "Collection follow-ups", "value": coll_n},
    ]


def _invoice_mtd_kpis(store, report_date):
    as_of = parse_date(report_date) if report_date else None
    if not as_of:
        return []
    month_start = as_of.replace(day=1, hour=12, minute=0, second=0, microsecond=0)
    data = list_invoices(store, {"limit": "5000", "sort": "date", "dir": "desc"})
    amounts = []
    for inv in data.get("invoices") or []:
        d = parse_date(inv.get("date"))
        if not d or d < month_start or d > as_of:
            continue
        amounts.append(float(inv.get("amount") or 0))
    if not amounts and not data.get("total"):
        return [
            {"id": "invoice_mtd_count", "label": "Invoices MTD", "value": 0},
            {"id": "invoice_mtd_avg", "label": "Avg invoice MTD", "value": None},
        ]
    count = len(amounts)
    total = sum(amounts)
    return [
        {"id": "invoice_mtd_count", "label": "Invoices MTD", "value": count},
        {
            "id": "invoice_mtd_avg",
            "label": "Avg invoice MTD",
            "value": round(total / count, 2) if count else None,
        },
    ]


def _wide_line_sum(report, line_name):
    if not report or report.get("wide") != "month":
        return None, None
    headers = report.get("headers") or []
    label_cols = int(report.get("label_cols") or 1)
    n = report.get("n_fy")
    if n is None:
        n = max(1, (len(headers) - label_cols - 1) // 13)
    yi = max(0, int(n) - 1)
    start = label_cols + yi * 13
    end = start + 12
    for row in report.get("rows") or []:
        if str(row[0] if row else "").strip().lower() != line_name:
            continue
        month_vals = []
        ytd = 0.0
        for i in range(start, min(end, len(headers))):
            raw = str(headers[i] or "")
            if "[after report date]" in raw.lower() or raw.lower() == "total":
                continue
            value = _num(row[i] if i < len(row) else None)
            if value is None:
                continue
            ytd += value
            month_vals.append(value)
        mtd = month_vals[-1] if month_vals else None
        return mtd, round(ytd, 2)
    return None, None


def _profit_dashboard(snapshot):
    if not snapshot:
        return None
    kpis = []
    chart = []
    exp = _find_report(snapshot, "expense_by_category")
    if exp:
        headers = exp.get("headers") or []
        total = _total_row(exp) or []
        mtd_i = _header_index(headers, "MTD")
        ytd_i = _header_index(headers, "YTD")
        if mtd_i >= 0:
            value = _num(total[mtd_i] if mtd_i < len(total) else None)
            if value is not None:
                kpis.append({"id": "expense_mtd", "label": "Expense MTD", "value": value})
        if ytd_i >= 0:
            value = _num(total[ytd_i] if ytd_i < len(total) else None)
            if value is not None:
                kpis.append({"id": "expense_ytd", "label": "Expense YTD", "value": value})
        for row in exp.get("rows") or []:
            name = str(row[0] if row else "").strip()
            if not name or name.lower() == "total":
                continue
            amount = _num(row[ytd_i] if ytd_i >= 0 and ytd_i < len(row) else None) or 0
            if amount:
                chart.append({"name": name, "amount": amount})
        chart.sort(key=lambda row: -row["amount"])
        chart = chart[:8]

    profit_report = _find_report(snapshot, "monthly_profit_report")
    profit_mtd, profit_ytd = _wide_line_sum(profit_report, "sales profit")
    sale_mtd, sale_ytd = _wide_line_sum(profit_report, "sale before tax")
    if profit_mtd is not None:
        kpis.append({"id": "profit_mtd", "label": "Sales profit MTD", "value": round(profit_mtd, 2)})
    if profit_ytd is not None:
        kpis.append({"id": "profit_ytd", "label": "Sales profit YTD", "value": profit_ytd})
    if profit_mtd is not None and sale_mtd and float(sale_mtd) > 0:
        kpis.append({
            "id": "margin_mtd_pct",
            "label": "Gross margin MTD",
            "value": round(100.0 * float(profit_mtd) / float(sale_mtd), 1),
        })
    if profit_ytd is not None and sale_ytd and float(sale_ytd) > 0:
        kpis.append({
            "id": "margin_ytd_pct",
            "label": "Gross margin YTD",
            "value": round(100.0 * float(profit_ytd) / float(sale_ytd), 1),
        })

    if not kpis and not chart:
        return None
    return {"kpis": kpis, "chart": chart}


def _fiscal_all_time(snapshot):
    report = _find_report(snapshot, "fiscal_monthly_sales_rep_performance_report")
    if not report:
        return None, None
    headers = report.get("headers") or []
    total = _total_row(report) or []
    sales_i = coll_i = -1
    for i, name in enumerate(headers):
        if name == "Total Sales":
            sales_i = i
        elif name == "Total Collection":
            coll_i = i
    if sales_i < 0 or coll_i < 0:
        return None, None
    return _num(total[sales_i] if sales_i < len(total) else None), _num(total[coll_i] if coll_i < len(total) else None)


def _store_all_time(store, report_date):
    from server.org_policy import collection_customer_keys

    cutoff = parse_date(report_date) if report_date else None
    customers = collection_customer_keys(store)
    sales = 0.0
    collection = 0.0
    for row in store.rows_of_type("sales"):
        fields = row.get("fields") or {}
        d = parse_date(fields.get("Date"))
        if cutoff and (not d or d > cutoff):
            continue
        sales += number_(fields.get("Net Amount"))
    for row in store.rows_of_type("credit_note"):
        fields = row.get("fields") or {}
        d = parse_date(fields.get("Date"))
        if cutoff and (not d or d > cutoff):
            continue
        amount = number_(fields.get("Net Amount"))
        if amount <= 0:
            continue
        sales -= amount
    for row in store.rows_of_type("receipt"):
        fields = row.get("fields") or {}
        rep = clean_text(fields.get("Sales Rep")) or DEFAULT_RECEIPT_REP
        if rep == DEFAULT_RECEIPT_REP:
            continue
        name = clean_text(fields.get("Account Name") or fields.get("Party Name"))
        if not name or name.lower() not in customers:
            continue
        d = parse_date(fields.get("Date"))
        if cutoff and (not d or d > cutoff):
            continue
        collection += number_(fields.get("Amount"))
    return round(sales, 2), round(collection, 2)


def _performance(snapshot, store=None, report_date=""):
    report = _find_report(snapshot, "sales_rep_performance_report")
    if not report:
        return [], [], None
    headers = report.get("headers") or []
    total = _total_row(report) or []
    kpis = []
    for kpi_id, label in KPI_COLS:
        idx = _header_index(headers, label)
        if idx < 0:
            continue
        value = _num(total[idx] if idx < len(total) else None)
        if value is None:
            value = 0.0
        kpis.append({"id": kpi_id, "label": label, "value": value})
    sales_i = _header_index(headers, "MTD Sales")
    coll_i = _header_index(headers, "MTD Collection")
    chart = []
    for row in report.get("rows") or []:
        name = str(row[0] if row else "").strip()
        if not name or name.lower() == "total":
            continue
        sales = _num(row[sales_i] if sales_i >= 0 and sales_i < len(row) else None) or 0
        collection = _num(row[coll_i] if coll_i >= 0 and coll_i < len(row) else None) or 0
        chart.append({"name": name, "sales": sales, "collection": collection})
    chart.sort(key=lambda row: -row["sales"])
    by_id = {row["id"]: row["value"] for row in kpis}
    _add_pair(kpis, by_id.get("mtd_sales"), by_id.get("mtd_collection"), "mtd_gap", "mtd_rate", "MTD Gap")
    _add_pair(kpis, by_id.get("d15_sales"), by_id.get("d15_collection"), "d15_gap", "d15_rate", "15 Days Gap")
    _add_pair(kpis, by_id.get("ytd_sales"), by_id.get("ytd_collection"), "ytd_gap", "ytd_rate", "YTD Gap")
    fiscal_sales, fiscal_collection = _fiscal_all_time(snapshot)
    total_source = None
    if fiscal_sales is not None and fiscal_collection is not None:
        total_sales, total_collection = fiscal_sales, fiscal_collection
        total_source = "fiscal"
    elif store is not None:
        total_sales, total_collection = _store_all_time(store, report_date)
        total_source = "imported"
    else:
        total_sales = total_collection = None
    if total_sales is not None and total_collection is not None:
        kpis.append({"id": "total_sales", "label": "Total Sales", "value": total_sales})
        kpis.append({"id": "total_collection", "label": "Total Collection", "value": total_collection})
        _add_pair(kpis, total_sales, total_collection, "total_gap", "total_rate", "Total Gap")
    _append_ar_kpis(snapshot, kpis)
    return kpis, chart[:8], total_source


def _finalize_performance(snapshot, store, report_date):
    kpis, chart, total_source = _performance(snapshot, store, report_date)
    chart_groups = _group_chart(snapshot)
    chart_groups_mtd = _group_chart(snapshot, "MTD Sales", "MTD Collection")
    chart_monthly = _monthly_chart(snapshot)
    _append_derived_kpis(kpis, chart, chart_monthly, report_date, snapshot)
    chart_aging = _aging_chart(kpis)
    chart_rate = _rate_chart(chart_monthly)
    return kpis, chart, chart_groups, chart_groups_mtd, chart_monthly, chart_aging, chart_rate, total_source


def _issues_count(snapshot):
    report = _find_report(snapshot, "source_data_warnings")
    if not report:
        return 0
    return len(report.get("rows") or [])


def _has_data(store, perms, uploads):
    if uploads:
        return True
    for type_name in SOURCE_TYPES:
        perm = type_perm(type_name, "view")
        if perm and perm in perms and store.rows_of_type(type_name):
            return True
    return False


def _uploads(store, perms, docs=None):
    rows = []
    source = store.list_uploads() or [] if docs is None else docs
    for doc in source:
        if not _can_see_upload(perms, doc):
            continue
        rows.append({
            "id": str(doc.get("_id")),
            "filename": doc.get("filename"),
            "type": doc.get("type"),
            "created_at": _when(doc.get("created_at")),
        })
        if len(rows) >= 3:
            break
    return rows


def _customers(store, views=None):
    from server.run_views import snapshot_list_customers
    data = snapshot_list_customers(store, {"page": "1"}, views)
    counts = data.get("counts") or {
        "urgent": 0,
        "followup": 0,
        "credit": 0,
        "ontrack": 0,
        "due_total": 0.0,
    }
    counts["due_total"] = round(float(counts.get("due_total") or 0), 2)
    due_ranked = snapshot_list_customers(store, {"page": "1", "sort": "due", "dir": "desc"}, views)
    top_due = []
    for row in due_ranked.get("customers") or []:
        due = _num(row.get("due"))
        if due is None or float(due) <= 0:
            continue
        top_due.append(_pick(row, CUSTOMER_KEYS))
        if len(top_due) >= 8:
            break
    return {
        "counts": counts,
        "total": data.get("total") or 0,
        "top": [_pick(row, CUSTOMER_KEYS) for row in data.get("attention") or []],
        "top_due": top_due,
    }


def _stock(store, views=None):
    from server.run_views import snapshot_list_items
    data = snapshot_list_items(store, {"status": "Below min", "limit": "5", "sort": "qty", "dir": "asc"}, views)
    return {
        "low_count": data.get("low_count") or 0,
        "soon_count": data.get("soon_count") or 0,
        "buy_qty_sum": round(float(data.get("buy_qty_sum") or 0), 2),
        "buy_value_sum": round(float(data.get("buy_value_sum") or 0), 2),
        "top": [_pick(row, STOCK_KEYS) for row in data.get("items") or []],
    }


def _invoices(store):
    data = list_invoices(store, {"limit": "5", "sort": "date", "dir": "desc"})
    return [_pick(row, INVOICE_KEYS) for row in data.get("invoices") or []]


_AR_DASH_IDS = {
    "ar_balance",
    "due_0_15",
    "due_15_30",
    "due_30_45",
    "due_45_60",
    "due_60_90",
    "due_90",
    "dso",
    "overdue_30",
    "overdue_15",
}


def _eligibility_for_run(store, run, live=True):
    manifest = (run or {}).get("manifest") or {}
    stored = manifest.get("eligibility") or {}
    report_date = (run or {}).get("report_date") or ""
    if not live or not report_date:
        return stored
    from vay.eligibility import evaluate

    live = evaluate(store, report_date)
    if not stored:
        return live
    # A run saved before the snapshot was dated should pick up the import day.
    ar_reason = (stored.get("ar_balance") or {}).get("reason") or ""
    stock_reason = (stored.get("stock_cover_days") or {}).get("reason") or ""
    if ar_reason.startswith("No AR") or stock_reason.startswith("No Stock"):
        return live
    return stored


def _apply_eligibility(payload, eligibility):
    """Keep AR and stock figures visible, and note when the snapshot date differs."""
    eligibility = eligibility or {}
    ar = eligibility.get("ar_balance") or {}
    if ar.get("status") == "unavailable":
        reason = ar.get("reason") or "Unavailable"
        for row in payload.get("kpis") or []:
            if row.get("id") in _AR_DASH_IDS and row.get("value") is not None:
                row["unavailable"] = True
                row["reason"] = reason
    if payload.get("stock") is not None:
        payload["stock"]["cover"] = dict(eligibility.get("stock_cover_days") or {})
        payload["stock"]["slow"] = dict(eligibility.get("slow_stock_value") or {})


def _attach_stock_numbers(store, payload, report_date):
    stock = payload.get("stock")
    if not stock or not report_date:
        return
    cover = stock.get("cover") or {}
    slow = stock.get("slow") or {}
    show = ("eligible", "unavailable")
    if cover.get("status") not in show and slow.get("status") not in show:
        return
    from server.phase2 import stock_headline
    headline = stock_headline(store, report_date)
    if cover.get("status") in show:
        cover["value"] = headline.get("cover_days")
        cover["label"] = headline.get("cover_label") or ""
        stock["cover"] = cover
    if slow.get("status") in show:
        slow["value"] = headline.get("slow_value")
        slow["uncosted"] = headline.get("uncosted") or 0
        stock["slow"] = slow


def _merge_kpis(payload, rows):
    if not rows:
        return
    existing = payload.setdefault("kpis", [])
    seen = {row.get("id") for row in existing}
    for row in rows:
        if row.get("id") in seen:
            continue
        existing.append(row)
        seen.add(row.get("id"))


def build_dashboard(store, permissions, run_id=None, *, prepared=None, live=True):
    """Build a dashboard payload.

    prepared is {"run", "snapshot", "views"} when Create already has them in memory.
    live scans invoices and stock. Create does that once. A page read does not.
    """
    from server.run_views import import_newer_than, load_run_views
    perms = list(permissions or [])
    if prepared is not None:
        run = prepared.get("run")
        views = prepared.get("views")
        raw_snapshot = prepared.get("snapshot")
        snapshot = None
        if run and raw_snapshot is not None and any(p.startswith("reports.view.") for p in perms):
            snapshot = filter_snapshot(raw_snapshot, perms)
    else:
        run, views = load_run_views(store, run_id)
        if not run:
            run = _latest_run(store)
            if run and not views:
                _run2, views = load_run_views(store, str(run.get("_id") or ""))
                run = _run2 or run
        snapshot = None
        if run and any(p.startswith("reports.view.") for p in perms):
            snapshot = _snapshot(store, run, perms)
    uploads = _uploads(store, perms)
    report_date = (run or {}).get("report_date") or ""
    payload = {
        "run": None,
        "freshness": {
            "report_date": report_date,
            "fy_label": (run or {}).get("fy_label") or "",
            "last_upload_at": uploads[0]["created_at"] if uploads else "",
        },
        "has_data": _has_data(store, perms, uploads),
        "import_newer": import_newer_than(store, run),
    }
    if run:
        payload["run"] = {
            "id": str(run.get("_id") or run.get("id") or ""),
            "report_date": report_date,
            "fy_label": run.get("fy_label") or "",
            "status": run.get("status") or "",
        }
    if "reports.view.performance" in perms:
        (
            kpis, chart, chart_groups, chart_groups_mtd, chart_monthly,
            chart_aging, chart_rate, total_source,
        ) = _finalize_performance(snapshot, store, report_date)
        payload["kpis"] = kpis
        payload["chart"] = chart
        payload["chart_groups"] = chart_groups
        payload["chart_groups_mtd"] = chart_groups_mtd
        payload["chart_monthly"] = chart_monthly
        payload["chart_aging"] = chart_aging
        payload["chart_rate"] = chart_rate
        if total_source:
            payload["total_source"] = total_source
    if "reports.view.followup" in perms:
        _merge_kpis(payload, _followup_kpis(snapshot))
    if "customer.view" in perms:
        payload["customers"] = _customers(store, views)
        due_chart = _due_chart(payload["customers"])
        if due_chart:
            payload["chart_due"] = due_chart
    if type_perm("stock", "view") in perms:
        payload["stock"] = _stock(store, views)
    if live and type_perm("sales", "view") in perms:
        payload["invoices"] = _invoices(store)
        _merge_kpis(payload, _invoice_mtd_kpis(store, report_date))
    if uploads:
        payload["uploads"] = uploads
    if "reports.view.issues" in perms:
        payload["issues"] = {"count": _issues_count(snapshot)}
    if "reports.view.profit" in perms:
        profit = _profit_dashboard(snapshot)
        if profit:
            payload["profit"] = profit
    eligibility = _eligibility_for_run(store, run, live=live)
    visible_eligibility = {
        key: value for key, value in (eligibility or {}).items() if metric_visible(perms, key)
    }
    if visible_eligibility:
        payload["eligibility"] = visible_eligibility
        _apply_eligibility(payload, visible_eligibility)
        if live:
            _attach_stock_numbers(store, payload, report_date)
    recon = ((run or {}).get("manifest") or {}).get("reconciliation") or {}
    exceptions = _visible_exceptions(recon.get("exceptions") or [], perms)
    if exceptions:
        payload["exceptions"] = exceptions
    return payload


_FOLLOWUP_KPI_IDS = {"inactive_mtd", "collection_followups"}
_INVOICE_KPI_IDS = {"invoice_mtd_count", "invoice_mtd_avg"}
_PERFORMANCE_KEYS = (
    "chart",
    "chart_groups",
    "chart_groups_mtd",
    "chart_monthly",
    "chart_aging",
    "chart_rate",
    "total_source",
)


def _visible_exceptions(rows, perms):
    see_sales = metric_visible(perms, "sales_mtd") or metric_visible(perms, "sales_ytd")
    see_ar = metric_visible(perms, "ar_balance")
    exceptions = []
    for row in rows or []:
        mid = (row or {}).get("metric_id") or ""
        if not mid:
            if see_sales or see_ar:
                exceptions.append(row)
        elif mid in ("sales_mtd", "sales_ytd") and see_sales:
            exceptions.append(row)
        elif mid == "ar_balance" and see_ar:
            exceptions.append(row)
        elif metric_visible(perms, mid):
            exceptions.append(row)
    return exceptions


def filter_dashboard(payload, permissions):
    """Drop sections this role cannot see. The stored payload is unfiltered."""
    perms = list(permissions or [])
    out = copy.deepcopy(payload or {})
    kpis = list(out.get("kpis") or [])
    if "reports.view.performance" not in perms:
        kpis = [
            row for row in kpis
            if row.get("id") in _FOLLOWUP_KPI_IDS or row.get("id") in _INVOICE_KPI_IDS
        ]
        for key in _PERFORMANCE_KEYS:
            out.pop(key, None)
    if "reports.view.followup" not in perms:
        kpis = [row for row in kpis if row.get("id") not in _FOLLOWUP_KPI_IDS]
    if type_perm("sales", "view") not in perms:
        kpis = [row for row in kpis if row.get("id") not in _INVOICE_KPI_IDS]
        out.pop("invoices", None)
    if kpis:
        out["kpis"] = kpis
    else:
        out.pop("kpis", None)
    if "customer.view" not in perms:
        out.pop("customers", None)
        out.pop("chart_due", None)
    if type_perm("stock", "view") not in perms:
        out.pop("stock", None)
    if "reports.view.issues" not in perms:
        out.pop("issues", None)
    if "reports.view.profit" not in perms:
        out.pop("profit", None)
    eligibility = {
        key: value
        for key, value in (out.get("eligibility") or {}).items()
        if metric_visible(perms, key)
    }
    if eligibility:
        out["eligibility"] = eligibility
    else:
        out.pop("eligibility", None)
    exceptions = _visible_exceptions(out.get("exceptions") or [], perms)
    if exceptions:
        out["exceptions"] = exceptions
    else:
        out.pop("exceptions", None)
    from server.explain import filter_dashboard_explanations
    return filter_dashboard_explanations(out, perms)


def _overlay_live(store, permissions, payload, run):
    """Refresh upload freshness. Official figures stay on the saved payload."""
    from server.run_views import import_newer_than
    perms = list(permissions or [])
    raw = store.list_uploads() or []
    uploads = _uploads(store, perms, raw)
    freshness = dict(payload.get("freshness") or {})
    freshness["last_upload_at"] = uploads[0]["created_at"] if uploads else ""
    payload["freshness"] = freshness
    payload["has_data"] = _has_data(store, perms, uploads)
    payload["import_newer"] = import_newer_than(store, run, uploads=raw)
    if uploads:
        payload["uploads"] = uploads
    else:
        payload.pop("uploads", None)
    return payload


def serve_dashboard(store, permissions, run_id=None):
    """Return the saved dashboard when the run has one, and backfill older runs once."""
    from server.run_views import resolve_run
    run = resolve_run(store, run_id)
    if not run:
        run = _latest_run(store)
    stored = (run or {}).get("dashboard")
    if run and isinstance(stored, dict):
        return _overlay_live(store, permissions, filter_dashboard(stored, permissions), run)
    if run:
        full = build_dashboard(
            store, list(ALL_PERMISSIONS), run_id=str(run.get("_id") or ""), live=False,
        )
        rid = str(run.get("_id") or "")
        if rid:
            store.update_run(rid, {"dashboard": full})
        return _overlay_live(store, permissions, filter_dashboard(full, permissions), run)
    return build_dashboard(store, permissions, run_id=run_id)
