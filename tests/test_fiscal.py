from datetime import datetime

from vay.engine import generate
from vay.export_excel import excel_sheet_name
from vay.reports.fiscal import current_fy_pair_slice
from vay.table import Table


def T(name, headers, rows):
    return Table(name, headers, [list(r) for r in rows])


def test_excel_followup_suffix_fits():
    used = set()
    long_group = "X" * 40
    a = excel_sheet_name("sales_follow_up_" + long_group, used)
    b = excel_sheet_name("sales_follow_up_" + long_group, used)
    assert len(a) <= 31
    assert len(b) <= 31
    assert a != b
    assert b.endswith("_2") or "_2" in b


def test_contiguous_empty_fy_has_columns():
    tables = {
        "arr": T("arr", ["Account Name", "Group", "Balance"], [["A", "G", 0]]),
        "sales": T("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [
            [datetime(2023, 5, 1, 12), "A", "R", 10],
            [datetime(2026, 5, 1, 12), "A", "R", 20],
        ]),
        "receipt": T("receipt", ["Date", "Account Name", "Sales Rep", "Amount"], []),
    }
    out = generate(tables, datetime(2026, 9, 19, 12), ["fiscal"])
    fy = next(r for r in out["reports"] if r["id"] == "fiscal_monthly_sales_rep_performance_report")
    n = len(out["ctx"]["fiscalYears"])
    assert n == 4  # 2023-24 through 2026-27
    # 1 label + 4*(24+2) + 2 all-FY
    assert len(fy["headers"]) == 1 + n * 26 + 2


def test_jan_2024_not_jan_2025():
    tables = {
        "arr": T("arr", ["Account Name", "Group", "Balance"], [["A", "G", 0]]),
        "sales": T("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [
            [datetime(2024, 1, 10, 12), "A", "R", 5],
            [datetime(2025, 1, 10, 12), "A", "R", 7],
        ]),
        "receipt": T("receipt", ["Date", "Account Name", "Sales Rep", "Amount"], []),
    }
    out = generate(tables, datetime(2026, 9, 19, 12), ["fiscal"])
    fy = next(r for r in out["reports"] if r["id"] == "fiscal_monthly_sales_rep_performance_report")
    row = fy["rows"][0]
    n = len(out["ctx"]["fiscalYears"])
    # FY 2023-24 starts Apr 2023: Jan 2024 is month index 9 of that FY
    years = out["ctx"]["fiscalYears"]
    i_2023 = years.index(datetime(2023, 4, 1, 12))
    i_2024 = years.index(datetime(2024, 4, 1, 12))
    jan = 9  # fiscal month index for January
    v_2023 = row[1 + i_2023 * 26 + jan * 2]
    v_2024 = row[1 + i_2024 * 26 + jan * 2]
    assert v_2023 == 5
    assert v_2024 == 7


def test_current_fy_slice_helper_width():
    row = ["R"] + [0] * 26 + [0] * 26 + [1, 2]
    sliced = current_fy_pair_slice(row, 1, 2)
    assert len(sliced) == 27
