"""Personal daily queue. Rows are derived; nothing is saved until the operator records it."""

from __future__ import annotations

from vay.dates import clean_text, number_, parse_date
from vay.eligibility import latest_snapshot_date

from server.actions import list_action_rows
from server.collection import PENDING_MESSAGE, follow_up_queues

ORDER_RULE = (
    "Blocked credit, then missed promises, then due follow-ups, "
    "then repurchase days past the usual gap, then inactive accounts."
)
EMPTY_REPS_MESSAGE = "Ask an admin to assign sales reps."

_KIND_RANK = {
    "missed_promise": 1,
    "pending_refresh": 2,
    "follow_up": 3,
    "repurchase": 4,
    "inactive": 5,
}


def _key(name):
    return clean_text(name).lower()


def _age(start, today):
    left = parse_date(start)
    right = parse_date(today)
    if not left or not right:
        return 0
    return max(0, (right - left).days)


def _reps_of(user):
    names = []
    for name in (user or {}).get("sales_reps") or []:
        text = clean_text(name)
        if text and text.lower() not in {item.lower() for item in names}:
            names.append(text)
    return names


def resolve_scope(store, user, staff=""):
    """Who this caller may see. Raises PermissionError or ValueError."""
    own = _reps_of(user)
    staff = clean_text(staff)
    can_review_staff = "users.view" in (user.get("permissions") or []) and not own
    if staff:
        if not can_review_staff:
            raise PermissionError("Forbidden")
        target = store.get_user(staff)
        if not target or not target.get("enabled", True):
            raise ValueError("User not found")
        return {
            "reps": _reps_of(target),
            "mode": "staff",
            "staff": target.get("username") or staff,
            "can_pick_staff": True,
            "message": "" if _reps_of(target) else EMPTY_REPS_MESSAGE,
        }
    if own:
        return {
            "reps": own,
            "mode": "self",
            "staff": "",
            "can_pick_staff": False,
            "message": "",
        }
    if "users.view" in (user.get("permissions") or []):
        return {
            "reps": None,
            "mode": "all",
            "staff": "",
            "can_pick_staff": True,
            "message": "",
        }
    return {
        "reps": [],
        "mode": "none",
        "staff": "",
        "can_pick_staff": False,
        "message": EMPTY_REPS_MESSAGE,
    }


def _blank(kind, customer, salesperson, reason, age, today, subject):
    return {
        "kind": kind,
        "customer": customer,
        "salesperson": salesperson,
        "reason": reason,
        "age": int(age or 0),
        "products": [],
        "credit": {"balance": 0.0, "overdue": 0.0},
        "value_kind": "",
        "amount": None,
        "evidence": {"kind": "customer", "name": customer},
        "data_date": today,
        "blocked": False,
        "block": "",
        "next_step": "",
        "action_id": "",
        "subject": subject,
    }


def _observed(row, amount):
    if amount in ("", None):
        return
    row["value_kind"] = "observed"
    row["amount"] = round(float(amount), 2)


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


def _directory(store):
    try:
        from server.customers import customer_directory_rows
        payload = customer_directory_rows(store) or {}
        rows = payload.get("rows") if isinstance(payload, dict) else payload
    except Exception:
        return {}
    found = {}
    for row in rows or []:
        if isinstance(row, dict) and row.get("name"):
            found[_key(row.get("name"))] = row
    return found


def _credit(profile):
    balance = number_((profile or {}).get("due"))
    overdue = 0.0
    for key in ("d30_45", "d45_60", "d60_90", "d90"):
        overdue += number_((profile or {}).get(key))
    return {"balance": round(balance, 2), "overdue": round(overdue, 2)}


def _profile(directory, reps, customer):
    key = _key(customer)
    profile = directory.get(key) or {}
    salesperson = clean_text(profile.get("salesperson") or profile.get("rep") or reps.get(key) or "")
    return profile, salesperson


def _allowed(scope, salesperson):
    reps = scope.get("reps")
    if reps is None:
        return True
    if not reps:
        return False
    wanted = {name.lower() for name in reps}
    return salesperson.lower() in wanted


