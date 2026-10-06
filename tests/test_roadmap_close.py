"""Remaining roadmap work: pilots stay blocked, isolation, release, analytics, hosted."""

import json
import os
from pathlib import Path

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient

from server.auth import SEED_ROLE_NAMES, seed_role_permissions
from server.backup import restore_org, snapshot_org
from server.import_jobs import run_import_job
from server.main import app
from server.pilots import baselines_ready, pilot_status, presets_for_received_pilots, samples_root
from server.startup import fail_orphaned_jobs
from server.store import get_store, reset_store_for_tests
from server.tenant import bind_org
from vay.passwords import hash_password


def client():
    reset_store_for_tests()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    return c


def _provision(store, org_id, username, password):
    roles = seed_role_permissions()
    with bind_org(org_id):
        for name in SEED_ROLE_NAMES:
            store.put_role(name, {"name": name, "permissions": list(roles[name])})
        store.put_user({
            "username": username,
            "password_hash": hash_password(password),
            "role": "Admin",
            "enabled": True,
            "must_change_password": False,
        })


def test_external_pilots_stay_blocked_until_a_workbook_arrives():
    rows = pilot_status(samples_root())
    assert [row["pilot"] for row in rows] == ["edge_point", "plymax", "eff_yes_traders"]
    assert all(row["blocked"] for row in rows)
    assert baselines_ready(samples_root()) is False
    assert presets_for_received_pilots(samples_root()) == []
    folder = Path(samples_root()) / "edge_point"
    assert "BLOCKER" in (folder / "MANIFEST.md").read_text(encoding="utf-8")


def test_second_organization_cannot_read_rows_runs_or_exports():
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 80},
    })
    run = store.insert_run({"status": "succeeded", "report_date": "2026-10-03", "xlsx_id": "missing"})
    _provision(store, "org_b", "beta", "beta-pass-1")
    other = TestClient(app)
    logged = other.post("/api/auth/login", json={"username": "beta", "password": "beta-pass-1"})
    assert logged.status_code == 200, logged.text
    assert logged.json()["org_id"] == "org_b"
    rows = other.get("/api/rows?type=sales")
    assert rows.status_code == 200, rows.text
    assert rows.json()["total"] == 0
    assert other.get("/api/runs/%s" % run["_id"]).status_code == 404
    assert other.get("/api/runs/%s/file" % run["_id"]).status_code == 404
    home = c.get("/api/rows?type=sales")
    assert home.json()["total"] == 1


def test_backup_restore_replaces_only_the_current_organization():
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "keep",
        "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 10},
    })
    snap = snapshot_org(store)
    store.upsert_row({
        "type": "sales",
        "uk": "later",
        "fields": {"Date": "2026-10-02", "Party Name": "Harbor", "Sales Rep": "Asha", "Net Amount": 5},
    })
    _provision(store, "org_b", "beta", "beta-pass-1")
    with bind_org("org_b"):
        store.upsert_row({
            "type": "sales",
            "uk": "theirs",
            "fields": {"Date": "2026-10-02", "Party Name": "Other", "Sales Rep": "Asha", "Net Amount": 7},
        })
    restored = c.post("/api/backup/restore", json=snap)
    assert restored.status_code == 200, restored.text
    names = [row["fields"]["Party Name"] for row in store.rows_of_type("sales")]
    assert names == ["Northwind"]
    with bind_org("org_b"):
        assert [row["fields"]["Party Name"] for row in store.rows_of_type("sales")] == ["Other"]


def test_restart_keeps_a_fresh_queued_job_and_cancel_stops_a_queued_run():
    c = client()
    store = get_store()
    queued = store.insert_run({"status": "queued", "report_date": "2026-10-03"})
    failed = fail_orphaned_jobs(store)
    assert failed["runs"] == 0
    assert store.get_run(queued["_id"])["status"] == "queued"
    again = store.insert_run({"status": "queued", "report_date": "2026-10-03"})
    cancelled = c.post("/api/runs/%s/cancel" % again["_id"])
    assert cancelled.status_code == 200, cancelled.text
    assert store.get_run(again["_id"])["status"] == "cancelled"


