"""Phase 3: derived results stay separate, and the previous settlement is only a comparison."""

from server.collection import ALLOCATION_TYPE
from server.ledger_persist import (
    LINK_TYPE,
    RESULT_TYPE,
    invalidate_ledger,
    publication,
    publish_ledger,
    save_confirmed_link,
    shadow_report,
    void_confirmed_link,
)
from server.opening_check import assess_store
from server.store import get_store
from server.tenant import bind_org


def _row(type_name, uk, fields, upload="u1"):
    return {
        "type": type_name,
        "uk": uk,
        "source_upload_id": upload,
        "fields": fields,
    }


def _books(store):
    store.upsert_row(_row("sales", "inv-1", {
        "Date": "2024-05-01", "Party Name": "Acme", "Net Amount": "100", "Invoice No": "INV-1",
    }))
    store.upsert_row(_row("receipt", "rct-1", {
        "Date": "2024-06-01", "Account Name": "Acme", "Amount": "40",
    }))
    store.upsert_row(_row("arr", "acme", {"Account Name": "Acme", "Balance": "100"}))


def test_publish_is_idempotent_and_a_later_source_replaces_only_derived_rows():
    store = get_store()
    _books(store)
    first = publish_ledger(store, "2026-03-31")
    assert first["reused"] is False
    assert first["customer_count"] == 1
    again = publish_ledger(store, "2026-03-31")
    assert again["reused"] is True
    assert len(store.rows_of_type(RESULT_TYPE)) == 1
    saved = store.rows_of_type(RESULT_TYPE)[0]["fields"]
    assert saved["derived"] is True
    assert saved["source_digest"] == first["source_digest"]
    assert saved["allocations"][0]["credit_id"] == "rct-1"
    assert saved["allocations"][0]["debit_id"] == "inv-1"
    assert saved["allocations"][0]["evidence"] == "inferred"

    store.upsert_row(_row("sales", "inv-2", {
        "Date": "2024-07-01", "Party Name": "Acme", "Net Amount": "10", "Invoice No": "INV-2",
    }, upload="u2"))
    stale = publication(store)
    assert stale["calculation_key"] == first["calculation_key"]
    refreshed = publish_ledger(store, "2026-03-31")
    assert refreshed["reused"] is False
    assert refreshed["calculation_key"] != first["calculation_key"]
    results = store.rows_of_type(RESULT_TYPE)
    assert len(results) == 1
    assert results[0]["fields"]["calculation_key"] == refreshed["calculation_key"]
    assert store.rows_of_type(ALLOCATION_TYPE) == []


def test_confirmed_link_is_not_a_promise_allocation_and_survives_replay():
    store = get_store()
    _books(store)
    link = save_confirmed_link(store, {
        "customer_id": "Acme",
        "credit_id": "rct-1",
        "debit_id": "inv-1",
        "amount": "40",
    }, "ada")
    assert link["evidence"] == "manually_confirmed"
    assert store.rows_of_type(ALLOCATION_TYPE) == []
    assert publication(store) == {}

    published = publish_ledger(store, "2026-03-31")
    result = store.rows_of_type(RESULT_TYPE)[0]["fields"]
    assert result["allocations"][0]["evidence"] == "manually_confirmed"
    assert result["calculation_key"] == published["calculation_key"]

    void_confirmed_link(store, link["id"], "ada")
    kept = store.find_row(LINK_TYPE, link["id"])
    assert kept["fields"]["voided_at"]
    replayed = publish_ledger(store, "2026-03-31")
    assert replayed["calculation_key"] != published["calculation_key"]
    after = store.rows_of_type(RESULT_TYPE)[0]["fields"]
    assert after["allocations"][0]["evidence"] == "inferred"
    assert store.find_row(LINK_TYPE, link["id"])["fields"]["voided_at"]
    assert store.rows_of_type(ALLOCATION_TYPE) == []


def test_shadow_explains_a_difference_without_treating_the_old_balance_as_correct():
    store = get_store()
    _books(store)
    assessment = assess_store(store, "2026-03-31")
    report = shadow_report(assessment, [{"name": "Acme", "due": 60}])
    assert report["legacy_is_oracle"] is False
    assert report["material_count"] == 1
    reasons = " ".join(report["material"][0]["reasons"])
    assert "comparison reading" in reasons
    assert "opening unknown" in reasons
    assert report["material"][0]["legacy_due"] == "60.00"


def test_invalidation_and_org_isolation_keep_the_other_publication():
    store = get_store()
    _books(store)
    first = publish_ledger(store, "2026-03-31")
    invalidate_ledger(store)
    assert publication(store) == {}
    assert store.rows_of_type(RESULT_TYPE)[0]["fields"]["calculation_key"] == first["calculation_key"]

    with bind_org("other"):
        other = publish_ledger(store, "2026-03-31")
        assert other["customer_count"] == 0
        assert publication(store)["calculation_key"] == other["calculation_key"]
    assert publication(store) == {}
    assert store.rows_of_type(RESULT_TYPE)[0]["fields"]["calculation_key"] == first["calculation_key"]
