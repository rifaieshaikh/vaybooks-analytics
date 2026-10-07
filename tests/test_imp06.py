"""IMP-06: review results stay observed, and one receipt is not counted twice."""

import os

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient

from server.items360 import save_holding
from server.main import app
from server.store import get_store, reset_store_for_tests


def client():
    reset_store_for_tests()
    c = TestClient(app)
    logged = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert logged.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    return c


def login(username, password):
    other = TestClient(app)
    logged = other.post("/api/auth/login", json={"username": username, "password": password})
    assert logged.status_code == 200, logged.text
    return other


def _run(store):
    store.insert_run({
        "status": "succeeded",
        "report_date": "2026-10-03",
        "finished_at": "2026-10-03T08:00:00Z",
        "manifest": {},
    })


def _action(c, kind, name, amount, due, assigned="2026-10-01"):
    created = c.post("/api/actions", json={
        "action_type": kind,
        "subject_kind": "customer" if kind != "purchase" else "item",
        "subject_name": name,
        "proposal": "%s %s" % (kind, name),
        "owner": "admin",
        "due_date": due,
        "amount": amount,
        "assigned_at": assigned,
        "report_date": "2026-10-03",
    })
    assert created.status_code == 200, created.text
    return created.json()


def test_one_receipt_is_not_added_to_two_tasks_and_allocations_stay_separate():
    c = client()
    _run(get_store())
    first = _action(c, "collection", "Acme", 40, "2026-10-08")
    second = _action(c, "collection", "Acme", 40, "2026-10-20")
    store = get_store()
    store.upsert_row({
        "type": "receipt",
        "uk": "shared",
        "fields": {"Date": "2026-10-05", "Account Name": "Acme", "Amount": 100},
    })
    review = c.get("/api/review")
    assert review.status_code == 200, review.text
    rows = {row["id"]: row for row in review.json()["actions"]}
    observed = sorted((rows[first["id"]]["outcome"].get("observed_amount") or 0, rows[second["id"]]["outcome"].get("observed_amount") or 0))
    assert observed == [0, 40]
    assert rows[first["id"]]["outcome"]["label"] == "Received since assigned"

    store.upsert_row({
        "type": "receipt",
        "uk": "paid",
        "fields": {"Date": "2026-10-05", "Account Name": "Harbor", "Amount": 20},
    })
    store.upsert_row({
        "type": "receipt",
        "uk": "open-receipt",
        "fields": {"Date": "2026-10-06", "Account Name": "Harbor", "Amount": 15},
    })
    harbor = _action(c, "collection", "Harbor", 100, "2026-10-09")
    promised = c.post("/api/collection/promises", json={
        "customer_name": "Harbor",
        "amount": 20,
        "promised_on": "2026-10-04",
        "action_id": harbor["id"],
    })
    assert promised.status_code == 200, promised.text
    store.upsert_row({
        "type": "collection_allocation",
        "uk": "alloc-paid",
        "fields": {
            "promise_id": promised.json()["id"],
            "source_uk": "paid",
            "source_type": "receipt",
            "amount": 20,
            "basis": "source_confirmed",
        },
    })
    again = c.get("/api/review")
    assert again.status_code == 200, again.text
    body = next(row for row in again.json()["actions"] if row["id"] == harbor["id"])
    evidence = body["outcome"]["evidence"]
    allocated = next(row for row in evidence if row["kind"] == "allocated")
    observed_row = next(row for row in evidence if row["kind"] == "observed")
    assert allocated["basis_label"] == "Source-confirmed"
    assert allocated["amount"] == 20
    assert body["outcome"]["verified_amount"] == 20
    assert observed_row["label"] == "Received since assigned"
    assert body["outcome"]["observed_amount"] == 15
    assert again.json()["results"]["refreshed_at"] == "2026-10-03T08:00:00Z"
    assert again.json()["results"]["review_opens"] == 1


