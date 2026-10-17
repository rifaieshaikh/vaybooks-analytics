"""Shared settlement contracts and the pure ledger engine.

No database and no UI. Money is decimal, half-up to 0.01. Quantities are
decimal, half-up to 0.0001. An account is organization + legal entity +
customer + currency. Missing evidence stays missing; it is never stored as zero.

Policies
  invoice_date_fifo   Opening debt first, then invoice issue date. Default.
  due_date_priority   Automatic allocation follows due date. Unknown due dates last.
  explicit_only       Confirmed links and unique references only. No FIFO.

A referenced remainder stays unapplied. An explicit reference that does not
match is unresolved and is not settled onto an unrelated invoice.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

ENGINE_VERSION = "1"
MONEY = Decimal("0.01")
QTY = Decimal("0.0001")

POLICY_INVOICE_FIFO = "invoice_date_fifo"
POLICY_DUE_DATE = "due_date_priority"
POLICY_EXPLICIT = "explicit_only"
POLICIES = (POLICY_INVOICE_FIFO, POLICY_DUE_DATE, POLICY_EXPLICIT)

EVIDENCE_SOURCE = "source_confirmed"
EVIDENCE_MANUAL = "manually_confirmed"
EVIDENCE_INFERRED = "inferred"
CONFIRMED_EVIDENCE = (EVIDENCE_SOURCE, EVIDENCE_MANUAL)

STATUS_IMPORTED = "imported"
STATUS_RECONSTRUCTED = "reconstructed"
STATUS_ESTIMATED = "estimated"
STATUS_UNRESOLVED = "unresolved"


def money(value):
    """Half-up currency amount. None and blank stay missing."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Amount is not a number")
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, float):
        dec = Decimal(str(value))
    else:
        text = str(value).replace(",", "").strip()
        if not text:
            return None
        dec = Decimal(text)
    return dec.quantize(MONEY, rounding=ROUND_HALF_UP)


