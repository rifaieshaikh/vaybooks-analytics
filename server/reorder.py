"""Reorder quantities from short-cover items. Does not create a purchase order."""

from __future__ import annotations

import json

from vay.phase3 import apply_budget, round_pack

from server.org_policy import SETTING_TYPE

PROPOSAL_UK = "reorder_proposal"


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
        saved_lines.append({
            "name": name,
            "qty": line.get("qty"),
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


def build_reorder(stock_rows, costs, proposal, cover_limit=30):
    """Short-cover lines, rounded to pack size, stopped by the budget.

    unit_cost is the current stock purchase price and is a snapshot cost.
    """
    proposal = proposal or {}
    edits = {str(line.get("name") or "").strip().lower(): line for line in proposal.get("lines") or []}
    draft = []
    for row in stock_rows or []:
        days = row.get("cover_days")
        if days is None or float(days) > float(cover_limit):
            continue
        name = row.get("name") or ""
        edit = edits.get(name.lower()) or {}
        qty = round_pack(edit.get("qty") if edit.get("qty") not in ("", None) else row.get("on_hand"), edit.get("pack_size"), edit.get("minimum"))
        cost = costs.get(name)
        draft.append({
            "name": name,
            "on_hand": row.get("on_hand"),
            "cover_days": days,
            "qty": qty,
            "pack_size": edit.get("pack_size") or 0,
            "minimum": edit.get("minimum") or 0,
            "lead_days": int(edit.get("lead_days") or 0),
            "supplier": edit.get("supplier") or "",
            "unit_cost": cost,
            "cost_label": "Snapshot cost",
        })
    kept, spent = apply_budget(draft, proposal.get("budget"))
    return {
        "budget": proposal.get("budget"),
        "spent": spent,
        "lines": kept,
        "stopped": len(kept) < len(draft),
    }
