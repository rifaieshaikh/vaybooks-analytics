"""Explain a figure from the run that produced it. The screen does not recompute the value."""

from __future__ import annotations

from vay.dates import build_report_context, clean_text, parse_date
from vay.eligibility import latest_snapshot_date

from server.auth import _redact_recon, metric_visible

SAVED_BEFORE = "This report was saved before number explanations."

_SALES = ("mtd_sales", "d15_sales", "ytd_sales", "total_sales")
_COLLECTION = ("mtd_collection", "d15_collection", "ytd_collection", "total_collection")
_PAIRS = {
    "mtd_gap": ("mtd_sales", "mtd_collection", "MTD sales minus MTD collection."),
    "mtd_rate": ("mtd_sales", "mtd_collection", "MTD collection divided by MTD sales."),
    "d15_gap": ("d15_sales", "d15_collection", "15-day sales minus 15-day collection."),
    "d15_rate": ("d15_sales", "d15_collection", "15-day collection divided by 15-day sales."),
    "ytd_gap": ("ytd_sales", "ytd_collection", "Year-to-date sales minus year-to-date collection."),
    "ytd_rate": ("ytd_sales", "ytd_collection", "Year-to-date collection divided by year-to-date sales."),
    "total_gap": ("total_sales", "total_collection", "Total sales minus total collection."),
    "total_rate": ("total_sales", "total_collection", "Total collection divided by total sales."),
}
_HEADLINES = _SALES + _COLLECTION + ("ar_balance",)
_STOCK = ("stock_cover_days", "slow_stock_value")
_SOURCE_TYPES = {
    "mtd_sales": ("sales", "credit_note"),
    "d15_sales": ("sales", "credit_note"),
    "ytd_sales": ("sales", "credit_note"),
    "total_sales": ("sales", "credit_note"),
    "mtd_collection": ("receipt",),
    "d15_collection": ("receipt",),
    "ytd_collection": ("receipt",),
    "total_collection": ("receipt",),
    "ar_balance": ("arr",),
    "stock_cover_days": ("stock", "items"),
    "slow_stock_value": ("stock",),
}
_FORMULAS = {
    "mtd_sales": "Sales invoices from the month start through the report date, minus credit notes.",
    "d15_sales": "Sales invoices in the 15 days through the report date, minus credit notes.",
    "ytd_sales": "Sales invoices from the financial year start through the report date, minus credit notes.",
    "mtd_collection": "Receipts from the month start through the report date.",
    "d15_collection": "Receipts in the 15 days through the report date.",
    "ytd_collection": "Receipts from the financial year start through the report date.",
    "ar_balance": "Outstanding balance on the receivables snapshot.",
    "stock_cover_days": "Days of cover from on-hand stock and recent item sales.",
    "slow_stock_value": "Slow stock value using the stock snapshot cost. Items with no cost stay uncosted.",
}


def _iso(value):
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    parsed = parse_date(value)
    if parsed:
        return parsed.strftime("%Y-%m-%d")
    text = str(value).strip()
    return text[:10] if len(text) >= 10 and text[4] == "-" else ""


def _see(perms, *names):
    have = set(perms or [])
    return any(name in have for name in names)


def can_see_source(perms, type_name):
    if type_name == "sales":
        return _see(perms, "sales.view", "reports.view.performance")
    if type_name == "credit_note":
        return _see(perms, "credit_note.view", "sales.view", "reports.view.performance")
    if type_name == "receipt":
        return _see(perms, "receipt.view", "reports.view.performance", "reports.view.followup")
    if type_name == "arr":
        return _see(perms, "arr.view") or metric_visible(perms, "ar_balance")
    if type_name == "items":
        return _see(perms, "items.view", "reports.view.items", "stock.view")
    if type_name == "stock":
        return _see(perms, "stock.view", "reports.view.items")
    return False


def filter_sources(sources, perms):
    return [row for row in sources or [] if can_see_source(perms, row.get("type"))]


