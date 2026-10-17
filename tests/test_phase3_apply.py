"""Phase 3 screens read the shared ledger. A rollback keeps confirmed links."""

from server.backup import restore_org, snapshot_org
from server.customers import customer_directory_rows, get_customer
from server.jobs import enqueue_run, run_job
from server.ledger_apply import list_exceptions, rollback_ledger
from server.ledger_persist import LINK_TYPE, save_confirmed_link
from server.store import get_store


def _customer(store):
    store.upsert_row({
        "type": "customer",
        "uk": "acme",
        "fields": {"Account Name": "Acme", "Group": "South"},
    })
    store.upsert_row({
        "type": "sales",
        "uk": "inv-1",
        "source_upload_id": "u1",
        "fields": {
            "Date": "2024-05-01", "Party Name": "Acme", "Sales Rep": "Ravi",
            "Net Amount": "100", "Invoice No": "INV-1",
        },
    })
    store.upsert_row({
        "type": "receipt",
        "uk": "rct-1",
        "source_upload_id": "u1",
        "fields": {"Date": "2024-06-01", "Account Name": "Acme", "Amount": "40"},
    })
    store.upsert_row({
        "type": "arr",
        "uk": "acme",
        "fields": {"Account Name": "Acme", "Balance": "80"},
    })


def test_customer_directory_and_profile_share_the_ledger_balance():
    store = get_store()
    _customer(store)
    detail = get_customer(store, "Acme")
    assert detail["ledger_engine"] == "1"
    assert detail["result_scope"] == "operational"
    assert detail["balance_exact"] is False
    assert detail["due"] == 60.0
    assert detail["ledger_links"][0]["evidence"] == "inferred"
    assert detail["ledger_links"][0]["cash"] is True
    listed = customer_directory_rows(store)["rows"]
    row = next(item for item in listed if item["name"] == "Acme")
    assert row["due"] == detail["due"]
    assert row["ledger_engine"] == "1"


def test_rollback_keeps_a_confirmed_link_and_backup_restores_rows():
    store = get_store()
    _customer(store)
    link = save_confirmed_link(store, {
        "customer_id": "Acme",
        "credit_id": "rct-1",
        "debit_id": "inv-1",
        "amount": "40",
    }, "ada")
    taken = snapshot_org(store)
    later = save_confirmed_link(store, {
        "customer_id": "Acme",
        "credit_id": "rct-1",
        "debit_id": "inv-1",
        "amount": "10",
        "id": "later-link",
    }, "ada")
    rolled = rollback_ledger(store)
    assert rolled["ledger_engine"] == "legacy"
    assert rolled["confirmed_links"] == 2
    assert store.find_row(LINK_TYPE, later["id"])
    detail = get_customer(store, "Acme")
    assert detail.get("ledger_links") is None
    assert detail["due"] == 80

    restore_org(store, taken)
    assert store.find_row(LINK_TYPE, link["id"])
    assert store.find_row(LINK_TYPE, later["id"]) is None


def test_exception_queue_names_the_missing_opening_and_a_new_run_keeps_the_old_one():
    store = get_store()
    _customer(store)
    queue = list_exceptions(store, "2026-03-31")
    assert any(row["code"] == "missing_opening" and row["customer_id"] == "acme" for row in queue["rows"])
    assert queue["rows"][0]["action"]
    first_id, err = enqueue_run(store, {"core": True}, "2026-03-31", reports=["phase2_quality"])
    assert err == ""
    run_job(store, first_id)
    first = store.get_run(first_id)
    second_id, err = enqueue_run(store, {"core": True}, "2026-04-30", reports=["phase2_quality"])
    assert err == ""
    assert store.get_run(first_id)["opening_assessment"] == first["opening_assessment"]
    assert store.get_run(second_id)["opening_assessment"]["as_of"] == "2026-04-30"
