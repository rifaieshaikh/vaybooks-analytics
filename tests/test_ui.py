"""Report identification in the UI: match by id/flags, not engine title."""

from vay.ui import (
    filter_dataframe,
    find_followup,
    followup_groups,
    friendly_title,
    is_wide_report,
    missing_pack_notes,
    report_group,
    search_columns,
    visible_groups,
)


def _follow(prefix, group):
    title_prefix = "Sales follow-up" if prefix.startswith("sales") else "Collection follow-up"
    return {
        "id": prefix + group,
        "title": "%s — %s" % (title_prefix, group),
        "headers": ["Customer", "Status"],
        "rows": [["Acme", "URGENT"]],
        "total": None,
        "key_col": 0,
        "followup": True,
        "status_header": "Status",
    }


def test_followup_routes_by_id_not_title():
    south = _follow("sales_follow_up_", "SOUTH")
    assert report_group(south) == "Follow-up"
    assert friendly_title(south) == "Who to follow up — sales"
    assert find_followup([south], "sales", "SOUTH") is south
    assert followup_groups([south], "collection") == []
    assert followup_groups([south], "sales") == ["SOUTH"]


def test_visible_groups_default_order_and_hide_empty_warnings():
    reports = [
        {"id": "sales_rep_performance_report", "title": "Sales rep performance", "rows": [[]]},
        {"id": "source_data_warnings", "title": "Source data warnings", "rows": []},
        {
            "id": "fiscal_monthly_account_performance_report",
            "title": "Fiscal monthly account",
            "wide": "pair",
            "rows": [[]],
        },
    ]
    assert visible_groups(reports) == ["Performance", "Monthly"]


def test_wide_flag_drives_year_picker():
    assert is_wide_report({"id": "monthly_profit_report", "wide": "month"})
    assert is_wide_report({"id": "item_wise_monthly_qty", "wide": "month", "trailing": 3})
    assert not is_wide_report({"id": "sales_rep_performance_report"})


def test_search_columns_fiscal_account_and_warnings():
    fiscal = {
        "id": "fiscal_monthly_account_performance_report",
        "key_col": 0,
        "headers": ["Account Name", "Group", "April"],
    }
    assert search_columns(fiscal, fiscal["headers"]) == [0, 1]
    warn = {
        "id": "source_data_warnings",
        "key_col": 2,
        "headers": ["Type", "Source", "Key", "Detail"],
    }
    assert search_columns(warn, warn["headers"]) == [0, 2, 3]


def test_filter_keeps_total_only_when_report_has_total():
    import pandas as pd

    perf = {
        "id": "sales_rep_performance_report",
        "key_col": 0,
        "total": ["TOTAL", 1],
        "headers": ["Sales Rep", "YTD"],
    }
    df = pd.DataFrame([["Ann", 1], ["TOTAL", 2]], columns=["Sales Rep", "YTD"])
    out = filter_dataframe(df, perf, "ann")
    assert list(out["Sales Rep"]) == ["Ann", "TOTAL"]

    follow = _follow("collection_follow_up_", "SOUTH")
    fdf = pd.DataFrame([["Acme", "WATCH"], ["TOTAL", "x"]], columns=["Customer", "Status"])
    fout = filter_dataframe(fdf, follow, "acme")
    assert list(fout["Customer"]) == ["Acme"]


def test_missing_pack_notes_from_sheets_not_status():
    notes = missing_pack_notes({"items": True, "profit": True}, ["sales", "receipt", "arr"])
    assert "Items need sheets named items and stock." in notes
    assert any("Profit needs" in n for n in notes)
    assert missing_pack_notes({"items": False, "profit": False}, ["sales"]) == []
