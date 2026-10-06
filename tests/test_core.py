from datetime import datetime

from vay.engine import generate
from vay.table import Table


def T(name, headers, rows):
    return Table(name, headers, [list(r) for r in rows])


def tiny_tables():
    return {
        "arr": T("arr", ["Account Name", "Group", "Balance", "Days"], [
            ["Alpha", "South", 1000, 12],
            ["Beta", "North", 0, 0],
        ]),
        "sales": T("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [
            [datetime(2026, 9, 19, 12), "Alpha", "Ravi", 1180],
            [datetime(2026, 7, 20, 12), "Alpha", "Ravi", 500],
            [datetime(2026, 7, 19, 12), "Alpha", "Ravi", 100],
            [datetime(2026, 4, 1, 12), "Beta", "Anu", 2000],
            [datetime(2023, 1, 15, 12), "OldCo", "Ravi", 50],
        ]),
        "receipt": T("receipt", ["Date", "Account Name", "Sales Rep", "Amount"], [
            [datetime(2026, 9, 19, 12), "Alpha", "Ravi", 100],
            [datetime(2026, 9, 19, 12), "Alpha", "INVESTMENT", 999],
        ]),
    }


def by_key(report):
    mapping = {}
    for row in report["rows"]:
        mapping[row[report.get("key_col", 0)]] = row
    if report.get("total"):
        mapping[report["total"][0]] = report["total"]
    return mapping


def test_sales_rep_sort_ytd_and_total_label():
    out = generate(tiny_tables(), datetime(2026, 9, 19, 12), ["core"])
    rep = next(r for r in out["reports"] if r["id"] == "sales_rep_performance_report")
    keys = by_key(rep)
    assert "TOTAL" in keys
    assert "Total" not in keys
    assert keys["Anu"][9] == 2000
    assert keys["Ravi"][9] == 1780
    assert list(r[0] for r in rep["rows"]) == ["Anu", "Ravi"]
    # INVESTMENT collection excluded
    assert keys["Ravi"][2] == 100
    # 2m starts 20 Jul: 1180+500
    assert keys["Ravi"][5] == 1680


def test_account_has_six_due_and_collection_headers():
    out = generate(tiny_tables(), datetime(2026, 9, 19, 12), ["core"])
    acc = next(r for r in out["reports"] if r["id"] == "account_performance_report")
    headers = acc["headers"]
    assert "Due 0–15 Days" in headers
    assert "Due 90+ Days" in headers
    assert "Collection 0–15 Days" in headers
    assert "Collection 90+ Days" in headers
    assert "30 Days Credit Lapsed" not in headers
    rep = next(r for r in out["reports"] if r["id"] == "sales_rep_performance_report")
    assert "Due 0–15 Days" in rep["headers"]
    assert "Collection 90+ Days" in rep["headers"]
    grp = next(r for r in out["reports"] if r["id"] == "group_performance_report")
    assert "Due 0–15 Days" in grp["headers"]


def test_account_ar_days_not_in_total():
    out = generate(tiny_tables(), datetime(2026, 9, 19, 12), ["core"])
    acc = next(r for r in out["reports"] if r["id"] == "account_performance_report")
    total = acc["total"]
    assert total[0] == "Total"
    assert total[2] == ""
    keys = by_key(acc)
    assert keys["Alpha"][2] == 12
    assert keys["Alpha"][9] == 1780


def test_missing_days_is_zero():
    tables = tiny_tables()
    tables["arr"] = T("arr", ["Account Name", "Group", "Balance"], [["Alpha", "South", 1]])
    out = generate(tables, datetime(2026, 9, 19, 12), ["core"])
    acc = next(r for r in out["reports"] if r["id"] == "account_performance_report")
    alpha = next(r for r in acc["rows"] if r[0] == "Alpha")
    assert alpha[2] == 0


def test_group_sort_mtd():
    out = generate(tiny_tables(), datetime(2026, 9, 19, 12), ["core"])
    grp = next(r for r in out["reports"] if r["id"] == "group_performance_report")
    # South has MTD 1180, North MTD 0
    assert grp["rows"][0][0] == "South"


def test_investment_excluded_everywhere():
    out = generate(tiny_tables(), datetime(2026, 9, 19, 12), ["core"])
    acc = next(r for r in out["reports"] if r["id"] == "account_performance_report")
    alpha = next(r for r in acc["rows"] if r[0] == "Alpha")
    assert alpha[4] == 100  # MTD collection


def test_collection_only_customers_when_set():
    tables = tiny_tables()
    tables["receipt"] = T("receipt", ["Date", "Account Name", "Sales Rep", "Amount"], [
        [datetime(2026, 9, 19, 12), "Alpha", "Ravi", 100],
        [datetime(2026, 9, 19, 12), "VendorCo", "Ravi", 500],
    ])
    out = generate(
        tables,
        datetime(2026, 9, 19, 12),
        ["core"],
        org_policy={"customer_accounts": ["Alpha"]},
    )
    acc = next(r for r in out["reports"] if r["id"] == "account_performance_report")
    keys = by_key(acc)
    assert keys["Alpha"][4] == 100
    # VendorCo may appear from ensure() only if it had sales/arr — it shouldn't get collection
    if "VendorCo" in keys:
        assert keys["VendorCo"][4] == 0
    rep = next(r for r in out["reports"] if r["id"] == "sales_rep_performance_report")
    ravi = by_key(rep)["Ravi"]
    assert ravi[2] == 100  # MTD collection excludes VendorCo
    warn = next(r for r in out["reports"] if r["id"] == "source_data_warnings")
    assert any(row[0] == "Non-customer receipt" for row in warn["rows"])


