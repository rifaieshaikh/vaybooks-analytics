"""Cash payment summary for one customer.

Receipts are observed cash. Credit notes stay in a separate total. A missing
date stays out of gap and period figures. A prior window that the books do not
cover is unavailable, not a zero.
"""

from __future__ import annotations

from datetime import date, datetime

from vay.dates import fiscal_year_start, fy_label, normalize_fy_start_month, parse_date
from vay.ledger import money


def payment_summary(receipts, *, as_of, start_month=None, coverage=None):
    as_of_day = _as_date(as_of)
    cash, non_cash = _occasions(receipts, as_of_day)
    dated = [row for row in cash if row["date"]]
    undated = [row for row in cash if not row["date"]]
    gaps = _gaps(dated)
    current, prior, trend_available, trend_reason = _windows(as_of_day, start_month, coverage)
    current_rows = _in_window(dated, current) if current else []
    prior_rows = _in_window(dated, prior) if prior and trend_available else []
    return {
        "basis": "cash_receipts",
        "evidence": "source_confirmed",
        "note": "Totals count cash receipts. Credit notes are separate and are not payment behavior. Inferred settlement is labeled on each receipt and is not confirmed payment timing.",
        "cash_total": _amount(cash),
        "occasions": len(cash),
        "typical_amount": _median_money([row["amount"] for row in cash]),
        "median_gap_days": _median_number(gaps),
        "gap_count": len(gaps),
        "dated_occasions": len(dated),
        "undated_count": len(undated),
        "undated_amount": _amount(undated),
        "non_cash_total": _amount(non_cash),
        "non_cash_count": len(non_cash),
        "transactions": [_public_row(row) for row in sorted(cash, key=lambda item: (item["date"] or date.min, item["source_id"]))],
        "non_cash": [_public_row(row) for row in non_cash],
        "trend": {
            "available": trend_available,
            "reason": trend_reason,
            "current": _window_public(current, current_rows),
            "prior": _window_public(prior, prior_rows) if trend_available else _window_public(prior, []),
            "cash_change_percent": _change(_amount(current_rows), _amount(prior_rows)) if trend_available else None,
        },
    }


def _occasions(receipts, as_of_day):
    cash = []
    non_cash = []
    for row in receipts or []:
        amount = money(row.get("amount"))
        day = _as_date(row.get("date") or row.get("effective_date"))
        if amount is None or amount <= 0:
            continue
        if as_of_day and day and day > as_of_day:
            continue
        labels = row.get("evidence") or []
        if isinstance(labels, str):
            labels = [labels]
        slot = {
            "source_id": str(row.get("source_id") or ""),
            "amount": amount,
            "date": day,
            "evidence": {label for label in labels if label},
            "cash": bool(row.get("cash")),
        }
        (cash if slot["cash"] else non_cash).append(slot)
    return cash, non_cash


def _gaps(dated):
    ordered = sorted(dated, key=lambda row: (row["date"], row["source_id"]))
    gaps = []
    for earlier, later in zip(ordered, ordered[1:]):
        gaps.append((later["date"] - earlier["date"]).days)
    return gaps


def _windows(as_of_day, start_month, coverage):
    if not as_of_day:
        return None, None, False, "No cutoff date."
    sm = normalize_fy_start_month(start_month)
    current_start = fiscal_year_start(datetime(as_of_day.year, as_of_day.month, as_of_day.day, 12), sm).date()
    prior_end = _shift_year(as_of_day, -1)
    prior_start = fiscal_year_start(datetime(prior_end.year, prior_end.month, prior_end.day, 12), sm).date()
    current = {"start": current_start, "end": as_of_day, "label": "%s through %s" % (fy_label(datetime(current_start.year, current_start.month, 1, 12)), as_of_day.isoformat())}
    prior = {"start": prior_start, "end": prior_end, "label": "%s through %s" % (fy_label(datetime(prior_start.year, prior_start.month, 1, 12)), prior_end.isoformat())}
    available, reason = _prior_available(prior_start, coverage)
    return current, prior, available, reason


def _prior_available(prior_start, coverage):
    coverage = coverage or {}
    if not coverage.get("complete"):
        return False, "Movement history is incomplete, so the earlier window is not compared."
    start = _as_date(coverage.get("start"))
    if start and start > prior_start:
        return False, "Imported history starts after the earlier window."
    return True, ""


def _in_window(rows, window):
    if not window:
        return []
    start, end = window["start"], window["end"]
    return [row for row in rows if row["date"] and start <= row["date"] <= end]


def _window_public(window, rows):
    if not window:
        return None
    return {
        "label": window["label"],
        "start": window["start"].isoformat(),
        "end": window["end"].isoformat(),
        "cash_total": _amount(rows),
        "occasions": len(rows),
        "typical_amount": _median_money([row["amount"] for row in rows]),
        "transactions": [row["source_id"] for row in rows],
    }


def _public_row(row):
    evidence = _settlement_evidence(row["evidence"])
    return {
        "source_id": row["source_id"],
        "date": row["date"].isoformat() if row["date"] else None,
        "amount": float(row["amount"]),
        "cash": row["cash"],
        "settlement_evidence": evidence,
    }


def _settlement_evidence(labels):
    labels = {label for label in labels if label}
    if not labels:
        return ""
    if labels == {"unapplied"}:
        return "unapplied"
    settled = labels - {"unapplied"}
    if "inferred" in settled and settled - {"inferred"}:
        return "mixed"
    if settled == {"inferred"}:
        return "inferred"
    if len(settled) == 1:
        return next(iter(settled))
    return "mixed"


def _amount(rows):
    total = money(0)
    for row in rows:
        total = money(total + row["amount"])
    return float(total)


def _median_money(amounts):
    if not amounts:
        return None
    ordered = sorted(amounts)
    count = len(ordered)
    if count % 2:
        return float(ordered[count // 2])
    return float(money((ordered[count // 2 - 1] + ordered[count // 2]) / 2))


def _median_number(values):
    if not values:
        return None
    ordered = sorted(values)
    count = len(ordered)
    mid = count // 2
    if count % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _change(current, prior):
    if prior in (None, 0):
        return None
    return float(money((money(current) - money(prior)) / money(prior) * 100))


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = parse_date(value)
    if isinstance(parsed, datetime):
        return parsed.date()
    return parsed if isinstance(parsed, date) else None


def _shift_year(day, years):
    try:
        return date(day.year + years, day.month, day.day)
    except ValueError:
        return date(day.year + years, day.month, day.day - 1)
