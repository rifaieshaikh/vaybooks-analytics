"""Opening bridges on profiles, supplier analysis, quality review, and exports.

A report run freezes the source rows before generation. Later imports do not
change that run's assessment.
"""

from __future__ import annotations

import hashlib

from vay.ledger import ENGINE_VERSION, POLICY_INVOICE_FIFO

from server.opening_check import _TYPES, assess_store

_BASIS_TYPES = _TYPES


def source_version(store):
    parts = []
    counts = {}
    for type_name in _BASIS_TYPES:
        rows = list(store.rows_of_type(type_name) or [])
        counts[type_name] = len(rows)
        for row in rows:
            parts.append("%s\t%s\t%s" % (
                type_name,
                row.get("uk") or "",
                row.get("source_upload_id") or "",
            ))
    parts.sort()
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return {
        "engine_version": ENGINE_VERSION,
        "policy": POLICY_INVOICE_FIFO,
        "digest": digest,
        "counts": counts,
    }


def current_assessment(store, as_of):
    """Return the assessment for these exact rows. A changed import builds a new one."""
    version = source_version(store)
    cached = getattr(store, "_opening_assessment", None)
    cached_version = getattr(store, "_opening_basis", None) or {}
    as_of_text = str(as_of)[:10]
    if (
        cached
        and cached_version.get("digest") == version["digest"]
        and str(cached.get("as_of") or "")[:10] == as_of_text
    ):
        return cached, cached_version
    assessment = assess_store(store, as_of)
    version["as_of"] = assessment.get("as_of") or as_of_text
    store._opening_assessment = assessment
    store._opening_basis = version
    return assessment, version


def freeze_opening_basis(store, as_of):
    """Read the current rows once and keep that assessment for this run."""
    assessment, version = current_assessment(store, as_of)
    return assessment, version


def customer_bridge_view(assessment, name):
    want = str(name or "").strip().lower()
    for row in (assessment or {}).get("customers") or []:
        if str(row.get("customer_id") or "") == want:
            opening = row.get("opening") or {}
            settlement = row.get("settlement") or {}
            reconciliation = settlement.get("reconciliation") or {}
            return {
                "opening_status": opening.get("status") or "",
                "opening_amount": opening.get("amount"),
                "origin": opening.get("origin") or "",
                "evidence": opening.get("evidence") or "",
                "tie_out": bool(opening.get("tie_out")),
                "coverage": row.get("coverage") or {},
                "bridge": row.get("bridge") or {},
                "overlap": row.get("overlap") or [],
                "reconciliation_state": reconciliation.get("state") or "",
                "allowed_outputs": row.get("allowed_outputs") or [],
                "withheld_outputs": row.get("withheld_outputs") or [],
            }
    return None


def item_bridge_view(assessment, name):
    want = str(name or "").strip().lower()
    rows = [
        row for row in (assessment or {}).get("items") or []
        if str(row.get("item_id") or "").strip().lower() == want
    ]
    if not rows:
        return None
    return {
        "bridges": [{
            "location": row.get("location") or "",
            "unit": row.get("unit") or "",
            "lot": row.get("lot") or "",
            "opening_status": row.get("opening_status") or "",
            "bridge": row.get("bridge") or {},
            "planning": row.get("planning") or [],
            "withheld_outputs": row.get("withheld_outputs") or [],
        } for row in rows],
        "cost_history": [
            dict(cost, item_id=row.get("item_id") or "")
            for row in rows
            for cost in (row.get("cost_history") or [])
        ],
        "valuation_method_unchanged": True,
    }


def supplier_purchase_view(assessment, supplier_name):
    """Received purchases for one supplier. Costs stay on the purchase, not on the valuation."""
    want = str(supplier_name or "").strip().lower()
    blank = want in ("", "no supplier")
    lines = []
    for row in (assessment or {}).get("items") or []:
        for cost in row.get("cost_history") or []:
            supplier = str(cost.get("supplier") or "").strip().lower()
            if blank:
                if supplier not in ("", "no supplier"):
                    continue
            elif supplier != want:
                continue
            lines.append(dict(cost, item_id=row.get("item_id") or "", unit=row.get("unit") or ""))
    qty = 0.0
    for line in lines:
        try:
            qty += float(line.get("qty") or 0)
        except (TypeError, ValueError):
            continue
    return {
        "supplier": supplier_name or "",
        "receipt_count": len(lines),
        "received_qty": round(qty, 4),
        "cost_history": lines,
        "valuation_method_unchanged": True,
    }


