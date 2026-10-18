"""Recovery targets and collection pools.

Overlapping buckets are reported separately and are not added together.
A promise or a target is a commitment against debt that already exists.
"""

from decimal import Decimal

from vay.ledger import money


def _amount(value):
    return money(value or 0)


def recovery_pools(items):
    """Split open debt into visible buckets that must not be summed.

    An item lands in one bucket: restricted credit, unknown age, disputed,
    then overdue. Actionable debt is only the overdue bucket.
    """
    overdue = Decimal("0")
    unknown_age = Decimal("0")
    disputed = Decimal("0")
    restricted = Decimal("0")
    for row in items or []:
        amount = _amount(row.get("remaining"))
        if amount <= 0:
            continue
        if row.get("restricted"):
            restricted = money(restricted + amount)
        elif row.get("unknown_age"):
            unknown_age = money(unknown_age + amount)
        elif row.get("disputed"):
            disputed = money(disputed + amount)
        elif row.get("overdue"):
            overdue = money(overdue + amount)
    return {
        "overdue": overdue,
        "unknown_age": unknown_age,
        "disputed": disputed,
        "restricted_credit": restricted,
        "actionable": overdue,
        "eligibility": {
            "overdue": "Known due date on or before the cutoff, and not disputed or restricted.",
            "unknown_age": "Visible, and excluded from the actionable and assigned pools.",
            "disputed": "Visible, and excluded until the dispute is closed.",
            "restricted_credit": "Visible unused credit that cannot be applied. It is not collectible cash.",
            "actionable": "The overdue bucket alone. Promises and targets are not added to it.",
        },
    }


def _active_target(row):
    return str(row.get("status") or "open") == "open"


def assign_targets(targets, actionable):
    """Cap open targets so their assigned amounts cannot exceed actionable debt.

    Superseded and cancelled targets stay in the history and add nothing.
    """
    room = _amount(actionable)
    assigned = Decimal("0")
    rows = []
    ordered = sorted(
        targets or [],
        key=lambda row: (str(row.get("created_at") or ""), str(row.get("id") or "")),
    )
    for row in ordered:
        wanted = _amount(row.get("assigned_amount"))
        if not _active_target(row):
            counted = Decimal("0")
        else:
            counted = wanted if wanted <= room else room
            room = money(room - counted)
            assigned = money(assigned + counted)
        rows.append({
            "id": row.get("id") or "",
            "assigned_amount": wanted,
            "counted": counted,
            "baseline_amount": _amount(row.get("baseline_amount")),
            "status": row.get("status") or "open",
            "owner": row.get("owner") or "",
        })
    return {"assigned": assigned, "targets": rows}


def promise_outcome(
    amount,
    cash_allocated,
    non_cash_allocated,
    promised_on,
    paid_on,
    as_of,
    complete_through,
    *,
    cancelled=False,
    superseded=False,
):
    """Classify a cash promise. A credit note never counts as kept."""
    promised = _amount(amount)
    cash = _amount(cash_allocated)
    non_cash = _amount(non_cash_allocated)
    if cash > promised:
        cash = promised
    debt_remaining = money(promised - cash - non_cash)
    if debt_remaining < 0:
        debt_remaining = Decimal("0")
    cash_remaining = money(promised - cash)
    if cancelled:
        return {"payment_status": "cancelled", "remaining": debt_remaining, "cash_kept": False}
    if superseded:
        return {"payment_status": "superseded", "remaining": Decimal("0"), "cash_kept": False}
    if debt_remaining <= 0 and cash_remaining > 0:
        return {"payment_status": "non_cash", "remaining": Decimal("0"), "cash_kept": False}
    if cash_remaining <= 0:
        late = bool(paid_on and promised_on and str(paid_on) > str(promised_on))
        return {
            "payment_status": "kept_late" if late else "kept_on_time",
            "remaining": Decimal("0"),
            "cash_kept": True,
        }
    covered = bool(complete_through and promised_on and str(complete_through) >= str(promised_on))
    if promised_on and as_of and str(promised_on) < str(as_of) and not covered:
        return {"payment_status": "awaiting_data", "remaining": debt_remaining, "cash_kept": False}
    if promised_on and as_of and str(promised_on) < str(as_of) and covered:
        return {"payment_status": "missed", "remaining": debt_remaining, "cash_kept": False}
    if cash > 0 or non_cash > 0:
        return {"payment_status": "partial", "remaining": debt_remaining, "cash_kept": False}
    return {"payment_status": "open", "remaining": debt_remaining, "cash_kept": False}


