"""Collection settlement and configurable aging helpers.

Shared by Customer/Group/Rep 360 and performance reports (no store/Mongo).

Settlement modes (receipts):
  oldest   — opening first, then invoices oldest → newest (default)
  specific — match Invoice No first; remainder (or no match) uses oldest FIFO

Outstanding (due): always LIFO on invoice remainders after settlement;
fully settled invoices are excluded; leftover ARR → opening.

Age bands: configurable list of {key, label, max_days|null}; last band is open-ended.
"""

from __future__ import annotations

import json
from datetime import datetime

from vay.dates import clean_text, fiscal_year_start, number_

SETTLEMENT_MODES = ("oldest", "specific")
DEFAULT_SETTLEMENT_MODE = "oldest"


def normalize_customer_accounts(names):
    """Lowercased Account Name keys that count as customers for collection."""
    if names is None:
        return None
    out = set()
    for name in names:
        key = clean_text(name).lower()
        if key:
            out.add(key)
    return frozenset(out)


def is_collection_customer(account_name, ctx=None):
    """Whether a receipt Account Name counts toward collection totals.

    When ctx['customer_accounts'] is set, only those customers count.
    When unset (offline unit tests), all accounts count — INVESTMENT rep is
    still filtered separately by callers.
    """
    key = clean_text(account_name).lower()
    if not key:
        return False
    allowed = (ctx or {}).get("customer_accounts")
    if allowed is None:
        return True
    return key in allowed


DEFAULT_AGING_BANDS = (
    {"key": "d0_15", "label": "0–15", "max_days": 15},
    {"key": "d15_30", "label": "15–30", "max_days": 30},
    {"key": "d30_45", "label": "30–45", "max_days": 45},
    {"key": "d45_60", "label": "45–60", "max_days": 60},
    {"key": "d60_90", "label": "60–90", "max_days": 90},
    {"key": "d90", "label": "90+", "max_days": None},
)

# Compat aliases for callers that still import these
BUCKET_KEYS = tuple(b["key"] for b in DEFAULT_AGING_BANDS)
BUCKET_LABELS = {b["key"]: b["label"] for b in DEFAULT_AGING_BANDS}


def default_aging_bands():
    return [dict(b) for b in DEFAULT_AGING_BANDS]


def normalize_mode(mode):
    text = clean_text(mode).lower()
    if text == "latest":
        return DEFAULT_SETTLEMENT_MODE  # migrate removed mode
    if text in SETTLEMENT_MODES:
        return text
    return DEFAULT_SETTLEMENT_MODE


def normalize_aging_bands(bands):
    """Validate/normalize band list. Raises ValueError on bad input."""
    if bands is None or bands == "":
        return default_aging_bands()
    if isinstance(bands, str):
        try:
            bands = json.loads(bands)
        except (TypeError, ValueError) as exc:
            raise ValueError("Aging bands must be valid JSON") from exc
    if not isinstance(bands, (list, tuple)) or len(bands) < 1:
        raise ValueError("At least one aging band is required")
    out = []
    prev_max = None
    keys = set()
    for i, raw in enumerate(bands):
        if not isinstance(raw, dict):
            raise ValueError("Each aging band must be an object")
        key = clean_text(raw.get("key") or ("d%d" % i))
        if not key or key in keys:
            raise ValueError("Aging band keys must be unique and non-empty")
        keys.add(key)
        label = clean_text(raw.get("label")) or key
        max_raw = raw.get("max_days")
        is_last = i == len(bands) - 1
        if is_last:
            max_days = None
        else:
            if max_raw is None or max_raw == "":
                raise ValueError("Only the last aging band may be open-ended")
            max_days = int(max_raw)
            if max_days < 0:
                raise ValueError("max_days must be >= 0")
            if prev_max is not None and max_days <= prev_max:
                raise ValueError("Aging band max_days must increase")
            prev_max = max_days
        out.append({"key": key, "label": label, "max_days": max_days})
    return out


