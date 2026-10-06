"""Compare all-time sales − collection − credit notes with the ARR snapshot."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from vay.config import DEFAULT_RECEIPT_REP
from vay.credit_notes import resolve_credit_party
from vay.dates import clean_text, fiscal_year_start, fy_label, number_

from server.org_policy import collection_customer_keys, get_org_policy


def _round2(value):
    return round(float(value or 0), 2)


def party_ledgers(store):
    """Lowercase party name → sales, collection, gap, and ARR snapshot."""
    customers = collection_customer_keys(store)
    sales = defaultdict(float)
    collection = defaultdict(float)
    credits = defaultdict(float)
    display = {}

    for row in store.rows_of_type("sales"):
        fields = row.get("fields") or {}
        name = clean_text(fields.get("Party Name") or fields.get("Account Name"))
        if not name:
            continue
        key = name.lower()
        sales[key] += number_(fields.get("Net Amount"))
        display.setdefault(key, name)

    for row in store.rows_of_type("receipt"):
        fields = row.get("fields") or {}
        name = clean_text(fields.get("Account Name") or fields.get("Party Name"))
        if not name:
            continue
        key = name.lower()
        rep = clean_text(fields.get("Sales Rep"))
        if rep == DEFAULT_RECEIPT_REP:
            continue
        if key not in customers:
            continue
        collection[key] += number_(fields.get("Amount"))
        display.setdefault(key, name)

    arr = {}
    for row in store.rows_of_type("arr"):
        fields = row.get("fields") or {}
        name = clean_text(fields.get("Account Name") or fields.get("Party Name"))
        if not name:
            continue
        key = name.lower()
        arr[key] = _round2(number_(fields.get("Balance")))
        display.setdefault(key, name)

    known = set(sales) | set(arr) | set(customers)
    for row in store.rows_of_type("credit_note"):
        fields = row.get("fields") or {}
        raw = clean_text(fields.get("Party Name") or fields.get("Account Name"))
        if not raw:
            continue
        amount = number_(fields.get("Net Amount"))
        if amount <= 0:
            continue
        key = resolve_credit_party(raw, known)
        credits[key] += amount
        display.setdefault(key, raw)

    out = {}
    for key in set(sales) | set(collection) | set(arr) | set(credits):
        sales_amt = _round2(sales.get(key, 0.0))
        coll_amt = _round2(collection.get(key, 0.0))
        credit_amt = _round2(credits.get(key, 0.0))
        out[key] = {
            "name": display.get(key, key),
            "sales": sales_amt,
            "collection": coll_amt,
            "credit_notes": credit_amt,
            "gap": _round2(sales_amt - coll_amt - credit_amt),
            "has_arr": key in arr,
            "arr": arr.get(key),
        }
    return out


def opening_from_gap(due, gap):
    """Part of the outstanding balance that no sale covers.

    Receipts and credit notes settle sales first. The balance is then
    associated with whatever sales remain. The rest, with no sale left, is
    the opening. When sales already exceed the balance, the opening is 0 and
    the excess stays a mismatch.
    """
    due = _round2(due)
    gap = _round2(gap)
    if due <= 0 or gap >= due:
        return 0.0
    return _round2(due - max(gap, 0.0))


def balance_parts(entry):
    """Gap, opening, ARR balance, and (opening + gap − ARR)."""
    entry = entry or {}
    sales = _round2(entry.get("sales") or 0)
    collection = _round2(entry.get("collection") or 0)
    credits = _round2(entry.get("credit_notes") or 0)
    gap = entry.get("gap")
    if gap is None:
        gap = _round2(sales - collection - credits)
    else:
        gap = _round2(gap)
    if not entry.get("has_arr"):
        return gap, 0.0, None, None
    arr = _round2(entry.get("arr") or 0)
    opening = opening_from_gap(arr, gap)
    diff = _round2(opening + gap - arr)
    return gap, opening, arr, diff


def classify_ledger(entry, tolerance):
    """Return mismatch, missing_arr, or ''."""
    entry = entry or {}
    tolerance = float(tolerance or 0)
    sales = entry.get("sales") or 0
    collection = entry.get("collection") or 0
    if not entry.get("has_arr"):
        if sales == 0 and collection == 0 and (entry.get("credit_notes") or 0) == 0:
            return ""
        return "missing_arr"
    _gap, _opening, _arr, diff = balance_parts(entry)
    if abs(diff) >= tolerance:
        return "mismatch"
    return ""


def fields_for(entry, tolerance):
    entry = entry or {"sales": 0, "collection": 0, "gap": 0, "has_arr": False, "arr": None}
    gap, opening, arr, diff = balance_parts(entry)
    return {
        "ledger_gap": gap,
        "ledger_opening": opening,
        "arr_balance": arr,
        "balance_diff": diff,
        "balance_issue": classify_ledger(entry, tolerance),
    }


def reconcile_stored_balance(row, tolerance):
    """Recompute a saved customer flag with that customer's opening included."""
    if not row or row.get("arr_balance") is None or row.get("balance_issue") == "missing_arr":
        return row
    gap = row.get("ledger_gap")
    if gap is None:
        return row
    arr = _round2(row.get("arr_balance") or 0)
    opening = opening_from_gap(arr, gap)
    diff = _round2(opening + _round2(gap) - arr)
    row["ledger_opening"] = opening
    row["balance_diff"] = diff
    row["balance_issue"] = "mismatch" if abs(diff) >= float(tolerance or 0) else ""
    return row


