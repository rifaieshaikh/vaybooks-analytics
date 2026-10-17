"""Fill a missing sales rep or group when a row is saved or a report is built."""

from vay.config import DEFAULT_GROUP, DEFAULT_SALES_REP
from vay.credit_notes import rep_on_or_before, resolve_credit_party
from vay.dates import clean_text, parse_date


def blank_group(value):
    group = clean_text(value)
    return not group or group == DEFAULT_GROUP or group.upper().replace(" ", "_") == "NO_GROUP"


def real_group(value):
    """A stored group, or empty when the value is blank or the No Group placeholder."""
    if blank_group(value):
        return ""
    return clean_text(value)


def party_name(fields, type_name):
    fields = fields or {}
    if type_name == "receipt":
        return clean_text(fields.get("Account Name") or fields.get("Party Name"))
    return clean_text(fields.get("Party Name") or fields.get("Account Name"))


def blank_sales_rep(value):
    text = clean_text(value)
    return not text or text == "NO_REP"


def stamp_fields(fields, type_name, groups=None, reps=None, known=None):
    """Return a copy with Sales Rep and Group filled when they are blank.

    Sales and receipts with no rep become No Rep. A sales return keeps an
    explicit rep, otherwise the rep on that party's latest sale, otherwise No Rep.
    Outstanding with no group becomes No Group. A missing group on a sale
    becomes the party's group, or No Group.
    """
    fields = dict(fields or {})
    if type_name not in ("sales", "receipt", "credit_note", "arr"):
        return fields
    if type_name == "arr":
        if blank_group(fields.get("Group")):
            fields["Group"] = DEFAULT_GROUP
        return fields

    raw = party_name(fields, type_name)
    groups = groups or {}
    known = known or set(groups)
    key = raw.lower()
    if type_name == "credit_note":
        key = resolve_credit_party(raw, known)
    if blank_group(fields.get("Group")):
        fields["Group"] = real_group(groups.get(key)) or DEFAULT_GROUP
    if type_name == "credit_note":
        if blank_sales_rep(fields.get("Sales Rep")):
            found = rep_on_or_before(reps, key, parse_date(fields.get("Date")))
            fields["Sales Rep"] = found or DEFAULT_SALES_REP
    elif blank_sales_rep(fields.get("Sales Rep")):
        fields["Sales Rep"] = DEFAULT_SALES_REP
    return fields
