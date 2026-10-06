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
    """Round a buy quantity up to the pack size, after applying the minimum."""
    amount = max(_num(qty), _num(minimum))
    pack = _num(pack_size)
    if pack <= 0:
        return round(amount, 2)
    units = math.ceil(amount / pack)
    return round(units * pack, 2)


def apply_budget(lines, budget):
    """Keep lines in order until the next one would pass the budget.

    A missing budget keeps every line. The first line that does not fit is
    excluded, and nothing after it is kept.
    """
    rows = list(lines or [])
    if budget in ("", None):
        return rows, None
    limit = _num(budget)
    kept = []
    spent = 0.0
    for line in rows:
        cost = round(_num(line.get("qty")) * _num(line.get("unit_cost")), 2)
        if spent + cost > limit + 1e-9:
            break
        kept.append(dict(line, line_cost=cost))
        spent = round(spent + cost, 2)
    return kept, spent


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
        if when and assigned and when > assigned and _num(row.get("amount")) > 0:
            return {"bought_again": True, "label": "Bought again"}
    return {"bought_again": False, "label": "No sale since assigned"}


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
