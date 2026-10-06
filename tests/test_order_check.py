"""Order-check policy evaluation and API."""

from __future__ import annotations

import os
from datetime import timedelta

os.environ.setdefault("VAY_STORE", "memory")
os.environ.setdefault("VAY_SYNC_JOBS", "1")

from fastapi.testclient import TestClient
from openpyxl import Workbook

from server.main import app
from server.order_check import (
    DEFAULT_POLICY,
    evaluate_order_check,
    resolve_policy,
    save_default_policy,
    save_policy_override,
)
from server.store import get_store, reset_store_for_tests
from vay.dates import today_ist


def client():
    reset_store_for_tests()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
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
    buf = __import__("io").BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_evaluate_blacklist_blocks():
    detail = {
        "due": 0,
        "due_days": 30,
        "open_invoices": [],
        "ordering": {"overall": {"sales_count": 2, "sales_value": 200}},
        "buying": {},
        "settlements": {"overall": {"total": 0, "buckets": {}}},
        "as_of": today_ist().strftime("%Y-%m-%d"),
    }
    out = evaluate_order_check(detail, order_value=100, flags={"premium": False, "blacklisted": True})
    assert out["action"] == "strong_push_back"
    assert any(r["code"] == "blacklisted" for r in out["reasons"])


def test_evaluate_urgent_and_reduce_volume():
    as_of = today_ist()
    detail = {
        "due": 500,
        "due_days": 30,
        "open_invoices": [{"age_days": 40, "amount": 500, "due": 500, "kind": "sale"}],
        "ordering": {"overall": {"sales_count": 4, "sales_value": 400}},
        "buying": {"last_order": [{"qty": 10}, {"qty": 5}]},
        "settlements": {"overall": {"total": 100, "buckets": {"d0_15": 100}}},
        "aging_bands": [{"key": "d0_15"}, {"key": "d90"}],
        "as_of": as_of.strftime("%Y-%m-%d"),
        "last_sale": (as_of - timedelta(days=60)).strftime("%Y-%m-%d"),
        "ordered_overdue": False,
    }
    # age 40 >= urgent 30 → strong; also oversized order
    out = evaluate_order_check(
        detail,
        order_value=1000,
        order_qty=50,
        policy=DEFAULT_POLICY,
        flags={"premium": False, "blacklisted": False},
    )
    assert out["action"] == "strong_push_back"
    assert any(r["code"] == "urgent_age" for r in out["reasons"])


def test_evaluate_reduce_volume_only():
    as_of = today_ist()
    detail = {
        "due": 0,
        "due_days": 30,
        "open_invoices": [],
        "ordering": {"overall": {"sales_count": 4, "sales_value": 400}},
        "buying": {"last_order": [{"qty": 10}]},
        "settlements": {"overall": {"total": 0, "buckets": {}}},
        "as_of": as_of.strftime("%Y-%m-%d"),
        "last_sale": (as_of - timedelta(days=30)).strftime("%Y-%m-%d"),
    }
    out = evaluate_order_check(
        detail,
        order_value=200,  # avg 100, 1.5x = 150
        order_qty=10,
        policy=DEFAULT_POLICY,
        flags={"premium": False, "blacklisted": False},
    )
    assert out["action"] == "reduce_volume"
    assert out["suggested_value"] is not None
    assert out["suggested_value"] <= 150


def test_evaluate_premium_demotes():
    as_of = today_ist()
    detail = {
        "due": 100,
        "due_days": 30,
        "open_invoices": [{"age_days": 20, "amount": 100, "due": 100, "kind": "sale"}],
        "ordering": {"overall": {"sales_count": 2, "sales_value": 200}},
        "buying": {},
        "settlements": {"overall": {"total": 0, "buckets": {}}},
        "as_of": as_of.strftime("%Y-%m-%d"),
        "last_sale": (as_of - timedelta(days=40)).strftime("%Y-%m-%d"),
    }
    base = evaluate_order_check(
        detail, order_value=100, policy=DEFAULT_POLICY,
        flags={"premium": False, "blacklisted": False},
    )
    assert base["action"] == "follow_up"
    prem = evaluate_order_check(
        detail, order_value=100, policy=DEFAULT_POLICY,
        flags={"premium": True, "blacklisted": False},
    )
    assert prem["action"] == "create_order"
    assert any(r["code"] == "premium_demote" for r in prem["reasons"])


