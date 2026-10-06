"""Forecasts, retail-pack helpers, and questions over approved metrics.

A forecast is not an official metric. A question that does not match an approved
report or a governed metric does not invent a number.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from vay.dates import between_, parse_date, normalize_date
from vay.phase2 import period_windows


def _noon(value):
    day = normalize_date(value)
    return datetime(day.year, day.month, day.day, 12)


def _shift_year(day, years):
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


def next_window(report_date):
    """The window after the report date, the same number of days as this period."""
    current = period_windows(report_date)["current"]
    span = (current["end"].date() - current["start"].date()).days
    start = _noon(current["end"] + timedelta(days=1))
    end = _noon(start + timedelta(days=span))
    return {"start": start, "end": end, "label": "Next period"}


def _sum_window(dated_amounts, start, end):
    seen = False
    total = 0.0
    for when, amount in dated_amounts or []:
        when = when if hasattr(when, "year") else parse_date(when)
        if not between_(when, start, end):
            continue
        seen = True
        total += float(amount or 0)
    if not seen:
        return None
    return round(total, 2)


def _method(label, value, empty_reason):
    if value is None:
        return {"label": label, "value": None, "status": "unavailable", "reason": empty_reason}
    return {"label": label, "value": value, "status": "eligible", "reason": ""}


def forecast_sales(dated_amounts, report_date):
    """Two sales figures for the next window. A method with no rows stays unavailable."""
    windows = period_windows(report_date)
    upcoming = next_window(report_date)
    last_start = _noon(_shift_year(upcoming["start"], -1))
    last_end = _noon(_shift_year(upcoming["end"], -1))
    year_ago = _sum_window(dated_amounts, last_start, last_end)
    completed = []
    for key in ("prior", "prior_year"):
        window = windows[key]
        value = _sum_window(dated_amounts, window["start"], window["end"])
        if value is not None:
            completed.append(value)
    trailing = round(sum(completed) / len(completed), 2) if completed else None
    methods = [
        _method("Same days last year", year_ago, "No sales last year"),
        _method("Average of completed periods", trailing, "No completed period"),
    ]
    if methods[0]["value"] is None or methods[1]["value"] is None:
        uncertainty = {"label": "Gap between methods", "value": None, "status": "unavailable", "reason": "Both methods are needed"}
    else:
        uncertainty = {
            "label": "Gap between methods",
            "value": round(abs(methods[0]["value"] - methods[1]["value"]), 2),
            "status": "eligible",
            "reason": "",
        }
    return {
        "window": {
            "start": upcoming["start"].strftime("%Y-%m-%d"),
            "end": upcoming["end"].strftime("%Y-%m-%d"),
            "label": upcoming["label"],
        },
        "methods": methods,
        "uncertainty": uncertainty,
    }


def apply_scenario(forecast, scenario):
    """A named assumption beside the forecast. It is not an official metric."""
    scenario = scenario or {}
    name = str(scenario.get("name") or "Scenario").strip() or "Scenario"
    try:
        factor = float(scenario.get("sales_factor"))
    except (TypeError, ValueError):
        factor = None
    methods = []
    for row in (forecast or {}).get("methods") or []:
        copied = dict(row)
        if factor is None or copied.get("value") is None:
            copied["value"] = None
            copied["status"] = "unavailable"
            copied["reason"] = copied.get("reason") or "Scenario needs a factor and a forecast"
        else:
            copied["value"] = round(float(copied["value"]) * factor, 2)
            copied["reason"] = ""
        methods.append(copied)
    return {
        "official": False,
        "label": "Scenario · not an official metric",
        "name": name,
        "sales_factor": factor,
        "methods": methods,
    }


def consolidate_companies(companies):
    """Sum eligible company figures. A company with no figure keeps the total blank."""
    rows = []
    blank = False
    total = 0.0
    for company in companies or []:
        name = str((company or {}).get("name") or "").strip()
        if not name:
            continue
        value = (company or {}).get("value")
        if value is None:
            blank = True
            rows.append({"name": name, "value": None, "status": "unavailable", "reason": (company or {}).get("reason") or "No eligible figure"})
            continue
        amount = round(float(value), 2)
        total += amount
        rows.append({"name": name, "value": amount, "status": "eligible", "reason": ""})
    rows.sort(key=lambda row: row["name"].lower())
    if not rows or blank:
        return {"rows": rows, "total": None, "status": "unavailable", "reason": "A company has no eligible figure" if blank else "No companies"}
    return {"rows": rows, "total": round(total, 2), "status": "eligible", "reason": ""}


def match_question(text, metrics, reports):
    """Match a question to one approved report or one governed metric. None when it does not."""
    query = " ".join(str(text or "").lower().split())
    if not query:
        return None
    for report in reports or []:
        if str(report.get("name") or "").lower() == query:
            return {"kind": "report", "id": report.get("id") or ""}
    for metric in metrics or []:
        label = str(metric.get("label") or "").lower()
        mid = str(metric.get("id") or "").lower()
        if query == label or query == mid:
            return {"kind": "metric", "id": metric.get("id") or ""}
    report_hits = [row for row in reports or [] if query in str(row.get("name") or "").lower()]
    metric_hits = [
        row for row in metrics or []
        if query in str(row.get("label") or "").lower() or query in str(row.get("id") or "").lower()
    ]
    if len(report_hits) + len(metric_hits) != 1:
        return None
    if report_hits:
        return {"kind": "report", "id": report_hits[0].get("id") or ""}
    return {"kind": "metric", "id": metric_hits[0].get("id") or ""}
