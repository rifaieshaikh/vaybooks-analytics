"""Phase 3 pure rules: outcomes, reorder rounding, and one weekly run."""

from __future__ import annotations

import math
from datetime import datetime


def _num(value):
    if value in ("", None):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def round_pack(qty, pack_size, minimum=0):
    """Round a positive buy quantity up to the pack size, after the minimum.

    A zero requirement stays zero. The order minimum does not create a purchase.
    """
    amount = _num(qty)
    if amount <= 0:
        return 0.0
    amount = max(amount, _num(minimum))
    pack = _num(pack_size)
    if pack <= 0:
        return round(amount, 2)
    units = math.ceil(amount / pack)
    return round(units * pack, 2)


def _cost_missing(line):
    return line.get("unit_cost") in ("", None)


def apply_budget(lines, budget):
    """Keep costed lines in order until the next one would pass the budget.

    A missing purchase cost is not treated as zero. With a budget, that line is
    left out and later costed lines can still be kept. After a costed line does
    not fit, every following line is deferred. A missing budget keeps every line
    and labels a missing cost as uncosted.
    """
    rows = list(lines or [])
    if budget in ("", None):
        shown = []
        for line in rows:
            row = dict(line)
            if _cost_missing(line):
                row["uncosted"] = True
                row["line_cost"] = None
                row["cost_label"] = "Uncosted"
            else:
                row["uncosted"] = False
                row["line_cost"] = round(_num(line.get("qty")) * _num(line.get("unit_cost")), 2)
                row["cost_label"] = line.get("cost_label") or "Snapshot cost"
            shown.append(row)
        return shown, None, []
    limit = _num(budget)
    kept = []
    deferred = []
    spent = 0.0
    blocked = False
    for line in rows:
        if blocked:
            deferred.append(dict(line, defer_reason="Would pass the budget"))
            continue
        if _cost_missing(line):
            deferred.append(dict(line, uncosted=True, line_cost=None, defer_reason="Missing purchase cost"))
            continue
        cost = round(_num(line.get("qty")) * _num(line.get("unit_cost")), 2)
        if spent + cost > limit + 1e-9:
            blocked = True
            deferred.append(dict(line, line_cost=cost, defer_reason="Would pass the budget"))
            continue
        kept.append(dict(line, uncosted=False, line_cost=cost, cost_label=line.get("cost_label") or "Snapshot cost"))
        spent = round(spent + cost, 2)
    return kept, spent, deferred


def received_since(receipts, name, assigned_date, cap):
    """Receipts for this customer strictly after the assignment date, capped."""
    key = (name or "").strip().lower()
    total = 0.0
    assigned = str(assigned_date or "")[:10]
    for row in receipts or []:
        if (row.get("name") or "").strip().lower() != key:
            continue
        when = str(row.get("date") or "")[:10]
        if not when or not assigned or when <= assigned:
            continue
        total += _num(row.get("amount"))
    total = round(total, 2)
    if cap not in ("", None):
        total = round(min(total, _num(cap)), 2)
    if total <= 0:
        return {"amount": 0.0, "label": "No receipts since assigned"}
    return {"amount": total, "label": "Received since assigned"}


def recovery_outcome(sales, name, assigned_date):
    key = (name or "").strip().lower()
    assigned = str(assigned_date or "")[:10]
    for row in sales or []:
        if (row.get("name") or "").strip().lower() != key:
            continue
        when = str(row.get("date") or "")[:10]
        amount = _num(row.get("amount"))
        if when and assigned and when > assigned and amount > 0:
            return {
                "bought_again": True,
                "label": "Bought again",
                "amount": amount,
                "evidence_date": when,
                "pending": False,
            }
    return {"bought_again": False, "label": "No sale since assigned", "amount": None, "evidence_date": "", "pending": False}


def purchase_outcome(on_hand, proposed_qty, slow, later_file):
    if not later_file:
        return {"resolved": False, "label": "Waiting for the next stock file"}
    qty = _num(on_hand)
    need = _num(proposed_qty)
    if need and qty + 1e-9 >= need:
        return {"resolved": True, "label": "On hand covers the proposed quantity"}
    if not slow:
        return {"resolved": True, "label": "Item is no longer slow"}
    return {"resolved": False, "label": "Stock risk is still open"}


def data_fix_outcome(message, current_messages, later_report):
    if not later_report:
        return {"cleared": False, "label": "Waiting for a later report"}
    text = (message or "").strip()
    if text and text in set(current_messages or []):
        return {"cleared": False, "label": "Still open"}
    return {"cleared": True, "label": "Cleared"}


def _week(value):
    text = str(value or "")[:10]
    try:
        day = datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return ""
    year, week, _ = day.isocalendar()
    return "%s-%02d" % (year, week)


def due_weekly_date(today, last_auto, enabled):
    """One report date for this week, or none.

    A gap of several weeks still returns only today. Older weeks are not filled in.
    """
    if not enabled:
        return None
    today = str(today or "")[:10]
    if not today:
        return None
    if last_auto and _week(last_auto) == _week(today):
        return None
    return today
