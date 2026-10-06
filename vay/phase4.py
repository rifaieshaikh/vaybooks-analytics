"""Saved reports over the governed metric catalog. A saved report does not change source totals."""

from __future__ import annotations

from vay.domain import METRIC_IDS
from vay.metrics import metric_versions

DIMENSIONS = ("customer", "product", "sales_rep", "group", "location")
COMPARISONS = ("current", "prior", "prior_year")
STATUSES = ("draft", "approved")

SNAPSHOT_METRICS = {
    "ar_balance",
    "ar_overdue_30",
    "dso",
    "collection_priority_score",
    "stock_cover_days",
    "slow_stock_value",
    "gross_margin",
}
COMPANY_METRICS = {"dso", "data_freshness"}
SNAPSHOT_HISTORY = "No earlier snapshot"

METRIC_META = {
    "sales_mtd": {"label": "Sales", "family": "scorecard", "dimensions": ("customer", "sales_rep", "group", "product", "location")},
    "sales_ytd": {"label": "Sales YTD", "family": "scorecard", "dimensions": ("customer", "sales_rep", "group")},
    "collections_mtd": {"label": "Collections", "family": "scorecard", "dimensions": ("customer", "sales_rep", "group")},
    "collection_rate": {"label": "Collection rate", "family": "scorecard", "dimensions": ("customer", "sales_rep", "group")},
    "sales_change_drivers": {"label": "Sales change", "family": "scorecard", "dimensions": ("customer", "sales_rep", "group", "product")},
    "inactive_customers": {"label": "Inactive customers", "family": "scorecard", "dimensions": ("customer", "sales_rep", "group")},
    "ar_balance": {"label": "Outstanding", "family": "followup", "dimensions": ("customer", "sales_rep", "group")},
    "ar_overdue_30": {"label": "Overdue 30+", "family": "followup", "dimensions": ("customer", "sales_rep", "group")},
    "dso": {"label": "DSO", "family": "followup", "dimensions": ()},
    "collection_priority_score": {"label": "Collection priority", "family": "followup", "dimensions": ("customer", "sales_rep", "group")},
    "item_velocity": {"label": "Item velocity", "family": "items", "dimensions": ("product",)},
    "stock_cover_days": {"label": "Stock cover", "family": "items", "dimensions": ("product",)},
    "slow_stock_value": {"label": "Slow stock", "family": "items", "dimensions": ("product",)},
    "gross_margin": {"label": "Gross margin", "family": "items", "dimensions": ("product",)},
    "data_freshness": {"label": "Data freshness", "family": "quality", "dimensions": ()},
}

TEMPLATES = (
    {
        "id": "sales_by_rep",
        "name": "Sales by salesperson",
        "metric_ids": ["sales_mtd"],
        "dimension": "sales_rep",
        "comparison": "current",
        "filters": [],
        "show_pack_size": False,
        "row_filter": "",
        "custom_column": "",
    },
    {
        "id": "overdue_by_customer",
        "name": "Overdue by customer",
        "metric_ids": ["ar_overdue_30"],
        "dimension": "customer",
        "comparison": "current",
        "filters": [],
        "show_pack_size": False,
        "row_filter": "",
        "custom_column": "",
    },
    {
        "id": "short_cover",
        "name": "Short-cover items",
        "metric_ids": ["stock_cover_days"],
        "dimension": "product",
        "comparison": "current",
        "filters": [],
        "show_pack_size": True,
        "row_filter": "short_cover",
        "custom_column": "",
    },
)


def _cell(value, status="eligible", reason=""):
    return {"value": value, "status": status, "reason": reason or ""}


def _unavailable(reason):
    return _cell(None, "unavailable", reason or "Unavailable")


def metric_cell(metric_id, member, comparison, eligibility):
    """One governed metric for one row. An ineligible metric stays unavailable."""
    meta = METRIC_META.get(metric_id)
    if not meta:
        return _unavailable("Unknown metric")
    state = (eligibility or {}).get(metric_id) or {}
    if state.get("status") == "unavailable":
        return _unavailable(state.get("reason") or "Unavailable")
    dimension = (member or {}).get("dimension") or ""
    if dimension and dimension not in meta["dimensions"]:
        return _unavailable("Not available for this grouping")
    if metric_id in COMPANY_METRICS:
        return _unavailable("Not available for this grouping")
    if metric_id in SNAPSHOT_METRICS and comparison != "current":
        return _unavailable(SNAPSHOT_HISTORY)
    if comparison not in COMPARISONS:
        return _unavailable("Unknown comparison")
    return _value_cell(metric_id, member or {}, comparison)


def _opt(bucket, comparison):
    if not isinstance(bucket, dict):
        return None
    return bucket.get(comparison)


def _change(bucket):
    current = _opt(bucket, "current")
    prior = _opt(bucket, "prior")
    if current is None and prior is None:
        return None
    return round(float(current or 0) - float(prior or 0), 2)


def _rate(collections, sales):
    if collections is None or sales is None or sales == 0:
        return None
    return round(100.0 * float(collections) / float(sales), 1)


