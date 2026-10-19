"""Persist Today's work. Create reports prepares it once a day; a refresh prepares it again."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime

from vay.dates import today_ist

from server.explain import can_see_source, mixed_coverage
from server.org_policy import SETTING_TYPE, get_org_policy
from server.worklist import (
    EMPTY_REPS_MESSAGE,
    ORDER_RULE,
    _KIND_RANK,
    _allowed,
    _due_status,
    _key,
    _staff_options,
)

WORK_TASK_TYPE = "work_task"
SYNC_UK = "work_sync"
_SEE_ALL = (
    "sales.view",
    "credit_note.view",
    "receipt.view",
    "arr.view",
    "items.view",
    "stock.view",
    "reports.view.performance",
    "reports.view.items",
    "reports.view.followup",
    "reports.view.scorecard",
    "reports.manage",
)
_sync_lock = threading.Lock()


def _now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _today(store):
    policy = get_org_policy(store)
    return today_ist(policy.get("timezone")).strftime("%Y-%m-%d")


def _latest_report_date(store):
    for run in store.list_runs() or []:
        if run.get("status") == "succeeded":
            return str(run.get("report_date") or "")[:10]
    return ""


def _load_state(store):
    doc = store.find_row(SETTING_TYPE, SYNC_UK) or {}
    fields = dict(doc.get("fields") or {})
    try:
        created = int(fields.get("created") or 0)
    except (TypeError, ValueError):
        created = 0
    try:
        updated = int(fields.get("updated") or 0)
    except (TypeError, ValueError):
        updated = 0
    raw = fields.get("owner_outcomes") or "[]"
    try:
        outcomes = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except (TypeError, ValueError):
        outcomes = []
    return {
        "synced_on": str(fields.get("synced_on") or "")[:10],
        "status": fields.get("status") or "",
        "created": created,
        "updated": updated,
        "message": fields.get("message") or "",
        "as_of": str(fields.get("as_of") or "")[:10],
        "order_rule": fields.get("order_rule") or ORDER_RULE,
        "owner_outcomes": outcomes if isinstance(outcomes, list) else [],
        "run_id": fields.get("run_id") or "",
    }


def _save_state(store, state):
    store.upsert_row({
        "type": SETTING_TYPE,
        "uk": SYNC_UK,
        "source_upload_id": "",
        "fields": {
            "synced_on": state.get("synced_on") or "",
            "status": state.get("status") or "",
            "created": int(state.get("created") or 0),
            "updated": int(state.get("updated") or 0),
            "message": state.get("message") or "",
            "as_of": state.get("as_of") or "",
            "order_rule": state.get("order_rule") or ORDER_RULE,
            "owner_outcomes": json.dumps(state.get("owner_outcomes") or []),
            "run_id": state.get("run_id") or "",
        },
    })


def list_work_tasks(store):
    rows = []
    for doc in store.rows_of_type(WORK_TASK_TYPE) or []:
        fields = dict(doc.get("fields") or {})
        fields["id"] = doc.get("uk") or ""
        rows.append(fields)
    return rows


def _task_key(row):
    return str((row or {}).get("task_key") or (row or {}).get("id") or "")


def _copy_row(row, today, current):
    payload = json.loads(json.dumps(row, default=str))
    payload["task_key"] = str(payload.pop("id", "") or "")
    payload.pop("subject", None)
    payload["last_seen"] = today
    payload["updated_at"] = _now()
    payload["created_at"] = (current or {}).get("created_at") or _now()
    payload["status"] = "open"
    payload.pop("closed_on", None)
    return payload


def _upsert_tasks(store, rows, today):
    open_by_key = {}
    closed_today = set()
    for task in list_work_tasks(store):
        key = _task_key(task)
        if not key:
            continue
        if task.get("status") == "open":
            open_by_key[key] = task
        elif task.get("status") in ("done", "dropped") and str(task.get("closed_on") or "")[:10] == today:
            closed_today.add(key)
    created = 0
    updated = 0
    seen = set()
    for row in rows or []:
        key = _task_key(row)
        if not key or key in seen:
            continue
        seen.add(key)
        current = open_by_key.get(key)
        if current:
            fields = _copy_row(row, today, current)
            store.upsert_row({
                "type": WORK_TASK_TYPE,
                "uk": current.get("id") or "",
                "source_upload_id": "",
                "fields": fields,
            })
            updated += 1
            continue
        if key in closed_today:
            continue
        fields = _copy_row(row, today, None)
        store.upsert_row({
            "type": WORK_TASK_TYPE,
            "uk": uuid.uuid4().hex,
            "source_upload_id": "",
            "fields": fields,
        })
        created += 1
    return created, updated


def _all_scope():
    return {
        "reps": None,
        "mode": "all",
        "staff": "",
        "username": "",
        "can_pick_staff": True,
        "message": "",
    }


def sync_work_tasks(store, report_date="", force=False, run_id="", today=""):
    """Write today's queue. An open task with the same kind and subject is updated."""
    today = str(today or _today(store))[:10]
    with _sync_lock:
        state = _load_state(store)
        if (
            not force
            and state.get("synced_on") == today
            and state.get("status") == "succeeded"
        ):
            skipped = dict(state)
            skipped["skipped"] = True
            skipped["status"] = "skipped"
            return skipped
        _save_state(store, {
            **state,
            "status": "running",
            "message": "",
            "run_id": run_id or state.get("run_id") or "",
        })
        try:
            from server.explain import annotate_today
            from server.worklist import build_worklist

            if not report_date:
                report_date = _latest_report_date(store)
            payload = build_worklist(store, _all_scope(), report_date)
            payload = annotate_today(store, payload, list(_SEE_ALL))
            created, updated = _upsert_tasks(store, payload.get("rows") or [], today)
            result = {
                "synced_on": today,
                "status": "succeeded",
                "created": created,
                "updated": updated,
                "message": "",
                "as_of": payload.get("as_of") or today,
                "order_rule": payload.get("order_rule") or ORDER_RULE,
                "owner_outcomes": payload.get("owner_outcomes") or [],
                "run_id": run_id or "",
                "skipped": False,
            }
            _save_state(store, result)
            return result
        except Exception as exc:
            failed = {
                "synced_on": state.get("synced_on") or "",
                "status": "failed",
                "created": 0,
                "updated": 0,
                "message": str(exc),
                "as_of": state.get("as_of") or "",
                "order_rule": state.get("order_rule") or ORDER_RULE,
                "owner_outcomes": state.get("owner_outcomes") or [],
                "run_id": run_id or "",
                "skipped": False,
            }
            _save_state(store, failed)
            raise


