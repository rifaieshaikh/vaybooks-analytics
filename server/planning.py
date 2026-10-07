"""Inventory position, demand target, and dated purchase cost.

A missing reservation, incoming order, or dated cost stays missing. It is not
treated as zero, and it does not change the holding buy quantity.
"""

from __future__ import annotations

import calendar
from datetime import timedelta

from server.customers import _fmt_day, _iso
from vay.dates import clean_text, number_, parse_date


SUPPLY_MISSING = "Reservations and incoming orders are not in this file."
PAST_MISSING = "Earlier stock is not in the file."
SEASON_LABEL = "Same month last year"
RECENT_LABEL = "Recent pace"


def _text_day(value):
    parsed = value if hasattr(value, "strftime") and not hasattr(value, "hour") else parse_date(value)
    if not parsed:
        return ""
    return parsed.strftime("%Y-%m-%d")


def _yes(value):
    return clean_text(value).lower() in ("1", "true", "yes", "y")


def load_supply(store):
    """Reservation and incoming rows keyed by item. Items with neither are absent."""
    out = {}

    def bucket(name):
        key = clean_text(name).lower()
        if not key:
            return None
        return out.setdefault(key, {"reservations": [], "incoming": []})

    for doc in store.rows_of_type("reservation") or []:
        fields = doc.get("fields") or {}
        slot = bucket(fields.get("Item Name"))
        if slot is None:
            continue
        slot["reservations"].append({
            "qty": number_(fields.get("Qty")) or 0.0,
            "need_by": _text_day(fields.get("Need By")),
        })
    for doc in store.rows_of_type("incoming") or []:
        fields = doc.get("fields") or {}
        slot = bucket(fields.get("Item Name"))
        if slot is None:
            continue
        slot["incoming"].append({
            "qty": number_(fields.get("Qty")) or 0.0,
            "expected": _text_day(fields.get("Expected Date")),
            "confirmed": _yes(fields.get("Confirmed")),
        })
    return out


def supply_for(index, name):
    row = (index or {}).get(clean_text(name).lower())
    if not row:
        return None
    if not row.get("reservations") and not row.get("incoming"):
        return None
    return row


def lines_by_item(store):
    out = {}
    for doc in store.rows_of_type("items") or []:
        fields = doc.get("fields") or {}
        name = clean_text(fields.get("Item Name"))
        if not name:
            continue
        out.setdefault(name.lower(), []).append({
            "date": parse_date(fields.get("Date")),
            "qty": number_(fields.get("Qty")) or 0.0,
            "name": name,
        })
    return out


def _need_day(as_of, on_hand, min_hold, pace, lead_days):
    """Date the units are needed. Later incoming does not cover an earlier shortage."""
    if as_of is None:
        return ""
    if pace > 0 and on_hand > min_hold + 1e-9:
        days = int(round((on_hand - min_hold) / pace))
        return (as_of + timedelta(days=max(0, days))).strftime("%Y-%m-%d")
    if on_hand + 1e-9 < min_hold:
        return as_of.strftime("%Y-%m-%d")
    return (as_of + timedelta(days=max(0, int(lead_days or 0)))).strftime("%Y-%m-%d")


def _split(supply, need):
    reserved = 0.0
    on_time = 0.0
    late = 0.0
    for row in supply.get("reservations") or []:
        day = row.get("need_by") or ""
        if need and day and day <= need:
            reserved += float(row.get("qty") or 0)
    for row in supply.get("incoming") or []:
        if not row.get("confirmed"):
            continue
        day = row.get("expected") or ""
        if not need or not day:
            continue
        if day <= need:
            on_time += float(row.get("qty") or 0)
        else:
            late += float(row.get("qty") or 0)
    return round(reserved, 2), round(on_time, 2), round(late, 2)


def seasonal_pace(lines, as_of):
    """Daily pace for the same calendar month last year, when those sales exist."""
    if as_of is None:
        return None
    year = as_of.year - 1
    month = as_of.month
    qty = 0.0
    seen = False
    for line in lines or []:
        day = line.get("date")
        if not day or not hasattr(day, "year"):
            continue
        if day.year == year and day.month == month and day <= as_of:
            seen = True
            qty += float(line.get("qty") or 0)
    if not seen:
        return None
    days = calendar.monthrange(year, month)[1]
    return round(qty / days, 4)


def _recent_pace(lines, as_of):
    if as_of is None:
        return 0.0
    start = as_of - timedelta(days=30)
    qty = 0.0
    for line in lines or []:
        day = line.get("date")
        if day and start < day <= as_of:
            qty += float(line.get("qty") or 0)
    return round(qty / 30.0, 4)


def _position(on_hand, supply, need):
    if not supply:
        return on_hand, None, None, None
    reserved, on_time, late = _split(supply, need)
    return round(on_hand - reserved + on_time, 2), reserved, on_time, late


def _set_buy_by(card, as_of, buy, pace, days_until_min, lead_days, on_hand, min_hold):
    if buy <= 0 or as_of is None:
        card["buy_by"] = None
        card["buy_by_label"] = ""
        return
    if pace > 0 and days_until_min is not None:
        buy_in = days_until_min - lead_days
        when = as_of + timedelta(days=max(0, buy_in))
    elif on_hand + 1e-9 < min_hold:
        when = as_of
    else:
        when = as_of
    card["buy_by"] = _iso(when)
    card["buy_by_label"] = _fmt_day(when)


