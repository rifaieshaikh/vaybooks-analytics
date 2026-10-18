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
TARGET_TYPE = "collection_target"
ACTION_TYPE = "action"

CHANNELS = ("phone", "visit", "whatsapp", "email", "other")
DISPUTE_STATUSES = ("open", "resolved")
PENDING_MESSAGE = "Payment confirmation is pending a refresh."

_INVOICE_KEYS = ("Invoice No", "Invoice", "Invoice Number")
_NAME_KEYS = ("Account Name", "Party Name")


def _now():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _today(as_of=None, store=None):
    if as_of:
        parsed = parse_date(str(as_of)[:10])
        if parsed:
            return parsed.strftime("%Y-%m-%d")
    timezone = None
    if store is not None:
        from server.org_policy import get_org_policy
        timezone = (get_org_policy(store) or {}).get("timezone")
    return today_ist(timezone).strftime("%Y-%m-%d")


def _audit(store, action, username, detail):
    from server.audit import record
    record(store, action, username or "", detail)


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


def coverage_through(store, customer_name):
    """Phase 1 coverage end. An upload date is not coverage."""
    latest = ""
    key = _key(customer_name)
    for doc in store.rows_of_type("customer_opening") or []:
        fields = doc.get("fields") or {}
        account = _key(fields.get("Account Name") or fields.get("Party Name") or "")
        if account and account != key:
            continue
        if str(fields.get("Kind") or "").strip().lower() != "coverage":
            continue
        day = _iso_date(fields.get("Complete Through"))
        if day and day > latest:
            latest = day
    return latest


def coverage_current(store, customer_name, promised_on, sources=None):
    """True when Phase 1 coverage or a receipt date reaches the promised date."""
    promised = _iso_date(promised_on)
    if not promised:
        return False
    through = coverage_through(store, customer_name)
    if through and through >= promised:
        return True
    key = _key(customer_name)
    latest = ""
    for row in sources if sources is not None else _load_sources(store):
        if row.get("source_type") != "receipt" or _key(row.get("name")) != key:
            continue
        if row.get("date") and row["date"] > latest:
            latest = row["date"]
    return bool(latest and latest >= promised)


def payment_state(
    amount,
    allocated,
    promised_on,
    as_of,
    current,
    cash_allocated=None,
    non_cash_allocated=0,
    paid_on="",
    cancelled=False,
    superseded=False,
):
    from vay.recovery import promise_outcome

    cash = allocated if cash_allocated is None else cash_allocated
    through = promised_on if current else ""
    outcome = promise_outcome(
        amount,
        cash,
        non_cash_allocated,
        _iso_date(promised_on),
        _iso_date(paid_on),
        _iso_date(as_of),
        _iso_date(through) if current else "",
        cancelled=cancelled,
        superseded=superseded,
    )
    status = outcome["payment_status"]
    message = ""
    if status == "awaiting_data":
        status = "pending_refresh"
        message = PENDING_MESSAGE
    return {
        "payment_status": status,
        "remaining": float(outcome["remaining"]),
        "message": message,
        "cash_kept": outcome["cash_kept"],
    }


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


def _receipt_coverage(customer_name, sources):
    latest = ""
    key = _key(customer_name)
    for row in sources or []:
        if row.get("source_type") != "receipt" or _key(row.get("name")) != key:
            continue
        day = row.get("date") or ""
        if day > latest:
            latest = day
    return latest


def _allocation_split(promise_id, allocs, sources):
    by_source = _source_map(sources)
    cash = 0.0
    non_cash = 0.0
    paid_on = ""
    for row in allocs:
        if row.get("promise_id") != promise_id or not _active(row):
            continue
        amount = round(float(row.get("amount") or 0), 2)
        source_type = row.get("source_type") or "receipt"
        src = by_source.get((source_type, row.get("source_uk") or ""))
        if source_type == "credit_note" or (src and src.get("source_type") == "credit_note"):
            non_cash = round(non_cash + amount, 2)
            continue
        cash = round(cash + amount, 2)
        day = (src or {}).get("date") or ""
        if day > paid_on:
            paid_on = day
    return cash, non_cash, paid_on


def _promise_view(promise, allocs, sources, store, as_of):
    allocated = _allocated_to(allocs, promise.get("id"))
    cash, non_cash, paid_on = _allocation_split(promise.get("id"), allocs, sources)
    current = coverage_current(store, promise.get("customer_name"), promise.get("promised_on"), sources)
    state = payment_state(
        promise.get("amount"),
        allocated,
        promise.get("promised_on"),
        as_of,
        current,
        cash_allocated=cash,
        non_cash_allocated=non_cash,
        paid_on=paid_on,
        cancelled=promise.get("status") == "cancelled",
        superseded=promise.get("status") == "superseded",
    )
    receipt_through = _receipt_coverage(promise.get("customer_name"), sources)
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
        "receipt_coverage_through": receipt_through,
        "data_basis": {
            "basis": "live",
            "receipt_coverage_through": receipt_through,
        },
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