def stamp_customer(detail, store):
    if not isinstance(detail, dict) or not store:
        return detail
    as_of = detail.get("as_of") or ""
    if not as_of:
        return detail
    assessment, _version = current_assessment(store, as_of)
    view = customer_bridge_view(assessment, detail.get("name"))
    if view:
        detail["ledger_bridge"] = view
    return detail


def stamp_item(detail, store):
    if not isinstance(detail, dict) or not store:
        return detail
    as_of = detail.get("as_of") or ""
    if not as_of:
        return detail
    assessment, _version = current_assessment(store, as_of)
    view = item_bridge_view(assessment, detail.get("name"))
    if view:
        detail["stock_bridge"] = view
    return detail


def stamp_supplier(detail, store, as_of):
    if not isinstance(detail, dict) or str(detail.get("dimension") or "") != "supplier":
        return detail
    assessment, _version = current_assessment(store, as_of)
    detail["purchases"] = supplier_purchase_view(assessment, detail.get("name"))
    return detail


def quality_rows(assessment):
    rows = []
    for row in (assessment or {}).get("customers") or []:
        opening = row.get("opening") or {}
        name = row.get("customer_id") or "customer"
        if opening.get("status") == "unresolved":
            rows.append({
                "severity": "warning",
                "message": "Customer %s has no verified opening balance." % name,
                "affected_reports": ["Customers", "Opening bridges"],
                "fix": "Import the customer opening, or declare the movements complete and supply a closing balance.",
            })
        reconciliation = ((row.get("settlement") or {}).get("reconciliation") or {})
        if reconciliation.get("state") == "mismatch":
            rows.append({
                "severity": "warning",
                "message": "Customer %s closing balance does not match the ledger." % name,
                "affected_reports": ["Customers", "Opening bridges"],
                "fix": "Review the bridge difference. Do not add a balancing entry.",
            })
    for row in (assessment or {}).get("items") or []:
        if row.get("opening_status") != "unresolved":
            difference = (row.get("bridge") or {}).get("difference")
            if difference not in (None, "", "0", "0.0000", "0.00"):
                rows.append({
                    "severity": "warning",
                    "message": "Item %s stock bridge does not match the counted closing." % (row.get("item_id") or "item"),
                    "affected_reports": ["Items", "Opening bridges"],
                    "fix": "Compare the opening, purchases, and stock movements with the stock count.",
                })
            continue
        rows.append({
            "severity": "warning",
            "message": "Item %s has no imported stock opening." % (row.get("item_id") or "item"),
            "affected_reports": ["Items", "Opening bridges"],
            "fix": "Import the opening stock. The quantity is not estimated.",
        })
    return rows


def bridge_reports(assessment):
    customer_rows = []
    for row in (assessment or {}).get("customers") or []:
        opening = row.get("opening") or {}
        bridge = row.get("bridge") or {}
        customer_rows.append([
            row.get("customer_id") or "",
            opening.get("status") or "",
            opening.get("evidence") or "",
            opening.get("amount") if opening.get("amount") is not None else "",
            bridge.get("calculated_closing") if bridge.get("calculated_closing") is not None else "",
            bridge.get("source_closing") if bridge.get("source_closing") is not None else "",
            bridge.get("difference") if bridge.get("difference") is not None else "",
            ", ".join(row.get("withheld_outputs") or []),
        ])
    item_rows = []
    for row in (assessment or {}).get("items") or []:
        bridge = row.get("bridge") or {}
        item_rows.append([
            row.get("item_id") or "",
            row.get("location") or "",
            row.get("unit") or "",
            row.get("opening_status") or "",
            bridge.get("opening_qty") if bridge.get("opening_qty") is not None else "",
            bridge.get("calculated_closing") if bridge.get("calculated_closing") is not None else "",
            bridge.get("source_closing") if bridge.get("source_closing") is not None else "",
            bridge.get("difference") if bridge.get("difference") is not None else "",
            ", ".join(row.get("withheld_outputs") or []),
        ])
    return [
        {
            "id": "opening_customer_bridges",
            "title": "Customer opening bridges",
            "headers": [
                "Customer", "Opening status", "Evidence", "Opening",
                "Calculated closing", "Source closing", "Difference", "Withheld",
            ],
            "rows": customer_rows,
            "total": None,
            "key_col": 0,
            "group": "Data issues",
        },
        {
            "id": "opening_stock_bridges",
            "title": "Stock opening bridges",
            "headers": [
                "Item", "Location", "Unit", "Opening status", "Opening qty",
                "Calculated closing", "Counted closing", "Difference", "Withheld",
            ],
            "rows": item_rows,
            "total": None,
            "key_col": 0,
            "group": "Data issues",
        },
    ]
