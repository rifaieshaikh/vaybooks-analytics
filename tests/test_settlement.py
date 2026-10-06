"""Unit tests for collection settlement, LIFO due, and configurable bands."""

from datetime import datetime

import pytest

from vay.settlement import (
    BUCKET_KEYS,
    allocate_collections,
    allocate_open,
    bucket_key,
    empty_buckets,
    estimate_opening_amount,
    normalize_aging_bands,
    normalize_mode,
    oldest_due_invoice,
)


def test_bucket_key_six_bands():
    assert bucket_key(0) == "d0_15"
    assert bucket_key(15) == "d0_15"
    assert bucket_key(16) == "d15_30"
    assert bucket_key(30) == "d15_30"
    assert bucket_key(31) == "d30_45"
    assert bucket_key(45) == "d30_45"
    assert bucket_key(46) == "d45_60"
    assert bucket_key(60) == "d45_60"
    assert bucket_key(61) == "d60_90"
    assert bucket_key(90) == "d60_90"
    assert bucket_key(91) == "d90"


def test_bucket_key_custom_bands():
    bands = normalize_aging_bands([
        {"key": "a", "label": "0–7", "max_days": 7},
        {"key": "b", "label": "7+", "max_days": None},
    ])
    assert bucket_key(7, bands) == "a"
    assert bucket_key(8, bands) == "b"


def test_oldest_due_invoice_ignores_opening_when_sales_exist():
    meta = oldest_due_invoice([
        {"kind": "opening", "age_days": 174, "due": 500, "what": "Opening balance"},
        {"kind": "sale", "age_days": 42, "due": 200, "invoice": "INV-1", "what": "Sale"},
        {"kind": "sale", "age_days": 12, "due": 100, "invoice": "INV-2", "what": "Sale"},
    ])
    assert meta["age_days"] == 42
    assert meta["kind"] == "sale"
    assert meta["invoice"] == "INV-1"


def test_oldest_due_invoice_falls_back_to_opening():
    meta = oldest_due_invoice([
        {"kind": "opening", "age_days": 174, "due": 500, "what": "Opening balance"},
    ])
    assert meta["age_days"] == 174
    assert meta["kind"] == "opening"


def test_normalize_aging_bands_rejects_unsorted():
    with pytest.raises(ValueError):
        normalize_aging_bands([
            {"key": "a", "label": "30", "max_days": 30},
            {"key": "b", "label": "15", "max_days": 15},
            {"key": "c", "label": "+", "max_days": None},
        ])


def test_normalize_mode_migrates_latest():
    assert normalize_mode("") == "oldest"
    assert normalize_mode("latest") == "oldest"
    assert normalize_mode("SPECIFIC") == "specific"
    assert normalize_mode("oldest") == "oldest"


def test_estimate_opening_amount():
    invoices = [{"amount": 100}, {"amount": 50}]
    receipts = [{"amount": 80}]
    assert estimate_opening_amount(70, invoices, receipts) == 0
    assert estimate_opening_amount(100, invoices, receipts) == 30
    # AR is already net of the credit note, so the note is added back into opening.
    assert estimate_opening_amount(200, [{"amount": 100}], [{"amount": 50}], [{"amount": 20}]) == 170


def test_allocate_open_always_lifo_no_receipts():
    """Due attribution is always newest→oldest on open invoice amounts."""
    as_of = datetime(2025, 9, 19, 12)
    invoices = [
        {"date": datetime(2024, 6, 15, 12), "amount": 200, "invoice": "OLD", "invoice_id": "a"},
        {"date": datetime(2025, 6, 15, 12), "amount": 100, "invoice": "NEW", "invoice_id": "b"},
    ]
    lines, buckets, opening, _dt = allocate_open(invoices, 150, as_of, mode="oldest")
    assert [x["invoice"] for x in lines] == ["NEW", "OLD"]
    assert lines[0]["due"] == 100
    assert lines[1]["due"] == 50
    assert opening == 0
    assert sum(buckets.values()) == 150