def refresh_targets(store, sources):
    """Write each open target's remaining amount from the current receipts."""
    from vay.recovery import apply_recovery

    targets = _rows(store, TARGET_TYPE)
    if not targets:
        return {"actual_cash": 0.0, "target_linked_cash": 0.0, "non_cash_resolutions": 0.0}
    result = apply_recovery(targets, sources, _rows(store, PROMISE_TYPE), _rows(store, ALLOCATION_TYPE))
    by_id = {row["id"]: row for row in result["targets"]}
    for row in targets:
        fresh = by_id.get(row.get("id") or "")
        if not fresh or (row.get("status") or "open") != "open":
            continue
        remaining = float(fresh["remaining"])
        cash_applied = float(fresh["cash_applied"])
        non_cash_applied = float(fresh["non_cash_applied"])
        changed = (
            abs(round(float(row.get("remaining") if row.get("remaining") is not None else row.get("assigned_amount") or 0), 2) - remaining) > 0.009
            or abs(round(float(row.get("cash_applied") or 0), 2) - cash_applied) > 0.009
            or abs(round(float(row.get("non_cash_applied") or 0), 2) - non_cash_applied) > 0.009
        )
        row["remaining"] = remaining
        row["cash_applied"] = cash_applied
        row["non_cash_applied"] = non_cash_applied
        if changed:
            _save(store, TARGET_TYPE, row["id"], row)
    return {
        "actual_cash": float(result["actual_cash"]),
        "target_linked_cash": float(result["target_linked_cash"]),
        "non_cash_resolutions": float(result["non_cash_resolutions"]),
    }


def _bundle(store, as_of=None):
    today = _today(as_of, store)
    sources = sync_allocations(store)
    refresh_targets(store, sources)
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


def _target_view(row):
    return {
        "id": row.get("id") or "",
        "customer_name": row.get("customer_name") or "",
        "owner": row.get("owner") or "",
        "period_start": row.get("period_start") or "",
        "period_end": row.get("period_end") or "",
        "debt_ids": list(row.get("debt_ids") or []),
        "assigned_amount": round(float(row.get("assigned_amount") or 0), 2),
        "baseline_amount": round(float(row.get("baseline_amount") or 0), 2),
        "remaining": round(float(row.get("remaining") if row.get("remaining") is not None else row.get("assigned_amount") or 0), 2),
        "cash_applied": round(float(row.get("cash_applied") or 0), 2),
        "non_cash_applied": round(float(row.get("non_cash_applied") or 0), 2),
        "status": row.get("status") or "open",
        "supersedes": row.get("supersedes") or "",
        "next_step": row.get("next_step") or "",
        "created_by": row.get("created_by") or "",
        "created_at": row.get("created_at") or "",
        "updated_by": row.get("updated_by") or "",
        "updated_at": row.get("updated_at") or "",
    }


def _customer_targets(store, customer_name):
    key = _key(customer_name)
    rows = [row for row in _rows(store, TARGET_TYPE) if _key(row.get("customer_name")) == key]
    rows.sort(key=lambda row: (row.get("created_at") or "", row.get("id") or ""))
    return [_target_view(row) for row in rows]


def current_target(row, as_of):
    """An open target whose period has not ended still commits the actionable pool."""
    if str((row or {}).get("status") or "open") != "open":
        return False
    end = str((row or {}).get("period_end") or "")[:10]
    if not end:
        return True
    return end >= str(as_of or "")[:10]