def quantity(value):
    """Half-up quantity. None and blank stay missing."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ValueError("Quantity is not a number")
    if isinstance(value, Decimal):
        dec = value
    elif isinstance(value, float):
        dec = Decimal(str(value))
    else:
        text = str(value).replace(",", "").strip()
        if not text:
            return None
        dec = Decimal(text)
    return dec.quantize(QTY, rounding=ROUND_HALF_UP)


def parse_day(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def invoice_age_days(as_of, invoice_day):
    """Days from the invoice date to the cutoff. Unknown dates stay unknown."""
    as_of = parse_day(as_of)
    invoice_day = parse_day(invoice_day)
    if not as_of or not invoice_day:
        return None
    return (as_of - invoice_day).days


def days_overdue(as_of, due_day):
    """Days past the due date. Not-yet-due is 0. A missing due date stays unknown."""
    as_of = parse_day(as_of)
    due_day = parse_day(due_day)
    if not as_of or not due_day:
        return None
    return max(0, (as_of - due_day).days)


def derive_due_date(invoice_day, due_day, terms_days):
    """Source due date wins. Otherwise invoice date plus the terms that were supplied."""
    due_day = parse_day(due_day)
    if due_day:
        return due_day, "source", None
    invoice_day = parse_day(invoice_day)
    if invoice_day is not None and terms_days is not None and terms_days != "":
        return invoice_day + timedelta(days=int(terms_days)), "terms", int(terms_days)
    return None, "unknown", None


def _s(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    return value


class LedgerError(ValueError):
    pass


class _Item:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Alloc:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def _scope_key(row):
    return (
        str(row.get("organization_id") or ""),
        str(row.get("legal_entity_id") or ""),
        str(row.get("customer_id") or ""),
        str(row.get("currency") or ""),
    )


def _debit_from(raw, default_scope):
    amount = money(raw.get("amount"))
    if amount is None:
        raise LedgerError("Debit %s has no amount" % (raw.get("source_id") or ""))
    opening = bool(raw.get("opening"))
    if "invoice_date" in raw:
        invoice_day = parse_day(raw.get("invoice_date"))
    elif opening:
        invoice_day = None
    else:
        invoice_day = parse_day(raw.get("effective_date"))
    due, due_source, terms = derive_due_date(invoice_day, raw.get("due_date"), raw.get("terms_days"))
    return _Item(
        source_id=str(raw.get("source_id") or ""),
        kind=str(raw.get("kind") or ("opening_invoice" if opening else "invoice")),
        amount=amount,
        remaining=amount,
        reversed=money(0),
        opening=opening,
        effective_date=parse_day(raw.get("effective_date")),
        invoice_date=invoice_day,
        due_date=due,
        due_source=due_source,
        terms_days=terms,
        invoice_key=str(raw.get("invoice_key") or raw.get("source_id") or ""),
        invoice_number=str(raw.get("invoice_number") or ""),
        sequence=int(raw.get("sequence") or 0),
        disputed=bool(raw.get("disputed")),
        void=False,
        scope=_scope_key(raw or default_scope),
        date_unknown=invoice_day is None,
    )


def _credit_from(raw):
    amount = money(raw.get("amount"))
    if amount is None:
        raise LedgerError("Credit %s has no amount" % (raw.get("source_id") or ""))
    reference = str(raw.get("reference") or "").strip()
    return _Item(
        source_id=str(raw.get("source_id") or ""),
        kind=str(raw.get("kind") or "receipt"),
        amount=amount,
        remaining=amount,
        reserved=money(0),
        reversed=money(0),
        opening=bool(raw.get("opening")),
        effective_date=parse_day(raw.get("effective_date")),
        reference=reference,
        pre_period=bool(raw.get("pre_period")),
        cash=bool(raw.get("cash", raw.get("kind", "receipt") == "receipt")),
        restricted=bool(raw.get("restricted")),
        sequence=int(raw.get("sequence") or 0),
        no_fifo=bool(reference) or bool(raw.get("restricted")),
        unresolved=False,
        void=False,
        scope=_scope_key(raw),
    )


def settle(
    debits,
    credits,
    links=None,
    reversals=None,
    *,
    policy=POLICY_INVOICE_FIFO,
    as_of,
    checkpoint=None,
    organization_id="",
    legal_entity_id="",
    customer_id="",
    currency="",
):
    """Replay one account through ``as_of`` and return allocations, open items, and exceptions.

    ``checkpoint`` is an optional signed net receivable. Negative means the source
    reports a customer advance. The engine does not invent a receipt to force a match.
    """
    if policy not in POLICIES:
        raise LedgerError("Unknown settlement policy %s" % policy)
    as_of_day = parse_day(as_of)
    if not as_of_day:
        raise LedgerError("as_of is required")
    scope = (str(organization_id), str(legal_entity_id or ""), str(customer_id), str(currency))
    exceptions = []
    suggestions = []

    def reject(code, message, **extra):
        row = {"code": code, "message": message}
        row.update(extra)
        exceptions.append(row)

    debit_rows = []
    for raw in debits or []:
        if _scope_key(raw) != scope:
            reject("scope_mismatch", "Debit is outside this account.", source_id=str(raw.get("source_id") or ""))
            continue
        item = _debit_from(raw, scope)
        if not item.source_id:
            reject("missing_identity", "Debit has no source id.")
            continue
        if item.amount < 0:
            reject("negative_amount", "Debit amount must be nonnegative.", source_id=item.source_id)
            continue
        if item.amount == 0:
            continue
        debit_rows.append(item)

    credit_rows = []
    for raw in credits or []:
        if _scope_key(raw) != scope:
            reject("scope_mismatch", "Credit is outside this account.", source_id=str(raw.get("source_id") or ""))
            continue
        item = _credit_from(raw)
        if not item.source_id:
            reject("missing_identity", "Credit has no source id.")
            continue
        if item.amount < 0:
            reject("negative_amount", "Credit amount must be nonnegative.", source_id=item.source_id)
            continue
        if item.amount == 0:
            continue
        if item.kind != "receipt":
            item.cash = False
        credit_rows.append(item)

    by_debit = {}
    for item in debit_rows:
        if item.source_id in by_debit:
            reject("duplicate_source", "Debit source id is repeated.", source_id=item.source_id)
            continue
        by_debit[item.source_id] = item
    by_credit = {}
    for item in credit_rows:
        if item.source_id in by_credit:
            reject("duplicate_source", "Credit source id is repeated.", source_id=item.source_id)
            continue
        by_credit[item.source_id] = item

    confirmed = []
    for raw in links or []:
        evidence = str(raw.get("evidence") or EVIDENCE_MANUAL)
        if evidence not in CONFIRMED_EVIDENCE:
            reject("bad_evidence", "Confirmed link evidence must be source-confirmed or manually confirmed.", credit_id=str(raw.get("credit_id") or ""))
            continue
        amount = money(raw.get("amount"))
        if amount is None or amount <= 0:
            reject("negative_amount", "Confirmed link amount must be positive.", credit_id=str(raw.get("credit_id") or ""))
            continue
        confirmed.append(_Item(
            credit_id=str(raw.get("credit_id") or ""),
            debit_id=str(raw.get("debit_id") or ""),
            amount=amount,
            evidence=evidence,
            applied=money(0),
        ))

    reversal_rows = []
    for raw in reversals or []:
        amount = money(raw.get("amount")) if raw.get("amount") not in (None, "") else None
        reversal_rows.append(_Item(
            source_id=str(raw.get("source_id") or ""),
            reverses_id=str(raw.get("reverses_id") or ""),
            effective_date=parse_day(raw.get("effective_date")),
            amount=amount,
            sequence=int(raw.get("sequence") or 0),
            opening=False,
        ))

    allocations = []
    open_ids = []

    def in_cutoff(day, opening):
        if opening and day is None:
            return True
        if day is None:
            return False
        return day <= as_of_day

    events = []
    for item in by_debit.values():
        if not in_cutoff(item.effective_date, item.opening):
            continue
        if not item.opening and item.effective_date is None:
            reject("missing_date", "Invoice has no effective date.", source_id=item.source_id)
            continue
        events.append(_Item(kind_order=0, item=item, action="debit", opening=item.opening, effective_date=item.effective_date, sequence=item.sequence, source_id=item.source_id))
    for item in by_credit.values():
        if not in_cutoff(item.effective_date, item.opening):
            continue
        if not item.opening and item.effective_date is None:
            reject("missing_date", "Credit has no effective date.", source_id=item.source_id)
            continue
        events.append(_Item(kind_order=1, item=item, action="credit", opening=item.opening, effective_date=item.effective_date, sequence=item.sequence, source_id=item.source_id))
    for item in reversal_rows:
        if not item.effective_date or item.effective_date > as_of_day:
            if item.effective_date and item.effective_date > as_of_day:
                continue
            reject("missing_date", "Reversal has no effective date.", source_id=item.source_id)
            continue
        events.append(_Item(kind_order=2, item=item, action="reversal", opening=False, effective_date=item.effective_date, sequence=item.sequence, source_id=item.source_id))

    def event_key(ev):
        return (
            0 if ev.opening else 1,
            ev.effective_date is None,
            ev.effective_date or date.min,
            ev.kind_order,
            ev.sequence,
            ev.source_id,
        )

    events.sort(key=event_key)

    def alloc_day(credit, debit):
        days = [day for day in (credit.effective_date, debit.effective_date) if day]
        if not days:
            return None
        return max(days)

    def add_alloc(credit, debit, amount, evidence):
        amount = money(amount)
        if amount is None or amount <= 0:
            return money(0)
        room = debit.remaining
        credit_room = credit.remaining
        take = min(amount, room, credit_room)
        if take <= 0:
            return money(0)
        debit.remaining = money(debit.remaining - take)
        credit.remaining = money(credit.remaining - take)
        allocations.append(_Alloc(
            credit_id=credit.source_id,
            debit_id=debit.source_id,
            amount=take,
            evidence=evidence,
            effective_date=alloc_day(credit, debit),
            cash=credit.cash,
            credit_kind=credit.kind,
            order=len(allocations),
        ))
        return take

    def live_allocations(credit_id=None, debit_id=None):
        rows = []
        for row in allocations:
            if row.amount <= 0:
                continue
            if credit_id and row.credit_id != credit_id:
                continue
            if debit_id and row.debit_id != debit_id:
                continue
            rows.append(row)
        return rows

    def fifo_targets():
        rows = [item for item in open_ids if not by_debit[item].void and by_debit[item].remaining > 0 and not by_debit[item].disputed]
        if policy == POLICY_DUE_DATE:
            rows.sort(key=lambda sid: (
                by_debit[sid].due_date is None,
                by_debit[sid].due_date or date.min,
                by_debit[sid].source_id,
            ))
            return rows
        rows.sort(key=lambda sid: (
            0 if by_debit[sid].opening else 1,
            by_debit[sid].invoice_date is None,
            by_debit[sid].invoice_date or by_debit[sid].effective_date or date.min,
            by_debit[sid].sequence,
            by_debit[sid].source_id,
        ))
        return rows

    def apply_fifo(credit):
        if policy == POLICY_EXPLICIT or credit.restricted or credit.no_fifo or credit.void:
            return
        for sid in fifo_targets():
            free = money(credit.remaining - credit.reserved)
            if free <= 0:
                return
            add_alloc(credit, by_debit[sid], free, EVIDENCE_INFERRED)

    def apply_carried(debit):
        if debit.disputed or debit.void or debit.remaining <= 0:
            return
        if policy == POLICY_EXPLICIT:
            return
        ordered = [by_credit[sid] for sid in by_credit if sid in seen_credits]
        ordered.sort(key=lambda item: (
            item.opening is False,
            item.effective_date is None,
            item.effective_date or date.min,
            item.sequence,
            item.source_id,
        ))
        for credit in ordered:
            if credit.void or credit.restricted or credit.no_fifo or credit.unresolved:
                continue
            if credit.reference:
                continue
            free = money(credit.remaining - credit.reserved)
            if free <= 0:
                continue
            add_alloc(credit, debit, min(free, debit.remaining), EVIDENCE_INFERRED)
            if debit.remaining <= 0:
                return

    def match_reference(reference):
        ref = reference.strip().lower()
        if not ref:
            return None, "missing"
        by_key = [item for item in by_debit.values() if item.invoice_key.lower() == ref]
        if len(by_key) > 1:
            return None, "ambiguous"
        if len(by_key) == 1:
            return by_key[0], "unique"
        by_num = [item for item in by_debit.values() if item.invoice_number and item.invoice_number.lower() == ref]
        if len(by_num) > 1:
            return None, "ambiguous"
        if len(by_num) == 1:
            return by_num[0], "unique"
        return None, "missing"

    def reserve(credit, debit, amount, evidence):
        amount = money(min(amount, money(credit.remaining - credit.reserved)))
        if amount <= 0:
            return money(0)
        credit.reserved = money(credit.reserved + amount)
        credit.holds = getattr(credit, "holds", [])
        credit.holds.append({"debit_id": debit.source_id, "amount": amount, "evidence": evidence})
        return amount

    def release_hold(credit, debit_id, amount):
        left = money(amount)
        kept = []
        for hold in getattr(credit, "holds", []):
            if left > 0 and hold["debit_id"] == debit_id:
                use = money(min(left, hold["amount"]))
                hold["amount"] = money(hold["amount"] - use)
                credit.reserved = money(max(0, credit.reserved - use))
                left = money(left - use)
            if hold["amount"] > 0:
                kept.append(hold)
        credit.holds = kept

    def apply_holds(debit):
        for credit in list(by_credit.values()):
            for hold in list(getattr(credit, "holds", [])):
                if hold["debit_id"] != debit.source_id or hold["amount"] <= 0 or credit.void:
                    continue
                amount = hold["amount"]
                evidence = hold["evidence"]
                release_hold(credit, debit.source_id, amount)
                if debit.void or debit.remaining <= 0:
                    continue
                add_alloc(credit, debit, amount, evidence)

    def apply_confirmed(credit):
        for link in confirmed:
            if link.credit_id != credit.source_id or link.applied >= link.amount:
                continue
            debit = by_debit.get(link.debit_id)
            if debit is None:
                reject("confirmed_target_missing", "Confirmed link does not match a debit in this account.", credit_id=credit.source_id, debit_id=link.debit_id)
                continue
            need = money(link.amount - link.applied)
            if debit.source_id not in open_ids or debit.void:
                parked = money(min(need, money(credit.remaining - credit.reserved)))
                credit.reserved = money(credit.reserved + parked)
                continue
            taken = add_alloc(credit, debit, need, link.evidence)
            link.applied = money(link.applied + taken)
            if taken < need:
                reject(
                    "conflicting_links",
                    "Confirmed link could not be applied in full.",
                    credit_id=credit.source_id,
                    debit_id=debit.source_id,
                )

    def apply_reference(credit):
        debit, status = match_reference(credit.reference)
        credit.no_fifo = True
        if status == "ambiguous":
            credit.unresolved = True
            reject("ambiguous_reference", "Receipt reference matches more than one invoice.", credit_id=credit.source_id, reference=credit.reference)
            return
        if status == "missing":
            if credit.pre_period:
                for sid in fifo_targets():
                    target = by_debit[sid]
                    if not target.opening or credit.remaining <= 0:
                        continue
                    add_alloc(credit, target, credit.remaining, EVIDENCE_INFERRED)
                if credit.remaining > 0:
                    credit.unresolved = True
                    reject("unresolved_reference", "Pre-period reference exceeds opening debt.", credit_id=credit.source_id, reference=credit.reference)
                return
            credit.unresolved = True
            reject("unresolved_reference", "Receipt reference does not match an invoice in this account.", credit_id=credit.source_id, reference=credit.reference)
            _suggest(credit)
            return
        if debit.effective_date and debit.effective_date > as_of_day:
            reject("after_cutoff", "Referenced invoice is after the report cutoff. The credit is carried.", credit_id=credit.source_id, reference=credit.reference)
            return
        if debit.source_id not in open_ids or debit.void:
            reserve(credit, debit, credit.remaining, EVIDENCE_SOURCE)
            return
        if debit.remaining <= 0:
            credit.unresolved = True
            reject("already_settled_reference", "Referenced invoice is already settled. The remainder stays unapplied.", credit_id=credit.source_id, reference=credit.reference)
            return
        taken = add_alloc(credit, debit, credit.remaining, EVIDENCE_SOURCE)
        if credit.remaining > 0 and taken > 0:
            reject("unapplied_remainder", "Referenced receipt exceeds the invoice. The remainder stays unapplied.", credit_id=credit.source_id, debit_id=debit.source_id)

    def _suggest(credit):
        same = [
            by_debit[sid] for sid in open_ids
            if by_debit[sid].remaining == credit.remaining and by_debit[sid].remaining > 0 and not by_debit[sid].void
        ]
        if len(same) == 1:
            suggestions.append({
                "credit_id": credit.source_id,
                "debit_id": same[0].source_id,
                "amount": credit.remaining,
                "reason": "unique_amount",
                "evidence": "suggestion",
            })

    def undo_alloc(row, amount):
        take = money(min(amount, row.amount))
        if take <= 0:
            return money(0)
        row.amount = money(row.amount - take)
        debit = by_debit.get(row.debit_id)
        credit = by_credit.get(row.credit_id)
        if debit and not debit.void:
            debit.remaining = money(debit.remaining + take)
        if credit and not credit.void:
            credit.remaining = money(credit.remaining + take)
        return take

    def reverse_credit(rev):
        credit = by_credit.get(rev.reverses_id)
        if credit is None or credit.source_id not in seen_credits:
            reject("reversal_target_missing", "Reversal does not match a credit in this cutoff.", source_id=rev.source_id, reverses_id=rev.reverses_id)
            return
        left = credit.amount if rev.amount is None else money(min(rev.amount, credit.amount - credit.reversed))
        if left <= 0:
            return
        unused = min(left, credit.remaining)
        credit.remaining = money(credit.remaining - unused)
        left = money(left - unused)
        credit.reversed = money(credit.reversed + unused)
        for row in reversed(live_allocations(credit_id=credit.source_id)):
            if left <= 0:
                break
            taken = undo_alloc(row, left)
            # A bounced receipt is gone. The restored amount is not spent again.
            credit.remaining = money(credit.remaining - taken)
            left = money(left - taken)
            credit.reversed = money(credit.reversed + taken)
        if credit.reversed >= credit.amount:
            credit.void = True
            credit.remaining = money(0)
        for sid in list(open_ids):
            apply_carried(by_debit[sid])

    def reverse_debit(rev):
        debit = by_debit.get(rev.reverses_id)
        if debit is None or debit.source_id not in open_ids and not live_allocations(debit_id=rev.reverses_id):
            reject("reversal_target_missing", "Reversal does not match a debit in this cutoff.", source_id=rev.source_id, reverses_id=rev.reverses_id)
            return
        left = debit.amount if rev.amount is None else money(min(rev.amount, debit.amount - debit.reversed))
        restored = []
        for row in reversed(live_allocations(debit_id=debit.source_id)):
            if left <= 0:
                break
            credit = by_credit.get(row.credit_id)
            taken = undo_alloc(row, left)
            left = money(left - taken)
            debit.reversed = money(debit.reversed + taken)
            if credit:
                restored.append(credit)
        unused = min(left, debit.remaining)
        debit.remaining = money(debit.remaining - unused)
        debit.reversed = money(debit.reversed + unused)
        if debit.reversed >= debit.amount or rev.amount is None:
            debit.void = True
            debit.remaining = money(0)
        for credit in restored:
            if credit.reference or credit.no_fifo:
                credit.unresolved = True
                credit.no_fifo = True
                reject("unresolved_reference", "Credit returned by a reversal keeps its reference and is not applied elsewhere.", credit_id=credit.source_id)
                continue
            apply_fifo(credit)

    seen_credits = set()
    for ev in events:
        if ev.action == "debit":
            debit = ev.item
            if debit.source_id not in open_ids:
                open_ids.append(debit.source_id)
            apply_holds(debit)
            for link in confirmed:
                if link.debit_id != debit.source_id or link.applied >= link.amount:
                    continue
                credit = by_credit.get(link.credit_id)
                if credit is None or credit.source_id not in seen_credits or credit.void:
                    continue
                need = money(link.amount - link.applied)
                credit.reserved = money(max(0, credit.reserved - need))
                taken = add_alloc(credit, debit, need, link.evidence)
                link.applied = money(link.applied + taken)
                if taken < need:
                    reject("conflicting_links", "Confirmed link could not be applied in full.", credit_id=credit.source_id, debit_id=debit.source_id)
            apply_carried(debit)
            continue
        if ev.action == "credit":
            credit = ev.item
            seen_credits.add(credit.source_id)
            apply_confirmed(credit)
            if credit.reference:
                apply_reference(credit)
            else:
                apply_fifo(credit)
            continue
        rev = ev.item
        if rev.reverses_id in by_credit:
            reverse_credit(rev)
        elif rev.reverses_id in by_debit:
            reverse_debit(rev)
        else:
            reject("reversal_target_missing", "Reversal does not match a ledger item.", source_id=rev.source_id, reverses_id=rev.reverses_id)

    for credit in by_credit.values():
        if credit.reserved > 0:
            reject("confirmed_target_missing", "Confirmed amount is still reserved because its invoice is not in this cutoff.", credit_id=credit.source_id)

    open_debits = []
    for sid in open_ids:
        debit = by_debit[sid]
        if debit.void or debit.remaining <= 0:
            continue
        age = invoice_age_days(as_of_day, debit.invoice_date)
        overdue = days_overdue(as_of_day, debit.due_date)
        open_debits.append({
            "source_id": debit.source_id,
            "kind": debit.kind,
            "opening": debit.opening,
            "remaining": debit.remaining,
            "invoice_number": debit.invoice_number,
            "invoice_key": debit.invoice_key,
            "invoice_date": debit.invoice_date,
            "due_date": debit.due_date,
            "due_source": debit.due_source,
            "terms_days": debit.terms_days,
            "invoice_age_days": age,
            "days_overdue": overdue,
            "unknown_age": age is None,
            "disputed": debit.disputed,
        })

    unused_credits = []
    for credit in by_credit.values():
        if credit.void or credit.remaining <= 0 or credit.source_id not in seen_credits:
            continue
        unused_credits.append({
            "source_id": credit.source_id,
            "kind": credit.kind,
            "remaining": credit.remaining,
            "cash": credit.cash,
            "restricted": credit.restricted,
            "unresolved": credit.unresolved,
            "reference": credit.reference,
            "effective_date": credit.effective_date,
            "opening": credit.opening,
            "provenance": "unknown" if credit.opening and credit.effective_date is None else "ledger",
        })

    open_total = money(sum((row["remaining"] for row in open_debits), money(0)))
    unused_total = money(sum((row["remaining"] for row in unused_credits), money(0)))
    ledger_net = money(open_total - unused_total)
    reconciliation = {
        "ledger_net": ledger_net,
        "open_debit": open_total,
        "unused_credit": unused_total,
        "checkpoint_net": None,
        "difference": None,
        "state": "no_checkpoint",
        "net_advance": money(0),
        "advance_origin": "",
        "advance_provenance": "",
    }
    if checkpoint is not None:
        checkpoint_net = money(checkpoint if not isinstance(checkpoint, dict) else checkpoint.get("net"))
        difference = money(ledger_net - checkpoint_net)
        net_advance = money(-checkpoint_net) if checkpoint_net < 0 else money(0)
        explained = money(min(unused_total, net_advance)) if net_advance else money(0)
        reconciliation.update({
            "checkpoint_net": checkpoint_net,
            "difference": difference,
            "net_advance": net_advance,
            "explained_advance": explained,
            "unexplained_advance": money(net_advance - explained) if net_advance else money(0),
        })
        if difference == 0:
            reconciliation["state"] = "reconciled"
            reconciliation["advance_origin"] = "ledger" if net_advance else ""
            reconciliation["advance_provenance"] = "ledger" if net_advance else ""
        elif net_advance > 0 and open_total == 0 and unused_total == 0:
            reconciliation["state"] = "arr_only_advance"
            reconciliation["advance_origin"] = "arr_only"
            reconciliation["advance_provenance"] = "unknown"
            reject("arr_only_advance", "Negative ARR is a net advance with no originating receipt. No receipt was created.", amount=net_advance)
        elif difference != 0:
            reconciliation["state"] = "mismatch"
            reconciliation["advance_origin"] = "ledger" if explained else ""
            reject("reconciliation_mismatch", "Open debits minus unused credits do not match the checkpoint.", difference=difference)

    alloc_out = []
    for row in allocations:
        if row.amount <= 0:
            continue
        debit = by_debit.get(row.debit_id)
        alloc_out.append({
            "credit_id": row.credit_id,
            "debit_id": row.debit_id,
            "amount": row.amount,
            "evidence": row.evidence,
            "effective_date": row.effective_date,
            "invoice_date": debit.invoice_date if debit else None,
            "invoice_number": debit.invoice_number if debit else "",
            "cash": row.cash,
            "credit_kind": row.credit_kind,
            "referenced": bool(getattr(row, "referenced", False) or (by_credit[row.credit_id].reference if row.credit_id in by_credit else False)),
        })

    return {
        "engine_version": ENGINE_VERSION,
        "policy": policy,
        "as_of": as_of_day,
        "organization_id": scope[0],
        "legal_entity_id": scope[1],
        "customer_id": scope[2],
        "currency": scope[3],
        "allocations": alloc_out,
        "receipts": _standing_receipts(by_credit, seen_credits, live_allocations),
        "open_debits": open_debits,
        "unused_credits": unused_credits,
        "suggestions": suggestions,
        "exceptions": exceptions,
        "reconciliation": reconciliation,
    }


def _standing_receipts(by_credit, seen_credits, live_allocations):
    """Cash and non-cash credits that still stand, dated on the credit itself."""
    rows = []
    for credit in by_credit.values():
        if credit.source_id not in seen_credits or credit.void:
            continue
        standing = money(credit.amount - credit.reversed)
        if standing is None or standing <= 0:
            continue
        labels = []
        for row in live_allocations(credit_id=credit.source_id):
            if row.evidence and row.evidence not in labels:
                labels.append(row.evidence)
        if credit.remaining > 0 and "unapplied" not in labels:
            labels.append("unapplied")
        rows.append({
            "source_id": credit.source_id,
            "amount": standing,
            "effective_date": credit.effective_date,
            "cash": credit.cash,
            "evidence": labels,
        })
    return rows


def public_result(result):
    """JSON-safe copy. Amounts stay fixed-point strings."""
    return _public(result)


def _public(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [_public(item) for item in value]
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items()}
    return value


def invariants(result):
    """Return conservation failures. An empty list means the result conserves amounts."""
    problems = []
    taken_from = {}
    taken_to = {}
    for row in result["allocations"]:
        amount = money(row["amount"])
        if amount < 0:
            problems.append("negative allocation")
        taken_from[row["credit_id"]] = money(taken_from.get(row["credit_id"], 0) + amount)
        taken_to[row["debit_id"]] = money(taken_to.get(row["debit_id"], 0) + amount)
    for row in result["open_debits"] + result["unused_credits"]:
        if money(row["remaining"]) < 0:
            problems.append("negative remaining %s" % row["source_id"])
    net = money(result["reconciliation"]["open_debit"] - result["reconciliation"]["unused_credit"])
    if net != money(result["reconciliation"]["ledger_net"]):
        problems.append("net identity")
    return problems


def reconstruct_customer_opening(*, closing_net, debit_movements, credit_movements, movements_complete):
    """Opening net = closing net − debits + credits.

    This matches the checkpoint it was built from. That is an arithmetic tie-out,
    not an independent verification. Incomplete evidence stays unresolved.
    """
    if closing_net is None or not movements_complete:
        return {
            "status": STATUS_UNRESOLVED,
            "amount": None,
            "origin": "missing",
            "evidence": "",
            "tie_out": False,
            "formula": "opening_net = closing_net - debits + credits",
        }
    amount = money(money(closing_net) - money(debit_movements or 0) + money(credit_movements or 0))
    return {
        "status": STATUS_RECONSTRUCTED,
        "amount": amount,
        "origin": "inferred",
        "evidence": EVIDENCE_INFERRED,
        "tie_out": True,
        "formula": "opening_net = closing_net - debits + credits",
    }


def select_customer_opening(imported_net, derived):
    """An imported opening is kept. A derived opening never replaces it."""
    if imported_net is not None:
        return {
            "status": STATUS_IMPORTED,
            "amount": money(imported_net),
            "origin": "imported",
            "evidence": EVIDENCE_SOURCE,
            "tie_out": False,
            "supersedes_derived": derived.get("status") == STATUS_RECONSTRUCTED,
        }
    return dict(derived)


def coverage_overlap(opening_keys, movement_keys):
    left = {str(key).strip().lower() for key in opening_keys if str(key).strip()}
    right = {str(key).strip().lower() for key in movement_keys if str(key).strip()}
    return sorted(left & right)


def normalize_purchases(lines):
    """Count a purchase invoice and its goods receipt once. Unreceived invoices stay planning."""
    groups = {}
    order = []
    for raw in lines or []:
        key = str(raw.get("movement_key") or raw.get("source_id") or "")
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(raw)
    inward = []
    returns = []
    planning = []
    for key in order:
        group = groups[key]
        if any(str(row.get("return_of") or "").strip() for row in group):
            qty = quantity(sum(quantity(row.get("qty") or 0) for row in group))
            returns.append({
                "movement_key": key,
                "qty": qty,
                "kind": "supplier_return",
                "item_id": str(group[0].get("item_id") or ""),
                "location": str(group[0].get("location") or ""),
                "unit": str(group[0].get("unit") or ""),
                "lot": str(group[0].get("lot") or ""),
                "documents": [str(row.get("source_id") or "") for row in group],
            })
            continue
        receipts = [row for row in group if str(row.get("role") or "") == "receipt" or _received(row)]
        invoices = [row for row in group if str(row.get("role") or "invoice") == "invoice"]
        received_rows = [row for row in receipts if _received(row) or str(row.get("role") or "") == "receipt"]
        if received_rows:
            chosen = received_rows
            kind = "purchase_receipt"
        elif invoices and all(_received(row) for row in invoices):
            chosen = invoices
            kind = "purchase_receipt"
        else:
            planning.append({
                "movement_key": key,
                "qty": quantity(sum(quantity(row.get("qty") or 0) for row in group)),
                "kind": "expected_incoming",
                "item_id": str(group[0].get("item_id") or ""),
            })
            continue
        # One physical movement. Duplicate invoice plus receipt share the receipt quantity.
        if any(str(row.get("role") or "") == "receipt" for row in chosen) and any(str(row.get("role") or "") == "invoice" for row in group):
            chosen = [row for row in chosen if str(row.get("role") or "") == "receipt"] or chosen
        qty = quantity(sum(quantity(row.get("qty") or 0) for row in chosen))
        inward.append({
            "movement_key": key,
            "qty": qty,
            "kind": kind,
            "item_id": str(chosen[0].get("item_id") or ""),
            "location": str(chosen[0].get("location") or ""),
            "unit": str(chosen[0].get("unit") or ""),
            "lot": str(chosen[0].get("lot") or ""),
            "documents": [str(row.get("source_id") or "") for row in group],
        })
    return {"inward": inward, "returns": returns, "planning": planning}


def _received(row):
    flag = row.get("received")
    if isinstance(flag, str):
        return flag.strip().lower() in ("1", "true", "yes", "received", "y")
    return bool(flag)


def roll_stock(opening_qty, movements):
    """Closing = imported opening + inbound − outbound. A missing opening is unresolved."""
    if opening_qty is None:
        return {
            "status": STATUS_UNRESOLVED,
            "opening_qty": None,
            "calculated_closing": None,
            "origin": "missing",
        }
    total = quantity(opening_qty)
    for row in movements or []:
        signed = quantity(row.get("signed_qty"))
        if signed is None:
            qty = quantity(row.get("qty") or 0)
            direction = str(row.get("direction") or "in")
            signed = qty if direction == "in" else quantity(0) - qty
        total = quantity(total + signed)
    return {
        "status": STATUS_IMPORTED,
        "opening_qty": quantity(opening_qty),
        "calculated_closing": total,
        "origin": "imported",
    }


def stock_bridge(opening_qty, movements, source_closing=None, *, opening_value=None, source_closing_value=None):
    grouped = {}
    signed_total = quantity(0)
    value_ok = opening_value is not None
    value_change = money(0) if value_ok else None
    for row in movements or []:
        kind = str(row.get("kind") or "movement")
        signed = quantity(row.get("signed_qty"))
        if signed is None:
            qty = quantity(row.get("qty") or 0)
            signed = qty if str(row.get("direction") or "in") == "in" else quantity(0) - qty
        grouped[kind] = quantity(grouped.get(kind, 0) + signed)
        signed_total = quantity(signed_total + signed)
        if value_ok:
            if row.get("value") in (None, ""):
                value_ok = False
                value_change = None
            else:
                value_change = money(value_change + money(row.get("value")))
    rolled = roll_stock(opening_qty, movements)
    difference = None
    if rolled["calculated_closing"] is not None and source_closing is not None:
        difference = quantity(rolled["calculated_closing"] - quantity(source_closing))
    value = None
    if value_ok and opening_value is not None:
        value = {
            "opening_value": money(opening_value),
            "movement_value": value_change,
            "calculated_closing_value": money(money(opening_value) + value_change),
            "source_closing_value": money(source_closing_value) if source_closing_value is not None else None,
        }
    return {
        "status": rolled["status"],
        "opening_qty": rolled["opening_qty"],
        "movements": grouped,
        "movement_qty": signed_total if rolled["opening_qty"] is not None else None,
        "calculated_closing": rolled["calculated_closing"],
        "source_closing": quantity(source_closing) if source_closing is not None else None,
        "difference": difference,
        "value": value,
        "planning_excluded": True,
    }


def customer_bridge(opening_net, movements, source_closing=None, *, period_start=None, period_end=None):
    """Roll a known opening forward. A missing opening does not become zero."""
    start = parse_day(period_start)
    end = parse_day(period_end)
    if opening_net is None:
        return {
            "status": STATUS_UNRESOLVED,
            "opening_net": None,
            "calculated_closing": None,
            "source_closing": money(source_closing) if source_closing is not None else None,
            "difference": None,
        }
    brought = money(opening_net)
    if start is not None:
        for row in movements or []:
            day = parse_day(row.get("date"))
            if day is None or day >= start:
                continue
            brought = money(brought + _signed_movement(row))
    buckets = {
        "invoices": money(0),
        "receipts": money(0),
        "credit_notes": money(0),
        "other_debits": money(0),
        "other_credits": money(0),
    }
    for row in movements or []:
        day = parse_day(row.get("date"))
        if start and (day is None or day < start):
            continue
        if end and day and day > end:
            continue
        kind = str(row.get("kind") or "")
        amount = money(row.get("amount") or 0)
        if kind in ("invoice", "debit"):
            buckets["invoices"] = money(buckets["invoices"] + amount)
        elif kind == "receipt":
            buckets["receipts"] = money(buckets["receipts"] + amount)
        elif kind == "credit_note":
            buckets["credit_notes"] = money(buckets["credit_notes"] + amount)
        elif _signed_movement(row) >= 0:
            buckets["other_debits"] = money(buckets["other_debits"] + amount)
        else:
            buckets["other_credits"] = money(buckets["other_credits"] + amount)
    closing = money(
        brought + buckets["invoices"] + buckets["other_debits"]
        - buckets["receipts"] - buckets["credit_notes"] - buckets["other_credits"]
    )
    difference = None if source_closing is None else money(closing - money(source_closing))
    return {
        "status": STATUS_IMPORTED if opening_net is not None else STATUS_UNRESOLVED,
        "opening_net": brought,
        "period_start": start,
        **buckets,
        "calculated_closing": closing,
        "source_closing": money(source_closing) if source_closing is not None else None,
        "difference": difference,
    }


def _signed_movement(row):
    amount = money(row.get("amount") or 0)
    kind = str(row.get("kind") or "")
    if kind in ("invoice", "debit", "debit_adjustment"):
        return amount
    if row.get("direction") == "debit":
        return amount
    return money(0) - amount


def cap_promise_targets(promises, debt):
    """Eligible promise amounts cannot add up to more than the debt."""
    left = money(debt or 0)
    out = []
    for raw in promises or []:
        amount = money(raw.get("amount") or 0)
        eligible = money(min(amount, left if left > 0 else 0))
        out.append({
            "id": str(raw.get("id") or ""),
            "amount": amount,
            "eligible": eligible,
            "excess": money(amount - eligible),
            "overlap": amount > eligible,
        })
        left = money(left - eligible)
    return out


def promise_data_state(complete_through, promised_on):
    """Coverage that does not reach the promise is awaiting data, not a missed promise."""
    end = parse_day(complete_through)
    promised = parse_day(promised_on)
    if end is None or promised is None or end < promised:
        return "awaiting_data"
    return "covered"


def assess_books(customers, items, *, as_of, policy=POLICY_INVOICE_FIFO):
    """Preflight every customer and stock item. Sales stay available when openings are unknown."""
    customer_rows = []
    for raw in customers or []:
        customer_rows.append(_assess_customer(raw, as_of=as_of, policy=policy))
    item_rows = []
    for raw in items or []:
        item_rows.append(_assess_item(raw))
    return {
        "engine_version": ENGINE_VERSION,
        "policy": policy,
        "as_of": parse_day(as_of).isoformat() if parse_day(as_of) else "",
        "customers": [_public(row) for row in customer_rows],
        "items": [_public(row) for row in item_rows],
    }


def _assess_customer(raw, *, as_of, policy):
    scope = {
        "organization_id": raw.get("organization_id") or "",
        "legal_entity_id": raw.get("legal_entity_id") or "",
        "customer_id": raw.get("customer_id") or "",
        "currency": raw.get("currency") or "",
    }
    imported_debits = []
    imported_credits = []
    imported_net = None
    for row in raw.get("imported_openings") or []:
        signed = money(row.get("amount"))
        if signed is None:
            continue
        imported_net = money((imported_net or 0) + signed)
        if signed >= 0:
            imported_debits.append(dict(row, amount=signed, opening=True, **scope))
        else:
            imported_credits.append({
                "source_id": row.get("source_id"),
                "kind": "opening_credit",
                "amount": money(0) - signed,
                "opening": True,
                "effective_date": row.get("effective_date"),
                "cash": False,
                "reference": row.get("reference") or "",
                **scope,
            })
    movements = list(raw.get("movements") or [])
    debit_total = money(sum((money(row.get("amount") or 0) for row in movements if str(row.get("kind")) in ("invoice", "debit", "debit_adjustment")), money(0)))
    credit_total = money(sum((money(row.get("amount") or 0) for row in movements if str(row.get("kind")) not in ("invoice", "debit", "debit_adjustment")), money(0)))
    derived = reconstruct_customer_opening(
        closing_net=raw.get("checkpoint_net"),
        debit_movements=debit_total,
        credit_movements=credit_total,
        movements_complete=bool(raw.get("movements_complete")) and raw.get("checkpoint_net") is not None,
    )
    chosen = select_customer_opening(imported_net, derived)
    debits = [dict(row, **scope) for row in (raw.get("debits") or [])]
    credits = [dict(row, **scope) for row in (raw.get("credits") or [])]
    if chosen["status"] == STATUS_IMPORTED:
        debits = imported_debits + debits
        credits = imported_credits + credits
    elif chosen["status"] == STATUS_RECONSTRUCTED and chosen["amount"] is not None:
        if chosen["amount"] >= 0:
            debits = [{
                "source_id": "opening:reconstructed",
                "kind": "opening_aggregate",
                "amount": chosen["amount"],
                "opening": True,
                "effective_date": raw.get("coverage_start"),
                "invoice_date": None,
                **scope,
            }] + debits
        elif chosen["amount"] < 0:
            credits = [{
                "source_id": "opening:reconstructed",
                "kind": "opening_credit",
                "amount": money(0) - chosen["amount"],
                "opening": True,
                "effective_date": raw.get("coverage_start"),
                "cash": False,
                **scope,
            }] + credits
    overlap = coverage_overlap(raw.get("opening_keys") or [], raw.get("movement_keys") or [])
    settlement = None
    if debits or credits or raw.get("checkpoint_net") is not None:
        settlement = settle(
            debits, credits, raw.get("links") or [], raw.get("reversals") or [],
            policy=policy, as_of=as_of, checkpoint=raw.get("checkpoint_net"), **scope,
        )
    exact = chosen["status"] in (STATUS_IMPORTED, STATUS_RECONSTRUCTED)
    unknown_age = chosen["status"] != STATUS_IMPORTED or any(
        not row.get("invoice_date") for row in (raw.get("imported_openings") or []) if money(row.get("amount") or 0) and money(row.get("amount")) > 0
    )
    withheld = []
    allowed = ["sales"]
    if not exact:
        withheld.extend(["exact_balance", "aging", "recommendations"])
    elif unknown_age:
        withheld.append("exact_aging")
    if overlap:
        withheld.append("exact_balance")
    bridge = customer_bridge(
        chosen["amount"] if exact else None,
        movements,
        raw.get("checkpoint_net"),
        period_start=raw.get("period_start"),
        period_end=as_of,
    )
    return {
        "customer_id": scope["customer_id"],
        "currency": scope["currency"],
        "organization_id": scope["organization_id"],
        "legal_entity_id": scope["legal_entity_id"],
        "opening": chosen,
        "overlap": overlap,
        "coverage": {
            "start": raw.get("coverage_start"),
            "complete_through": raw.get("complete_through"),
            "complete": bool(raw.get("movements_complete")),
        },
        "bridge": bridge,
        "settlement": settlement,
        "allowed_outputs": allowed,
        "withheld_outputs": withheld,
    }


def _assess_item(raw):
    purchases = normalize_purchases(raw.get("purchases") or [])
    movements = []
    for row in purchases["inward"]:
        movements.append({"kind": row["kind"], "qty": row["qty"], "direction": "in"})
    for row in purchases["returns"]:
        movements.append({"kind": row["kind"], "qty": row["qty"], "direction": "out"})
    for row in raw.get("movements") or []:
        if str(row.get("kind")) in ("reservation", "expected_incoming", "credit_note"):
            continue
        movements.append(row)
    opening_qty = raw.get("opening_qty")
    bridge = stock_bridge(
        opening_qty,
        movements,
        raw.get("source_closing_qty"),
        opening_value=raw.get("opening_value"),
        source_closing_value=raw.get("source_closing_value"),
    )
    cost_history = _received_cost_history(raw.get("purchases") or [])
    withheld = []
    allowed = ["current_stock", "sales", "purchases"]
    if opening_qty is None:
        withheld.extend(["stock_change", "stock_value"])
    elif raw.get("opening_value") is None:
        withheld.append("stock_value")
    return {
        "item_id": raw.get("item_id") or "",
        "location": raw.get("location") or "",
        "unit": raw.get("unit") or "",
        "lot": raw.get("lot") or "",
        "opening_status": STATUS_UNRESOLVED if opening_qty is None else STATUS_IMPORTED,
        "bridge": bridge,
        "planning": purchases["planning"],
        "cost_history": cost_history,
        "valuation_method_unchanged": True,
        "allowed_outputs": allowed,
        "withheld_outputs": withheld,
    }


def _received_cost_history(lines):
    """Received purchase costs. A blank rate stays missing and does not change valuation."""
    groups = {}
    order = []
    for raw in lines or []:
        if str(raw.get("return_of") or "").strip():
            continue
        key = str(raw.get("movement_key") or raw.get("source_id") or "")
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(raw)
    history = []
    for key in order:
        group = groups[key]
        received = [row for row in group if _received(row) or str(row.get("role") or "") == "receipt"]
        if not received:
            continue
        chosen = [row for row in received if str(row.get("role") or "") == "receipt"] or received
        row = chosen[0]
        history.append({
            "movement_key": key,
            "date": row.get("date") or "",
            "supplier": row.get("supplier") or "",
            "qty": quantity(row.get("qty") or 0),
            "rate": money(row.get("rate")) if row.get("rate") not in (None, "") else None,
            "amount": money(row.get("amount")) if row.get("amount") not in (None, "") else None,
        })
    return history


def opening_preview_issues(rows):
    """Duplicate identities, mixed currencies, and conflicting opening totals for one preview."""
    issues = []
    seen = {}
    totals = {}
    for index, row in enumerate(rows or []):
        customer = str(row.get("customer_id") or row.get("Account Name") or "").strip().lower()
        currency = str(row.get("currency") or row.get("Currency") or "").strip().upper()
        invoice = str(row.get("invoice_number") or row.get("Invoice No") or "").strip().lower()
        amount = row.get("amount", row.get("Balance"))
        ident = (customer, invoice, str(amount))
        if customer and ident in seen:
            issues.append({"code": "duplicate_opening", "customer_id": customer, "invoice_number": invoice})
        seen[ident] = index
        bucket = totals.setdefault(customer, {"currency": currency, "amount": money(0), "count": 0})
        if currency and bucket["currency"] and currency != bucket["currency"]:
            issues.append({"code": "currency_conflict", "customer_id": customer})
        if amount not in (None, ""):
            bucket["amount"] = money(bucket["amount"] + (money(amount) or 0))
            bucket["count"] += 1
        if row.get("control_total") not in (None, ""):
            control = money(row.get("control_total"))
            if control is not None and bucket["count"] and bucket["amount"] != control and invoice == "":
                issues.append({"code": "control_total", "customer_id": customer})
    return issues
