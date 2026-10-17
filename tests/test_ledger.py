"""Hand-calculated settlement, opening, stock, and coverage fixtures."""

from datetime import date
from decimal import Decimal

import pytest

from vay.ledger import (
    POLICY_DUE_DATE,
    POLICY_EXPLICIT,
    STATUS_IMPORTED,
    STATUS_RECONSTRUCTED,
    STATUS_UNRESOLVED,
    assess_books,
    cap_promise_targets,
    coverage_overlap,
    customer_bridge,
    days_overdue,
    invariants,
    invoice_age_days,
    money,
    normalize_purchases,
    opening_preview_issues,
    promise_data_state,
    public_result,
    reconstruct_customer_opening,
    roll_stock,
    select_customer_opening,
    settle,
    stock_bridge,
)

AS_OF = "2026-03-31"
SCOPE = {
    "organization_id": "org",
    "legal_entity_id": "org",
    "customer_id": "acme",
    "currency": "INR",
}


def D(value):
    return money(value)


def debit(**kwargs):
    row = dict(SCOPE)
    row.update(kwargs)
    return row


def credit(**kwargs):
    row = dict(SCOPE)
    row.update(kwargs)
    return row


def run(debits, credits, links=None, reversals=None, checkpoint=None, policy="invoice_date_fifo", as_of=AS_OF):
    result = settle(
        debits, credits, links or [], reversals or [],
        policy=policy, as_of=as_of, checkpoint=checkpoint, **SCOPE,
    )
    assert invariants(result) == []
    return result


def by_id(rows):
    return {row["source_id"]: row for row in rows}


def test_money_is_half_up_and_blank_stays_missing():
    assert money("10.005") == Decimal("10.01")
    assert money("10.004") == Decimal("10.00")
    assert money(None) is None
    assert money("") is None
    assert money(0) == Decimal("0.00")


def test_unknown_dates_stay_unknown():
    assert invoice_age_days(AS_OF, None) is None
    assert days_overdue(AS_OF, None) is None
    assert days_overdue("2026-03-31", "2026-04-15") == 0
    assert invoice_age_days("2026-03-31", "2023-06-01") == 1034
    assert days_overdue("2026-03-31", "2023-07-01") == 1004


def test_opening_remainder_is_not_replayed():
    """An opening invoice starts at its remaining amount. Earlier receipts are absent."""
    result = run(
        [debit(source_id="OLD", amount="400", opening=True, invoice_date="2023-06-01", effective_date="2024-04-01", invoice_number="OLD")],
        [debit and credit(source_id="R", amount="100", kind="receipt", cash=True, effective_date="2024-06-01")],
    )
    assert by_id(result["open_debits"])["OLD"]["remaining"] == D("300")
    assert result["allocations"][0]["evidence"] == "inferred"


def test_two_years_of_receipts_clear_opening_before_invoices():
    result = run(
        [
            debit(source_id="OLD", amount="1000", opening=True, invoice_date="2023-06-01", due_date="2023-07-01", effective_date="2024-04-01", invoice_number="OLD"),
            debit(source_id="A", amount="400", effective_date="2024-05-01", invoice_number="INV-A", terms_days=30),
            debit(source_id="B", amount="300", effective_date="2025-05-01", invoice_number="INV-B", terms_days=30),
        ],
        [
            credit(source_id="R1", amount="600", kind="receipt", cash=True, effective_date="2024-06-01"),
            credit(source_id="R2", amount="400", kind="receipt", cash=True, effective_date="2024-07-01", reference="INV-A"),
            credit(source_id="R3", amount="80", kind="receipt", cash=True, effective_date="2024-08-01", reference="GONE-1"),
            credit(source_id="CN", amount="50", kind="credit_note", cash=False, effective_date="2024-09-01"),
            credit(source_id="R4", amount="200", kind="receipt", cash=True, effective_date="2025-06-01"),
            credit(source_id="R5", amount="350", kind="receipt", cash=True, effective_date="2025-08-01", reference="INV-B"),
            credit(source_id="R6", amount="100", kind="receipt", cash=True, effective_date="2026-03-01"),
        ],
        reversals=[debit and {"source_id": "REV", "reverses_id": "R1", "effective_date": "2026-02-01"}],
        checkpoint="520",
    )
    # R1 600 pays OLD. R2 clears INV-A. R3 stays unresolved.
    # CN 50 and R4 200 pay OLD (1000-600-50-200=150). R5 pays INV-B 300 and leaves 50.
    # Reversing R1 reopens 600, so OLD is 750. R6 then pays 100. OLD remains 650.
    # Unused: unresolved 80 + referenced remainder 50. Net 650-130=520.
    opens = by_id(result["open_debits"])
    unused = by_id(result["unused_credits"])
    assert "A" not in opens and "B" not in opens
    assert opens["OLD"]["remaining"] == D("650")
    assert opens["OLD"]["invoice_age_days"] == 1034
    assert opens["OLD"]["days_overdue"] == 1004
    assert opens["OLD"]["due_source"] == "source"
    assert unused["R3"]["remaining"] == D("80")
    assert unused["R3"]["unresolved"] is True
    assert unused["R5"]["remaining"] == D("50")
    assert "R1" not in unused
    assert result["reconciliation"]["state"] == "reconciled"
    assert result["reconciliation"]["ledger_net"] == D("520")
    kinds = {(row["credit_id"], row["debit_id"], row["evidence"], row["cash"]) for row in result["allocations"]}
    assert ("R2", "A", "source_confirmed", True) in kinds
    assert ("CN", "OLD", "inferred", False) in kinds
    assert all(row["credit_id"] != "R3" for row in result["allocations"])
    assert all(row["debit_id"] != "C" for row in result["allocations"])


