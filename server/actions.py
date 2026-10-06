"""Assignable actions and their outcomes. Saving an action does not change source rows."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from vay.dates import clean_text, number_, parse_date
from vay.phase3 import data_fix_outcome, purchase_outcome, received_since, recovery_outcome

ACTION_TYPE = "action"
KINDS = ("collection", "recovery", "purchase", "data_fix")
STATUSES = ("open", "done", "dropped")


def _now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _fields(row):
    return dict((row or {}).get("fields") or {})


def list_action_rows(store):
    rows = []
    for doc in store.rows_of_type(ACTION_TYPE) or []:
        fields = _fields(doc)
        fields["id"] = doc.get("uk") or ""
        rows.append(fields)
    rows.sort(key=lambda row: row.get("assigned_at") or "", reverse=True)
    return rows


def _owners(store):
    names = []
    for doc in store.list_users() or []:
        if doc.get("enabled", True) and doc.get("username"):
            names.append(doc["username"])
    return sorted(names, key=str.lower)


def create_action(store, body, username):
    kind = (body.get("action_type") or "").strip()
    if kind not in KINDS:
        raise ValueError("action_type must be collection, recovery, purchase, or data_fix")
    owner = (body.get("owner") or username or "").strip()
    if not owner or owner not in _owners(store):
        raise ValueError("Owner is not a user in this install")
    due = str(body.get("due_date") or "")[:10]
    if not due:
        raise ValueError("due_date is required")
    proposal = clean_text(body.get("proposal"))
    if not proposal:
        raise ValueError("proposal is required")
    uk = uuid.uuid4().hex
    amount = body.get("amount")
    try:
        amount = None if amount in ("", None) else round(float(amount), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError("amount must be a number") from exc
    fields = {
        "action_type": kind,
        "subject_name": clean_text(body.get("subject_name")),
        "subject_kind": clean_text(body.get("subject_kind")) or "customer",
        "proposal": proposal,
        "owner": owner,
        "due_date": due,
        "status": "open",
        "amount": amount,
        "assigned_at": str(body.get("assigned_at") or _now()),
        "report_date": str(body.get("report_date") or "")[:10],
        "quality_message": clean_text(body.get("quality_message")),
        "was_inactive": bool(body.get("was_inactive")),
        "created_by": username or "",
    }
    store.upsert_row({
        "type": ACTION_TYPE,
        "uk": uk,
        "source_upload_id": "",
        "fields": fields,
    })
    fields["id"] = uk
    return fields


def set_status(store, action_id, status):
    status = (status or "").strip()
    if status not in STATUSES:
        raise ValueError("status must be open, done, or dropped")
    for doc in store.rows_of_type(ACTION_TYPE) or []:
        if (doc.get("uk") or "") != action_id:
            continue
        fields = _fields(doc)
        fields["status"] = status
        if status == "done":
            fields["done_at"] = _now()
        store.upsert_row({
            "type": ACTION_TYPE,
            "uk": action_id,
            "source_upload_id": doc.get("source_upload_id") or "",
            "fields": fields,
        })
        fields["id"] = action_id
        return fields
    raise ValueError("Action not found")


def _dated(store, type_name, name_keys, amount_key):
    rows = []
    for doc in store.rows_of_type(type_name) or []:
        fields = doc.get("fields") or {}
        name = ""
        for key in name_keys:
            name = clean_text(fields.get(key))
            if name:
                break
        when = parse_date(fields.get("Date"))
        rows.append({
            "name": name,
            "date": when.strftime("%Y-%m-%d") if when else "",
            "amount": number_(fields.get(amount_key)),
        })
    return rows


def _later_report(store, assigned_at):
    assigned = str(assigned_at or "")[:10]
    for run in store.list_runs() or []:
        if run.get("status") != "succeeded":
            continue
        if str(run.get("report_date") or "")[:10] > assigned:
            return True
    return False


def _later_stock_file(store, assigned_at):
    assigned = str(assigned_at or "")[:10]
    for doc in store.rows_of_type("stock") or []:
        uid = str(doc.get("source_upload_id") or "")
        if not uid:
            continue
        upload = store.get_upload(uid) if hasattr(store, "get_upload") else None
        created = (upload or {}).get("created_at")
        text = created.strftime("%Y-%m-%d") if hasattr(created, "strftime") else str(created or "")[:10]
        if text and assigned and text > assigned:
            return True
    return False


def _on_hand(store, name):
    total = 0.0
    found = False
    slow = False
    key = (name or "").strip().lower()
    for doc in store.rows_of_type("stock") or []:
        fields = doc.get("fields") or {}
        if clean_text(fields.get("Item Name")).lower() != key:
            continue
        found = True
        total += number_(fields.get("Qty"))
    return total, found, slow


def _stock_index(store, report_date):
    from server.phase2 import stock_headline
    from vay.dates import today_ist
    when = report_date or today_ist().strftime("%Y-%m-%d")
    try:
        headline = stock_headline(store, when)
    except (TypeError, ValueError):
        return {}
    return {str(row.get("name") or "").strip().lower(): row for row in headline.get("rows") or []}


def attach_outcomes(store, actions, quality_messages=None, report_date=None):
    receipts = _dated(store, "receipt", ("Account Name", "Party Name"), "Amount")
    sales = _dated(store, "sales", ("Party Name", "Account Name"), "Net Amount")
    messages = list(quality_messages or [])
    stock = _stock_index(store, report_date) if any((a or {}).get("action_type") == "purchase" for a in actions or []) else {}
    out = []
    for action in actions or []:
        row = dict(action)
        kind = row.get("action_type")
        assigned = row.get("assigned_at") or ""
        name = row.get("subject_name") or ""
        if kind == "collection":
            row["outcome"] = received_since(receipts, name, assigned, row.get("amount"))
        elif kind == "recovery":
            row["outcome"] = recovery_outcome(sales, name, assigned)
        elif kind == "purchase":
            item = stock.get(name.strip().lower()) or {}
            on_hand = item.get("on_hand")
            if on_hand is None:
                on_hand, _found, _slow = _on_hand(store, name)
            row["outcome"] = purchase_outcome(
                on_hand, row.get("amount"), bool(item.get("slow")), _later_stock_file(store, assigned),
            )
        elif kind == "data_fix":
            row["outcome"] = data_fix_outcome(row.get("quality_message"), messages, _later_report(store, assigned))
        else:
            row["outcome"] = {"label": ""}
        out.append(row)
    return out


def suggestions(bundle, thresholds=None):
    """Proposed actions from the Phase 2 lists. Nothing is saved until the user confirms."""
    thresholds = thresholds or {}
    cover_limit = thresholds.get("cover_days")
    overdue_limit = thresholds.get("overdue_amount")
    change = (bundle or {}).get("sales_change") or {}
    customers = change.get("customers") or []
    top = customers[0] if customers else None
    collection = ((bundle or {}).get("collection") or {}).get("rows") or []
    first_collection = collection[0] if collection else None
    if overdue_limit not in ("", None) and first_collection:
        if float(first_collection.get("overdue_30") or 0) < float(overdue_limit):
            first_collection = None
    stock_rows = ((bundle or {}).get("stock") or {}).get("rows") or []
    short = None
    limit = float(cover_limit) if cover_limit not in ("", None) else 30.0
    for row in stock_rows:
        days = row.get("cover_days")
        if days is None:
            continue
        if float(days) <= limit:
            short = row
            break
    movement = {row.get("name"): row for row in ((bundle or {}).get("customer_movement") or {}).get("rows") or []}
    quality = ((bundle or {}).get("quality") or {}).get("rows") or []
    ideas = []
    if top:
        inactive = (movement.get(top.get("name")) or {}).get("movement") == "inactive"
        ideas.append({
            "action_type": "recovery",
            "subject_kind": "customer",
            "subject_name": top.get("name") or "",
            "proposal": "Review the sales change for %s" % (top.get("name") or ""),
            "amount": top.get("change"),
            "was_inactive": inactive,
            "reason": "Largest sales change",
        })
    if first_collection:
        ideas.append({
            "action_type": "collection",
            "subject_kind": "customer",
            "subject_name": first_collection.get("name") or "",
            "proposal": "Collect from %s" % (first_collection.get("name") or ""),
            "amount": first_collection.get("balance"),
            "reason": "First collection",
        })
    if short:
        ideas.append({
            "action_type": "purchase",
            "subject_kind": "item",
            "subject_name": short.get("name") or "",
            "proposal": "Reorder %s" % (short.get("name") or ""),
            "amount": short.get("on_hand"),
            "reason": "Short stock cover",
        })
    if quality:
        row = quality[0]
        ideas.append({
            "action_type": "data_fix",
            "subject_kind": "quality",
            "subject_name": row.get("message") or "",
            "proposal": row.get("fix") or "Correct the source file",
            "quality_message": row.get("message") or "",
            "reason": "Data quality",
        })
    return ideas


def default_due(report_date, days=7):
    parsed = parse_date(report_date)
    if not parsed:
        parsed = datetime.utcnow()
    return (parsed + timedelta(days=days)).strftime("%Y-%m-%d")