def _value_cell(metric_id, member, comparison):
    sales = member.get("sales") or {}
    collections = member.get("collections") or {}
    if metric_id == "sales_mtd":
        return _cell(_opt(sales, comparison))
    if metric_id == "sales_ytd":
        if comparison != "current":
            return _unavailable(SNAPSHOT_HISTORY)
        return _cell(member.get("ytd"))
    if metric_id == "collections_mtd":
        return _cell(_opt(collections, comparison))
    if metric_id == "collection_rate":
        return _cell(_rate(_opt(collections, comparison), _opt(sales, comparison)))
    if metric_id == "sales_change_drivers":
        if comparison != "current":
            return _cell(_opt(sales, comparison))
        return _cell(_change(sales))
    if metric_id == "inactive_customers":
        if comparison != "current":
            return _unavailable("Not available for this comparison")
        return _cell(member.get("inactive"))
    if metric_id == "ar_balance":
        return _cell(member.get("balance"))
    if metric_id == "ar_overdue_30":
        return _cell(member.get("overdue_30"))
    if metric_id == "collection_priority_score":
        return _cell(member.get("priority"))
    if metric_id == "item_velocity":
        return _cell(_opt(member.get("qty") or {}, comparison))
    if metric_id == "stock_cover_days":
        if member.get("cover_days") is None and member.get("cover_label"):
            return _cell(None, "eligible", member.get("cover_label"))
        return _cell(member.get("cover_days"))
    if metric_id == "slow_stock_value":
        if member.get("slow_reason"):
            return _unavailable(member.get("slow_reason"))
        return _cell(member.get("slow_value"))
    if metric_id == "gross_margin":
        reason = (member.get("margin_reason") or {}).get(comparison) if isinstance(member.get("margin_reason"), dict) else member.get("margin_reason")
        if reason:
            return _unavailable(reason)
        return _cell(_opt(member.get("margin") or {}, comparison))
    return _unavailable("Unknown metric")


def _filters_match(member, filters):
    for item in filters or []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "name")
        expected = str(item.get("value") or "")
        actual = member.get("name") if field == "name" else member.get(field)
        if str(actual or "") != expected:
            return False
    return True


def _short_cover(member, limit):
    cover = member.get("cover_days")
    if cover is None:
        return False
    try:
        return float(cover) <= float(limit)
    except (TypeError, ValueError):
        return False


def run_definition(members, definition, eligibility, cover_limit=30):
    """Group already-built rows. Saving is separate and does not call this."""
    definition = definition or {}
    metric_ids = [mid for mid in (definition.get("metric_ids") or []) if mid in METRIC_IDS]
    comparison = definition.get("comparison") or "current"
    if comparison not in COMPARISONS:
        comparison = "current"
    dimension = definition.get("dimension") or "customer"
    versions = metric_versions()
    metrics = []
    for mid in metric_ids:
        state = (eligibility or {}).get(mid) or {}
        meta = METRIC_META.get(mid) or {}
        if state.get("status") == "unavailable":
            metrics.append({
                "id": mid,
                "label": meta.get("label") or mid,
                "status": "unavailable",
                "reason": state.get("reason") or "Unavailable",
            })
        elif dimension not in (meta.get("dimensions") or ()):
            metrics.append({
                "id": mid,
                "label": meta.get("label") or mid,
                "status": "unavailable",
                "reason": "Not available for this grouping",
            })
        else:
            metrics.append({"id": mid, "label": meta.get("label") or mid, "status": "eligible", "reason": ""})
    if definition.get("row_filter") == "returns":
        for row in metrics:
            if row["id"] == "sales_mtd":
                row["label"] = "Returns"
    blocked = {row["id"] for row in metrics if row["status"] == "unavailable"}
    rows = []
    for member in members or []:
        if not _filters_match(member, definition.get("filters") or []):
            continue
        if definition.get("row_filter") == "short_cover" and "stock_cover_days" not in blocked:
            if not _short_cover(member, cover_limit):
                continue
        if definition.get("row_filter") == "repeat" and member.get("movement") != "repeat":
            continue
        if definition.get("row_filter") == "returns":
            amount = _opt(member.get("returns") or {}, comparison)
            if amount is None:
                continue
        stamped = dict(member)
        stamped["dimension"] = dimension
        cells = {}
        for mid in metric_ids:
            cells[mid] = metric_cell(mid, stamped, comparison, eligibility)
        if definition.get("row_filter") == "returns" and "sales_mtd" in cells:
            cells["sales_mtd"] = _cell(_opt(member.get("returns") or {}, comparison))
        custom = member.get("custom")
        rows.append({
            "name": member.get("name") or "",
            "cells": cells,
            "pack_size": member.get("pack_size") if member.get("pack_size") not in (None, "") else "",
            "custom": "" if custom in (None, "") else custom,
        })
    rows.sort(key=lambda row: (row.get("name") or "").lower())
    return {
        "dimension": dimension,
        "comparison": comparison,
        "metric_versions": {mid: versions.get(mid, 1) for mid in metric_ids},
        "metrics": metrics,
        "rows": rows,
        "show_pack_size": bool(definition.get("show_pack_size")),
        "custom_column": definition.get("custom_column") or "",
    }