def test_future_invoice_is_not_invented_and_later_replay_uses_carried_credit():
    early = run(
        [debit(source_id="A", amount="40", effective_date="2026-06-01", invoice_number="INV-A")],
        [credit(source_id="R", amount="40", kind="receipt", cash=True, effective_date="2026-03-01")],
        as_of="2026-03-31",
    )
    assert early["open_debits"] == []
    assert by_id(early["unused_credits"])["R"]["remaining"] == D("40")
    assert early["allocations"] == []
    later = run(
        [debit(source_id="A", amount="40", effective_date="2026-06-01", invoice_number="INV-A")],
        [credit(source_id="R", amount="40", kind="receipt", cash=True, effective_date="2026-03-01")],
        as_of="2026-06-30",
    )
    assert later["open_debits"] == []
    assert later["allocations"][0]["effective_date"] == date(2026, 6, 1)
    assert later["allocations"][0]["evidence"] == "inferred"


def test_receipt_before_invoice_waits_for_its_reference():
    result = run(
        [debit(source_id="A", amount="50", effective_date="2024-05-02", invoice_number="INV-A")],
        [credit(source_id="R", amount="50", kind="receipt", cash=True, effective_date="2024-05-01", reference="INV-A")],
    )
    assert result["allocations"][0]["debit_id"] == "A"
    assert result["allocations"][0]["evidence"] == "source_confirmed"
    assert result["allocations"][0]["effective_date"] == date(2024, 5, 2)
    assert result["open_debits"] == []


def test_unmatched_reference_does_not_fall_through_to_fifo():
    result = run(
        [debit(source_id="A", amount="100", effective_date="2024-05-01", invoice_number="INV-A")],
        [credit(source_id="R", amount="100", kind="receipt", cash=True, effective_date="2024-06-01", reference="OTHER")],
    )
    assert result["allocations"] == []
    assert by_id(result["open_debits"])["A"]["remaining"] == D("100")
    assert by_id(result["unused_credits"])["R"]["unresolved"] is True
    assert result["suggestions"][0]["reason"] == "unique_amount"
    assert result["suggestions"][0]["evidence"] == "suggestion"


def test_pre_period_reference_uses_opening_debt_only():
    result = run(
        [
            debit(source_id="OLD", amount="100", opening=True, invoice_date="2023-01-01", effective_date="2024-04-01", invoice_number="OLD"),
            debit(source_id="A", amount="100", effective_date="2024-05-01", invoice_number="INV-A"),
        ],
        [credit(source_id="R", amount="40", kind="receipt", cash=True, effective_date="2024-06-01", reference="HIST", pre_period=True)],
    )
    assert result["allocations"] == [{
        "credit_id": "R",
        "debit_id": "OLD",
        "amount": D("40"),
        "evidence": "inferred",
        "effective_date": date(2024, 6, 1),
        "invoice_date": date(2023, 1, 1),
        "invoice_number": "OLD",
        "cash": True,
        "credit_kind": "receipt",
        "referenced": True,
    }]
    assert by_id(result["open_debits"])["A"]["remaining"] == D("100")


