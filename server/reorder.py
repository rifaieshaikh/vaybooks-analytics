"""Reorder quantities from the Item 360 buy quantity. Does not create a purchase order."""

from __future__ import annotations

import json

from vay.phase3 import apply_budget, round_pack

from server.org_policy import SETTING_TYPE

PROPOSAL_UK = "reorder_proposal"
ORDER_RULE = "Earliest buy-by, then larger quantity, then name."


def _load(store):
    from server.org_policy import _fields
    raw = _fields(store, PROPOSAL_UK).get("Proposal")
    if not raw:
        return {"budget": None, "lines": []}
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"budget": None, "lines": []}
    if not isinstance(data, dict):
        return {"budget": None, "lines": []}
    return data


def _num(value):
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def save_proposal(store, body):
    budget = body.get("budget")
    if budget in ("", None):
        budget = None
    else:
        budget = round(float(budget), 2)
    saved_lines = []
    for line in body.get("lines") or []:
        name = str(line.get("name") or "").strip()
        if not name:
            continue
        manual = bool(line.get("manual"))
        basis = _num(line.get("basis_qty")) if manual else None
        saved_lines.append({
            "name": name,
            "qty": line.get("qty") if manual else None,
            "manual": manual,
            "basis_qty": basis,
            "pack_size": line.get("pack_size") or 0,
            "minimum": line.get("minimum") or 0,
            "lead_days": int(line.get("lead_days") or 0),
            "supplier": str(line.get("supplier") or "").strip(),
        })
    payload = {"budget": budget, "lines": saved_lines}
    store.upsert_row({
        "type": SETTING_TYPE,
        "uk": PROPOSAL_UK,
        "source_upload_id": "",
        "fields": {"Proposal": json.dumps(payload)},
    })
    return payload


def _is_manual(edit):
    if not edit:
        return False
    if "manual" in edit:
        return bool(edit.get("manual"))
    return edit.get("qty") not in ("", None) and "basis_qty" not in edit


def _pack_note(base, rounded, pack_size, minimum):
    added = round(float(rounded or 0) - float(base or 0), 2)
    if added <= 0.009:
        return 0.0, ""
    minimum_n = _num(minimum) or 0
    pack_n = _num(pack_size) or 0
    if minimum_n > float(base or 0) + 0.009 and pack_n > 0:
        reason = "Raised to the order minimum, then rounded to the pack."
    elif minimum_n > float(base or 0) + 0.009:
        reason = "Raised to the order minimum."
    else:
        reason = "Rounded up to the pack size."
    return added, reason


def _line_from_plan(plan, edit, manual):
    base = round(float(plan.get("buy_qty") or 0), 2)
    pack = edit.get("pack_size") or 0
    minimum = edit.get("minimum") or 0
    rounded = round_pack(base, pack, minimum)
    added, pack_reason = _pack_note(base, rounded, pack, minimum)
    basis = _num(edit.get("basis_qty")) if edit else None
    needs_review = False
    if manual:
        qty = round_pack(edit.get("qty"), pack, minimum)
        if basis is None or abs(basis - base) > 0.009:
            needs_review = True
    else:
        qty = rounded
    lead = edit.get("lead_days") if edit and "lead_days" in edit else plan.get("lead_days")
    supplier = (edit.get("supplier") if edit and edit.get("supplier") else "") or plan.get("supplier") or ""
    cost = plan.get("unit_cost")
    return {
        "name": plan.get("name") or "",
        "on_hand": plan.get("on_hand"),
        "reserved": plan.get("reserved"),
        "incoming_on_time": plan.get("incoming_on_time"),
        "incoming_late": plan.get("incoming_late"),
        "position": plan.get("position"),
        "supply_label": plan.get("supply_label") or "",
        "demand_label": plan.get("demand_label") or "",
        "demand_target": plan.get("demand_target"),
        "past_check": plan.get("past_check"),
        "suggested_qty": base,
        "qty": qty,
        "manual": manual,
        "needs_review": needs_review,
        "review_reason": "The calculated buy quantity changed." if needs_review else "",
        "pack_size": pack or 0,
        "minimum": minimum or 0,
        "pack_added": added,
        "pack_reason": pack_reason,
        "pace": plan.get("pace") or 0,
        "pace_days": plan.get("pace_days") or 0,
        "fill_to": plan.get("fill_to") or 0,
        "min_hold": plan.get("min_hold") or 0,
        "buy_by": plan.get("buy_by") or "",
        "buy_by_label": plan.get("buy_by_label") or "",
        "lead_days": int(lead or 0),
        "supplier": supplier,
        "reason": plan.get("reason") or "",
        "unit_cost": cost,
        "cost_label": plan.get("cost_label") or ("Uncosted" if cost in ("", None) else "Snapshot cost"),
        "discontinued": bool(plan.get("discontinued")),
        "uses_position": plan.get("position") not in ("", None),
        "quantity_reason": plan.get("reason") or "",
    }


def _auto_key(line):
    when = line.get("buy_by") or "9999-99-99"
    return (when, -float(line.get("suggested_qty") or 0), (line.get("name") or "").lower())


