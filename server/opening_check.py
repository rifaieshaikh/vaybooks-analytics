"""Pre-report opening assessment for every customer and stock item.

The result is stored with the report run. It does not replace the balances
shown on existing screens; those stay on the current settlement until the
shared engine is connected.
"""

from __future__ import annotations

from vay.dates import clean_text, parse_date
from vay.ledger import assess_books, money

from server.account_aliases import alias_lookup, apply_alias_fields
from server.tenant import DEFAULT_ORG, current_org_id

_TYPES = (
    "sales", "receipt", "credit_note", "arr", "stock",
    "customer_opening", "stock_opening", "purchases", "stock_movement",
)


def assess_store(store, as_of):
    from server.due_days import get_default_due_days
    from server.org_policy import get_org_policy

    rows = []
    for type_name in _TYPES:
        for row in store.rows_of_type(type_name) or []:
            rows.append(row)
    policy = get_org_policy(store) or {}
    return assess_rows(
        rows,
        as_of=as_of,
        organization_id=current_org_id() or DEFAULT_ORG,
        currency=policy.get("currency_code") or "INR",
        terms_days=get_default_due_days(store),
        aliases=alias_lookup(store),
    )


def assess_rows(rows, *, as_of, organization_id, currency, terms_days, aliases=None):
    aliases = aliases or {}
    customers = {}
    items = {}
    for row in rows or []:
        fields = apply_alias_fields(dict((row.get("fields") or {})), aliases)
        type_name = row.get("type")
        if type_name in ("sales", "receipt", "credit_note", "arr", "customer_opening"):
            _take_customer(customers, row, fields, organization_id, currency, terms_days)
        elif type_name in ("stock", "stock_opening", "purchases", "stock_movement"):
            _take_item(items, row, fields)
    payload = []
    for bucket in customers.values():
        if bucket.get("checkpoint_conflict"):
            bucket["checkpoint_net"] = None
            bucket["movements_complete"] = False
        payload.append(bucket)
    return assess_books(payload, list(items.values()), as_of=as_of)


def _customer(customers, name, organization_id, currency):
    key = (name.lower(), currency)
    if key not in customers:
        customers[key] = {
            "organization_id": organization_id,
            "legal_entity_id": organization_id,
            "customer_id": name.lower(),
            "currency": currency,
            "imported_openings": [],
            "debits": [],
            "credits": [],
            "movements": [],
            "opening_keys": [],
            "movement_keys": [],
            "links": [],
            "reversals": [],
            "checkpoint_net": None,
            "checkpoint_conflict": False,
            "movements_complete": False,
            "coverage_start": None,
            "complete_through": None,
        }
    return customers[key]


def _party(fields):
    return clean_text(fields.get("Account Name") or fields.get("Party Name"))


def _currency(fields, default):
    text = clean_text(fields.get("Currency")).upper()
    return text or default


def _day(value):
    parsed = parse_date(value)
    if not parsed:
        return ""
    return parsed.strftime("%Y-%m-%d")


def _amount(fields, key):
    if fields.get(key) in (None, ""):
        return None
    return money(fields.get(key))


def _yes(value):
    return str(value or "").strip().lower() in ("1", "true", "yes", "y")


