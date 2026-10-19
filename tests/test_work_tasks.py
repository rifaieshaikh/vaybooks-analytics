"""Today's work is stored once a day and updated in place."""

import os

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient

from server.main import app
from server.store import get_store, reset_store_for_tests
from server.work_tasks import WORK_TASK_TYPE, list_work_tasks, set_work_task_status, sync_work_tasks


def client():
    reset_store_for_tests()
    c = TestClient(app)
    logged = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert logged.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    return c


def _sale(store, name, rep="Asha"):
    store.upsert_row({
        "type": "sales",
        "uk": name,
        "fields": {"Date": "2026-09-01", "Party Name": name, "Sales Rep": rep, "Net Amount": 80},
    })


def _customer(store, name):
    store.upsert_row({
        "type": "customer",
        "uk": name,
        "fields": {"Account Name": name, "Group": "South", "Balance": 10},
    })


def _contact(c, name):
    created = c.post("/api/collection/contacts", json={
        "customer_name": name,
        "contacted_on": "2026-09-01",
        "channel": "phone",
        "note": "Called",
        "next_step": "Call again",
        "next_follow_up": "2026-09-01",
    })
    assert created.status_code == 200, created.text
    return created.json()


def test_refresh_creates_then_updates_and_keeps_the_same_task():
    c = client()
    store = get_store()
    _sale(store, "Northwind")
    _customer(store, "Northwind")
    _contact(c, "Northwind")

    first = c.post("/api/worklist/refresh")
    assert first.status_code == 200, first.text
    assert first.json()["created"] >= 1
    assert first.json()["updated"] == 0
    stored = [row for row in list_work_tasks(store) if row.get("customer") == "Northwind"]
    assert stored
    task_id = stored[0]["id"]
    assert store.rows_of_type(WORK_TASK_TYPE)

    second = c.post("/api/worklist/refresh")
    assert second.status_code == 200, second.text
    body = second.json()
    assert body["created"] == 0
    assert body["updated"] >= 1
    again = [row for row in list_work_tasks(store) if row.get("customer") == "Northwind" and row.get("status") == "open"]
    assert len(again) == 1
    assert again[0]["id"] == task_id

    listed = c.get("/api/worklist")
    assert listed.status_code == 200, listed.text
    assert any(row["customer"] == "Northwind" for row in listed.json()["rows"])

    skipped = sync_work_tasks(store, force=False, today=body["synced_on"])
    assert skipped["skipped"] is True
    assert skipped["created"] == 0
    marked = c.post("/api/worklist/%s/status" % task_id, json={"status": "done"})
    assert marked.status_code == 200, marked.text
    assert marked.json()["status"] == "done"


def test_done_task_stays_done_and_a_later_day_opens_a_new_one():
    c = client()
    store = get_store()
    _sale(store, "Northwind")
    _customer(store, "Northwind")
    _contact(c, "Northwind")
    prepared = sync_work_tasks(store, force=True, today="2026-10-18")
    assert prepared["created"] >= 1
    task = next(row for row in list_work_tasks(store) if row.get("customer") == "Northwind" and row.get("status") == "open")
    done = set_work_task_status(store, task["id"], "done", today="2026-10-18")
    assert done["status"] == "done"

    same_day = sync_work_tasks(store, force=True, today="2026-10-18")
    assert same_day["created"] == 0
    listed = c.get("/api/worklist")
    assert "Northwind" not in [row["customer"] for row in listed.json()["rows"]]
    assert any(row["id"] == task["id"] and row["status"] == "done" for row in list_work_tasks(store))

    next_day = sync_work_tasks(store, force=True, today="2026-10-19")
    assert next_day["created"] >= 1
    open_rows = [
        row for row in list_work_tasks(store)
        if row.get("customer") == "Northwind" and row.get("status") == "open"
    ]
    assert len(open_rows) == 1
    assert open_rows[0]["id"] != task["id"]
    assert any(row["id"] == task["id"] and row["status"] == "done" for row in list_work_tasks(store))


def test_a_removed_follow_up_stays_stored_until_it_is_dropped():
    c = client()
    store = get_store()
    _sale(store, "Northwind")
    _customer(store, "Northwind")
    contact = _contact(c, "Northwind")
    sync_work_tasks(store, force=True, today="2026-10-18")
    store.delete_row("collection_contact", contact["id"])
    sync_work_tasks(store, force=True, today="2026-10-18")
    kept = [row for row in list_work_tasks(store) if row.get("customer") == "Northwind"]
    assert kept
    assert kept[0]["status"] == "open"
    assert kept[0]["last_seen"] == "2026-10-18"
    listed = c.get("/api/worklist")
    assert any(row["customer"] == "Northwind" for row in listed.json()["rows"])