def _follow_rows(store, scope, directory, reps, today):
    queues = follow_up_queues(store, today)
    today = queues.get("as_of") or today
    rows = []
    for contact in queues.get("due_follow_ups") or []:
        customer = contact.get("customer_name") or ""
        profile, salesperson = _profile(directory, reps, customer)
        if not _allowed(scope, salesperson):
            continue
        row = _blank(
            "follow_up",
            customer,
            salesperson,
            contact.get("next_step") or "Follow up",
            _age(contact.get("next_follow_up"), today),
            today,
            contact.get("id") or customer,
        )
        row["credit"] = _credit(profile)
        row["next_step"] = contact.get("next_step") or ""
        rows.append(row)
    for promise in queues.get("missed_promises") or []:
        customer = promise.get("customer_name") or ""
        profile, salesperson = _profile(directory, reps, customer)
        if not _allowed(scope, salesperson):
            continue
        row = _blank(
            "missed_promise",
            customer,
            salesperson,
            "Missed promise",
            _age(promise.get("promised_on"), today),
            today,
            promise.get("id") or customer,
        )
        row["credit"] = _credit(profile)
        _observed(row, promise.get("remaining"))
        rows.append(row)
    for promise in queues.get("pending_refresh") or []:
        customer = promise.get("customer_name") or ""
        profile, salesperson = _profile(directory, reps, customer)
        if not _allowed(scope, salesperson):
            continue
        row = _blank(
            "pending_refresh",
            customer,
            salesperson,
            promise.get("message") or PENDING_MESSAGE,
            _age(promise.get("promised_on"), today),
            today,
            promise.get("id") or customer,
        )
        row["credit"] = _credit(profile)
        _observed(row, promise.get("remaining"))
        rows.append(row)
    return rows, today


def _attach_actions(rows, store, scope, directory, reps, today):
    for action in list_action_rows(store):
        if action.get("status") != "open":
            continue
        if action.get("action_type") not in ("collection", "recovery"):
            continue
        if (action.get("subject_kind") or "customer") not in ("customer", ""):
            continue
        customer = action.get("subject_name") or ""
        profile, salesperson = _profile(directory, reps, customer)
        if not _allowed(scope, salesperson):
            continue
        kind = "inactive" if action.get("action_type") == "recovery" else "follow_up"
        match = None
        for row in rows:
            if _key(row.get("customer")) == _key(customer) and row.get("kind") == kind and not row.get("action_id"):
                match = row
                break
        if kind == "follow_up" and match is None:
            for row in rows:
                if _key(row.get("customer")) != _key(customer) or row.get("action_id"):
                    continue
                if row.get("kind") in ("missed_promise", "pending_refresh"):
                    match = row
                    break
        if match is not None:
            match["action_id"] = action.get("id") or ""
            continue
        row = _blank(
            kind,
            customer,
            salesperson,
            action.get("proposal") or "Assigned",
            _age(action.get("due_date"), today),
            action.get("report_date") or today,
            action.get("id") or customer,
        )
        row["credit"] = _credit(profile)
        row["action_id"] = action.get("id") or ""
        _observed(row, action.get("amount"))
        rows.append(row)
    return rows


def _repurchase_rows(store, scope, directory, reps, today):
    try:
        from server.book import load_book
        from server.repurchase import ensure_repurchase
        index = ensure_repurchase(load_book(store))
    except Exception:
        return []
    as_of = index.get("as_of")
    data_date = as_of.strftime("%Y-%m-%d") if hasattr(as_of, "strftime") else (str(as_of)[:10] if as_of else today)
    rows = []
    overdue = []
    for pair in index.get("pairs") or []:
        median = pair.get("median")
        days_since = pair.get("days_since")
        if median is None or days_since is None or days_since <= median:
            continue
        overdue.append(pair)
    for pair in overdue:
        customer = pair.get("party") or ""
        profile, salesperson = _profile(directory, reps, customer)
        salesperson = salesperson or clean_text(pair.get("rep"))
        if not _allowed(scope, salesperson):
            continue
        gap = int(pair.get("days_since") or 0) - int(pair.get("median") or 0)
        item = pair.get("item") or ""
        row = _blank(
            "repurchase",
            customer,
            salesperson,
            "Usual gap passed",
            max(0, gap),
            data_date,
            item or customer,
        )
        row["credit"] = _credit(profile)
        row["products"] = [item] if item else []
        amount = None
        for point in reversed(pair.get("points") or []):
            if point.get("amount") not in ("", None):
                amount = point.get("amount")
                break
        _observed(row, amount)
        row["on_hand_item"] = item
        rows.append(row)
    return rows


def _inactive_rows(store, scope, directory, reps, report_date, today):
    if not report_date:
        return []
    try:
        from server.phase2 import build_bundle
        bundle = build_bundle(store, report_date)
    except Exception:
        return []
    rows = []
    for source in ((bundle.get("customer_movement") or {}).get("rows") or []):
        if source.get("movement") != "inactive":
            continue
        customer = source.get("name") or ""
        profile, salesperson = _profile(directory, reps, customer)
        if not _allowed(scope, salesperson):
            continue
        current = number_(source.get("current"))
        prior = number_(source.get("prior"))
        row = _blank(
            "inactive",
            customer,
            salesperson,
            "No sale in the current period",
            0,
            report_date or today,
            customer,
        )
        row["credit"] = _credit(profile)
        _observed(row, round(current - prior, 2))
        rows.append(row)
    return rows


