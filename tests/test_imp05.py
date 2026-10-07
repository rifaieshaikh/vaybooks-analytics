"""IMP-05: explain a saved figure, and keep live follow-up on its own data basis."""

import io
import os

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient
from openpyxl import Workbook

from server.items360 import save_holding
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


def login(username, password):
    other = TestClient(app)
    logged = other.post("/api/auth/login", json={"username": username, "password": password})
    assert logged.status_code == 200, logged.text
    return other


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


def _upload(c, type_name, headers, rows, filename, effective_date=""):
    data = {"type": type_name}
    if effective_date:
        data["effective_date"] = effective_date
    posted = c.post(
        "/api/uploads",
        data=data,
        files={"file": (filename, xlsx_bytes([(type_name, headers, rows)]), MIME)},
    )
    assert posted.status_code == 200, posted.text
    return posted.json()


def _sales_source(explanation):
    return next(row for row in explanation.get("sources") or [] if row.get("type") == "sales")


def test_saved_sales_explanation_keeps_its_basis_after_a_later_upload():
    c = client()
    c.put("/api/mappers/sales", json={"column_map": {}, "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"]})
    c.put("/api/mappers/receipt", json={"column_map": {}, "unique_key": ["Date", "Account Name", "Sales Rep", "Amount"]})
    c.put("/api/mappers/arr", json={"column_map": {}, "unique_key": ["Account Name"]})
    _upload(c, "sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [["19-09-26", "Acme", "RepA", 100]], "s.xlsx", "2026-09-19")
    _upload(c, "receipt", ["Date", "Account Name", "Sales Rep", "Amount"], [["19-09-26", "Acme", "RepA", 40]], "r.xlsx")
    _upload(c, "arr", ["Account Name", "Group", "Balance"], [["Acme", "South", 110]], "a.xlsx", "2026-09-19")
    run = c.post("/api/runs", json={"packs": {"core": True}, "report_date": "2026-09-19"})
    assert run.status_code == 202, run.text
    detail = c.get("/api/runs/%s" % run.json()["id"])
    assert detail.status_code == 200, detail.text
    assert detail.json()["status"] == "succeeded", detail.text
    home = c.get("/api/dashboard")
    assert home.status_code == 200, home.text
    body = home.json()
    kpis = {row["id"]: row["value"] for row in body.get("kpis") or []}
    explained = (body.get("explanations") or {}).get("mtd_sales")
    assert explained, body.get("explanations_message")
    assert explained["value"] == kpis["mtd_sales"]
    assert explained["window"]["to"] == "2026-09-19"
    assert explained["reconciliation"]["status"] == (detail.json().get("manifest") or {}).get("reconciliation", {}).get("status")
    assert "label_kind" not in explained
    assert _sales_source(explained)["coverage_through"] == "2026-09-19"
    saved_through = _sales_source(explained)["coverage_through"]

    assert c.post("/api/users", json={"username": "shelf", "password": "shelf12345", "role": "Warehouse"}).status_code == 200
    shelf = login("shelf", "shelf12345")
    hidden = shelf.get("/api/dashboard")
    assert hidden.status_code == 200, hidden.text
    for row in (hidden.json().get("explanations") or {}).values():
        assert all(source.get("type") != "sales" for source in row.get("sources") or [])
    assert "mtd_sales" not in (hidden.json().get("explanations") or {})

    contact = c.post("/api/collection/contacts", json={
        "customer_name": "Acme",
        "contacted_on": "2026-09-01",
        "channel": "phone",
        "note": "Called",
        "next_step": "Call again",
        "next_follow_up": "2026-09-01",
    })
    assert contact.status_code == 200, contact.text
    promised = c.post("/api/collection/promises", json={
        "customer_name": "Acme",
        "amount": 40,
        "promised_on": "2026-09-01",
    })
    assert promised.status_code == 200, promised.text
    _upload(c, "sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [["07-10-26", "Acme", "RepA", 20]], "later.xlsx")
    _upload(c, "receipt", ["Date", "Account Name", "Sales Rep", "Amount"], [["07-10-26", "Acme", "RepA", 5]], "later-r.xlsx")

    again = c.get("/api/dashboard").json()
    assert _sales_source(again["explanations"]["mtd_sales"])["coverage_through"] == saved_through
    follow = c.get("/api/collection", params={"customer": "Acme"})
    assert follow.status_code == 200, follow.text
    promise = follow.json()["promises"][0]
    assert promise["receipt_coverage_through"] == "2026-10-07"
    assert promise["data_basis"]["basis"] == "live"
    today = c.get("/api/worklist")
    assert today.status_code == 200, today.text
    acme = next(row for row in today.json()["rows"] if row["customer"] == "Acme")
    assert acme["basis"]["basis"] == "live"
    assert _sales_source(acme["basis"])["coverage_through"] == "2026-10-07"

    assert c.post("/api/roles", json={"name": "Outsider", "permissions": ["stock.upload"]}).status_code == 200
    assert c.post("/api/users", json={"username": "outsider", "password": "outsider123", "role": "Outsider"}).status_code == 200
    outsider = login("outsider", "outsider123")
    refused = outsider.get("/api/collection", params={"customer": "Acme"})
    assert refused.status_code == 403
    assert "basis_label" not in refused.text
    assert "receipt_coverage_through" not in refused.text


def test_reorder_cost_and_mixed_coverage_follow_the_caller():
    c = client()
    store = get_store()
    store.insert_run({"status": "succeeded", "report_date": "2026-10-03", "manifest": {}})
    store.upsert_row({
        "type": "stock",
        "uk": "Widget",
        "effective_date": "2026-10-03",
        "fields": {"Item Name": "Widget", "Qty": 2, "P.Price": 4, "EffectiveDate": "2026-10-03"},
    })
    store.upsert_row({
        "type": "stock",
        "uk": "Bare",
        "effective_date": "2026-10-03",
        "fields": {"Item Name": "Bare", "Qty": 1, "EffectiveDate": "2026-10-03"},
    })
    store.upsert_row({
        "type": "items",
        "uk": "w1",
        "fields": {"Date": "2026-01-11", "Item Name": "Widget", "Qty": 5, "Rate": 4, "Party Name": "Repeat"},
    })
    store.upsert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {"Date": "2026-01-11", "Party Name": "Repeat", "Sales Rep": "Asha", "Net Amount": 20},
    })
    save_holding(store, "Widget", min_hold=20, fill_to=50, lead_days=0)
    save_holding(store, "Bare", min_hold=20, fill_to=50, lead_days=0)
    listed = c.get("/api/reorder")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["status"] == "eligible", body
    widget = next(row for row in body["order"] if row["name"] == "Widget")
    bare = next(row for row in body["order"] if row["name"] == "Bare")
    assert widget["explanation"]["label_kind"] == "snapshot_cost"
    assert widget["explanation"]["mixed_coverage"] is True
    assert "2026-01-11" in widget["explanation"]["coverage_note"]
    assert "2026-10-03" in widget["explanation"]["coverage_note"]
    assert any(source["type"] == "sales" for source in widget["explanation"]["sources"])
    assert bare["explanation"]["label_kind"] == "cost_unavailable"
    assert bare["explanation"]["value"] is None
    assert bare["explanation"]["value"] != 0

    assert c.post("/api/users", json={"username": "shelf", "password": "shelf12345", "role": "Warehouse"}).status_code == 200
    shelf = login("shelf", "shelf12345")
    hidden = shelf.get("/api/reorder")
    assert hidden.status_code == 200, hidden.text
    for row in hidden.json().get("order") or []:
        assert all(source.get("type") != "sales" for source in (row.get("explanation") or {}).get("sources") or [])