def _window(metric_id, report_date, total_source):
    report_date = _iso(report_date)
    day = parse_date(report_date) if report_date else None
    window = {"from": "", "to": report_date, "report_date": report_date}
    if not day:
        return window
    ctx = build_report_context(day)
    if metric_id.startswith("mtd_"):
        window["from"] = _iso(ctx["monthStart"])
    elif metric_id.startswith("d15_"):
        window["from"] = _iso(ctx["last15Start"])
    elif metric_id.startswith("ytd_"):
        window["from"] = _iso(ctx["fiscalYearStart"])
    elif metric_id.startswith("total_") and total_source == "fiscal":
        window["from"] = ""
    return window


def _formula(metric_id, total_source):
    if metric_id == "total_sales":
        if total_source == "imported":
            return "Imported sales invoices through the report date, minus credit notes."
        return "Sales invoices across the saved financial years through the report date, minus credit notes."
    if metric_id == "total_collection":
        if total_source == "imported":
            return "Imported receipts through the report date."
        return "Receipts across the saved financial years through the report date."
    return _FORMULAS.get(metric_id) or _PAIRS.get(metric_id, ("", "", ""))[2]


def _max_transaction(store, type_name):
    latest = ""
    for row in store.rows_of_type(type_name) or []:
        day = _iso((row.get("fields") or {}).get("Date"))
        if day > latest:
            latest = day
    return latest


def _count_of(count):
    if isinstance(count, dict):
        total = 0
        for key in ("added", "updated", "upserted"):
            try:
                total += int(count.get(key) or 0)
            except (TypeError, ValueError):
                continue
        return total
    try:
        return int(count or 0)
    except (TypeError, ValueError):
        return 0


def _upload_facts(uploads, type_name):
    records = 0
    uploaded = ""
    effective = ""
    for item in uploads or []:
        counts = item.get("row_counts") or {}
        typed = (item.get("type") or "") == type_name
        if type_name not in counts and not typed and type_name not in (item.get("effective_dates") or {}):
            continue
        records += _count_of(counts.get(type_name) or 0)
        stamp = str(item.get("finished_at") or "")
        if stamp > uploaded:
            uploaded = stamp
        dates = item.get("effective_dates") or {}
        eff = _iso(dates.get(type_name))
        if not eff and typed:
            eff = _iso(item.get("effective_date"))
        if eff > effective:
            effective = eff
    return records, uploaded, effective


def source_entry(store, uploads, type_name):
    coverage = _max_transaction(store, type_name) if type_name not in ("arr", "stock") else ""
    records, uploaded, effective = _upload_facts(uploads, type_name)
    if type_name in ("arr", "stock"):
        effective = latest_snapshot_date(store, type_name) or effective
        if not records:
            records = len(store.rows_of_type(type_name) or [])
    elif not records:
        records = len(store.rows_of_type(type_name) or [])
    if not records and not coverage and not effective and not uploaded:
        return None
    return {
        "type": type_name,
        "records": records,
        "coverage_through": coverage,
        "effective_date": effective,
        "uploaded_at": uploaded,
    }


def _blank(metric_id, label, value, report_date, total_source, basis):
    return {
        "id": metric_id,
        "label": label,
        "value": value,
        "status": "available",
        "reason": "",
        "formula": _formula(metric_id, total_source),
        "window": _window(metric_id, report_date, total_source),
        "sources": [],
        "reconciliation": {"status": "unavailable", "message": ""},
        "basis": basis,
        "mixed_coverage": False,
        "coverage_note": "",
    }


def _apply_eligibility(row, eligibility):
    state = (eligibility or {}).get(row["id"]) or {}
    if state.get("status") == "unavailable":
        row["value"] = None
        row["status"] = "unavailable"
        row["reason"] = state.get("reason") or "Unavailable"


def mixed_coverage(parts):
    """parts: list of (label, date, type). Two or more different dates set the note."""
    present = [(label, day, type_name) for label, day, type_name in parts if day]
    if len(present) < 2 or len({day for _label, day, _type in present}) < 2:
        return False, ""
    return True, "; ".join("%s %s" % (label, day) for label, day, _type in present)


