"""Build engine Table objects from mapped Mongo rows. Dates → noon IST."""

from datetime import datetime

from vay.config import REQUIRED_COLUMNS
from vay.dates import normalize_date, parse_date
from vay.table import Table


def _cell(value):
    if hasattr(value, "year") and hasattr(value, "month"):
        parsed = parse_date(value)
        return parsed or value
    parsed = parse_date(value)
    if parsed:
        return parsed
    return value


def tables_from_store(store, type_names):
    tables = {}
    for type_name in type_names:
        rows_docs = store.rows_of_type(type_name)
        required = list(REQUIRED_COLUMNS.get(type_name) or [])
        extra = []
        for doc in rows_docs:
            for key in (doc.get("fields") or {}):
                if key not in required and key not in extra:
                    extra.append(key)
        if type_name == "arr" and "Days" not in required:
            if any("Days" in (d.get("fields") or {}) for d in rows_docs):
                extra = ["Days"] + [e for e in extra if e != "Days"]
        headers = required + extra
        rows = []
        for doc in rows_docs:
            fields = doc.get("fields") or {}
            row = []
            for h in headers:
                val = fields.get(h, "")
                if h == "Date":
                    val = _cell(val)
                row.append(val)
            rows.append(row)
        if rows_docs:
            tables[type_name] = Table(type_name, headers, rows)
    return tables