def band_keys(bands=None):
    bands = bands or DEFAULT_AGING_BANDS
    return tuple(b["key"] for b in bands)


def band_labels(bands=None):
    bands = bands or DEFAULT_AGING_BANDS
    return {b["key"]: b["label"] for b in bands}


def empty_buckets(bands=None):
    return {k: 0.0 for k in band_keys(bands)}


def age_days(as_of, d):
    if not d or not as_of:
        return 0
    a = datetime(as_of.year, as_of.month, as_of.day)
    b = datetime(d.year, d.month, d.day)
    return max(0, (a - b).days)


def bucket_key(days, bands=None):
    """Map age in days to a band key using configured (or default) bands."""
    bands = bands or DEFAULT_AGING_BANDS
    days = max(0, int(days or 0))
    for band in bands:
        mx = band.get("max_days")
        if mx is None:
            return band["key"]
        if days <= int(mx):
            return band["key"]
    return bands[-1]["key"]


def sort_invoices_fifo(invoices):
    """Oldest → newest."""
    return sorted(invoices or [], key=lambda x: x.get("date") or datetime.min)


def sort_invoices_lifo(invoices):
    """Newest → oldest."""
    return sorted(invoices or [], key=lambda x: x.get("date") or datetime.min, reverse=True)


def estimate_opening_amount(due, invoices, receipts, credits=None):
    """Reconstruct opening balance before applying receipts and credit notes.

    opening = max(0, ARR due + receipts + credit notes − invoice amounts)

    The AR snapshot is already net of credit notes, so the credit-note total
    has to be added back or opening is short by that amount.
    """
    inv_total = sum(max(0.0, number_(inv.get("amount"))) for inv in (invoices or []))
    rec_total = sum(max(0.0, number_(r.get("amount"))) for r in (receipts or []))
    credit_total = sum(max(0.0, number_(c.get("amount"))) for c in (credits or []))
    return max(0.0, number_(due) + rec_total + credit_total - inv_total)


def _invoice_match_key(inv):
    inv_no = clean_text(inv.get("invoice") or "").lower()
    if inv_no:
        return inv_no
    return clean_text(inv.get("invoice_id") or "").lower()


def _line_from_inv(inv, take, age, fmt_day=None, iso=None):
    line = {
        "kind": "sale",
        "what": "Sale",
        "due": take,
        "age_days": age,
        "invoice": inv.get("invoice") or "",
        "invoice_id": inv.get("invoice_id") or "",
        "_date": inv.get("date"),
    }
    if iso:
        line["date"] = iso(inv.get("date"))
    else:
        line["date"] = inv.get("date")
    if fmt_day:
        line["date_label"] = fmt_day(inv.get("date"))
    return line


def _opening_line(opening_dt, take, age, fmt_day=None, iso=None):
    line = {
        "kind": "opening",
        "what": "Opening balance",
        "due": take,
        "age_days": age,
        "invoice": "",
        "invoice_id": "",
        "_date": opening_dt,
    }
    if iso:
        line["date"] = iso(opening_dt)
    else:
        line["date"] = opening_dt
    if fmt_day:
        line["date_label"] = fmt_day(opening_dt)
    return line