def attach_saved_explanations(dashboard, manifest, store):
    """Freeze explanations onto the dashboard from this run. Later imports do not rewrite them."""
    dashboard = dashboard or {}
    manifest = manifest or {}
    report_date = _iso((dashboard.get("run") or {}).get("report_date") or manifest.get("report_date"))
    total_source = dashboard.get("total_source") or ""
    uploads = ((manifest.get("data_version") or {}).get("uploads") or [])
    eligibility = manifest.get("eligibility") or {}
    recon = manifest.get("reconciliation") or {}
    recon_view = {"status": recon.get("status") or "unavailable", "message": recon.get("message") or ""}
    by_id = {row.get("id"): row for row in dashboard.get("kpis") or []}
    explanations = {}
    for metric_id in _HEADLINES:
        kpi = by_id.get(metric_id)
        if not kpi:
            continue
        row = _blank(metric_id, kpi.get("label") or metric_id, kpi.get("value"), report_date, total_source, "saved")
        row["reconciliation"] = dict(recon_view)
        _apply_eligibility(row, eligibility)
        for type_name in _SOURCE_TYPES.get(metric_id) or ():
            source = source_entry(store, uploads, type_name)
            if source:
                row["sources"].append(source)
        explanations[metric_id] = row
    for metric_id, (left, right, _text) in _PAIRS.items():
        kpi = by_id.get(metric_id)
        if not kpi or left not in explanations or right not in explanations:
            continue
        row = _blank(metric_id, kpi.get("label") or metric_id, kpi.get("value"), report_date, total_source, "saved")
        row["inputs"] = [left, right]
        row["reconciliation"] = dict(recon_view)
        explanations[metric_id] = row
    stock = dashboard.get("stock") or {}
    cover = stock.get("cover") or {}
    slow = stock.get("slow") or {}
    if cover:
        row = _blank("stock_cover_days", "Stock cover", cover.get("value"), report_date, total_source, "saved")
        row["reconciliation"] = {"status": "unavailable", "message": ""}
        _apply_eligibility(row, eligibility)
        row["label_kind"] = "snapshot_cost"
        for type_name in _SOURCE_TYPES["stock_cover_days"]:
            source = source_entry(store, uploads, type_name)
            if source:
                row["sources"].append(source)
        dates = [(src["type"], src.get("effective_date") or src.get("coverage_through") or "") for src in row["sources"]]
        mixed, note = mixed_coverage([(label, day, label) for label, day in dates])
        row["mixed_coverage"] = mixed
        row["coverage_note"] = note
        explanations["stock_cover_days"] = row
    if slow:
        uncosted = int(slow.get("uncosted") or 0)
        value = slow.get("value")
        row = _blank("slow_stock_value", "Slow stock", value, report_date, total_source, "saved")
        row["reconciliation"] = {"status": "unavailable", "message": ""}
        _apply_eligibility(row, eligibility)
        if uncosted and row["value"] in (0, 0.0, None, ""):
            row["value"] = None
            row["status"] = "unavailable"
            row["reason"] = row["reason"] or "Missing purchase cost"
            row["label_kind"] = "cost_unavailable"
        elif uncosted:
            row["label_kind"] = "cost_unavailable"
            row["reason"] = row["reason"] or "%s item%s with no cost excluded" % (uncosted, "" if uncosted == 1 else "s")
        else:
            row["label_kind"] = "snapshot_cost"
        source = source_entry(store, uploads, "stock")
        if source:
            row["sources"].append(source)
        explanations["slow_stock_value"] = row
    dashboard["explanations"] = explanations
    return dashboard


def _visible_metric(perms, metric_id):
    if metric_id in _SALES or metric_id in _COLLECTION or metric_id in _PAIRS:
        return "reports.view.performance" in set(perms or [])
    if metric_id == "ar_balance":
        return metric_visible(perms, "ar_balance")
    if metric_id in _STOCK:
        return metric_visible(perms, metric_id) or _see(perms, "stock.view", "reports.view.items")
    return False


def filter_explanations(explanations, perms):
    out = {}
    for metric_id, row in (explanations or {}).items():
        if not _visible_metric(perms, metric_id):
            continue
        copy = dict(row)
        copy["sources"] = filter_sources(row.get("sources"), perms)
        stored = dict(row.get("reconciliation") or {})
        stored.setdefault("computed", {})
        stored.setdefault("expected", {})
        stored.setdefault("deltas", {})
        stored.setdefault("checks", {})
        redacted = _redact_recon(stored, perms)
        copy["reconciliation"] = {
            "status": redacted.get("status") or "unavailable",
            "message": redacted.get("message") or "",
        }
        out[metric_id] = copy
    return out


