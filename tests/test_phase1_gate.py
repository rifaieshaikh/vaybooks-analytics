"""Phase 1 gate: provenance, import modes, recon sidecars, run manifests."""

import hashlib
import io
import json
import os

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient
from openpyxl import Workbook

from server.main import app
from server.reconcile import compute_headlines, parse_recon_sidecar, reconcile
from server.store import get_store, reset_store_for_tests


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


def seed_core(c, report_day="19-09-26"):
    """Minimal sales + arr for Create and recon."""
    c.put("/api/mappers/sales", json={
        "column_map": {},
        "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    })
    c.put("/api/mappers/receipt", json={
        "column_map": {},
        "unique_key": ["Date", "Account Name", "Sales Rep", "Amount"],
    })
    c.put("/api/mappers/arr", json={"column_map": {}, "unique_key": ["Account Name"]})
    sales = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [
        [report_day, "Acme", "RepA", 100],
        ["01-09-26", "Acme", "RepA", 50],
    ])])
    receipt = xlsx_bytes([("receipt", ["Date", "Account Name", "Sales Rep", "Amount"], [
        [report_day, "Acme", "RepA", 40],
    ])])
    arr = xlsx_bytes([("arr", ["Account Name", "Group", "Balance"], [
        ["Acme", "South", 110],
    ])])
    rs = c.post(
        "/api/uploads",
        data={"type": "sales", "effective_date": "2026-09-19"},
        files={"file": ("s.xlsx", sales, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert rs.status_code == 200
    rr = c.post(
        "/api/uploads",
        data={"type": "receipt"},
        files={"file": ("r.xlsx", receipt, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert rr.status_code == 200
    ra = c.post(
        "/api/uploads",
        data={"type": "arr", "effective_date": "2026-09-19"},
        files={"file": ("a.xlsx", arr, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert ra.status_code == 200
    return rs.json(), rr.json(), ra.json()


def test_upload_stores_file_sha256_and_mapper_version():
    c = client()
    c.put("/api/mappers/sales", json={
        "column_map": {},
        "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    })
    data = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [["19-09-26", "A", "R", 1]])])
    r = c.post(
        "/api/uploads",
        data={"type": "sales"},
        files={"file": ("t.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["file_sha256"] == hashlib.sha256(data).hexdigest()
    assert body["mapper_versions"]["sales"]
    assert body["row_counts"]["sales"]["added"] == 1
    listed = c.get("/api/uploads").json()["uploads"]
    assert any(u["file_sha256"] == body["file_sha256"] for u in listed)


def test_dry_run_preview_does_not_insert():
    c = client()
    c.put("/api/mappers/sales", json={
        "column_map": {},
        "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    })
    data = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [["19-09-26", "A", "R", 5]])])
    r = c.post(
        "/api/uploads",
        data={"type": "sales", "dry_run": "1"},
        files={"file": ("t.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    assert r.json()["dry_run"] is True
    assert r.json()["types"]["sales"]["added"] == 1
    assert r.json()["types"]["sales"].get("dry_run") is True
    assert "preview_rows" not in r.json()["types"]["sales"]
    sheets = r.json().get("sheets") or []
    assert sheets and sheets[0].get("preview_rows", {}).get("added")
    assert sheets[0]["preview_rows"]["added"][0]["fields"]["Party Name"] == "A"
    assert len(get_store().rows_of_type("sales")) == 0


def test_replace_batch_no_double_count():
    c = client()
    c.put("/api/mappers/sales", json={
        "column_map": {},
        "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    })
    data1 = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [["19-09-26", "Acme", "R", 10]])])
    data2 = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [["19-09-26", "Acme", "R", 10]])])
    r1 = c.post(
        "/api/uploads",
        data={"type": "sales", "event_mode": "skip"},
        files={"file": ("a.xlsx", data1, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r1.json()["types"]["sales"]["added"] == 1
    r2 = c.post(
        "/api/uploads",
        data={"type": "sales", "event_mode": "replace_batch"},
        files={"file": ("b.xlsx", data2, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    body = r2.json()["types"]["sales"]
    assert body.get("deleted") == 1
    assert body.get("added") == 1
    assert len(get_store().rows_of_type("sales")) == 1


def test_replace_period_deletes_range_then_inserts():
    c = client()
    c.put("/api/mappers/sales", json={
        "column_map": {},
        "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount", "Invoice No"],
    })
    first = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount", "Invoice No"], [
        ["10-09-26", "Acme", "R", 10, "A1"],
        ["15-09-26", "Acme", "R", 20, "A2"],
        ["01-08-26", "Acme", "R", 5, "OLD"],
    ])])
    c.post(
        "/api/uploads",
        data={"type": "sales", "event_mode": "skip"},
        files={"file": ("a.xlsx", first, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert len(get_store().rows_of_type("sales")) == 3
    second = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount", "Invoice No"], [
        ["10-09-26", "Acme", "R", 11, "B1"],
        ["15-09-26", "Acme", "R", 22, "B2"],
    ])])
    r = c.post(
        "/api/uploads",
        data={"type": "sales", "event_mode": "replace_period"},
        files={"file": ("b.xlsx", second, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.json()["types"]["sales"]["deleted"] == 2
    assert r.json()["types"]["sales"]["added"] == 2
    rows = get_store().rows_of_type("sales")
    assert len(rows) == 3  # August retained + 2 new September
    invoices = {(row.get("fields") or {}).get("Invoice No") for row in rows}
    assert "OLD" in invoices
    assert "B1" in invoices
    assert "A1" not in invoices


def test_undo_upload_restores_counts():
    c = client()
    c.put("/api/mappers/sales", json={
        "column_map": {},
        "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    })
    data = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [["19-09-26", "A", "R", 7]])])
    r = c.post(
        "/api/uploads",
        data={"type": "sales"},
        files={"file": ("t.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    uid = r.json()["id"]
    assert len(get_store().rows_of_type("sales")) == 1
    d = c.delete("/api/uploads/%s" % uid)
    assert d.status_code == 200
    assert len(get_store().rows_of_type("sales")) == 0


def test_arr_effective_date_persisted():
    c = client()
    c.put("/api/mappers/arr", json={"column_map": {}, "unique_key": ["Account Name"]})
    arr = xlsx_bytes([("arr", ["Account Name", "Group", "Balance"], [["Acme", "South", 50]])])
    r = c.post(
        "/api/uploads",
        data={"type": "arr", "effective_date": "2026-09-19"},
        files={"file": ("a.xlsx", arr, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 200
    assert r.json()["effective_date"] == "2026-09-19"
    row = get_store().rows_of_type("arr")[0]
    assert (row.get("fields") or {}).get("EffectiveDate") == "2026-09-19"


def test_recon_sidecar_pass_and_fail():
    c = client()
    seed_core(c)
    headlines = compute_headlines(get_store(), "2026-09-19")
    good = {
        "report_date": "2026-09-19",
        "sales_mtd": headlines["sales_mtd"],
        "sales_ytd": headlines["sales_ytd"],
        "ar_balance": headlines["ar_balance"],
        "tolerance": 0.01,
    }
    bad = dict(good)
    bad["sales_mtd"] = headlines["sales_mtd"] + 999

    good_bytes = json.dumps(good).encode("utf-8")
    up = c.post(
        "/api/recon/sidecars",
        files={"file": ("ok.recon.json", good_bytes, "application/json")},
    )
    assert up.status_code == 200
    assert up.json()["report_date"] == "2026-09-19"

    from server.reconcile import find_sidecar_for_date
    _doc, payload = find_sidecar_for_date(get_store(), "2026-09-19")
    assert reconcile(get_store(), payload, "2026-09-19")["status"] == "pass"
    assert reconcile(get_store(), bad, "2026-09-19")["status"] == "fail"
    assert reconcile(get_store(), None, "2026-09-19")["status"] == "unavailable"


def test_create_run_manifest_and_reproduce():
    c = client()
    seed_core(c)
    headlines = compute_headlines(get_store(), "2026-09-19")
    sidecar = json.dumps({
        "report_date": "2026-09-19",
        "sales_mtd": headlines["sales_mtd"],
        "sales_ytd": headlines["sales_ytd"],
        "ar_balance": headlines["ar_balance"],
        "tolerance": 0.01,
    }).encode("utf-8")
    c.post(
        "/api/recon/sidecars",
        files={"file": ("gate.recon.json", sidecar, "application/json")},
    )
    run = c.post("/api/runs", json={
        "packs": {"core": True, "fiscal": False, "items": False, "profit": False},
        "report_date": "2026-09-19",
    })
    assert run.status_code == 202
    rid = run.json()["id"]
    detail = c.get("/api/runs/%s" % rid)
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "succeeded"
    manifest = body.get("manifest") or {}
    assert manifest.get("data_version", {}).get("uploads")
    assert manifest.get("calculation_version", {}).get("engine") == "vay.engine.generate"
    assert manifest.get("calculation_version", {}).get("metrics", {}).get("sales_mtd") == 1
    assert manifest.get("eligibility", {}).get("sales_mtd", {}).get("status") == "eligible"
    assert manifest.get("reconciliation", {}).get("status") == "pass"
    snap1 = body.get("snapshot")
    detail2 = c.get("/api/runs/%s" % rid).json()
    assert detail2.get("snapshot") == snap1


def _fixture(name):
    path = os.path.join(os.path.dirname(__file__), "fixtures", "phase1", name)
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _sales_total(store):
    from vay.dates import number_

    total = 0.0
    for row in store.rows_of_type("sales"):
        total += number_((row.get("fields") or {}).get("Net Amount"))
    return total


def test_credit_note_reduces_sales_not_collections():
    spec = _fixture("credit_note.json")
    c = client()
    c.put("/api/mappers/sales", json={
        "column_map": {},
        "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    })
    c.put("/api/mappers/receipt", json={
        "column_map": {},
        "unique_key": ["Date", "Account Name", "Sales Rep", "Amount"],
    })
    c.put("/api/mappers/credit_note", json={
        "column_map": {},
        "unique_key": ["Date", "Party Name", "Invoice No", "Net Amount"],
    })
    sales = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [spec["sales"]])])
    note = xlsx_bytes([(
        "credit_note",
        ["SlNo", "Invoice No", "Date", "Party Name", "Sales Amount", "SGST", "CGST", "IGST", "Net Amount"],
        [spec["credit_note"]],
    )])
    receipt = xlsx_bytes([("receipt", ["Date", "Account Name", "Sales Rep", "Amount"], [spec["receipt"]])])
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert c.post("/api/uploads", files={"file": ("s.xlsx", sales, mime)}).status_code == 200
    assert c.post("/api/uploads", files={"file": ("c.xlsx", note, mime)}).status_code == 200
    assert c.post("/api/uploads", files={"file": ("r.xlsx", receipt, mime)}).status_code == 200
    headlines = compute_headlines(get_store(), spec["report_date"])
    assert headlines["sales_mtd"] == spec["expect_sales_mtd"]
    from vay.dates import number_

    collected = 0.0
    for row in get_store().rows_of_type("receipt"):
        collected += number_((row.get("fields") or {}).get("Amount"))
    assert collected == spec["expect_collection"]


def test_reimport_skip_and_replace_period():
    spec = _fixture("reimport.json")
    c = client()
    c.put("/api/mappers/sales", json={
        "column_map": {},
        "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    })
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    def upload(amount, mode):
        data = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [
            [spec["day"], "Acme", "RepA", amount],
        ])])
        return c.post(
            "/api/uploads",
            data={"type": "sales", "event_mode": mode},
            files={"file": ("s.xlsx", data, mime)},
        )

    assert upload(spec["first_amount"], "skip").status_code == 200
    assert upload(spec["first_amount"], "skip").status_code == 200
    assert _sales_total(get_store()) == spec["first_amount"]
    assert len(list(get_store().rows_of_type("sales"))) == 1
    assert upload(spec["replacement_amount"], "replace_period").status_code == 200
    assert _sales_total(get_store()) == spec["replacement_amount"]
    assert len(list(get_store().rows_of_type("sales"))) == 1


def test_partial_receipt_leaves_open_remainder():
    spec = _fixture("partial_receipt.json")
    c = client()
    c.put("/api/mappers/sales", json={
        "column_map": {},
        "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    })
    c.put("/api/mappers/receipt", json={
        "column_map": {},
        "unique_key": ["Date", "Account Name", "Sales Rep", "Amount"],
    })
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    sales = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [
        [spec["day"], "Acme", "RepA", spec["invoice_amount"]],
    ])])
    receipt = xlsx_bytes([("receipt", ["Date", "Account Name", "Sales Rep", "Amount"], [
        [spec["day"], "Acme", "RepA", spec["receipt_amount"]],
    ])])
    assert c.post("/api/uploads", files={"file": ("s.xlsx", sales, mime)}).status_code == 200
    assert c.post("/api/uploads", files={"file": ("r.xlsx", receipt, mime)}).status_code == 200
    from datetime import datetime

    from vay.dates import number_, parse_date
    from vay.settlement import allocate_collections

    invoices = []
    for row in get_store().rows_of_type("sales"):
        fields = row.get("fields") or {}
        invoices.append({
            "amount": number_(fields.get("Net Amount")),
            "date": parse_date(fields.get("Date")),
            "invoice": "INV1",
        })
    receipts = []
    for row in get_store().rows_of_type("receipt"):
        fields = row.get("fields") or {}
        receipts.append({
            "amount": number_(fields.get("Amount")),
            "date": parse_date(fields.get("Date")),
        })
    _buckets, _allocs, _credit, remainders, _opening = allocate_collections(
        invoices, receipts, datetime(2026, 9, 19),
    )
    left = sum(number_(row.get("remaining")) for row in remainders)
    assert left == spec["expect_remaining"]


def test_missing_cost_makes_gross_margin_unavailable():
    spec = _fixture("missing_cost.json")
    c = client()
    c.put("/api/mappers/items", json={"column_map": {}, "unique_key": ["Date", "Item Name", "Qty", "Rate"]})
    c.put("/api/mappers/stock", json={"column_map": {}, "unique_key": ["Item Name"]})
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    items = xlsx_bytes([("items", ["Date", "Item Name", "Qty", "Rate"], [spec["item"]])])
    stock = xlsx_bytes([("stock", ["Item Name", "Qty", "P.Price"], [spec["stock"]])])
    assert c.post("/api/uploads", data={"type": "items"}, files={"file": ("i.xlsx", items, mime)}).status_code == 200
    assert c.post(
        "/api/uploads",
        data={"type": "stock", "effective_date": spec["report_date"]},
        files={"file": ("k.xlsx", stock, mime)},
    ).status_code == 200
    from vay.eligibility import evaluate

    margin = evaluate(get_store(), spec["report_date"])["gross_margin"]
    assert margin["status"] == "unavailable"
    assert margin["reason"] == "Missing item cost"
    assert "value" not in margin
    assert margin.get("as_of") != 0


def test_near_match_review_queue_merges_customer_id():
    spec = _fixture("near_match.json")
    c = client()
    c.put("/api/mappers/sales", json={
        "column_map": {},
        "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    })
    rows = [[spec["day"], name, "RepA", 10 + i] for i, name in enumerate(spec["names"])]
    data = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], rows)])
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert c.post("/api/uploads", data={"type": "sales"}, files={"file": ("s.xlsx", data, mime)}).status_code == 200
    listed = c.get("/api/settings/entity-review")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 1
    assert {items[0]["left_name"], items[0]["right_name"]} == set(spec["names"])
    merged = c.post("/api/settings/entity-review/merge", json={
        "kind": items[0]["kind"],
        "left_name": items[0]["left_name"],
        "right_entity_id": items[0]["right_entity_id"],
    })
    assert merged.status_code == 200
    assert merged.json()["items"] == []
    ids = {
        (row.get("fields") or {}).get("customer_id")
        for row in get_store().rows_of_type("sales")
    }
    assert len(ids) == 1
    assert "" not in ids
    from server.entities import resolve_name

    entities = []
    queue = [{
        "kind": "customer",
        "left_name": items[0]["left_name"],
        "left_norm": items[0]["left_name"].lower(),
        "left_entity_id": "cus_left",
        "right_entity_id": items[0]["right_entity_id"],
        "right_name": items[0]["right_name"],
        "score": 0.95,
        "state": "rejected",
    }]
    entities.append({
        "id": items[0]["right_entity_id"],
        "kind": "customer",
        "display_name": items[0]["right_name"],
        "normalized_name": items[0]["right_name"].lower(),
        "status": "active",
    })
    _eid, _created, queued = resolve_name("customer", items[0]["left_name"], entities, queue)
    assert queued is False


def test_stale_arr_snapshot_is_unavailable_warning():
    spec = _fixture("stale_snapshot.json")
    c = client()
    c.put("/api/mappers/sales", json={
        "column_map": {},
        "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    })
    c.put("/api/mappers/arr", json={"column_map": {}, "unique_key": ["Account Name"]})
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    sales = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount"], [
        [spec["day"], "Acme", "RepA", 100],
    ])])
    arr = xlsx_bytes([("arr", ["Account Name", "Group", "Balance"], [["Acme", "South", 100]])])
    assert c.post("/api/uploads", data={"type": "sales"}, files={"file": ("s.xlsx", sales, mime)}).status_code == 200
    assert c.post(
        "/api/uploads",
        data={"type": "arr", "effective_date": spec["snapshot_date"]},
        files={"file": ("a.xlsx", arr, mime)},
    ).status_code == 200
    from vay.eligibility import evaluate
    from server.reconcile import arr_effective_date_warning

    elig = evaluate(get_store(), spec["report_date"])["ar_balance"]
    assert elig["status"] == "unavailable"
    assert spec["snapshot_date"] in elig["reason"]
    assert elig["as_of"] == spec["snapshot_date"]
    warnings = arr_effective_date_warning(get_store(), spec["report_date"])
    assert len(warnings) == 1
    assert warnings[0]["source_type"] == "arr"
    run = c.post("/api/runs", json={"packs": {"core": True}, "report_date": spec["report_date"]})
    assert run.status_code == 202
    manifest = c.get("/api/runs/%s" % run.json()["id"]).json()["manifest"]
    assert manifest["eligibility"]["ar_balance"]["status"] == "unavailable"
    kinds = [row["severity"] for row in manifest["reconciliation"]["exceptions"]]
    assert "warning" in kinds
    warning = next(row for row in manifest["reconciliation"]["exceptions"] if row["severity"] == "warning")
    assert warning["metric_id"] == "ar_balance"
    assert "Collection follow-up" in warning["affected_reports"]


def test_parse_recon_sidecar_schema():
    parsed = parse_recon_sidecar({
        "report_date": "2026-09-19",
        "sales_mtd": 1,
        "ar_balance": 2,
    })
    assert parsed["report_date"] == "2026-09-19"
    assert parsed["sales_mtd"] == 1.0
