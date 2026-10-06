"""Headline sales/AR reconciliation against sidecar fixtures (no manual entry)."""

from __future__ import annotations

import json
from datetime import datetime

from vay.dates import (
    between_,
    build_report_context,
    number_,
    normalize_date,
    parse_date,
)
from vay.domain import METRIC_IDS
from vay.eligibility import latest_snapshot_date

from server.org_policy import org_policy_for_generate
from server.tables import tables_from_store

SALES_REPORTS = ["Sales by person", "Sales by customer", "Sales by group"]
AR_REPORTS = ["Sales by customer", "Sales by group", "Collection follow-up"]
STOCK_REPORTS = ["Item sales", "Stock cover", "Slow stock"]


def parse_recon_sidecar(raw) -> dict:
    if isinstance(raw, dict):
        data = raw
    else:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
    report_date = str(data.get("report_date") or "").strip()
    if not report_date:
        raise ValueError("recon sidecar requires report_date")
    try:
        tolerance = float(data.get("tolerance", 0.01))
    except (TypeError, ValueError):
        tolerance = 0.01
    out = {
        "report_date": report_date[:10],
        "tolerance": tolerance,
    }
    for key in ("sales_mtd", "sales_ytd", "ar_balance"):
        if key in data and data[key] is not None:
            out[key] = float(data[key])
    return out


def compute_headlines(store, report_date, org_policy=None):
    """Compute sales_mtd, sales_ytd, ar_balance from stored rows."""
    policy = org_policy if org_policy is not None else org_policy_for_generate(store)
    dt = normalize_date(parse_date(report_date) or report_date)
    if not dt:
        raise ValueError("invalid report_date")
    ctx = build_report_context(dt, org_policy=policy)
    fy_start = ctx["fiscalYearStart"]
    month_start = ctx["monthStart"]
    tables = tables_from_store(store, ["sales", "credit_note", "arr"])
    sales_mtd = 0.0
    sales_ytd = 0.0
    sales = tables.get("sales")
    if sales and "Date" in sales.index and "Net Amount" in sales.index:
        di = sales.index["Date"]
        ai = sales.index["Net Amount"]
        for row in sales.rows:
            d = row[di] if isinstance(row[di], datetime) else parse_date(row[di])
            if not d or d > ctx["reportDate"]:
                continue
            amount = number_(row[ai])
            if between_(d, month_start, ctx["reportDate"]):
                sales_mtd += amount
            if between_(d, fy_start, ctx["reportDate"]):
                sales_ytd += amount
    notes = tables.get("credit_note")
    if notes and "Date" in notes.index and "Net Amount" in notes.index:
        di = notes.index["Date"]
        ai = notes.index["Net Amount"]
        for row in notes.rows:
            d = row[di] if isinstance(row[di], datetime) else parse_date(row[di])
            if not d or d > ctx["reportDate"]:
                continue
            amount = number_(row[ai])
            if amount <= 0:
                continue
            if between_(d, month_start, ctx["reportDate"]):
                sales_mtd -= amount
            if between_(d, fy_start, ctx["reportDate"]):
                sales_ytd -= amount
    ar_balance = 0.0
    arr = tables.get("arr")
    if arr and "Balance" in arr.index:
        bi = arr.index["Balance"]
        for row in arr.rows:
            ar_balance += number_(row[bi])
    return {
        "sales_mtd": sales_mtd,
        "sales_ytd": sales_ytd,
        "ar_balance": ar_balance,
        "report_date": ctx["reportDate"].strftime("%Y-%m-%d"),
        "fiscal_year_start": fy_start.strftime("%Y-%m-%d"),
    }


def _close(a, b, tol):
    return abs(float(a) - float(b)) <= float(tol) + 1e-12


