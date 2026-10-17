"""Put the shared ledger on the screens that still showed the previous settlement.

A saved report run keeps the result it stored. The live customer, group, rep,
stock, collection, and statement figures read the current publication. Rolling
the engine back does not delete confirmed links.
"""

from __future__ import annotations

from vay.dates import parse_date
from vay.ledger import ENGINE_VERSION
from vay.payments import payment_behavior, payment_summary
from vay.settlement import bucket_key, empty_buckets

from server.ledger_surface import current_assessment
from server.org_policy import get_org_policy, save_org_policy

LEGACY_ENGINE = "legacy"


def _public_invoice(line):
    number = str((line or {}).get("invoice") or "").strip()
    if number and "\x1f" not in number:
        return number
    return "Sale"


def ledger_engine(store):
    return str((get_org_policy(store) or {}).get("ledger_engine") or "")


def ledger_enabled(store):
    return ledger_engine(store) == ENGINE_VERSION


def enable_ledger(store):
    save_org_policy(store, {"ledger_engine": ENGINE_VERSION})
    return {"ledger_engine": ENGINE_VERSION}


def rollback_ledger(store):
    """Return screens to the previous settlement. Confirmed links stay stored."""
    save_org_policy(store, {"ledger_engine": LEGACY_ENGINE})
    from server.ledger_persist import LINK_TYPE
    return {
        "ledger_engine": LEGACY_ENGINE,
        "confirmed_links": len(store.rows_of_type(LINK_TYPE) or []),
    }


