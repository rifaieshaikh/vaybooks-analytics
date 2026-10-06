"""Phase 3 actions, outcomes, reorder budget, and one weekly run."""

import os

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient

from server.main import app
from server.store import get_store, reset_store_for_tests
from server.weekly import ensure_weekly_run
from vay.dates import today_ist
from vay.phase3 import apply_budget, due_weekly_date, received_since, round_pack


def client():
    reset_store_for_tests()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    return c


def test_action_saves_owner_and_due_date():
    c = client()
    created = c.post("/api/actions", json={
        "action_type": "collection",
        "subject_kind": "customer",
        "subject_name": "Acme",
        "proposal": "Collect from Acme",
        "owner": "admin",
        "due_date": "2026-10-10",
        "amount": 100,
        "report_date": "2026-10-03",
        "assigned_at": "2026-10-03",
    })
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["owner"] == "admin"
    assert body["due_date"] == "2026-10-10"
    assert body["status"] == "open"
    done = c.post("/api/actions/%s/status" % body["id"], json={"status": "done"})
    assert done.status_code == 200
    assert done.json()["status"] == "done"


def test_collection_outcome_is_capped_at_assigned_balance():
    capped = received_since(
        [
            {"name": "Acme", "date": "2026-10-02", "amount": 500},
            {"name": "Acme", "date": "2026-10-05", "amount": 40},
            {"name": "Acme", "date": "2026-10-06", "amount": 80},
        ],
        "Acme",
        "2026-10-03",
        100,
    )
    assert capped["amount"] == 100
    assert capped["label"] == "Received since assigned"
    c = client()
    created = c.post("/api/actions", json={
        "action_type": "collection",
        "subject_name": "Acme",
        "proposal": "Collect from Acme",
        "owner": "admin",
        "due_date": "2026-10-10",
        "amount": 100,
        "assigned_at": "2026-10-03",
    })
    assert created.status_code == 200, created.text
    store = get_store()
    store.upsert_row({
        "type": "receipt",
        "uk": "r1",
        "fields": {"Date": "2026-10-05", "Account Name": "Acme", "Sales Rep": "Rep", "Amount": 40},
    })
    store.upsert_row({
        "type": "receipt",
        "uk": "r2",
        "fields": {"Date": "2026-10-06", "Account Name": "Acme", "Sales Rep": "Rep", "Amount": 90},
    })
    listed = c.get("/api/actions").json()["actions"]
    assert listed[0]["outcome"]["amount"] == 100
    assert listed[0]["outcome"]["label"] == "Received since assigned"


def test_reorder_rounds_to_pack_and_stops_at_budget():
    assert round_pack(5, 4, 0) == 8
    kept, spent = apply_budget(
        [
            {"name": "A", "qty": 8, "unit_cost": 10},
            {"name": "B", "qty": 10, "unit_cost": 20},
        ],
        100,
    )
    assert [row["name"] for row in kept] == ["A"]
    assert spent == 80
    c = client()
    saved = c.put("/api/reorder", json={
        "budget": 100,
        "report_date": "2026-10-03",
        "lines": [
            {"name": "A", "qty": 5, "pack_size": 4, "minimum": 0, "unit_cost": 10, "lead_days": 3, "supplier": "Mill"},
            {"name": "B", "qty": 10, "pack_size": 1, "minimum": 0, "unit_cost": 20, "lead_days": 1, "supplier": ""},
        ],
    })
    assert saved.status_code == 200, saved.text
    lines = saved.json()["lines"]
    assert len(lines) == 1
    assert lines[0]["name"] == "A"
    assert lines[0]["qty"] == 8


def test_weekly_run_does_not_backfill_skipped_weeks():
    assert due_weekly_date("2026-10-03", "2026-08-01", True) == "2026-10-03"
    assert due_weekly_date("2026-10-03", "2026-10-01", True) is None
    assert due_weekly_date("2026-10-03", "2026-08-01", False) is None
    c = client()
    assert c.post("/api/settings/org-policy", json={"weekly_run": True}).status_code == 200
    store = get_store()
    first = ensure_weekly_run(store, start=False)
    second = ensure_weekly_run(store, start=False)
    assert first
    assert second is None
    weekly = [row for row in store.list_runs() if row.get("weekly")]
    assert len(weekly) == 1
    assert weekly[0]["report_date"] == today_ist().strftime("%Y-%m-%d")
