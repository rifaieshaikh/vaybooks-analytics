"""Representative import, desktop license, and data-directory restore."""

import io
import os
import shutil
import time
from pathlib import Path

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient
from openpyxl import Workbook

from server.hosted import pack_enabled, set_entitlement
from server.main import app
from server.store import get_store, reset_store_for_tests

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def client():
    reset_store_for_tests()
    c = TestClient(app)
    logged = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert logged.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    return c


def xlsx_bytes(name, headers, rows):
    book = Workbook()
    sheet = book.active
    sheet.title = name
    sheet.append(headers)
    for row in rows:
        sheet.append(row)
    buf = io.BytesIO()
    book.save(buf)
    return buf.getvalue()


def upload(c, type_name, headers, rows, **data):
    payload = xlsx_bytes(type_name, headers, rows)
    return c.post(
        "/api/uploads",
        data={"type": type_name, **data},
        files={"file": ("%s.xlsx" % type_name, payload, MIME)},
    )


def test_representative_import_reconciles_and_a_repeat_does_not_duplicate():
    reset_store_for_tests()
    c = TestClient(app, raise_server_exceptions=False)
    logged = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert logged.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    started = time.perf_counter()
    rejected = c.post(
        "/api/uploads",
        data={"type": "sales"},
        files={"file": ("sales.xlsx", b"not a workbook", MIME)},
    )
    assert rejected.status_code >= 400
    assert get_store().rows_of_type("sales") == []
    sales = upload(
        c, "sales",
        ["Date", "Party Name", "Sales Rep", "Net Amount"],
        [["2026-10-01", "Harbour Traders", "Asha", 1000], ["2026-10-05", "Harbour Traders", "Asha", 500]],
        event_mode="skip",
    )
    assert sales.status_code == 200, sales.text
    assert sales.json()["types"]["sales"]["added"] == 2
    receipt = upload(
        c, "receipt",
        ["Date", "Account Name", "Sales Rep", "Amount"],
        [["2026-10-06", "Harbour Traders", "Asha", 400]],
    )
    assert receipt.status_code == 200, receipt.text
    outstanding = upload(
        c, "arr",
        ["Account Name", "Group", "Balance"],
        [["Harbour Traders", "Trade", 1100]],
        effective_date="2026-10-07",
    )
    assert outstanding.status_code == 200, outstanding.text
    run = c.post("/api/runs", json={"packs": {"core": True}, "report_date": "2026-10-07"})
    assert run.status_code == 202, run.text
    assert run.json()["status"] == "succeeded"
    elapsed = time.perf_counter() - started
    assert elapsed < 60
    print("REPRESENTATIVE_IMPORT_SECONDS %.3f" % elapsed)
    customers = c.get("/api/customers").json()["customers"]
    harbour = next(row for row in customers if row["name"] == "Harbour Traders")
    assert harbour["due"] == 1100
    again = upload(
        c, "sales",
        ["Date", "Party Name", "Sales Rep", "Net Amount"],
        [["2026-10-01", "Harbour Traders", "Asha", 1000], ["2026-10-05", "Harbour Traders", "Asha", 500]],
        event_mode="skip",
    )
    assert again.status_code == 200, again.text
    assert again.json()["types"]["sales"]["skipped"] == 2
    assert len(get_store().rows_of_type("sales")) == 2


def test_data_directory_copy_restores_the_folder(tmp_path):
    source = Path(tmp_path) / "Vay Reports"
    source.mkdir()
    (source / "marker.txt").write_text("customer-rows", encoding="utf-8")
    copy = Path(tmp_path) / "backup"
    shutil.copytree(source, copy)
    shutil.rmtree(source)
    assert not source.exists()
    shutil.copytree(copy, source)
    assert (source / "marker.txt").read_text(encoding="utf-8") == "customer-rows"


def test_hosted_pack_off_keeps_the_customer_and_the_same_permissions():
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "customer",
        "uk": "Harbour Traders",
        "fields": {"Account Name": "Harbour Traders", "Balance": 1100},
    })
    users_before = len(store.rows_of_type("user"))
    os.environ["VAY_HOSTED"] = "1"
    try:
        set_entitlement(store, "retail", False)
        assert pack_enabled(store, "retail") is False
        assert pack_enabled(store, "wholesale") is False
    finally:
        os.environ.pop("VAY_HOSTED", None)
    names = {row.get("fields", {}).get("Account Name") for row in store.rows_of_type("customer")}
    assert "Harbour Traders" in names
    assert len(store.rows_of_type("user")) == users_before
    assert c.get("/api/customers").status_code == 200