def test_today_mixed_coverage_names_each_date_and_hides_sales_sources():
    c = client()
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "only",
        "fields": {"Date": "2026-09-01", "Party Name": "Only", "Sales Rep": "Asha", "Net Amount": 10},
    })
    store.upsert_row({
        "type": "customer",
        "uk": "Only",
        "fields": {"Account Name": "Only", "Group": "South", "Balance": 0},
    })
    only = c.post("/api/collection/contacts", json={
        "customer_name": "Only",
        "contacted_on": "2026-09-01",
        "channel": "phone",
        "note": "Called",
        "next_step": "Call again",
        "next_follow_up": "2026-09-01",
    })
    assert only.status_code == 200, only.text
    single = c.get("/api/worklist")
    assert single.status_code == 200, single.text
    card = next(row for row in single.json()["rows"] if row["customer"] == "Only")
    assert card["basis"]["mixed_coverage"] is False
    assert card["basis"]["coverage_note"] == ""

    store.upsert_row({
        "type": "items",
        "uk": "w1",
        "fields": {"Date": "2026-01-01", "Item Name": "Widget", "Qty": 5, "Rate": 4, "Party Name": "Repeat", "Sales Rep": "Asha"},
    })
    store.upsert_row({
        "type": "items",
        "uk": "w2",
        "fields": {"Date": "2026-01-11", "Item Name": "Widget", "Qty": 5, "Rate": 4, "Party Name": "Repeat", "Sales Rep": "Asha"},
    })
    store.upsert_row({
        "type": "sales",
        "uk": "repeat",
        "fields": {"Date": "2026-01-11", "Party Name": "Repeat", "Sales Rep": "Asha", "Net Amount": 20},
    })
    store.upsert_row({
        "type": "customer",
        "uk": "Repeat",
        "fields": {"Account Name": "Repeat", "Group": "South", "Balance": 0},
    })
    store.upsert_row({
        "type": "arr",
        "uk": "Repeat",
        "effective_date": "2026-09-01",
        "fields": {"Account Name": "Repeat", "Balance": 0, "EffectiveDate": "2026-09-01"},
    })
    store.upsert_row({
        "type": "stock",
        "uk": "Widget",
        "effective_date": "2026-10-03",
        "fields": {"Item Name": "Widget", "Qty": 1, "P.Price": 4, "EffectiveDate": "2026-10-03"},
    })
    mixed = c.get("/api/worklist")
    assert mixed.status_code == 200, mixed.text
    repeat = next(row for row in mixed.json()["rows"] if row["customer"] == "Repeat" and row["kind"] == "repurchase")
    assert repeat["basis"]["mixed_coverage"] is True
    note = repeat["basis"]["coverage_note"]
    assert "Receivables 2026-09-01" in note
    assert "Sales 2026-01-11" in note
    assert "Stock 2026-10-03" in note

    assert c.post("/api/roles", json={"name": "Caller", "permissions": ["reports.view.followup"]}).status_code == 200
    assert c.post("/api/users", json={"username": "caller", "password": "caller12345", "role": "Caller"}).status_code == 200
    assert c.patch("/api/users/caller", json={"sales_reps": ["Asha"]}).status_code == 200
    caller = login("caller", "caller12345")
    own = caller.get("/api/worklist")
    assert own.status_code == 200, own.text
    for row in own.json()["rows"]:
        assert all(source.get("type") != "sales" for source in (row.get("basis") or {}).get("sources") or [])
    caller_repeat = next(row for row in own.json()["rows"] if row["customer"] == "Repeat" and row["kind"] == "repurchase")
    assert "Sales" not in (caller_repeat["basis"]["coverage_note"] or "")
