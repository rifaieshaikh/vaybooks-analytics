from datetime import datetime

from vay.dates import (
    add_days,
    add_months_clamped,
    build_report_context,
    fiscal_year_start,
    inclusive_tax,
    iter_fiscal_years,
    number_,
    parse_date,
    today_ist,
)
from vay.passwords import hash_password
from vay.preprocess import preprocess
from vay.reports.profit import (
    active_expense_categories,
    active_operating_categories,
    expense_by_category,
    payment_category,
    payment_summaries,
)
from vay.table import Table


def T(name, headers, rows):
    return Table(name, headers, [list(r) for r in rows])


def test_rolling_two_months_19_sep():
    d = parse_date("19-09-2026")
    start = add_days(add_months_clamped(d, -2), 1)
    assert start == datetime(2026, 7, 20, 12)


def test_add_months_clamped_31_mar():
    d = datetime(2026, 3, 31, 12)
    assert add_months_clamped(d, 1) == datetime(2026, 4, 30, 12)


def test_parse_dd_mm_yy():
    assert parse_date("19-09-24") == datetime(2024, 9, 19, 12)
    assert parse_date("19-09-2024") == datetime(2024, 9, 19, 12)
    assert parse_date("2024-09-19") == datetime(2024, 9, 19, 12)


def test_round2_half_up():
    from vay.dates import round2
    assert round2(1.004) == 1.00
    assert round2(1.005) == 1.01
    assert round2(2.675) == 2.68
    assert round2(-1.005) == -1.01
    assert round2("") == ""


def test_number_commas():
    assert number_("1,234.50") == 1234.50


def test_jan_min_date_fy():
    years = iter_fiscal_years(datetime(2023, 1, 15, 12), datetime(2026, 9, 19, 12))
    assert years[0] == datetime(2022, 4, 1, 12)
    assert years[-1] == datetime(2026, 4, 1, 12)


def test_empty_dated_sources_one_fy():
    years = iter_fiscal_years(None, datetime(2026, 9, 19, 12))
    assert years == [datetime(2026, 4, 1, 12)]


def test_inclusive_tax():
    assert abs(inclusive_tax(118) - 18) < 1e-9


def test_today_ist_has_noon():
    t = today_ist()
    assert t.hour == 12


def test_password_bcrypt_roundtrip():
    from vay.passwords import hash_password, password_ok

    digest = hash_password("x")
    assert digest.startswith("$2")
    assert password_ok("x", digest)
    assert not password_ok("y", digest)


def test_carriage_inward_is_office():
    from vay.packs.vay_wholesale import EXPENSE_ACCOUNT_MAP

    assert payment_category("Carriage inward", EXPENSE_ACCOUNT_MAP) == "Office Expenses"
    assert payment_category("AMAL_TRADERS", EXPENSE_ACCOUNT_MAP) == "Office Expenses"


def test_payment_fallback_unmapped_salary():
    assert payment_category("SOMEONE SALARY") == "Salary"


def test_active_expense_categories_includes_custom():
    cats = active_expense_categories({
        "Office Expenses": ["X"],
        "Custom Marketing": ["AD_SPEND"],
    })
    assert "Office Expenses" in cats
    assert "Custom Marketing" in cats
    assert "Other" in cats
    assert "Custom Marketing" in active_operating_categories(cats)
    assert "Purchase" not in active_operating_categories(cats)


def test_payment_summaries_custom_category():
    report = datetime(2026, 9, 19, 12)
    ctx = build_report_context(report)
    ctx["fiscalYears"] = [datetime(2026, 4, 1, 12)]
    ctx["inventory"] = {}
    ctx["payment_categories"] = {
        "Office Expenses": [],
        "Custom Marketing": ["AD_SPEND_ACCOUNT"],
    }
    tables = {
        "sales": T("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], []),
        "items": T("items", ["Date", "Item Name", "Qty", "Rate"], []),
        "payments": T(
            "payments",
            ["Date", "Account Name", "Amount"],
            [[report, "AD_SPEND_ACCOUNT", 250]],
        ),
    }
    data = payment_summaries(tables, ctx, include_cogs=False)
    assert "Custom Marketing" in data["categories"]
    assert "Custom Marketing" in data["byCategory"]
    assert abs(data["byCategory"]["Custom Marketing"]["mtd"] - 250) < 1e-9
    report_rows = expense_by_category(data)["rows"]
    labels = [r[0] for r in report_rows]
    assert "Custom Marketing" in labels
    custom = next(r for r in report_rows if r[0] == "Custom Marketing")
    assert abs(custom[1] - 250) < 1e-9


def test_no_party_name_inserted():
    tables = {
        "arr": T("arr", ["Account Name", "Group", "Balance"], [["Alpha", "South", 1]]),
        "sales": T("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], []),
        "receipt": T("receipt", ["Date", "Account Name", "Sales Rep", "Amount"], []),
        "items": T("items", ["Date", "Item Name", "Qty", "Rate"], []),
    }
    preprocess(tables)
    names = [r[0] for r in tables["arr"].rows]
    assert "NO_PARTY_NAME" in names


def test_fy_start_april():
    assert fiscal_year_start(datetime(2026, 9, 19, 12)) == datetime(2026, 4, 1, 12)
    assert fiscal_year_start(datetime(2026, 3, 1, 12)) == datetime(2025, 4, 1, 12)


def test_fy_start_january():
    assert fiscal_year_start(datetime(2026, 9, 19, 12), 1) == datetime(2026, 1, 1, 12)
    assert fiscal_year_start(datetime(2026, 1, 1, 12), 1) == datetime(2026, 1, 1, 12)
    years = iter_fiscal_years(datetime(2024, 6, 1, 12), datetime(2026, 3, 1, 12), start_month=1)
    assert years[0] == datetime(2024, 1, 1, 12)
    assert years[-1] == datetime(2026, 1, 1, 12)


def test_context_windows():
    ctx = build_report_context(datetime(2026, 9, 19, 12))
    assert ctx["last2MonthsStart"] == datetime(2026, 7, 20, 12)
    assert ctx["last15Start"] == datetime(2026, 9, 5, 12)
    assert ctx["fiscalYearStart"] == datetime(2026, 4, 1, 12)
    assert ctx["fiscalYearStartMonth"] == 4
    assert ctx["sales_tax_inclusive_rate"] == 0.18


def test_context_org_policy_override():
    ctx = build_report_context(
        datetime(2026, 9, 19, 12),
        org_policy={"fiscal_year_start_month": 1, "sales_tax_inclusive_rate": 0.05, "timezone": "Asia/Kolkata"},
    )
    assert ctx["fiscalYearStart"] == datetime(2026, 1, 1, 12)
    assert ctx["fiscalYearStartMonth"] == 1
    assert ctx["sales_tax_inclusive_rate"] == 0.05