def sync_after_report(store, run_id, report_date):
    """Prepare Today's work after a report succeeds. A later report the same day does not repeat it."""
    try:
        result = sync_work_tasks(store, report_date, force=False, run_id=run_id)
    except Exception as exc:
        store.update_run(run_id, {
            "worklist_status": "failed",
            "worklist_created": 0,
            "worklist_updated": 0,
            "worklist_message": "Today's work could not be prepared.",
            "worklist_skipped": False,
        })
        raise exc
    skipped = bool(result.get("skipped"))
    store.update_run(run_id, {
        "worklist_status": "skipped" if skipped else (result.get("status") or "succeeded"),
        "worklist_created": int(result.get("created") or 0),
        "worklist_updated": int(result.get("updated") or 0),
        "worklist_message": result.get("message") or "",
        "worklist_skipped": skipped,
    })
    return result


def present_task(fields, perms):
    row = dict(fields or {})
    parts = row.pop("coverage_parts", None) or []
    tuple_parts = [
        (part.get("label") or "", part.get("date") or "", part.get("type") or "")
        for part in parts
        if isinstance(part, dict)
    ]
    visible = [part for part in tuple_parts if part[1] and can_see_source(perms, part[2])]
    mixed, note = mixed_coverage(visible)
    basis = dict(row.get("basis") or {})
    sources = [
        source for source in (basis.get("sources") or [])
        if can_see_source(perms, source.get("type"))
    ]
    through = ""
    for source in sources:
        day = source.get("coverage_through") or source.get("effective_date") or ""
        if day > through:
            through = day
    if parts:
        basis["mixed_coverage"] = mixed
        basis["coverage_note"] = note
        basis["coverage_through"] = through
    basis["sources"] = sources
    row["basis"] = basis
    explanation = dict(row.get("explanation") or {})
    explanation["sources"] = sources
    if parts:
        explanation["mixed_coverage"] = mixed
        explanation["coverage_note"] = note
    row["explanation"] = explanation
    return row