def reconcile(store, sidecar: dict | None, report_date=None, org_policy=None):
    if not sidecar:
        result = {
            "status": "unavailable",
            "message": "No reconciliation sidecar attached",
            "computed": None,
            "expected": None,
            "deltas": None,
        }
        result["exceptions"] = exceptions_for_recon(result)
        return result
    expected = parse_recon_sidecar(sidecar)
    rd = report_date or expected.get("report_date")
    computed = compute_headlines(store, rd, org_policy=org_policy)
    tol = expected.get("tolerance", 0.01)
    deltas = {}
    checks = {}
    for key in ("sales_mtd", "sales_ytd", "ar_balance"):
        if key not in expected:
            continue
        deltas[key] = round(computed[key] - expected[key], 6)
        checks[key] = _close(computed[key], expected[key], tol)
    if not checks:
        status = "unavailable"
        message = "Sidecar has no comparable totals"
    elif all(checks.values()):
        status = "pass"
        message = "Headline sales and AR match sidecar"
    else:
        status = "fail"
        failed = [k for k, ok in checks.items() if not ok]
        message = "Mismatch on " + ", ".join(failed)
    result = {
        "status": status,
        "message": message,
        "computed": computed,
        "expected": {k: expected[k] for k in ("sales_mtd", "sales_ytd", "ar_balance", "report_date", "tolerance") if k in expected or k == "report_date"},
        "deltas": deltas,
        "checks": checks,
        "metric_ids": [m for m in METRIC_IDS if m in ("sales_mtd", "sales_ytd", "ar_balance")],
    }
    result["exceptions"] = exceptions_for_recon(result)
    return result


def find_sidecar_for_date(store, report_date: str):
    """Latest recon sidecar whose report_date matches (YYYY-MM-DD)."""
    target = str(report_date or "")[:10]
    best = None
    for doc in store.list_recon_sidecars():
        if str(doc.get("report_date") or "")[:10] != target:
            continue
        if best is None or str(doc.get("created_at") or "") > str(best.get("created_at") or ""):
            best = doc
    if not best:
        return None, None
    blob = store.get_blob(best.get("blob_id"))
    if not blob or not blob.get("data"):
        return best, None
    try:
        payload = parse_recon_sidecar(blob["data"])
    except (ValueError, json.JSONDecodeError):
        return best, None
    return best, payload


def exceptions_for_recon(recon):
    """Severity and affected reports for a reconciliation result."""
    status = (recon or {}).get("status")
    message = (recon or {}).get("message") or ""
    if status == "unavailable":
        return [{
            "severity": "info",
            "metric_id": "",
            "message": message or "No reconciliation sidecar attached",
            "affected_reports": [],
        }]
    out = []
    checks = (recon or {}).get("checks") or {}
    for key, ok in checks.items():
        if ok:
            continue
        if key in ("sales_mtd", "sales_ytd"):
            reports = SALES_REPORTS
        elif key == "ar_balance":
            reports = AR_REPORTS
        else:
            reports = []
        out.append({
            "severity": "error",
            "metric_id": key,
            "message": "Mismatch on %s" % key,
            "affected_reports": list(reports),
        })
    return out


def snapshot_exceptions(warnings):
    """One warning exception per mismatched snapshot type."""
    out = []
    for warning in warnings or []:
        source = warning.get("source_type") or "arr"
        if source == "stock":
            reports = STOCK_REPORTS
            metric_id = "stock_cover_days"
        else:
            reports = AR_REPORTS
            metric_id = "ar_balance"
        out.append({
            "severity": "warning",
            "metric_id": metric_id,
            "message": warning.get("message") or "",
            "affected_reports": list(reports),
        })
    return out


def attach_snapshot_warnings(recon, warnings):
    recon = dict(recon or {})
    exceptions = list(recon.get("exceptions") or [])
    exceptions.extend(snapshot_exceptions(warnings))
    recon["exceptions"] = exceptions
    recon["asof_warnings"] = list(warnings or [])
    return recon


def arr_effective_date_warning(store, report_date: str):
    """One warning per snapshot type when its date differs from the report date.

    Covers ARR and stock. A matching date, or no snapshot date, adds nothing.
    """
    rd = str(report_date or "")[:10]
    warnings = []
    for source_type, label in (("arr", "ARR"), ("stock", "Stock")):
        as_of = latest_snapshot_date(store, source_type)
        if not as_of or not rd or as_of == rd:
            continue
        warnings.append({
            "source_type": source_type,
            "effective_date": as_of,
            "report_date": rd,
            "message": "%s snapshot date %s differs from report date %s" % (label, as_of, rd),
        })
    return warnings