def past_check(lines, holding, as_of, on_hand, stock_day, supply):
    """What the demand rule would have bought at an earlier stock date.

    The result is separate from the current buy quantity.
    """
    review = holding.get("review_days")
    if review is None:
        return None
    past = parse_date(stock_day)
    if as_of is None or not past or past >= as_of:
        return {"as_of": "", "buy_qty": None, "exceeded": None, "label": PAST_MISSING}
    lead = int(holding.get("lead_days") or 0)
    safety = float(holding.get("safety_stock") or 0)
    min_hold = float(holding.get("min_hold") or 0)
    earlier = [line for line in lines or [] if line.get("date") and line["date"] <= past]
    seasonal = seasonal_pace(earlier, past)
    if seasonal is not None:
        demand = seasonal
        label = SEASON_LABEL
    else:
        demand = _recent_pace(earlier, past)
        label = RECENT_LABEL
    need = _need_day(past, on_hand, min_hold, demand, lead)
    position, _reserved, _on_time, _late = _position(on_hand, supply, need)
    target = demand * (lead + int(review)) + safety
    buy = round(max(0.0, target - position), 2)
    if holding.get("discontinued"):
        buy = 0.0
    end = past + timedelta(days=max(lead, 0))
    later = 0.0
    for line in lines or []:
        day = line.get("date")
        if day and past < day <= end:
            later += float(line.get("qty") or 0)
    later = round(later, 2)
    return {
        "as_of": past.strftime("%Y-%m-%d"),
        "buy_qty": buy,
        "on_hand": on_hand,
        "later_qty": later,
        "exceeded": later > on_hand + 1e-9,
        "label": label,
    }


def choose_cost(snapshot, history, as_of):
    """Latest cost dated on or before as_of, otherwise the undated snapshot price."""
    limit = as_of.strftime("%Y-%m-%d") if as_of is not None else ""
    best_day = ""
    best = None
    for row in history or []:
        day = str(row.get("date") or "")[:10]
        cost = row.get("cost")
        if cost is None or not day or not limit or day > limit:
            continue
        if day >= best_day:
            best_day = day
            best = float(cost)
    if best is not None:
        return best, "Historical cost"
    if snapshot is not None:
        return float(snapshot), "Snapshot cost"
    return None, "Uncosted"


def cost_history(store, name):
    history = []
    key = clean_text(name).lower()
    for doc in store.rows_of_type("item_cost") or []:
        fields = doc.get("fields") or {}
        if clean_text(fields.get("Item Name")).lower() != key:
            continue
        cost = number_(fields.get("Cost"))
        day = _text_day(fields.get("Effective Date") or doc.get("effective_date"))
        if cost is None or not day:
            continue
        history.append({"date": day, "cost": cost})
    return history


def apply_plan(card, holding, as_of=None, lines=None, supply=None, stock_day="", cost_date="", store=None):
    """Set position and, when review days are set, the demand target.

    Leaves buy_qty on the holding formula when this item has no supply rows
    and review days are unset.
    """
    on_hand = float(card.get("qty") or 0)
    fill_to = float(card.get("fill_to") or 0)
    min_hold = float(card.get("min_hold") or 0)
    lead = int(holding.get("lead_days") or card.get("lead_days") or 0)
    pace = float(card.get("pace") or 0)
    review = holding.get("review_days")
    need = _need_day(as_of, on_hand, min_hold, pace, lead)
    position, reserved, on_time, late = _position(on_hand, supply, need)
    uses_supply = supply is not None
    if uses_supply:
        card["reserved"] = reserved
        card["incoming_on_time"] = on_time
        card["incoming_late"] = late
        card["position"] = position
        card["supply_label"] = ""
    else:
        card["reserved"] = None
        card["incoming_on_time"] = None
        card["incoming_late"] = None
        card["position"] = None
        card["supply_label"] = SUPPLY_MISSING
        position = on_hand
    demand_label = ""
    target = None
    uses_demand = review is not None
    if uses_demand:
        seasonal = seasonal_pace(lines, as_of)
        if seasonal is not None:
            demand = seasonal
            demand_label = SEASON_LABEL
        else:
            demand = pace
            demand_label = RECENT_LABEL
        safety = float(holding.get("safety_stock") or 0)
        target = round(demand * (lead + int(review)) + safety, 2)
        buy = round(max(0.0, target - position), 2)
    elif uses_supply:
        buy = round(max(0.0, fill_to - position), 2)
    else:
        buy = float(card.get("buy_qty") or 0)
    if holding.get("discontinued"):
        buy = 0.0
    if uses_demand or uses_supply:
        card["buy_qty"] = buy
        _set_buy_by(
            card, as_of, buy, pace, card.get("days_until_min"), lead, on_hand, min_hold,
        )
    card["demand_label"] = demand_label
    card["demand_target"] = target
    card["review_days"] = int(review) if review is not None else None
    card["safety_stock"] = holding.get("safety_stock")
    card["past_check"] = past_check(lines, holding, as_of, on_hand, stock_day, supply) if uses_demand else None
    if store is not None:
        history = cost_history(store, card.get("name"))
        snapshot = card.get("rate")
        extra_day = _text_day(cost_date)
        if extra_day and snapshot is not None:
            history = list(history) + [{"date": extra_day, "cost": float(snapshot)}]
            snapshot = None
        amount, label = choose_cost(snapshot, history, as_of)
        card["plan_unit_cost"] = amount
        card["cost_label"] = label
    return card
