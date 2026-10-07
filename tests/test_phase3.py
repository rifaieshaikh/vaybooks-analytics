"""Phase 3 actions, outcomes, reorder budget, and one weekly run."""

import os

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient

from server.actions import suggestions
from server.collection import reminder_context
from server.customers import customer_pdf
from server.items360 import save_holding
from server.main import app
from server.phase2 import build_bundle
from server.reorder import build_reorder
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
    assert round_pack(0, 4, 10) == 0
    kept, spent, deferred = apply_budget(
        [
            {"name": "A", "qty": 8, "unit_cost": 10},
            {"name": "B", "qty": 10, "unit_cost": 20},
        ],
        100,
    )
    assert [row["name"] for row in kept] == ["A"]
    assert spent == 80
    assert deferred[0]["name"] == "B"
    assert deferred[0]["defer_reason"] == "Would pass the budget"
    uncosted, unspent, left_out = apply_budget(
        [
            {"name": "Open", "qty": 4, "unit_cost": None},
            {"name": "Priced", "qty": 2, "unit_cost": 5},
        ],
        100,
    )
    assert [row["name"] for row in uncosted] == ["Priced"]
    assert unspent == 10
    assert left_out[0]["defer_reason"] == "Missing purchase cost"
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


def _promise(c, **extra):
    body = {
        "customer_name": "Acme",
        "amount": 100,
        "promised_on": "2027-01-15",
        "invoice_refs": ["INV-1"],
    }
    body.update(extra)
    created = c.post("/api/collection/promises", json=body)
    assert created.status_code == 200, created.text
    return created.json()


def _receipt(uk, amount, invoice="", date="2026-10-05", name="Acme"):
    store = get_store()
    fields = {"Date": date, "Account Name": name, "Amount": amount}
    if invoice:
        fields["Invoice No"] = invoice
    store.upsert_row({"type": "receipt", "uk": uk, "fields": fields})


def test_partial_payment_reduces_the_promise_and_leaves_the_action_open():
    c = client()
    action = c.post("/api/actions", json={
        "action_type": "collection",
        "subject_kind": "customer",
        "subject_name": "Acme",
        "proposal": "Collect from Acme",
        "owner": "admin",
        "due_date": "2026-10-10",
        "amount": 100,
        "assigned_at": "2026-10-03",
    })
    assert action.status_code == 200, action.text
    promise = _promise(c, action_id=action.json()["id"], amount=100, invoice_refs=["INV-1"])
    _receipt("r-partial", 40, invoice="INV-1")
    listed = c.get("/api/collection", params={"customer": "Acme"}).json()
    saved = listed["promises"][0]
    assert saved["id"] == promise["id"]
    assert saved["remaining"] == 60
    assert saved["payment_status"] == "partial"
    assert saved["allocations"][0]["basis"] == "source_confirmed"
    again = c.get("/api/actions").json()["actions"][0]
    assert again["status"] == "open"
    assert again["collection"]["remaining"] == 60
    done = c.post("/api/actions/%s/status" % action.json()["id"], json={"status": "done"})
    assert done.json()["status"] == "done"
    after = c.get("/api/collection", params={"customer": "Acme"}).json()["promises"][0]
    assert after["remaining"] == 60
    context = reminder_context(get_store(), "Acme")
    assert context["promises"][0]["remaining"] == 60
    assert context["promises"][0]["promised_on"] == "2027-01-15"
    reminder = customer_pdf(
        {"name": "Acme", "due": 60, "as_of_label": "7 Oct 2026", "collection_reminder": context},
        view="reminder",
    )
    statement = customer_pdf({"name": "Acme", "due": 60, "as_of_label": "7 Oct 2026"}, view="customer")
    assert reminder.startswith(b"%PDF")
    assert len(reminder) > len(statement)


