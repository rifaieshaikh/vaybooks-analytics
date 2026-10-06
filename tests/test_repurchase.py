from datetime import datetime

from server.repurchase import build_repurchase_index, ensure_repurchase, repurchase_for


def _line(year, month, day, item, party, qty=1, amount=10, invoice="", group="", rep="", extra=""):
    when = datetime(year, month, day, 12)
    return {
        "date": when,
        "name": item,
        "uk": item,
        "qty": qty,
        "amount": amount,
        "party": party,
        "group": group,
        "rep": rep,
        "invoice": invoice or extra or ("INV-%s" % day),
        "invoice_id": invoice or ("id-%s-%s" % (item, day)),
    }


def _index(lines, attrs=None, as_of=None):
    by_uk = {}
    for line in lines:
        by_uk.setdefault(line["uk"].lower(), []).append(line)
    return build_repurchase_index(by_uk, attrs or {}, as_of or datetime(2026, 6, 1, 12), start_month=4)


def _counts(summary):
    return {row["key"]: row["count"] for row in summary["overall"]["buckets"]}


def test_wait_between_same_item_purchases_excludes_same_day_companion():
    index = _index([
        _line(2026, 3, 1, "A", "Ravi", invoice="1"),
        _line(2026, 3, 1, "B", "Ravi", invoice="1"),
        _line(2026, 3, 10, "C", "Ravi", invoice="2"),
        _line(2026, 3, 20, "D", "Ravi", invoice="3"),
        _line(2026, 3, 20, "E", "Ravi", invoice="3"),
        _line(2026, 5, 1, "A", "Ravi", invoice="4"),
        _line(2026, 5, 1, "F", "Ravi", invoice="4"),
    ], as_of=datetime(2026, 6, 1, 12))
    got = repurchase_for(index, item="A")
    assert got["overall"]["orders"] == 1
    line = got["overall"]["lines"][0]
    assert line["gap_days"] == 61
    assert line["prev_iso"] == "2026-03-01"
    assert {row["name"] for row in line["between"]} == {"C", "D", "E"}
    assert line["intervene_orders"] == 2
    assert line["intervene_items"] == 3
    wait = {row["name"] for row in got["overall"]["wait_items"]}
    assert wait == {"C", "D", "E"}
    same = {row["name"] for row in got["overall"]["same_day_items"]}
    assert same == {"F"}
    assert "B" not in wait
    assert got["overall"]["median"] == 61
    assert got["repeaters"] == 1
    assert got["member_axis"] == "customer"
    assert got["timeline"][0]["name"] == "Ravi"
    assert [point["gap_days"] for point in got["timeline"][0]["points"]] == [None, 61]


def test_same_day_invoices_of_one_item_are_one_purchase():
    index = _index([
        _line(2026, 3, 1, "A", "Ravi", invoice="1"),
        _line(2026, 3, 1, "A", "Ravi", invoice="2", amount=4),
        _line(2026, 3, 21, "A", "Ravi", invoice="3", amount=8),
    ])
    got = repurchase_for(index, item="A")
    assert got["overall"]["orders"] == 1
    assert got["overall"]["lines"][0]["gap_days"] == 20
    assert got["overall"]["lines"][0]["amount"] == 8
    assert _counts(got)["w4"] == 1


def test_single_purchase_is_not_a_gap():
    index = _index([_line(2026, 3, 1, "A", "Ravi")])
    got = repurchase_for(index, item="A")
    assert got["overall"]["orders"] == 0
    assert got["once"] == 1
    assert got["repeaters"] == 0
    assert sum(_counts(got).values()) == 0
    assert got["timeline"][0]["name"] == "Ravi"
    assert got["timeline"][0]["purchases"] == 1
    assert len(got["timeline"][0]["points"]) == 1
    assert got["overdue"] == []


