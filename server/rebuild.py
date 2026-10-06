"""Rebuild unique keys after mapper unique_key changes."""

from server.keys import RowFail, build_uk
from server.settings import EVENT_TYPES


def rebuild_type(store, type_name, mapper):
    rows = store.rows_of_type(type_name)
    unique_key = mapper.get("unique_key") or []
    extra_types = mapper.get("extra_types") or {}
    by_uk = {}
    failed = 0
    for row in rows:
        fields = row.get("fields") or {}
        try:
            uk = build_uk(fields, unique_key, extra_types)
        except RowFail:
            failed += 1
            continue
        row = dict(row)
        row["uk"] = uk
        existing = by_uk.get(uk)
        if existing is None:
            by_uk[uk] = row
            continue
        if type_name in EVENT_TYPES:
            if str(row.get("source_upload_id") or "") < str(existing.get("source_upload_id") or ""):
                by_uk[uk] = row
        else:
            # snapshots keep latest upload id (string compare of ObjectId is weak; prefer created order)
            by_uk[uk] = row
    docs = []
    for uk, row in by_uk.items():
        doc = {
            "type": type_name,
            "uk": uk,
            "source_upload_id": row.get("source_upload_id"),
            "fields": row.get("fields") or {},
        }
        if "Date" in (row.get("fields") or {}):
            doc["Date"] = row["fields"].get("Date")
        docs.append(doc)
    store.replace_type_rows(type_name, docs)
    return {"kept": len(docs), "failed_row": failed, "dropped": max(0, len(rows) - len(docs) - failed)}
