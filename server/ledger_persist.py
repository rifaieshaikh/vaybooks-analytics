"""Persisted ledger results, confirmed links, and the shadow comparison.

Derived allocations are replaced when the source, policy, or cutoff changes.
Confirmed links and collection-promise allocations are different records and
are not rewritten by that replay. The previous settlement is only a comparison.
"""

from __future__ import annotations

import hashlib
import uuid

from vay.ledger import ENGINE_VERSION, money

from server.ledger_surface import current_assessment, source_version
from server.store import now_utc

RESULT_TYPE = "ledger_result"
LINK_TYPE = "ledger_link"
PUBLICATION_TYPE = "ledger_publication"
PUBLICATION_UK = "current"


def _as_of_text(as_of):
    return str(as_of)[:10]


def _link_fields(row):
    return dict((row or {}).get("fields") or {})


def link_fingerprint(store):
    parts = []
    for row in store.rows_of_type(LINK_TYPE) or []:
        fields = _link_fields(row)
        parts.append("%s|%s|%s|%s|%s|%s|%s" % (
            row.get("uk") or "",
            fields.get("customer_id") or "",
            fields.get("credit_id") or "",
            fields.get("debit_id") or "",
            fields.get("amount") if fields.get("amount") is not None else "",
            fields.get("evidence") or "",
            fields.get("voided_at") or "",
        ))
    parts.sort()
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def calculation_key(store, as_of):
    version = source_version(store)
    as_of_text = _as_of_text(as_of)
    raw = "\n".join([
        version.get("digest") or "",
        version.get("policy") or "",
        version.get("engine_version") or ENGINE_VERSION,
        as_of_text,
        link_fingerprint(store),
    ])
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return digest, version, as_of_text


def publication(store):
    row = store.find_row(PUBLICATION_TYPE, PUBLICATION_UK)
    return _link_fields(row)


def invalidate_ledger(store):
    """Drop the current publication. Confirmed links and promise allocations stay."""
    store.delete_row(PUBLICATION_TYPE, PUBLICATION_UK)
    return {"invalidated": True}


def confirmed_links(store):
    rows = []
    for row in store.rows_of_type(LINK_TYPE) or []:
        fields = _link_fields(row)
        if fields.get("voided_at"):
            continue
        if fields.get("evidence") != "manually_confirmed":
            continue
        rows.append(fields)
    return rows


def save_confirmed_link(store, body, username=""):
    """Store a manual settlement instruction. This does not create a promise allocation."""
    payload = dict(body or {})
    evidence = str(payload.get("evidence") or "manually_confirmed")
    if evidence != "manually_confirmed":
        raise ValueError("A saved instruction must be manually confirmed.")
    customer_id = str(payload.get("customer_id") or "").strip().lower()
    credit_id = str(payload.get("credit_id") or "").strip()
    debit_id = str(payload.get("debit_id") or "").strip()
    amount = money(payload.get("amount"))
    if not customer_id or not credit_id or not debit_id:
        raise ValueError("A confirmed link needs a customer, a credit, and a debit.")
    if amount is None or amount <= 0:
        raise ValueError("A confirmed link amount must be positive.")
    uk = str(payload.get("id") or uuid.uuid4().hex)
    fields = {
        "id": uk,
        "customer_id": customer_id,
        "credit_id": credit_id,
        "debit_id": debit_id,
        "amount": format(amount, "f"),
        "evidence": "manually_confirmed",
        "currency": str(payload.get("currency") or "").strip().upper(),
        "created_by": username or "",
        "voided_at": "",
        "voided_by": "",
        "derived": False,
    }
    store.upsert_row({"type": LINK_TYPE, "uk": uk, "fields": fields})
    invalidate_ledger(store)
    return fields


def void_confirmed_link(store, link_id, username=""):
    row = store.find_row(LINK_TYPE, str(link_id or ""))
    if not row:
        raise ValueError("Confirmed link was not found.")
    fields = _link_fields(row)
    fields["voided_at"] = fields.get("voided_at") or str(now_utc())
    fields["voided_by"] = username or ""
    store.upsert_row({"type": LINK_TYPE, "uk": row.get("uk"), "fields": fields})
    invalidate_ledger(store)
    return fields


def _result_fields(customer, key, version, as_of_text):
    settlement = customer.get("settlement") or {}
    exceptions = list(settlement.get("exceptions") or [])
    return {
        "calculation_key": key,
        "customer_id": customer.get("customer_id") or "",
        "currency": customer.get("currency") or "",
        "organization_id": customer.get("organization_id") or "",
        "legal_entity_id": customer.get("legal_entity_id") or "",
        "engine_version": version.get("engine_version") or ENGINE_VERSION,
        "policy": version.get("policy") or settlement.get("policy") or "",
        "as_of": as_of_text,
        "source_digest": version.get("digest") or "",
        "derived": True,
        "opening": customer.get("opening") or {},
        "withheld_outputs": list(customer.get("withheld_outputs") or []),
        "allocations": list(settlement.get("allocations") or []),
        "open_debits": list(settlement.get("open_debits") or []),
        "unused_credits": list(settlement.get("unused_credits") or []),
        "exceptions": exceptions,
        "reversals": [
            item for item in exceptions
            if item.get("reverses_id") or item.get("code") == "reversal_target_missing"
        ],
        "reconciliation": settlement.get("reconciliation") or {},
    }