def _demand_label(plans):
    windows = []
    for plan in plans or []:
        try:
            days = int(plan.get("pace_days") or 0)
        except (TypeError, ValueError):
            days = 0
        if days > 0:
            windows.append(days)
    if not windows:
        return "No recent demand"
    return "Demand window up to %s days" % max(windows)


def item_pack_rules(store):
    """Pack size and order minimum stored on the stock item, when present."""
    rules = {}
    for doc in store.rows_of_type("stock") or []:
        fields = doc.get("fields") or {}
        name = str(fields.get("Item Name") or "").strip().lower()
        if not name:
            continue
        pack = _num(fields.get("Pack Size") if fields.get("Pack Size") not in ("", None) else fields.get("Pack"))
        minimum = _num(fields.get("Order Minimum") if fields.get("Order Minimum") not in ("", None) else fields.get("Minimum"))
        rules[name] = {"pack_size": pack or 0, "minimum": minimum or 0}
    return rules


def build_reorder(plans, proposal, packs=None):
    """Draft a reorder from Item 360 buy quantities.

    An unedited quantity is that buy_qty, then pack and minimum when it is positive.
    A typed quantity is kept and marked for review when the base later changes.
    """
    proposal = proposal or {}
    edits = {}
    saved_order = []
    for line in proposal.get("lines") or []:
        key = str(line.get("name") or "").strip().lower()
        if not key:
            continue
        edits[key] = line
        saved_order.append(key)
    saved_index = {name: index for index, name in enumerate(saved_order)}
    seen = set()
    candidates = []
    held = []
    for plan in plans or []:
        name = str(plan.get("name") or "").strip()
        key = name.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        edit = dict(edits.get(key) or {})
        rule = (packs or {}).get(key) or {}
        if not edit.get("pack_size") and rule.get("pack_size"):
            edit["pack_size"] = rule["pack_size"]
        if not edit.get("minimum") and rule.get("minimum"):
            edit["minimum"] = rule["minimum"]
        manual = _is_manual(edit)
        base = float(plan.get("buy_qty") or 0)
        discontinued = bool(plan.get("discontinued"))
        if discontinued or base <= 0.009:
            if manual:
                row = _line_from_plan(plan, edit, True)
                row["included"] = False
                row["defer_reason"] = plan.get("reason") or "No purchase needed."
                held.append(row)
            continue
        candidates.append(_line_from_plan(plan, edit, manual))
    for key, edit in edits.items():
        if key in seen or not _is_manual(edit):
            continue
        held.append({
            "name": edit.get("name") or key,
            "suggested_qty": 0,
            "qty": round_pack(edit.get("qty"), edit.get("pack_size"), edit.get("minimum")),
            "manual": True,
            "needs_review": True,
            "review_reason": "This item is not in the current stock recommendation.",
            "included": False,
            "defer_reason": "This item is not in the current stock recommendation.",
            "pack_size": edit.get("pack_size") or 0,
            "minimum": edit.get("minimum") or 0,
            "lead_days": int(edit.get("lead_days") or 0),
            "supplier": edit.get("supplier") or "",
            "unit_cost": None,
            "cost_label": "Uncosted",
            "reason": "This item is not in the current stock recommendation.",
        })

    def sort_key(line):
        key = (line.get("name") or "").lower()
        when, qty, name = _auto_key(line)
        if key in saved_index:
            return (0, saved_index[key], when, qty, name)
        return (1, 0, when, qty, name)

    candidates.sort(key=sort_key)
    budget_input = []
    zeroed = []
    for line in candidates:
        if float(line.get("qty") or 0) <= 0.009:
            zeroed.append(dict(line, included=False, defer_reason="Quantity set to zero"))
            continue
        budget_input.append(line)
    kept, spent, deferred = apply_budget(budget_input, proposal.get("budget"))
    deferred_by = {(row.get("name") or "").lower(): row for row in deferred}
    kept_by = {(row.get("name") or "").lower(): row for row in kept}
    zero_by = {(row.get("name") or "").lower(): row for row in zeroed}
    order = []
    for line in candidates:
        key = (line.get("name") or "").lower()
        if key in kept_by:
            row = dict(kept_by[key])
            row["included"] = True
            row["defer_reason"] = ""
            order.append(row)
        elif key in deferred_by:
            row = dict(line)
            row.update({k: deferred_by[key][k] for k in ("defer_reason", "line_cost", "uncosted", "cost_label") if k in deferred_by[key]})
            row["included"] = False
            order.append(row)
        else:
            order.append(zero_by.get(key) or dict(line, included=False, defer_reason="Quantity set to zero"))
    stopped = any(row.get("defer_reason") == "Would pass the budget" for row in deferred)
    return {
        "budget": proposal.get("budget"),
        "spent": spent,
        "lines": [row for row in order if row.get("included")],
        "deferred": [row for row in order if not row.get("included")],
        "held": held,
        "order": order,
        "stopped": stopped,
        "order_rule": ORDER_RULE,
        "demand_label": _demand_label(plans),
    }