def test_allocate_open_skips_fully_settled_invoice():
    as_of = datetime(2025, 9, 19, 12)
    invoices = [
        {"date": datetime(2024, 6, 15, 12), "amount": 200, "invoice": "OLD", "invoice_id": "a"},
        {"date": datetime(2025, 6, 15, 12), "amount": 100, "invoice": "NEW", "invoice_id": "b"},
    ]
    # Settle NEW fully; due 150 should land on OLD only (NEW remaining 0).
    receipts = [
        {"date": datetime(2025, 7, 1, 12), "amount": 100, "invoice": "NEW"},
    ]
    # opening = 150 + 100 − 300 = 0; specific settles NEW first
    lines, buckets, opening, _dt = allocate_open(
        invoices, 150, as_of, mode="specific", receipts=receipts,
    )
    assert [x["invoice"] for x in lines] == ["OLD"]
    assert lines[0]["due"] == 150
    assert opening == 0
    assert sum(buckets[k] for k in BUCKET_KEYS) == 150


def test_allocate_collections_oldest_opening_first_then_invoices():
    as_of = datetime(2025, 9, 19, 12)
    opening = datetime(2025, 4, 1, 12)
    invoices = [
        {"date": datetime(2025, 8, 1, 12), "amount": 100, "invoice": "A"},
        {"date": datetime(2025, 9, 1, 12), "amount": 50, "invoice": "B"},
    ]
    receipts = [
        {"date": datetime(2025, 9, 10, 12), "amount": 120, "invoice": ""},
    ]
    buckets, allocs, credit, rem, op_left = allocate_collections(
        invoices, receipts, as_of, opening_dt=opening, mode="oldest", due=80,
    )
    assert credit == 0
    assert sum(a["amount"] for a in allocs) == 120
    assert allocs[0]["kind"] == "opening"
    assert allocs[0]["amount"] == 50
    assert allocs[1]["kind"] == "sale"
    assert allocs[1]["invoice"] == "A"
    assert allocs[1]["amount"] == 70
    assert abs(sum(buckets.values()) - 120) < 1e-9
    assert {r["invoice"]: r["remaining"] for r in rem} == {"A": 30.0, "B": 50.0}
    assert op_left == 0


def test_allocate_collections_oldest_no_opening_hits_invoices():
    as_of = datetime(2025, 9, 19, 12)
    opening = datetime(2025, 4, 1, 12)
    invoices = [
        {"date": datetime(2025, 8, 1, 12), "amount": 100, "invoice": "A"},
        {"date": datetime(2025, 9, 1, 12), "amount": 50, "invoice": "B"},
    ]
    receipts = [
        {"date": datetime(2025, 9, 10, 12), "amount": 120, "invoice": ""},
    ]
    buckets, allocs, credit, _rem, _op = allocate_collections(
        invoices, receipts, as_of, opening_dt=opening, mode="oldest", due=0,
    )
    assert credit == 0
    kinds = [a["kind"] for a in allocs]
    assert kinds.count("opening") == 0
    assert kinds.count("sale") == 2
    assert allocs[0]["invoice"] == "A" and allocs[0]["amount"] == 100
    assert allocs[1]["invoice"] == "B" and allocs[1]["amount"] == 20
    assert abs(sum(buckets.values()) - 120) < 1e-9


