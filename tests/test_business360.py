from vay.reports.profit import _wide_line

from server.business360 import company_settlements, profit_periods, visible_business


def _headers(n, report_mi):
    headers = ["Component"]
    for yi in range(n):
        for mi in range(12):
            stamp = "M%d" % mi
            if yi == n - 1 and mi > report_mi:
                stamp += " [after report date]"
            headers.append(stamp)
        headers.append("Total")
    headers.append("Total")
    return headers


def _report():
    sale = [[10.0] * 12, [20.0, 30.0] + [0.0] * 10]
    cogs = [[4.0] * 12, [5.0, 6.0] + [0.0] * 10]
    salary = [[1.0] * 12, [2.0, 3.0] + [0.0] * 10]
    profit = [
        [sale[y][i] - cogs[y][i] - salary[y][i] for i in range(12)]
        for y in range(2)
    ]
    rows = [
        _wide_line("Sale before tax", sale, 1, 2),
        _wide_line("Less: Cost of items sold", cogs, 1, 2),
        _wide_line("Less: Salary", salary, 1, 2),
        _wide_line("Sales profit", profit, 1, 2),
    ]
    return {
        "id": "monthly_profit_report",
        "wide": "month",
        "label_cols": 1,
        "n_fy": 2,
        "headers": _headers(2, 1),
        "rows": rows,
    }


def _value(period, field):
    return period[field]["value"]


def test_profit_periods_and_unavailable():
    report = _report()
    got = profit_periods(report, margin_status="eligible", payments_present=True)

    assert _value(got["overall"], "gross_profit") == 111
    assert _value(got["overall"], "operating_expenses") == 17
    assert _value(got["overall"], "ebitda") == 94
    assert got["overall"]["sales_profit"] == 94

    assert got["fy"]["sale_before_tax"] == 50
    assert _value(got["fy"], "gross_profit") == 39
    assert _value(got["fy"], "operating_expenses") == 5
    assert _value(got["fy"], "ebitda") == 34
    assert got["fy"]["sales_profit"] == 34
    assert got["fy"]["prior"]["sales_profit"] == 60
    assert _value(got["fy"]["prior"], "ebitda") == 60

    assert got["month"]["sale_before_tax"] == 30
    assert _value(got["month"], "gross_profit") == 24
    assert _value(got["month"], "operating_expenses") == 3
    assert _value(got["month"], "ebitda") == 21
    assert got["month"]["sales_profit"] == 21
    assert got["month"]["prior"]["sale_before_tax"] == 20
    assert _value(got["month"]["prior"], "ebitda") == 13

    blocked = profit_periods(report, margin_status="unavailable", margin_reason="Missing item cost", payments_present=True)
    assert blocked["overall"]["gross_profit"]["unavailable"] is True
    assert blocked["overall"]["gross_profit"]["value"] is None
    assert blocked["overall"]["gross_profit"]["reason"] == "Missing item cost"
    assert blocked["fy"]["ebitda"]["unavailable"] is True
    assert blocked["month"]["gross_margin_pct"]["unavailable"] is True
    assert blocked["overall"]["operating_expenses"]["value"] == 17
    assert blocked["overall"]["sales_profit"] == 94

    no_pay = profit_periods(report, margin_status="eligible", payments_present=False)
    assert no_pay["overall"]["gross_profit"]["value"] == 111
    assert no_pay["overall"]["operating_expenses"]["unavailable"] is True
    assert no_pay["month"]["ebitda"]["unavailable"] is True
    assert no_pay["fy"]["sales_profit"] == 34


def test_visible_business_strips_sections():
    doc = {
        "empty": False,
        "name": "Business",
        "periods": {
            "month": {
                "sales": {"value": 10, "prior": None, "prior_year": None, "target": None},
                "profit": {"ebitda": {"value": 4, "unavailable": False, "reason": ""}, "sales_profit": 4},
            },
        },
        "receivables": {"urgent": 2},
        "stock": {"low_count": 1},
        "mix": {"groups": [{"name": "A"}], "expenses": [{"name": "Salary"}], "buy": [{"name": "Item"}]},
        "movement": {"customers": [{"name": "C"}], "products": [{"name": "P"}], "counts": {"new": 1}},
        "exceptions": [
            {"id": "urgent", "section": "customers", "label": "Urgent customers", "value": 2},
            {"id": "low_stock", "section": "stock", "label": "Items below minimum", "value": 1},
            {"id": "unmapped", "section": "profit", "label": "Unmapped payments", "value": 3},
        ],
        "cost_note": "cost",
        "settlements": {"overall": {"total": 80, "buckets": {}, "credit": 0}},
        "sales_gaps": {"overall": {"orders": 3, "value": 12}},
    }
    sales_only = visible_business(doc, ["sales.view"])
    assert sales_only["periods"]["month"]["sales"]["value"] == 10
    assert "profit" not in sales_only["periods"]["month"]
    assert "receivables" not in sales_only
    assert "settlements" not in sales_only
    assert sales_only["sales_gaps"]["overall"]["orders"] == 3
    assert sales_only["movement"]["products"][0]["name"] == "P"
    assert sales_only["exceptions"] == []

    profit_only = visible_business(doc, ["reports.view.profit"])
    assert profit_only["periods"]["month"]["profit"]["sales_profit"] == 4
    assert "sales" not in profit_only["periods"]["month"]
    assert profit_only["mix"]["expenses"][0]["name"] == "Salary"
    assert profit_only["exceptions"][0]["id"] == "unmapped"
    assert "settlements" not in profit_only
    assert "sales_gaps" not in profit_only

    customers = visible_business(doc, ["customer.view"])
    assert customers["settlements"]["overall"]["total"] == 80


