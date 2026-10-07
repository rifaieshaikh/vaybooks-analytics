"""IMP-03: plain sales preset, repeat imports, header drift, controls, refresh."""

import io
import json
import os

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient
from openpyxl import Workbook

from server.main import app
from server.mappers import PLAIN_SALES_SHAPE
from server.store import get_store, reset_store_for_tests

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def client():
    reset_store_for_tests()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    c.post("/api/settings/settlement", json={"mode": "oldest", "setup_complete": True})
    return c


def xlsx_bytes(sheets):
    wb = Workbook()
    first = True
    for name, headers, rows in sheets:
        ws = wb.active if first else wb.create_sheet(name)
        if first:
            ws.title = name
            first = False
        ws.append(headers)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(c, name, headers, rows, **data):
    payload = xlsx_bytes([(name, headers, rows)])
    return c.post(
        "/api/uploads",
        data=data,
        files={"file": ("%s.xlsx" % name, payload, MIME)},
    )


def _sales_rows():
    return list(get_store().rows_of_type("sales"))


def test_plain_sales_is_the_only_shipped_preset_and_imports_its_shape():
    c = client()
    listed = c.get("/api/mappers/presets")
    assert listed.status_code == 200
    presets = listed.json()["presets"]
    assert [row["id"] for row in presets] == ["plain_sales"]
    applied = c.post("/api/mappers/sales/preset/plain_sales")
    assert applied.status_code == 200, applied.text
    shape = applied.json()["shape"]
    assert shape["source_columns"] == PLAIN_SALES_SHAPE["source_columns"]
    assert shape["date_column"] == "Invoice Date"
    assert shape["snapshot_date"] is False
    assert shape["canonical"]["Amount"] == "Net Amount"
    uploaded = _upload(
        c, "sales",
        ["Invoice Date", "Customer", "Rep", "Amount"],
        [["2026-10-02", "Northwind", "Asha", 80]],
        type="sales",
    )
    assert uploaded.status_code == 200, uploaded.text
    assert uploaded.json()["types"]["sales"]["added"] == 1
    fields = _sales_rows()[0]["fields"]
    assert fields["Date"]
    assert fields["Party Name"] == "Northwind"
    assert fields["Sales Rep"] == "Asha"
    assert float(fields["Net Amount"]) == 80
    check = c.get("/api/analytics/onboarding?report_date=2026-10-03")
    sales = next(row for row in check.json()["sources"] if row["type"] == "sales")
    assert sales["required_fields"] == ["Date", "Party Name", "Sales Rep", "Net Amount"]
    assert sales["date_kind"] == "transaction"
    assert sales["date_ok"] is True
    assert "Date column" in sales["date_note"]


def test_skip_does_not_double_count_and_update_replace_keep_upload_records():
    c = client()
    c.put("/api/mappers/sales", json={
        "column_map": {},
        "unique_key": ["Date", "Party Name", "Sales Rep"],
    })
    headers = ["Date", "Party Name", "Sales Rep", "Net Amount"]
    first = _upload(c, "sales", headers, [["2026-10-02", "Northwind", "Asha", 100]], type="sales", event_mode="skip")
    assert first.status_code == 200, first.text
    again = _upload(c, "sales", headers, [["2026-10-02", "Northwind", "Asha", 100]], type="sales", event_mode="skip")
    assert again.status_code == 200, again.text
    assert again.json()["types"]["sales"]["skipped"] == 1
    assert len(_sales_rows()) == 1
    assert float(_sales_rows()[0]["fields"]["Net Amount"]) == 100
    updated = _upload(c, "sales", headers, [["2026-10-02", "Northwind", "Asha", 40]], type="sales", event_mode="update")
    assert updated.status_code == 200, updated.text
    assert float(_sales_rows()[0]["fields"]["Net Amount"]) == 40
    replaced = _upload(
        c, "sales", headers,
        [["2026-10-02", "Harbor", "Asha", 15]],
        type="sales",
        event_mode="replace_period",
    )
    assert replaced.status_code == 200, replaced.text
    names = sorted(row["fields"]["Party Name"] for row in _sales_rows())
    assert names == ["Harbor"]
    uploads = [row for row in get_store().list_uploads() if not row.get("dry_run")]
    assert len(uploads) == 4
    assert all(row.get("finished_at") for row in uploads)
    remembered = c.get("/api/mappers/sales")
    assert remembered.json()["event_mode"] == "replace_period"
    preview = c.post(
        "/api/uploads/preview",
        files={"file": ("sales.xlsx", xlsx_bytes([("sales", headers, [["2026-10-02", "Harbor", "Asha", 15]])]), MIME)},
    )
    assert preview.json()["sheets"][0]["event_mode"] == "replace_period"


