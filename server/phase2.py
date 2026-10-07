"""Load store rows into Phase 2 analytics and saved views."""

from __future__ import annotations

import json

from vay.config import REQUIRED_COLUMNS
from vay.dates import between_, build_report_context, normalize_date, number_, parse_date
from vay.phase2 import (
    collection_worklist,
    customer_movement,
    excel_reports,
    gross_margin_periods,
    onboarding_checklist,
    period_windows,
    quality_fixes,
    sales_change,
    scorecard,
    stock_decisions,
)
from vay.reports.core import account_performance
from vay.table import Table

from server.org_policy import SETTING_TYPE, get_org_policy, org_policy_for_generate
from server.tables import tables_from_store

SAVED_VIEW_PREFIX = "saved_views:"


def _empty(type_name):
    return Table(type_name, list(REQUIRED_COLUMNS.get(type_name) or []), [])


def _prepare_tables(store):
    tables = tables_from_store(store, ["sales", "receipt", "credit_note", "arr", "items", "stock"])
    for name in ("sales", "receipt", "credit_note", "arr", "items", "stock"):
        tables.setdefault(name, _empty(name))
    return tables


def _ids_by_name(store):
    found = {}
    for type_name, field in (("sales", "Party Name"), ("arr", "Account Name"), ("party", "Account Name"), ("customer", "Account Name")):
        for doc in store.rows_of_type(type_name) or []:
            fields = doc.get("fields") or {}
            name = (fields.get(field) or fields.get("Party Name") or fields.get("Account Name") or "").strip()
            cid = (fields.get("customer_id") or "").strip()
            if name and cid and name.lower() not in found:
                found[name.lower()] = cid
    return found


def _accounts(store, report_date):
    policy = org_policy_for_generate(store)
    ctx = build_report_context(parse_date(report_date) or report_date, org_policy=policy)
    from server.customers import get_aging_bands, get_settlement_mode
    ctx["settlement_mode"] = get_settlement_mode(store)
    ctx["aging_bands"] = get_aging_bands(store)
    tables = _prepare_tables(store)
    account_performance(tables, ctx)
    ids = _ids_by_name(store)
    for account in ctx.get("accounts") or []:
        account["customer_id"] = ids.get((account.get("name") or "").lower()) or ""
    return ctx, tables, policy, ids


def _dated_sales(tables, report_date):
    end = normalize_date(parse_date(report_date) or report_date)
    amounts = []
    sales = tables.get("sales")
    if sales and "Date" in sales.index and "Net Amount" in sales.index:
        for row in sales.rows:
            when = row[sales.index["Date"]]
            when = when if hasattr(when, "year") else parse_date(when)
            if not when or (end and when > end):
                continue
            amounts.append((when, number_(row[sales.index["Net Amount"]])))
    notes = tables.get("credit_note")
    if notes and "Date" in notes.index and "Net Amount" in notes.index:
        for row in notes.rows:
            when = row[notes.index["Date"]]
            when = when if hasattr(when, "year") else parse_date(when)
            amount = number_(row[notes.index["Net Amount"]])
            if not when or amount <= 0 or (end and when > end):
                continue
            amounts.append((when, -amount))
    return amounts


def _dated_collections(tables, report_date):
    end = normalize_date(parse_date(report_date) or report_date)
    amounts = []
    receipts = tables.get("receipt")
    if not receipts or "Date" not in receipts.index or "Amount" not in receipts.index:
        return amounts
    for row in receipts.rows:
        when = row[receipts.index["Date"]]
        when = when if hasattr(when, "year") else parse_date(when)
        if not when or (end and when > end):
            continue
        amounts.append((when, number_(row[receipts.index["Amount"]])))
    return amounts


def _ytd_sales(amounts, report_date, policy):
    ctx = build_report_context(parse_date(report_date) or report_date, org_policy=policy)
    total = 0.0
    seen = False
    for when, amount in amounts:
        if between_(when, ctx["fiscalYearStart"], ctx["reportDate"]):
            seen = True
            total += amount
    if not seen:
        return None
    return round(total, 2)


def _customer_periods(accounts, report_date):
    windows = period_windows(report_date)
    rows = []
    for account in accounts or []:
        current = _account_net(account, windows["current"])
        prior = _account_net(account, windows["prior"])
        rows.append({
            "name": account.get("name") or "",
            "customer_id": account.get("customer_id") or "",
            "current": current,
            "prior": prior,
        })
    return rows


def _account_net(account, window):
    seen = False
    total = 0.0
    for inv in account.get("invoices") or []:
        when = inv.get("date")
        if when and between_(when, window["start"], window["end"]):
            seen = True
            total += float(inv.get("amount") or 0)
    for credit in account.get("credits") or []:
        when = credit.get("date")
        if when and between_(when, window["start"], window["end"]):
            seen = True
            total -= float(credit.get("amount") or 0)
    if not seen:
        return None
    return round(total, 2)