def allocate_collections(invoices, receipts, as_of, opening_dt=None, mode=None, due=None, bands=None, credits=None):
    """Apply receipts; return (collection_buckets, allocations, credit, open_invoices).

    open_invoices: list of invoice dicts with remaining > 0 after settlement
    (also includes opening_remaining on a synthetic field via return).

    Returns also opening_remaining after settlement as 5th value... keep 3-tuple
    and put remainders on invoice objects + return opening_left via allocations.

    Actually return: buckets, allocations, credit, invoice_remainders, opening_left
    where invoice_remainders are copies of opens with remaining after settlement.
    """
    mode = normalize_mode(mode)
    bands = bands or DEFAULT_AGING_BANDS
    opening_dt = opening_dt or fiscal_year_start(as_of)
    opens = []
    for inv in invoices or []:
        amt = max(0.0, number_(inv.get("amount")))
        if amt <= 0:
            continue
        opens.append({
            "date": inv.get("date"),
            "amount": amt,
            "remaining": amt,
            "invoice": inv.get("invoice") or "",
            "invoice_id": inv.get("invoice_id") or "",
            "kind": "sale",
        })

    ordered_receipts = sorted(
        [r for r in (receipts or []) if r.get("date") and number_(r.get("amount")) > 0],
        key=lambda r: r["date"],
    )
    ordered_credits = sorted(
        [c for c in (credits or []) if c.get("date") and number_(c.get("amount")) > 0],
        key=lambda c: c["date"],
    )

    if due is None:
        opening_remaining = 0.0
    else:
        opening_remaining = estimate_opening_amount(due, invoices, ordered_receipts, ordered_credits)

    opening_target = {
        "date": opening_dt,
        "remaining": opening_remaining,
        "invoice": "",
        "invoice_id": "",
        "kind": "opening",
    }

    buckets = empty_buckets(bands)
    allocations = []
    credit = 0.0

    def apply_to(target, take, event_date, left_ref, collect=True):
        if take <= 0:
            return left_ref
        target["remaining"] = max(0.0, target["remaining"] - take)
        left_ref -= take
        if collect:
            age = age_days(event_date, target["date"])
            buckets[bucket_key(age, bands)] += take
            allocations.append({
                "amount": take,
                "age_days": age,
                "kind": target["kind"],
                "invoice": target.get("invoice") or "",
                "invoice_id": target.get("invoice_id") or "",
                "receipt_date": event_date,
                "target_date": target["date"],
            })
        return left_ref

    def apply_fifo(left, event_date, collect=True):
        """Opening first, then oldest → newest invoices."""
        if left <= 0:
            return left
        take = min(left, max(0.0, opening_target["remaining"]))
        if take > 0:
            left = apply_to(opening_target, take, event_date, left, collect=collect)
        if left <= 0:
            return left
        for target in sort_invoices_fifo(opens):
            if left <= 0:
                break
            if target["remaining"] <= 0:
                continue
            take = min(left, target["remaining"])
            left = apply_to(target, take, event_date, left, collect=collect)
        return left

    movements = [("receipt", row) for row in ordered_receipts]
    movements.extend(("credit_note", row) for row in ordered_credits)
    movements.sort(key=lambda item: item[1]["date"])

    for kind, event in movements:
        left = number_(event.get("amount"))
        event_date = event["date"]
        collect = kind == "receipt"
        event_inv = clean_text(event.get("invoice") or "").lower()

        if collect and mode == "specific" and event_inv:
            for target in opens:
                if target["remaining"] <= 0:
                    continue
                if _invoice_match_key(target) == event_inv:
                    take = min(left, target["remaining"])
                    left = apply_to(target, take, event_date, left, collect=True)
                    break
            # Remainder (or unmatched): Oldest to latest FIFO
            left = apply_fifo(left, event_date, collect=True)
        else:
            # Credit notes always clear oldest open first. Their own invoice
            # number is the credit-note document, not a sales invoice.
            left = apply_fifo(left, event_date, collect=collect)

        if left > 0:
            credit += left

    remainders = [dict(o) for o in opens if o["remaining"] > 0]
    opening_left = max(0.0, opening_target["remaining"])
    return buckets, allocations, credit, remainders, opening_left


