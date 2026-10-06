"""Phase 2: period comparison, sales change, collection grain, stock as-of."""

import os
from datetime import datetime

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient

from server.main import app
from server.phase2 import build_bundle
from server.store import get_store, reset_store_for_tests
from server.business360 import qty_levels
from server.customers import attach_fy_qty
from server.item_dims import _empty_slot, _finish
from vay.phase2 import _collection_invoice_text, collection_worklist, compare_measures, sales_change, scorecard


def client():
    reset_store_for_tests()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    return c


def _when(text):
    return datetime.strptime(text, "%Y-%m-%d").replace(hour=12)


def test_scorecard_prior_period_is_not_zero_when_missing_and_compares_when_present():
    sales = [(_when("2026-10-02"), 100.0), (_when("2026-09-02"), 40.0)]
    card = scorecard(sales, [], {}, {}, "2026-10-03")
    by_id = {row["id"]: row for row in card["rows"]}
    assert by_id["sales_mtd"]["current"]["value"] == 100.0
    assert by_id["sales_mtd"]["prior"]["value"] == 40.0
    assert by_id["sales_mtd"]["prior_year"]["value"] is None
    assert by_id["sales_mtd"]["target"]["reason"] == "No target"


def test_sales_change_ranks_customer_and_withholds_bridge_without_rates():
    change = sales_change(
        [
            {"name": "Acme", "current": 80, "prior": 20},
            {"name": "Beta", "current": 10, "prior": 50},
        ],
        [{"name": "Widget", "qty_current": None, "rate_current": None, "qty_prior": 1, "rate_prior": 5}],
    )
    assert change["customers"][0]["name"] == "Acme"
    assert change["customers"][0]["change"] == 60
    assert change["bridge"]["status"] == "unavailable"
    assert change["customers"]
    assert change["products"][0]["qty_prior"] == 1
    assert change["products"][0]["qty_current"] is None
    assert change["products"][0]["qty_change"] is None
    assert change["summary"]["qty"]["status"] == "eligible"
    assert change["summary"]["amount"]["change"] == 20
    assert change["summary"]["verdict"] == "Quantity cannot be compared with the prior period. Amount is up."


def test_compare_measures_says_when_both_improved_and_when_they_split():
    both = compare_measures(1240, 1100, 480000, 420000)
    assert both["qty"]["change"] == 140
    assert both["amount"]["change"] == 60000
    assert both["verdict"] == "Sales improved on quantity and amount."
    split = compare_measures(10, 4, 20, 40)
    assert split["verdict"] == "Quantity is up and amount is down."
    declined = compare_measures(1, 4, 10, 40)
    assert declined["verdict"] == "Sales declined on quantity and amount."


def test_compare_measures_withholds_quantity_and_a_missing_prior():
    missing_qty = compare_measures(None, None, 80, 50, qty_available=False)
    assert missing_qty["qty"]["status"] == "unavailable"
    assert missing_qty["qty"]["reason"] == "Quantity needs item lines in these periods"
    assert missing_qty["verdict"] == "Amount is up."
    missing_prior = compare_measures(5, None, None, None)
    assert missing_prior["amount"]["change"] is None
    assert missing_prior["qty"]["change"] is None
    assert missing_prior["verdict"] == "Sales cannot be compared with the prior period."


def test_sales_change_keeps_product_quantity_beside_amount():
    change = sales_change(
        [{"name": "Acme", "current": 80, "prior": 20}],
        [{"name": "Widget", "qty_current": 8, "rate_current": 10, "qty_prior": 5, "rate_prior": 8}],
    )
    row = change["products"][0]
    assert row["qty_current"] == 8
    assert row["qty_prior"] == 5
    assert row["qty_change"] == 3
    assert row["current"] == 80
    assert row["prior"] == 40
    assert row["change"] == 40
    assert change["summary"]["verdict"] == "Sales improved on quantity and amount."


def test_quantity_uses_the_same_windows_as_amount_and_skips_a_compare():
    lines = [
        {"date": _when("2026-10-02"), "qty": 4},
        {"date": _when("2026-09-02"), "qty": 2},
        {"date": _when("2026-02-02"), "qty": 5},
        {"date": _when("2025-06-02"), "qty": 3},
    ]
    levels = qty_levels(lines, _when("2026-10-06"), 1)
    assert levels["available"] is True
    assert levels["month"] == 4
    assert levels["fy"] == 11
    assert levels["overall"] == 14
    missing = qty_levels([], _when("2026-10-06"), 1)
    assert missing["available"] is False
    assert missing["month"] is None
    assert missing["fy"] is None
    assert missing["overall"] is None

    years = [
        {"start": "2026-01-01", "label": "2026", "sales": 330},
        {"start": "2025-01-01", "label": "2025", "sales": 50},
    ]
    attach_fy_qty(years, lines, True)
    assert years[0]["qty"] == 11
    assert years[0]["sales"] == 330
    assert years[1]["qty"] == 3
    bare = [
        {"start": "2026-01-01", "sales": 90},
        {"start": "2025-01-01", "sales": 50},
    ]
    attach_fy_qty(bare, [], False)
    assert bare[0]["qty"] is None
    assert bare[1]["qty"] is None

    slot = _empty_slot("widget", "Widget")
    done = _finish(slot)
    assert "sales_compare" not in done
    assert "qty_change" not in done
    assert "amount_change" not in done
    assert done["overall"]["qty"] == 0
    assert done["fy_years"] == []


