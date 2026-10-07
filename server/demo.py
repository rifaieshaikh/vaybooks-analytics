"""Labeled sample company inside the default organization.

Desktop has no organization switcher, so demo rows live beside real data and
are marked Demo=yes. Reset refuses to run after a real import.
"""

from __future__ import annotations

from datetime import timedelta

from vay.dates import parse_date, today_ist

from server.actions import create_action
from server.collection import create_contact, create_promise
from server.org_policy import get_org_policy, save_org_policy

DEMO_FLAG = "yes"
DEMO_COMPANY = "Vay Demo Traders"
BUSINESS_TYPES = ("sales", "receipt", "credit_note", "arr", "items", "stock", "party", "customer")
SCENARIOS = (
    {"id": "overdue", "name": "Harbour Traders", "summary": "Overdue balance and a follow-up due today."},
    {"id": "missed_promise", "name": "North Mill", "summary": "Promise dated yesterday, partial receipt, remaining balance."},
    {"id": "declining", "name": "Lane and Co", "summary": "Purchases down from an earlier period to a small recent sale."},
    {"id": "stock", "name": "Oak Board 18mm", "summary": "Stock below the latest selling quantity, with an assigned purchase."},
)


def _day(store, offset=0):
    policy = get_org_policy(store)
    today = today_ist(policy.get("timezone"))
    return (today + timedelta(days=offset)).strftime("%Y-%m-%d")


def _is_demo(row):
    return str((row.get("fields") or {}).get("Demo") or "") == DEMO_FLAG


def has_customer_data(store):
    for row in store.list_rows() or []:
        if row.get("type") not in BUSINESS_TYPES or _is_demo(row):
            continue
        return True
    for upload in store.list_uploads() or []:
        if not upload.get("dry_run"):
            return True
    return False


def _put(store, type_name, uk, fields):
    fields = dict(fields)
    fields["Demo"] = DEMO_FLAG
    store.upsert_row({
        "type": type_name,
        "uk": uk,
        "source_upload_id": "",
        "fields": fields,
    })


def _mark(store, type_name, uk):
    row = store.find_row(type_name, uk)
    if not row:
        return
    fields = dict(row.get("fields") or {})
    fields["Demo"] = DEMO_FLAG
    store.upsert_row({
        "type": type_name,
        "uk": uk,
        "source_upload_id": row.get("source_upload_id") or "",
        "fields": fields,
    })


def _clear_demo(store):
    for row in store.list_rows() or []:
        if _is_demo(row):
            store.delete_row(row.get("type"), row.get("uk"))
    for run in store.list_runs() or []:
        if run.get("demo"):
            store.delete_run(run.get("_id"))


