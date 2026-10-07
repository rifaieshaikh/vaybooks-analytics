"""IMP-04: a personal daily queue scoped to the salesperson's accounts."""

import os

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient

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


def _sale(store, name, rep, day="2026-09-01", amount=80):
    store.upsert_row({
        "type": "sales",
        "uk": "%s-%s" % (name, day),
        "fields": {
            "Date": day,
            "Party Name": name,
            "Sales Rep": rep,
            "Net Amount": amount,
            "Invoice No": name[:3],
        },
    })


def _customer(store, name, **fields):
    body = {"Account Name": name, "Group": "South", "Balance": 10}
    body.update(fields)
    store.upsert_row({"type": "customer", "uk": name, "fields": body})


def _contact(c, name, when):
    created = c.post("/api/collection/contacts", json={
        "customer_name": name,
        "contacted_on": "2026-09-01",
        "channel": "phone",
        "note": "Called",
        "next_step": "Call again",
        "next_follow_up": when,
    })
    assert created.status_code == 200, created.text
    return created.json()


def test_salesperson_sees_only_assigned_reps_and_cannot_open_another_queue():
    c = client()
    store = get_store()
    _sale(store, "Northwind", "Asha")
    _sale(store, "Harbor", "Rita")
    _customer(store, "Northwind")
    _customer(store, "Harbor")
    _contact(c, "Northwind", "2026-09-01")
    _contact(c, "Harbor", "2026-09-01")
    assert c.post("/api/users", json={"username": "asha", "password": "asha12345", "role": "Sales"}).status_code == 200
    assert c.post("/api/users", json={"username": "rita", "password": "rita12345", "role": "Sales"}).status_code == 200
    assert c.patch("/api/users/asha", json={"sales_reps": ["Asha"]}).status_code == 200
    assert c.patch("/api/users/rita", json={"sales_reps": ["Rita"]}).status_code == 200

    asha = login("asha", "asha12345")
    own = asha.get("/api/worklist")
    assert own.status_code == 200, own.text
    names = [row["customer"] for row in own.json()["rows"]]
    assert "Northwind" in names
    assert "Harbor" not in names
    refused = asha.get("/api/worklist?staff=rita")
    assert refused.status_code == 403

    admin = c.get("/api/worklist?staff=asha")
    assert admin.status_code == 200, admin.text
    assert [row["customer"] for row in admin.json()["rows"]] == ["Northwind"]
    everyone = c.get("/api/worklist")
    assert "Harbor" in [row["customer"] for row in everyone.json()["rows"]]


def test_matching_follow_up_and_action_are_one_row():
    c = client()
    store = get_store()
    _sale(store, "Northwind", "Asha")
    _customer(store, "Northwind")
    _contact(c, "Northwind", "2026-09-01")
    created = c.post("/api/actions", json={
        "action_type": "collection",
        "subject_kind": "customer",
        "subject_name": "Northwind",
        "proposal": "Collect from Northwind",
        "owner": "admin",
        "due_date": "2026-10-01",
        "report_date": "2026-10-03",
    })
    assert created.status_code == 200, created.text
    body = c.get("/api/worklist")
    assert body.status_code == 200, body.text
    matched = [row for row in body.json()["rows"] if row["customer"] == "Northwind" and row["kind"] == "follow_up"]
    assert len(matched) == 1
    assert matched[0]["action_id"] == created.json()["id"]
    assert matched[0]["evidence"]["name"] == "Northwind"
    assert matched[0]["data_date"]


def test_done_work_and_a_future_follow_up_leave_the_queue_and_stay_in_history():
    c = client()
    store = get_store()
    _sale(store, "Later", "Asha")
    _sale(store, "Finished", "Asha")
    _customer(store, "Later")
    _customer(store, "Finished")
    later = _contact(c, "Later", "2026-12-01")
    created = c.post("/api/actions", json={
        "action_type": "collection",
        "subject_kind": "customer",
        "subject_name": "Finished",
        "proposal": "Collect from Finished",
        "owner": "admin",
        "due_date": "2026-10-01",
    })
    assert created.status_code == 200, created.text
    done = c.post("/api/actions/%s/status" % created.json()["id"], json={"status": "done"})
    assert done.status_code == 200, done.text
    rows = c.get("/api/worklist").json()["rows"]
    assert "Later" not in [row["customer"] for row in rows]
    assert "Finished" not in [row["customer"] for row in rows]
    history = c.get("/api/collection?customer=Later")
    assert history.status_code == 200
    assert any(row["id"] == later["id"] for row in history.json()["contacts"])
    actions = c.get("/api/actions").json()["actions"]
    assert any(row["id"] == created.json()["id"] and row["status"] == "done" for row in actions)


def test_pending_promise_is_not_marked_missed_and_blocks_name_the_next_step():
    c = client()
    store = get_store()
    _sale(store, "Pending", "Asha")
    _customer(store, "Pending")
    promised = c.post("/api/collection/promises", json={
        "customer_name": "Pending",
        "amount": 40,
        "promised_on": "2026-09-01",
    })
    assert promised.status_code == 200, promised.text
    _sale(store, "Blocked", "Asha")
    _customer(store, "Blocked", Blacklisted=True)
    _contact(c, "Blocked", "2026-09-01")
    store.upsert_row({
        "type": "items",
        "uk": "w1",
        "fields": {
            "Date": "2026-01-01", "Item Name": "Widget", "Qty": 5, "Rate": 4,
            "Party Name": "Repeat", "Sales Rep": "Asha",
        },
    })
    store.upsert_row({
        "type": "items",
        "uk": "w2",
        "fields": {
            "Date": "2026-01-11", "Item Name": "Widget", "Qty": 5, "Rate": 4,
            "Party Name": "Repeat", "Sales Rep": "Asha",
        },
    })
    _sale(store, "Repeat", "Asha", "2026-01-11", 20)
    _customer(store, "Repeat", Balance=0)
    store.upsert_row({
        "type": "stock",
        "uk": "Widget",
        "effective_date": "2026-10-03",
        "fields": {"Item Name": "Widget", "Qty": 1, "P.Price": 4, "EffectiveDate": "2026-10-03"},
    })
    body = c.get("/api/worklist")
    assert body.status_code == 200, body.text
    rows = body.json()["rows"]
    pending = next(row for row in rows if row["customer"] == "Pending")
    assert pending["kind"] == "pending_refresh"
    assert "pending a refresh" in pending["reason"]
    assert pending["kind"] != "missed_promise"
    blocked = next(row for row in rows if row["customer"] == "Blocked")
    assert blocked["blocked"] is True
    assert blocked["block"] == "credit"
    assert blocked["next_step"].startswith("Collect before the next order.")
    assert blocked["data_date"]
    repeat = next(row for row in rows if row["customer"] == "Repeat" and row["kind"] == "repurchase")
    assert repeat["blocked"] is True
    assert repeat["block"] == "stock"
    assert repeat["next_step"] == "Wait for stock."
    assert repeat["data_date"] == "2026-10-03"
    assert repeat["value_kind"] == "observed"
    assert "Blocked credit" in body.json()["order_rule"]