def test_allocate_collections_specific_no_match_uses_fifo():
    """Unmatched specific receipt uses Oldest to latest (not dump-to-opening only)."""
    as_of = datetime(2025, 9, 19, 12)
    opening = datetime(2025, 4, 1, 12)
    invoices = [
        {"date": datetime(2025, 8, 1, 12), "amount": 100, "invoice": "A"},
        {"date": datetime(2025, 9, 1, 12), "amount": 50, "invoice": "B"},
    ]
    receipts = [
        {"date": datetime(2025, 9, 10, 12), "amount": 40, "invoice": "MISSING"},
    ]
    # due=100 → opening = 100+40-150 = 0 → FIFO hits oldest invoice A
    buckets, allocs, credit, rem, _op = allocate_collections(
        invoices, receipts, as_of, opening_dt=opening, mode="specific", due=100,
    )
    assert credit == 0
    assert len(allocs) == 1
    assert allocs[0]["kind"] == "sale"
    assert allocs[0]["invoice"] == "A"
    assert allocs[0]["amount"] == 40
    assert rem[0]["invoice"] == "A" and rem[0]["remaining"] == 60


def test_allocate_collections_specific_match_then_remainder_fifo():
    as_of = datetime(2025, 9, 19, 12)
    opening = datetime(2025, 4, 1, 12)
    invoices = [
        {"date": datetime(2025, 8, 1, 12), "amount": 100, "invoice": "A"},
        {"date": datetime(2025, 9, 1, 12), "amount": 80, "invoice": "B"},
    ]
    receipts = [
        {"date": datetime(2025, 9, 10, 12), "amount": 120, "invoice": "B"},
    ]
    # due=100 → opening = 100+120-180 = 40
    # Match B: 80, remainder 40 → opening 40
    buckets, allocs, credit, rem, op_left = allocate_collections(
        invoices, receipts, as_of, opening_dt=opening, mode="specific", due=100,
    )
    assert credit == 0
    assert allocs[0]["invoice"] == "B" and allocs[0]["amount"] == 80
    assert allocs[1]["kind"] == "opening" and allocs[1]["amount"] == 40
    assert {r["invoice"]: r["remaining"] for r in rem} == {"A": 100.0}
    assert op_left == 0
    assert abs(sum(buckets.values()) - 120) < 1e-9


def test_allocate_collections_specific_match():
    as_of = datetime(2025, 9, 19, 12)
    invoices = [
        {"date": datetime(2025, 8, 1, 12), "amount": 100, "invoice": "A"},
        {"date": datetime(2025, 9, 1, 12), "amount": 80, "invoice": "B"},
    ]
    receipts = [
        {"date": datetime(2025, 9, 10, 12), "amount": 50, "invoice": "B"},
    ]
    _buckets, allocs, credit, rem, _op = allocate_collections(
        invoices, receipts, as_of, mode="specific", due=130,
    )
    assert credit == 0
    assert allocs[0]["invoice"] == "B"
    assert allocs[0]["amount"] == 50
    assert allocs[0]["age_days"] == (datetime(2025, 9, 10) - datetime(2025, 9, 1)).days
    assert empty_buckets()


def test_credit_note_clears_oldest_and_skips_collection_buckets():
    as_of = datetime(2026, 6, 1, 12)
    invoices = [
        {"date": datetime(2026, 1, 1, 12), "amount": 100, "invoice": "A"},
        {"date": datetime(2026, 3, 1, 12), "amount": 80, "invoice": "B"},
    ]
    credits = [{"date": datetime(2026, 4, 1, 12), "amount": 40, "invoice": "CN-1"}]
    buckets, allocs, credit, rem, _op = allocate_collections(
        invoices, [], as_of, due=140, credits=credits,
    )
    assert sum(buckets.values()) == 0
    assert allocs == []
    assert credit == 0
    assert {r["invoice"]: r["remaining"] for r in rem} == {"A": 60.0, "B": 80.0}

    buckets, allocs, credit, rem, _op = allocate_collections(
        [{"date": datetime(2026, 1, 1, 12), "amount": 100, "invoice": "A"}],
        [],
        as_of,
        due=-50,
        credits=[{"date": datetime(2026, 4, 1, 12), "amount": 150, "invoice": "CN-9"}],
    )
    assert sum(buckets.values()) == 0
    assert credit == 50
    assert rem == []