def test_ambiguous_invoice_number_is_not_settled():
    result = run(
        [
            debit(source_id="A", amount="10", effective_date="2024-05-01", invoice_number="1", invoice_key="A"),
            debit(source_id="B", amount="10", effective_date="2024-06-01", invoice_number="1", invoice_key="B"),
        ],
        [
            credit(source_id="R", amount="10", kind="receipt", cash=True, effective_date="2024-07-01", reference="1"),
            credit(source_id="K", amount="10", kind="receipt", cash=True, effective_date="2024-07-02", reference="B"),
        ],
    )
    assert all(row["credit_id"] != "R" for row in result["allocations"])
    assert result["allocations"][0]["debit_id"] == "B"


def test_confirmed_link_beats_fifo_and_conflict_does_not_overallocate():
    kept = run(
        [
            debit(source_id="OLD", amount="100", opening=True, invoice_date="2023-01-01", effective_date="2024-04-01"),
            debit(source_id="A", amount="100", effective_date="2024-05-01", invoice_number="INV-A"),
        ],
        [credit(source_id="R", amount="100", kind="receipt", cash=True, effective_date="2024-06-01")],
        links=[{"credit_id": "R", "debit_id": "A", "amount": "100", "evidence": "manually_confirmed"}],
    )
    assert kept["allocations"][0]["debit_id"] == "A"
    assert kept["allocations"][0]["evidence"] == "manually_confirmed"
    assert by_id(kept["open_debits"])["OLD"]["remaining"] == D("100")

    conflict = run(
        [debit(source_id="A", amount="100", effective_date="2024-05-01")],
        [credit(source_id="R", amount="100", kind="receipt", cash=True, effective_date="2024-06-01")],
        links=[
            {"credit_id": "R", "debit_id": "A", "amount": "80", "evidence": "source_confirmed"},
            {"credit_id": "R", "debit_id": "A", "amount": "80", "evidence": "manually_confirmed"},
        ],
    )
    assert sum(row["amount"] for row in conflict["allocations"]) == D("100")
    assert any(row["code"] == "conflicting_links" for row in conflict["exceptions"])


def test_partial_split_and_same_day_receipt():
    result = run(
        [debit(source_id="A", amount="100", effective_date="2024-05-01", invoice_number="INV-A")],
        [
            credit(source_id="R1", amount="30", kind="receipt", cash=True, effective_date="2024-05-01"),
            credit(source_id="R2", amount="20", kind="receipt", cash=True, effective_date="2024-05-02"),
        ],
    )
    assert by_id(result["open_debits"])["A"]["remaining"] == D("50")
    assert {row["credit_id"] for row in result["allocations"]} == {"R1", "R2"}


def test_bounce_reopens_debt_and_does_not_reuse_the_receipt():
    result = run(
        [debit(source_id="A", amount="100", effective_date="2024-05-01")],
        [credit(source_id="R", amount="100", kind="receipt", cash=True, effective_date="2024-05-02")],
        reversals=[{"source_id": "REV", "reverses_id": "R", "effective_date": "2024-05-03"}],
    )
    assert result["allocations"] == []
    assert by_id(result["open_debits"])["A"]["remaining"] == D("100")
    assert result["unused_credits"] == []


def test_cancelling_an_invoice_releases_an_unreferenced_receipt_only():
    result = run(
        [
            debit(source_id="A", amount="40", effective_date="2024-05-01", invoice_number="INV-A"),
            debit(source_id="B", amount="40", effective_date="2024-05-03", invoice_number="INV-B"),
        ],
        [credit(source_id="R", amount="40", kind="receipt", cash=True, effective_date="2024-05-02", reference="INV-A")],
        reversals=[{"source_id": "REV", "reverses_id": "A", "effective_date": "2024-05-04"}],
    )
    assert result["allocations"] == []
    assert "A" not in by_id(result["open_debits"])
    assert by_id(result["open_debits"])["B"]["remaining"] == D("40")
    assert by_id(result["unused_credits"])["R"]["remaining"] == D("40")