def _product_periods(tables, report_date):
    windows = period_windows(report_date)
    items = tables.get("items")
    slots = {}
    if not items or "Item Name" not in items.index:
        return []
    end = normalize_date(parse_date(report_date) or report_date)
    for row in items.rows:
        name = str(items.get(row, "Item Name") or "").strip()
        when = items.get(row, "Date")
        when = when if hasattr(when, "year") else parse_date(when)
        if not name or not when or (end and when > end):
            continue
        qty = number_(items.get(row, "Qty"))
        rate = number_(items.get(row, "Rate"))
        slot = slots.setdefault(name, {"name": name, "product_id": str(items.get(row, "product_id") or ""), "q0": 0.0, "v0": 0.0, "n0": 0, "q1": 0.0, "v1": 0.0, "n1": 0})
        if between_(when, windows["prior"]["start"], windows["prior"]["end"]):
            slot["q0"] += qty
            slot["v0"] += qty * rate
            slot["n0"] += 1
        if between_(when, windows["current"]["start"], windows["current"]["end"]):
            slot["q1"] += qty
            slot["v1"] += qty * rate
            slot["n1"] += 1
    out = []
    for slot in slots.values():
        out.append({
            "name": slot["name"],
            "product_id": slot["product_id"],
            "qty_prior": slot["q0"] if slot["n0"] else None,
            "rate_prior": (slot["v0"] / slot["q0"]) if slot["n0"] and slot["q0"] else (None if not slot["n0"] else 0.0),
            "qty_current": slot["q1"] if slot["n1"] else None,
            "rate_current": (slot["v1"] / slot["q1"]) if slot["n1"] and slot["q1"] else (None if not slot["n1"] else 0.0),
        })
    return out


def _item_rows(tables):
    items = tables.get("items")
    rows = []
    if not items or "Item Name" not in items.index:
        return rows
    for row in items.rows:
        when = items.get(row, "Date")
        when = when if hasattr(when, "year") else parse_date(when)
        rows.append({
            "name": str(items.get(row, "Item Name") or "").strip(),
            "date": when,
            "qty": number_(items.get(row, "Qty")),
            "rate": number_(items.get(row, "Rate")),
            "product_id": str(items.get(row, "product_id") or ""),
        })
    return rows


def _stock_rows(tables):
    stock = tables.get("stock")
    rows = []
    if not stock or "Item Name" not in stock.index:
        return rows
    for row in stock.rows:
        raw = stock.get(row, "P.Price")
        cost = None
        if raw not in ("", None):
            try:
                cost = float(str(raw).replace(",", "").strip())
            except (TypeError, ValueError):
                cost = None
        rows.append({
            "name": str(stock.get(row, "Item Name") or "").strip(),
            "qty": number_(stock.get(row, "Qty")),
            "cost": cost,
        })
    return rows


def _costs(stock_rows):
    out = {}
    for row in stock_rows:
        if row.get("name") and row.get("cost") is not None:
            out[row["name"]] = row["cost"]
    return out


def _ar_totals(accounts):
    balance = 0.0
    overdue = 0.0
    seen = False
    for account in accounts or []:
        bal = float(account.get("balance") or 0)
        if bal == 0 and not account.get("name"):
            continue
        if account.get("balance") is None:
            continue
        seen = True
        balance += bal
        overdue += float(account.get("overdue30") or 0)
    if not seen:
        return None, None
    return round(balance, 2), round(overdue, 2)


def build_bundle(store, report_date, exceptions=None, review_count=0, prepared=None):
    from vay.eligibility import evaluate

    prepared = prepared or {}
    if prepared.get("ctx") is not None and prepared.get("tables") is not None:
        ctx = prepared["ctx"]
        tables = prepared["tables"]
        policy = prepared.get("policy") or org_policy_for_generate(store)
        ids = prepared.get("ids") or _ids_by_name(store)
    else:
        ctx, tables, policy, ids = _accounts(store, report_date)
    accounts = ctx.get("accounts") or []
    eligibility = prepared.get("eligibility")
    if eligibility is None:
        eligibility = evaluate(store, str(report_date)[:10])
    sales = _dated_sales(tables, report_date)
    collections = _dated_collections(tables, report_date)
    ar_balance, overdue = _ar_totals(accounts)
    item_rows = _item_rows(tables)
    stock_rows = _stock_rows(tables)
    stock = stock_decisions(item_rows, stock_rows, report_date)
    margin = None
    if (eligibility.get("gross_margin") or {}).get("status") == "eligible":
        margin = gross_margin_periods(item_rows, _costs(stock_rows), report_date, policy.get("sales_tax_inclusive_rate"))
    targets = (get_org_policy(store) or {}).get("targets") or {}
    bundle = {
        "report_date": str(report_date)[:10],
        "scorecard": scorecard(
            sales, collections, eligibility, targets, report_date,
            ar_balance=ar_balance, overdue=overdue, ytd_sales=_ytd_sales(sales, report_date, policy),
            margin=margin, stock=stock,
        ),
        "sales_change": sales_change(_customer_periods(accounts, report_date), _product_periods(tables, report_date)),
        "customer_movement": customer_movement(accounts, report_date, ids),
        "collection": _gate_collection(collection_worklist(accounts), eligibility),
        "stock": _attach_buy(_gate_stock(stock, eligibility), store),
        "quality": quality_fixes(exceptions, eligibility, review_count),
        "eligibility": eligibility,
    }
    return bundle