def _debt_keys(target):
    keys = set()
    for debt_id in target.get("debt_ids") or []:
        text = str(debt_id or "").strip().lower()
        if text:
            keys.add(text)
    for debt in target.get("debts") or []:
        for field in ("id", "invoice", "invoice_number"):
            text = str(debt.get(field) or "").strip().lower()
            if text:
                keys.add(text)
    return keys


def apply_recovery(targets, receipts, promises=None, allocations=None):
    """Reduce each open target from receipts that match its selected debts.

    Each receipt is spent once across open targets. Actual cash is the receipt
    total, counted once, whether or not a target claims it. A credit note
    reduces the target and stays out of the cash totals. The linked amount is
    an attribution, not proof the target caused the payment.
    """
    promise_rows = {str(row.get("id") or ""): row for row in promises or []}
    by_receipt = {}
    for row in allocations or []:
        if row.get("voided_at"):
            continue
        key = (str(row.get("source_type") or "receipt"), str(row.get("source_uk") or row.get("receipt_id") or ""))
        by_receipt.setdefault(key, []).append(row)
    room = {}
    ordered_receipts = sorted(
        receipts or [],
        key=lambda row: (str(row.get("date") or ""), str(row.get("uk") or row.get("id") or "")),
    )
    for row in ordered_receipts:
        key = (str(row.get("source_type") or "receipt"), str(row.get("uk") or row.get("id") or ""))
        room[key] = _amount(row.get("amount"))
    actual = Decimal("0")
    non_cash_total = Decimal("0")
    for row in ordered_receipts:
        amount = _amount(row.get("amount"))
        if str(row.get("source_type") or "receipt") == "credit_note" or row.get("cash") is False:
            non_cash_total = money(non_cash_total + amount)
        else:
            actual = money(actual + amount)
    linked = Decimal("0")
    applied_non_cash = Decimal("0")
    updated = []
    ordered_targets = sorted(
        targets or [],
        key=lambda row: (str(row.get("created_at") or ""), str(row.get("id") or "")),
    )
    for target in ordered_targets:
        assigned = _amount(target.get("assigned_amount"))
        if not _active_target(target):
            updated.append({
                "id": target.get("id") or "",
                "remaining": _amount(target.get("remaining") if target.get("remaining") is not None else 0),
                "cash_applied": _amount(target.get("cash_applied")),
                "non_cash_applied": _amount(target.get("non_cash_applied")),
            })
            continue
        keys = _debt_keys(target)
        need = assigned
        got_cash = Decimal("0")
        got_non_cash = Decimal("0")
        customer = str(target.get("customer_name") or "").strip().lower()
        for row in ordered_receipts:
            if need <= 0:
                break
            if customer and str(row.get("name") or "").strip().lower() != customer:
                continue
            token = (str(row.get("source_type") or "receipt"), str(row.get("uk") or row.get("id") or ""))
            invoice = str(row.get("invoice") or "").strip().lower()
            eligible = _amount(row.get("amount")) if invoice and invoice in keys else Decimal("0")
            if eligible <= 0:
                for alloc in by_receipt.get(token, []):
                    promise = promise_rows.get(str(alloc.get("promise_id") or ""))
                    refs = {str(ref).strip().lower() for ref in (promise or {}).get("invoice_refs") or []}
                    if keys and refs.intersection(keys):
                        eligible = money(eligible + _amount(alloc.get("amount")))
            if eligible <= 0 or token not in room or room[token] <= 0:
                continue
            take = eligible if eligible <= room[token] else room[token]
            if take > need:
                take = need
            room[token] = money(room[token] - take)
            need = money(need - take)
            is_cash = str(row.get("source_type") or "receipt") != "credit_note" and row.get("cash") is not False
            if is_cash:
                got_cash = money(got_cash + take)
            else:
                got_non_cash = money(got_non_cash + take)
        linked = money(linked + got_cash)
        applied_non_cash = money(applied_non_cash + got_non_cash)
        updated.append({
            "id": target.get("id") or "",
            "remaining": money(assigned - got_cash - got_non_cash),
            "cash_applied": got_cash,
            "non_cash_applied": got_non_cash,
        })
    return {
        "actual_cash": actual,
        "target_linked_cash": linked,
        "non_cash_resolutions": non_cash_total,
        "targets": updated,
    }