def test_same_file_hash_does_not_import_twice():
    client()
    store = get_store()
    blob = store.put_blob(b"not-a-workbook", "sales.xlsx", "application/octet-stream")
    first_upload = store.insert_upload({"filename": "sales.xlsx", "gridfs_id": blob, "file_sha256": "abc", "dry_run": False})
    first = store.insert_import_job({
        "status": "succeeded",
        "upload_id": first_upload,
        "file_sha256": "abc",
        "dry_run": False,
        "filename": "sales.xlsx",
    })
    second_upload = store.insert_upload({"filename": "sales.xlsx", "gridfs_id": blob, "file_sha256": "abc", "dry_run": False})
    store.insert_row({
        "type": "sales",
        "uk": "kept",
        "source_upload_id": first_upload,
        "fields": {"Party Name": "Northwind"},
    })
    second = store.insert_import_job({
        "status": "queued",
        "upload_id": second_upload,
        "file_sha256": "abc",
        "dry_run": False,
        "filename": "sales.xlsx",
        "maps": {},
        "permissions": ["*"],
    })
    run_import_job(store, second["_id"])
    done = store.get_import_job(second["_id"])
    assert done["status"] == "succeeded"
    assert done["message"] == "Already imported"
    assert done["reused_job_id"] == str(first["_id"])
    assert len(store.rows_of_type("sales")) == 1


def test_same_file_imports_again_after_its_rows_are_gone():
    client()
    store = get_store()
    blob = store.put_blob(b"not-a-workbook", "sales.xlsx", "application/octet-stream")
    first_upload = store.insert_upload({"filename": "sales.xlsx", "gridfs_id": blob, "file_sha256": "abc", "dry_run": False})
    store.insert_import_job({
        "status": "succeeded",
        "upload_id": first_upload,
        "file_sha256": "abc",
        "dry_run": False,
        "filename": "sales.xlsx",
    })
    second_upload = store.insert_upload({"filename": "sales.xlsx", "gridfs_id": blob, "file_sha256": "abc", "dry_run": False})
    second = store.insert_import_job({
        "status": "queued",
        "upload_id": second_upload,
        "file_sha256": "abc",
        "dry_run": False,
        "filename": "sales.xlsx",
        "maps": {},
        "permissions": ["*"],
    })
    run_import_job(store, second["_id"])
    done = store.get_import_job(second["_id"])
    assert done["message"] != "Already imported"
    assert done["status"] == "failed"


def test_audit_records_login_and_pages_runs():
    c = client()
    store = get_store()
    for i in range(3):
        store.insert_run({"status": "succeeded", "report_date": "2026-10-0%d" % (i + 1)})
    page = c.get("/api/runs?limit=2&page=1")
    assert page.status_code == 200
    body = page.json()
    assert body["total"] >= 3
    assert len(body["runs"]) == 2
    audit = c.get("/api/audit")
    assert audit.status_code == 200, audit.text
    assert any(row["action"] == "login" for row in audit.json()["events"])


def test_rows_page_is_bounded():
    c = client()
    store = get_store()
    for i in range(500):
        store.upsert_row({
            "type": "sales",
            "uk": "s%d" % i,
            "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 1},
        })
    page = c.get("/api/rows?type=sales&limit=50")
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["total"] == 500
    assert len(body["rows"]) == 50
    assert body["limit"] == 50


def test_composed_metric_rejects_unknown_and_versions_on_edit():
    c = client()
    bad = c.post("/api/custom-metrics", json={"name": "Nope", "metric_ids": ["not_a_metric"]})
    assert bad.status_code == 400
    created = c.post("/api/custom-metrics", json={"name": "Sales and overdue", "metric_ids": ["sales_mtd", "ar_overdue_30"]})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["dependencies"] == ["sales_mtd", "ar_overdue_30"]
    assert body["status"] == "draft"
    assert body["version"] == 1
    edited = c.put("/api/custom-metrics/%s" % body["id"], json={"metric_ids": ["sales_mtd"]})
    assert edited.status_code == 200, edited.text
    assert edited.json()["version"] == 2
    assert edited.json()["status"] == "draft"
    approved = c.post("/api/custom-metrics/%s/approve" % body["id"])
    assert approved.json()["status"] == "approved"


