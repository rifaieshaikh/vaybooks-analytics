"""Phase 5 recovery targets stay inside the debt they were assigned to."""

from decimal import Decimal

from server.store import get_store
from tests.test_phase3 import _promise, _receipt, client
from vay.recovery import (
    assign_targets,
    attribute_receipts,
    cap_commitments,
    owner_outcomes,
    planned_inflows,
    promise_outcome,
    recovery_pools,
)


def test_pools_keep_disputed_unknown_and_restricted_out_of_actionable():
    pools = recovery_pools([
        {"id": "a", "remaining": "100", "overdue": True},
        {"id": "b", "remaining": "40", "overdue": True, "disputed": True},
        {"id": "c", "remaining": "15", "unknown_age": True},
        {"id": "d", "remaining": "10", "restricted": True},
    ])
    assert pools["overdue"] == Decimal("100")
    assert pools["actionable"] == Decimal("100")
    assert pools["disputed"] == Decimal("40")
    assert pools["unknown_age"] == Decimal("15")
    assert pools["restricted_credit"] == Decimal("10")
    assert pools["actionable"] != pools["overdue"] + pools["disputed"]


def test_a_receipt_is_spent_once_and_a_credit_note_is_not_kept_cash():
    shared = attribute_receipts(
        [
            {"id": "r1", "amount": "40", "cash": True},
            {"id": "cn", "amount": "30", "cash": False},
        ],
        [
            {"id": "promise", "receipt_id": "r1", "amount": "40", "cash_only": True},
            {"id": "again", "receipt_id": "r1", "amount": "40", "cash_only": True},
            {"id": "note", "receipt_id": "cn", "amount": "30", "cash_only": True},
        ],
    )
    assert shared["actual_cash"] == Decimal("40")
    assert shared["target_linked_cash"] == Decimal("40")
    assert shared["claims"][1]["amount"] == Decimal("0")
    assert shared["claims"][2]["amount"] == Decimal("0")
    reversed_receipt = attribute_receipts(
        [{"id": "r1", "amount": "0", "cash": True}],
        [{"id": "promise", "receipt_id": "r1", "amount": "40", "cash_only": True}],
    )
    assert reversed_receipt["actual_cash"] == Decimal("0")
    assert reversed_receipt["target_linked_cash"] == Decimal("0")
    kept = promise_outcome("80", "40", "0", "2026-03-01", "2026-01-02", "2026-02-01", "2026-02-01")
    assert kept["payment_status"] == "partial"
    missed = promise_outcome("80", "40", "0", "2026-01-01", "2026-01-02", "2026-02-01", "2026-02-01")
    assert missed["payment_status"] == "missed"
    note = promise_outcome("30", "0", "30", "2026-01-01", "", "2026-02-01", "2026-02-01")
    assert note["payment_status"] == "non_cash"
    assert note["cash_kept"] is False
    late = promise_outcome("40", "40", "0", "2026-01-01", "2026-01-05", "2026-02-01", "2026-02-01")
    assert late["payment_status"] == "kept_late"
    waiting = promise_outcome("40", "0", "0", "2020-01-01", "", "2026-02-01", "")
    assert waiting["payment_status"] == "awaiting_data"


def test_revised_and_reassigned_targets_do_not_double_count():
    first = {"id": "t1", "assigned_amount": "100", "baseline_amount": "100", "status": "superseded", "owner": "A", "created_at": "1"}
    second = {"id": "t2", "assigned_amount": "60", "baseline_amount": "60", "status": "open", "owner": "B", "created_at": "2"}
    assigned = assign_targets([first, second], "100")
    assert assigned["assigned"] == Decimal("60")
    owners = owner_outcomes([first, second])
    by_owner = {row["owner"]: row for row in owners}
    assert by_owner["A"]["open_assigned"] == Decimal("0")
    assert by_owner["A"]["superseded"] == Decimal("100")
    assert by_owner["B"]["baseline"] == Decimal("60")
    inflows = planned_inflows(
        [{"customer_name": "Acme", "payment_status": "partial", "remaining": "40"}],
        [{"customer_name": "Acme", "status": "open", "assigned_amount": "60", "remaining": "60"}],
    )
    assert inflows["amount"] == Decimal("60")
    capped = cap_commitments(
        [
            {"id": "p1", "payment_status": "open", "remaining": "80", "promised_on": "2026-01-01"},
            {"id": "p2", "payment_status": "open", "remaining": "80", "promised_on": "2026-02-01"},
        ],
        "100",
    )
    assert capped["remaining_promises"] == Decimal("100")


