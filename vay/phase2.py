"""Phase 2 analytics: scorecard, change, movement, collections, stock.

Event totals follow the headline rule: sales net of credit notes on the
credit-note date. Snapshot metrics stay blank when eligibility is unavailable.
A missing earlier period is blank, not zero.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from vay.config import DEFAULT_PARTY
from vay.dates import between_, build_report_context, normalize_date, number_, parse_date

SNAPSHOT_HISTORY = "No earlier snapshot"


def _day(year, month, day):
    last = calendar.monthrange(year, month)[1]
    return datetime(year, month, min(day, last), 12)


def _prev_month(d):
    if d.month == 1:
        return d.year - 1, 12
    return d.year, d.month - 1


def period_windows(report_date):
    """MTD window, the same days in the prior month, and the same days last year."""
    d = normalize_date(parse_date(report_date) or report_date)
    if not d:
        raise ValueError("invalid report_date")
    current = {"start": datetime(d.year, d.month, 1, 12), "end": d, "label": "This period"}
    py, pm = _prev_month(d)
    prior = {"start": datetime(py, pm, 1, 12), "end": _day(py, pm, d.day), "label": "Prior period"}
    prior_year = {
        "start": datetime(d.year - 1, d.month, 1, 12),
        "end": _day(d.year - 1, d.month, d.day),
        "label": "Prior year",
    }
    return {"current": current, "prior": prior, "prior_year": prior_year}


def _in(d, window):
    if not d or not window:
        return False
    return between_(d, window["start"], window["end"])


def _round(value, places=2):
    if value is None:
        return None
    return round(float(value), places)


def _blank(reason=""):
    return {"value": None, "reason": reason or ""}


def _filled(value, places=2):
    return {"value": _round(value, places), "reason": ""}


def _window_sum(dated_amounts, window):
    """Sum amounts inside the window. None when the window has no rows."""
    seen = False
    total = 0.0
    for when, amount in dated_amounts:
        if not _in(when, window):
            continue
        seen = True
        total += amount
    if not seen:
        return None
    return round(total, 2)


def _rate(collection, sales):
    if collection is None or sales is None or sales == 0:
        return None
    return round(100.0 * collection / sales, 1)


def _target_cell(targets, metric_id):
    targets = targets or {}
    if metric_id not in targets or targets.get(metric_id) in ("", None):
        return _blank("No target")
    try:
        return _filled(float(targets[metric_id]))
    except (TypeError, ValueError):
        return _blank("No target")


def _metric(metric_id, label, current, prior, prior_year, targets, reason=""):
    def cell(value, extra=""):
        if reason and value is None and extra == "":
            return _blank(reason)
        if value is None:
            return _blank(extra)
        return _filled(value)

    return {
        "id": metric_id,
        "label": label,
        "current": cell(current),
        "prior": cell(prior, SNAPSHOT_HISTORY if prior is None and reason else ""),
        "prior_year": cell(prior_year, SNAPSHOT_HISTORY if prior_year is None and reason else ""),
        "target": _target_cell(targets, metric_id),
    }


def scorecard(sales, collections, eligibility, targets, report_date, ar_balance=None, overdue=None, ytd_sales=None, margin=None, stock=None):
    """Compare flow metrics across three windows. Snapshots only fill the current column."""
    windows = period_windows(report_date)
    eligibility = eligibility or {}
    sales_c = _window_sum(sales, windows["current"])
    sales_p = _window_sum(sales, windows["prior"])
    sales_y = _window_sum(sales, windows["prior_year"])
    col_c = _window_sum(collections, windows["current"])
    col_p = _window_sum(collections, windows["prior"])
    col_y = _window_sum(collections, windows["prior_year"])

    def flow(metric_id, label, cur, prior, year):
        return _metric(metric_id, label, cur, prior, year, targets)

    rows = [
        flow("sales_mtd", "Sales", sales_c, sales_p, sales_y),
        flow("collections_mtd", "Collections", col_c, col_p, col_y),
        flow(
            "collection_rate",
            "Collection rate",
            _rate(col_c, sales_c),
            _rate(col_p, sales_p),
            _rate(col_y, sales_y),
        ),
    ]
    ar_state = (eligibility.get("ar_balance") or {})
    ar_ok = ar_state.get("status") == "eligible"
    ar_reason = ar_state.get("reason") or "Unavailable"
    if ar_ok:
        rows.append(_metric("ar_balance", "AR balance", ar_balance, None, None, targets))
        rows[-1]["prior"] = _blank(SNAPSHOT_HISTORY)
        rows[-1]["prior_year"] = _blank(SNAPSHOT_HISTORY)
        dso = None
        if ar_balance is not None and ytd_sales and float(ytd_sales) > 0:
            ctx = build_report_context(parse_date(report_date) or report_date)
            days = max(1, (ctx["reportDate"] - ctx["fiscalYearStart"]).days + 1)
            dso = round(float(ar_balance) / (float(ytd_sales) / days), 1)
        rows.append(_metric("dso", "DSO (days)", dso, None, None, targets))
        rows[-1]["prior"] = _blank(SNAPSHOT_HISTORY)
        rows[-1]["prior_year"] = _blank(SNAPSHOT_HISTORY)
        rows.append(_metric("ar_overdue_30", "Overdue 30+", overdue, None, None, targets))
        rows[-1]["prior"] = _blank(SNAPSHOT_HISTORY)
        rows[-1]["prior_year"] = _blank(SNAPSHOT_HISTORY)
    else:
        for metric_id, label in (
            ("ar_balance", "AR balance"),
            ("dso", "DSO (days)"),
            ("ar_overdue_30", "Overdue 30+"),
        ):
            row = _metric(metric_id, label, None, None, None, targets, reason=ar_reason)
            row["current"] = _blank(ar_reason)
            row["prior"] = _blank(ar_reason)
            row["prior_year"] = _blank(ar_reason)
            rows.append(row)

    stock_state = eligibility.get("stock_cover_days") or {}
    stock_ok = stock_state.get("status") == "eligible"
    stock_reason = stock_state.get("reason") or "Unavailable"
    stock = stock or {}
    margin_state = eligibility.get("gross_margin") or {}
    margin_ok = margin_state.get("status") == "eligible"
    margin = margin or {}

    def snapshot_row(metric_id, label, value, ok, reason):
        if not ok:
            row = _metric(metric_id, label, None, None, None, targets, reason=reason)
            row["current"] = _blank(reason)
            row["prior"] = _blank(reason)
            row["prior_year"] = _blank(reason)
            return row
        row = _metric(metric_id, label, value, None, None, targets)
        row["prior"] = _blank(SNAPSHOT_HISTORY)
        row["prior_year"] = _blank(SNAPSHOT_HISTORY)
        return row

    rows.append(snapshot_row(
        "gross_margin", "Gross margin",
        margin.get("current") if margin_ok else None,
        margin_ok, margin_state.get("reason") or "Missing item cost",
    ))
    if margin_ok:
        rows[-1]["prior"] = _filled(margin["prior"]) if margin.get("prior") is not None else _blank()
        rows[-1]["prior_year"] = _filled(margin["prior_year"]) if margin.get("prior_year") is not None else _blank()
    rows.append(snapshot_row(
        "stock_cover_days", "Stock cover (days)",
        stock.get("cover_days") if stock_ok else None,
        stock_ok, stock_reason,
    ))
    rows.append(snapshot_row(
        "slow_stock_value", "Slow stock value",
        stock.get("slow_value") if stock_ok else None,
        stock_ok, (eligibility.get("slow_stock_value") or stock_state).get("reason") or stock_reason,
    ))
    return {"windows": {k: {"label": v["label"], "start": v["start"].strftime("%Y-%m-%d"), "end": v["end"].strftime("%Y-%m-%d")} for k, v in windows.items()}, "rows": rows}


def _party_key(name):
    text = (name or "").strip()
    if not text or text == DEFAULT_PARTY:
        return ""
    return text.lower()


QTY_NEEDS_LINES = "Quantity needs item lines in these periods"


def _present(value):
    if value is None or value == "":
        return None
    return round(float(value), 2)


def _sum_present(rows, key):
    vals = [row.get(key) for row in rows or [] if row.get(key) is not None]
    if not vals:
        return None
    return round(sum(float(value) for value in vals), 2)


def _signed(change):
    if change is None:
        return None
    if change > 0:
        return "up"
    if change < 0:
        return "down"
    return "flat"


def _side_phrase(name, direction):
    word = {"up": "up", "down": "down", "flat": "unchanged"}[direction]
    return "%s is %s" % (name, word)


def _amount_only(direction):
    if direction == "up":
        return "Amount is up."
    if direction == "down":
        return "Amount is down."
    if direction == "flat":
        return "Amount is unchanged."
    return "Amount cannot be compared with the prior period."


def _verdict(qty, amount):
    qty_ok = (qty or {}).get("status") == "eligible"
    amount_direction = _signed((amount or {}).get("change"))
    if not qty_ok:
        return _amount_only(amount_direction)
    qty_direction = _signed(qty.get("change"))
    if qty_direction is None and amount_direction is None:
        return "Sales cannot be compared with the prior period."
    if qty_direction is None:
        return "Quantity cannot be compared with the prior period. " + _amount_only(amount_direction)
    if amount_direction is None:
        return "Amount cannot be compared with the prior period. " + _side_phrase("Quantity", qty_direction) + "."
    if qty_direction == "up" and amount_direction == "up":
        return "Sales improved on quantity and amount."
    if qty_direction == "down" and amount_direction == "down":
        return "Sales declined on quantity and amount."
    if qty_direction == "flat" and amount_direction == "flat":
        return "Quantity and amount are unchanged."
    if qty_direction == "up" and amount_direction == "down":
        return "Quantity is up and amount is down."
    if qty_direction == "down" and amount_direction == "up":
        return "Amount is up and quantity is down."
    return _side_phrase("Quantity", qty_direction) + " and " + _side_phrase("amount", amount_direction) + "."


def _measure(current, prior, available, reason):
    current = _present(current)
    prior = _present(prior)
    if not available:
        return {
            "status": "unavailable",
            "reason": reason,
            "current": None,
            "prior": None,
            "change": None,
        }
    change = None
    if current is not None and prior is not None:
        change = round(current - prior, 2)
    return {
        "status": "eligible",
        "reason": "",
        "current": current,
        "prior": prior,
        "change": change,
    }


def compare_measures(qty_current, qty_prior, amount_current, amount_prior, qty_available=True):
    """Quantity and amount for one window, plus the sentence that reads both."""
    qty = _measure(qty_current, qty_prior, qty_available, QTY_NEEDS_LINES)
    amount = _measure(amount_current, amount_prior, True, "")
    return {"qty": qty, "amount": amount, "verdict": _verdict(qty, amount)}


def pair_windows(
    month_qty, month_qty_prior, month_amount, month_amount_prior,
    year_qty, year_qty_prior, year_amount, year_amount_prior,
    qty_available=True,
):
    """This month vs last month, and this year vs last year."""
    month = compare_measures(month_qty, month_qty_prior, month_amount, month_amount_prior, qty_available)
    month["label"] = "This month vs last month"
    month["current_label"] = "This month"
    month["prior_label"] = "Last month"
    year = compare_measures(year_qty, year_qty_prior, year_amount, year_amount_prior, qty_available)
    year["label"] = "This year vs last year"
    year["current_label"] = "This year"
    year["prior_label"] = "Last year"
    return {"month": month, "year": year}


def sales_change(customers, products):
    """Rank who moved net sales. Price-volume only when qty and rate match across periods."""
    cust_rows = []
    for row in customers or []:
        name = (row.get("name") or "").strip()
        if not _party_key(name):
            continue
        current = row.get("current")
        prior = row.get("prior")
        if current is None and prior is None:
            continue
        change = round(float(current or 0) - float(prior or 0), 2)
        cust_rows.append({
            "name": name,
            "customer_id": row.get("customer_id") or "",
            "current": current,
            "prior": prior,
            "change": change,
            "drill": {"kind": "customer", "name": name},
        })
    cust_rows.sort(key=lambda r: (-abs(r["change"]), r["name"].lower()))

    prod_rows = []
    price = volume = mix = 0.0
    comparable = 0
    for row in products or []:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        q0, p0 = row.get("qty_prior"), row.get("rate_prior")
        q1, p1 = row.get("qty_current"), row.get("rate_current")
        v0 = None if q0 is None or p0 is None else round(float(q0) * float(p0), 2)
        v1 = None if q1 is None or p1 is None else round(float(q1) * float(p1), 2)
        if v0 is None and v1 is None and q0 is None and q1 is None:
            continue
        change = round(float(v1 or 0) - float(v0 or 0), 2)
        both = q0 is not None and p0 is not None and q1 is not None and p1 is not None
        if both:
            price += (float(p1) - float(p0)) * float(q1)
            volume += (float(q1) - float(q0)) * float(p0)
            comparable += 1
        elif v0 is not None or v1 is not None:
            mix += float(v1 or 0) - float(v0 or 0)
        qty_change = None
        if q0 is not None and q1 is not None:
            qty_change = round(float(q1) - float(q0), 2)
        prod_rows.append({
            "name": name,
            "product_id": row.get("product_id") or "",
            "current": v1,
            "prior": v0,
            "change": change,
            "qty_current": q1,
            "qty_prior": q0,
            "qty_change": qty_change,
            "drill": {"kind": "item", "name": name},
        })
    prod_rows.sort(key=lambda r: (-abs(r["change"]), r["name"].lower()))
    if comparable:
        bridge = {
            "status": "eligible",
            "reason": "",
            "price": round(price, 2),
            "volume": round(volume, 2),
            "mix": round(mix, 2),
        }
    else:
        bridge = {
            "status": "unavailable",
            "reason": "Price and volume need quantity and rate in both periods",
            "price": None,
            "volume": None,
            "mix": None,
        }
    qty_available = any(
        row.get("qty_current") is not None or row.get("qty_prior") is not None
        for row in prod_rows
    )
    summary = compare_measures(
        _sum_present(prod_rows, "qty_current"),
        _sum_present(prod_rows, "qty_prior"),
        _sum_present(cust_rows, "current"),
        _sum_present(cust_rows, "prior"),
        qty_available=qty_available,
    )
    summary["label"] = "This period vs prior period"
    summary["current_label"] = "This period"
    summary["prior_label"] = "Prior period"
    return {"customers": cust_rows, "products": prod_rows, "bridge": bridge, "summary": summary}


def customer_movement(accounts, report_date, ids_by_name=None):
    """New, repeat, inactive, and reactivated customers. Credit notes do not count as a sale."""
    windows = period_windows(report_date)
    ctx = build_report_context(parse_date(report_date) or report_date)
    ids_by_name = ids_by_name or {}
    rows = []
    for account in accounts or []:
        name = (account.get("name") or "").strip()
        if not _party_key(name):
            continue
        sales_dates = []
        for inv in account.get("invoices") or []:
            when = inv.get("date")
            amount = float(inv.get("amount") or 0)
            if not when or amount == 0:
                continue
            sales_dates.append(when)
        if not sales_dates:
            continue
        sales_dates.sort()
        current = _signed_in(account, windows["current"])
        prior = _signed_in(account, windows["prior"])
        before_prior = any(d < windows["prior"]["start"] for d in sales_dates)
        summary = account.get("summary") or {}
        mtd = float(summary.get("mtdSales") or 0)
        if mtd == 0 and not _has_history(account):
            continue
        if mtd > 0 and sales_dates[0] >= windows["current"]["start"]:
            movement = "new"
            status = ""
        elif mtd > 0 and (prior or 0) == 0 and before_prior:
            movement = "reactivated"
            status = ""
        elif mtd > 0:
            movement = "repeat"
            status = ""
        else:
            movement = "inactive"
            status = _inactive_status(account)
        cycle, cycle_reason = _buying_cycle(sales_dates, ctx["reportDate"])
        rows.append({
            "name": name,
            "customer_id": ids_by_name.get(name.lower()) or account.get("customer_id") or "",
            "movement": movement,
            "status": status,
            "current": current,
            "prior": prior,
            "buying_cycle": cycle,
            "buying_cycle_reason": cycle_reason,
            "drill": {"kind": "customer", "name": name},
        })
    order = {"inactive": 0, "reactivated": 1, "new": 2, "repeat": 3}
    rows.sort(key=lambda r: (order.get(r["movement"], 9), r["name"].lower()))
    return {"rows": rows}


def _signed_in(account, window):
    seen = False
    total = 0.0
    for inv in account.get("invoices") or []:
        if _in(inv.get("date"), window):
            seen = True
            total += float(inv.get("amount") or 0)
    for credit in account.get("credits") or []:
        if _in(credit.get("date"), window):
            seen = True
            total -= float(credit.get("amount") or 0)
    if not seen:
        return None
    return round(total, 2)


def _has_history(account):
    summary = account.get("summary") or {}
    if float(summary.get("ytdSales") or 0) != 0:
        return True
    for key in ("d0to15Sales", "d16to30Sales", "d31to60Sales", "olderSales"):
        if float(account.get(key) or 0) != 0:
            return True
    if float(summary.get("m2Sales") or 0) != 0 or float(summary.get("m3Sales") or 0) != 0:
        return True
    return bool(account.get("invoices"))


def _inactive_status(account):
    if float(account.get("d0to15Sales") or 0) > 0:
        return "NEWLY INACTIVE"
    if float(account.get("d16to30Sales") or 0) > 0:
        return "FOLLOW UP"
    if float(account.get("d31to60Sales") or 0) > 0:
        return "URGENT"
    return "DORMANT"


def _buying_cycle(dates, report_date):
    unique = []
    for d in dates:
        day = d.strftime("%Y-%m-%d")
        if not unique or unique[-1] != day:
            unique.append(day)
    if len(unique) < 3:
        return None, "Not enough history"
    parsed = [datetime.strptime(day, "%Y-%m-%d") for day in unique]
    gaps = [(parsed[i] - parsed[i - 1]).days for i in range(1, len(parsed))]
    gaps.sort()
    median = gaps[len(gaps) // 2]
    last = parsed[-1]
    late = (report_date - last).days > max(median, 1) * 1.5
    return ("overdue" if late else "on cycle"), ""


def collection_worklist(accounts):
    """Rank open balances. Named receipts are exact; otherwise lines are estimated."""
    priority = {"URGENT": 3, "FOLLOW UP": 2, "WATCH": 1}
    rows = []
    for account in accounts or []:
        name = (account.get("name") or "").strip()
        balance = float(account.get("balance") or 0)
        if not _party_key(name) or balance <= 0:
            continue
        overdue = float(account.get("overdue30") or account.get("bal30Plus") or 0)
        mid = float(account.get("overdue15") or account.get("bal15Plus") or 0)
        if overdue > 0:
            status = "URGENT"
        elif mid > 0:
            status = "FOLLOW UP"
        else:
            status = "WATCH"
        invoices, detail = _invoice_lines(account)
        rows.append({
            "name": name,
            "customer_id": account.get("customer_id") or "",
            "status": status,
            "balance": round(balance, 2),
            "overdue_30": round(overdue, 2),
            "invoice_detail": detail,
            "invoices": invoices,
            "drill": {"kind": "customer", "name": name},
        })
    rows.sort(key=lambda r: (-priority.get(r["status"], 0), -r["overdue_30"], -r["balance"], r["name"].lower()))
    return {"rows": rows}


def _dated(value):
    if value is None or value == "":
        return None
    if hasattr(value, "year"):
        return value
    return parse_date(value)


def _invoice_lines(account):
    """Invoice lines when a receipt names the invoice.

    When receipts do not name an invoice, allocate with oldest-first settlement
    and mark the lines estimated. Stay unavailable when there is no invoice
    identity or no receipt to allocate.
    """
    invoices = [inv for inv in (account.get("invoices") or []) if (inv.get("invoice") or "").strip()]
    receipts = account.get("receipts") or []
    credits = account.get("credits") or []
    named = [rec for rec in receipts if (rec.get("invoice") or "").strip()]
    loose_receipts = _loose_money(receipts)
    loose_credits = _loose_money(credits)
    if invoices and named and not loose_receipts and not loose_credits:
        matched = _named_invoice_lines(invoices, named, credits)
        if matched[1] == "available":
            return matched
    if invoices and named and (loose_receipts or loose_credits):
        mixed = _mixed_invoice_lines(account, invoices, named, loose_receipts, loose_credits, credits)
        if mixed[1] != "unavailable":
            return mixed
    return _estimated_invoice_lines(account, invoices)


def _loose_money(rows):
    loose = []
    for row in rows or []:
        if (row.get("invoice") or "").strip():
            continue
        if float(row.get("amount") or 0) > 0:
            loose.append(row)
    return loose


def _mixed_invoice_lines(account, invoices, named_receipts, loose_receipts, loose_credits, credits):
    """Named receipts stay exact. Receipts without an invoice number are estimated on what remains."""
    named_credits = [row for row in credits or [] if (row.get("invoice") or "").strip()]
    named_lines, named_status = _named_invoice_lines(invoices, named_receipts, named_credits)
    taken = {}
    by_no = {}
    if named_status == "available":
        for line in named_lines:
            taken[line["invoice"]] = line["allocated"]
            by_no[line["invoice"]] = dict(line)
    originals = {}
    reduced = []
    for inv in invoices:
        key = inv["invoice"].strip()
        originals[key] = float(inv.get("amount") or 0)
        remain = round(originals[key] - taken.get(key, 0.0), 2)
        if remain <= 0:
            continue
        reduced.append({
            "date": inv.get("date"),
            "amount": remain,
            "invoice": key,
        })
    if not reduced:
        if named_status != "available":
            return [], "unavailable"
        return list(by_no.values()), "estimated"
    estimated_lines, est_status = _estimated_invoice_lines(
        {"receipts": loose_receipts, "credits": loose_credits, "as_of": account.get("as_of")},
        reduced,
    )
    if est_status != "estimated":
        return [], "unavailable"
    for line in estimated_lines:
        key = line["invoice"]
        base = by_no.get(key)
        extra = float(line.get("allocated") or 0)
        original = originals.get(key, line["amount"])
        if not base:
            by_no[key] = {
                "invoice": key,
                "amount": round(original, 2),
                "allocated": round(extra, 2),
                "remaining": round(original - extra, 2),
                "basis": "estimated",
            }
            continue
        base["allocated"] = round(float(base["allocated"]) + extra, 2)
        base["remaining"] = round(float(base["amount"]) - base["allocated"], 2)
        base["basis"] = "estimated"
    lines = sorted(by_no.values(), key=lambda row: row["invoice"])
    return lines, "estimated"


def _named_invoice_lines(invoices, receipts, credits):
    by_no = {}
    for inv in invoices:
        key = inv["invoice"].strip().lower()
        slot = by_no.setdefault(key, {"invoice": inv["invoice"].strip(), "amount": 0.0, "allocated": 0.0})
        slot["amount"] += float(inv.get("amount") or 0)
    matched = False
    for rec in receipts:
        key = rec["invoice"].strip().lower()
        if key not in by_no:
            continue
        matched = True
        by_no[key]["allocated"] += float(rec.get("amount") or 0)
    for credit in credits:
        key = (credit.get("invoice") or "").strip().lower()
        if key and key in by_no:
            by_no[key]["allocated"] += float(credit.get("amount") or 0)
    if not matched:
        return [], "unavailable"
    lines = []
    for slot in by_no.values():
        lines.append({
            "invoice": slot["invoice"],
            "amount": round(slot["amount"], 2),
            "allocated": round(slot["allocated"], 2),
            "remaining": round(slot["amount"] - slot["allocated"], 2),
            "basis": "named",
        })
    lines.sort(key=lambda r: r["invoice"])
    return lines, "available"


def _estimated_invoice_lines(account, invoices):
    if not invoices:
        return [], "unavailable"
    receipts = []
    for rec in account.get("receipts") or []:
        when = _dated(rec.get("date"))
        amount = float(rec.get("amount") or 0)
        if when and amount > 0:
            receipts.append({"date": when, "amount": amount, "invoice": rec.get("invoice") or ""})
    credits = []
    for credit in account.get("credits") or []:
        when = _dated(credit.get("date"))
        amount = float(credit.get("amount") or 0)
        if when and amount > 0:
            credits.append({"date": when, "amount": amount, "invoice": credit.get("invoice") or ""})
    if not receipts and not credits:
        return [], "unavailable"
    prepared = []
    for inv in invoices:
        when = _dated(inv.get("date"))
        if not when:
            return [], "unavailable"
        prepared.append({
            "date": when,
            "amount": float(inv.get("amount") or 0),
            "invoice": inv["invoice"].strip(),
        })
    as_of = _dated(account.get("as_of")) or prepared[-1]["date"]
    from vay.settlement import allocate_collections

    _buckets, allocations, _credit, _remainders, _opening = allocate_collections(
        prepared,
        receipts,
        as_of,
        mode="oldest",
        credits=credits,
    )
    allocated = {}
    for row in allocations:
        key = (row.get("invoice") or "").strip()
        if not key:
            continue
        allocated[key] = round(allocated.get(key, 0.0) + float(row.get("amount") or 0), 2)
    lines = []
    for inv in prepared:
        taken = allocated.get(inv["invoice"], 0.0)
        lines.append({
            "invoice": inv["invoice"],
            "amount": round(inv["amount"], 2),
            "allocated": taken,
            "remaining": round(inv["amount"] - taken, 2),
            "basis": "estimated",
        })
    lines.sort(key=lambda r: r["invoice"])
    return lines, "estimated"


def stock_decisions(items, stock_rows, report_date):
    """Velocity, cover, and slow stock. Zero demand is labelled. Missing cost is excluded from the value."""
    d = normalize_date(parse_date(report_date) or report_date)
    if not d:
        raise ValueError("invalid report_date")
    start_30 = d - timedelta(days=29)
    month_start = datetime(d.year, d.month, 1, 12)
    demand = {}
    for row in items or []:
        name = (row.get("name") or "").strip()
        when = row.get("date")
        if not name or not when or when > d:
            continue
        qty = row.get("qty")
        if qty is None:
            continue
        slot = demand.setdefault(name, {"qty_30": 0.0, "qty_mtd": 0.0, "seen_30": False, "product_id": row.get("product_id") or ""})
        if row.get("product_id") and not slot["product_id"]:
            slot["product_id"] = row["product_id"]
        if when >= start_30:
            slot["qty_30"] += float(qty)
            slot["seen_30"] = True
        if when >= month_start:
            slot["qty_mtd"] += float(qty)
    costs = {}
    on_hand = {}
    for row in stock_rows or []:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        qty = float(row.get("qty") or 0)
        on_hand[name] = on_hand.get(name, 0.0) + qty
        price = row.get("cost")
        if price is not None:
            costs[name] = float(price)
    rows = []
    slow_value = 0.0
    slow_seen = False
    uncosted = 0
    cover_qty = 0.0
    cover_demand = 0.0
    names = sorted(set(on_hand) | set(demand), key=str.lower)
    for name in names:
        qty_on = on_hand.get(name, 0.0)
        slot = demand.get(name) or {}
        qty_30 = float(slot.get("qty_30") or 0)
        per_day = qty_30 / 30.0 if qty_30 > 0 else 0.0
        if per_day > 0:
            cover = int(round(qty_on / per_day))
            cover_label = ""
            cover_qty += qty_on
            cover_demand += per_day
        else:
            cover = None
            cover_label = "No recent demand"
        cost = costs.get(name)
        slow = qty_on > 0 and qty_30 <= 0
        line_value = None
        if slow:
            if cost is None:
                uncosted += 1
            else:
                line_value = round(qty_on * cost, 2)
                slow_value += line_value
                slow_seen = True
        if qty_on == 0 and qty_30 == 0 and not slot:
            continue
        rows.append({
            "name": name,
            "product_id": slot.get("product_id") or "",
            "on_hand": round(qty_on, 2),
            "qty_30": round(qty_30, 2),
            "qty_mtd": round(float(slot.get("qty_mtd") or 0), 2),
            "cover_days": cover,
            "cover_label": cover_label,
            "slow": slow,
            "slow_value": line_value,
            "drill": {"kind": "item", "name": name},
        })
    headline_cover = int(round(cover_qty / cover_demand)) if cover_demand > 0 else None
    return {
        "rows": rows,
        "cover_days": headline_cover,
        "cover_label": "" if headline_cover is not None else "No recent demand",
        "slow_value": round(slow_value, 2) if slow_seen else (0.0 if stock_rows else None),
        "uncosted": uncosted,
    }


def _sale_day(when):
    if when is None:
        return ""
    if hasattr(when, "strftime"):
        return when.strftime("%Y-%m-%d")
    return str(when)[:10]


def cost_for_sale(costs, name, when):
    """Latest cost on or before the sale. A later cost does not reprice it.

    A plain number is the undated snapshot price. A missing cost stays missing.
    """
    entry = (costs or {}).get(name) if name else None
    if entry is None:
        return None, ""
    if isinstance(entry, (int, float)):
        return float(entry), "snapshot"
    if not isinstance(entry, dict):
        return None, ""
    history = entry.get("history") or []
    sale = _sale_day(when)
    best_day = ""
    best = None
    for row in history:
        day = str(row.get("date") or "")[:10]
        cost = row.get("cost")
        if cost is None or not day or not sale or day > sale:
            continue
        if day >= best_day:
            best_day = day
            best = float(cost)
    if best is not None:
        return best, "historical"
    snapshot = entry.get("snapshot")
    if snapshot is not None:
        return float(snapshot), "snapshot"
    return None, ""


def gross_margin_periods(items, costs, report_date, tax_rate):
    """Margin for each window. A window with a missing cost is unavailable."""
    windows = period_windows(report_date)
    rate = float(tax_rate or 0)
    out = {}
    current_kinds = []
    for key, window in windows.items():
        sales = 0.0
        cogs = 0.0
        seen = False
        missing = False
        kinds = []
        for row in items or []:
            when = row.get("date")
            if not _in(when, window):
                continue
            qty = row.get("qty")
            price = row.get("rate")
            if qty is None or price is None:
                continue
            seen = True
            name = (row.get("name") or "").strip()
            cost, kind = cost_for_sale(costs, name, when)
            if cost is None:
                missing = True
                break
            kinds.append(kind)
            sales += float(qty) * float(price)
            cogs += float(qty) * float(cost)
        if key == "current":
            current_kinds = kinds
        if not seen or missing or sales == 0:
            out[key] = None
            continue
        net = sales / (1 + rate) if rate else sales
        if net == 0:
            out[key] = None
            continue
        out[key] = round(100.0 * (net - cogs) / net, 1)
    if current_kinds and "historical" in current_kinds and "snapshot" not in current_kinds:
        out["cost_label"] = "Historical cost"
    elif current_kinds:
        out["cost_label"] = "Snapshot cost"
    else:
        out["cost_label"] = ""
    return out


def quality_fixes(exceptions, eligibility=None, review_count=0):
    """One plain-language fix for each Phase 1 exception."""
    rows = []
    for exc in exceptions or []:
        rows.append({
            "severity": exc.get("severity") or "info",
            "message": exc.get("message") or "",
            "affected_reports": list(exc.get("affected_reports") or []),
            "fix": _fix_text(exc),
        })
    eligibility = eligibility or {}
    for metric_id, entry in eligibility.items():
        if (entry or {}).get("status") != "unavailable":
            continue
        reason = entry.get("reason") or "Unavailable"
        if any(reason and reason in (row.get("message") or "") for row in rows):
            continue
        rows.append({
            "severity": "warning",
            "message": reason,
            "affected_reports": [metric_id],
            "fix": _fix_text({"metric_id": metric_id, "message": reason, "severity": "warning"}),
        })
    if review_count:
        rows.append({
            "severity": "warning",
            "message": "%s name%s need review" % (review_count, "" if review_count == 1 else "s"),
            "affected_reports": ["Customers", "Products"],
            "fix": "Review the near-match in Settings → Account migrations.",
        })
    return {"rows": rows}


def _fix_text(exc):
    message = (exc.get("message") or "").lower()
    metric = exc.get("metric_id") or ""
    if "sidecar" in message or (exc.get("severity") == "info" and not metric):
        return "Attach a reconciliation file with the source sales and outstanding totals."
    if "cost" in message or metric == "gross_margin":
        return "Add a stock purchase price for items that have sales."
    if metric == "stock_cover_days" or "stock snapshot" in message:
        return "Replace the stock file so its date matches the report date."
    if "snapshot" in message or "no ar" in message or "no stock" in message:
        return "Replace the outstanding or stock file so its date matches the report date."
    if metric in ("sales_mtd", "sales_ytd"):
        return "Re-import sales or correct the sidecar sales total."
    if metric == "ar_balance":
        return "Re-import outstanding or correct the sidecar outstanding total."
    if "name" in message or "near" in message:
        return "Review the near-match in Settings → Account migrations."
    return "Open the affected report and correct the source file."


def _control_money(value):
    try:
        return "%.2f" % float(value)
    except (TypeError, ValueError):
        return "0.00"


def onboarding_checklist(eligibility, present_types, sources=None, controls=None):
    """What the current files can and cannot support."""
    present = set(present_types or [])
    needed = (
        ("sales", "Sales"),
        ("receipt", "Receipts"),
        ("arr", "Outstanding"),
        ("items", "Item sales"),
        ("stock", "Stock"),
    )
    missing = [{"type": key, "label": label} for key, label in needed if key not in present]
    metrics = []
    for metric_id, entry in (eligibility or {}).items():
        status = (entry or {}).get("status") or "unavailable"
        reason = (entry or {}).get("reason") or ""
        metrics.append({
            "id": metric_id,
            "status": status,
            "reason": reason,
            "fix": "" if status == "eligible" else _fix_text({"metric_id": metric_id, "message": reason}),
        })
    exceptions = []
    labels = {"sales": "Sales", "outstanding": "Outstanding"}
    for key, label in labels.items():
        entry = (controls or {}).get(key) or {}
        if entry.get("entered") is None or entry.get("match"):
            continue
        exceptions.append({
            "id": "%s_control" % key,
            "message": "%s total %s does not match the entered total %s." % (
                label,
                _control_money(entry.get("actual")),
                _control_money(entry.get("entered")),
            ),
        })
    return {
        "missing_files": missing,
        "metrics": metrics,
        "sources": list(sources or []),
        "controls": controls or {},
        "exceptions": exceptions,
    }


def excel_reports(bundle):
    """Report dicts the existing workbook writer already understands."""
    bundle = bundle or {}
    reports = []
    score = bundle.get("scorecard") or {}
    rows = []
    for row in score.get("rows") or []:
        rows.append([
            row.get("label") or "",
            _excel_cell(row.get("current")),
            _excel_cell(row.get("prior")),
            _excel_cell(row.get("prior_year")),
            _excel_cell(row.get("target")),
        ])
    reports.append(_sheet("phase2_scorecard", "Scorecard", ["Metric", "This period", "Prior period", "Prior year", "Target"], rows, "Scorecard"))
    change = bundle.get("sales_change") or {}
    summary = change.get("summary") or {}
    qty = summary.get("qty") or {}
    amount = summary.get("amount") or {}

    def _excel_measure(row):
        if row.get("status") == "unavailable":
            return [row.get("reason") or "", "", ""]
        return [row.get("current"), row.get("prior"), row.get("change")]

    sales_rows = [
        [summary.get("verdict") or "", "", "", "", "", "", ""],
        ["Measure", "This period", "Prior period", "Change", "", "", ""],
        ["Quantity", *_excel_measure(qty), "", "", "", ""],
        ["Amount", *_excel_measure(amount), "", "", "", ""],
        ["", "", "", "", "", "", ""],
        ["Customer", "This period", "Prior period", "Change", "", "", ""],
    ]
    sales_rows.extend(
        [r.get("name"), r.get("current"), r.get("prior"), r.get("change"), "", "", ""]
        for r in change.get("customers") or []
    )
    sales_rows.append(["", "", "", "", "", "", ""])
    sales_rows.append(["Product", "Qty this period", "Qty prior", "Qty change", "Amount this period", "Amount prior", "Amount change"])
    sales_rows.extend(
        [r.get("name"), r.get("qty_current"), r.get("qty_prior"), r.get("qty_change"), r.get("current"), r.get("prior"), r.get("change")]
        for r in change.get("products") or []
    )
    reports.append(_sheet(
        "phase2_sales_change",
        "Sales change",
        ["Sales change", "This period", "Prior period", "Change", "Amount this period", "Amount prior", "Amount change"],
        sales_rows,
        "Scorecard",
    ))
    movement = bundle.get("customer_movement") or {}
    reports.append(_sheet(
        "phase2_customer_movement",
        "Customer movement",
        ["Customer", "Movement", "Status", "This period", "Prior period", "Buying cycle"],
        [[r.get("name"), r.get("movement"), r.get("status"), r.get("current"), r.get("prior"), r.get("buying_cycle") or r.get("buying_cycle_reason") or ""] for r in movement.get("rows") or []],
        "Scorecard",
    ))
    work = bundle.get("collection") or {}
    coll_rows = []
    if work.get("status") == "unavailable":
        coll_rows.append(["", work.get("reason") or "Unavailable", "", "", ""])
    for row in work.get("rows") or []:
        detail = _collection_invoice_text(row)
        coll_rows.append([row.get("name"), row.get("status"), row.get("balance"), row.get("overdue_30"), detail])
    reports.append(_sheet("phase2_collection", "Collection worklist", ["Customer", "Status", "Balance", "Overdue 30+", "Invoices"], coll_rows, "Follow-up"))
    stock = bundle.get("stock") or {}
    stock_rows = []
    if stock.get("status") == "unavailable":
        stock_rows.append([stock.get("reason") or "Unavailable", "", "", "", "", ""])
    stock_rows.extend([
        [r.get("name"), r.get("on_hand"), r.get("qty_30"), r.get("qty_mtd"), r.get("cover_days") if r.get("cover_days") is not None else r.get("cover_label"), r.get("slow_value")]
        for r in stock.get("rows") or []
    ])
    if stock.get("rows"):
        reports.append(_sheet("phase2_stock", "Stock decisions", ["Item", "On hand", "Qty 30 days", "Qty MTD", "Cover days", "Slow value"], stock_rows, "Items"))
    quality = bundle.get("quality") or {}
    reports.append(_sheet(
        "phase2_quality",
        "Data quality",
        ["Severity", "Message", "Fix"],
        [[r.get("severity"), r.get("message"), r.get("fix")] for r in quality.get("rows") or []],
        "Data issues",
    ))
    return [r for r in reports if r.get("rows")]


def _excel_cell(cell):
    if not isinstance(cell, dict):
        return cell
    if cell.get("value") is None:
        return cell.get("reason") or ""
    return cell.get("value")


def _collection_invoice_text(row):
    detail = row.get("invoice_detail")
    if detail == "unavailable":
        return "Invoice detail unavailable"
    parts = []
    for inv in row.get("invoices") or []:
        label = "%s remaining %s" % (inv.get("invoice"), inv.get("remaining"))
        if inv.get("basis") == "estimated":
            label += " (estimated)"
        parts.append(label)
    return "; ".join(parts) if parts else "Invoice detail unavailable"


def _sheet(report_id, title, headers, rows, group=""):
    return {
        "id": report_id,
        "title": title,
        "headers": headers,
        "rows": rows,
        "total": None,
        "key_col": 0,
        "group": group,
    }