def test_changed_headers_stop_until_the_mapping_is_confirmed():
    c = client()
    c.put("/api/mappers/sales", json={
        "column_map": {
            "Date": "Date",
            "Party Name": "Party Name",
            "Sales Rep": "Sales Rep",
            "Net Amount": "Net Amount",
        },
        "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    })
    headers = ["Invoice Date", "Customer", "Rep", "Amount"]
    rows = [["2026-10-02", "Northwind", "Asha", 80]]
    preview = c.post(
        "/api/uploads/preview",
        files={"file": ("sales.xlsx", xlsx_bytes([("sales", headers, rows)]), MIME)},
    )
    changes = preview.json()["sheets"][0]["header_changes"]
    assert changes["changed"] is True
    assert "Date" in changes["removed"]
    assert "Invoice Date" in changes["added"]
    blocked = _upload(c, "sales", headers, rows, type="sales")
    assert blocked.status_code == 200
    assert "Headers changed" in blocked.json()["types"]["sales"]["error"]
    assert _sales_rows() == []
    maps = json.dumps({
        "sales": {
            "column_map": dict(PLAIN_SALES_SHAPE["canonical"]),
            "unique_key": list(PLAIN_SALES_SHAPE["unique_key"]),
            "mapping_confirmed": True,
        }
    })
    allowed = _upload(c, "sales", headers, rows, type="sales", maps=maps)
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["types"]["sales"]["added"] == 1
    assert _sales_rows()[0]["fields"]["Party Name"] == "Northwind"


def test_control_total_mismatch_stays_visible():
    c = client()
    get_store().upsert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {"Date": "2026-10-02", "Party Name": "Northwind", "Sales Rep": "Asha", "Net Amount": 80},
    })
    get_store().upsert_row({
        "type": "arr",
        "uk": "a1",
        "fields": {"Account Name": "Northwind", "Group": "South", "Balance": 25},
    })
    missed = c.get("/api/analytics/onboarding?report_date=2026-10-03&control_sales=50&control_outstanding=25")
    assert missed.status_code == 200, missed.text
    messages = [row["message"] for row in missed.json()["exceptions"]]
    assert any(row.startswith("Sales total 80.00 does not match") for row in messages)
    assert not any(row.startswith("Outstanding total") for row in messages)
    again = c.get("/api/analytics/onboarding?report_date=2026-10-03")
    assert any("does not match the entered total 50.00" in row["message"] for row in again.json()["exceptions"])
    matched = c.get("/api/analytics/onboarding?report_date=2026-10-03&control_sales=80")
    assert matched.json()["exceptions"] == []


def test_later_used_upload_marks_the_report_and_unused_type_does_not():
    c = client()
    store = get_store()
    sales_id = store.insert_upload({
        "filename": "sales.xlsx",
        "type": "sales",
        "row_counts": {"sales": {"added": 1}},
        "dry_run": False,
    })
    run = store.insert_run({
        "status": "succeeded",
        "report_date": "2026-10-03",
        "finished_at": "2026-10-03 09:00:00",
        "manifest": {
            "data_version": {
                "types_used": ["sales", "arr"],
                "uploads": [{
                    "id": sales_id,
                    "filename": "sales.xlsx",
                    "finished_at": "2026-10-03 08:00:00",
                    "row_counts": {"sales": {"added": 1}},
                }],
            }
        },
    })
    current = c.get("/api/analytics/refresh?run=%s" % run["_id"])
    assert current.status_code == 200, current.text
    body = current.json()
    assert body["current"] is True
    assert body["report_finished_at"] == "2026-10-03 09:00:00"
    assert body["included"][0]["finished_at"] == "2026-10-03 08:00:00"
    store.insert_upload({
        "filename": "stock.xlsx",
        "type": "stock",
        "row_counts": {"stock": {"upserted": 1}},
        "dry_run": False,
    })
    still = c.get("/api/analytics/refresh?run=%s" % run["_id"]).json()
    assert still["current"] is True
    assert still["missing"] == []
    store.insert_upload({
        "filename": "sales-later.xlsx",
        "type": "sales",
        "row_counts": {"sales": {"added": 1}},
        "dry_run": False,
        "finished_at": "2026-10-04 10:00:00",
    })
    stale = c.get("/api/analytics/refresh?run=%s" % run["_id"]).json()
    assert stale["current"] is False
    assert stale["missing"][0]["filename"] == "sales-later.xlsx"
    assert stale["missing"][0]["types"] == ["sales"]
    assert stale["missing"][0]["finished_at"] == "2026-10-04 10:00:00"
    assert stale["report_finished_at"] == "2026-10-03 09:00:00"
