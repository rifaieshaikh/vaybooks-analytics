"""Phase 4 saved reports, wholesale templates, export, and one weekly run."""

import os

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient

from server.main import app
from server.saved_reports import scheduled_sheets
from server.store import get_store, reset_store_for_tests
from server.weekly import ensure_weekly_run
from vay.dates import today_ist
from vay.packs.vay_wholesale import EXPENSE_ACCOUNT_MAP
from vay.phase4 import run_definition


def client():
    reset_store_for_tests()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    return c


def _report(name="Sales by rep", metrics=None, dimension="sales_rep"):
    return {
        "name": name,
        "metric_ids": metrics or ["sales_mtd", "ar_overdue_30"],
        "dimension": dimension,
        "comparison": "current",
        "filters": [],
        "report_date": "2026-10-03",
    }


def test_viewer_sees_saved_report_only_after_approval():
    c = client()
    created = c.post("/api/saved-reports", json=_report())
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["owner"] == "admin"
    assert body["status"] == "draft"
    assert c.post("/api/users", json={"username": "look", "password": "look123", "role": "Viewer"}).status_code == 200
    viewer = TestClient(app)
    assert viewer.post("/api/auth/login", json={"username": "look", "password": "look123"}).status_code == 200
    assert body["id"] not in [row["id"] for row in viewer.get("/api/saved-reports").json()["reports"]]
    assert viewer.get("/api/saved-reports/%s/export?report_date=2026-10-03" % body["id"]).status_code == 404
    approved = c.post("/api/saved-reports/%s/approve" % body["id"])
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    listed = viewer.get("/api/saved-reports").json()["reports"]
    assert body["id"] in [row["id"] for row in listed]


def test_unavailable_metric_stays_unavailable():
    result = run_definition(
        [{"name": "Widget", "cover_days": 4, "cover_label": "", "pack_size": ""}],
        {"metric_ids": ["stock_cover_days"], "dimension": "product", "comparison": "current"},
        {"stock_cover_days": {"status": "unavailable", "reason": "Stock snapshot is dated 2026-09-01; report date is 2026-10-03"}},
    )
    cell = result["rows"][0]["cells"]["stock_cover_days"]
    assert cell["value"] is None
    assert cell["status"] == "unavailable"
    assert "2026-09-01" in cell["reason"]
    assert result["metrics"][0]["status"] == "unavailable"
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "stock",
        "uk": "st1",
        "fields": {"Item Name": "Widget", "Qty": 10, "P.Price": 5},
    })
    store.upsert_row({
        "type": "items",
        "uk": "it1",
        "fields": {"Date": "2026-10-02", "Item Name": "Widget", "Qty": 2, "Rate": 8},
    })
    preview = c.post("/api/saved-reports/preview", json={
        "name": "Cover",
        "metric_ids": ["stock_cover_days"],
        "dimension": "product",
        "comparison": "current",
        "report_date": "2026-10-03",
    })
    assert preview.status_code == 200, preview.text
    payload = preview.json()
    assert payload["metrics"][0]["status"] == "unavailable"
    assert payload["rows"]
    assert payload["rows"][0]["cells"]["stock_cover_days"]["value"] is None
    assert payload["rows"][0]["cells"]["stock_cover_days"]["value"] != 0


def test_wholesale_template_runs_without_vay_accounts():
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 80, "Route": "Dock"},
    })
    store.upsert_row({
        "type": "sales",
        "uk": "s2",
        "fields": {"Date": "2026-10-02", "Party Name": "Harbor", "Sales Rep": "Asha", "Net Amount": 20},
    })
    adopted = c.post("/api/saved-reports/adopt-pack")
    assert adopted.status_code == 200, adopted.text
    reports = c.get("/api/saved-reports").json()["reports"]
    template = next(row for row in reports if row["template_id"] == "sales_by_rep")
    assert template["status"] == "draft"
    ran = c.get("/api/saved-reports/%s/run?report_date=2026-10-03" % template["id"])
    assert ran.status_code == 200, ran.text
    body = ran.json()
    row = next(item for item in body["rows"] if item["name"] == "Asha")
    assert row["cells"]["sales_mtd"]["value"] == 100
    blob = str(body)
    for names in EXPENSE_ACCOUNT_MAP.values():
        for name in names:
            assert name not in blob
    preview = c.post("/api/saved-reports/preview", json={
        "name": "Routes",
        "metric_ids": ["sales_mtd"],
        "dimension": "customer",
        "comparison": "current",
        "custom_column": "Route",
        "report_date": "2026-10-03",
    })
    assert preview.status_code == 200, preview.text
    by_name = {row["name"]: row for row in preview.json()["rows"]}
    assert by_name["Northwind"]["custom"] == "Dock"
    assert by_name["Harbor"]["custom"] == ""


def test_dataset_export_includes_metric_version():
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 40},
    })
    created = c.post("/api/saved-reports", json=_report("Export", ["sales_mtd"], "sales_rep"))
    assert created.status_code == 200, created.text
    report_id = created.json()["id"]
    assert c.get("/api/saved-reports/%s/export?report_date=2026-10-03" % report_id).status_code == 404
    assert c.post("/api/saved-reports/%s/approve" % report_id).status_code == 200
    exported = c.get("/api/saved-reports/%s/export?report_date=2026-10-03" % report_id)
    assert exported.status_code == 200, exported.text
    body = exported.json()
    assert body["metric_versions"]["sales_mtd"] == 1
    assert body["rows"][0]["cells"]["sales_mtd"]["value"] == 40
    csv_res = c.get("/api/saved-reports/%s/export?report_date=2026-10-03&format=csv" % report_id)
    assert csv_res.status_code == 200
    assert "metric_version" in csv_res.text
    assert ",1" in csv_res.text


def test_scheduled_report_does_not_create_a_second_weekly_run():
    c = client()
    created = c.post("/api/saved-reports", json={
        **_report("Weekly sales", ["sales_mtd"], "sales_rep"),
        "schedule": True,
    })
    assert created.status_code == 200, created.text
    report_id = created.json()["id"]
    assert c.post("/api/saved-reports/%s/approve" % report_id).status_code == 200
    assert c.post("/api/settings/org-policy", json={"weekly_run": True}).status_code == 200
    store = get_store()
    before = len(store.list_runs() or [])
    sheets = scheduled_sheets(store, "2026-10-03")
    assert any(row.get("title") == "Weekly sales" for row in sheets)
    assert len(store.list_runs() or []) == before
    first = ensure_weekly_run(store, start=False)
    second = ensure_weekly_run(store, start=False)
    assert first
    assert second is None
    weekly = [row for row in store.list_runs() if row.get("weekly")]
    assert len(weekly) == 1
    assert weekly[0]["report_date"] == today_ist().strftime("%Y-%m-%d")
