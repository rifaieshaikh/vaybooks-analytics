"""Phase 5 forecast, retail pack, header preset, location, and questions."""

import os

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient

from server.main import app
from server.mappers import apply_column_map, sales_total
from server.phase2 import build_bundle
from server.store import get_store, reset_store_for_tests
from vay.packs.retail import EXPENSE_ACCOUNT_MAP as RETAIL_MAP
from vay.packs.vay_wholesale import EXPENSE_ACCOUNT_MAP
from vay.phase5 import forecast_sales


def client():
    reset_store_for_tests()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    return c


def test_forecast_withheld_when_last_year_has_no_sales():
    dated = [("2026-09-02", 40), ("2026-10-02", 80)]
    forecast = forecast_sales(dated, "2026-10-03")
    year_ago = forecast["methods"][0]
    trailing = forecast["methods"][1]
    assert year_ago["label"] == "Same days last year"
    assert year_ago["value"] is None
    assert year_ago["status"] == "unavailable"
    assert year_ago["reason"] == "No sales last year"
    assert trailing["value"] == 40
    assert forecast["uncertainty"]["value"] is None
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 80},
    })
    body = c.get("/api/forecast?report_date=2026-10-03")
    assert body.status_code == 200, body.text
    assert body.json()["methods"][0]["value"] is None
    scorecard = build_bundle(store, "2026-10-03")["scorecard"]["rows"]
    assert "sales_mtd" in [row["id"] for row in scorecard]
    assert all("forecast" not in row["id"] for row in scorecard)


def test_retail_template_does_not_copy_vay_expense_names():
    assert RETAIL_MAP == {}
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {"Date": "2026-09-02", "Party Name": "Harbor", "Sales Rep": "Asha", "Net Amount": 30},
    })
    store.upsert_row({
        "type": "sales",
        "uk": "s2",
        "fields": {"Date": "2026-10-02", "Party Name": "Harbor", "Sales Rep": "Asha", "Net Amount": 50},
    })
    store.upsert_row({
        "type": "sales",
        "uk": "s3",
        "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 80},
    })
    store.upsert_row({
        "type": "credit_note",
        "uk": "c1",
        "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Net Amount": 15, "Invoice No": "CN1"},
    })
    adopted = c.post("/api/saved-reports/adopt-retail")
    assert adopted.status_code == 200, adopted.text
    reports = c.get("/api/saved-reports").json()["reports"]
    template = next(row for row in reports if row["template_id"] == "returns_by_customer")
    assert template["status"] == "draft"
    ran = c.get("/api/saved-reports/%s/run?report_date=2026-10-03" % template["id"])
    assert ran.status_code == 200, ran.text
    body = ran.json()
    row = next(item for item in body["rows"] if item["name"] == "Northwind")
    assert row["cells"]["sales_mtd"]["value"] == 15
    blob = str(body)
    for names in EXPENSE_ACCOUNT_MAP.values():
        for name in names:
            assert name not in blob
    wholesale = c.post("/api/saved-reports/adopt-pack")
    assert wholesale.status_code == 200
    again = c.get("/api/saved-reports").json()["reports"]
    assert any(item["template_id"] == "sales_by_rep" for item in again)
    assert any(item["template_id"] == "returns_by_customer" for item in again)


def test_header_preset_keeps_the_same_sales_total():
    c = client()
    applied = c.post("/api/mappers/sales/preset/plain_sales")
    assert applied.status_code == 200, applied.text
    column_map = applied.json()["column_map"]
    canonical = [{"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 80}]
    alternate = [{"Invoice Date": "2026-10-02", "Customer": "Northwind", "Rep": "Asha", "Amount": 80}]
    mapped = [apply_column_map(row, column_map) for row in alternate]
    assert sales_total(mapped) == sales_total(canonical) == 80


def test_blank_location_left_out_of_groups():
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 10, "Location": "Dock"},
    })
    store.upsert_row({
        "type": "sales",
        "uk": "s2",
        "fields": {"Date": "2026-10-02", "Party Name": "Harbor", "Sales Rep": "Asha", "Net Amount": 99, "Location": ""},
    })
    preview = c.post("/api/saved-reports/preview", json={
        "name": "By location",
        "metric_ids": ["sales_mtd"],
        "dimension": "location",
        "comparison": "current",
        "report_date": "2026-10-03",
    })
    assert preview.status_code == 200, preview.text
    rows = preview.json()["rows"]
    assert [row["name"] for row in rows] == ["Dock"]
    assert rows[0]["cells"]["sales_mtd"]["value"] == 10


def test_unmatched_question_does_not_invent_a_number():
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 80},
    })
    missed = c.post("/api/saved-reports/ask", json={"text": "what is the weather", "report_date": "2026-10-03"})
    assert missed.status_code == 200, missed.text
    body = missed.json()
    assert body["answered"] is False
    assert body["value"] is None
    assert body["message"] == "Cannot answer that."
    hit = c.post("/api/saved-reports/ask", json={"text": "Sales", "report_date": "2026-10-03"})
    assert hit.status_code == 200, hit.text
    answered = hit.json()
    assert answered["answered"] is True
    assert answered["value"] == 80
    assert answered["metric_versions"]["sales_mtd"] == 1