def publish_ledger(store, as_of):
    """Write derived results for this cutoff. Repeat the same inputs and the rows stay put."""
    key, version, as_of_text = calculation_key(store, as_of)
    current = publication(store)
    if current.get("calculation_key") == key and str(current.get("as_of") or "")[:10] == as_of_text:
        return {
            "reused": True,
            "calculation_key": key,
            "as_of": as_of_text,
            "engine_version": version.get("engine_version") or ENGINE_VERSION,
            "policy": version.get("policy") or "",
            "source_digest": version.get("digest") or "",
            "customer_count": current.get("customer_count") or 0,
        }
    assessment, basis = current_assessment(store, as_of)
    written = 0
    for customer in assessment.get("customers") or []:
        customer_id = customer.get("customer_id") or ""
        uk = "%s:%s" % (key[:16], customer_id)
        store.upsert_row({
            "type": RESULT_TYPE,
            "uk": uk,
            "fields": _result_fields(customer, key, basis, as_of_text),
        })
        written += 1
    for row in list(store.rows_of_type(RESULT_TYPE) or []):
        fields = _link_fields(row)
        if fields.get("calculation_key") == key:
            continue
        store.delete_row(RESULT_TYPE, row.get("uk"))
    store.upsert_row({
        "type": PUBLICATION_TYPE,
        "uk": PUBLICATION_UK,
        "fields": {
            "calculation_key": key,
            "as_of": as_of_text,
            "engine_version": basis.get("engine_version") or ENGINE_VERSION,
            "policy": basis.get("policy") or "",
            "source_digest": basis.get("digest") or "",
            "customer_count": written,
        },
    })
    return {
        "reused": False,
        "calculation_key": key,
        "as_of": as_of_text,
        "engine_version": basis.get("engine_version") or ENGINE_VERSION,
        "policy": basis.get("policy") or "",
        "source_digest": basis.get("digest") or "",
        "customer_count": written,
    }


def rewrite_links_for_merge(store, source_name, destination_name):
    source_key = str(source_name or "").strip().lower()
    destination = str(destination_name or "").strip().lower()
    if not source_key or not destination or source_key == destination:
        return 0
    moved = 0
    for row in list(store.rows_of_type(LINK_TYPE) or []):
        fields = _link_fields(row)
        if str(fields.get("customer_id") or "") != source_key:
            continue
        fields["prior_customer_id"] = source_key
        fields["customer_id"] = destination
        store.upsert_row({"type": LINK_TYPE, "uk": row.get("uk"), "fields": fields})
        moved += 1
    invalidate_ledger(store)
    return moved


def _legacy_money(value):
    parsed = money(value)
    if parsed is None:
        return None
    return format(parsed, "f")


def explain_difference(customer, legacy_due):
    """Say why the shared ledger and the previous settlement differ.

    The previous amount is a comparison reading. It does not decide the ledger.
    """
    opening = customer.get("opening") or {}
    settlement = customer.get("settlement") or {}
    reconciliation = settlement.get("reconciliation") or {}
    withheld = set(customer.get("withheld_outputs") or [])
    reasons = []
    if opening.get("status") == "unresolved" or "exact_balance" in withheld:
        reasons.append(
            "The ledger leaves the opening unknown, so the exact balance stays withheld. "
            "The previous settlement estimates an opening from the closing balance."
        )
    if reconciliation.get("state") == "arr_only_advance":
        reasons.append(
            "The ledger reports a net advance and keeps the originating receipt unknown. "
            "It does not add a receipt to match the previous balance."
        )
    if any(row.get("evidence") == "inferred" for row in settlement.get("allocations") or []):
        reasons.append(
            "The ledger pays opening debt and then invoices by issue date, and marks those links inferred."
        )
    if any(row.get("code") == "unresolved_reference" for row in settlement.get("exceptions") or []):
        reasons.append(
            "A receipt names an invoice the ledger cannot apply, so that credit stays unresolved."
        )
    if not reasons:
        reasons.append(
            "The source rows are the same. The shared ledger and the previous settlement allocate them differently."
        )
    reasons.append("The previous settlement is a comparison reading. The shared ledger is the calculation being checked.")
    return {
        "customer_id": customer.get("customer_id") or "",
        "legacy_due": _legacy_money(legacy_due),
        "ledger_net": reconciliation.get("ledger_net"),
        "opening_status": opening.get("status") or "",
        "withheld_outputs": list(customer.get("withheld_outputs") or []),
        "reasons": reasons,
    }


def shadow_report(assessment, legacy_customers):
    by_name = {}
    for row in legacy_customers or []:
        name = str((row or {}).get("name") or (row or {}).get("customer_id") or "").strip().lower()
        if name:
            by_name[name] = row.get("due")
    material = []
    matches = 0
    compared = 0
    for customer in (assessment or {}).get("customers") or []:
        name = str(customer.get("customer_id") or "")
        if name not in by_name:
            continue
        compared += 1
        legacy_text = _legacy_money(by_name[name])
        ledger_net = ((customer.get("settlement") or {}).get("reconciliation") or {}).get("ledger_net")
        withheld = "exact_balance" in set(customer.get("withheld_outputs") or [])
        same = legacy_text is not None and ledger_net is not None and legacy_text == str(ledger_net) and not withheld
        if same:
            matches += 1
            continue
        material.append(explain_difference(customer, by_name[name]))
    return {
        "compared": compared,
        "matches": matches,
        "material_count": len(material),
        "material": material,
        "legacy_is_oracle": False,
    }