def _num(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _customer_row(assessment, name):
    want = str(name or "").strip().lower()
    for row in (assessment or {}).get("customers") or []:
        if str(row.get("customer_id") or "") == want:
            return row
    return None


def project_customer(customer, as_of, bands=None, start_month=None):
    """Screen fields for one ledger customer. An unknown opening is not shown as zero."""
    if not customer:
        return None
    settlement = customer.get("settlement") or {}
    reconciliation = settlement.get("reconciliation") or {}
    withheld = list(customer.get("withheld_outputs") or [])
    exact = "exact_balance" not in withheld
    net = _num(reconciliation.get("ledger_net"))
    open_lines = []
    buckets = empty_buckets(bands)
    unknown_age_due = 0.0
    for debit in settlement.get("open_debits") or []:
        remaining = _num(debit.get("remaining")) or 0.0
        if remaining <= 0:
            continue
        unknown = bool(debit.get("unknown_age")) or debit.get("invoice_age_days") in (None, "")
        age = 0 if unknown else int(_num(debit.get("invoice_age_days")) or 0)
        opening = bool(debit.get("opening"))
        line = {
            "kind": "opening" if opening else "sale",
            "what": "Opening balance" if opening else "Sale",
            "due": remaining,
            "age_days": age,
            "unknown_age": unknown,
            "invoice": debit.get("invoice_number") or "",
            "invoice_id": debit.get("source_id") or "",
            "date": debit.get("invoice_date") or debit.get("effective_date") or "",
            "evidence": (customer.get("opening") or {}).get("evidence") or "" if opening else "source_confirmed",
        }
        open_lines.append(line)
        if unknown:
            unknown_age_due += remaining
        else:
            buckets[bucket_key(age, bands)] += remaining
    allocs = []
    links = []
    as_of_day = parse_date(as_of)
    for row in settlement.get("allocations") or []:
        amount = _num(row.get("amount")) or 0.0
        if amount <= 0:
            continue
        receipt = parse_date(row.get("effective_date"))
        invoice_day = parse_date(row.get("invoice_date"))
        if receipt and invoice_day:
            age = (receipt.date() - invoice_day.date()).days
            unknown = False
        else:
            age = 0
            unknown = True
        allocs.append({
            "receipt_date": receipt,
            "target_date": invoice_day,
            "amount": amount,
            "age_days": age,
            "kind": "receipt" if row.get("cash") else (row.get("credit_kind") or "credit"),
            "invoice": row.get("invoice_number") or row.get("debit_id") or "",
            "invoice_id": row.get("debit_id") or "",
            "evidence": row.get("evidence") or "",
            "cash": bool(row.get("cash")),
            "unknown_age": unknown,
        })
        links.append({
            "credit_id": row.get("credit_id") or "",
            "debit_id": row.get("debit_id") or "",
            "invoice": row.get("invoice_number") or "",
            "amount": amount,
            "evidence": row.get("evidence") or "",
            "cash": bool(row.get("cash")),
            "effective_date": row.get("effective_date") or "",
        })
    from server.customers import build_settlements_summary, _status_from_open
    settlements = None
    collection_buckets = empty_buckets(bands)
    unused_cash = 0.0
    has_known = bool(open_lines)
    for row in settlement.get("unused_credits") or []:
        remaining = _num(row.get("remaining")) or 0.0
        if remaining <= 0:
            continue
        has_known = True
        if row.get("cash"):
            unused_cash += remaining
    if as_of_day is not None:
        cash_allocs = [row for row in allocs if row.get("cash")]
        settlements = build_settlements_summary(
            cash_allocs, as_of_day, bands=bands, credit=unused_cash, start_month=start_month,
        )
        for row in cash_allocs:
            if row.get("unknown_age"):
                continue
            collection_buckets[bucket_key(row.get("age_days") or 0, bands)] += row["amount"]
    if exact or has_known:
        due = 0.0 if net is None else net
        status = _status_from_open(due, open_lines)
    else:
        due = None
        status = "unknown"
    opening = customer.get("opening") or {}
    return {
        "due": due,
        "credit": due is not None and due < 0,
        "balance_exact": exact,
        "opening_status": opening.get("status") or "",
        "opening_evidence": opening.get("evidence") or "",
        "opening_balance": _num(opening.get("amount")) if exact and opening.get("amount") not in (None, "") else 0.0,
        "open_invoices": open_lines,
        "invoices_waiting": len(open_lines),
        "owe_buckets": buckets,
        "due_buckets": buckets,
        "unknown_age_due": round(unknown_age_due, 2),
        "collection_buckets": collection_buckets,
        "settlements": settlements,
        "ledger_links": links,
        "unused_credits": list(settlement.get("unused_credits") or []),
        "ledger_exceptions": list(settlement.get("exceptions") or []),
        "withheld_outputs": withheld,
        "status": status,
        "ledger_engine": ENGINE_VERSION,
        "result_scope": "operational",
        "payments": payment_summary(
            settlement.get("receipts") or [],
            as_of=as_of_day or as_of,
            start_month=start_month,
            coverage=customer.get("coverage") or {},
        ),
        "payment_behavior": payment_behavior(
            settlement.get("timing") or [],
            settlement.get("open_debits") or [],
            settlement.get("unused_credits") or [],
            settlement.get("posted") or [],
            reconciliation=settlement.get("reconciliation") or {},
            as_of=as_of_day or as_of,
            start_month=start_month,
            coverage=customer.get("coverage") or {},
        ),
    }


def assessment_for(store, as_of):
    assessment, version = current_assessment(store, as_of)
    return assessment, version


def apply_ledger_customer(store, detail):
    if not isinstance(detail, dict) or not ledger_enabled(store):
        return detail
    assessment, version = assessment_for(store, detail.get("as_of") or "")
    row = _customer_row(assessment, detail.get("name"))
    detail["ledger_engine"] = ENGINE_VERSION
    detail["result_scope"] = "operational"
    detail["ledger_source_digest"] = version.get("digest") or ""
    if not row:
        return detail
    projected = project_customer(
        row,
        detail.get("as_of"),
        bands=detail.get("aging_bands"),
        start_month=detail.get("fiscal_year_start_month"),
    )
    if not projected:
        return detail
    detail.update(projected)
    detail["ledger_engine"] = ENGINE_VERSION
    detail["result_scope"] = "operational"
    detail["payment_behavior"] = payment_behavior(
        (row.get("settlement") or {}).get("timing") or [],
        (row.get("settlement") or {}).get("open_debits") or [],
        (row.get("settlement") or {}).get("unused_credits") or [],
        (row.get("settlement") or {}).get("posted") or [],
        reconciliation=(row.get("settlement") or {}).get("reconciliation") or {},
        as_of=detail.get("as_of"),
        start_month=detail.get("fiscal_year_start_month"),
        coverage=row.get("coverage") or {},
        promises=_promises_for(store, detail.get("name"), detail.get("as_of")),
    )
    return detail


def _promises_for(store, name, as_of):
    if not name:
        return None
    try:
        from server.collection import customer_follow_up
        follow = customer_follow_up(store, name, as_of)
    except ValueError:
        return None
    return follow.get("promises") or []


def apply_directory_row(customer, row, as_of, bands, start_month):
    projected = project_customer(customer, as_of, bands=bands, start_month=start_month)
    if not projected:
        return row
    from vay.settlement import flatten_collection, flatten_owe
    due = projected["due"]
    buckets = projected["owe_buckets"]
    collection = projected["collection_buckets"]
    row["due"] = due
    row["credit"] = due < 0
    row["status"] = projected["status"]
    row["balance_exact"] = projected["balance_exact"]
    row["opening_status"] = projected["opening_status"]
    row["ledger_engine"] = ENGINE_VERSION
    row["invoices_waiting"] = projected["invoices_waiting"]
    row.update(flatten_owe(buckets))
    row.update(flatten_collection(collection))
    return row


def collection_rows(store, as_of):
    if not ledger_enabled(store):
        return None
    assessment, _version = assessment_for(store, as_of)
    rows = []
    for customer in assessment.get("customers") or []:
        projected = project_customer(customer, as_of)
        if not projected:
            continue
        due = projected["due"]
        if due is None:
            continue
        if due <= 0 and projected["balance_exact"]:
            continue
        if due <= 0 and not projected["withheld_outputs"]:
            continue
        overdue = 0.0
        for line in projected["open_invoices"]:
            if line.get("unknown_age"):
                continue
            if (line.get("age_days") or 0) >= 30:
                overdue += line["due"]
        status_labels = {"urgent": "URGENT", "followup": "FOLLOW UP", "credit": "WATCH", "ontrack": "WATCH"}
        rows.append({
            "name": customer.get("customer_id") or "",
            "customer_id": customer.get("customer_id") or "",
            "status": "WATCH" if not projected["balance_exact"] else status_labels.get(projected["status"] or "", "WATCH"),
            "balance": round(due, 2),
            "balance_exact": projected["balance_exact"],
            "overdue_30": round(overdue, 2),
            "invoice_detail": "ledger",
            "invoices": [
                {
                    "invoice": _public_invoice(line),
                    "remaining": line.get("due"),
                    "amount": line.get("due"),
                }
                for line in projected["open_invoices"]
            ],
            "drill": {"kind": "customer", "name": customer.get("customer_id") or ""},
            "source": "ledger",
        })
    rows.sort(key=lambda item: (-item["overdue_30"], -item["balance"], item["name"]))
    return rows


def list_exceptions(store, as_of):
    assessment, version = assessment_for(store, as_of)
    rows = []
    for customer in assessment.get("customers") or []:
        opening = customer.get("opening") or {}
        if opening.get("status") == "unresolved":
            rows.append({
                "customer_id": customer.get("customer_id") or "",
                "code": "missing_opening",
                "message": "Customer has no verified opening balance.",
                "action": "import_opening",
            })
        for item in (customer.get("settlement") or {}).get("exceptions") or []:
            code = item.get("code") or ""
            if code not in ("unresolved_reference", "ambiguous_reference", "already_settled_reference", "reconciliation_mismatch", "conflicting_links", "arr_only_advance"):
                continue
            action = "confirm_link" if code in ("unresolved_reference", "ambiguous_reference", "already_settled_reference") else "review"
            rows.append({
                "customer_id": customer.get("customer_id") or "",
                "code": code,
                "message": item.get("message") or "",
                "credit_id": item.get("credit_id") or "",
                "debit_id": item.get("debit_id") or "",
                "action": action,
            })
    for item in assessment.get("items") or []:
        if item.get("opening_status") == "unresolved":
            rows.append({
                "item_id": item.get("item_id") or "",
                "code": "missing_stock_opening",
                "message": "Item has no imported stock opening.",
                "action": "import_opening",
            })
        difference = (item.get("bridge") or {}).get("difference")
        if difference not in (None, "", "0", "0.0000", "0.00"):
            rows.append({
                "item_id": item.get("item_id") or "",
                "code": "stock_difference",
                "message": "Stock bridge does not match the counted closing.",
                "action": "review",
            })
    return {
        "engine_version": version.get("engine_version") or ENGINE_VERSION,
        "source_digest": version.get("digest") or "",
        "as_of": str(as_of)[:10],
        "rows": rows,
    }


def preflight_public(assessment):
    customers = (assessment or {}).get("customers") or []
    items = (assessment or {}).get("items") or []
    return {
        "engine_version": (assessment or {}).get("engine_version") or "",
        "as_of": (assessment or {}).get("as_of") or "",
        "customers": len(customers),
        "unresolved_customers": sum(1 for row in customers if (row.get("opening") or {}).get("status") == "unresolved"),
        "items": len(items),
        "unresolved_items": sum(1 for row in items if row.get("opening_status") == "unresolved"),
    }
