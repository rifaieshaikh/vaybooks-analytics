"""Later planning: position, demand, dated cost, and cash stay blank when inputs are missing."""

import calendar
import os
from datetime import timedelta

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient

from server.items360 import save_holding
from server.main import app
from server.store import get_store, reset_store_for_tests
from vay.dates import today_ist
from vay.phase2 import gross_margin_periods


def client():
    reset_store_for_tests()
    c = TestClient(app)
    logged = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert logged.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    return c


def _stock(store, name, qty, price=4, effective=""):
    fields = {"Item Name": name, "Qty": qty, "P.Price": price}
    if effective:
        fields["EffectiveDate"] = effective
    store.upsert_row({"type": "stock", "uk": name, "fields": fields})


def _day(offset):
    return (today_ist() + timedelta(days=offset)).strftime("%Y-%m-%d")


def test_buy_qty_uses_incoming_only_when_it_arrives_on_time():
    c = client()
    store = get_store()
    _stock(store, "Widget", 30)
    save_holding(store, "Widget", min_hold=10, fill_to=50, lead_days=5)
    plain = c.get("/api/items/Widget")
    assert plain.status_code == 200, plain.text
    assert plain.json()["buy_qty"] == 20
    assert plain.json()["position"] is None

    store.upsert_row({
        "type": "incoming",
        "uk": "late",
        "fields": {"Item Name": "Widget", "Qty": 15, "Expected Date": _day(30), "Confirmed": "Yes"},
    })
    late = c.get("/api/items/Widget")
    assert late.status_code == 200, late.text
    assert late.json()["buy_qty"] == 20
    assert late.json()["incoming_late"] == 15
    assert late.json()["incoming_on_time"] == 0
    assert late.json()["position"] == 30

    store.upsert_row({
        "type": "incoming",
        "uk": "soon",
        "fields": {"Item Name": "Widget", "Qty": 15, "Expected Date": _day(1), "Confirmed": "Yes"},
    })
    timed = c.get("/api/items/Widget")
    assert timed.status_code == 200, timed.text
    assert timed.json()["incoming_on_time"] == 15
    assert timed.json()["position"] == 45
    assert timed.json()["buy_qty"] == 5


def test_review_days_use_last_year_and_leave_the_current_buy_unchanged_by_the_past_check():
    c = client()
    store = get_store()
    today = today_ist()
    days = calendar.monthrange(today.year - 1, today.month)[1]
    _stock(store, "Widget", 10, effective="%04d-%02d-01" % (today.year - 1, today.month))
    store.upsert_row({
        "type": "items",
        "uk": "old",
        "fields": {
            "Date": "%04d-%02d-15" % (today.year - 1, today.month),
            "Item Name": "Widget",
            "Qty": days,
            "Rate": 10,
        },
    })
    store.upsert_row({
        "type": "incoming",
        "uk": "soon",
        "fields": {"Item Name": "Widget", "Qty": 5, "Expected Date": _day(1), "Confirmed": "Yes"},
    })
    save_holding(store, "Widget", min_hold=0, fill_to=50, lead_days=5, review_days=7, safety_stock=20)
    item = c.get("/api/items/Widget")
    assert item.status_code == 200, item.text
    body = item.json()
    assert body["demand_label"] == "Same month last year"
    assert body["position"] == 15
    assert body["demand_target"] == 32
    assert body["buy_qty"] == 17
    assert body["past_check"]["buy_qty"] is not None
    assert body["buy_qty"] == 17


def test_margin_uses_the_cost_dated_on_or_before_the_sale():
    from datetime import datetime
    items = [{"name": "Widget", "date": datetime(2026, 10, 1, 12), "qty": 2, "rate": 10}]
    costs = {"Widget": {"snapshot": 9, "history": [
        {"date": "2026-09-01", "cost": 4},
        {"date": "2026-10-15", "cost": 9},
    ]}}
    margin = gross_margin_periods(items, costs, "2026-10-07", 0)
    assert margin["current"] == 60.0
    assert margin["cost_label"] == "Historical cost"
    missing = gross_margin_periods(
        items, {"Widget": {"snapshot": None, "history": []}}, "2026-10-07", 0,
    )
    assert missing["current"] is None


def test_cash_leaves_a_missing_opening_blank_and_counts_a_receipt_once():
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "receipt",
        "uk": "paid",
        "fields": {"Date": _day(0), "Account Name": "Harbor", "Amount": 40},
    })
    promised = c.post("/api/collection/promises", json={
        "customer_name": "Harbor",
        "amount": 100,
        "promised_on": _day(1),
    })
    assert promised.status_code == 200, promised.text
    applied = c.post("/api/collection/allocations", json={
        "promise_id": promised.json()["id"],
        "source_uk": "paid",
        "source_type": "receipt",
        "amount": 40,
    })
    assert applied.status_code == 200, applied.text
    quiet = c.post("/api/collection/promises", json={
        "customer_name": "Quiet",
        "amount": 25,
        "promised_on": _day(-3),
    })
    assert quiet.status_code == 200, quiet.text
    cash = c.get("/api/cash")
    assert cash.status_code == 200, cash.text
    body = cash.json()
    assert body["opening"] is None
    assert "not in the file" in body["opening_label"].lower()
    assert all(week["opening"] is None for week in body["weeks"])
    assert all(week["net"] is None for week in body["weeks"])
    assert round(sum(week["promises"] for week in body["weeks"]), 2) == 60
    assert any(row["customer_name"] == "Quiet" and row["amount"] == 25 for row in body["pending"])