def _usual_qty(store, item):
    best = ("", 0.0)
    want = _key(item)
    for doc in store.rows_of_type("items") or []:
        fields = doc.get("fields") or {}
        if _key(fields.get("Item Name")) != want:
            continue
        day = str(fields.get("Date") or "")
        qty = number_(fields.get("Qty"))
        if day >= best[0]:
            best = (day, qty)
    return best[1]


def _on_hand(store):
    totals = {}
    for doc in store.rows_of_type("stock") or []:
        fields = doc.get("fields") or {}
        name = _key(fields.get("Item Name"))
        if not name:
            continue
        totals[name] = totals.get(name, 0.0) + number_(fields.get("Qty"))
    return totals


def _apply_credit(store, rows):
    from server.customers import account_uk
    from server.order_check import run_customer_order_check

    cached = {}
    for row in rows:
        key = _key(row.get("customer"))
        if key not in cached:
            try:
                cached[key] = run_customer_order_check(store, account_uk(row.get("customer"))) or {}
            except Exception:
                cached[key] = {}
        result = cached[key] or {}
        action = result.get("action") or ""
        if action not in ("push_back", "strong_push_back") and not result.get("blacklisted"):
            continue
        reason = ""
        for item in result.get("reasons") or []:
            reason = item.get("message") or ""
            if reason:
                break
        row["blocked"] = True
        row["block"] = "credit"
        step = "Collect before the next order."
        if reason:
            step = step + " " + reason
        row["next_step"] = step


def _apply_stock(store, rows):
    stock_date = latest_snapshot_date(store, "stock")
    on_hand = _on_hand(store)
    usual = {}
    for row in rows:
        if row.get("kind") != "repurchase" or row.get("block") == "credit":
            continue
        item = row.get("on_hand_item") or (row.get("products") or [""])[0]
        if not item:
            continue
        key = _key(item)
        if key not in usual:
            usual[key] = _usual_qty(store, item)
        if usual[key] <= 0 or on_hand.get(key, 0.0) >= usual[key]:
            continue
        row["blocked"] = True
        row["block"] = "stock"
        row["next_step"] = "Wait for stock."
        if stock_date:
            row["data_date"] = stock_date


def _sort(rows):
    def key(row):
        credit = 0 if row.get("block") == "credit" else 1
        return (
            credit,
            _KIND_RANK.get(row.get("kind"), 9),
            -int(row.get("age") or 0),
            _key(row.get("customer")),
        )
    rows.sort(key=key)
    for row in rows:
        row["id"] = "%s:%s" % (row.get("kind") or "", row.get("subject") or row.get("customer") or "")
        row.pop("on_hand_item", None)
        row.pop("subject", None)
    return rows


def _staff_options(store):
    options = []
    for doc in store.list_users() or []:
        if not doc.get("enabled", True):
            continue
        reps = _reps_of(doc)
        if not reps:
            continue
        options.append({"username": doc.get("username") or "", "sales_reps": reps})
    options.sort(key=lambda row: row["username"].lower())
    return options


def build_worklist(store, scope, report_date=""):
    scope = scope or {}
    if scope.get("reps") == []:
        return {
            "as_of": "",
            "order_rule": ORDER_RULE,
            "message": scope.get("message") or EMPTY_REPS_MESSAGE,
            "rows": [],
            "can_pick_staff": bool(scope.get("can_pick_staff")),
            "staff": scope.get("staff") or "",
            "staff_options": _staff_options(store) if scope.get("can_pick_staff") else [],
        }
    directory = _directory(store)
    reps = _rep_map(store)
    rows, today = _follow_rows(store, scope, directory, reps, "")
    rows.extend(_repurchase_rows(store, scope, directory, reps, today))
    rows.extend(_inactive_rows(store, scope, directory, reps, report_date, today))
    _attach_actions(rows, store, scope, directory, reps, today)
    _apply_credit(store, rows)
    _apply_stock(store, rows)
    _sort(rows)
    return {
        "as_of": today,
        "order_rule": ORDER_RULE,
        "message": scope.get("message") or "",
        "rows": rows,
        "can_pick_staff": bool(scope.get("can_pick_staff")),
        "staff": scope.get("staff") or "",
        "staff_options": _staff_options(store) if scope.get("can_pick_staff") else [],
    }
