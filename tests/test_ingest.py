from server.ingest import prepare_rows
from server.mappers import validate_mapper
from server.persist import persist_type
from server.store import reset_store_for_tests


SALES_MAP = {
    "column_map": {},
    "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"],
}
ARR_MAP = {"column_map": {}, "unique_key": ["Account Name"]}
STOCK_MAP = {"column_map": {}, "unique_key": ["Item Name"]}


def test_two_headers_to_one_field_rejected():
    err = validate_mapper("sales", {
        "column_map": {"Date": "Date", "Bill Date": "Date"},
        "unique_key": ["Date"],
    })
    assert err


def test_total_and_blank_skipped_before_collapse():
    headers = ["Item Name", "Qty", "P.Price"]
    rows = [
        ["Total", 9, 1],
        ["", 1, 1],
        ["SKU", 2, 10],
        ["SKU", 3, 10],
    ]
    prepared, counts, rejects = prepare_rows("stock", headers, rows, STOCK_MAP)
    assert counts["total_skipped"] == 1
    assert counts["blank_skipped"] == 1
    assert len(prepared) == 1
    assert prepared[0][0]["Qty"] == 5
    reasons = {r["reason"] for r in rejects}
    assert "total_row" in reasons
    assert "blank_name" in reasons


def test_two_stock_rows_same_item_sum_qty():
    headers = ["Item Name", "Qty", "P.Price"]
    rows = [["SKU", 2, 10], ["SKU", 3, 20]]
    prepared, _counts, _rejects = prepare_rows("stock", headers, rows, STOCK_MAP)
    fields, _uk = prepared[0]
    assert fields["Qty"] == 5
    assert abs(fields["P.Price"] - 16.0) < 0.01  # (2*10+3*20)/5


def test_two_arr_rows_last_wins():
    headers = ["Account Name", "Group", "Balance", "Days"]
    rows = [["Acme", "G1", 10, 1], ["Acme", "G2", 99, 5]]
    prepared, _counts, _rejects = prepare_rows("arr", headers, rows, ARR_MAP)
    fields, _uk = prepared[0]
    assert fields["Balance"] == 99
    assert fields["Group"] == "G2"


def test_party_rows_last_wins():
    headers = ["Account Name", "Group"]
    rows = [["Acme", "South"], ["Acme", "North"]]
    mapper = {"column_map": {}, "unique_key": ["Account Name"]}
    prepared, _counts, _rejects = prepare_rows("party", headers, rows, mapper)
    assert len(prepared) == 1
    assert prepared[0][0]["Group"] == "North"


def test_event_in_file_keeps_first():
    headers = ["Date", "Party Name", "Sales Rep", "Net Amount"]
    rows = [
        ["19-09-24", "Acme", "R", 10],
        ["19-09-24", "Acme", "R", 10],
    ]
    prepared, counts, rejects = prepare_rows("sales", headers, rows, SALES_MAP)
    assert len(prepared) == 1
    assert counts["clash"] == 1
    assert any(r["reason"] == "duplicate_in_file" for r in rejects)


def test_failed_row_continues():
    headers = ["Date", "Party Name", "Sales Rep", "Net Amount"]
    rows = [
        ["bad", "Acme", "R", 10],
        ["19-09-24", "Beta", "R", 10],
    ]
    prepared, counts, rejects = prepare_rows("sales", headers, rows, SALES_MAP)
    assert counts["failed_row"] == 1
    assert len(prepared) == 1
    assert any(r["reason"] == "failed_key" for r in rejects)


def test_second_arr_file_upserts():
    store = reset_store_for_tests()
    headers = ["Account Name", "Group", "Balance"]
    persist_type(store, "arr", headers, [["Acme", "G", 10]], ARR_MAP, "u1")
    persist_type(store, "arr", headers, [["Acme", "G", 77]], ARR_MAP, "u2")
    rows = store.rows_of_type("arr")
    assert len(rows) == 1
    assert rows[0]["fields"]["Balance"] == 77
    assert rows[0]["source_upload_id"] == "u2"


