from datetime import datetime

from server.customers import merge_sales_gaps, sales_gap_periods, sales_gaps_from_detail


def _order(year, month, day, amount, party="A"):
    when = datetime(year, month, day, 12)
    return {
        "date": when,
        "date_iso": when.strftime("%Y-%m-%d"),
        "date_label": when.strftime("%d %b %Y"),
        "amount": amount,
        "invoice": "INV-%s" % day,
        "party": party,
        "customer_uk": party.lower(),
    }


def _counts(summary):
    return {row["key"]: row["count"] for row in summary["overall"]["buckets"]}


def test_order_gap_uses_each_customers_previous_order():
    as_of = datetime(2026, 1, 31, 12)
    alpha = sales_gap_periods([
        _order(2025, 3, 1, 4),
        _order(2026, 1, 1, 10),
        _order(2026, 1, 20, 30),
    ], as_of, start_month=4)
    counts = _counts(alpha)
    assert counts["first"] == 1
    assert counts["d90"] == 1
    assert counts["d15_30"] == 1
    assert alpha["fy"]["orders"] == 2
    assert alpha["month"]["orders"] == 2
    assert alpha["overall"]["orders"] == 3
    assert [row["key"] for row in alpha["by_fy"]] == ["2025-04-01", "2024-04-01"]
    assert alpha["by_fy"][0]["orders"] == 2
    assert alpha["by_fy"][1]["orders"] == 1
    assert [row["key"] for row in alpha["months"]] == ["2026-01", "2025-03"]
    assert alpha["months"][1]["orders"] == 1

    beta = sales_gap_periods([_order(2026, 1, 2, 5, "B")], as_of, start_month=4)
    merged = merge_sales_gaps([alpha, beta])
    merged_counts = _counts(merged)
    assert merged_counts["first"] == 2
    assert merged_counts["d15_30"] == 1
    assert merged["overall"]["value"] == 49
    jan = next(row for row in merged["months"] if row["key"] == "2026-01")
    assert jan["orders"] == 3


def test_same_day_invoices_are_one_order():
    detail = {
        "name": "A",
        "uk": "a",
        "as_of": "2026-01-31",
        "fiscal_year_start_month": 4,
        "activity": [
            {"kind": "sale", "date": "2026-01-01", "amount": 10, "invoice": "1"},
            {"kind": "sale", "date": "2026-01-01", "amount": 5, "invoice": "2"},
            {"kind": "collection", "date": "2026-01-02", "amount": 3},
            {"kind": "sale", "date": "2026-01-21", "amount": 8, "invoice": "3"},
        ],
    }
    got = sales_gaps_from_detail(detail)
    assert got["overall"]["orders"] == 2
    first = next(row for row in got["overall"]["buckets"] if row["key"] == "first")
    follow = next(row for row in got["overall"]["buckets"] if row["key"] == "d15_30")
    assert first["value"] == 15
    assert follow["count"] == 1
    assert follow["value"] == 8