def test_one_receipt_cannot_fill_two_promises():
    c = client()
    first = _promise(c, amount=80, invoice_refs=[], promised_on="2027-02-01")
    second = _promise(c, amount=80, invoice_refs=[], promised_on="2027-03-01")
    _receipt("r-shared", 100, invoice="")
    applied = c.post("/api/collection/allocations", json={
        "promise_id": first["id"],
        "source_uk": "r-shared",
    })
    assert applied.status_code == 200, applied.text
    assert applied.json()["remaining"] == 0
    assert applied.json()["allocations"][0]["basis"] == "confirmed_inferred"
    over = c.post("/api/collection/allocations", json={
        "promise_id": second["id"],
        "source_uk": "r-shared",
        "amount": 80,
    })
    assert over.status_code == 400
    capped = c.post("/api/collection/allocations", json={
        "promise_id": second["id"],
        "source_uk": "r-shared",
    })
    assert capped.status_code == 200, capped.text
    assert capped.json()["allocated"] == 20
    assert capped.json()["remaining"] == 60
    both = c.get("/api/collection", params={"customer": "Acme"}).json()["promises"]
    assert round(sum(row["allocated"] for row in both), 2) == 100


def test_named_receipt_matches_and_unnamed_receipt_waits_for_confirmation():
    c = client()
    named = _promise(c, amount=50, invoice_refs=["INV-9"])
    _receipt("r-named", 50, invoice="INV-9")
    _receipt("r-open", 25, invoice="")
    payload = c.get("/api/collection", params={"customer": "Acme"}).json()
    row = payload["promises"][0]
    assert row["id"] == named["id"]
    assert row["remaining"] == 0
    assert row["allocations"][0]["basis"] == "source_confirmed"
    assert row["allocations"][0]["basis_label"] == "Source-confirmed"
    assert row["suggestions"] == []
    other = _promise(c, amount=25, invoice_refs=[], promised_on="2027-04-01")
    waiting = c.get("/api/collection", params={"customer": "Acme"}).json()
    plain = next(item for item in waiting["promises"] if item["id"] == other["id"])
    assert plain["allocated"] == 0
    assert plain["suggestions"][0]["source_uk"] == "r-open"


def test_credit_note_reduces_a_linked_promise():
    c = client()
    _promise(c, amount=80, invoice_refs=["INV-2"])
    get_store().upsert_row({
        "type": "credit_note",
        "uk": "cn-1",
        "fields": {"Date": "2026-10-06", "Account Name": "Acme", "Net Amount": 30, "Invoice No": "INV-2"},
    })
    row = c.get("/api/collection", params={"customer": "Acme"}).json()["promises"][0]
    assert row["remaining"] == 50
    assert row["allocations"][0]["source_type"] == "credit_note"
    assert row["allocations"][0]["basis_label"] == "Credit note"


def test_corrected_import_voids_or_clamps_allocations():
    c = client()
    _promise(c, amount=100, invoice_refs=["INV-3"], promised_on="2027-05-01")
    _receipt("r-edit", 100, invoice="INV-3")
    first = c.get("/api/collection", params={"customer": "Acme"}).json()["promises"][0]
    assert first["remaining"] == 0
    _receipt("r-edit", 40, invoice="INV-3")
    clamped = c.get("/api/collection", params={"customer": "Acme"}).json()["promises"][0]
    assert clamped["remaining"] == 60
    assert clamped["allocations"][0]["amount"] == 40
    assert clamped["allocations"][0]["clamped_by"] == "system"
    assert clamped["allocations"][0]["clamped_at"]
    get_store().delete_row("receipt", "r-edit")
    removed = c.get("/api/collection", params={"customer": "Acme"}).json()["promises"][0]
    assert removed["remaining"] == 100
    assert removed["payment_status"] == "open"
    assert removed["allocations"][0]["voided_by"] == "system"
    assert removed["allocations"][0]["voided_at"]


def test_missed_promise_requires_current_receipt_coverage():
    c = client()
    pending = _promise(c, amount=40, invoice_refs=[], promised_on="2020-01-01")
    row = c.get("/api/collection", params={"customer": "Acme"}).json()["promises"][0]
    assert row["id"] == pending["id"]
    assert row["payment_status"] == "pending_refresh"
    assert row["message"] == "Payment confirmation is pending a refresh."
    queues = c.get("/api/collection/queues").json()
    assert queues["pending_refresh"][0]["id"] == pending["id"]
    assert queues["missed_promises"] == []
    get_store().insert_upload({"type": "stock", "filename": "stock.xlsx", "dry_run": False})
    still = c.get("/api/collection", params={"customer": "Acme"}).json()["promises"][0]
    assert still["payment_status"] == "pending_refresh"
    get_store().insert_import_job({
        "status": "succeeded",
        "dry_run": False,
        "types": {"receipt": {"added": 0}},
    })
    missed = c.get("/api/collection", params={"customer": "Acme"}).json()["promises"][0]
    assert missed["payment_status"] == "missed"
    assert c.get("/api/collection/queues").json()["missed_promises"][0]["id"] == pending["id"]


