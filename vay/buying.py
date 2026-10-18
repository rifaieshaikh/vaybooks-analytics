"""Observed purchases and the ledger exposure just before each one.

A purchase day is a sale date. It is not an order. Cycle language stays
unavailable when the history is too short or the books do not cover it.
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from vay.ledger import money


def _day(value):
    text = str(value or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _median(values):
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        return None
    mid = count // 2
    if count % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def exposure_before(movements, on_date, *, opening_known=True):
    """Net of ledger items strictly before on_date.

    A missing opening does not become zero. An opening without an invoice
    date stays in the amount and is marked unknown age.
    """
    day = _day(on_date)
    if day is None:
        return {"available": False, "amount": None, "age_known": False, "reason": "The purchase date is missing."}
    if not opening_known:
        return {
            "available": False,
            "amount": None,
            "age_known": False,
            "reason": "Opening is unknown, so exposure before this purchase is unavailable.",
        }
    total = Decimal("0")
    age_known = True
    for row in movements or []:
        posted = _day(row.get("date") or row.get("effective_date"))
        if posted is None or posted >= day:
            continue
        amount = money(row.get("amount") or 0)
        if str(row.get("side") or "debit") == "credit":
            total = money(total - amount)
        else:
            total = money(total + amount)
        if row.get("opening") and row.get("unknown_age"):
            age_known = False
    return {"available": True, "amount": total, "age_known": age_known, "reason": ""}


def purchase_behavior(sales, *, as_of, coverage=None, movements=None, opening_known=True, products=None, exposure=None, exposure_exact=True):
    """Summarize observed purchases and the exposure the ledger can support."""
    coverage = coverage or {}
    as_of_day = _day(as_of)
    occasions = {}
    invoices = set()
    value = Decimal("0")
    quantity = Decimal("0")
    quantity_known = False
    for row in sales or []:
        day = _day(row.get("date"))
        if day is None or (as_of_day and day > as_of_day):
            continue
        amount = money(row.get("amount") or 0)
        value = money(value + amount)
        invoice = str(row.get("invoice") or "").strip()
        if invoice:
            invoices.add(invoice.lower())
        slot = occasions.setdefault(day, {"date": day.isoformat(), "amount": Decimal("0"), "invoices": 0})
        slot["amount"] = money(slot["amount"] + amount)
        slot["invoices"] += 1
        if row.get("qty") not in (None, ""):
            quantity_known = True
            quantity = (quantity + Decimal(str(row.get("qty") or 0))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    days = sorted(occasions)
    gaps = [(days[index] - days[index - 1]).days for index in range(1, len(days))]
    median_gap = _median(gaps) if len(gaps) >= 2 else None
    variation = None
    if median_gap is not None and len(gaps) >= 2:
        variation = _median([abs(gap - median_gap) for gap in gaps])
    complete = bool(coverage.get("complete"))
    cycle = "sufficient" if complete and len(days) >= 3 and median_gap is not None else "insufficient"
    days_since = None
    late = False
    if days and as_of_day:
        days_since = (as_of_day - days[-1]).days
    if cycle == "sufficient" and days_since is not None and variation is not None and days_since > median_gap + variation:
        late = True
    first = days[0].isoformat() if days else ""
    start = str(coverage.get("start") or "")[:10]
    if not days:
        customer_kind = "none"
    elif complete and start and start < first:
        customer_kind = "new"
    else:
        customer_kind = "first_seen"
    mix = []
    for row in products or []:
        mix.append({
            "name": row.get("name") or "",
            "amount": float(money(row.get("amount") or 0)),
            "qty": None if row.get("qty") in (None, "") else float(money(row.get("qty") or 0)),
        })
    mix.sort(key=lambda row: (-row["amount"], row["name"].lower()))
    purchases = []
    for day in days:
        before = exposure_before(movements, day.isoformat(), opening_known=opening_known)
        purchases.append({
            "date": day.isoformat(),
            "amount": float(occasions[day]["amount"]),
            "invoices": occasions[day]["invoices"],
            "exposure_before": None if before["amount"] is None else float(before["amount"]),
            "exposure_available": before["available"],
            "age_known": before["age_known"],
            "exposure_reason": before["reason"],
        })
    current = exposure
    exposure_available = current is not None
    uncertain = []
    if not complete:
        uncertain.append("Movement history does not cover this customer.")
    if not opening_known or exposure_exact is False:
        uncertain.append("Opening is unknown. Exposure is not a complete balance.")
    if not exposure_available:
        uncertain.append("Exposure is unavailable.")
    advice = "withhold" if uncertain else "available"
    cycle_reason = ""
    if cycle == "insufficient":
        cycle_reason = "Fewer than three covered purchases, so there is no next-purchase date."
    return {
        "basis": "observed_purchases",
        "order_records": "none",
        "purchase_occasions": len(days),
        "invoice_count": len(invoices) if invoices else sum(occasions[day]["invoices"] for day in days),
        "value": float(value),
        "quantity": None if not quantity_known else float(quantity),
        "product_mix": mix[:5],
        "median_gap_days": None if median_gap is None else float(median_gap),
        "gap_variation_days": None if variation is None else float(variation),
        "days_since_last_purchase": days_since,
        "late_cycle": late,
        "cycle_evidence": cycle,
        "cycle_reason": cycle_reason,
        "next_purchase": None,
        "customer_kind": customer_kind,
        "customer_kind_label": {
            "new": "New customer",
            "first_seen": "First seen in the available history",
            "none": "No purchases",
        }.get(customer_kind, customer_kind),
        "exposure": None if current is None else float(money(current)),
        "exposure_available": exposure_available,
        "exposure_exact": bool(exposure_exact) and exposure_available,
        "advice": advice,
        "uncertain": uncertain,
        "purchases": purchases,
        "evidence": "Sales dates and amounts. Not orders.",
    }