_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def _movement_amount(row):
    if isinstance(row, dict):
        return number_(row.get("amount"))
    return number_(row[1])


def _movement_date(row):
    if isinstance(row, dict):
        return row.get("date")
    return row[0]


def build_ar_statement(sales, receipts, credits, due, as_of, start_month=None, tolerance=0.5, opening=0):
    """Month ledger of sales, collection, and credit notes.

    The opening is the part of the outstanding balance that no sale covers.
    It starts the ledger. Each later month opens with the previous balance.
    Mismatch is opening + sales − collection − credit notes − outstanding.
    """
    tolerance = float(tolerance or 0)
    outstanding = _round2(due)
    opening = _round2(opening)
    sales_m = defaultdict(float)
    coll_m = defaultdict(float)
    credit_m = defaultdict(float)

    def add(bucket, rows):
        for row in rows or []:
            d = _movement_date(row)
            if d is None or (as_of is not None and d > as_of):
                continue
            bucket[(d.year, d.month)] += _movement_amount(row)

    add(sales_m, sales)
    add(coll_m, receipts)
    add(credit_m, credits)

    keys = sorted(set(sales_m) | set(coll_m) | set(credit_m))
    active = []
    for key in keys:
        sales_amt = _round2(sales_m[key])
        coll_amt = _round2(coll_m[key])
        credit_amt = _round2(credit_m[key])
        if sales_amt == 0 and coll_amt == 0 and credit_amt == 0:
            continue
        active.append((key, sales_amt, coll_amt, credit_amt))

    total_sales = _round2(sum(item[1] for item in active))
    total_coll = _round2(sum(item[2] for item in active))
    total_credits = _round2(sum(item[3] for item in active))
    ledger = _round2(total_sales - total_coll - total_credits)
    if not active:
        diff = _round2(opening - outstanding)
        return {
            "opening": opening,
            "opening_month": "",
            "sales": 0.0,
            "collection": 0.0,
            "credit_notes": 0.0,
            "ledger": 0.0,
            "balance": opening,
            "outstanding": outstanding,
            "balance_diff": diff,
            "balance_issue": "mismatch" if abs(diff) >= tolerance else "",
            "tolerance": tolerance,
            "years": [],
        }

    end = datetime(active[-1][0][0], active[-1][0][1], 1, 12)
    if as_of is not None:
        end = datetime(as_of.year, as_of.month, 1, 12)
    current_fy = fiscal_year_start(end, start_month)
    running = opening
    years = []
    current = None
    first_year, first_month = active[0][0]
    opening_month = "%s %d" % (_MONTHS[first_month - 1], first_year) if opening else ""
    for (year, month), sales_amt, coll_amt, credit_amt in active:
        month_opening = running
        running = _round2(running + sales_amt - coll_amt - credit_amt)
        cursor = datetime(year, month, 1, 12)
        fy = fiscal_year_start(cursor, start_month)
        key = fy.strftime("%Y-%m-%d")
        if current is None or current["start"] != key:
            current = {
                "label": fy_label(fy),
                "start": key,
                "complete": fy < current_fy,
                "opening": month_opening,
                "sales": 0.0,
                "collection": 0.0,
                "credit_notes": 0.0,
                "balance": running,
                "months": [],
            }
            years.append(current)
        current["sales"] = _round2(current["sales"] + sales_amt)
        current["collection"] = _round2(current["collection"] + coll_amt)
        current["credit_notes"] = _round2(current["credit_notes"] + credit_amt)
        current["balance"] = running
        current["months"].append({
            "label": "%s %d" % (_MONTHS[month - 1], year),
            "start": "%04d-%02d-01" % (year, month),
            "opening": month_opening,
            "sales": sales_amt,
            "collection": coll_amt,
            "credit_notes": credit_amt,
            "balance": running,
        })

    diff = _round2(running - outstanding)
    return {
        "opening": opening,
        "opening_month": opening_month,
        "sales": total_sales,
        "collection": total_coll,
        "credit_notes": total_credits,
        "ledger": ledger,
        "balance": running,
        "outstanding": outstanding,
        "balance_diff": diff,
        "balance_issue": "mismatch" if abs(diff) >= tolerance else "",
        "tolerance": tolerance,
        "years": years,
    }


def annotate_customer(store, name, ledgers=None, tolerance=None):
    if ledgers is None:
        ledgers = getattr(store, "_ar_ledgers", None)
    if tolerance is None:
        tolerance = getattr(store, "_ar_tolerance", None)
    if tolerance is None:
        tolerance = get_org_policy(store)["ar_balance_tolerance"]
    if ledgers is None:
        ledgers = party_ledgers(store)
    key = clean_text(name).lower()
    return fields_for(ledgers.get(key), tolerance)
