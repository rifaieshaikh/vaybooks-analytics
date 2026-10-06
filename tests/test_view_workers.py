"""Worker sizing, parallel customer settlement, and in-step progress."""

import json
from datetime import datetime

from server.ar_balance import party_ledgers
from server.book import load_book
from server.customers import account_uk, customer_directory_rows, ensure_detail_settlements, get_customer
from server.groups360 import get_group
from server.jobs import _generate_progress
from server.store import MemoryStore
from server.view_workers import choose_workers, open_pool, settle_customers, worker_budget


def _gb(value):
    return int(value * 1024 * 1024 * 1024)


def test_worker_budget_follows_cpu_and_ram():
    assert worker_budget(500, 8, _gb(4.58)) == 4
    assert worker_budget(500, 2, _gb(16)) == 1
    assert worker_budget(500, 8, _gb(1)) == 1
    assert worker_budget(3, 16, _gb(64)) == 3


def test_choose_workers_uses_the_machine_and_the_override(monkeypatch):
    monkeypatch.setenv("VAY_STORE", "mongo")
    monkeypatch.delenv("VAY_360_WORKERS", raising=False)
    monkeypatch.setattr("server.view_workers._logical_cpus", lambda: 8)
    monkeypatch.setattr("server.view_workers._available_ram_bytes", lambda: _gb(4.58))
    assert choose_workers(500) == 4
    assert choose_workers(12) == 1
    monkeypatch.setattr("server.view_workers._available_ram_bytes", lambda: _gb(1))
    assert choose_workers(500) == 1
    monkeypatch.setenv("VAY_STORE", "memory")
    monkeypatch.setattr("server.view_workers._logical_cpus", lambda: 8)
    monkeypatch.setattr("server.view_workers._available_ram_bytes", lambda: _gb(32))
    assert choose_workers(500) == 1
    monkeypatch.setenv("VAY_360_WORKERS", "6")
    assert choose_workers(100) == 6


def _books_store():
    store = MemoryStore()
    store._force_as_of = datetime(2026, 10, 2, 12)
    store.insert_row({
        "type": "customer",
        "uk": "acme",
        "fields": {"Account Name": "Acme", "Group": "South", "Balance": 800},
    })
    store.insert_row({
        "type": "customer",
        "uk": "beta",
        "fields": {"Account Name": "Beta", "Group": "South", "Balance": 200},
    })
    store.insert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {
            "Date": datetime(2026, 9, 1, 12),
            "Party Name": "Acme",
            "Sales Rep": "Ravi",
            "Net Amount": 1000,
            "Invoice No": "INV-1",
        },
    })
    store.insert_row({
        "type": "sales",
        "uk": "s2",
        "fields": {
            "Date": datetime(2026, 8, 1, 12),
            "Party Name": "Beta",
            "Sales Rep": "Ravi",
            "Net Amount": 400,
            "Invoice No": "INV-2",
        },
    })
    store.insert_row({
        "type": "receipt",
        "uk": "r1",
        "fields": {
            "Date": datetime(2026, 9, 15, 12),
            "Account Name": "Acme",
            "Sales Rep": "Ravi",
            "Amount": 200,
            "Invoice No": "INV-1",
        },
    })
    return store


def _settlement_key(detail):
    return json.dumps(detail.get("settlements"), default=str, sort_keys=True)


def test_pool_matches_in_process_settlement():
    store = _books_store()
    book = load_book(store)
    direct = ensure_detail_settlements(store, get_customer(store, "acme"), book=book, force=False)
    directory = customer_directory_rows(store)
    ledgers = party_ledgers(store)
    with open_pool(2) as pool:
        pooled = settle_customers(
            store,
            book,
            directory["rows"],
            workers=2,
            ledgers=ledgers,
            tolerance=0.5,
            executor=pool,
        )
    assert "acme" in pooled
    assert pooled["acme"]["settlements"]["months"]
    assert _settlement_key(pooled["acme"]) == _settlement_key(direct)
    assert pooled["acme"]["collection_buckets"] == direct["collection_buckets"]


def test_group_sums_settled_customers_without_allocating_again(monkeypatch):
    store = _books_store()
    book = load_book(store)
    directory = customer_directory_rows(store)
    ledgers = party_ledgers(store)
    details = settle_customers(
        store,
        book,
        directory["rows"],
        workers=1,
        ledgers=ledgers,
        tolerance=0.5,
    )
    book["_settled_customers"] = details

    def boom(*_args, **_kwargs):
        raise AssertionError("group settlement allocated again")

    monkeypatch.setattr("server.groups360._allocate_open", boom)
    monkeypatch.setattr("server.groups360.allocate_collections", boom)
    got = get_group(store, account_uk("South"))
    assert got["due"] == sum(row["due"] for row in details.values())
    for key, value in (got.get("collection_buckets") or {}).items():
        assert value == sum((row.get("collection_buckets") or {}).get(key) or 0 for row in details.values())


def test_running_progress_keeps_a_new_fraction():
    store = MemoryStore()
    doc = store.insert_run({"status": "running", "report_date": "2026-10-02"})
    steps = [{"id": "360-customers", "title": "Customers 360", "group": "360 View", "state": "waiting"}]
    steps = _generate_progress(store, doc["_id"], steps, "360-customers", "Customers 360", "360 View", "running", 0)
    steps = _generate_progress(
        store, doc["_id"], steps, "360-customers", "Customers 360 · 2 of 4", "360 View", "running", 0.5,
    )
    saved = store.get_run(doc["_id"])["generate_progress"]
    assert saved["fraction"] == 0.5
    row = saved["steps"][0]
    assert row["state"] == "running"
    assert row["title"] == "Customers 360 · 2 of 4"
    assert row["fraction"] == 0.5