def _recovery_summary(promises, targets, disputes, as_of):
    from vay.recovery import assign_targets, cap_commitments, owner_outcomes, recovery_pools

    items = []
    seen = set()
    open_disputes = set()
    for dispute in disputes or []:
        if (dispute.get("status") or "open") != "open":
            continue
        for ref in dispute.get("invoice_refs") or []:
            open_disputes.add(str(ref).lower())
    for target in targets or []:
        if not current_target(target, as_of):
            continue
        for debt in target.get("debts") or []:
            debt_id = str(debt.get("id") or "")
            if not debt_id or debt_id in seen:
                continue
            seen.add(debt_id)
            item = dict(debt)
            if debt_id.lower() in open_disputes:
                item["disputed"] = True
            items.append(item)
    pools = recovery_pools(items)
    current = [row for row in targets or [] if current_target(row, as_of)]
    assigned = assign_targets(current, pools["actionable"])
    commitments = cap_commitments(promises, pools["actionable"])
    outcome_rows = current + [row for row in targets or [] if str(row.get("status") or "") == "superseded"]
    return {
        "pools": {key: float(value) if key != "eligibility" else value for key, value in pools.items()},
        "assigned_targets": float(assigned["assigned"]),
        "remaining_promises": float(commitments["remaining_promises"]),
        "owner_outcomes": [
            {
                "owner": row["owner"],
                "open_assigned": float(row["open_assigned"]),
                "baseline": float(row["baseline"]),
                "superseded": float(row["superseded"]),
            }
            for row in owner_outcomes(outcome_rows)
        ],
    }


