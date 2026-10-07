"""Scripted sales demonstration, license display, and organization restore.

Pilot timings, buyer feedback, prices, and renewal dates are not filled in here.
"""

import json
import os

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient

from server.backup import restore_org, snapshot_org
from server.main import app
from server.sales_exports import statement_reports, workbook_bytes
from server.store import get_store, reset_store_for_tests


def client():
    reset_store_for_tests()
    c = TestClient(app)
    logged = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert logged.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    opened = c.post("/api/demo")
    assert opened.status_code == 200, opened.text
    return c


def test_demo_path_reaches_follow_up_explanation_and_statement():
    c = client()
    home = c.get("/api/dashboard")
    assert home.status_code == 200, home.text
    assert home.json().get("explanations")
    work = c.get("/api/worklist")
    assert work.status_code == 200, work.text
    assert any(row.get("customer") == "Harbour Traders" or row.get("subject") == "Harbour Traders" for row in work.json()["rows"])
    contact = c.post("/api/collection/contacts", json={
        "customer_name": "Harbour Traders",
        "contacted_on": "2026-10-07",
        "staff": "admin",
        "channel": "phone",
        "note": "Confirmed the overdue balance is still open.",
        "next_step": "Send the statement",
        "next_follow_up": "2026-10-08",
    })
    assert contact.status_code == 200, contact.text
    listed = c.get("/api/collection", params={"customer": "North Mill"}).json()
    promise = listed["promises"][0]
    suggestion = (promise.get("suggestions") or [None])[0]
    assert suggestion, listed
    confirmed = c.post("/api/collection/allocations", json={
        "promise_id": promise["id"],
        "source_uk": suggestion["source_uk"],
        "source_type": suggestion["source_type"],
        "amount": 15000,
    })
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["remaining"] > 0
    assert confirmed.json()["allocated"] == 15000
    customers = c.get("/api/customers").json()["customers"]
    harbour = next(row for row in customers if row["name"] == "Harbour Traders")
    statement = c.get("/api/customers/" + harbour["uk"] + "/xlsx")
    assert statement.status_code == 200, statement.text
    assert b"PK" == statement.content[:2]


def test_long_name_and_empty_statement_still_export():
    name = "A" * 180
    reports = statement_reports({
        "name": name,
        "company_name": "Vay Demo Traders",
        "currency_code": "INR",
        "as_of": "2026-10-07",
        "due": 0,
        "open_invoices": [],
        "owe_buckets": {},
    })
    blob = workbook_bytes(reports)
    assert blob[:2] == b"PK"
    assert any(row[1] == name for report in reports for row in report["rows"] if len(row) > 1)


def test_license_matches_the_desktop_policy_and_diagnostics_omit_credentials():
    c = client()
    license_view = c.get("/api/license")
    assert license_view.status_code == 200, license_view.text
    body = license_view.json()
    assert body["status"] == "active"
    assert body["price"] == "Included with this install"
    assert body["renewal"] is None
    assert body["expires"] is None
    assert "does not expire" in body["renewal_note"]
    assert body["packs"]["wholesale"] is True
    diagnostics = c.get("/api/license/diagnostics")
    assert diagnostics.status_code == 200, diagnostics.text
    text = diagnostics.text.lower()
    for secret in ("password", "secret", "token", "session", "admin123"):
        assert secret not in text
    parsed = json.loads(diagnostics.content)
    assert "row_counts" in parsed
    assert "user" not in parsed["row_counts"]


def test_restore_and_entitlement_keep_customer_rows():
    c = client()
    store = get_store()
    before = snapshot_org(store)
    names = {row.get("fields", {}).get("Account Name") for row in store.rows_of_type("customer")}
    assert "Harbour Traders" in names
    for row in list(store.rows_of_type("customer")):
        store.delete_row("customer", row.get("uk"))
    assert store.rows_of_type("customer") == []
    restored = c.post("/api/backup/restore", json=before)
    assert restored.status_code == 200, restored.text
    names = {row.get("fields", {}).get("Account Name") for row in store.rows_of_type("customer")}
    assert "Harbour Traders" in names
    changed = c.post("/api/entitlements", json={"pack": "retail", "enabled": False})
    assert changed.status_code == 200, changed.text
    names = {row.get("fields", {}).get("Account Name") for row in store.rows_of_type("customer")}
    assert "Harbour Traders" in names
    assert restore_org(store, before)["restored"] >= 1