def test_explicit_policy_does_not_fifo():
    result = run(
        [debit(source_id="A", amount="10", effective_date="2024-05-01")],
        [credit(source_id="R", amount="10", kind="receipt", cash=True, effective_date="2024-05-02")],
        policy=POLICY_EXPLICIT,
    )
    assert result["allocations"] == []
    assert by_id(result["unused_credits"])["R"]["remaining"] == D("10")


def test_due_date_priority_pays_the_earlier_due_date():
    result = run(
        [
            debit(source_id="NEW", amount="10", effective_date="2024-06-01", due_date="2024-06-15", invoice_number="NEW"),
            debit(source_id="SOON", amount="10", effective_date="2024-05-01", due_date="2024-05-10", invoice_number="SOON"),
        ],
        [credit(source_id="R", amount="10", kind="receipt", cash=True, effective_date="2024-07-01")],
        policy=POLICY_DUE_DATE,
    )
    assert result["allocations"][0]["debit_id"] == "SOON"


def test_disputed_invoice_stays_open_while_a_later_invoice_can_be_paid():
    result = run(
        [
            debit(source_id="A", amount="10", effective_date="2024-05-01", disputed=True),
            debit(source_id="B", amount="10", effective_date="2024-06-01"),
        ],
        [credit(source_id="R", amount="10", kind="receipt", cash=True, effective_date="2024-07-01")],
    )
    assert by_id(result["open_debits"])["A"]["remaining"] == D("10")
    assert "B" not in by_id(result["open_debits"])


def test_negative_arr_uses_existing_credit_and_does_not_create_a_receipt():
    matched = run(
        [],
        [credit(source_id="C", amount="200", kind="opening_credit", opening=True, cash=False, effective_date="2024-04-01")],
        checkpoint="-200",
    )
    assert matched["reconciliation"]["state"] == "reconciled"
    assert matched["reconciliation"]["net_advance"] == D("200")
    assert matched["reconciliation"]["advance_origin"] == "ledger"
    assert len(matched["unused_credits"]) == 1

    only = run([], [], checkpoint="-150")
    assert only["unused_credits"] == []
    assert only["reconciliation"]["state"] == "arr_only_advance"
    assert only["reconciliation"]["net_advance"] == D("150")
    assert only["reconciliation"]["advance_provenance"] == "unknown"
    assert only["allocations"] == []


def test_zero_net_with_unresolved_items_is_not_treated_as_settled():
    result = run(
        [debit(source_id="A", amount="100", effective_date="2024-05-01", invoice_number="INV-A")],
        [credit(source_id="R", amount="100", kind="receipt", cash=True, effective_date="2024-06-01", reference="MISSING")],
    )
    assert result["reconciliation"]["ledger_net"] == D("0")
    assert result["open_debits"][0]["remaining"] == D("100")
    assert result["unused_credits"][0]["remaining"] == D("100")


def test_other_currency_is_rejected():
    foreign = dict(SCOPE)
    foreign["currency"] = "USD"
    result = run(
        [debit(source_id="A", amount="10", effective_date="2024-05-01")],
        [credit(source_id="R", amount="10", kind="receipt", cash=True, effective_date="2024-06-01", currency="USD")],
    )
    assert result["allocations"] == []
    assert any(row["code"] == "scope_mismatch" for row in result["exceptions"])


def test_checkpoint_difference_is_not_forced():
    result = run(
        [debit(source_id="A", amount="100", effective_date="2024-05-01")],
        [],
        checkpoint="80",
    )
    assert by_id(result["open_debits"])["A"]["remaining"] == D("100")
    assert result["reconciliation"]["state"] == "mismatch"
    assert result["reconciliation"]["difference"] == D("20")


def test_replay_is_stable():
    args = (
        [debit(source_id="A", amount="15", effective_date="2024-05-01")],
        [credit(source_id="R", amount="5", kind="receipt", cash=True, effective_date="2024-05-02")],
    )
    assert public_result(run(*args)) == public_result(run(*args))