def test_existing_action_stays_readable_and_follow_up_edits_are_audited():
    c = client()
    created = c.post("/api/actions", json={
        "action_type": "collection",
        "subject_name": "Acme",
        "proposal": "Collect from Acme",
        "owner": "admin",
        "due_date": "2026-10-10",
        "amount": 20,
    })
    assert created.status_code == 200, created.text
    listed = c.get("/api/actions").json()["actions"][0]
    assert listed["status"] == "open"
    assert listed["collection"]["promise_count"] == 0
    stored = get_store().rows_of_type("action")[0]["fields"]
    assert "collection" not in stored
    assert "payment_status" not in stored
    contact = c.post("/api/collection/contacts", json={
        "customer_name": "Acme",
        "contacted_on": "2026-10-06",
        "channel": "phone",
        "note": "Asked for Friday",
        "next_step": "Call again",
        "next_follow_up": "2020-01-02",
    })
    assert contact.status_code == 200, contact.text
    body = contact.json()
    assert body["created_by"] == "admin"
    assert body["created_at"]
    edited = c.patch("/api/collection/contacts/" + body["id"], json={"note": "Asked for Monday"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["note"] == "Asked for Monday"
    assert edited.json()["updated_by"] == "admin"
    assert edited.json()["updated_at"]
    assert edited.json()["created_at"] == body["created_at"]
    dispute = c.post("/api/collection/disputes", json={
        "customer_name": "Acme",
        "note": "Price difference on INV-1",
    })
    assert dispute.status_code == 200, dispute.text
    assert dispute.json()["status"] == "open"
    resolved = c.patch("/api/collection/disputes/" + dispute.json()["id"], json={"status": "resolved"})
    assert resolved.status_code == 200
    assert resolved.json()["updated_by"] == "admin"
    due = c.get("/api/collection/queues").json()["due_follow_ups"]
    assert due[0]["id"] == body["id"]
    c.post("/api/users", json={"username": "look", "password": "look12345", "role": "Viewer"})
    viewer = TestClient(app)
    assert viewer.post("/api/auth/login", json={"username": "look", "password": "look12345"}).status_code == 200
    forbidden = viewer.post("/api/collection/contacts", json={
        "customer_name": "Acme",
        "contacted_on": "2026-10-06",
        "channel": "phone",
        "note": "No",
    })
    assert forbidden.status_code == 403
    role = c.post("/api/roles", json={"name": "Clerk", "permissions": ["sales.view"]})
    assert role.status_code == 200, role.text
    assert c.post("/api/users", json={"username": "clerk", "password": "clerk12345", "role": "Clerk"}).status_code == 200
    clerk = TestClient(app)
    assert clerk.post("/api/auth/login", json={"username": "clerk", "password": "clerk12345"}).status_code == 200
    assert clerk.get("/api/collection/queues").status_code == 403
    assert clerk.get("/api/collection", params={"customer": "Acme"}).status_code == 403
    assert c.post("/api/roles", json={"name": "Reader", "permissions": ["customer.view"]}).status_code == 200
    assert c.post("/api/users", json={"username": "reader", "password": "reader12345", "role": "Reader"}).status_code == 200
    reader = TestClient(app)
    assert reader.post("/api/auth/login", json={"username": "reader", "password": "reader12345"}).status_code == 200
    assert reader.get("/api/collection", params={"customer": "Acme"}).status_code == 200
    assert reader.get("/api/collection/queues").status_code == 403
    assert reader.post("/api/collection/promises", json={
        "customer_name": "Acme",
        "amount": 10,
        "promised_on": "2027-01-01",
    }).status_code == 403


def test_reorder_uses_the_item_buy_quantity():
    c = client()
    store = get_store()
    store.insert_run({"status": "succeeded", "report_date": "2026-10-03", "manifest": {}})
    for name, qty, price in (("Widget", 8, 4), ("Bolt", 100, 2), ("Nail", 1, 3)):
        store.upsert_row({
            "type": "stock",
            "uk": name,
            "effective_date": "2026-10-03",
            "fields": {"Item Name": name, "Qty": qty, "P.Price": price},
        })
    save_holding(store, "Widget", min_hold=20, fill_to=50, lead_days=7)
    save_holding(store, "Nail", min_hold=20, fill_to=50, lead_days=7, discontinued=True)
    item = c.get("/api/items/Widget").json()
    listed = c.get("/api/reorder").json()
    assert listed["status"] == "eligible"
    widget = next(row for row in listed["order"] if row["name"] == "Widget")
    assert widget["suggested_qty"] == item["buy_qty"]
    assert widget["qty"] == item["buy_qty"]
    assert widget["manual"] is False
    assert "Nail" not in {row["name"] for row in listed["order"]}
    assert "Bolt" not in {row["name"] for row in listed["order"]}
    bundle = build_bundle(store, "2026-10-03")
    stock_row = next(row for row in bundle["stock"]["rows"] if row["name"] == "Widget")
    assert stock_row["buy_qty"] == item["buy_qty"]
    purchase = next(row for row in suggestions(bundle) if row["action_type"] == "purchase")
    assert purchase["subject_name"] == "Widget"
    assert purchase["amount"] == item["buy_qty"]

    packed = c.put("/api/reorder", json={
        "budget": None,
        "lines": [{
            "name": "Widget",
            "manual": False,
            "pack_size": 4,
            "minimum": 0,
            "lead_days": 7,
            "unit_cost": 4,
        }],
    })
    assert packed.status_code == 200, packed.text
    again = c.get("/api/reorder").json()
    widget = next(row for row in again["order"] if row["name"] == "Widget")
    assert widget["suggested_qty"] == item["buy_qty"]
    assert widget["qty"] == 44
    assert widget["pack_added"] == 2
    assert widget["pack_reason"]

    edited = c.put("/api/reorder", json={
        "budget": None,
        "lines": [{
            "name": "Widget",
            "qty": 10,
            "manual": True,
            "basis_qty": item["buy_qty"],
            "pack_size": 1,
            "minimum": 0,
            "lead_days": 7,
            "unit_cost": 4,
        }],
    })
    assert edited.status_code == 200, edited.text
    save_holding(store, "Widget", min_hold=20, fill_to=60, lead_days=7)
    reviewed = c.get("/api/reorder").json()
    widget = next(row for row in reviewed["order"] if row["name"] == "Widget")
    assert widget["qty"] == 10
    assert widget["suggested_qty"] == c.get("/api/items/Widget").json()["buy_qty"]
    assert widget["needs_review"] is True

    rejected = c.put("/api/reorder", json={
        "lines": [{"name": "Widget", "qty": -1, "pack_size": 1, "unit_cost": 4}],
    })
    assert rejected.status_code == 400


def test_zero_requirement_and_missing_cost_stay_out_of_the_budget():
    idle = build_reorder(
        [{
            "name": "Idle",
            "buy_qty": 0,
            "discontinued": False,
            "unit_cost": 5,
            "reason": "No purchase needed right now.",
            "lead_days": 0,
            "pace": 0,
            "pace_days": 0,
            "fill_to": 10,
            "on_hand": 10,
            "buy_by": "",
        }],
        {"budget": 100, "lines": [{"name": "Idle", "minimum": 12, "pack_size": 4}]},
    )
    assert idle["lines"] == []
    built = build_reorder(
        [
            {
                "name": "Bare",
                "buy_qty": 4,
                "unit_cost": None,
                "buy_by": "2026-10-01",
                "discontinued": False,
                "reason": "Buy 4 now.",
                "lead_days": 1,
                "pace": 1,
                "pace_days": 90,
                "fill_to": 4,
                "on_hand": 0,
            },
            {
                "name": "Priced",
                "buy_qty": 2,
                "unit_cost": 5,
                "buy_by": "2026-10-02",
                "discontinued": False,
                "reason": "Buy 2 now.",
                "lead_days": 1,
                "pace": 1,
                "pace_days": 90,
                "fill_to": 2,
                "on_hand": 0,
            },
        ],
        {"budget": 100, "lines": []},
    )
    assert [row["name"] for row in built["lines"]] == ["Priced"]
    assert built["spent"] == 10
    bare = next(row for row in built["deferred"] if row["name"] == "Bare")
    assert bare["defer_reason"] == "Missing purchase cost"


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