def test_sale_and_stock_results_name_the_evidence_or_stay_pending():
    c = client()
    _run(get_store())
    recovery = _action(c, "recovery", "Repeat", None, "2026-10-08")
    purchase = _action(c, "purchase", "Widget", 10, "2026-10-08")
    quiet = _action(c, "collection", "Quiet", 25, "2026-10-08")
    missed_sale = _action(c, "recovery", "Quiet", None, "2026-10-08")
    missed_stock = _action(c, "purchase", "Bolt", 4, "2026-10-08")
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "again",
        "fields": {"Date": "2026-10-06", "Party Name": "Repeat", "Sales Rep": "Asha", "Net Amount": 80, "Invoice No": "R1"},
    })
    save_holding(store, "Widget", min_hold=20)
    store.upsert_row({
        "type": "stock",
        "uk": "Widget",
        "effective_date": "2026-10-05",
        "fields": {"Item Name": "Widget", "Qty": 8, "EffectiveDate": "2026-10-05"},
    })
    review = c.get("/api/review")
    assert review.status_code == 200, review.text
    rows = {row["id"]: row["outcome"] for row in review.json()["actions"]}
    assert rows[recovery["id"]]["label"] == "Bought again"
    assert rows[recovery["id"]]["amount"] == 80
    assert rows[recovery["id"]]["evidence_date"] == "2026-10-06"
    assert rows[purchase["id"]]["label"] == "Stock risk is still open"
    assert rows[purchase["id"]]["resolved"] is False
    assert rows[purchase["id"]]["evidence_date"] == "2026-10-05"
    assert rows[quiet["id"]]["pending"] is True
    assert "pending" in rows[quiet["id"]]["label"].lower()
    assert rows[quiet["id"]]["amount"] is None
    assert rows[missed_sale["id"]]["label"] == "No sale since assigned"
    assert rows[missed_sale["id"]]["amount"] is None
    assert rows[missed_stock["id"]]["label"] == "Waiting for the next stock file"
    assert rows[missed_stock["id"]]["amount"] is None

    fresh = client()
    _run(get_store())
    waiting = _action(fresh, "recovery", "Quiet", None, "2026-10-08")
    alone = fresh.get("/api/review")
    assert alone.status_code == 200, alone.text
    pending_sale = next(row["outcome"] for row in alone.json()["actions"] if row["id"] == waiting["id"])
    assert pending_sale["pending"] is True
    assert "pending" in pending_sale["label"].lower()
    assert pending_sale["amount"] is None


def test_results_follow_the_salesperson_and_hide_from_someone_who_cannot_read():
    c = client()
    store = get_store()
    _run(store)
    store.upsert_row({
        "type": "sales",
        "uk": "n",
        "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 10},
    })
    store.upsert_row({
        "type": "sales",
        "uk": "h",
        "fields": {"Date": "2026-10-02", "Party Name": "Harbor", "Sales Rep": "Rita", "Net Amount": 12},
    })
    _action(c, "collection", "Northwind", 10, "2026-10-08")
    _action(c, "collection", "Harbor", 10, "2026-10-08")
    assert c.post("/api/users", json={"username": "asha", "password": "asha12345", "role": "Sales"}).status_code == 200
    assert c.patch("/api/users/asha", json={"sales_reps": ["Asha"]}).status_code == 200
    asha = login("asha", "asha12345")
    own = asha.get("/api/review")
    assert own.status_code == 200, own.text
    names = [row["subject_name"] for row in own.json()["results"]["rows"]]
    assert names == ["Northwind"]
    assert asha.get("/api/review?staff=admin").status_code == 403

    assert c.post("/api/roles", json={"name": "Outsider", "permissions": ["stock.upload"]}).status_code == 200
    assert c.post("/api/users", json={"username": "outsider", "password": "outsider123", "role": "Outsider"}).status_code == 200
    outsider = login("outsider", "outsider123")
    refused = outsider.get("/api/review")
    assert refused.status_code == 403
    assert "verified_amount" not in refused.text
    assert "results" not in refused.text