def _seed_rows(store, username):
    today = _day(store, 0)
    yesterday = _day(store, -1)
    rep = "Asha"
    _put(store, "sales", "demo-sales-harbour", {
        "Date": _day(store, -20), "Party Name": "Harbour Traders", "Sales Rep": rep, "Net Amount": 80000,
    })
    _put(store, "arr", "demo-arr-harbour", {
        "Account Name": "Harbour Traders", "Group": "Trade", "Balance": 80000, "EffectiveDate": today,
    })
    _put(store, "sales", "demo-sales-north", {
        "Date": _day(store, -15), "Party Name": "North Mill", "Sales Rep": rep, "Net Amount": 40000,
    })
    _put(store, "receipt", "demo-receipt-north", {
        "Date": yesterday, "Account Name": "North Mill", "Sales Rep": rep, "Amount": 15000,
    })
    _put(store, "arr", "demo-arr-north", {
        "Account Name": "North Mill", "Group": "Trade", "Balance": 25000, "EffectiveDate": today,
    })
    _put(store, "sales", "demo-sales-lane-old", {
        "Date": _day(store, -80), "Party Name": "Lane and Co", "Sales Rep": rep, "Net Amount": 90000,
    })
    _put(store, "sales", "demo-sales-lane-new", {
        "Date": _day(store, -4), "Party Name": "Lane and Co", "Sales Rep": rep, "Net Amount": 5000,
    })
    _put(store, "items", "demo-items-oak", {
        "Date": _day(store, -10), "Item Name": "Oak Board 18mm", "Qty": 40, "Rate": 100,
    })
    _put(store, "stock", "demo-stock-oak", {
        "Item Name": "Oak Board 18mm", "Qty": 8, "P.Price": 80, "EffectiveDate": today,
    })
    for name, balance in (("Harbour Traders", 80000), ("North Mill", 25000), ("Lane and Co", 0)):
        _put(store, "customer", name, {
            "Account Name": name, "Group": "Trade", "Balance": balance, "party_uk": name,
        })
        _put(store, "party", name, {
            "Account Name": name, "Group": "Trade", "Balance": balance, "customer_uk": name,
        })
    harbour = create_action(store, {
        "action_type": "collection",
        "subject_kind": "customer",
        "subject_name": "Harbour Traders",
        "proposal": "Collect the overdue balance",
        "owner": username or "admin",
        "due_date": today,
        "amount": 80000,
        "report_date": today,
    }, username)
    _mark(store, "action", harbour["id"])
    contact = create_contact(store, {
        "customer_name": "Harbour Traders",
        "action_id": harbour["id"],
        "contacted_on": yesterday,
        "staff": username or "admin",
        "channel": "phone",
        "note": "Asked for payment of the overdue balance.",
        "next_step": "Call again for the overdue balance",
        "next_follow_up": today,
    }, username)
    _mark(store, "collection_contact", contact["id"])
    promise = create_promise(store, {
        "customer_name": "North Mill",
        "amount": 40000,
        "promised_on": yesterday,
        "invoice_refs": ["NM-1"],
        "staff": username or "admin",
    }, username)
    _mark(store, "collection_promise", promise["id"])
    purchase = create_action(store, {
        "action_type": "purchase",
        "subject_kind": "item",
        "subject_name": "Oak Board 18mm",
        "proposal": "Buy Oak Board 18mm before it runs out",
        "owner": username or "admin",
        "due_date": today,
        "amount": 32,
        "report_date": today,
    }, username)
    _mark(store, "action", purchase["id"])
    return {
        "sales": 215000.0,
        "receipts": 15000.0,
        "outstanding": 105000.0,
        "as_of": today,
    }


def _rebuild_report(store, username, report_date):
    from server.jobs import enqueue_run, run_job
    run_id, err = enqueue_run(
        store,
        {"core": True},
        report_date,
        perms=None,
    )
    if err or not run_id:
        return {"id": "", "status": "failed", "message": err or "Could not start the demo report."}
    store.update_run(run_id, {"demo": True})
    try:
        run_job(store, run_id)
    except Exception as exc:
        store.update_run(run_id, {"demo": True, "status": "failed", "message": str(exc)})
    doc = store.get_run(run_id) or {}
    store.update_run(run_id, {"demo": True})
    return {
        "id": run_id,
        "status": doc.get("status") or "",
        "message": doc.get("message") or "",
        "report_date": str(doc.get("report_date") or report_date)[:10],
    }


def demo_status(store):
    policy = get_org_policy(store)
    rows = [row for row in (store.list_rows() or []) if _is_demo(row)]
    runs = [row for row in (store.list_runs() or []) if row.get("demo") and row.get("status") == "succeeded"]
    return {
        "labeled": True,
        "company_name": policy.get("company_name") or "",
        "present": bool(rows),
        "blocked": has_customer_data(store),
        "scenarios": list(SCENARIOS),
        "report_id": (runs[0].get("_id") if runs else "") or "",
        "report_date": str((runs[0].get("report_date") if runs else "") or "")[:10],
    }


def open_demo(store, username):
    if has_customer_data(store):
        raise ValueError("Demo reset is blocked because this company already has imported data.")
    policy = get_org_policy(store)
    if not (policy.get("company_name") or "").strip():
        save_org_policy(store, {"company_name": DEMO_COMPANY})
    _clear_demo(store)
    totals = _seed_rows(store, username or "admin")
    report = _rebuild_report(store, username, totals["as_of"])
    status = demo_status(store)
    status["control_totals"] = totals
    status["report"] = report
    return status