def _gate_collection(worklist, eligibility):
    state = (eligibility or {}).get("ar_balance") or {}
    if state.get("status") == "unavailable":
        return {"rows": [], "status": "unavailable", "reason": state.get("reason") or "Unavailable"}
    worklist = dict(worklist or {})
    worklist["status"] = "eligible"
    worklist["reason"] = ""
    return worklist


def _attach_buy(stock, store):
    """Copy the Item 360 buy quantity onto each stock-decision row."""
    rows = list((stock or {}).get("rows") or [])
    if not rows:
        return stock
    from server.items360 import purchase_plans
    by_name = {}
    for plan in purchase_plans(store):
        by_name[(plan.get("name") or "").strip().lower()] = plan
    attached = []
    for row in rows:
        plan = by_name.get((row.get("name") or "").strip().lower()) or {}
        item = dict(row)
        item["buy_qty"] = plan.get("buy_qty") or 0
        item["buy_by"] = plan.get("buy_by") or ""
        item["buy_by_label"] = plan.get("buy_by_label") or ""
        item["buy_reason"] = plan.get("reason") or ""
        attached.append(item)
    out = dict(stock)
    out["rows"] = attached
    return out


def _gate_stock(stock, eligibility):
    state = (eligibility or {}).get("stock_cover_days") or {}
    if state.get("status") == "unavailable":
        return {
            "rows": [],
            "cover_days": None,
            "cover_label": "",
            "slow_value": None,
            "uncosted": 0,
            "status": "unavailable",
            "reason": state.get("reason") or "Unavailable",
        }
    stock = dict(stock or {})
    stock["status"] = "eligible"
    stock["reason"] = ""
    return stock


def stock_headline(store, report_date):
    if not report_date:
        return {}
    tables = _prepare_tables(store)
    return stock_decisions(_item_rows(tables), _stock_rows(tables), report_date)


def present_source_types(store):
    found = []
    for name in ("sales", "receipt", "credit_note", "arr", "items", "stock", "payments", "party"):
        if store.rows_of_type(name):
            found.append(name)
    return found


_CONTROL_UK = "import_controls"
_CHECK_SOURCES = (
    ("sales", "Sales", "transaction"),
    ("receipt", "Receipts", "transaction"),
    ("arr", "Outstanding", "snapshot"),
    ("items", "Item sales", "transaction"),
    ("stock", "Stock", "snapshot"),
)


def _amount_sum(store, type_name, field):
    total = 0.0
    for row in store.rows_of_type(type_name) or []:
        raw = (row.get("fields") or {}).get(field)
        try:
            total += float(str(raw).replace(",", "").strip() or 0)
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def _blank_transaction_dates(store, type_name):
    rows = store.rows_of_type(type_name) or []
    missing = 0
    for row in rows:
        if not str((row.get("fields") or {}).get("Date") or "").strip():
            missing += 1
    return len(rows), missing


def _source_checklist(store, present):
    from server.settings import REQUIRED_FIELDS
    from vay.eligibility import latest_snapshot_date

    present = set(present or [])
    rows = []
    for key, label, kind in _CHECK_SOURCES:
        here = key in present
        date_value = ""
        if not here:
            date_ok = False
            note = "File not imported yet."
        elif kind == "transaction":
            count, missing = _blank_transaction_dates(store, key)
            date_ok = count > 0 and missing == 0
            if missing:
                note = "%d row%s have no transaction date." % (missing, "" if missing == 1 else "s")
            else:
                note = "Transaction dates are on the Date column."
        else:
            date_value = latest_snapshot_date(store, key)
            date_ok = bool(date_value)
            note = "Effective date %s." % date_value if date_value else "No effective date on this snapshot."
        rows.append({
            "type": key,
            "label": label,
            "present": here,
            "required_fields": list(REQUIRED_FIELDS.get(key) or []),
            "date_kind": kind,
            "date_value": date_value,
            "date_ok": date_ok,
            "date_note": note,
        })
    return rows