def allocate_open(
    invoices,
    due,
    as_of,
    opening_dt=None,
    mode=None,
    fmt_day=None,
    iso=None,
    receipts=None,
    bands=None,
    credits=None,
):
    """Attribute ARR outstanding LIFO on post-settlement invoice remainders.

    Fully settled invoices are excluded. Leftover due → opening.
    Settlement mode only affects how receipts clear invoices first.
    """
    mode = normalize_mode(mode)
    bands = bands or DEFAULT_AGING_BANDS
    outstanding = max(0.0, number_(due))
    opening_dt = opening_dt or fiscal_year_start(as_of)

    _col, _allocs, _credit, remainders, opening_left_after = allocate_collections(
        invoices,
        receipts or [],
        as_of,
        opening_dt=opening_dt,
        mode=mode,
        due=due,
        bands=bands,
        credits=credits,
    )

    # Attribute current ARR due against remaining open invoice balances (LIFO).
    # remainders already exclude fully settled invoices.
    open_lines = []
    remaining = outstanding
    for inv in sort_invoices_lifo(remainders):
        if remaining <= 0:
            break
        open_amt = max(0.0, number_(inv.get("remaining")))
        if open_amt <= 0:
            continue
        take = min(remaining, open_amt)
        remaining -= take
        age = age_days(as_of, inv.get("date"))
        open_lines.append(_line_from_inv(inv, take, age, fmt_day=fmt_day, iso=iso))

    if remaining > 0:
        age = age_days(as_of, opening_dt)
        open_lines.append(_opening_line(opening_dt, remaining, age, fmt_day=fmt_day, iso=iso))

    buckets = empty_buckets(bands)
    for line in open_lines:
        buckets[bucket_key(line["age_days"], bands)] += line["due"]
    opening_amount = 0.0
    for line in open_lines:
        if line["kind"] == "opening":
            opening_amount = line["due"]
            break
    return open_lines, buckets, opening_amount, opening_dt


def oldest_due_invoice(open_lines):
    """Oldest still-due *sale invoice* from allocate_open lines.

    Prefer sale lines (what Due shows as invoices). Opening balance is aged from
    fiscal-year start and is not a due invoice — use it only when no sales remain.
    """
    lines = [
        line for line in (open_lines or [])
        if number_(line.get("due") if line.get("due") is not None else line.get("amount") or 0) >= 0.005
    ]
    invoices = [line for line in lines if clean_text(line.get("kind")).lower() != "opening"]
    pool = invoices if invoices else lines
    if not pool:
        return {"age_days": 0, "kind": "", "what": "", "invoice": ""}
    best = max(pool, key=lambda line: int(number_(line.get("age_days") or 0)))
    kind = clean_text(best.get("kind")).lower() or "sale"
    return {
        "age_days": int(number_(best.get("age_days") or 0)),
        "kind": kind,
        "what": clean_text(best.get("what") or best.get("invoice") or kind),
        "invoice": clean_text(best.get("invoice") or ""),
    }


def flatten_owe(buckets, bands=None):
    b = buckets or empty_buckets(bands)
    keys = band_keys(bands) if bands else (
        tuple(b.keys()) if b else BUCKET_KEYS
    )
    if not keys:
        keys = BUCKET_KEYS
    # Prefer keys from buckets if custom
    if b:
        keys = tuple(b.keys())
    return {k: b.get(k) or 0.0 for k in keys}


def flatten_collection(buckets, prefix="c_", bands=None):
    flat = flatten_owe(buckets, bands=bands)
    return {prefix + k: v for k, v in flat.items()}


def sales_age_bucket_index(d, ctx, bands=None):
    """Index into salesBands list: 0 = newest band … last = oldest."""
    bands = bands or ctx.get("aging_bands") or DEFAULT_AGING_BANDS
    if not d:
        return len(bands) - 1
    as_of = ctx.get("reportDate")
    if not as_of:
        return len(bands) - 1
    key = bucket_key(age_days(as_of, d), bands)
    for i, band in enumerate(bands):
        if band["key"] == key:
            return i
    return len(bands) - 1


def owe_header_keys(bands=None):
    bands = bands or DEFAULT_AGING_BANDS
    return [("owe_" + b["key"], "Due %s Days" % b["label"]) for b in bands]


def collection_header_keys(bands=None):
    bands = bands or DEFAULT_AGING_BANDS
    return [("col_" + b["key"], "Collection %s Days" % b["label"]) for b in bands]


# Compat names used by reports
OWE_HEADER_KEYS = owe_header_keys()
COLLECTION_HEADER_KEYS = collection_header_keys()
