"""Cash receipt summary. Figures are calculated by hand in each test."""

from datetime import date

from server.ledger_apply import project_customer
from vay.ledger import settle
from vay.payments import payment_summary


def _receipt(source_id, amount, day, *, cash=True, evidence="source_confirmed"):
    labels = evidence if isinstance(evidence, list) else [evidence]
    return {
        "source_id": source_id,
        "amount": amount,
        "effective_date": day,
        "cash": cash,
        "evidence": labels,
    }


def test_two_receipts_have_total_gap_and_median():
    summary = payment_summary(
        [
            _receipt("R1", 40, date(2024, 4, 1)),
            _receipt("R2", 60, date(2024, 4, 11)),
        ],
        as_of=date(2024, 9, 19),
        start_month=4,
        coverage={"complete": True, "start": "2023-04-01"},
    )
    assert summary["cash_total"] == 100.0
    assert summary["occasions"] == 2
    assert summary["typical_amount"] == 50.0
    assert summary["median_gap_days"] == 10
    assert summary["gap_count"] == 1
    assert summary["evidence"] == "source_confirmed"
    assert [row["source_id"] for row in summary["transactions"]] == ["R1", "R2"]


def test_credit_note_stays_out_of_cash():
    summary = payment_summary(
        [
            _receipt("R1", 40, date(2024, 4, 1)),
            _receipt("CN1", 100, date(2024, 4, 2), cash=False),
        ],
        as_of=date(2024, 9, 19),
        start_month=4,
        coverage={"complete": True, "start": "2023-04-01"},
    )
    assert summary["cash_total"] == 40.0
    assert summary["occasions"] == 1
    assert summary["non_cash_total"] == 100.0
    assert summary["non_cash_count"] == 1
    assert [row["source_id"] for row in summary["transactions"]] == ["R1"]


def test_one_receipt_has_no_gap():
    summary = payment_summary(
        [_receipt("R1", 40, date(2024, 4, 1))],
        as_of=date(2024, 9, 19),
        start_month=4,
        coverage={"complete": True, "start": "2023-04-01"},
    )
    assert summary["typical_amount"] == 40.0
    assert summary["median_gap_days"] is None
    assert summary["gap_count"] == 0


def test_undated_receipt_is_in_the_total_and_out_of_the_gap():
    summary = payment_summary(
        [
            _receipt("R1", 40, date(2024, 4, 1)),
            _receipt("R2", 25, None),
        ],
        as_of=date(2024, 9, 19),
        start_month=4,
        coverage={"complete": True, "start": "2023-04-01"},
    )
    assert summary["cash_total"] == 65.0
    assert summary["occasions"] == 2
    assert summary["undated_count"] == 1
    assert summary["undated_amount"] == 25.0
    assert summary["median_gap_days"] is None
    assert summary["dated_occasions"] == 1


def test_inferred_allocation_is_not_confirmed_behavior():
    summary = payment_summary(
        [_receipt("R1", 40, date(2024, 4, 1), evidence="inferred")],
        as_of=date(2024, 9, 19),
        start_month=4,
        coverage={"complete": True, "start": "2023-04-01"},
    )
    assert summary["evidence"] == "source_confirmed"
    assert summary["transactions"][0]["settlement_evidence"] == "inferred"
    assert summary["cash_total"] == 40.0


def test_prior_window_matches_the_same_span():
    summary = payment_summary(
        [
            _receipt("OLD", 80, date(2023, 5, 1)),
            _receipt("NEW", 100, date(2024, 5, 1)),
            _receipt("LATER", 999, date(2023, 12, 1)),
        ],
        as_of=date(2024, 9, 19),
        start_month=4,
        coverage={"complete": True, "start": "2023-04-01"},
    )
    trend = summary["trend"]
    assert trend["available"] is True
    assert trend["current"]["start"] == "2024-04-01"
    assert trend["current"]["end"] == "2024-09-19"
    assert trend["current"]["cash_total"] == 100.0
    assert trend["current"]["transactions"] == ["NEW"]
    assert trend["prior"]["start"] == "2023-04-01"
    assert trend["prior"]["end"] == "2023-09-19"
    assert trend["prior"]["cash_total"] == 80.0
    assert trend["prior"]["transactions"] == ["OLD"]
    assert trend["cash_change_percent"] == 25.0


def test_empty_prior_window_does_not_become_a_percent():
    summary = payment_summary(
        [_receipt("NEW", 100, date(2024, 5, 1))],
        as_of=date(2024, 9, 19),
        start_month=4,
        coverage={"complete": True, "start": "2023-04-01"},
    )
    assert summary["trend"]["available"] is True
    assert summary["trend"]["prior"]["occasions"] == 0
    assert summary["trend"]["cash_change_percent"] is None


def test_incomplete_history_withholds_the_comparison():
    summary = payment_summary(
        [_receipt("NEW", 100, date(2024, 5, 1))],
        as_of=date(2024, 9, 19),
        start_month=4,
        coverage={"complete": False, "start": "2024-04-01"},
    )
    assert summary["cash_total"] == 100.0
    assert summary["trend"]["available"] is False
    assert summary["trend"]["cash_change_percent"] is None
    assert "incomplete" in summary["trend"]["reason"]


def test_even_median_uses_half_up():
    summary = payment_summary(
        [
            _receipt("A", "10.10", date(2024, 4, 1)),
            _receipt("B", "10.20", date(2024, 4, 2)),
        ],
        as_of=date(2024, 9, 19),
        start_month=4,
        coverage={"complete": True, "start": "2023-04-01"},
    )
    assert summary["typical_amount"] == 10.15


def test_customer_profile_keeps_the_receipt_date():
    projected = project_customer({
        "coverage": {"complete": True, "start": "2023-04-01"},
        "opening": {"status": "imported", "amount": "0"},
        "settlement": {
            "reconciliation": {"ledger_net": "0"},
            "receipts": [_receipt("R1", 40, date(2024, 5, 1), evidence="inferred")],
            "allocations": [],
            "unused_credits": [],
            "open_debits": [],
        },
    }, date(2024, 9, 19), start_month=4)
    assert projected["payments"]["cash_total"] == 40.0
    assert projected["payments"]["transactions"][0]["date"] == "2024-05-01"
    assert projected["payments"]["transactions"][0]["settlement_evidence"] == "inferred"


def test_settlement_keeps_the_receipt_date_when_the_invoice_is_later():
    result = settle(
        [{
            "source_id": "INV",
            "amount": 100,
            "effective_date": date(2024, 9, 19),
            "invoice_date": date(2024, 9, 19),
        }],
        [
            {"source_id": "R-OLD", "amount": 80, "effective_date": date(2023, 5, 1), "cash": True},
            {"source_id": "R-NEW", "amount": 40, "effective_date": date(2024, 5, 1), "cash": True},
        ],
        as_of=date(2024, 9, 19),
    )
    by_id = {row["source_id"]: row for row in result["receipts"]}
    assert by_id["R-OLD"]["effective_date"] == date(2023, 5, 1)
    assert by_id["R-NEW"]["effective_date"] == date(2024, 5, 1)
    assert float(by_id["R-OLD"]["amount"]) == 80.0
    assert float(by_id["R-NEW"]["amount"]) == 40.0
    summary = payment_summary(
        result["receipts"],
        as_of=date(2024, 9, 19),
        start_month=4,
        coverage={"complete": True, "start": "2023-04-01"},
    )
    assert summary["median_gap_days"] == 366
    assert summary["transactions"][0]["settlement_evidence"] == "inferred"