def _read_controls(store):
    for row in store.rows_of_type("setting") or []:
        if row.get("uk") == _CONTROL_UK:
            return dict(row.get("fields") or {})
    return {}


def _write_controls(store, fields):
    store.upsert_row({"type": "setting", "uk": _CONTROL_UK, "fields": dict(fields or {})})


def _control_entry(entered, actual):
    if entered is None:
        return {"entered": None, "actual": actual, "match": None}
    match = abs(float(entered) - float(actual)) <= 0.009
    return {"entered": float(entered), "actual": actual, "match": match}


def onboarding(store, report_date, entered=None):
    from vay.dates import today_ist
    from vay.eligibility import evaluate

    rd = str(report_date or "")[:10] or today_ist().strftime("%Y-%m-%d")
    present = present_source_types(store)
    saved = _read_controls(store)
    if entered is not None:
        for key, value in entered.items():
            if value is None:
                saved.pop(key, None)
            else:
                saved[key] = value
        _write_controls(store, saved)
    controls = {
        "sales": _control_entry(saved.get("sales"), _amount_sum(store, "sales", "Net Amount")),
        "outstanding": _control_entry(saved.get("outstanding"), _amount_sum(store, "arr", "Balance")),
    }
    eligibility = evaluate(store, rd)
    payload = onboarding_checklist(
        eligibility,
        present,
        sources=_source_checklist(store, present),
        controls=controls,
    )
    payload["report_date"] = rd
    return payload


def _stamp(value):
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat(sep=" ", timespec="seconds")
    return str(value)


def _upload_sheet_types(upload):
    """Sheet types a finished import actually wrote. An error-only upload does not count."""
    found = set()
    counts = upload.get("row_counts") or {}
    if isinstance(counts, dict):
        for key, info in counts.items():
            if isinstance(info, dict) and any(info.values()):
                found.add(str(key))
    dates = upload.get("effective_dates") or {}
    if isinstance(dates, dict):
        found.update(str(key) for key, val in dates.items() if val)
    if not found and not counts:
        named = str(upload.get("type") or "")
        if named and named != "combined":
            found.add(named)
    return found


def refresh_status(store, run):
    """Later imports of sheet types this report used. Other types stay out of the comparison."""
    run = run or {}
    version = ((run.get("manifest") or {}).get("data_version") or {})
    types_used = {str(name) for name in (version.get("types_used") or []) if name}
    live = {}
    for upload in store.list_uploads() or []:
        live[str(upload.get("_id") or "")] = upload
    included_ids = set()
    included = []
    for item in version.get("uploads") or []:
        uid = str(item.get("id") or "")
        included_ids.add(uid)
        current = live.get(uid) or {}
        sheet_types = _upload_sheet_types(current) if current else set((item.get("row_counts") or {}).keys())
        included.append({
            "id": uid,
            "filename": item.get("filename") or current.get("filename") or "",
            "types": sorted(set(sheet_types) & types_used),
            "finished_at": _stamp(item.get("finished_at") or current.get("finished_at") or current.get("created_at")),
        })
    missing = []
    for upload in store.list_uploads() or []:
        if upload.get("dry_run"):
            continue
        uid = str(upload.get("_id") or "")
        if not uid or uid in included_ids:
            continue
        used = sorted(_upload_sheet_types(upload) & types_used)
        if not used:
            continue
        missing.append({
            "id": uid,
            "filename": upload.get("filename") or "",
            "types": used,
            "finished_at": _stamp(upload.get("finished_at") or upload.get("created_at")),
        })
    return {
        "current": not missing,
        "missing": missing,
        "included": included,
        "report_finished_at": _stamp(run.get("finished_at") or run.get("created_at")),
        "types_used": sorted(types_used),
    }


def _view_uk(username):
    return SAVED_VIEW_PREFIX + (username or "").strip().lower()


def get_saved_views(store, username):
    from server.org_policy import _fields
    raw = _fields(store, _view_uk(username)).get("Views")
    if not raw:
        return {}
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_saved_view(store, username, page, filters):
    views = get_saved_views(store, username)
    page = (page or "").strip()
    if not page:
        raise ValueError("page is required")
    views[page] = filters if isinstance(filters, dict) else {}
    store.upsert_row({
        "type": SETTING_TYPE,
        "uk": _view_uk(username),
        "source_upload_id": "",
        "fields": {"Views": json.dumps(views)},
    })
    return views


def open_review_count(store):
    from server.entities import list_open_reviews
    data = list_open_reviews(store) or {}
    return len(data.get("items") or [])
