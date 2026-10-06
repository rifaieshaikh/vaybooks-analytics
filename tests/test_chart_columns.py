from datetime import datetime

from vay.engine import generate
from vay.table import Table

from server.serialize import serialize_result


def T(name, headers, rows):
    return Table(name, headers, rows)


def test_sales_rep_has_15d_group_does_not():
    tables = {
        "arr": T("arr", ["Account Name", "Group", "Balance"], [["Acme", "South", 1]]),
        "sales": T("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [
            [datetime(2024, 9, 10, 12), "Acme", "R", 100],
        ]),
        "receipt": T("receipt", ["Date", "Account Name", "Sales Rep", "Amount"], [
            [datetime(2024, 9, 10, 12), "Acme", "R", 40],
        ]),
    }
    out = generate(tables, datetime(2024, 9, 19, 12), ["core"])
    snap = serialize_result(out)
    ids = {r["id"]: r["headers"] for r in snap["reports"]}
    assert "15 Days Sales" in ids["sales_rep_performance_report"]
    assert "15 Days Sales" not in ids["group_performance_report"]
    assert "MTD Sales" in ids["group_performance_report"]
    assert "YTD Sales" in ids["group_performance_report"]
    report_ids = {r["id"] for r in snap["reports"]}
    assert "monthly_profit_report" not in report_ids
    assert "expense_by_category" not in report_ids

    rep = next(r for r in snap["reports"] if r["id"] == "sales_rep_performance_report")
    mtd_i = rep["headers"].index("MTD Sales")
    body = [r for r in (rep["rows"] or []) if str(r[0]).lower() != "total"]
    chart_sum = sum(_num(r[mtd_i]) for r in body)
    if rep.get("total"):
        assert abs(chart_sum - _num(rep["total"][mtd_i])) < 1e-6


def _num(val):
    try:
        return float(str(val).replace(",", ""))
    except (TypeError, ValueError):
        return 0.0