def test_customer_opening_reconstruction_and_import_priority():
    # closing 200, invoices 500, receipts 400 -> opening 200 - 500 + 400 = 100
    derived = reconstruct_customer_opening(
        closing_net="200", debit_movements="500", credit_movements="400", movements_complete=True,
    )
    assert derived["amount"] == D("100")
    assert derived["status"] == STATUS_RECONSTRUCTED
    assert derived["tie_out"] is True
    missing = reconstruct_customer_opening(
        closing_net=None, debit_movements="500", credit_movements="400", movements_complete=True,
    )
    assert missing["status"] == STATUS_UNRESOLVED
    assert missing["amount"] is None
    chosen = select_customer_opening("80", derived)
    assert chosen["status"] == STATUS_IMPORTED
    assert chosen["amount"] == D("80")
    assert coverage_overlap(["INV-1"], ["inv-1", "INV-2"]) == ["inv-1"]


def test_preflight_reconstructs_a_customer_and_refuses_a_stock_estimate():
    books = assess_books(
        [{
            **SCOPE,
            "checkpoint_net": "200",
            "movements_complete": True,
            "coverage_start": "2024-04-01",
            "complete_through": "2026-03-31",
            "movements": [
                {"kind": "invoice", "amount": "500", "date": "2024-05-01"},
                {"kind": "receipt", "amount": "400", "date": "2024-06-01"},
            ],
            "debits": [debit(source_id="A", amount="500", effective_date="2024-05-01", invoice_number="INV-A")],
            "credits": [credit(source_id="R", amount="400", kind="receipt", cash=True, effective_date="2024-06-01")],
        }],
        [{
            "item_id": "widget",
            "unit": "pcs",
            "opening_qty": None,
            "source_closing_qty": "11",
            "purchases": [],
            "movements": [{"kind": "sale_issue", "qty": "3", "direction": "out"}],
        }],
        as_of=AS_OF,
    )
    customer = books["customers"][0]
    assert customer["opening"]["status"] == STATUS_RECONSTRUCTED
    assert customer["opening"]["amount"] == "100.00"
    assert customer["bridge"]["calculated_closing"] == "200.00"
    assert customer["bridge"]["difference"] == "0.00"
    assert "sales" in customer["allowed_outputs"]
    assert "exact_aging" in customer["withheld_outputs"]
    item = books["items"][0]
    assert item["opening_status"] == STATUS_UNRESOLVED
    assert item["bridge"]["calculated_closing"] is None
    assert "stock_change" in item["withheld_outputs"]
    assert "current_stock" in item["allowed_outputs"]


def test_imported_opening_is_not_replaced_and_stock_rolls_forward_once():
    books = assess_books(
        [{
            **SCOPE,
            "checkpoint_net": "50",
            "movements_complete": True,
            "imported_openings": [{
                "source_id": "OLD",
                "amount": "150",
                "invoice_date": "2023-06-01",
                "effective_date": "2024-04-01",
                "invoice_number": "OLD",
            }],
            "debits": [],
            "credits": [credit(source_id="R", amount="100", kind="receipt", cash=True, effective_date="2024-06-01")],
            "movements": [{"kind": "receipt", "amount": "100", "date": "2024-06-01"}],
        }],
        [{
            "item_id": "widget",
            "unit": "pcs",
            "location": "main",
            "opening_qty": "10",
            "opening_value": "100",
            "source_closing_qty": "11",
            "purchases": [
                {"source_id": "PI", "movement_key": "M1", "role": "invoice", "qty": "4", "received": False, "item_id": "widget"},
                {"source_id": "GR", "movement_key": "M1", "role": "receipt", "qty": "4", "received": True, "item_id": "widget"},
            ],
            "movements": [
                {"kind": "sale_issue", "qty": "3", "direction": "out"},
                {"kind": "customer_return", "qty": "1", "direction": "in"},
                {"kind": "transfer_out", "qty": "2", "direction": "out"},
                {"kind": "count", "signed_qty": "1"},
                {"kind": "reservation", "qty": "9", "direction": "out"},
                {"kind": "credit_note", "qty": "4", "direction": "in"},
            ],
        }],
        as_of=AS_OF,
    )
    assert books["customers"][0]["opening"]["status"] == STATUS_IMPORTED
    assert books["customers"][0]["opening"]["amount"] == "150.00"
    assert books["customers"][0]["settlement"]["reconciliation"]["ledger_net"] == "50.00"
    item = books["items"][0]
    # 10 + 4 - 3 + 1 - 2 + 1 = 11. Reservation and financial credit note are ignored.
    assert item["bridge"]["calculated_closing"] == "11.0000"
    assert item["bridge"]["difference"] == "0.0000"
    assert item["bridge"]["movements"]["purchase_receipt"] == "4.0000"
    assert item["planning"] == []