def test_scenario_is_not_on_the_scorecard_and_consolidation_stays_blank():
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "now",
        "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 80, "Company": "Dock"},
    })
    store.upsert_row({
        "type": "sales",
        "uk": "old",
        "fields": {"Date": "2026-08-02", "Party Name": "Harbor", "Sales Rep": "Asha", "Net Amount": 40, "Company": "Pier"},
    })
    forecast = c.get("/api/forecast?report_date=2026-10-03&scenario=Sales+factor&sales_factor=2")
    assert forecast.status_code == 200, forecast.text
    body = forecast.json()
    assert body["scenario"]["official"] is False
    assert "not an official metric" in body["scenario"]["label"]
    rolled = c.get("/api/consolidation?report_date=2026-10-03")
    assert rolled.status_code == 200, rolled.text
    consolidated = rolled.json()
    assert consolidated["total"] is None
    assert consolidated["status"] == "unavailable"
    pier = next(row for row in consolidated["rows"] if row["name"] == "Pier")
    assert pier["value"] is None


def test_hosted_entitlement_and_support_gate():
    c = client()
    os.environ["VAY_HOSTED"] = "1"
    try:
        denied = c.post("/api/saved-reports/adopt-pack")
        assert denied.status_code == 403, denied.text
        turned = c.post("/api/entitlements", json={"pack": "wholesale", "enabled": True})
        assert turned.status_code == 200, turned.text
        adopted = c.post("/api/saved-reports/adopt-pack")
        assert adopted.status_code == 200, adopted.text
        hours = c.post("/api/support-hours", json={"hours": 3, "note": "onboarding"})
        assert hours.status_code == 200, hours.text
        assert hours.json()["met"] is False
    finally:
        os.environ.pop("VAY_HOSTED", None)


def test_product_path_assigns_three_actions_and_approves_a_report():
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 80, "Invoice No": "1"},
    })
    store.upsert_row({
        "type": "sales",
        "uk": "s0",
        "fields": {"Date": "2026-09-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 20, "Invoice No": "0"},
    })
    run = store.insert_run({"status": "succeeded", "report_date": "2026-10-03", "manifest": {}})
    preview = c.get("/api/analytics/onboarding?report_date=2026-10-03")
    assert preview.status_code == 200
    score = c.get("/api/analytics?run=%s" % run["_id"])
    assert score.status_code == 200, score.text
    change = score.json()["sales_change"]["customers"][0]["change"]
    assert change == 60
    for kind, proposal in (
        ("collection", "Collect from Northwind"),
        ("recovery", "Recover Northwind"),
        ("purchase", "Reorder Widget"),
    ):
        created = c.post("/api/actions", json={
            "action_type": kind,
            "subject_kind": "customer",
            "subject_name": "Northwind",
            "proposal": proposal,
            "owner": "admin",
            "due_date": "2026-10-10",
            "report_date": "2026-10-03",
            "assigned_at": "2026-10-03",
        })
        assert created.status_code == 200, created.text
    adopted = c.post("/api/saved-reports/adopt-pack")
    assert adopted.status_code == 200, adopted.text
    report = c.get("/api/saved-reports").json()["reports"][0]
    approved = c.post("/api/saved-reports/%s/approve" % report["id"])
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"


def test_header_preset_loader_reads_only_a_received_pilot(tmp_path):
    pilot = tmp_path / "edge_point"
    pilot.mkdir()
    (pilot / "MANIFEST.md").write_text("Status: received\n", encoding="utf-8")
    (pilot / "sales.csv").write_text("Invoice Date,Customer,Rep,Amount\n2026-10-02,Northwind,Asha,80\n", encoding="utf-8")
    (pilot / "preset.json").write_text(json.dumps({
        "id": "edge_point_sales",
        "type": "sales",
        "column_map": {"Invoice Date": "Date", "Customer": "Party Name", "Rep": "Sales Rep", "Amount": "Net Amount"},
    }), encoding="utf-8")
    for name in ("plymax", "eff_yes_traders"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "MANIFEST.md").write_text("BLOCKER — workbook not yet received\n", encoding="utf-8")
    found = presets_for_received_pilots(tmp_path)
    assert [row["id"] for row in found] == ["edge_point_sales"]
