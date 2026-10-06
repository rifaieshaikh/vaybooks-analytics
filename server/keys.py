"""Scalar unique keys using vay.dates parsers. Never store uk as a list."""

from vay.config import REQUIRED_COLUMNS
from vay.dates import clean_text, number_, parse_date

from server.settings import AMOUNT_FIELDS, DATE_FIELDS, UK_SEP

CANONICAL_ALL = set()
for cols in REQUIRED_COLUMNS.values():
    CANONICAL_ALL.update(cols)
CANONICAL_ALL.add("Days")


class RowFail(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def field_kind(name, extra_types=None):
    extra_types = extra_types or {}
    if name in extra_types:
        return extra_types[name]
    if name in DATE_FIELDS:
        return "date"
    if name in AMOUNT_FIELDS:
        return "number"
    return "text"


def part_value(name, raw, extra_types=None):
    kind = field_kind(name, extra_types)
    if kind == "date":
        parsed = parse_date(raw)
        if not parsed:
            raise RowFail("Unreadable date in unique key field %s" % name)
        return parsed.strftime("%Y-%m-%d")
    if kind == "number":
        return "{:.4f}".format(number_(raw))
    return clean_text(raw)


def build_uk(fields, unique_key, extra_types=None):
    if not unique_key:
        raise RowFail("unique_key is empty")
    parts = []
    for name in unique_key:
        parts.append(part_value(name, fields.get(name), extra_types))
    return UK_SEP.join(parts)
