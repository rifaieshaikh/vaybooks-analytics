"""Sales demonstration: demo seed, collection scope, and today's stock rows."""

import os

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient

from server.main import app
from server.store import get_store, reset_store_for_tests
from server.tenant import bind_org


def client():
    reset_store_for_tests()
    c = TestClient(app)
    logged = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert logged.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    return c


def test_demo_opens_resets_and_blocks_after_a_real_import():
    c = client()
    opened = c.post("/api/demo")
    assert opened.status_code == 200, opened.text
    body = opened.json()
    names = {row["name"] for row in body["scenarios"]}
    assert names == {"Harbour Traders", "North Mill", "Lane and Co", "Oak Board 18mm"}
    assert body["company_name"] == "Vay Demo Traders"
    assert body["report"]["status"] == "succeeded", body["report"]
    home = c.get("/api/dashboard")
    assert home.status_code == 200, home.text
    assert home.json().get("explanations"), home.text
    again = c.post("/api/demo")
    assert again.status_code == 200, again.text
    assert again.json()["report"]["id"] != body["report"]["id"]
    store = get_store()
    with bind_org("org_b"):
        store.upsert_row({
            "type": "sales",
            "uk": "other-sale",
            "fields": {"Date": "2026-10-01", "Party Name": "Other Co", "Sales Rep": "Asha", "Net Amount": 10},
        })
    store.upsert_row({
        "type": "sales",
        "uk": "real-sale",
        "fields": {"Date": "2026-10-01", "Party Name": "Real Co", "Sales Rep": "Asha", "Net Amount": 5},
    })
    refused = c.post("/api/demo")
    assert refused.status_code == 409, refused.text
    with bind_org("org_b"):
        kept = store.find_row("sales", "other-sale")
    assert kept is not None
    assert (kept.get("fields") or {}).get("Party Name") == "Other Co"


def test_promise_staff_partial_confirm_and_audit():
    c = client()
    created = c.post("/api/collection/promises", json={
        "customer_name": "Acme",
        "amount": 100,
        "promised_on": "2027-01-15",
        "staff": "Asha",
    })
    assert created.status_code == 200, created.text
    assert created.json()["staff"] == "Asha"
    store = get_store()
    store.upsert_row({
        "type": "receipt",
        "uk": "r-open",
        "fields": {"Date": "2026-10-05", "Account Name": "Acme", "Amount": 40},
    })
    listed = c.get("/api/collection", params={"customer": "Acme"}).json()
    suggestion = listed["promises"][0]["suggestions"][0]
    confirmed = c.post("/api/collection/allocations", json={
        "promise_id": created.json()["id"],
        "source_uk": suggestion["source_uk"],
        "source_type": suggestion["source_type"],
        "amount": 15,
    })
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["allocated"] == 15
    assert confirmed.json()["remaining"] == 85
    audit = c.get("/api/audit")
    assert audit.status_code == 200, audit.text
    assert any(row["action"] == "collection_promise" for row in audit.json()["events"])


def test_today_includes_assigned_stock_and_filters_kind():
    c = client()
    opened = c.post("/api/demo")
    assert opened.status_code == 200, opened.text
    work = c.get("/api/worklist")
    assert work.status_code == 200, work.text
    kinds = {row["kind"] for row in work.json()["rows"]}
    assert "stock" in kinds
    assert "follow_up" in kinds
    stock = c.get("/api/worklist", params={"kind": "stock"})
    assert stock.status_code == 200, stock.text
    assert stock.json()["rows"]
    assert all(row["kind"] == "stock" for row in stock.json()["rows"])
    row = stock.json()["rows"][0]
    assert row["explanation"]["formula"]
