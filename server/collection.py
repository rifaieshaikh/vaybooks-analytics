"""Collection contacts, promises, disputes, and receipt allocations.

These rows are operational metadata. They do not post transactions back to the
source system, and they are not imported customer notes.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from vay.dates import clean_text, number_, parse_date, today_ist

CONTACT_TYPE = "collection_contact"
PROMISE_TYPE = "collection_promise"
DISPUTE_TYPE = "collection_dispute"
ALLOCATION_TYPE = "collection_allocation"
ACTION_TYPE = "action"

CHANNELS = ("phone", "visit", "whatsapp", "email", "other")
DISPUTE_STATUSES = ("open", "resolved")
PENDING_MESSAGE = "Payment confirmation is pending a refresh."

_INVOICE_KEYS = ("Invoice No", "Invoice", "Invoice Number")
_NAME_KEYS = ("Account Name", "Party Name")


def _now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _today(as_of=None):
    if as_of:
        parsed = parse_date(str(as_of)[:10])
        if parsed:
            return parsed.strftime("%Y-%m-%d")
    return today_ist().strftime("%Y-%m-%d")


def _iso_date(value):
    if value is None or value == "":
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    parsed = parse_date(value)
    if parsed:
        return parsed.strftime("%Y-%m-%d")
    return str(value)[:10]


def _money(value):
    if value in ("", None):
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _require_date(value, label):
    text = _iso_date(value)
    if not text or not parse_date(text):
        raise ValueError("%s is required" % label)
    return text


def _optional_date(value, label):
    if value in ("", None):
        return ""
    text = _iso_date(value)
    if not text or not parse_date(text):
        raise ValueError("%s must be a date" % label)
    return text


def _refs(value):
    if isinstance(value, (list, tuple)):
        raw = value
    else:
        raw = str(value or "").replace(";", ",").split(",")
    out = []
    seen = set()
    for item in raw:
        text = clean_text(item)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def _key(name):
    return clean_text(name).lower()


def _rows(store, type_name):
    out = []
    for doc in store.rows_of_type(type_name) or []:
        fields = dict(doc.get("fields") or {})
        fields["id"] = doc.get("uk") or ""
        out.append(fields)
    return out


def _save(store, type_name, uk, fields):
    store.upsert_row({
        "type": type_name,
        "uk": uk,
        "source_upload_id": "",
        "fields": {k: v for k, v in fields.items() if k != "id"},
    })


def _find(rows, row_id):
    for row in rows:
        if row.get("id") == row_id:
            return row
    return None


def _party(fields):
    for key in _NAME_KEYS:
        name = clean_text(fields.get(key))
        if name:
            return name
    return ""


def _invoice(fields):
    for key in _INVOICE_KEYS:
        text = clean_text(fields.get(key))
        if text:
            return text
    return ""


def _check_action(store, action_id):
    action_id = clean_text(action_id)
    if not action_id:
        return ""
    for doc in store.rows_of_type(ACTION_TYPE) or []:
        if (doc.get("uk") or "") != action_id:
            continue
        kind = (doc.get("fields") or {}).get("action_type") or ""
        if kind != "collection":
            raise ValueError("action is not a collection task")
        return action_id
    raise ValueError("Action not found")


def _load_sources(store):
    specs = (("receipt", "Amount"), ("credit_note", "Net Amount"))
    out = []
    for type_name, amount_key in specs:
        for doc in store.rows_of_type(type_name) or []:
            fields = doc.get("fields") or {}
            amount = round(number_(fields.get(amount_key)), 2)
            if amount <= 0:
                continue
            out.append({
                "uk": doc.get("uk") or "",
                "source_type": type_name,
                "amount": amount,
                "name": _party(fields),
                "invoice": _invoice(fields),
                "date": _iso_date(fields.get("Date")),
            })
    return out


def _source_map(sources):
    return {(row["source_type"], row["uk"]): row for row in sources if row.get("uk")}


def _receipt_upload_dates(store):
    dates = []

    def take(value):
        text = _iso_date(value)
        if text:
            dates.append(text)

    for job in store.list_import_jobs() or []:
        if job.get("dry_run") or job.get("status") != "succeeded":
            continue
        types = job.get("types") or {}
        counts = job.get("row_counts") or {}
        if "receipt" not in types and "receipt" not in counts:
            continue
        take(job.get("created_at"))
        upload_id = job.get("upload_id")
        if upload_id and hasattr(store, "get_upload"):
            upload = store.get_upload(str(upload_id))
            if upload and not upload.get("dry_run"):
                take(upload.get("created_at"))
    for upload in store.list_uploads() or []:
        if upload.get("dry_run"):
            continue
        counts = upload.get("row_counts") or {}
        if upload.get("type") == "receipt" or "receipt" in counts:
            take(upload.get("created_at"))
    return dates


def coverage_current(store, customer_name, promised_on, sources=None):
    """True when receipt data reaches the promised date."""
    promised = _iso_date(promised_on)
    if not promised:
        return False
    key = _key(customer_name)
    latest = ""
    for row in sources if sources is not None else _load_sources(store):
        if row.get("source_type") != "receipt" or _key(row.get("name")) != key:
            continue
        if row.get("date") and row["date"] > latest:
            latest = row["date"]
    if latest and latest >= promised:
        return True
    for day in _receipt_upload_dates(store):
        if day >= promised:
            return True
    return False


def payment_state(amount, allocated, promised_on, as_of, current):
    remaining = round(max(0.0, round(float(amount or 0), 2) - round(float(allocated or 0), 2)), 2)
    promised = _iso_date(promised_on)
    today = _iso_date(as_of)
    if remaining <= 0.009:
        return {"payment_status": "kept", "remaining": 0.0, "message": ""}
    if promised and today and promised < today:
        if current:
            return {"payment_status": "missed", "remaining": remaining, "message": ""}
        return {
            "payment_status": "pending_refresh",
            "remaining": remaining,
            "message": PENDING_MESSAGE,
        }
    if round(float(allocated or 0), 2) > 0.009:
        return {"payment_status": "partial", "remaining": remaining, "message": ""}
    return {"payment_status": "open", "remaining": remaining, "message": ""}


def _active(alloc):
    return not alloc.get("voided_at")


def _allocated_to(allocs, promise_id):
    total = 0.0
    for row in allocs:
        if row.get("promise_id") == promise_id and _active(row):
            total += round(float(row.get("amount") or 0), 2)
    return round(total, 2)


def _void(row, username, reason):
    row["voided_at"] = _now()
    row["voided_by"] = username or "system"
    row["void_reason"] = reason
    row["updated_by"] = row["voided_by"]
    row["updated_at"] = row["voided_at"]
    row["amount"] = 0.0


def _clamp(row, amount, username):
    row["amount"] = round(amount, 2)
    row["clamped_at"] = _now()
    row["clamped_by"] = username or "system"
    row["updated_by"] = row["clamped_by"]
    row["updated_at"] = row["clamped_at"]


def sync_allocations(store):
    """Apply named invoice matches and drop allocations whose source disappeared."""
    sources = _load_sources(store)
    by_source = _source_map(sources)
    allocs = _rows(store, ALLOCATION_TYPE)
    dirty = set()

    for row in allocs:
        if not _active(row):
            continue
        src = by_source.get((row.get("source_type") or "", row.get("source_uk") or ""))
        if not src:
            _void(row, "system", "source_removed")
            dirty.add(row["id"])

    used = {}
    inferred = [row for row in allocs if _active(row) and row.get("basis") == "confirmed_inferred"]
    inferred.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    for row in inferred:
        src = by_source.get((row.get("source_type") or "", row.get("source_uk") or ""))
        if not src:
            continue
        key = (src["source_type"], src["uk"])
        room = round(src["amount"] - used.get(key, 0.0), 2)
        amount = round(float(row.get("amount") or 0), 2)
        if amount > room + 0.009:
            if room <= 0.009:
                _void(row, "system", "amount_reduced")
            else:
                _clamp(row, room, "system")
            dirty.add(row["id"])
            amount = round(float(row.get("amount") or 0), 2) if _active(row) else 0.0
        if amount > 0:
            used[key] = round(used.get(key, 0.0) + amount, 2)

    promises = _rows(store, PROMISE_TYPE)
    promises.sort(key=lambda row: (row.get("promised_on") or "", row.get("created_at") or "", row.get("id") or ""))
    desired = {}
    for promise in promises:
        refs = {ref.lower() for ref in _refs(promise.get("invoice_refs"))}
        if not refs:
            continue
        need = round(float(promise.get("amount") or 0) - _allocated_to(
            [row for row in allocs if row.get("basis") == "confirmed_inferred"],
            promise["id"],
        ), 2)
        if need <= 0.009:
            continue
        matches = [
            src for src in sources
            if _key(src.get("name")) == _key(promise.get("customer_name"))
            and (src.get("invoice") or "").lower() in refs
        ]
        matches.sort(key=lambda src: (src.get("date") or "", src.get("source_type") or "", src.get("uk") or ""))
        for src in matches:
            key = (src["source_type"], src["uk"])
            room = round(src["amount"] - used.get(key, 0.0), 2)
            take = round(min(room, need), 2)
            if take <= 0.009:
                continue
            desired[(promise["id"], src["source_type"], src["uk"])] = take
            used[key] = round(used.get(key, 0.0) + take, 2)
            need = round(need - take, 2)
            if need <= 0.009:
                break

    existing = {}
    for row in allocs:
        if row.get("basis") != "source_confirmed":
            continue
        token = (row.get("promise_id") or "", row.get("source_type") or "", row.get("source_uk") or "")
        existing.setdefault(token, []).append(row)

    for token, rows in existing.items():
        want = desired.get(token)
        active = [row for row in rows if _active(row)]
        if want is None:
            for row in active:
                _void(row, "system", "source_removed")
                dirty.add(row["id"])
            continue
        if not active:
            continue
        primary = sorted(active, key=lambda row: row.get("created_at") or "")[0]
        previous = round(float(primary.get("amount") or 0), 2)
        primary["amount"] = want
        if want + 0.009 < previous:
            _clamp(primary, want, "system")
        elif previous + 0.009 < want:
            primary.pop("clamped_at", None)
            primary.pop("clamped_by", None)
            primary["updated_by"] = "system"
            primary["updated_at"] = _now()
        dirty.add(primary["id"])
        for extra in active:
            if extra is primary:
                continue
            _void(extra, "system", "amount_reduced")
            dirty.add(extra["id"])
        desired.pop(token, None)

    for (promise_id, source_type, source_uk), amount in desired.items():
        uk = uuid.uuid4().hex
        stamp = _now()
        allocs.append({
            "id": uk,
            "promise_id": promise_id,
            "source_uk": source_uk,
            "source_type": source_type,
            "amount": amount,
            "basis": "source_confirmed",
            "confirmed_by": "system",
            "confirmed_at": stamp,
            "created_at": stamp,
            "updated_by": "system",
            "updated_at": stamp,
        })
        dirty.add(uk)

    for row in allocs:
        if row.get("id") in dirty:
            _save(store, ALLOCATION_TYPE, row["id"], row)
    return sources


def _basis_label(row):
    if row.get("voided_at"):
        if row.get("void_reason") == "cleared":
            return "Cleared"
        return "Voided"
    if row.get("source_type") == "credit_note" and row.get("basis") == "source_confirmed":
        label = "Credit note"
    elif row.get("basis") == "confirmed_inferred":
        label = "Confirmed inferred match"
    else:
        label = "Source-confirmed"
    if row.get("clamped_at"):
        label = "%s, adjusted after import" % label
    return label


def _allocation_view(row):
    return {
        "id": row.get("id") or "",
        "promise_id": row.get("promise_id") or "",
        "source_uk": row.get("source_uk") or "",
        "source_type": row.get("source_type") or "",
        "amount": round(float(row.get("amount") or 0), 2),
        "basis": row.get("basis") or "",
        "basis_label": _basis_label(row),
        "confirmed_by": row.get("confirmed_by") or "",
        "confirmed_at": row.get("confirmed_at") or "",
        "voided_at": row.get("voided_at") or "",
        "voided_by": row.get("voided_by") or "",
        "void_reason": row.get("void_reason") or "",
        "clamped_at": row.get("clamped_at") or "",
        "clamped_by": row.get("clamped_by") or "",
        "created_at": row.get("created_at") or "",
        "updated_by": row.get("updated_by") or "",
        "updated_at": row.get("updated_at") or "",
    }


def _suggestions(promise, sources, allocs):
    key = _key(promise.get("customer_name"))
    out = []
    for src in sources:
        if src.get("source_type") != "receipt" or _key(src.get("name")) != key:
            continue
        if src.get("invoice"):
            continue
        used = 0.0
        for row in allocs:
            if not _active(row):
                continue
            if row.get("source_uk") == src["uk"] and row.get("source_type") == "receipt":
                used += round(float(row.get("amount") or 0), 2)
        unused = round(src["amount"] - used, 2)
        if unused <= 0.009:
            continue
        out.append({
            "source_uk": src["uk"],
            "source_type": "receipt",
            "date": src.get("date") or "",
            "amount": src["amount"],
            "unused": unused,
            "label": "Inferred match. Confirm to apply.",
        })
    return out


def _promise_view(promise, allocs, sources, store, as_of):
    allocated = _allocated_to(allocs, promise.get("id"))
    current = coverage_current(store, promise.get("customer_name"), promise.get("promised_on"), sources)
    state = payment_state(promise.get("amount"), allocated, promise.get("promised_on"), as_of, current)
    view = {
        "id": promise.get("id") or "",
        "customer_name": promise.get("customer_name") or "",
        "action_id": promise.get("action_id") or "",
        "amount": round(float(promise.get("amount") or 0), 2),
        "promised_on": promise.get("promised_on") or "",
        "invoice_refs": _refs(promise.get("invoice_refs")),
        "staff": promise.get("staff") or "",
        "allocated": allocated,
        "coverage_current": current,
        "allocations": [_allocation_view(row) for row in allocs if row.get("promise_id") == promise.get("id")],
        "suggestions": [] if state["remaining"] <= 0.009 else _suggestions(promise, sources, allocs),
        "created_by": promise.get("created_by") or "",
        "created_at": promise.get("created_at") or "",
        "updated_by": promise.get("updated_by") or "",
        "updated_at": promise.get("updated_at") or "",
    }
    view.update(state)
    return view


def _contact_view(row):
    return {
        "id": row.get("id") or "",
        "customer_name": row.get("customer_name") or "",
        "action_id": row.get("action_id") or "",
        "contacted_on": row.get("contacted_on") or "",
        "staff": row.get("staff") or "",
        "channel": row.get("channel") or "",
        "note": row.get("note") or "",
        "next_step": row.get("next_step") or "",
        "next_follow_up": row.get("next_follow_up") or "",
        "created_by": row.get("created_by") or "",
        "created_at": row.get("created_at") or "",
        "updated_by": row.get("updated_by") or "",
        "updated_at": row.get("updated_at") or "",
    }


def _dispute_view(row):
    return {
        "id": row.get("id") or "",
        "customer_name": row.get("customer_name") or "",
        "promise_id": row.get("promise_id") or "",
        "invoice_refs": _refs(row.get("invoice_refs")),
        "note": row.get("note") or "",
        "staff": row.get("staff") or "",
        "status": row.get("status") or "open",
        "opened_on": row.get("opened_on") or "",
        "created_by": row.get("created_by") or "",
        "created_at": row.get("created_at") or "",
        "updated_by": row.get("updated_by") or "",
        "updated_at": row.get("updated_at") or "",
    }


def _bundle(store, as_of=None):
    today = _today(as_of)
    sources = sync_allocations(store)
    allocs = _rows(store, ALLOCATION_TYPE)
    promises = [
        _promise_view(row, allocs, sources, store, today)
        for row in _rows(store, PROMISE_TYPE)
    ]
    contacts = [_contact_view(row) for row in _rows(store, CONTACT_TYPE)]
    disputes = [_dispute_view(row) for row in _rows(store, DISPUTE_TYPE)]
    contacts.sort(key=lambda row: (row.get("contacted_on") or "", row.get("created_at") or ""), reverse=True)
    promises.sort(key=lambda row: (row.get("promised_on") or "", row.get("created_at") or ""))
    disputes.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    return today, contacts, promises, disputes


def customer_follow_up(store, customer_name, as_of=None):
    name = clean_text(customer_name)
    if not name:
        raise ValueError("customer_name is required")
    _today_value, contacts, promises, disputes = _bundle(store, as_of)
    key = _key(name)
    return {
        "customer_name": name,
        "contacts": [row for row in contacts if _key(row.get("customer_name")) == key],
        "promises": [row for row in promises if _key(row.get("customer_name")) == key],
        "disputes": [row for row in disputes if _key(row.get("customer_name")) == key],
    }


def follow_up_queues(store, as_of=None):
    today, contacts, promises, _disputes = _bundle(store, as_of)
    due = [
        row for row in contacts
        if row.get("next_follow_up") and row["next_follow_up"] <= today
    ]
    due.sort(key=lambda row: (row.get("next_follow_up") or "", _key(row.get("customer_name"))))
    missed = [row for row in promises if row.get("payment_status") == "missed"]
    pending = [row for row in promises if row.get("payment_status") == "pending_refresh"]
    return {
        "as_of": today,
        "due_follow_ups": due,
        "missed_promises": missed,
        "pending_refresh": pending,
    }


def reminder_context(store, customer_name, as_of=None):
    payload = customer_follow_up(store, customer_name, as_of)
    open_promises = [
        row for row in payload["promises"]
        if row.get("payment_status") != "kept"
    ]
    next_step = ""
    next_follow_up = ""
    for row in payload["contacts"]:
        if row.get("next_step") and not next_step:
            next_step = row["next_step"]
        when = row.get("next_follow_up") or ""
        if when and (not next_follow_up or when < next_follow_up):
            next_follow_up = when
            if row.get("next_step"):
                next_step = row["next_step"]
    return {
        "customer_name": payload["customer_name"],
        "promises": open_promises,
        "next_step": next_step,
        "next_follow_up": next_follow_up,
    }


def attach_collection_summaries(store, actions, as_of=None):
    if not any((row or {}).get("action_type") == "collection" for row in actions or []):
        return actions
    _today_value, contacts, promises, _disputes = _bundle(store, as_of)
    by_name = {}
    for row in promises:
        by_name.setdefault(_key(row.get("customer_name")), []).append(row)
    follow = {}
    for row in contacts:
        when = row.get("next_follow_up") or ""
        if not when:
            continue
        key = _key(row.get("customer_name"))
        if key not in follow or when < follow[key]:
            follow[key] = when
    for action in actions or []:
        if (action or {}).get("action_type") != "collection":
            continue
        related = by_name.get(_key(action.get("subject_name")), [])
        remaining = round(sum(float(row.get("remaining") or 0) for row in related), 2)
        if any(row.get("payment_status") == "pending_refresh" for row in related):
            label = PENDING_MESSAGE
        elif any(row.get("payment_status") == "missed" for row in related):
            label = "Missed promise"
        elif related and remaining <= 0.009:
            label = "Promise kept"
        elif related:
            label = "Remaining promised"
        else:
            label = ""
        action["collection"] = {
            "promise_count": len(related),
            "remaining": remaining,
            "next_follow_up": follow.get(_key(action.get("subject_name")), ""),
            "missed": sum(1 for row in related if row.get("payment_status") == "missed"),
            "pending_refresh": sum(1 for row in related if row.get("payment_status") == "pending_refresh"),
            "label": label,
        }
    return actions


def create_contact(store, body, username):
    name = clean_text(body.get("customer_name"))
    if not name:
        raise ValueError("customer_name is required")
    channel = clean_text(body.get("channel")).lower()
    if channel not in CHANNELS:
        raise ValueError("channel must be phone, visit, whatsapp, email, or other")
    stamp = _now()
    uk = uuid.uuid4().hex
    fields = {
        "customer_name": name,
        "action_id": _check_action(store, body.get("action_id")),
        "contacted_on": _require_date(body.get("contacted_on"), "contacted_on"),
        "staff": clean_text(body.get("staff")) or (username or ""),
        "channel": channel,
        "note": clean_text(body.get("note")),
        "next_step": clean_text(body.get("next_step")),
        "next_follow_up": _optional_date(body.get("next_follow_up"), "next_follow_up"),
        "created_by": username or "",
        "created_at": stamp,
        "updated_by": username or "",
        "updated_at": stamp,
    }
    _save(store, CONTACT_TYPE, uk, fields)
    fields["id"] = uk
    return _contact_view(fields)


def update_contact(store, contact_id, body, username):
    row = _find(_rows(store, CONTACT_TYPE), contact_id)
    if not row:
        raise ValueError("Contact not found")
    if "customer_name" in body:
        name = clean_text(body.get("customer_name"))
        if not name:
            raise ValueError("customer_name is required")
        row["customer_name"] = name
    if "action_id" in body:
        row["action_id"] = _check_action(store, body.get("action_id"))
    if "contacted_on" in body:
        row["contacted_on"] = _require_date(body.get("contacted_on"), "contacted_on")
    if "staff" in body:
        row["staff"] = clean_text(body.get("staff")) or (username or "")
    if "channel" in body:
        channel = clean_text(body.get("channel")).lower()
        if channel not in CHANNELS:
            raise ValueError("channel must be phone, visit, whatsapp, email, or other")
        row["channel"] = channel
    if "note" in body:
        row["note"] = clean_text(body.get("note"))
    if "next_step" in body:
        row["next_step"] = clean_text(body.get("next_step"))
    if "next_follow_up" in body:
        row["next_follow_up"] = _optional_date(body.get("next_follow_up"), "next_follow_up")
    row["updated_by"] = username or ""
    row["updated_at"] = _now()
    _save(store, CONTACT_TYPE, row["id"], row)
    return _contact_view(row)


def create_promise(store, body, username):
    name = clean_text(body.get("customer_name"))
    if not name:
        raise ValueError("customer_name is required")
    amount = _money(body.get("amount"))
    if amount is None or amount <= 0:
        raise ValueError("amount must be a positive number")
    stamp = _now()
    uk = uuid.uuid4().hex
    fields = {
        "customer_name": name,
        "action_id": _check_action(store, body.get("action_id")),
        "amount": amount,
        "promised_on": _require_date(body.get("promised_on"), "promised_on"),
        "invoice_refs": _refs(body.get("invoice_refs")),
        "staff": clean_text(body.get("staff")) or (username or ""),
        "created_by": username or "",
        "created_at": stamp,
        "updated_by": username or "",
        "updated_at": stamp,
    }
    _save(store, PROMISE_TYPE, uk, fields)
    payload = customer_follow_up(store, name)
    for row in payload["promises"]:
        if row["id"] == uk:
            return row
    fields["id"] = uk
    return fields


def update_promise(store, promise_id, body, username):
    row = _find(_rows(store, PROMISE_TYPE), promise_id)
    if not row:
        raise ValueError("Promise not found")
    if "customer_name" in body:
        name = clean_text(body.get("customer_name"))
        if not name:
            raise ValueError("customer_name is required")
        row["customer_name"] = name
    if "action_id" in body:
        row["action_id"] = _check_action(store, body.get("action_id"))
    if "amount" in body:
        amount = _money(body.get("amount"))
        if amount is None or amount <= 0:
            raise ValueError("amount must be a positive number")
        sync_allocations(store)
        allocated = _allocated_to(_rows(store, ALLOCATION_TYPE), promise_id)
        if amount + 0.009 < allocated:
            raise ValueError("amount is below the amount already allocated")
        row["amount"] = amount
    if "promised_on" in body:
        row["promised_on"] = _require_date(body.get("promised_on"), "promised_on")
    if "invoice_refs" in body:
        row["invoice_refs"] = _refs(body.get("invoice_refs"))
    if "staff" in body:
        row["staff"] = clean_text(body.get("staff")) or (username or "")
    row["updated_by"] = username or ""
    row["updated_at"] = _now()
    _save(store, PROMISE_TYPE, row["id"], row)
    payload = customer_follow_up(store, row.get("customer_name"))
    for item in payload["promises"]:
        if item["id"] == promise_id:
            return item
    return row


def create_dispute(store, body, username):
    name = clean_text(body.get("customer_name"))
    if not name:
        raise ValueError("customer_name is required")
    note = clean_text(body.get("note"))
    if not note:
        raise ValueError("note is required")
    promise_id = clean_text(body.get("promise_id"))
    if promise_id and not _find(_rows(store, PROMISE_TYPE), promise_id):
        raise ValueError("Promise not found")
    status = clean_text(body.get("status")).lower() or "open"
    if status not in DISPUTE_STATUSES:
        raise ValueError("status must be open or resolved")
    stamp = _now()
    uk = uuid.uuid4().hex
    fields = {
        "customer_name": name,
        "promise_id": promise_id,
        "invoice_refs": _refs(body.get("invoice_refs")),
        "note": note,
        "status": status,
        "opened_on": _optional_date(body.get("opened_on"), "opened_on") or _today(),
        "staff": clean_text(body.get("staff")) or (username or ""),
        "created_by": username or "",
        "created_at": stamp,
        "updated_by": username or "",
        "updated_at": stamp,
    }
    _save(store, DISPUTE_TYPE, uk, fields)
    fields["id"] = uk
    return _dispute_view(fields)


def update_dispute(store, dispute_id, body, username):
    row = _find(_rows(store, DISPUTE_TYPE), dispute_id)
    if not row:
        raise ValueError("Dispute not found")
    if "customer_name" in body:
        name = clean_text(body.get("customer_name"))
        if not name:
            raise ValueError("customer_name is required")
        row["customer_name"] = name
    if "promise_id" in body:
        promise_id = clean_text(body.get("promise_id"))
        if promise_id and not _find(_rows(store, PROMISE_TYPE), promise_id):
            raise ValueError("Promise not found")
        row["promise_id"] = promise_id
    if "invoice_refs" in body:
        row["invoice_refs"] = _refs(body.get("invoice_refs"))
    if "note" in body:
        note = clean_text(body.get("note"))
        if not note:
            raise ValueError("note is required")
        row["note"] = note
    if "status" in body:
        status = clean_text(body.get("status")).lower()
        if status not in DISPUTE_STATUSES:
            raise ValueError("status must be open or resolved")
        row["status"] = status
    if "opened_on" in body:
        row["opened_on"] = _require_date(body.get("opened_on"), "opened_on")
    if "staff" in body:
        row["staff"] = clean_text(body.get("staff")) or (username or "")
    row["updated_by"] = username or ""
    row["updated_at"] = _now()
    _save(store, DISPUTE_TYPE, row["id"], row)
    return _dispute_view(row)


def confirm_allocation(store, body, username):
    promise = _find(_rows(store, PROMISE_TYPE), clean_text(body.get("promise_id")))
    if not promise:
        raise ValueError("Promise not found")
    source_type = clean_text(body.get("source_type")) or "receipt"
    if source_type != "receipt":
        raise ValueError("Only an unallocated receipt can be confirmed")
    source_uk = clean_text(body.get("source_uk"))
    sources = sync_allocations(store)
    src = _source_map(sources).get((source_type, source_uk))
    if not src or _key(src.get("name")) != _key(promise.get("customer_name")):
        raise ValueError("Receipt not found")
    if src.get("invoice"):
        raise ValueError("A named receipt is applied from the invoice, not by confirmation")
    allocs = _rows(store, ALLOCATION_TYPE)
    used = 0.0
    for row in allocs:
        if _active(row) and row.get("source_uk") == source_uk and row.get("source_type") == source_type:
            used += round(float(row.get("amount") or 0), 2)
    unused = round(src["amount"] - used, 2)
    remaining = round(float(promise.get("amount") or 0) - _allocated_to(allocs, promise["id"]), 2)
    if unused <= 0.009 or remaining <= 0.009:
        raise ValueError("Nothing left to apply from this receipt")
    requested = body.get("amount")
    if requested in ("", None):
        amount = round(min(unused, remaining), 2)
    else:
        amount = _money(requested)
        if amount is None or amount <= 0:
            raise ValueError("amount must be a positive number")
        if amount > unused + 0.009 or amount > remaining + 0.009:
            raise ValueError("amount is above the unused receipt or the remaining promise")
    stamp = _now()
    uk = uuid.uuid4().hex
    fields = {
        "promise_id": promise["id"],
        "source_uk": source_uk,
        "source_type": source_type,
        "amount": amount,
        "basis": "confirmed_inferred",
        "confirmed_by": username or "",
        "confirmed_at": stamp,
        "created_at": stamp,
        "updated_by": username or "",
        "updated_at": stamp,
    }
    _save(store, ALLOCATION_TYPE, uk, fields)
    payload = customer_follow_up(store, promise.get("customer_name"))
    for row in payload["promises"]:
        if row["id"] == promise["id"]:
            return row
    return fields


def clear_allocation(store, allocation_id, username):
    row = _find(_rows(store, ALLOCATION_TYPE), allocation_id)
    if not row:
        raise ValueError("Allocation not found")
    if row.get("basis") != "confirmed_inferred":
        raise ValueError("Only a confirmed inferred match can be cleared")
    if row.get("voided_at"):
        raise ValueError("Allocation is already cleared")
    promise = _find(_rows(store, PROMISE_TYPE), row.get("promise_id") or "")
    _void(row, username or "", "cleared")
    _save(store, ALLOCATION_TYPE, row["id"], row)
    if not promise:
        return {"id": allocation_id, "voided_at": row.get("voided_at")}
    payload = customer_follow_up(store, promise.get("customer_name"))
    for item in payload["promises"]:
        if item["id"] == promise["id"]:
            return item
    return row