def test_open_cycle_stays_out_of_the_histogram_and_can_be_overdue():
    index = _index([
        _line(2026, 1, 1, "A", "Ravi", amount=10),
        _line(2026, 2, 1, "A", "Ravi", amount=12),
    ], as_of=datetime(2026, 4, 15, 12))
    got = repurchase_for(index, item="A")
    assert got["overall"]["orders"] == 1
    assert sum(_counts(got).values()) == 1
    assert _counts(got)["m2"] == 1
    assert got["overdue"][0]["days_since"] == 73
    assert got["overdue"][0]["median"] == 31
    assert got["overdue"][0]["party"] == "Ravi"
    assert got["overdue"][0]["item"] == "A"


def test_category_filter_keeps_each_customers_own_gap():
    attrs = {
        "apple": {"Category": "Food"},
        "pear": {"Category": "Drink"},
    }
    index = _index([
        _line(2026, 1, 1, "Apple", "Ann", amount=10),
        _line(2026, 1, 11, "Apple", "Ann", amount=10),
        _line(2026, 1, 1, "Apple", "Bea", amount=40),
        _line(2026, 4, 11, "Apple", "Bea", amount=40),
        _line(2026, 1, 1, "Pear", "Ann", amount=5),
        _line(2026, 1, 6, "Pear", "Ann", amount=5),
    ], attrs=attrs)
    food = repurchase_for(index, category="Food")
    gaps = sorted(row["gap_days"] for row in food["overall"]["lines"])
    assert gaps == [10, 100]
    assert food["overall"]["orders"] == 2
    assert food["overall"]["value"] == 50
    assert food["member_axis"] == "item"
    assert {row["name"] for row in food["overall"]["members"]} == {"Apple"}
    assert food["once"] == 0
    assert food["repeaters"] == 2
    drink = repurchase_for(index, category="Drink")
    assert [row["gap_days"] for row in drink["overall"]["lines"]] == [5]


def test_customer_history_lists_every_item_including_one_purchase():
    index = _index([
        _line(2026, 1, 1, "Apple", "Ravi"),
        _line(2026, 3, 1, "Apple", "Ravi"),
        _line(2026, 2, 1, "Banana", "Ravi"),
        _line(2026, 2, 2, "Cherry", "Ravi"),
        _line(2026, 1, 5, "Apple", "Bea"),
    ])
    got = repurchase_for(index, party="Ravi")
    assert [row["name"] for row in got["timeline"]] == ["Apple", "Banana", "Cherry"]
    apple = got["timeline"][0]
    assert apple["kind"] == "item"
    assert apple["purchases"] == 2
    assert len(apple["points"]) == 2
    assert got["timeline"][1]["purchases"] == 1
    item = repurchase_for(index, item="Apple")
    assert [row["name"] for row in item["timeline"]] == ["Bea", "Ravi"]
    assert item["timeline"][0]["kind"] == "customer"


def test_dimension_history_keeps_each_customer_and_item():
    attrs = {"apple": {"Category": "Food"}, "pear": {"Category": "Food"}}
    index = _index([
        _line(2026, 1, 1, "Apple", "Ann"),
        _line(2026, 2, 1, "Pear", "Bea"),
    ], attrs=attrs)
    food = repurchase_for(index, category="Food")
    assert {row["kind"] for row in food["timeline"]} == {"both"}
    assert {row["item"] for row in food["timeline"]} == {"Apple", "Pear"}
    assert {row["party"] for row in food["timeline"]} == {"Ann", "Bea"}


def test_index_is_cached_on_the_book():
    as_of = datetime(2026, 6, 1, 12)
    book = {
        "item_lines_by_uk": {"a": [_line(2026, 1, 1, "A", "Ravi"), _line(2026, 2, 1, "A", "Ravi")]},
        "item_attrs": {},
        "as_of": as_of,
        "fiscal_year_start_month": 4,
    }
    first = ensure_repurchase(book)
    second = ensure_repurchase(book)
    assert first is second
    assert first["cycles"][0]["gap_days"] == 31
