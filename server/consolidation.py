"""Sales by company for the current period. A blank company is left out."""

from __future__ import annotations

from vay.dates import between_, number_, parse_date
from vay.phase2 import period_windows


def company_figures(store, report_date):
    window = period_windows(report_date)["current"]
    slots = {}
    for doc in store.rows_of_type("sales") or []:
        fields = doc.get("fields") or {}
        name = str(fields.get("Company") or fields.get("Entity") or "").strip()
        if not name:
            continue
        slot = slots.setdefault(name, {"name": name, "value": None, "seen": False, "reason": "No eligible figure"})
        when = parse_date(fields.get("Date"))
        if not when or not between_(when, window["start"], window["end"]):
            continue
        slot["seen"] = True
        slot["value"] = round((slot["value"] or 0) + number_(fields.get("Net Amount")), 2)
        slot["reason"] = ""
    return [
        {"name": slot["name"], "value": slot["value"] if slot["seen"] else None, "reason": slot["reason"]}
        for slot in slots.values()
    ]
