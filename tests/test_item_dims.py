from datetime import datetime

from server.item_attrs import ATTR_TYPE
from server.item_dims import get_item_dim, list_item_dims
from server.items360 import get_item, list_items
from server.persist import persist_type
from server.rows import query_rows
from server.run_views import build_views_snapshot, snapshot_get_item_dim, snapshot_list_item_dims
from server.store import reset_store_for_tests


STOCK_MAP = {"column_map": {}, "unique_key": ["Item Name"]}
ITEMS_MAP = {"column_map": {}, "unique_key": ["Date", "Item Name", "Qty", "Rate"]}


def _attr(store, name):
    row = store.find_row(ATTR_TYPE, name)
    return (row or {}).get("fields") or {}


def test_unmapped_import_keeps_brand_and_mapped_blank_clears_it():
    store = reset_store_for_tests()
    persist_type(
        store, "stock",
        ["Item Name", "Qty", "P.Price", "Brand"],
        [["Pen", 10, 5, "Mill"]],
        STOCK_MAP, "u1",
    )
    assert _attr(store, "Pen")["Brand"] == "Mill"
    assert _attr(store, "Pen")["Brand Source"] == "stock"

    persist_type(
        store, "stock",
        ["Item Name", "Qty", "P.Price"],
        [["Pen", 12, 5]],
        STOCK_MAP, "u2",
    )
    assert _attr(store, "Pen")["Brand"] == "Mill"

    persist_type(
        store, "stock",
        ["Item Name", "Qty", "P.Price", "Brand"],
        [["Pen", 12, 5, ""]],
        STOCK_MAP, "u3",
    )
    assert _attr(store, "Pen")["Brand"] == ""
    assert "NO_GROUP" not in _attr(store, "Pen").values()

    persist_type(
        store, "items",
        ["Date", "Item Name", "Qty", "Rate", "Brand"],
        [["15-06-26", "Pen", 1, 10, "Nope"]],
        ITEMS_MAP, "u4",
    )
    assert _attr(store, "Pen")["Brand"] == ""
    assert _attr(store, "Pen")["Brand Source"] == "stock"


def test_items_fill_a_field_stock_did_not_map():
    store = reset_store_for_tests()
    persist_type(
        store, "stock",
        ["Item Name", "Qty", "P.Price"],
        [["Pen", 4, 2]],
        STOCK_MAP, "u1",
    )
    assert store.rows_of_type(ATTR_TYPE) == []
    persist_type(
        store, "items",
        ["Date", "Item Name", "Qty", "Rate", "Category"],
        [["15-06-26", "Pen", 2, 8, "Pens"]],
        ITEMS_MAP, "u2",
    )
    assert _attr(store, "Pen")["Category"] == "Pens"
    assert _attr(store, "Pen")["Category Source"] == "items"
    assert _attr(store, "Pen").get("Brand", "") == ""


def test_stock_value_wins_when_both_map_the_field():
    store = reset_store_for_tests()
    persist_type(
        store, "items",
        ["Date", "Item Name", "Qty", "Rate", "Supplier"],
        [["15-06-26", "Pen", 1, 10, "Line Co"]],
        ITEMS_MAP, "u1",
    )
    persist_type(
        store, "stock",
        ["Item Name", "Qty", "P.Price", "Supplier"],
        [["Pen", 3, 4, "Mill"]],
        STOCK_MAP, "u2",
    )
    assert _attr(store, "Pen")["Supplier"] == "Mill"
    assert _attr(store, "Pen")["Supplier Source"] == "stock"


