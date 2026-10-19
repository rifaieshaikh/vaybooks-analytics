"""Weekly review keeps the suggestions from Create reports and refreshes results when the books change."""

import os

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient

from server.actions import attach_outcomes
from server.main import app
from server.store import get_store, reset_store_for_tests


def client():
    reset_store_for_tests()
    c = TestClient(app)
    logged = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert logged.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    return c


def test_saved_suggestions_are_read_and_results_recompute_when_receipts_change(monkeypatch):
    c = client()
    store = get_store()
    run = store.insert_run({
        "status": "succeeded",
        "report_date": "2026-10-03",
        "finished_at": "2026-10-03T08:00:00Z",
        "manifest": {},
        "review_suggestions": [{
            "action_type": "collection",
            "subject_kind": "customer",
            "subject_name": "Saved",
            "proposal": "Collect from Saved",
            "reason": "First collection",
        }],
        "review_quality_messages": [],
    })
    calls = {"n": 0}
    real = attach_outcomes

    def wrapped(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr("server.actions.attach_outcomes", wrapped)
    monkeypatch.setattr("server.phase2.build_bundle", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("bundle rebuilt")))

    first = c.get("/api/review")
    assert first.status_code == 200, first.text
    assert first.json()["suggestions"][0]["subject_name"] == "Saved"
    assert calls["n"] == 1

    second = c.get("/api/review")
    assert second.status_code == 200, second.text
    assert second.json()["suggestions"][0]["subject_name"] == "Saved"
    assert calls["n"] == 1

    store.upsert_row({
        "type": "receipt",
        "uk": "later",
        "fields": {"Date": "2026-10-05", "Account Name": "Saved", "Amount": 10},
    })
    third = c.get("/api/review")
    assert third.status_code == 200, third.text
    assert calls["n"] == 2

    forced = c.get("/api/review", params={"refresh": "1"})
    assert forced.status_code == 200, forced.text
    assert calls["n"] == 3
    assert store.get_run(run["_id"]).get("review_cache", {}).get("fingerprint")
