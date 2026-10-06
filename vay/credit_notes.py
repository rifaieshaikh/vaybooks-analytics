"""Sales-return credit notes.

A credit note reduces net sales and open invoices. It is not a collection
and it does not move item quantities.
"""

from vay.dates import clean_text


def rep_index(pairs):
    """party lower -> [(date, rep), ...] sorted by date."""
    by = {}
    for party, date, rep in pairs or []:
        party_l = clean_text(party).lower()
        name = clean_text(rep)
        if not party_l or not date or not name:
            continue
        by.setdefault(party_l, []).append((date, name))
    for party_l in by:
        by[party_l].sort(key=lambda item: item[0])
    return by


def rep_on_or_before(index, party, date):
    """Sales rep on that party's latest sale on or before date."""
    best = ""
    if not date:
        return best
    for sale_date, rep in (index or {}).get(clean_text(party).lower(), []):
        if sale_date <= date:
            best = rep
        else:
            break
    return best


def credit_party(fields):
    fields = fields or {}
    return clean_text(fields.get("Party Name") or fields.get("Account Name"))


def resolve_credit_party(party, known):
    """Map a credit-note party onto a customer name.

    Exact names stay put. A longer note name such as "EDGE POINT B.P ANGADI"
    maps to the longest known customer it extends, "EDGE POINT".
    """
    name = clean_text(party).lower()
    if not name:
        return ""
    known = {clean_text(item).lower() for item in (known or []) if clean_text(item)}
    if name in known:
        return name
    best = ""
    for customer in known:
        if name.startswith(customer + " ") and len(customer) > len(best):
            best = customer
    return best or name