def test_target_revision_reassignment_and_task_close_keep_cash_honest():
    c = client()
    debts = [
        {"id": "inv-1", "remaining": 100, "overdue": True},
        {"id": "inv-2", "remaining": 40, "disputed": True, "overdue": True},
    ]
    created = c.post("/api/collection/targets", json={
        "customer_name": "Acme",
        "owner": "admin",
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
        "assigned_amount": 100,
        "debts": debts,
        "next_step": "Call Acme",
    })
    assert created.status_code == 200, created.text
    target = created.json()
    assert target["baseline_amount"] == 100
    assert target["assigned_amount"] == 100
    moved = c.patch("/api/collection/targets/%s" % target["id"], json={"owner": "rita"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["owner"] == "rita"
    assert moved.json()["baseline_amount"] == 100
    revised = c.post("/api/collection/targets", json={
        "customer_name": "Acme",
        "owner": "rita",
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
        "assigned_amount": 60,
        "debts": debts,
        "supersedes": target["id"],
    })
    assert revised.status_code == 200, revised.text
    listed = c.get("/api/collection", params={"customer": "Acme"}).json()
    assert listed["pools"]["actionable"] == 100
    assert listed["pools"]["disputed"] == 40
    assert listed["assigned_targets"] == 60
    blocked = c.post("/api/collection/targets", json={
        "customer_name": "Acme",
        "owner": "rita",
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
        "assigned_amount": 50,
        "debts": debts,
    })
    assert blocked.status_code == 400
    promise = _promise(c, amount=100, invoice_refs=["INV-1"], promised_on="2026-10-20")
    _receipt("r-part", 40, invoice="INV-1")
    action = c.post("/api/actions", json={
        "action_type": "collection",
        "subject_name": "Acme",
        "proposal": "Collect from Acme",
        "owner": "admin",
        "due_date": "2026-10-20",
        "amount": 100,
    })
    done = c.post("/api/actions/%s/status" % action.json()["id"], json={"status": "done"})
    assert done.status_code == 200
    after = c.get("/api/collection", params={"customer": "Acme"}).json()
    saved = next(row for row in after["promises"] if row["id"] == promise["id"])
    assert saved["remaining"] == 60
    assert saved["payment_status"] == "partial"
    assert after["assigned_targets"] == 60
    open_target = next(row for row in after["targets"] if row["status"] == "open")
    assert open_target["remaining"] == 20
    assert open_target["baseline_amount"] == 60
    assert after["actual_cash"] == 40
    assert after["target_linked_cash"] == 40
    assert after["non_cash_resolutions"] == 0
    revised_promise = c.patch("/api/collection/promises/%s" % promise["id"], json={"amount": 50})
    assert revised_promise.status_code == 200, revised_promise.text
    held = c.get("/api/collection", params={"customer": "Acme"}).json()
    assert next(row for row in held["targets"] if row["status"] == "open")["remaining"] == 20
    assert held["actual_cash"] == 40


def test_credit_note_and_receipt_reversal_update_the_target_once():
    c = client()
    created = c.post("/api/collection/targets", json={
        "customer_name": "Acme",
        "owner": "admin",
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
        "assigned_amount": 100,
        "debts": [{"id": "INV-1", "remaining": 100, "overdue": True}],
    })
    assert created.status_code == 200, created.text
    _receipt("r-part", 40, invoice="INV-1")
    partial = c.get("/api/collection", params={"customer": "Acme"}).json()
    assert partial["targets"][0]["remaining"] == 60
    assert partial["actual_cash"] == 40
    assert partial["target_linked_cash"] == 40
    get_store().upsert_row({
        "type": "credit_note",
        "uk": "cn-1",
        "fields": {"Date": "2026-10-06", "Account Name": "Acme", "Net Amount": 30, "Invoice No": "INV-1"},
    })
    noted = c.get("/api/collection", params={"customer": "Acme"}).json()
    assert noted["targets"][0]["remaining"] == 30
    assert noted["actual_cash"] == 40
    assert noted["target_linked_cash"] == 40
    assert noted["non_cash_resolutions"] == 30
    assert noted["targets"][0]["baseline_amount"] == 100
    get_store().delete_row("receipt", "r-part")
    reversed_cash = c.get("/api/collection", params={"customer": "Acme"}).json()
    assert reversed_cash["actual_cash"] == 0
    assert reversed_cash["target_linked_cash"] == 0
    assert reversed_cash["targets"][0]["remaining"] == 70
    moved = c.patch("/api/collection/targets/%s" % created.json()["id"], json={"owner": "rita"})
    assert moved.status_code == 200, moved.text
    assert moved.json()["baseline_amount"] == 100
    after_move = c.get("/api/collection", params={"customer": "Acme"}).json()
    assert after_move["targets"][0]["owner"] == "rita"
    assert after_move["targets"][0]["remaining"] == 70