def _take_customer(customers, row, fields, organization_id, currency, terms_days):
    name = _party(fields)
    if not name:
        return
    code = _currency(fields, currency)
    bucket = _customer(customers, name, organization_id, code)
    scope = {
        "organization_id": organization_id,
        "legal_entity_id": organization_id,
        "customer_id": name.lower(),
        "currency": code,
    }
    type_name = row.get("type")
    source_id = str(row.get("uk") or "")
    if type_name == "sales":
        day = _day(fields.get("Date"))
        amount = _amount(fields, "Net Amount")
        if not day or amount is None:
            return
        invoice = clean_text(fields.get("Invoice No"))
        due = _day(fields.get("Due Date"))
        debit = dict(scope)
        debit.update({
            "source_id": source_id,
            "kind": "invoice",
            "amount": amount,
            "effective_date": day,
            "invoice_date": day,
            "invoice_number": invoice,
            "invoice_key": source_id,
        })
        if due:
            debit["due_date"] = due
        elif terms_days is not None:
            debit["terms_days"] = terms_days
        bucket["debits"].append(debit)
        bucket["movements"].append({"kind": "invoice", "amount": amount, "date": day})
        if invoice:
            bucket["movement_keys"].append(invoice)
        return
    if type_name == "receipt":
        day = _day(fields.get("Date"))
        amount = _amount(fields, "Amount")
        if not day or amount is None:
            return
        reference = clean_text(fields.get("Invoice No") or fields.get("Invoice") or fields.get("Invoice Number"))
        credit = dict(scope)
        credit.update({
            "source_id": source_id,
            "kind": "receipt",
            "amount": amount,
            "effective_date": day,
            "cash": True,
            "reference": reference,
            "pre_period": _yes(fields.get("Pre Period")),
        })
        bucket["credits"].append(credit)
        bucket["movements"].append({"kind": "receipt", "amount": amount, "date": day})
        return
    if type_name == "credit_note":
        day = _day(fields.get("Date"))
        amount = _amount(fields, "Net Amount")
        if not day or amount is None:
            return
        credit = dict(scope)
        credit.update({
            "source_id": source_id,
            "kind": "credit_note",
            "amount": amount,
            "effective_date": day,
            "cash": False,
            "reference": clean_text(fields.get("Against Invoice")),
        })
        bucket["credits"].append(credit)
        bucket["movements"].append({"kind": "credit_note", "amount": amount, "date": day})
        return
    if type_name == "arr":
        amount = _amount(fields, "Balance")
        if amount is None:
            return
        if bucket["checkpoint_net"] is not None and bucket["checkpoint_net"] != amount:
            bucket["checkpoint_conflict"] = True
        bucket["checkpoint_net"] = amount
        return
    kind = clean_text(fields.get("Kind")).lower()
    day = _day(fields.get("Date"))
    if day and not bucket["coverage_start"]:
        bucket["coverage_start"] = day
    complete_through = _day(fields.get("Complete Through"))
    if complete_through:
        bucket["complete_through"] = complete_through
    if _yes(fields.get("Complete")) or kind == "coverage":
        if _yes(fields.get("Complete")):
            bucket["movements_complete"] = True
    if kind == "coverage":
        return
    amount = _amount(fields, "Balance")
    if amount is None:
        return
    invoice = clean_text(fields.get("Invoice No"))
    invoice_day = _day(fields.get("Invoice Date"))
    bucket["imported_openings"].append({
        "source_id": source_id or "opening:%s" % len(bucket["imported_openings"]),
        "amount": amount,
        "effective_date": day,
        "invoice_date": invoice_day or None,
        "due_date": _day(fields.get("Due Date")) or None,
        "invoice_number": invoice,
        "invoice_key": invoice or source_id,
        "reference": clean_text(fields.get("Reference")),
    })
    if invoice:
        bucket["opening_keys"].append(invoice)


def _item(items, fields):
    name = clean_text(fields.get("Item Name"))
    if not name:
        return None
    location = clean_text(fields.get("Location"))
    lot = clean_text(fields.get("Lot"))
    unit = clean_text(fields.get("Unit"))
    key = (name.lower(), location.lower(), lot.lower(), unit.lower())
    if key not in items:
        items[key] = {
            "item_id": name,
            "location": location,
            "lot": lot,
            "unit": unit,
            "opening_qty": None,
            "opening_value": None,
            "source_closing_qty": None,
            "source_closing_value": None,
            "purchases": [],
            "movements": [],
        }
    return items[key]


def _take_item(items, row, fields):
    bucket = _item(items, fields)
    if bucket is None:
        return
    type_name = row.get("type")
    source_id = str(row.get("uk") or "")
    if type_name == "stock_opening":
        qty = fields.get("Qty")
        if qty in (None, ""):
            return
        bucket["opening_qty"] = qty
        if fields.get("Value") not in (None, ""):
            bucket["opening_value"] = fields.get("Value")
        return
    if type_name == "stock":
        if fields.get("Qty") not in (None, ""):
            bucket["source_closing_qty"] = fields.get("Qty")
        return
    if type_name == "purchases":
        received = str(fields.get("Receipt Status") or "").strip().lower()
        bucket["purchases"].append({
            "source_id": source_id,
            "movement_key": clean_text(fields.get("Movement Key")) or source_id,
            "role": "receipt" if received in ("received", "receipt") else "invoice",
            "qty": fields.get("Qty"),
            "received": received in ("received", "receipt", "yes", "true", "1"),
            "item_id": bucket["item_id"],
            "location": bucket["location"],
            "unit": bucket["unit"],
            "lot": bucket["lot"],
            "return_of": clean_text(fields.get("Return Of")),
            "supplier": clean_text(fields.get("Supplier")),
            "date": _day(fields.get("Receipt Date") or fields.get("Date")),
            "rate": None if fields.get("Rate") in (None, "") else fields.get("Rate"),
            "amount": None if fields.get("Amount") in (None, "") else fields.get("Amount"),
        })
        return
    movement = clean_text(fields.get("Movement")).lower().replace(" ", "_")
    direction = "in" if movement in ("customer_return", "transfer_in", "production_in") else "out"
    signed = fields.get("Signed Qty")
    row_move = {
        "kind": movement or "movement",
        "qty": fields.get("Qty"),
        "direction": direction,
    }
    if signed not in (None, ""):
        row_move["signed_qty"] = signed
    if movement == "count" and signed in (None, ""):
        row_move["signed_qty"] = fields.get("Qty")
    bucket["movements"].append(row_move)