def test_oldest_open_ignores_opening_when_invoices_exist():
    from server.order_check import _oldest_open_meta

    detail = {
        "open_invoices": [
            {"kind": "opening", "age_days": 174, "due": 500, "what": "Opening balance"},
            {"kind": "sale", "age_days": 42, "due": 200, "invoice": "INV-1", "what": "Sale"},
            {"kind": "sale", "age_days": 12, "due": 100, "invoice": "INV-2", "what": "Sale"},
        ],
    }
    meta = _oldest_open_meta(detail)
    assert meta["oldest_open_age"] == 42
    assert meta["oldest_open_kind"] != "opening"

    # Prefer precomputed Due fields when present (no re-scan).
    detail_pre = {
        **detail,
        "oldest_due_age": 42,
        "oldest_due_kind": "sale",
        "oldest_due_what": "INV-1",
    }
    assert _oldest_open_meta(detail_pre)["oldest_open_age"] == 42


def test_policy_resolution_hierarchy():
    reset_store_for_tests()
    store = get_store()
    save_default_policy(store, {"max_order_value_vs_avg": 1.2})
    save_policy_override(store, "group", "South", {"max_order_value_vs_avg": 1.8})
    save_policy_override(store, "customer", "Acme", {"credit_limit": 5000})
    resolved = resolve_policy(store, customer_uk="Acme", group="South", rep="RepA")
    assert resolved["source"] == "customer"
    assert resolved["policy"]["credit_limit"] == 5000
    assert resolved["policy"]["max_order_value_vs_avg"] == 1.8
    cleared = resolve_policy(store, customer_uk="Other", group="South", rep="")
    assert cleared["source"] == "group"
    assert cleared["policy"]["max_order_value_vs_avg"] == 1.8


