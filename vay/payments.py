"""Cash payment summary for one customer.

Receipts are observed cash. Credit notes stay in a separate total. A missing
date stays out of gap and period figures. A prior window that the books do not
cover is unavailable, not a zero.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from vay.dates import fiscal_year_start, fy_label, normalize_fy_start_month, parse_date
from vay.ledger import money, promise_data_state

CONFIRMED = {"source_confirmed", "manually_confirmed"}


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


def payment_behavior(
    timing,
    open_debits,
    unused_credits,
    posted,
    *,
    reconciliation=None,
    as_of,
    start_month=None,
    coverage=None,
    promises=None,
):
    """Timing, coverage, and debt movement for one customer through the cutoff.

    Unknown-age amounts stay out of the averages. Inferred timing is not folded
    into confirmed timing. An open invoice stays in outstanding and is not
    treated as settled. A window the books do not cover is unavailable.
    """
    as_of_day = _as_date(as_of)
    lines = [_line(row) for row in timing or []]
    opens = [_open_row(row) for row in open_debits or []]
    unused = list(unused_credits or [])
    posted_rows = list(posted or [])
    reconciliation = reconciliation or {}
    confirmed = [row for row in lines if row["evidence"] in CONFIRMED and not row["unknown_age"]]
    inferred = [row for row in lines if row["evidence"] == "inferred" and not row["unknown_age"]]
    unknown_lines = [row for row in lines if row["unknown_age"]]
    unknown_open = [row for row in opens if row["unknown_age"]]
    unknown_amount = _money_sum([row["amount"] for row in unknown_lines] + [row["remaining"] for row in unknown_open])
    partial_confirmed = [row for row in confirmed if not row["closed"]]
    partial_inferred = [row for row in inferred if not row["closed"]]
    full_confirmed = _closers([row for row in confirmed if row["closed"]])
    full_inferred = _closers([row for row in inferred if row["closed"]])
    open_known = [row for row in opens if not row["unknown_age"]]
    current, prior, trend_available, trend_reason = _windows(as_of_day, start_month, coverage)
    return {
        "as_of": as_of_day.isoformat() if as_of_day else None,
        "reconciliation": reconciliation.get("state") or "",
        "note": "Confirmed timing uses source-confirmed and manually confirmed links. Inferred timing is separate and is not confirmed payment behavior. Unknown-age amounts are excluded from the averages.",
        "confirmed": _age_metric(confirmed, unknown_amount, "No confirmed link has a known invoice date."),
        "inferred": _age_metric(inferred, unknown_amount, "No inferred link has a known invoice date."),
        "partial": {
            "confirmed": _day_metric(partial_confirmed, "invoice_age_days", "amount", unknown_amount, "No confirmed payment left a balance."),
            "inferred": _day_metric(partial_inferred, "invoice_age_days", "amount", unknown_amount, "No inferred payment left a balance."),
        },
        "full_settlement": {
            "confirmed": _day_metric(full_confirmed, "invoice_age_days", "invoice_amount", _money_sum(row["remaining"] for row in open_known), "No confirmed link has cleared an invoice."),
            "inferred": _day_metric(full_inferred, "invoice_age_days", "invoice_amount", _money_sum(row["remaining"] for row in open_known), "No inferred link has cleared an invoice."),
            "excluded_open": _money_sum(row["remaining"] for row in open_known),
        },
        "open_invoices": {
            "count": len(opens),
            "amount": _money_sum(row["remaining"] for row in opens),
            "overdue_amount": _money_sum(row["remaining"] for row in opens if row["days_overdue"] not in (None, "") and row["days_overdue"] > 0),
            "unknown_age_amount": _money_sum(row["remaining"] for row in unknown_open),
            "transactions": opens,
            "note": "Still-open invoices stay in outstanding. They are not averaged into time to full settlement.",
        },
        "coverage": _coverage(confirmed, inferred, unused, unknown_amount),
        "movement": _movement(posted_rows, lines, unused, reconciliation, as_of_day, current, prior, trend_available, trend_reason),
        "age_comparison": _age_comparison(confirmed, current, prior, trend_available, trend_reason),
        "promises": _promise_summary(promises, coverage),
    }


def _line(row):
    return {
        "credit_id": str(row.get("credit_id") or ""),
        "debit_id": str(row.get("debit_id") or ""),
        "invoice_number": str(row.get("invoice_number") or ""),
        "amount": money(row.get("amount") or 0),
        "invoice_amount": money(row.get("invoice_amount") or 0),
        "evidence": str(row.get("evidence") or ""),
        "cash": bool(row.get("cash")),
        "date": _as_date(row.get("effective_date")),
        "unknown_age": bool(row.get("unknown_age")),
        "closed": bool(row.get("closed")),
        "opening": bool(row.get("opening")),
        "invoice_age_days": _int_or_none(row.get("invoice_age_days")),
        "days_overdue": _int_or_none(row.get("days_overdue")),
    }


def _open_row(row):
    overdue = _int_or_none(row.get("days_overdue"))
    return {
        "source_id": str(row.get("source_id") or ""),
        "invoice": str(row.get("invoice_number") or "") or "Sale",
        "date": _iso(row.get("invoice_date") or row.get("effective_date")),
        "remaining": float(money(row.get("remaining") or 0)),
        "days_overdue": overdue,
        "unknown_age": bool(row.get("unknown_age")),
        "opening": bool(row.get("opening")),
    }


def _closers(lines):
    """One row per invoice: the allocation that brought the balance to zero."""
    chosen = {}
    for row in lines:
        chosen[row["debit_id"]] = row
    return list(chosen.values())


def _age_metric(lines, unknown_amount, empty_reason):
    age = _day_metric(lines, "invoice_age_days", "amount", unknown_amount, empty_reason)
    overdue_lines = [row for row in lines if row["days_overdue"] is not None]
    unknown_due = _money_sum(row["amount"] for row in lines if row["days_overdue"] is None)
    overdue = _day_metric(overdue_lines, "days_overdue", "amount", unknown_due, "No link has a known due date.")
    return {
        "invoice_age": age,
        "days_overdue": overdue,
        "transactions": [_timing_tx(row) for row in lines],
    }


def _day_metric(lines, day_key, amount_key, excluded, empty_reason):
    pairs = []
    transactions = []
    for row in lines:
        days = row.get(day_key)
        amount = row.get(amount_key)
        if days is None or amount is None:
            continue
        pairs.append((days, amount))
        transactions.append(_timing_tx(row, days=days, amount=amount))
    value = _weighted_days(pairs)
    denominator = _money_sum(amount for _days, amount in pairs)
    return {
        "available": value is not None,
        "value": value,
        "denominator": denominator,
        "excluded": float(money(excluded or 0)),
        "reason": "" if value is not None else empty_reason,
        "transactions": transactions,
    }


def _timing_tx(row, days=None, amount=None):
    return {
        "source_id": row.get("credit_id") or row.get("source_id") or "",
        "invoice": row.get("invoice_number") or row.get("invoice") or row.get("debit_id") or "",
        "debit_id": row.get("debit_id") or "",
        "date": _iso(row.get("date")),
        "amount": float(amount if amount is not None else row.get("amount") or 0),
        "days": row.get("invoice_age_days") if days is None else days,
        "evidence": row.get("evidence") or "",
        "cash": bool(row.get("cash")),
    }


def _coverage(confirmed, inferred, unused, unknown_amount):
    confirmed_amount = _money_sum(row["amount"] for row in confirmed)
    inferred_amount = _money_sum(row["amount"] for row in inferred)
    unresolved = _money_sum(
        money(row.get("remaining") or 0)
        for row in unused
        if row.get("unresolved")
    )
    unknown = float(money(unknown_amount or 0))
    denominator = _money_sum([confirmed_amount, inferred_amount, unresolved, unknown])
    return {
        "confirmed": confirmed_amount,
        "inferred": inferred_amount,
        "unresolved": unresolved,
        "unknown_age": unknown,
        "denominator": denominator,
        "confirmed_share": _share(confirmed_amount, denominator),
        "inferred_share": _share(inferred_amount, denominator),
        "unresolved_share": _share(unresolved, denominator),
        "unknown_age_share": _share(unknown, denominator),
        "note": "Unknown-age opening amounts are excluded from exact timing and shown here by value.",
    }


def _movement(posted, lines, unused, reconciliation, as_of_day, current, prior, trend_available, trend_reason):
    growth_rows = []
    reversal_rows = []
    for row in posted:
        standing = money(money(row.get("amount") or 0) - money(row.get("reversed") or 0))
        reversed_amount = money(row.get("reversed") or 0)
        if reversed_amount and reversed_amount > 0:
            reversal_rows.append(_flow_tx(row, reversed_amount))
        if row.get("void") or row.get("opening") or row.get("side") != "debit":
            continue
        if standing is None or standing <= 0:
            continue
        growth_rows.append(_flow_tx(row, standing))
    cash_rows = [_timing_tx(row) for row in lines if row["cash"]]
    note_rows = [_timing_tx(row) for row in lines if not row["cash"]]
    advance_rows = []
    for row in unused:
        if not row.get("cash"):
            continue
        remaining = money(row.get("remaining") or 0)
        if remaining is None or remaining <= 0:
            continue
        advance_rows.append({
            "source_id": str(row.get("source_id") or ""),
            "invoice": "",
            "date": _iso(row.get("effective_date")),
            "amount": float(remaining),
            "days": None,
            "evidence": "unapplied",
            "cash": True,
        })
    growth = _flow_metric(growth_rows, "No invoice was posted through this cutoff.")
    cash_reduction = _flow_metric(cash_rows, "No cash was applied through this cutoff.")
    non_cash = _flow_metric(note_rows, "No credit note was applied through this cutoff.")
    advance = _flow_metric(advance_rows, "No unused cash is open at this cutoff.")
    reversals = _flow_metric(reversal_rows, "No reversal is in this cutoff.")
    return {
        "cutoff": as_of_day.isoformat() if as_of_day else None,
        "reconciliation": reconciliation.get("state") or "",
        "growth": growth,
        "cash_reduction": cash_reduction,
        "non_cash_reduction": non_cash,
        "advance": advance,
        "reversals": reversals,
        "trend": {
            "available": trend_available,
            "reason": trend_reason,
            "current": _movement_window(current, growth_rows, cash_rows, note_rows),
            "prior": _movement_window(prior, growth_rows, cash_rows, note_rows) if trend_available else _empty_window(prior),
        },
        "note": "Cash applied to invoices is separate from credit notes. The advance is unused cash at this cutoff and is not compared with an earlier cutoff.",
    }


def _age_comparison(confirmed, current, prior, available, reason):
    def window_metric(window):
        if not window:
            return None
        rows = [row for row in confirmed if row["date"] and window["start"] <= row["date"] <= window["end"]]
        metric = _day_metric(rows, "invoice_age_days", "amount", 0, "No confirmed link falls in this window.")
        metric["label"] = window["label"]
        return metric
    return {
        "available": available,
        "reason": reason,
        "current": window_metric(current),
        "prior": window_metric(prior) if available else None,
    }


def _promise_summary(promises, coverage):
    if promises is None:
        return {
            "available": False,
            "reason": "Promise results are not on this view.",
            "count": 0,
            "amount": 0.0,
            "kept": 0.0,
            "partial": 0.0,
            "missed": 0.0,
            "awaiting_data": 0.0,
            "open": 0.0,
            "transactions": [],
            "note": "A credit note does not count as a kept cash promise.",
        }
    coverage = coverage or {}
    rows = []
    totals = {"kept": money(0), "partial": money(0), "missed": money(0), "awaiting_data": money(0), "open": money(0)}
    for raw in promises:
        status = str(raw.get("payment_status") or "open")
        if promise_data_state(coverage.get("complete_through"), raw.get("promised_on")) == "awaiting_data" and status in ("missed", "open", "partial"):
            status = "awaiting_data"
        if status not in totals:
            status = "open"
        amount = money(raw.get("amount") or 0)
        remaining = money(raw.get("remaining") if raw.get("remaining") is not None else amount)
        totals[status] = money(totals[status] + amount)
        rows.append({
            "source_id": str(raw.get("id") or ""),
            "date": _iso(raw.get("promised_on")),
            "amount": float(amount),
            "remaining": float(remaining or 0),
            "status": status,
        })
    return {
        "available": True,
        "reason": "" if rows else "No promise is recorded for this customer.",
        "count": len(rows),
        "amount": _money_sum(row["amount"] for row in rows),
        "kept": float(totals["kept"]),
        "partial": float(totals["partial"]),
        "missed": float(totals["missed"]),
        "awaiting_data": float(totals["awaiting_data"]),
        "open": float(totals["open"]),
        "transactions": rows,
        "note": "Promise results use the coverage cutoff. A credit note does not count as a kept cash promise.",
    }


def _movement_window(window, growth_rows, cash_rows, note_rows):
    if not window:
        return None
    def inside(rows):
        kept = []
        for row in rows:
            day = _as_date(row.get("date"))
            if day and window["start"] <= day <= window["end"]:
                kept.append(row)
        return kept
    growth = inside(growth_rows)
    cash = inside(cash_rows)
    notes = inside(note_rows)
    return {
        "label": window["label"],
        "start": window["start"].isoformat(),
        "end": window["end"].isoformat(),
        "growth": _money_sum(row["amount"] for row in growth),
        "cash_reduction": _money_sum(row["amount"] for row in cash),
        "non_cash_reduction": _money_sum(row["amount"] for row in notes),
        "transactions": [row["source_id"] for row in growth + cash + notes],
    }


def _empty_window(window):
    if not window:
        return None
    return {
        "label": window["label"],
        "start": window["start"].isoformat(),
        "end": window["end"].isoformat(),
        "growth": 0.0,
        "cash_reduction": 0.0,
        "non_cash_reduction": 0.0,
        "transactions": [],
    }


def _flow_tx(row, amount):
    return {
        "source_id": str(row.get("source_id") or ""),
        "invoice": str(row.get("kind") or ""),
        "debit_id": "",
        "date": _iso(row.get("effective_date")),
        "amount": float(amount),
        "days": None,
        "evidence": "",
        "cash": bool(row.get("cash")),
    }


def _flow_metric(rows, empty_reason):
    total = _money_sum(row["amount"] for row in rows)
    return {
        "available": bool(rows),
        "value": total if rows else None,
        "denominator": total if rows else 0.0,
        "excluded": 0.0,
        "reason": "" if rows else empty_reason,
        "transactions": rows,
    }


def _weighted_days(pairs):
    if not pairs:
        return None
    total = money(0)
    acc = Decimal(0)
    for days, amount in pairs:
        total = money(total + amount)
        acc += Decimal(int(days)) * money(amount)
    if total == 0:
        return None
    value = (acc / total).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    if value == value.to_integral():
        return int(value)
    return float(value)


def _money_sum(values):
    total = money(0)
    for value in values:
        total = money(total + money(value or 0))
    return float(total)


def _share(part, whole):
    whole = money(whole or 0)
    if whole == 0:
        return None
    return float(money(money(part or 0) / whole * 100))


def _int_or_none(value):
    if value is None or value == "":
        return None
    return int(value)


def _iso(value):
    day = _as_date(value)
    return day.isoformat() if day else None