def test_warnings_only_core_or_items():
    out = generate(tiny_tables(), datetime(2026, 9, 19, 12), ["fiscal"])
    ids = [r["id"] for r in out["reports"]]
    assert "source_data_warnings" not in ids
    out2 = generate(tiny_tables(), datetime(2026, 9, 19, 12), ["core"])
    assert any(r["id"] == "source_data_warnings" for r in out2["reports"])


def test_password_args_no_longer_skip_profit():
    """Profit packs are permission-gated in the API; engine ignores password args."""
    tables = tiny_tables()
    out = generate(tables, datetime(2026, 9, 19, 12), ["core", "profit"], password="nope", password_hash="abc")
    statuses = {s["report"]: s["status"] for s in out["statuses"]}
    assert statuses.get("profit") != "SKIPPED"
    assert any(s["report"] == "Sales rep performance" and s["status"] == "SUCCESS" for s in out["statuses"])


def test_credit_note_nets_sales_not_collections():
    tables = tiny_tables()
    tables["credit_note"] = T(
        "credit_note",
        ["Date", "Party Name", "Invoice No", "Net Amount"],
        [[datetime(2026, 9, 1, 12), "Alpha", "CN-1", 180]],
    )
    out = generate(tables, datetime(2026, 9, 19, 12), ["core"])
    rep = next(r for r in out["reports"] if r["id"] == "sales_rep_performance_report")
    keys = by_key(rep)
    assert keys["Ravi"][9] == 1600
    assert keys["Ravi"][1] == 1000
    assert keys["Ravi"][2] == 100
    acc = next(r for r in out["reports"] if r["id"] == "account_performance_report")
    alpha = by_key(acc)["Alpha"]
    assert alpha[9] == 1600
    assert alpha[3] == 1000
    assert alpha[4] == 100


def test_amounts_round_to_two_decimals_and_totals_follow():
    tables = {
        "arr": T("arr", ["Account Name", "Group", "Balance", "Days"], [
            ["Alpha", "South", 0.004, 12],
            ["Beta", "North", 0.004, 0],
        ]),
        "sales": T("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [
            [datetime(2026, 9, 2, 12), "Alpha", "Ravi", 0.004],
            [datetime(2026, 9, 3, 12), "Beta", "Anu", 0.004],
            [datetime(2026, 5, 1, 12), "Alpha", "Ravi", 0.004],
            [datetime(2026, 6, 1, 12), "Alpha", "Ravi", 0.004],
        ]),
        "receipt": T("receipt", ["Date", "Account Name", "Sales Rep", "Amount"], []),
    }
    out = generate(tables, datetime(2026, 9, 19, 12), ["core", "fiscal"])
    rep = next(r for r in out["reports"] if r["id"] == "sales_rep_performance_report")
    keys = by_key(rep)
    assert keys["Ravi"][1] == 0
    assert keys["Anu"][1] == 0
    assert keys["TOTAL"][1] == 0
    fy = next(r for r in out["reports"] if r["id"] == "fiscal_monthly_sales_rep_performance_report")
    row = next(r for r in fy["rows"] if r[0] == "Ravi")
    may = row[1 + 1 * 2]
    june = row[1 + 2 * 2]
    fy_sales = row[1 + 24]
    assert may == 0
    assert june == 0
    assert fy_sales == 0
    assert fy["total"][1 + 24] == 0


def test_empty_password_hash_runs_profit():
    tables = tiny_tables()
    out = generate(tables, datetime(2026, 9, 19, 12), ["core", "profit"], password="", password_hash="")
    statuses = {s["report"]: s["status"] for s in out["statuses"]}
    assert statuses.get("profit") != "SKIPPED"


def test_one_failed_sheet_keeps_the_others(monkeypatch):
    from vay.reports import core as core_mod

    def boom(_ctx):
        raise RuntimeError("group broke")

    monkeypatch.setattr(core_mod, "group_performance", boom)
    out = generate(tiny_tables(), datetime(2026, 9, 19, 12), ["core"])
    titles = [r["title"] for r in out["reports"]]
    assert "Account performance" in titles
    assert "Group performance" not in titles
    failed = next(s for s in out["statuses"] if s["report"] == "Group performance")
    assert failed["status"] == "FAILED"
    assert "group broke" in failed["message"]
    assert any(s["report"] == "Account performance" and s["status"] == "SUCCESS" for s in out["statuses"])


def test_only_reports_runs_the_named_sheet():
    out = generate(
        tiny_tables(),
        datetime(2026, 9, 19, 12),
        ["core"],
        only_reports=["Sales rep performance"],
    )
    titles = [r["title"] for r in out["reports"]]
    assert titles == ["Sales rep performance"]


def test_merge_reports_keeps_sheets_that_were_not_rerun():
    from server.jobs import _merge_reports
    previous = [
        {"title": "Account performance", "rows": [[1]]},
        {"title": "Group performance", "rows": [[2]]},
    ]
    fresh = [{"title": "Group performance", "rows": [[9]]}]
    merged = _merge_reports(previous, fresh)
    assert merged[0]["rows"] == [[1]]
    assert merged[1]["rows"] == [[9]]


def test_ledger_preload_is_reused():
    from server.jobs import _ledger_store

    class Store:
        def __init__(self):
            self.calls = []

        def rows_of_type(self, name):
            self.calls.append(name)
            return [{"type": name}]

    store = Store()
    cached = _ledger_store(store, ["sales"])
    assert cached.rows_of_type("sales")[0]["type"] == "sales"
    assert cached.rows_of_type("sales")[0]["type"] == "sales"
    assert store.calls.count("sales") == 1