def test_order_check_api_end_to_end():
    c = client()
    as_of = today_ist()
    d_old = as_of - timedelta(days=40)

    got = c.get("/api/settings/order-check").json()
    assert "policy" in got
    assert got["policy"]["followup_age_days"] == 15

    saved = c.post("/api/settings/order-check", json={
        "policy": {"max_order_value_vs_avg": 1.2, "credit_limit": 10000},
    }).json()
    assert saved["policy"]["max_order_value_vs_avg"] == 1.2
    assert saved["policy"]["credit_limit"] == 10000

    c.put("/api/mappers/arr", json={"column_map": {}, "unique_key": ["Account Name"]})
    c.put("/api/mappers/sales", json={"column_map": {}, "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount", "Invoice No"]})
    c.put("/api/mappers/customer", json={"column_map": {}, "unique_key": ["Account Name"]})
    c.post("/api/settings/settlement", json={"mode": "oldest", "aging_bands": None})

    arr = xlsx_bytes([("arr", ["Account Name", "Group", "Balance"], [
        ["Acme", "South", 200],
    ])])
    sales = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount", "Invoice No"], [
        [d_old.strftime("%d-%m-%y"), "Acme", "RepA", 200, "A-OLD"],
        [as_of.strftime("%d-%m-%y"), "Acme", "RepA", 100, "A-NEW"],
    ])])
    c.post("/api/uploads", data={"type": "arr"}, files={"file": ("a.xlsx", arr, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    c.post("/api/uploads", data={"type": "sales"}, files={"file": ("s.xlsx", sales, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

    listed = c.get("/api/customers").json()["customers"]
    acme = next(r for r in listed if r["name"] == "Acme")
    uk = acme["uk"]

    flags = c.put("/api/customers/%s/order-flags" % uk, json={"premium": True, "blacklisted": False}).json()
    assert flags["premium"] is True

    detail = c.get("/api/customers/%s" % uk).json()
    assert detail["premium"] is True
    assert "order_check_policy" in detail

    c.put("/api/customers/%s/order-check" % uk, json={"policy": {"urgent_age_days": 90}})
    result = c.post("/api/customers/%s/order-check/run" % uk, json={"order_value": 50, "order_qty": 1}).json()
    assert "action" in result
    assert result["action_label"]
    assert result["premium"] is True
    assert "due_days" in (result.get("signals") or {})
    assert "due_days_source" in (result.get("signals") or {})
    assert isinstance(result.get("reason_groups"), list)

    # Blacklist wins
    c.put("/api/customers/%s/order-flags" % uk, json={"blacklisted": True})
    blocked = c.post("/api/customers/%s/order-check/run" % uk, json={"order_value": 50}).json()
    assert blocked["action"] == "strong_push_back"


def test_group_and_rep_order_check_api():
    c = client()
    as_of = today_ist()
    d_old = as_of - timedelta(days=40)

    c.put("/api/mappers/arr", json={"column_map": {}, "unique_key": ["Account Name"]})
    c.put("/api/mappers/sales", json={"column_map": {}, "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount", "Invoice No"]})
    c.post("/api/settings/settlement", json={"mode": "oldest", "aging_bands": None})

    arr = xlsx_bytes([("arr", ["Account Name", "Group", "Balance"], [
        ["Acme", "South", 200],
    ])])
    sales = xlsx_bytes([("sales", ["Date", "Party Name", "Sales Rep", "Net Amount", "Invoice No"], [
        [d_old.strftime("%d-%m-%y"), "Acme", "RepA", 200, "A-OLD"],
        [as_of.strftime("%d-%m-%y"), "Acme", "RepA", 100, "A-NEW"],
    ])])
    c.post("/api/uploads", data={"type": "arr"}, files={"file": ("a.xlsx", arr, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    c.post("/api/uploads", data={"type": "sales"}, files={"file": ("s.xlsx", sales, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})

    groups = c.get("/api/groups").json()["groups"]
    south = next(g for g in groups if g["name"] == "South")
    guk = south["uk"]
    group = c.get("/api/groups/%s" % guk).json()
    assert "order_check_policy" in group

    saved = c.put("/api/groups/%s/order-check" % guk, json={"policy": {"urgent_age_days": 90}}).json()
    assert "effective_policy" in saved or saved.get("policy_own") or saved.get("own")
    group2 = c.get("/api/groups/%s" % guk).json()
    assert group2.get("order_check_own") is True
    assert group2["order_check_policy"]["urgent_age_days"] == 90

    run = c.post("/api/groups/%s/order-check/run" % guk, json={"order_value": 50, "order_qty": 1})
    assert run.status_code == 200
    result = run.json()
    assert "action" in result
    assert result.get("premium") is False
    assert result.get("blacklisted") is False
    assert result.get("entity") == "group"

    reps = c.get("/api/reps").json()["reps"]
    rep = next(r for r in reps if r["name"] == "RepA")
    ruk = rep["uk"]
    c.put("/api/reps/%s/order-check" % ruk, json={"policy": {"max_order_value_vs_avg": 1.1}})
    rep_detail = c.get("/api/reps/%s" % ruk).json()
    assert rep_detail.get("order_check_own") is True
    rep_run = c.post("/api/reps/%s/order-check/run" % ruk, json={"order_value": 50})
    assert rep_run.status_code == 200
    assert "action" in rep_run.json()
    assert rep_run.json().get("entity") == "rep"

    cleared = c.put("/api/groups/%s/order-check" % guk, json={"clear": True}).json()
    assert cleared.get("policy_own") is False or cleared.get("own") is False or "effective_policy" in cleared