def filter_dashboard_explanations(payload, perms):
    if not isinstance(payload, dict):
        return payload
    if "explanations" not in payload:
        payload["explanations_message"] = SAVED_BEFORE
        return payload
    payload["explanations"] = filter_explanations(payload.get("explanations"), perms)
    return payload


def live_sources(store, type_names, perms):
    uploads = []
    for item in store.list_uploads() or []:
        if item.get("dry_run"):
            continue
        uploads.append(item)
    sources = []
    for type_name in type_names:
        source = source_entry(store, uploads, type_name)
        if source and can_see_source(perms, type_name):
            sources.append(source)
    return sources


def _customer_sales_date(store, customer):
    latest = ""
    wanted = clean_text(customer).lower()
    for row in store.rows_of_type("sales") or []:
        fields = row.get("fields") or {}
        name = clean_text(fields.get("Party Name") or fields.get("Account Name")).lower()
        if name != wanted:
            continue
        day = _iso(fields.get("Date"))
        if day > latest:
            latest = day
    return latest


def annotate_today(store, payload, perms):
    rows = (payload or {}).get("rows") or []
    arr_date = latest_snapshot_date(store, "arr")
    stock_date = latest_snapshot_date(store, "stock")
    for row in rows:
        sales_date = _customer_sales_date(store, row.get("customer"))
        use_stock = row.get("kind") == "repurchase" or row.get("block") == "stock"
        parts = [
            ("Receivables", arr_date, "arr"),
            ("Sales", sales_date, "sales"),
            ("Stock", stock_date if use_stock else "", "stock"),
        ]
        visible = [part for part in parts if part[1] and can_see_source(perms, part[2])]
        mixed, note = mixed_coverage(visible)
        types = []
        for _label, _day, type_name in visible:
            if type_name not in types:
                types.append(type_name)
        if sales_date and "sales" in types and "credit_note" not in types:
            types.append("credit_note")
        sources = live_sources(store, types, perms)
        through = ""
        for source in sources:
            day = source.get("coverage_through") or source.get("effective_date") or ""
            if day > through:
                through = day
        row["basis"] = {
            "basis": "live",
            "sources": sources,
            "coverage_through": through,
            "mixed_coverage": mixed,
            "coverage_note": note,
        }
    return payload


def annotate_reorder(built, store, perms):
    built = built or {}
    stock_date = _iso(built.get("stock_date")) or latest_snapshot_date(store, "stock")
    rows = []
    for key in ("order", "lines", "held", "deferred"):
        rows.extend(built.get(key) or [])
    seen = set()
    for line in rows:
        marker = id(line)
        if marker in seen:
            continue
        seen.add(marker)
        items_date = ""
        name = line.get("name") or ""
        for row in store.rows_of_type("items") or []:
            fields = row.get("fields") or {}
            if clean_text(fields.get("Item Name")).lower() != clean_text(name).lower():
                continue
            day = _iso(fields.get("Date"))
            if day > items_date:
                items_date = day
        cost = line.get("unit_cost")
        missing = cost in ("", None)
        if missing:
            kind = "cost_unavailable"
        elif line.get("cost_label") == "Historical cost":
            kind = "historical_cost"
        else:
            kind = "snapshot_cost"
        parts = [("Item sales", items_date, "items"), ("Stock", stock_date, "stock")]
        if store.rows_of_type("sales"):
            parts.append(("Sales", _max_transaction(store, "sales"), "sales"))
        visible = [part for part in parts if part[1] and can_see_source(perms, part[2])]
        item_stock = [part for part in visible if part[2] in ("items", "stock")]
        mixed, note = mixed_coverage(item_stock if len(item_stock) >= 2 else visible)
        types = []
        for _label, _day, type_name in visible:
            if type_name not in types:
                types.append(type_name)
        line["explanation"] = {
            "id": "reorder:%s" % name,
            "basis": "live",
            "label_kind": kind,
            "value": None if missing else cost,
            "status": "unavailable" if missing else "available",
            "reason": "Missing purchase cost" if missing else "",
            "items_coverage": items_date if can_see_source(perms, "items") else "",
            "stock_date": stock_date if can_see_source(perms, "stock") else "",
            "sources": live_sources(store, types, perms),
            "mixed_coverage": mixed,
            "coverage_note": note,
        }
    return built