def customer_follow_up(store, customer_name, as_of=None):
    name = clean_text(customer_name)
    if not name:
        raise ValueError("customer_name is required")
    today, contacts, promises, disputes = _bundle(store, as_of)
    key = _key(name)
    customer_promises = [row for row in promises if _key(row.get("customer_name")) == key]
    customer_disputes = [row for row in disputes if _key(row.get("customer_name")) == key]
    stored_targets = [row for row in _rows(store, TARGET_TYPE) if _key(row.get("customer_name")) == key]
    summary = _recovery_summary(customer_promises, stored_targets, customer_disputes, today)
    from vay.recovery import apply_recovery
    customer_sources = [row for row in _load_sources(store) if _key(row.get("name")) == key]
    cash = apply_recovery(
        stored_targets,
        customer_sources,
        [row for row in _rows(store, PROMISE_TYPE) if _key(row.get("customer_name")) == key],
        _rows(store, ALLOCATION_TYPE),
    )
    summary["actual_cash"] = float(cash["actual_cash"])
    summary["target_linked_cash"] = float(cash["target_linked_cash"])
    summary["non_cash_resolutions"] = float(cash["non_cash_resolutions"])
    summary["cash_note"] = "Linked cash shares each receipt once. It does not show that the target caused the payment."
    summary["forecast_note"] = (
        "Expected recovery is on Cash, and only after completed periods pass the recorded checks. "
        "This assigned amount stays as entered."
    )
    return {
        "customer_name": name,
        "contacts": [row for row in contacts if _key(row.get("customer_name")) == key],
        "promises": customer_promises,
        "disputes": customer_disputes,
        "targets": [_target_view(row) for row in stored_targets],
        **summary,
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
    from server.org_policy import get_org_policy
    from vay.recovery import owner_outcomes
    policy = get_org_policy(store)
    stored_targets = _rows(store, TARGET_TYPE)
    targets = [_target_view(row) for row in stored_targets if current_target(row, today)]
    return {
        "as_of": today,
        "currency_code": policy.get("currency_code") or "",
        "currency_symbol": policy.get("currency_symbol") or "",
        "due_follow_ups": due,
        "missed_promises": missed,
        "pending_refresh": pending,
        "targets": [row for row in targets if row.get("status") == "open"],
        "owner_outcomes": [
            {
                "owner": row["owner"],
                "open_assigned": float(row["open_assigned"]),
                "baseline": float(row["baseline"]),
                "superseded": float(row["superseded"]),
            }
            for row in owner_outcomes(
                [row for row in stored_targets if current_target(row, today) or str(row.get("status") or "") == "superseded"]
            )
        ],
    }


def reminder_context(store, customer_name, as_of=None):
    payload = customer_follow_up(store, customer_name, as_of)
    settled = {"kept", "kept_on_time", "kept_late", "cancelled", "superseded", "non_cash"}
    open_promises = [
        row for row in payload["promises"]
        if row.get("payment_status") not in settled
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
    from server.org_policy import get_org_policy
    policy = get_org_policy(store)
    return {
        "customer_name": payload["customer_name"],
        "promises": open_promises,
        "next_step": next_step,
        "next_follow_up": next_follow_up,
        "currency_code": policy.get("currency_code") or "",
        "currency_symbol": policy.get("currency_symbol") or "",
        "company_name": policy.get("company_name") or "",
        "as_of": _today(as_of, store),
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
    _audit(store, "collection_contact", username, "Create contact %s" % name)
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
    _audit(store, "collection_contact", username, "Update contact %s" % (row.get("customer_name") or contact_id))
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
    _audit(store, "collection_promise", username, "Create promise %s" % name)
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
    if body.get("status") in ("cancelled", "superseded"):
        row["status"] = body["status"]
    row["updated_by"] = username or ""
    row["updated_at"] = _now()
    _save(store, PROMISE_TYPE, row["id"], row)
    _audit(store, "collection_promise", username, "Update promise %s" % (row.get("customer_name") or promise_id))
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
        "opened_on": _optional_date(body.get("opened_on"), "opened_on") or _today(store=store),
        "staff": clean_text(body.get("staff")) or (username or ""),
        "created_by": username or "",
        "created_at": stamp,
        "updated_by": username or "",
        "updated_at": stamp,
    }
    _save(store, DISPUTE_TYPE, uk, fields)
    fields["id"] = uk
    _audit(store, "collection_dispute", username, "Create dispute %s" % name)
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
    _audit(store, "collection_dispute", username, "Update dispute %s" % (row.get("customer_name") or dispute_id))
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
    _audit(store, "collection_allocation", username, "Confirm allocation %s" % (promise.get("customer_name") or ""))
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
    _audit(store, "collection_allocation", username, "Clear allocation %s" % allocation_id)
    if not promise:
        return {"id": allocation_id, "voided_at": row.get("voided_at")}
    payload = customer_follow_up(store, promise.get("customer_name"))
    for item in payload["promises"]:
        if item["id"] == promise["id"]:
            return item
    return row


def create_target(store, body, username):
    from vay.recovery import assign_targets, recovery_pools

    name = clean_text(body.get("customer_name"))
    if not name:
        raise ValueError("customer_name is required")
    owner = clean_text(body.get("owner")) or (username or "")
    if not owner:
        raise ValueError("owner is required")
    start = _require_date(body.get("period_start"), "period_start")
    end = _require_date(body.get("period_end"), "period_end")
    if end < start:
        raise ValueError("period_end is before period_start")
    assigned = _money(body.get("assigned_amount"))
    if assigned is None or assigned <= 0:
        raise ValueError("assigned_amount must be a positive number")
    debts = body.get("debts") or []
    if debts:
        pools = recovery_pools(debts)
        today = _today(None, store)
        if end >= today:
            replaced = clean_text(body.get("supersedes"))
            existing = [
                row for row in _rows(store, TARGET_TYPE)
                if _key(row.get("customer_name")) == _key(name)
                and current_target(row, today)
                and row.get("id") != replaced
            ]
            counted = assign_targets(
                existing + [{"id": "new", "assigned_amount": assigned, "status": "open", "created_at": "9999"}],
                pools["actionable"],
            )
            fitted = float(counted["targets"][-1]["counted"])
            if fitted + 0.009 < assigned:
                raise ValueError("assigned amount is outside the actionable pool")
            assigned = fitted
    supersedes = clean_text(body.get("supersedes"))
    if supersedes:
        previous = _find(_rows(store, TARGET_TYPE), supersedes)
        if not previous:
            raise ValueError("Target not found")
        previous["status"] = "superseded"
        previous["updated_by"] = username or ""
        previous["updated_at"] = _now()
        _save(store, TARGET_TYPE, previous["id"], previous)
    stamp = _now()
    uk = uuid.uuid4().hex
    fields = {
        "customer_name": name,
        "owner": owner,
        "period_start": start,
        "period_end": end,
        "debt_ids": [str(debt.get("id") or "") for debt in debts if debt.get("id")],
        "debts": debts,
        "assigned_amount": assigned,
        "baseline_amount": assigned,
        "remaining": assigned,
        "status": "open",
        "supersedes": supersedes,
        "next_step": clean_text(body.get("next_step")),
        "created_by": username or "",
        "created_at": stamp,
        "updated_by": username or "",
        "updated_at": stamp,
    }
    _save(store, TARGET_TYPE, uk, fields)
    _audit(store, "collection_target", username, "Create target %s" % name)
    return _target_view(fields | {"id": uk})


def update_target(store, target_id, body, username):
    row = _find(_rows(store, TARGET_TYPE), target_id)
    if not row:
        raise ValueError("Target not found")
    if (row.get("status") or "open") != "open":
        raise ValueError("Only an open target can be changed")
    if "owner" in body:
        owner = clean_text(body.get("owner"))
        if not owner:
            raise ValueError("owner is required")
        row["owner"] = owner
    if "next_step" in body:
        row["next_step"] = clean_text(body.get("next_step"))
    row["updated_by"] = username or ""
    row["updated_at"] = _now()
    _save(store, TARGET_TYPE, row["id"], row)
    _audit(store, "collection_target", username, "Update target %s" % (row.get("customer_name") or target_id))
    return _target_view(row)
