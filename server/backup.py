"""Organization snapshot backup and restore.

Desktop operators also copy the MongoDB data directory. This snapshot is the
tested restore of one organization's imported rows onto a clean store.
"""

from __future__ import annotations

import json
from datetime import datetime

from server.tenant import DEFAULT_ORG, current_org_id


def snapshot_org(store):
    rows = []
    for row in store.list_rows() or []:
        rows.append({
            "type": row.get("type"),
            "uk": row.get("uk"),
            "source_upload_id": row.get("source_upload_id") or "",
            "fields": dict(row.get("fields") or {}),
            "org_id": row.get("org_id") or DEFAULT_ORG,
        })
    return {
        "org_id": current_org_id() or DEFAULT_ORG,
        "taken_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "rows": rows,
    }


def dumps_snapshot(store):
    return json.dumps(snapshot_org(store), default=str)


def restore_org(store, payload):
    """Replace the current organization's rows with the snapshot. Other orgs stay."""
    if isinstance(payload, (bytes, str)):
        payload = json.loads(payload)
    types = sorted({row.get("type") for row in (payload or {}).get("rows") or [] if row.get("type")})
    existing_types = sorted({row.get("type") for row in (store.list_rows() or []) if row.get("type")})
    for type_name in set(types) | set(existing_types):
        store.delete_rows_of_type(type_name)
    restored = 0
    for row in (payload or {}).get("rows") or []:
        if not row.get("type") or not row.get("uk"):
            continue
        store.upsert_row({
            "type": row["type"],
            "uk": row["uk"],
            "source_upload_id": row.get("source_upload_id") or "",
            "fields": dict(row.get("fields") or {}),
        })
        restored += 1
    return {"restored": restored, "org_id": current_org_id() or DEFAULT_ORG}
