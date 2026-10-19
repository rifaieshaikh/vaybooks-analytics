"""Weekly review reads the suggestions saved with a report, and reuses results until the books change."""

from __future__ import annotations

import hashlib
import json

from vay.dates import today_ist

_FINGERPRINT_TYPES = (
    "sales",
    "receipt",
    "stock",
    "item_hold",
    "action",
    "collection_contact",
    "collection_promise",
    "collection_allocation",
    "collection_target",
)


def _json(value):
    return json.loads(json.dumps(value, default=str))


def review_fingerprint(store):
    parts = []
    for type_name in _FINGERPRINT_TYPES:
        bits = []
        for doc in store.rows_of_type(type_name) or []:
            fields = doc.get("fields") or {}
            bits.append("|".join((
                str(doc.get("uk") or ""),
                str(fields.get("Date") or ""),
                str(fields.get("Amount") or fields.get("Net Amount") or fields.get("Qty") or ""),
                str(fields.get("status") or ""),
                str(fields.get("assigned_at") or ""),
                str(fields.get("done_at") or ""),
                str(fields.get("updated_at") or ""),
                str(fields.get("Min Hold") or ""),
                str(fields.get("remaining") or ""),
                str(fields.get("payment_status") or ""),
            )))
        bits.sort()
        parts.append(type_name + "\n" + "\n".join(bits))
    uploads = []
    for item in store.list_uploads() or []:
        if item.get("dry_run"):
            continue
        if (item.get("type") or "") not in ("sales", "receipt", "stock"):
            continue
        uploads.append("%s:%s" % (item.get("_id") or "", item.get("finished_at") or item.get("created_at") or ""))
    uploads.sort()
    parts.append("uploads\n" + "\n".join(uploads))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def save_review_suggestions(store, run_id, bundle):
    """Keep the four ideas from the bundle Create reports just built."""
    from server.actions import suggestions
    from server.org_policy import get_org_policy

    ideas = suggestions(bundle, (get_org_policy(store) or {}).get("thresholds") or {})
    quality = [
        row.get("message") or ""
        for row in ((bundle or {}).get("quality") or {}).get("rows") or []
        if isinstance(row, dict)
    ]
    store.update_run(run_id, {
        "review_suggestions": _json(ideas),
        "review_quality_messages": quality,
    })
    return ideas


def ensure_review_suggestions(store, run):
    """Use the saved ideas. An older report is filled in once."""
    if "review_suggestions" in (run or {}):
        return list(run.get("review_suggestions") or []), list(run.get("review_quality_messages") or [])
    from server.phase2 import build_bundle, open_review_count

    report_date = str((run or {}).get("report_date") or "")[:10]
    exceptions = (((run or {}).get("manifest") or {}).get("reconciliation") or {}).get("exceptions") or []
    bundle = build_bundle(store, report_date, exceptions=exceptions, review_count=open_review_count(store))
    ideas = save_review_suggestions(store, str(run.get("_id") or run.get("id") or ""), bundle)
    quality = [
        row.get("message") or ""
        for row in ((bundle or {}).get("quality") or {}).get("rows") or []
        if isinstance(row, dict)
    ]
    return ideas, quality


def compute_review_material(store, report_date, quality_messages):
    from server.actions import _rep_map, _sales_after_contact, attach_outcomes, list_action_rows
    from server.collection import TARGET_TYPE, _bundle, _rows
    from server.org_policy import get_org_policy

    actions = attach_outcomes(
        store,
        list_action_rows(store),
        list(quality_messages or []),
        report_date=report_date,
    )
    as_of = today_ist(get_org_policy(store).get("timezone")).strftime("%Y-%m-%d")
    _today, contacts, promises, _disputes = _bundle(store, as_of)
    return {
        "actions": actions,
        "reps": _rep_map(store),
        "contacts": contacts,
        "promises": promises,
        "targets": _rows(store, TARGET_TYPE),
        "recovery": _sales_after_contact(store, contacts),
        "as_of": as_of,
    }


def review_material(store, run, report_date, quality_messages, force=False):
    """Return outcome facts for this report. Recompute when the books or a refresh ask for it."""
    run_id = str((run or {}).get("_id") or (run or {}).get("id") or "")
    cache = (run or {}).get("review_cache") or {}
    current = review_fingerprint(store)
    if not force and cache.get("fingerprint") == current and isinstance(cache.get("actions"), list):
        return cache
    material = compute_review_material(store, report_date, quality_messages)
    material["fingerprint"] = review_fingerprint(store)
    stored = _json(material)
    if run_id:
        store.update_run(run_id, {"review_cache": stored})
    return stored