def test_blank_category_is_only_the_none_row_and_filled_categories_sum():
    store = reset_store_for_tests()
    store._force_as_of = datetime(2026, 10, 4, 12)
    persist_type(
        store, "stock",
        ["Item Name", "Qty", "P.Price", "Category", "Item Group", "Brand", "Supplier"],
        [
            ["Pen", 10, 5, "Stationery", "Writing", "Mill", "Acme"],
            ["Pencil", 4, 2, "Stationery", "Writing", "Note", "Acme"],
            ["Eraser", 3, 1, "", "", "", ""],
        ],
        STOCK_MAP, "u1",
    )
    persist_type(
        store, "items",
        ["Date", "Item Name", "Qty", "Rate", "Group", "Sales Rep"],
        [
            ["15-06-26", "Pen", 2, 20, "South", "Ria"],
            ["15-06-26", "Pencil", 1, 10, "South", "Ria"],
            ["15-06-26", "Eraser", 5, 4, "North", "Ria"],
        ],
        ITEMS_MAP, "u2",
    )
    listed = list_item_dims(store, "category", {})
    by_name = {row["name"]: row for row in listed["rows"]}
    assert set(by_name) == {"Stationery", "No category"}
    assert by_name["Stationery"]["items"] == 2
    assert by_name["Stationery"]["qty"] == 14
    assert by_name["Stationery"]["stock_value"] == 58
    assert by_name["Stationery"]["sales_qty"] == 3
    assert by_name["Stationery"]["sales_value"] == 50
    assert by_name["Stationery"]["brand_count"] == 2
    assert by_name["Stationery"]["supplier_count"] == 1
    assert by_name["No category"]["brand_count"] == 1
    stationery = get_item_dim(store, "category", "Stationery")
    assert {row["brand"] for row in stationery["members"]} == {"Mill", "Note"}
    assert {row["supplier"] for row in stationery["members"]} == {"Acme"}
    assert stationery["overall"]["qty"] == 3
    assert stationery["overall"]["amount"] == 50
    assert stationery["months"] == [{"key": "2026-06", "label": "Jun 2026", "qty": 3, "amount": 50, "times": 2}]
    assert stationery["fy_years"][0]["label"] == "FY 2026-27"
    assert stationery["fy_years"][0]["amount"] == 50
    assert "months" not in by_name["Stationery"]
    assert "fy_years" not in by_name["Stationery"]
    assert by_name["Stationery"]["trend"] in ("up", "down", "flat")
    assert by_name["Stationery"]["up_count"] + by_name["Stationery"]["down_count"] + by_name["Stationery"]["flat_count"] == 2
    assert "groups" not in by_name["Stationery"]
    assert stationery["groups"][0]["name"] == "South"
    assert stationery["groups"][0]["amount"] == 50
    assert stationery["groups"][0]["qty"] == 3
    assert stationery["reps"][0]["name"] == "Ria"
    assert stationery["reps"][0]["amount"] == 50
    assert listed["totals"]["sales_value"] == 70
    assert listed["totals"]["stock_value"] == 61
    assert by_name["No category"]["uk"] == "__none__"
    assert by_name["No category"]["items"] == 1
    assert by_name["No category"]["qty"] == 3
    assert by_name["No category"]["sales_value"] == 20
    assert "members" not in by_name["Stationery"]

    writing = get_item_dim(store, "item-group", "Writing")
    assert writing["name"] == "Writing"
    assert writing["items"] == 2

    pen_stock = store.find_row("stock", "Pen")["fields"]
    assert pen_stock["Category"] == "Stationery"
    assert pen_stock["Item Group"] == "Writing"
    assert pen_stock["Brand"] == "Mill"
    assert pen_stock["Supplier"] == "Acme"
    stock_rows = {row["item"]: row for row in query_rows(store, {"type": "stock"})["rows"]}
    assert stock_rows["Pen"]["category"] == "Stationery"
    assert stock_rows["Pen"]["item_group"] == "Writing"
    assert stock_rows["Pen"]["brand"] == "Mill"
    assert stock_rows["Pen"]["supplier"] == "Acme"
    cards = {row["name"]: row for row in list_items(store, {})["items"]}
    assert cards["Pen"]["category"] == "Stationery"
    assert cards["Pen"]["item_group"] == "Writing"
    assert cards["Pen"]["brand"] == "Mill"
    assert cards["Pen"]["supplier"] == "Acme"

    pen = get_item(store, "Pen")
    assert pen["category"] == "Stationery"
    assert pen["category_uk"] == "Stationery"
    assert pen["brand"] == "Mill"
    assert pen["brand_uk"] == "Mill"
    assert pen["supplier"] == "Acme"

    eraser = get_item(store, "Eraser")
    assert eraser["category"] == "No category"
    assert eraser["category_uk"] == "__none__"
    assert eraser["item_group"] == "No item group"
    assert eraser["brand"] == "No brand"
    assert eraser["supplier"] == "No supplier"
    assert _attr(store, "Eraser")["Category"] == ""
    assert cards["Eraser"]["category"] == "No category"
    assert cards["Eraser"]["item_group"] == "No item group"
    assert stock_rows["Eraser"]["category"] == "No category"
    assert stock_rows["Eraser"]["brand"] == "No brand"
    assert stock_rows["Eraser"]["supplier"] == "No supplier"


def test_none_row_is_omitted_when_every_item_has_a_value():
    store = reset_store_for_tests()
    store._force_as_of = datetime(2026, 10, 4, 12)
    persist_type(
        store, "stock",
        ["Item Name", "Qty", "P.Price", "Brand"],
        [["Pen", 1, 1, "Mill"], ["Pencil", 1, 1, "Mill"]],
        STOCK_MAP, "u1",
    )
    listed = list_item_dims(store, "brand", {})
    assert [row["name"] for row in listed["rows"]] == ["Mill"]
    assert get_item_dim(store, "brand", "__none__") is None


def test_item_dims_are_read_from_the_snapshot_only():
    store = reset_store_for_tests()
    persist_type(
        store, "stock",
        ["Item Name", "Qty", "P.Price", "Supplier"],
        [["Pen", 2, 3, "Mill"]],
        STOCK_MAP, "u1",
    )
    missing = snapshot_list_item_dims(store, "supplier", {}, {"directory": {}})
    assert missing["needs_rebuild"] is True
    assert missing["rows"] == []
    assert snapshot_list_item_dims(store, "supplier", {}, None)["needs_rebuild"] is True
    views = build_views_snapshot(store)
    assert set(views["item_dims"]) == {"category", "item_group", "brand", "supplier"}
    packed = snapshot_list_item_dims(store, "supplier", {}, views)
    assert packed["from_snapshot"] is True
    assert not packed.get("needs_rebuild")
    assert packed["rows"][0]["name"] == "Mill"
    saved = views["item_dims"]["supplier"]["details"]["Mill"]
    assert saved.get("members") in (None, [])
    opened = snapshot_get_item_dim(store, "supplier", "Mill", views, {})
    assert opened["members"] == []
    opened = snapshot_get_item_dim(store, "supplier", "Mill", views, {"members": "1"})
    assert opened["member_total"] == 1
    assert opened["members"][0]["name"] == "Pen"
    none_row = snapshot_list_item_dims(store, "category", {}, views)
    assert none_row["from_snapshot"] is True
    assert [row["name"] for row in none_row["rows"]] == ["No category"]
    assert list_item_dims(store, "not-a-dimension", {}) is None