def test_event_second_file_skips_and_keeps_original_count():
    store = reset_store_for_tests()
    headers = ["Date", "Party Name", "Sales Rep", "Net Amount"]
    row = [["19-09-24", "Acme", "R", 10]]
    c1 = persist_type(store, "sales", headers, row, SALES_MAP, "u1")
    c2 = persist_type(store, "sales", headers, row, SALES_MAP, "u2")
    assert c1["added"] == 1
    assert c2["skipped"] == 1
    assert len(store.rows_of_type("sales")) == 1


def test_event_second_file_updates_when_mode_update():
    store = reset_store_for_tests()
    headers = ["Date", "Party Name", "Sales Rep", "Net Amount"]
    first = [["19-09-24", "Acme", "R", 10]]
    persist_type(store, "sales", headers, first, SALES_MAP, "u1")
    out = persist_type(store, "sales", headers, first, SALES_MAP, "u2", event_mode="update")
    assert out.get("updated") == 1
    rows = store.rows_of_type("sales")
    assert len(rows) == 1
    assert rows[0]["source_upload_id"] == "u2"


def test_event_update_does_not_delete_other_rows():
    store = reset_store_for_tests()
    headers = ["Date", "Party Name", "Sales Rep", "Net Amount"]
    persist_type(store, "sales", headers, [["19-09-24", "Acme", "R", 10]], SALES_MAP, "u1")
    persist_type(store, "sales", headers, [["20-09-24", "Beta", "R", 20]], SALES_MAP, "u2")
    persist_type(store, "sales", headers, [["19-09-24", "Acme", "R", 10]], SALES_MAP, "u3", event_mode="update")
    assert len(store.rows_of_type("sales")) == 2


def test_dry_run_preview_already_exists_and_rejects():
    store = reset_store_for_tests()
    headers = ["Date", "Party Name", "Sales Rep", "Net Amount"]
    persist_type(store, "sales", headers, [["19-09-24", "Acme", "R", 10]], SALES_MAP, "u1")
    out = persist_type(
        store,
        "sales",
        headers,
        [
            ["19-09-24", "Acme", "R", 10],
            ["19-09-24", "Total", "R", 1],
            ["19-09-24", "", "R", 1],
            ["19-09-24", "Acme", "R", 10],
            ["20-09-24", "Beta", "R", 20],
        ],
        SALES_MAP,
        "u2",
        dry_run=True,
    )
    assert out["dry_run"] is True
    assert out["added"] == 1
    assert out["skipped"] == 1
    assert out["skipped_total"] >= 4  # total + blank + clash + already_exists
    reasons = {r["reason"] for r in out["preview_rows"]["skipped"]}
    assert "already_exists" in reasons
    assert "total_row" in reasons
    assert "blank_name" in reasons
    assert "duplicate_in_file" in reasons
    assert len(out["preview_rows"]["added"]) == 1
    assert out["preview_rows"]["added"][0]["fields"]["Party Name"] == "Beta"
    assert len(store.rows_of_type("sales")) == 1


def test_dry_run_replace_batch_would_delete():
    store = reset_store_for_tests()
    headers = ["Date", "Party Name", "Sales Rep", "Net Amount"]
    persist_type(store, "sales", headers, [["19-09-24", "Acme", "R", 10]], SALES_MAP, "u1")
    out = persist_type(
        store,
        "sales",
        headers,
        [["19-09-24", "Acme", "R", 10]],
        SALES_MAP,
        "u2",
        event_mode="replace_batch",
        dry_run=True,
    )
    assert out["would_delete"] == 1
    assert out["added"] == 1
    assert out["preview_rows"]["would_delete"][0]["reason"] == "would_replace_batch"
    assert len(store.rows_of_type("sales")) == 1
