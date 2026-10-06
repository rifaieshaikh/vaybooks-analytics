"""Orphaned job cleanup on process restart."""

import os
from datetime import datetime, timedelta

from server.startup import fail_orphaned_jobs, pid_alive
from server.store import MemoryStore


def test_live_owner_is_left_alone():
    store = MemoryStore()
    run = store.insert_run({"status": "running", "packs": {}, "report_date": "2024-01-01", "owner_pid": os.getpid()})
    rid = str(run["_id"])
    out = fail_orphaned_jobs(store)
    assert out["runs"] == 0
    assert store.get_run(rid)["status"] == "running"
    assert store.get_run(rid)["owner_pid"] == os.getpid()


def test_dead_owner_is_resumed_instead_of_failed():
    assert not pid_alive(2**31 - 1)
    store = MemoryStore()
    run = store.insert_run({
        "status": "running",
        "packs": {},
        "report_date": "2024-01-01",
        "owner_pid": 2**31 - 1,
        "message": "working",
    })
    rid = str(run["_id"])
    out = fail_orphaned_jobs(store)
    assert out["run_ids"] == [rid]
    doc = store.get_run(rid)
    assert doc["status"] == "queued"
    assert doc["owner_pid"] == os.getpid()
    assert doc["message"] == ""


def test_unowned_running_create_is_not_failed():
    store = MemoryStore()
    run = store.insert_run({"status": "running", "packs": {}, "report_date": "2024-01-01", "message": "working"})
    rid = str(run["_id"])
    run2 = store.insert_run({"status": "succeeded", "packs": {}, "report_date": "2024-01-02"})
    store.update_run(str(run2["_id"]), {"pdf_export_status": "running"})
    job = store.insert_import_job({"status": "queued", "filename": "x.xlsx"})

    out = fail_orphaned_jobs(store)
    assert out == {"runs": 0, "exports": 0, "imports": 0, "run_ids": [], "export_ids": [], "import_ids": []}
    assert store.get_run(rid)["status"] == "running"
    assert store.get_run(rid)["message"] == "working"
    assert store.get_run(str(run2["_id"]))["pdf_export_status"] == "running"
    assert store.get_import_job(str(job["_id"]))["status"] == "queued"


def test_stale_queued_job_is_resumed():
    store = MemoryStore()
    run = store.insert_run({"status": "queued", "packs": {}, "report_date": "2024-01-01"})
    rid = str(run["_id"])
    store.update_run(rid, {"created_at": datetime.utcnow() - timedelta(minutes=5)})
    job = store.insert_import_job({"status": "queued", "filename": "x.xlsx"})
    store.update_import_job(str(job["_id"]), {"created_at": datetime.utcnow() - timedelta(minutes=5)})

    out = fail_orphaned_jobs(store)
    assert out["runs"] == 1
    assert out["imports"] == 1
    assert store.get_run(rid)["status"] == "queued"
    assert store.get_run(rid)["owner_pid"] == os.getpid()
    assert store.get_import_job(str(job["_id"]))["status"] == "queued"
    assert store.get_import_job(str(job["_id"]))["owner_pid"] == os.getpid()
