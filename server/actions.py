"""Assignable actions and their outcomes. Saving an action does not change source rows."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta

from server.collection import (
    ALLOCATION_TYPE,
    PENDING_MESSAGE,
    PROMISE_TYPE,
    _basis_label,
    _bundle,
    _key,
    _load_sources,
    _rows,
    attach_collection_summaries,
)
from server.org_policy import SETTING_TYPE
from vay.dates import clean_text, number_, parse_date, today_ist
from vay.phase3 import data_fix_outcome, received_since, recovery_outcome

REVIEW_OPENS_UK = "review_opens"
SALE_PENDING = "Sale confirmation is pending a refresh."

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


def _assigned_day(value):
    return str(value or "")[:10]


def _later_than(day, assigned):
    return bool(day and assigned and day > assigned)


def _cap_amount(total, cap):
    total = round(float(total or 0), 2)
    if cap in ("", None):
        return total
    return round(min(total, number_(cap)), 2)


def _open_collections(actions):
    rows = [
        row for row in actions or []
        if row.get("action_type") == "collection" and row.get("status") == "open"
    ]
    rows.sort(key=lambda row: (row.get("due_date") or "9999-99-99", row.get("assigned_at") or "", row.get("id") or ""))
    return rows


def _oldest_open(actions, customer):
    key = _key(customer)
    for row in _open_collections(actions):
        if _key(row.get("subject_name")) == key:
            return row
    return None


def _collection_outcomes(store, actions):
    """Each receipt counts on one open collection task. A single task stays capped."""
    sources = _load_sources(store)
    by_source = {(row.get("source_type"), row.get("uk")): row for row in sources if row.get("uk")}
    promises = {row.get("id"): row for row in _rows(store, PROMISE_TYPE)}
    open_ids = {row.get("id") for row in _open_collections(actions)}
    verified = {row.get("id"): [] for row in actions or []}
    observed = {row.get("id"): [] for row in actions or []}
    used = {}
    for alloc in _rows(store, ALLOCATION_TYPE):
        if alloc.get("voided_at") or alloc.get("basis") not in ("source_confirmed", "confirmed_inferred"):
            continue
        promise = promises.get(alloc.get("promise_id")) or {}
        customer = promise.get("customer_name") or ""
        target = None
        linked = promise.get("action_id") or ""
        if linked in open_ids:
            target = next((row for row in actions or [] if row.get("id") == linked), None)
        if target is None:
            target = _oldest_open(actions, customer)
        if target is None:
            continue
        source = by_source.get((alloc.get("source_type") or "", alloc.get("source_uk") or "")) or {}
        amount = round(float(alloc.get("amount") or 0), 2)
        if amount <= 0:
            continue
        token = (alloc.get("source_type") or "", alloc.get("source_uk") or "")
        used[token] = round(used.get(token, 0.0) + amount, 2)
        verified[target.get("id")].append({
            "kind": "allocated",
            "amount": amount,
            "date": source.get("date") or "",
            "basis": alloc.get("basis") or "",
            "basis_label": _basis_label(alloc),
            "source_uk": alloc.get("source_uk") or "",
            "source_type": alloc.get("source_type") or "",
        })
    for source in sources:
        token = (source.get("source_type") or "", source.get("uk") or "")
        remainder = round(float(source.get("amount") or 0) - used.get(token, 0.0), 2)
        if remainder <= 0.009:
            continue
        target = _oldest_open(actions, source.get("name"))
        if target is None:
            continue
        if not _later_than(source.get("date") or "", _assigned_day(target.get("assigned_at"))):
            continue
        observed[target.get("id")].append({
            "kind": "observed",
            "label": "Received since assigned",
            "amount": remainder,
            "date": source.get("date") or "",
            "source_uk": source.get("uk") or "",
            "source_type": source.get("source_type") or "",
        })
    later_customers = set()
    for source in sources:
        if source.get("date"):
            later_customers.add((_key(source.get("name")), source.get("date")))
    out = {}
    for action in _open_collections(actions):
        action_id = action.get("id")
        verified_rows = verified.get(action_id) or []
        observed_rows = observed.get(action_id) or []
        verified_amount = round(sum(row["amount"] for row in verified_rows), 2)
        observed_amount = _cap_amount(sum(row["amount"] for row in observed_rows), action.get("amount"))
        assigned = _assigned_day(action.get("assigned_at"))
        has_later = any(day > assigned for key, day in later_customers if key == _key(action.get("subject_name")))
        evidence = verified_rows + observed_rows
        dates = [row.get("date") or "" for row in evidence if row.get("date")]
        pending = not has_later and verified_amount <= 0 and observed_amount <= 0
        if pending:
            label = PENDING_MESSAGE
            amount = None
        elif observed_amount > 0:
            label = "Received since assigned"
            amount = observed_amount
        elif verified_amount > 0:
            label = "Allocated"
            amount = verified_amount
        else:
            label = "No receipts since assigned"
            amount = 0.0
        out[action_id] = {
            "label": label,
            "amount": amount,
            "verified_amount": verified_amount,
            "observed_amount": observed_amount if not pending else None,
            "evidence": evidence,
            "evidence_date": max(dates) if dates else "",
            "pending": pending,
        }
    return out


def _any_later(rows, assigned):
    assigned = _assigned_day(assigned)
    for row in rows or []:
        if _later_than(str(row.get("date") or "")[:10], assigned):
            return True
    return False


def _stock_after(store, name, assigned):
    """Latest on-hand for this item on a stock snapshot dated after assignment."""
    assigned = _assigned_day(assigned)
    key = clean_text(name).lower()
    grouped = {}
    for doc in store.rows_of_type("stock") or []:
        fields = doc.get("fields") or {}
        if clean_text(fields.get("Item Name")).lower() != key:
            continue
        eff = str(fields.get("EffectiveDate") or doc.get("effective_date") or "")[:10]
        if not _later_than(eff, assigned):
            continue
        grouped[eff] = round(grouped.get(eff, 0.0) + number_(fields.get("Qty")), 2)
    if not grouped:
        return "", None
    latest = max(grouped)
    return latest, grouped[latest]


def _item_minimum(store, name):
    from server.items360 import _hold_map, _holding_for, account_uk
    holds, default_min, default_max = _hold_map(store)
    holding = _holding_for(holds, default_min, account_uk(name), default_max)
    return float(holding.get("min_hold") or 0)


def _purchase_result(store, name, assigned):
    snap_date, on_hand = _stock_after(store, name, assigned)
    if not snap_date:
        return {
            "resolved": False,
            "label": "Waiting for the next stock file",
            "amount": None,
            "pending": True,
            "evidence_date": "",
        }
    minimum = _item_minimum(store, name)
    covered = on_hand + 1e-9 >= minimum
    return {
        "resolved": covered,
        "label": "On hand meets the minimum." if covered else "Stock risk is still open",
        "amount": on_hand,
        "minimum": minimum,
        "pending": False,
        "evidence_date": snap_date,
    }


def attach_outcomes(store, actions, quality_messages=None, report_date=None):
    sales = _dated(store, "sales", ("Party Name", "Account Name"), "Net Amount")
    receipts = _dated(store, "receipt", ("Account Name", "Party Name"), "Amount")
    messages = list(quality_messages or [])
    collection = _collection_outcomes(store, actions)
    out = []
    for action in actions or []:
        row = dict(action)
        kind = row.get("action_type")
        assigned = row.get("assigned_at") or ""
        name = row.get("subject_name") or ""
        if kind == "collection":
            row["outcome"] = collection.get(row.get("id")) or received_since(receipts, name, assigned, row.get("amount"))
        elif kind == "recovery":
            if not _any_later(sales, assigned):
                row["outcome"] = {
                    "bought_again": False,
                    "label": SALE_PENDING,
                    "amount": None,
                    "evidence_date": "",
                    "pending": True,
                }
            else:
                row["outcome"] = recovery_outcome(sales, name, assigned)
        elif kind == "purchase":
            row["outcome"] = _purchase_result(store, name, assigned)
        elif kind == "data_fix":
            row["outcome"] = data_fix_outcome(row.get("quality_message"), messages, _later_report(store, assigned))
        else:
            row["outcome"] = {"label": ""}
        out.append(row)
    return attach_collection_summaries(store, out)


def _rep_map(store):
    last = {}
    when = {}
    for doc in store.rows_of_type("sales") or []:
        fields = doc.get("fields") or {}
        name = clean_text(fields.get("Party Name") or fields.get("Account Name"))
        rep = clean_text(fields.get("Sales Rep"))
        day = str(fields.get("Date") or "")
        if not name:
            continue
        key = _key(name)
        if key not in when or day >= when[key]:
            when[key] = day
            last[key] = rep
    return last


def _customer_in_scope(scope, reps, name):
    wanted = scope.get("reps") if scope else None
    if wanted is None:
        return True
    allowed = {clean_text(item).lower() for item in wanted if clean_text(item)}
    if not allowed:
        return False
    return reps.get(_key(name), "").lower() in allowed


def _scoped_actions(actions, scope, reps):
    if not scope or scope.get("reps") is None:
        return list(actions or [])
    out = []
    for row in actions or []:
        if row.get("action_type") in ("purchase", "data_fix"):
            continue
        if _customer_in_scope(scope, reps, row.get("subject_name")):
            out.append(row)
    return out


def listed_review_opens(store, report_date):
    """Opens already recorded for this report date. Does not write."""
    report_date = str(report_date or "")[:10]
    existing = store.find_row(SETTING_TYPE, REVIEW_OPENS_UK) if hasattr(store, "find_row") else None
    fields = dict((existing or {}).get("fields") or {})
    try:
        opens = json.loads(fields.get("Opens") or "[]")
    except (TypeError, ValueError):
        opens = []
    if not isinstance(opens, list):
        opens = []
    return [item for item in opens if isinstance(item, dict) and item.get("report_date") == report_date]


def record_review_open(store, username, report_date):
    """One open per person and report date. A later open updates the time."""
    username = clean_text(username)
    report_date = str(report_date or "")[:10]
    existing = store.find_row(SETTING_TYPE, REVIEW_OPENS_UK) if hasattr(store, "find_row") else None
    fields = dict((existing or {}).get("fields") or {})
    try:
        opens = json.loads(fields.get("Opens") or "[]")
    except (TypeError, ValueError):
        opens = []
    if not isinstance(opens, list):
        opens = []
    stamp = _now()
    found = False
    for item in opens:
        if not isinstance(item, dict):
            continue
        if item.get("user") == username and item.get("report_date") == report_date:
            item["opened_at"] = stamp
            found = True
            break
    if not found and username and report_date:
        opens.append({"user": username, "report_date": report_date, "opened_at": stamp})
    fields["Opens"] = json.dumps(opens)
    store.upsert_row({
        "type": SETTING_TYPE,
        "uk": REVIEW_OPENS_UK,
        "source_upload_id": "",
        "fields": fields,
    })
    return [item for item in opens if isinstance(item, dict) and item.get("report_date") == report_date]


def _result_row(action):
    outcome = action.get("outcome") or {}
    return {
        "id": action.get("id") or "",
        "action_type": action.get("action_type") or "",
        "subject_name": action.get("subject_name") or "",
        "status": action.get("status") or "",
        "due_date": action.get("due_date") or "",
        "owner": action.get("owner") or "",
        "label": outcome.get("label") or "",
        "verified_amount": outcome.get("verified_amount"),
        "observed_amount": outcome.get("observed_amount") if "observed_amount" in outcome else outcome.get("amount"),
        "evidence_date": outcome.get("evidence_date") or "",
        "pending": bool(outcome.get("pending")),
        "basis": "live",
    }


def _results_by_owner(actions, as_of):
    buckets = {}
    for row in actions or []:
        owner = row.get("owner") or "Unassigned"
        bucket = buckets.setdefault(owner, {"owner": owner, "open": 0, "overdue": 0, "allocated": 0.0})
        if row.get("status") != "open":
            continue
        bucket["open"] += 1
        if row.get("due_date") and row["due_date"] < as_of:
            bucket["overdue"] += 1
        verified = (row.get("outcome") or {}).get("verified_amount")
        if verified:
            bucket["allocated"] = round(bucket["allocated"] + float(verified), 2)
    return [buckets[key] for key in sorted(buckets)]


def _sales_after_contact(store, contacts):
    """Customers who bought again after a recorded contact. This does not claim the contact caused the sale."""
    sales = []
    for doc in store.rows_of_type("sales") or []:
        fields = doc.get("fields") or {}
        name = clean_text(fields.get("Party Name") or fields.get("Account Name"))
        day = str(fields.get("Date") or "")[:10]
        if name and day:
            sales.append((name.lower(), name, day, fields.get("Net Amount") or fields.get("Amount"), doc.get("uk") or ""))
    found = []
    seen = set()
    for contact in contacts or []:
        name = clean_text(contact.get("customer_name"))
        when = str(contact.get("contacted_on") or "")[:10]
        if not name or not when:
            continue
        for key, label, day, amount, uk in sales:
            token = (key, uk or day)
            if key == name.lower() and day > when and token not in seen:
                seen.add(token)
                found.append({
                    "customer": label,
                    "contacted_on": when,
                    "sale_date": day,
                    "amount": amount,
                    "source_uk": uk,
                })
    return found[:20]


def build_results(store, actions, scope, report_date, run, opens):
    """Derived review summary. It does not claim an action caused a payment or a sale."""
    reps = _rep_map(store)
    scoped = _scoped_actions(actions, scope, reps)
    from server.org_policy import get_org_policy
    as_of = today_ist(get_org_policy(store).get("timezone")).strftime("%Y-%m-%d")
    _today, contacts, promises, _disputes = _bundle(store, as_of)
    open_rows = [row for row in scoped if row.get("status") == "open"]
    overdue = [row for row in open_rows if row.get("due_date") and row["due_date"] < as_of]
    promise_counts = {"kept": 0, "partial": 0, "missed": 0, "pending_refresh": 0, "open": 0}
    for row in promises:
        if not _customer_in_scope(scope, reps, row.get("customer_name")):
            continue
        status = row.get("payment_status") or ""
        if status in promise_counts:
            promise_counts[status] += 1
    contact_count = sum(1 for row in contacts if _customer_in_scope(scope, reps, row.get("customer_name")))
    review_opens = [item for item in opens or [] if item.get("user")]
    latest = ""
    for item in review_opens:
        stamp = item.get("opened_at") or ""
        if stamp > latest:
            latest = stamp
    return {
        "as_of": as_of,
        "report_date": str(report_date or "")[:10],
        "basis": "live",
        "message": (scope or {}).get("message") or "",
        "open_count": len(open_rows),
        "overdue_count": len(overdue),
        "contacts": contact_count,
        "promises": promise_counts,
        "review_opens": len({item.get("user") for item in review_opens}),
        "review_opened_at": latest,
        "refreshed_at": str((run or {}).get("finished_at") or ""),
        "rows": [_result_row(row) for row in scoped],
        "by_owner": _results_by_owner(scoped, as_of),
        "recovery": _sales_after_contact(store, contacts),
        "attribution": "Allocated receipts are counted on one task. Received since assigned is observed, not proof that the task caused the payment.",
    }


def _purchase_choice(stock_rows):
    """First item Item 360 says to buy: earliest buy-by, then larger quantity, then name."""
    choices = []
    for row in stock_rows or []:
        try:
            buy = float(row.get("buy_qty") or 0)
        except (TypeError, ValueError):
            buy = 0.0
        if buy <= 0.009:
            continue
        choices.append(row)
    if not choices:
        return None

    def key(row):
        when = row.get("buy_by") or "9999-99-99"
        return (when, -float(row.get("buy_qty") or 0), (row.get("name") or "").lower())

    choices.sort(key=key)
    return choices[0]


def suggestions(bundle, thresholds=None):
    """Proposed actions from the Phase 2 lists. Nothing is saved until the user confirms."""
    thresholds = thresholds or {}
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
    purchase = _purchase_choice(stock_rows)
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
    if purchase:
        ideas.append({
            "action_type": "purchase",
            "subject_kind": "item",
            "subject_name": purchase.get("name") or "",
            "proposal": "Reorder %s" % (purchase.get("name") or ""),
            "amount": purchase.get("buy_qty"),
            "reason": purchase.get("buy_reason") or "Purchase",
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