def _stock_visible(scope, task):
    if scope.get("reps") is None:
        return True
    if not scope.get("reps"):
        return False
    if scope.get("mode") in ("self", "staff"):
        limit = scope.get("username") or ""
        return bool(limit) and (task.get("owner") or "") == limit
    return True


def _visible(scope, task):
    if (task or {}).get("kind") == "stock":
        return _stock_visible(scope, task)
    return _allowed(scope, (task or {}).get("salesperson") or "")


def _ordered(rows):
    def key(row):
        credit = 0 if row.get("block") == "credit" else 1
        return (
            credit,
            _KIND_RANK.get(row.get("kind"), 9),
            -int(row.get("age") or 0),
            _key(row.get("customer")),
        )
    rows.sort(key=key)
    return rows


def load_worklist(store, scope, kind="", due="", perms=None):
    scope = scope or {}
    state = _load_state(store)
    if scope.get("reps") == []:
        return {
            "as_of": state.get("as_of") or "",
            "synced_on": state.get("synced_on") or "",
            "order_rule": state.get("order_rule") or ORDER_RULE,
            "message": scope.get("message") or EMPTY_REPS_MESSAGE,
            "rows": [],
            "owner_outcomes": [],
            "can_pick_staff": bool(scope.get("can_pick_staff")),
            "staff": scope.get("staff") or "",
            "staff_options": _staff_options(store) if scope.get("can_pick_staff") else [],
        }
    today = state.get("as_of") or state.get("synced_on") or ""
    rows = []
    for task in list_work_tasks(store):
        if task.get("status") != "open":
            continue
        if not _visible(scope, task):
            continue
        if kind and task.get("kind") != kind:
            continue
        if due and not _due_status(task, today, due):
            continue
        rows.append(present_task(task, perms or []))
    _ordered(rows)
    message = scope.get("message") or ""
    if not state.get("synced_on") and not rows:
        message = "Create reports to prepare today's work."
    return {
        "as_of": state.get("as_of") or "",
        "synced_on": state.get("synced_on") or "",
        "order_rule": state.get("order_rule") or ORDER_RULE,
        "message": message,
        "rows": rows,
        "owner_outcomes": state.get("owner_outcomes") or [],
        "can_pick_staff": bool(scope.get("can_pick_staff")),
        "staff": scope.get("staff") or "",
        "staff_options": _staff_options(store) if scope.get("can_pick_staff") else [],
    }


def set_work_task_status(store, task_id, status, today=""):
    status = (status or "").strip()
    if status not in ("open", "done", "dropped"):
        raise ValueError("status must be open, done, or dropped")
    today = str(today or _today(store))[:10]
    for doc in store.rows_of_type(WORK_TASK_TYPE) or []:
        if (doc.get("uk") or "") != task_id:
            continue
        fields = dict(doc.get("fields") or {})
        fields["status"] = status
        if status in ("done", "dropped"):
            fields["closed_on"] = today
        else:
            fields.pop("closed_on", None)
        fields["updated_at"] = _now()
        store.upsert_row({
            "type": WORK_TASK_TYPE,
            "uk": task_id,
            "source_upload_id": doc.get("source_upload_id") or "",
            "fields": fields,
        })
        fields["id"] = task_id
        return fields
    raise ValueError("Task not found")