def test_company_settlements_sums_customers():
    bands = [
        {"key": "d0_15", "label": "0–15", "max_days": 15},
        {"key": "d90", "label": "90+", "max_days": None},
    ]
    customers = {
        "a": {
            "aging_bands": bands,
            "settlements": {
                "overall": {"total": 100, "credit": 5, "buckets": {"d0_15": 40, "d90": 60}},
                "by_fy": [{"key": "2025-04-01", "label": "FY 2025-26", "total": 100, "buckets": {"d0_15": 40, "d90": 60}}],
                "months": [{"key": "2026-01", "year": 2026, "month": 1, "label": "Jan 2026", "total": 100, "buckets": {"d0_15": 40, "d90": 60}}],
                "default_month": "2026-01",
            },
        },
        "b": {
            "settlements": {
                "overall": {"total": 50, "credit": 0, "buckets": {"d0_15": 50, "d90": 0}},
                "by_fy": [{"key": "2025-04-01", "label": "FY 2025-26", "total": 50, "buckets": {"d0_15": 50}}],
                "months": [{"key": "2026-02", "year": 2026, "month": 2, "label": "Feb 2026", "total": 50, "buckets": {"d0_15": 50}}],
                "default_month": "2026-02",
            },
        },
    }
    got = company_settlements(customers)
    assert got["overall"]["total"] == 150
    assert got["overall"]["credit"] == 5
    assert got["overall"]["buckets"]["d0_15"] == 90
    assert got["overall"]["buckets"]["d90"] == 60
    assert got["by_fy"][0]["total"] == 150
    assert [row["key"] for row in got["months"]] == ["2026-02", "2026-01"]
    assert got["default_month"] == "2026-02"
    assert got["months"][0]["total"] == 50
    assert got["months"][1]["total"] == 100


def test_settlement_lines_follow_the_receipt():
    from datetime import datetime

    from server.customers import build_settlements_summary

    bands = [
        {"key": "d0_15", "label": "0–15", "max_days": 15},
        {"key": "d15_30", "label": "15–30", "max_days": 30},
        {"key": "d90", "label": "90+", "max_days": None},
    ]
    allocs = [{
        "amount": 40,
        "age_days": 15,
        "kind": "sale",
        "invoice": "INV-1",
        "invoice_id": "id1",
        "receipt_date": datetime(2026, 1, 20, 12),
        "target_date": datetime(2026, 1, 5, 12),
        "party": "Acme",
        "customer_uk": "acme",
    }]
    summary = build_settlements_summary(allocs, datetime(2026, 1, 31, 12), bands=bands, start_month=4)
    january = next(row for row in summary["months"] if row["key"] == "2026-01")
    for period in (summary["overall"], summary["by_fy"][0], january):
        assert period["lines"][0]["invoice"] == "INV-1"
        assert period["lines"][0]["bucket"] == "d0_15"
        assert period["lines"][0]["party"] == "Acme"
        assert period["buckets"]["d0_15"] == 40


def test_company_settlements_keeps_invoice_lines():
    line_a = {
        "date_iso": "2026-01-20",
        "invoice": "A-1",
        "amount": 40,
        "bucket": "d0_15",
        "party": "",
        "customer_uk": "",
    }
    line_b = {
        "date_iso": "2026-02-02",
        "invoice": "B-1",
        "amount": 50,
        "bucket": "d0_15",
        "party": "Beta",
        "customer_uk": "beta",
    }
    customers = {
        "a": {
            "uk": "alpha",
            "name": "Alpha",
            "settlements": {
                "overall": {"total": 40, "credit": 0, "buckets": {"d0_15": 40}, "lines": [line_a]},
                "by_fy": [{"key": "2025-04-01", "label": "FY 2025-26", "total": 40, "buckets": {"d0_15": 40}, "lines": [line_a]}],
                "months": [{"key": "2026-01", "year": 2026, "month": 1, "label": "Jan 2026", "total": 40, "buckets": {"d0_15": 40}, "lines": [line_a]}],
            },
        },
        "b": {
            "uk": "beta",
            "name": "Beta",
            "settlements": {
                "overall": {"total": 50, "credit": 0, "buckets": {"d0_15": 50}, "lines": [line_b]},
                "by_fy": [{"key": "2025-04-01", "label": "FY 2025-26", "total": 50, "buckets": {"d0_15": 50}, "lines": [line_b]}],
                "months": [{"key": "2026-02", "year": 2026, "month": 2, "label": "Feb 2026", "total": 50, "buckets": {"d0_15": 50}, "lines": [line_b]}],
            },
        },
    }
    got = company_settlements(customers)
    assert got["overall"]["total"] == 90
    parties = {line["party"] for line in got["overall"]["lines"]}
    assert parties == {"Alpha", "Beta"}
    assert {line["invoice"] for line in got["by_fy"][0]["lines"]} == {"A-1", "B-1"}
    january = next(row for row in got["months"] if row["key"] == "2026-01")
    assert january["lines"][0]["invoice"] == "A-1"
    assert january["lines"][0]["party"] == "Alpha"


def test_due_band_boundaries():
    from vay.settlement import bucket_key

    bands = [
        {"key": "d0_15", "label": "0–15", "max_days": 15},
        {"key": "d15_30", "label": "15–30", "max_days": 30},
        {"key": "d90", "label": "90+", "max_days": None},
    ]
    assert bucket_key(15, bands) == "d0_15"
    assert bucket_key(16, bands) == "d15_30"
    assert bucket_key(31, bands) == "d90"