def test_purchase_dedup_and_unreceived_invoice_is_planning():
    folded = normalize_purchases([
        {"source_id": "PI", "movement_key": "M1", "role": "invoice", "qty": "4", "received": False, "item_id": "widget"},
        {"source_id": "GR", "movement_key": "M1", "role": "receipt", "qty": "4", "received": True, "item_id": "widget"},
    ])
    assert folded["inward"][0]["qty"] == D("4") if False else folded["inward"][0]["qty"] == __import__("decimal").Decimal("4.0000")
    assert len(folded["inward"]) == 1
    waiting = normalize_purchases([
        {"source_id": "PI", "movement_key": "M2", "role": "invoice", "qty": "2", "received": False, "item_id": "bolt"},
    ])
    assert waiting["inward"] == []
    assert waiting["planning"][0]["kind"] == "expected_incoming"
    returned = normalize_purchases([
        {"source_id": "SR", "movement_key": "M3", "role": "receipt", "qty": "1", "return_of": "PI", "item_id": "bolt"},
    ])
    assert returned["returns"][0]["kind"] == "supplier_return"
    rolled = roll_stock(None, [{"qty": "5", "direction": "in"}])
    assert rolled["status"] == STATUS_UNRESOLVED
    assert rolled["calculated_closing"] is None


def test_stock_value_needs_an_imported_opening_value():
    bridge = stock_bridge("10", [{"kind": "purchase_receipt", "qty": "2", "direction": "in"}], "12")
    assert bridge["value"] is None
    valued = stock_bridge(
        "10",
        [{"kind": "purchase_receipt", "qty": "2", "direction": "in", "value": "20"}],
        "12",
        opening_value="50",
    )
    assert valued["value"]["calculated_closing_value"] == D("70")


def test_duration_bridge_rolls_forward_instead_of_rebuilding_an_opening():
    bridge = customer_bridge(
        "100",
        [
            {"kind": "invoice", "amount": "40", "date": "2024-05-01"},
            {"kind": "receipt", "amount": "10", "date": "2024-06-01"},
            {"kind": "invoice", "amount": "5", "date": "2025-01-01"},
        ],
        source_closing=None,
        period_start="2025-01-01",
        period_end="2026-03-31",
    )
    # Opening 100 + 40 - 10 is brought into 2025, then the January invoice is inside the window.
    assert bridge["opening_net"] == D("130")
    assert bridge["invoices"] == D("5")
    assert bridge["calculated_closing"] == D("135")


def test_promise_targets_cannot_exceed_debt_and_stale_coverage_waits():
    capped = cap_promise_targets(
        [{"id": "p1", "amount": "60"}, {"id": "p2", "amount": "50"}],
        "80",
    )
    assert capped[0]["eligible"] == D("60")
    assert capped[1]["eligible"] == D("20")
    assert capped[1]["overlap"] is True
    assert sum(row["eligible"] for row in capped) == D("80")
    assert promise_data_state("2026-03-01", "2026-03-15") == "awaiting_data"
    assert promise_data_state("2026-03-31", "2026-03-15") == "covered"


def test_opening_preview_flags_duplicates_and_currency():
    issues = opening_preview_issues([
        {"Account Name": "Acme", "Invoice No": "1", "Balance": "10", "Currency": "INR"},
        {"Account Name": "Acme", "Invoice No": "1", "Balance": "10", "Currency": "USD"},
    ])
    assert {row["code"] for row in issues} >= {"duplicate_opening", "currency_conflict"}


def test_missing_opening_withholds_exact_balance_but_keeps_sales():
    books = assess_books(
        [{
            **SCOPE,
            "checkpoint_net": None,
            "movements_complete": False,
            "debits": [debit(source_id="A", amount="10", effective_date="2024-05-01")],
            "credits": [],
            "movements": [],
        }],
        [],
        as_of=AS_OF,
    )
    customer = books["customers"][0]
    assert customer["opening"]["status"] == STATUS_UNRESOLVED
    assert customer["opening"]["amount"] is None
    assert "sales" in customer["allowed_outputs"]
    assert "exact_balance" in customer["withheld_outputs"]