def attribute_receipts(receipts, claims):
    """Spend each receipt once across promise and target claims.

    The result is an attribution, not proof that the receipt was paid because
    of the promise. Credit notes cannot satisfy a cash claim.
    """
    room = {}
    cash = {}
    for row in receipts or []:
        key = str(row.get("id") or "")
        room[key] = _amount(row.get("amount"))
        cash[key] = bool(row.get("cash", True))
    accepted = []
    linked = Decimal("0")
    non_cash = Decimal("0")
    for claim in claims or []:
        key = str(claim.get("receipt_id") or "")
        wanted = _amount(claim.get("amount"))
        if key not in room or wanted <= 0:
            accepted.append({"id": claim.get("id") or "", "amount": Decimal("0")})
            continue
        if claim.get("cash_only") and not cash.get(key):
            accepted.append({"id": claim.get("id") or "", "amount": Decimal("0")})
            continue
        take = wanted if wanted <= room[key] else room[key]
        room[key] = money(room[key] - take)
        accepted.append({"id": claim.get("id") or "", "amount": take})
        if cash.get(key):
            linked = money(linked + take)
        else:
            non_cash = money(non_cash + take)
    actual = Decimal("0")
    for row in receipts or []:
        if row.get("cash", True):
            actual = money(actual + _amount(row.get("amount")))
    return {
        "actual_cash": actual,
        "target_linked_cash": linked,
        "non_cash_resolutions": non_cash,
        "claims": accepted,
    }


def cap_commitments(promises, actionable):
    """Keep the sum of open promise remainders inside the actionable pool."""
    room = _amount(actionable)
    counted = Decimal("0")
    ordered = sorted(
        promises or [],
        key=lambda row: (str(row.get("promised_on") or ""), str(row.get("id") or "")),
    )
    rows = []
    for row in ordered:
        status = str(row.get("payment_status") or "")
        if status in ("cancelled", "superseded", "kept", "kept_on_time", "kept_late"):
            counted_amount = Decimal("0")
            remaining = Decimal("0")
        else:
            remaining = _amount(row.get("remaining"))
            counted_amount = remaining if remaining <= room else room
            room = money(room - counted_amount)
            counted = money(counted + counted_amount)
        rows.append({
            "id": row.get("id") or "",
            "remaining": _amount(row.get("remaining")),
            "counted": counted_amount,
        })
    return {"remaining_promises": counted, "promises": rows}


def planned_inflows(promises, targets):
    """One planned amount per customer: the larger of the promise and the target.

    Closing a task is ignored. Paid status is not read from task state.
    """
    by_customer = {}
    for row in promises or []:
        status = str(row.get("payment_status") or "")
        if status not in ("open", "partial"):
            continue
        name = str(row.get("customer_name") or "").strip().lower()
        by_customer[name] = money(by_customer.get(name, Decimal("0")) + _amount(row.get("remaining")))
    for row in targets or []:
        if not _active_target(row):
            continue
        name = str(row.get("customer_name") or "").strip().lower()
        remaining = _amount(row.get("remaining") if row.get("remaining") is not None else row.get("assigned_amount"))
        current = by_customer.get(name, Decimal("0"))
        if remaining > current:
            by_customer[name] = remaining
    total = Decimal("0")
    for amount in by_customer.values():
        total = money(total + amount)
    return {"amount": total, "by_customer": by_customer}


def owner_outcomes(targets):
    """What each owner still has open, and what was reassigned away."""
    owners = {}
    for row in targets or []:
        owner = str(row.get("owner") or "")
        bucket = owners.setdefault(owner, {
            "owner": owner,
            "open_assigned": Decimal("0"),
            "baseline": Decimal("0"),
            "superseded": Decimal("0"),
        })
        baseline = _amount(row.get("baseline_amount"))
        assigned = _amount(row.get("assigned_amount"))
        if _active_target(row):
            bucket["open_assigned"] = money(bucket["open_assigned"] + assigned)
            bucket["baseline"] = money(bucket["baseline"] + baseline)
        elif str(row.get("status") or "") == "superseded":
            bucket["superseded"] = money(bucket["superseded"] + baseline)
    return list(owners.values())