def test_collection_worklist_estimates_when_receipts_omit_invoice_numbers():
    rows = collection_worklist([{
        "name": "Acme",
        "balance": 80,
        "overdue30": 80,
        "as_of": _when("2026-10-03"),
        "invoices": [
            {"date": _when("2026-08-01"), "amount": 60, "invoice": "A"},
            {"date": _when("2026-09-01"), "amount": 40, "invoice": "B"},
        ],
        "receipts": [{"date": _when("2026-09-15"), "amount": 60, "invoice": ""}],
    }])["rows"]
    assert rows[0]["invoice_detail"] == "estimated"
    by_no = {line["invoice"]: line for line in rows[0]["invoices"]}
    assert by_no["A"]["remaining"] == 0
    assert by_no["B"]["remaining"] == 40
    assert by_no["A"]["basis"] == "estimated"


def test_collection_worklist_keeps_named_receipts_and_estimates_the_rest():
    rows = collection_worklist([{
        "name": "Acme",
        "balance": 40,
        "overdue30": 40,
        "as_of": _when("2026-10-03"),
        "invoices": [
            {"date": _when("2026-08-01"), "amount": 60, "invoice": "A"},
            {"date": _when("2026-09-01"), "amount": 40, "invoice": "B"},
        ],
        "receipts": [
            {"date": _when("2026-09-10"), "amount": 60, "invoice": "A"},
            {"date": _when("2026-09-20"), "amount": 20, "invoice": ""},
        ],
    }])["rows"]
    assert rows[0]["invoice_detail"] == "estimated"
    by_no = {line["invoice"]: line for line in rows[0]["invoices"]}
    assert by_no["A"]["remaining"] == 0
    assert by_no["A"]["basis"] == "named"
    assert by_no["B"]["allocated"] == 20
    assert by_no["B"]["remaining"] == 20
    assert by_no["B"]["basis"] == "estimated"
    text = _collection_invoice_text(rows[0])
    assert "A remaining 0.0" in text
    assert "B remaining 20.0 (estimated)" in text
    assert "A remaining 0.0 (estimated)" not in text


def test_collection_worklist_stays_at_customer_without_invoice_allocation():
    rows = collection_worklist([{
        "name": "Acme",
        "balance": 100,
        "overdue30": 80,
        "overdue15": 80,
        "invoices": [{"date": _when("2026-08-01"), "amount": 100, "invoice": ""}],
        "receipts": [{"date": _when("2026-09-01"), "amount": 20, "invoice": ""}],
    }])["rows"]
    assert rows[0]["name"] == "Acme"
    assert rows[0]["status"] == "URGENT"
    assert rows[0]["invoice_detail"] == "unavailable"
    assert rows[0]["invoices"] == []


def test_stock_cover_withheld_when_snapshot_date_differs():
    c = client()
    store = get_store()
    uid = store.insert_upload({"type": "stock", "effective_date": "2026-09-01", "dry_run": False})
    store.upsert_row({
        "type": "stock",
        "uk": "widget",
        "source_upload_id": uid,
        "fields": {"Item Name": "Widget", "Qty": 10, "P.Price": 5, "EffectiveDate": "2026-09-01"},
    })
    store.upsert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {"Date": "2026-09-02", "Party Name": "Acme", "Sales Rep": "Rep", "Net Amount": 100},
    })
    store.upsert_row({
        "type": "receipt",
        "uk": "r1",
        "fields": {"Date": "2026-09-02", "Account Name": "Acme", "Sales Rep": "Rep", "Amount": 10},
    })
    store.upsert_row({
        "type": "arr",
        "uk": "acme",
        "fields": {"Account Name": "Acme", "Group": "South", "Balance": 90},
    })
    run = store.insert_run({"status": "succeeded", "report_date": "2026-09-19", "manifest": {}})
    payload = c.get("/api/analytics?run=%s" % run["_id"])
    assert payload.status_code == 200, payload.text
    body = payload.json()
    stock = body["stock"]
    assert stock["status"] == "unavailable"
    assert stock["rows"] == []
    assert stock["cover_days"] is None


def test_saved_view_is_per_user():
    c = client()
    saved = c.put("/api/analytics/views", json={"page": "scorecard", "filters": {"query": "Acme"}})
    assert saved.status_code == 200
    again = c.get("/api/analytics/views").json()["views"]["scorecard"]["query"]
    assert again == "Acme"


def test_bundle_explains_a_sales_increase():
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "now",
        "fields": {"Date": "2026-10-02", "Party Name": "Acme", "Sales Rep": "Rep", "Net Amount": 80, "Invoice No": "1"},
    })
    store.upsert_row({
        "type": "sales",
        "uk": "then",
        "fields": {"Date": "2026-09-02", "Party Name": "Acme", "Sales Rep": "Rep", "Net Amount": 20, "Invoice No": "0"},
    })
    store.upsert_row({
        "type": "receipt",
        "uk": "r",
        "fields": {"Date": "2026-10-02", "Account Name": "Acme", "Sales Rep": "Rep", "Amount": 0},
    })
    store.upsert_row({
        "type": "arr",
        "uk": "a",
        "fields": {"Account Name": "Acme", "Group": "South", "Balance": 0},
    })
    bundle = build_bundle(store, "2026-10-03")
    customers = bundle["sales_change"]["customers"]
    assert customers[0]["name"] == "Acme"
    assert customers[0]["change"] == 60
    assert bundle["scorecard"]["rows"][0]["current"]["value"] == 80
    assert bundle["scorecard"]["rows"][0]["prior"]["value"] == 20
