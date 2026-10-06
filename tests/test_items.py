from datetime import datetime

from vay.engine import generate
from vay.table import Table


def T(name, headers, rows):
    return Table(name, headers, [list(r) for r in rows])


def test_item_name_case_sensitive_vs_stock():
    tables = {
        "items": T("items", ["Date", "Item Name", "Qty", "Rate"], [
            [datetime(2026, 9, 1, 12), "Bolt", 2, 10],
        ]),
        "stock": T("stock", ["Item Name", "Qty", "P.Price"], [
            ["bolt", 5, 3],
        ]),
        "sales": T("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], []),
        "receipt": T("receipt", ["Date", "Account Name", "Sales Rep", "Amount"], []),
        "arr": T("arr", ["Account Name", "Group", "Balance"], []),
        "payments": T("payments", ["Date", "Account Name", "Amount"], []),
    }
    out = generate(tables, datetime(2026, 9, 19, 12), ["items"])
    exc = next(r for r in out["reports"] if r["id"] == "item_cost_exceptions")
    assert any(r[0] == "Bolt" for r in exc["rows"])


def test_old_sku_appears_on_monthly_qty():
    tables = {
        "items": T("items", ["Date", "Item Name", "Qty", "Rate"], [
            [datetime(2023, 5, 1, 12), "OldSku", 1, 10],
            [datetime(2026, 9, 1, 12), "NewSku", 1, 10],
        ]),
        "stock": T("stock", ["Item Name", "Qty", "P.Price"], [
            ["OldSku", 0, 1],
            ["NewSku", 10, 1],
        ]),
        "sales": T("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], []),
        "receipt": T("receipt", ["Date", "Account Name", "Sales Rep", "Amount"], []),
        "arr": T("arr", ["Account Name", "Group", "Balance"], []),
        "payments": T("payments", ["Date", "Account Name", "Amount"], []),
    }
    out = generate(tables, datetime(2026, 9, 19, 12), ["items"])
    qty = next(r for r in out["reports"] if r["id"] == "item_wise_monthly_qty")
    names = [r[0] for r in qty["rows"]]
    assert "OldSku" in names
    old = next(r for r in qty["rows"] if r[0] == "OldSku")
    assert old[-1] == "OK"


def test_weighted_price_and_missing_cogs():
    from vay.reports.items import stock_map
    tables = {
        "stock": T("stock", ["Item Name", "Qty", "P.Price"], [
            ["A", 2, 10],
            ["A", 2, 20],
            ["B", 1, ""],
        ]),
    }
    mapping = stock_map(tables)
    assert mapping["A"]["cost"] == 15
    assert mapping["B"]["cost"] is None
