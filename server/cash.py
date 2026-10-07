"""Weekly cash from opening cash, open promises, payables, and committed reorders.

A missing opening balance stays blank. A pending promise is listed and left out
of the sum. An allocated receipt is already inside the promise remainder.
"""

from __future__ import annotations

from datetime import timedelta

from server.collection import _bundle
from server.items360 import purchase_plans
from server.reorder import _load, build_reorder
from vay.dates import clean_text, number_, parse_date, today_ist


OPENING_MISSING = "Opening cash is not in the file."


def _day(value):
    parsed = parse_date(value)
    if not parsed:
        return ""
    return parsed.strftime("%Y-%m-%d")


def _week_start(day):
    parsed = parse_date(day)
    if not parsed:
        return ""
    start = parsed - timedelta(days=parsed.weekday())
    return start.strftime("%Y-%m-%d")


def _openings(store):
    rows = []
    for doc in store.rows_of_type("opening_cash") or []:
        fields = doc.get("fields") or {}
        day = _day(fields.get("Date"))
        amount = number_(fields.get("Amount"))
        if day and amount is not None:
            rows.append((day, round(float(amount), 2)))
    rows.sort()
    return rows


def _payables(store):
    rows = []
    for doc in store.rows_of_type("payable") or []:
        fields = doc.get("fields") or {}
        day = _day(fields.get("Due Date"))
        amount = number_(fields.get("Amount"))
        if not day or amount is None:
            continue
        rows.append({
            "name": clean_text(fields.get("Account Name")),
            "amount": round(float(amount), 2),
            "due_date": day,
            "week": _week_start(day),
        })
    return rows


def _commitments(store):
    built = build_reorder(purchase_plans(store), _load(store))
    dated = []
    uncosted = []
    for line in built.get("lines") or []:
        if not line.get("included", True):
            continue
        name = line.get("name") or ""
        qty = float(line.get("qty") or 0)
        if qty <= 0.009:
            continue
        cost = line.get("unit_cost")
        if cost in ("", None):
            uncosted.append({"name": name, "qty": qty})
            continue
        when = _day(line.get("buy_by"))
        if not when:
            uncosted.append({"name": name, "qty": qty, "label": "No commitment date"})
            continue
        dated.append({
            "name": name,
            "amount": round(qty * float(cost), 2),
            "week": _week_start(when),
        })
    return dated, uncosted


def _opening_on(openings, week):
    parsed = parse_date(week)
    if not parsed:
        return None
    end = (parsed + timedelta(days=6)).strftime("%Y-%m-%d")
    latest = None
    for day, amount in openings:
        if day <= end:
            latest = amount
    return latest


def build_cash(store, as_of=None):
    as_of = as_of or today_ist()
    openings = _openings(store)
    _today, _contacts, promises, _disputes = _bundle(store, as_of.strftime("%Y-%m-%d"))
    payables = _payables(store)
    commitments, uncosted = _commitments(store)
    inflow = {}
    pending = []
    weeks = set()
    for day, _amount in openings:
        weeks.add(_week_start(day))
    for row in payables:
        weeks.add(row["week"])
    for row in commitments:
        weeks.add(row["week"])
    for row in promises or []:
        status = row.get("payment_status") or ""
        promised = _day(row.get("promised_on"))
        remaining = round(float(row.get("remaining") or 0), 2)
        if status == "pending_refresh":
            pending.append({
                "customer_name": row.get("customer_name") or "",
                "amount": remaining,
                "promised_on": promised,
                "label": row.get("message") or "Payment confirmation is pending a refresh.",
            })
            continue
        if status not in ("open", "partial") or not promised or remaining <= 0.009:
            continue
        week = _week_start(promised)
        weeks.add(week)
        inflow[week] = round(inflow.get(week, 0.0) + remaining, 2)
    payable_sum = {}
    for row in payables:
        payable_sum[row["week"]] = round(payable_sum.get(row["week"], 0.0) + row["amount"], 2)
    commit_sum = {}
    for row in commitments:
        commit_sum[row["week"]] = round(commit_sum.get(row["week"], 0.0) + row["amount"], 2)
    listed = []
    for week in sorted(week for week in weeks if week):
        opening = _opening_on(openings, week) if openings else None
        promises_in = inflow.get(week, 0.0)
        due = payable_sum.get(week, 0.0)
        committed = commit_sum.get(week, 0.0)
        net = None
        if opening is not None:
            net = round(opening + promises_in - due - committed, 2)
        listed.append({
            "week": week,
            "opening": opening,
            "promises": promises_in,
            "payables": due,
            "committed": committed,
            "net": net,
        })
    first = openings[0] if openings else None
    return {
        "as_of": as_of.strftime("%Y-%m-%d"),
        "opening": first[1] if first else None,
        "opening_date": first[0] if first else "",
        "opening_label": "" if first else OPENING_MISSING,
        "pending": pending,
        "uncosted": uncosted,
        "weeks": listed,
    }
