"""Composed metrics over the governed catalog. No free-form formulas."""

from __future__ import annotations

import json
import uuid

from vay.domain import METRIC_IDS

METRIC_TYPE = "custom_metric"


def _fields(doc):
    return dict((doc or {}).get("fields") or {})


def _public(doc):
    fields = _fields(doc)
    try:
        deps = json.loads(fields.get("dependencies") or "[]")
    except (TypeError, ValueError):
        deps = []
    return {
        "id": doc.get("uk") or "",
        "name": fields.get("name") or "",
        "metric_ids": deps,
        "dependencies": deps,
        "owner": fields.get("owner") or "",
        "status": fields.get("status") or "draft",
        "version": int(fields.get("version") or 1),
    }


def compose(metric_ids):
    found = []
    for mid in metric_ids or []:
        mid = str(mid or "").strip()
        if not mid:
            continue
        if mid not in METRIC_IDS:
            raise ValueError("Unknown metric %s" % mid)
        if mid not in found:
            found.append(mid)
    if not found:
        raise ValueError("A composed metric needs a governed metric")
    return found


def list_metrics(store):
    rows = [_public(doc) for doc in store.rows_of_type(METRIC_TYPE) or []]
    rows.sort(key=lambda row: (row.get("name") or "").lower())
    return rows


def create_metric(store, body, username):
    deps = compose((body or {}).get("metric_ids"))
    name = str((body or {}).get("name") or "").strip()
    if not name:
        raise ValueError("name is required")
    uk = uuid.uuid4().hex
    store.upsert_row({
        "type": METRIC_TYPE,
        "uk": uk,
        "source_upload_id": "",
        "fields": {
            "name": name,
            "dependencies": json.dumps(deps),
            "owner": username or "",
            "status": "draft",
            "version": "1",
        },
    })
    return _public(store.find_row(METRIC_TYPE, uk))


def update_metric(store, metric_id, body):
    doc = store.find_row(METRIC_TYPE, metric_id)
    if not doc:
        return None
    fields = _fields(doc)
    if (body or {}).get("metric_ids") is not None:
        deps = compose(body.get("metric_ids"))
        fields["dependencies"] = json.dumps(deps)
    if (body or {}).get("name"):
        fields["name"] = str(body.get("name")).strip()
    fields["version"] = str(int(fields.get("version") or 1) + 1)
    fields["status"] = "draft"
    store.upsert_row({
        "type": METRIC_TYPE,
        "uk": metric_id,
        "source_upload_id": "",
        "fields": fields,
    })
    return _public(store.find_row(METRIC_TYPE, metric_id))


def approve_metric(store, metric_id):
    doc = store.find_row(METRIC_TYPE, metric_id)
    if not doc:
        return None
    fields = _fields(doc)
    compose(json.loads(fields.get("dependencies") or "[]"))
    fields["status"] = "approved"
    store.upsert_row({
        "type": METRIC_TYPE,
        "uk": metric_id,
        "source_upload_id": "",
        "fields": fields,
    })
    return _public(store.find_row(METRIC_TYPE, metric_id))
