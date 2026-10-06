"""Saved report definitions, wholesale templates, and dataset rows."""

from __future__ import annotations

import json
import uuid

from vay.config import DEFAULT_PARTY, TEXT_HEADERS
from vay.dates import between_, build_report_context, clean_text, number_, parse_date
from vay.domain import METRIC_IDS
from vay.phase2 import period_windows, stock_decisions
from vay.phase4 import COMPARISONS, DIMENSIONS, METRIC_META, TEMPLATES, run_definition
from vay.row_defaults import real_group

from server.org_policy import SETTING_TYPE, get_org_policy, save_org_policy
from server.phase2 import _accounts, _item_rows, _prepare_tables, _stock_rows

REPORT_TYPE = "saved_report"


def _dump(value):
    return json.dumps(value if value is not None else [])


def _load(raw, fallback):
    if raw in ("", None):
        return fallback
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _flag(raw):
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def _public(doc):
    fields = dict((doc or {}).get("fields") or {})
    return {
        "id": doc.get("uk") or "",
        "name": fields.get("name") or "",
        "metric_ids": _load(fields.get("metric_ids"), []),
        "dimension": fields.get("dimension") or "customer",
        "filters": _load(fields.get("filters"), []),
        "comparison": fields.get("comparison") or "current",
        "status": fields.get("status") or "draft",
        "owner": fields.get("owner") or "",
        "schedule": _flag(fields.get("schedule")),
        "template_id": fields.get("template_id") or "",
        "custom_column": fields.get("custom_column") or "",
        "show_pack_size": _flag(fields.get("show_pack_size")),
        "row_filter": fields.get("row_filter") or "",
    }


def list_definitions(store):
    rows = [_public(doc) for doc in store.rows_of_type(REPORT_TYPE) or []]
    rows.sort(key=lambda row: (row.get("name") or "").lower())
    return rows


def get_definition(store, report_id):
    doc = store.find_row(REPORT_TYPE, report_id)
    if not doc:
        return None
    return _public(doc)


def _clean_metrics(raw):
    found = []
    for mid in raw or []:
        mid = str(mid or "").strip()
        if mid in METRIC_IDS and mid not in found:
            found.append(mid)
    if not found:
        raise ValueError("Choose at least one metric")
    return found


def _clean_filters(raw):
    out = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "name").strip() or "name"
        value = str(item.get("value") or "").strip()
        if value:
            out.append({"field": field, "value": value})
    return out


def validate_definition(body):
    body = body or {}
    name = clean_text(body.get("name"))
    if not name:
        raise ValueError("Name is required")
    dimension = str(body.get("dimension") or "customer").strip()
    if dimension not in DIMENSIONS:
        raise ValueError("Grouping must be customer, product, sales rep, group, or location")
    comparison = str(body.get("comparison") or "current").strip()
    if comparison not in COMPARISONS:
        raise ValueError("Comparison must be current, prior, or prior year")
    row_filter = str(body.get("row_filter") or "").strip()
    if row_filter and row_filter not in ("short_cover", "repeat", "returns"):
        raise ValueError("Unknown row filter")
    return {
        "name": name,
        "metric_ids": _clean_metrics(body.get("metric_ids")),
        "dimension": dimension,
        "filters": _clean_filters(body.get("filters")),
        "comparison": comparison,
        "schedule": bool(body.get("schedule")),
        "template_id": str(body.get("template_id") or "").strip(),
        "custom_column": clean_text(body.get("custom_column")),
        "show_pack_size": bool(body.get("show_pack_size")),
        "row_filter": row_filter,
    }


def _store_fields(cleaned, owner, status):
    return {
        "name": cleaned["name"],
        "metric_ids": _dump(cleaned["metric_ids"]),
        "dimension": cleaned["dimension"],
        "filters": _dump(cleaned["filters"]),
        "comparison": cleaned["comparison"],
        "status": status,
        "owner": owner,
        "schedule": "1" if cleaned["schedule"] else "0",
        "template_id": cleaned["template_id"],
        "custom_column": cleaned["custom_column"],
        "show_pack_size": "1" if cleaned["show_pack_size"] else "0",
        "row_filter": cleaned["row_filter"],
    }


def create_definition(store, body, username):
    cleaned = validate_definition(body)
    uk = uuid.uuid4().hex
    store.upsert_row({
        "type": REPORT_TYPE,
        "uk": uk,
        "source_upload_id": "",
        "fields": _store_fields(cleaned, username or "", "draft"),
    })
    return get_definition(store, uk)


def update_definition(store, report_id, body, username):
    current = get_definition(store, report_id)
    if not current:
        return None
    cleaned = validate_definition(body)
    status = current["status"] if current["status"] == "approved" else "draft"
    store.upsert_row({
        "type": REPORT_TYPE,
        "uk": report_id,
        "source_upload_id": "",
        "fields": _store_fields(cleaned, current.get("owner") or username or "", status),
    })
    return get_definition(store, report_id)


def approve_definition(store, report_id):
    current = get_definition(store, report_id)
    if not current:
        return None
    doc = store.find_row(REPORT_TYPE, report_id)
    fields = dict(doc.get("fields") or {})
    fields["status"] = "approved"
    store.upsert_row({
        "type": REPORT_TYPE,
        "uk": report_id,
        "source_upload_id": "",
        "fields": fields,
    })
    return get_definition(store, report_id)


def visible_to(user, definition):
    perms = set((user or {}).get("permissions") or [])
    if "reports.manage" in perms:
        return True
    if (definition or {}).get("status") != "approved":
        return False
    for mid in definition.get("metric_ids") or []:
        family = (METRIC_META.get(mid) or {}).get("family") or "scorecard"
        if "reports.view.%s" % family not in perms:
            return False
    return True


def _copy_templates(store, username, templates, flag):
    from server.hosted import pack_enabled
    pack = "wholesale" if flag == "wholesale_pack" else "retail"
    if not pack_enabled(store, pack):
        raise ValueError("Pack is not enabled for this organization")
    save_org_policy(store, {flag: True})
    existing = {row.get("template_id") for row in list_definitions(store) if row.get("template_id")}
    created = []
    for template in templates:
        if template["id"] in existing:
            continue
        payload = dict(template)
        payload["template_id"] = template["id"]
        created.append(create_definition(store, payload, username))
    return created


def adopt_pack(store, username):
    """Copy wholesale templates as drafts. Does not require Vay expense account names."""
    return _copy_templates(store, username, TEMPLATES, "wholesale_pack")


def adopt_retail_pack(store, username):
    """Copy retail templates as drafts. Does not replace wholesale drafts or Vay expense names."""
    from vay.packs.retail import TEMPLATES as RETAIL_TEMPLATES
    return _copy_templates(store, username, RETAIL_TEMPLATES, "retail_pack")


def _window_key(when, windows):
    for key in ("current", "prior", "prior_year"):
        window = windows[key]
        if between_(when, window["start"], window["end"]):
            return key
    return ""


def _add_amount(bucket, key, amount):
    if not key:
        return
    if bucket.get(key) is None:
        bucket[key] = 0.0
    bucket[key] = round(bucket[key] + amount, 2)


def _blank_periods():
    return {"current": None, "prior": None, "prior_year": None}


def _sum_periods(parts):
    out = _blank_periods()
    for key in out:
        seen = [part.get(key) for part in parts if part.get(key) is not None]
        if seen:
            out[key] = round(sum(seen), 2)
    return out


def _party_key(name):
    text = clean_text(name)
    if not text or text == DEFAULT_PARTY:
        return ""
    return text.lower()


def _custom_value(store, entity, header, name):
    if not header or not name:
        return ""
    types = ("party", "customer", "sales", "arr") if entity == "customer" else ("stock", "items")
    for type_name in types:
        for doc in store.rows_of_type(type_name) or []:
            fields = doc.get("fields") or {}
            if entity == "product":
                label = clean_text(fields.get("Item Name"))
            else:
                label = clean_text(fields.get("Party Name") or fields.get("Account Name"))
            if label.lower() != name.lower():
                continue
            value = fields.get(header)
            if value not in ("", None):
                return value
    return ""


def _pack_sizes(store):
    sizes = {}
    for doc in store.rows_of_type("stock") or []:
        fields = doc.get("fields") or {}
        name = clean_text(fields.get("Item Name"))
        raw = fields.get("Pack Size")
        if raw in ("", None):
            raw = fields.get("Pack")
        if name and raw not in ("", None):
            sizes[name.lower()] = raw
    try:
        from server.reorder import _load
        proposal = _load(store) or {}
    except Exception:
        proposal = {}
    for line in proposal.get("lines") or []:
        name = clean_text(line.get("name"))
        raw = line.get("pack_size")
        if name and raw not in ("", None, 0) and name.lower() not in sizes:
            sizes[name.lower()] = raw
    return sizes


def _account_periods(account, windows):
    sales = _blank_periods()
    collections = _blank_periods()
    for inv in account.get("invoices") or []:
        _add_amount(sales, _window_key(inv.get("date"), windows), float(inv.get("amount") or 0))
    for credit in account.get("credits") or []:
        _add_amount(sales, _window_key(credit.get("date"), windows), -float(credit.get("amount") or 0))
    for rec in account.get("receipts") or []:
        _add_amount(collections, _window_key(rec.get("date"), windows), float(rec.get("amount") or 0))
    return sales, collections


def _priority(account):
    overdue = float(account.get("overdue30") or account.get("bal30Plus") or 0)
    mid = float(account.get("overdue15") or account.get("bal15Plus") or 0)
    balance = float(account.get("balance") or 0)
    if balance <= 0:
        return None
    if overdue > 0:
        return 3
    if mid > 0:
        return 2
    return 1


def _margin_for(name, item_rows, costs, windows, tax_rate):
    margin = _blank_periods()
    reasons = {}
    rate = float(tax_rate or 0)
    for key, window in windows.items():
        sales = 0.0
        cogs = 0.0
        seen = False
        missing = False
        for row in item_rows or []:
            if (row.get("name") or "").strip().lower() != name.lower():
                continue
            if not between_(row.get("date"), window["start"], window["end"]):
                continue
            qty = row.get("qty")
            price = row.get("rate")
            if qty is None or price is None:
                continue
            seen = True
            cost = costs.get(name)
            if cost is None:
                missing = True
                break
            sales += float(qty) * float(price)
            cogs += float(qty) * float(cost)
        if not seen:
            continue
        if missing or sales == 0:
            reasons[key] = "Missing item cost" if missing else ""
            continue
        net = sales / (1 + rate) if rate else sales
        if net:
            margin[key] = round(100.0 * (net - cogs) / net, 1)
    return margin, reasons


def build_members(store, report_date, dimension, custom_column):
    ctx, tables, policy, _ids = _accounts(store, report_date)
    windows = period_windows(report_date)
    accounts = ctx.get("accounts") or []
    fy = build_report_context(parse_date(report_date) or report_date, org_policy=policy)
    item_rows = _item_rows(tables)
    stock_rows = _stock_rows(tables)
    stock = stock_decisions(item_rows, stock_rows, report_date)
    packs = _pack_sizes(store)
    costs = {}
    for row in stock_rows:
        if row.get("name") and row.get("cost") is not None:
            costs[row["name"]] = row["cost"]
    inactive = set()
    movement_of = {}
    from vay.phase2 import customer_movement
    for row in (customer_movement(accounts, report_date).get("rows") or []):
        movement_of[(row.get("name") or "").lower()] = row.get("movement") or ""
        if row.get("movement") == "inactive":
            inactive.add((row.get("name") or "").lower())

    customers = []
    rep_of = {}
    for account in accounts:
        name = clean_text(account.get("name"))
        if not _party_key(name):
            continue
        sales, collections = _account_periods(account, windows)
        returns = _blank_periods()
        for credit in account.get("credits") or []:
            _add_amount(returns, _window_key(credit.get("date"), windows), float(credit.get("amount") or 0))
        ytd = None
        ytd_seen = False
        ytd_total = 0.0
        for inv in account.get("invoices") or []:
            when = inv.get("date")
            if when and between_(when, fy["fiscalYearStart"], fy["reportDate"]):
                ytd_seen = True
                ytd_total += float(inv.get("amount") or 0)
        for credit in account.get("credits") or []:
            when = credit.get("date")
            if when and between_(when, fy["fiscalYearStart"], fy["reportDate"]):
                ytd_seen = True
                ytd_total -= float(credit.get("amount") or 0)
        if ytd_seen:
            ytd = round(ytd_total, 2)
        salesperson = clean_text(account.get("salesperson"))
        if salesperson:
            rep_of[name.lower()] = salesperson
        balance = account.get("balance")
        balance = None if balance in ("", None) else round(float(balance), 2)
        overdue = account.get("overdue30")
        if overdue in ("", None) and balance is None:
            overdue_value = None
        else:
            overdue_value = round(float(overdue or 0), 2) if balance is not None else None
        customers.append({
            "name": name,
            "salesperson": salesperson,
            "group": real_group(account.get("group")),
            "sales": sales,
            "collections": collections,
            "ytd": ytd,
            "balance": balance,
            "overdue_30": overdue_value,
            "priority": _priority(account),
            "inactive": 1 if name.lower() in inactive else None,
            "movement": movement_of.get(name.lower()) or "",
            "returns": returns,
            "pack_size": "",
            "custom": _custom_value(store, "customer", custom_column, name) if dimension != "product" else "",
        })

    if dimension == "customer":
        return customers
    if dimension == "group":
        return _group_members(customers)
    if dimension == "sales_rep":
        return _rep_members(store, tables, windows, customers, rep_of, fy, custom_column if dimension != "product" else "")
    if dimension == "location":
        return _location_members(tables, windows, fy["reportDate"])
    return _product_members(store, item_rows, stock, costs, windows, policy, packs, custom_column)


def _location_members(tables, windows, report_end):
    """Sales by Location. A blank location is left out."""
    buckets = {}

    def slot(place):
        place = clean_text(place)
        if not place:
            return None
        return buckets.setdefault(place, _blank_periods())

    sales = tables.get("sales")
    if sales is not None and "Location" in getattr(sales, "index", {}):
        for row in sales.rows:
            when = sales.get(row, "Date")
            when = when if hasattr(when, "year") else parse_date(when)
            if not when or when > report_end:
                continue
            target = slot(sales.get(row, "Location"))
            if not target:
                continue
            _add_amount(target, _window_key(when, windows), number_(sales.get(row, "Net Amount")))
    notes = tables.get("credit_note")
    if notes is not None and "Location" in getattr(notes, "index", {}) and "Net Amount" in notes.index:
        for row in notes.rows:
            when = notes.get(row, "Date")
            when = when if hasattr(when, "year") else parse_date(when)
            amount = number_(notes.get(row, "Net Amount"))
            if not when or amount <= 0 or when > report_end:
                continue
            target = slot(notes.get(row, "Location"))
            if not target:
                continue
            _add_amount(target, _window_key(when, windows), -amount)
    out = []
    for name, periods in buckets.items():
        out.append({
            "name": name,
            "salesperson": "",
            "group": "",
            "sales": periods,
            "collections": _blank_periods(),
            "ytd": None,
            "balance": None,
            "overdue_30": None,
            "priority": None,
            "inactive": None,
            "movement": "",
            "returns": _blank_periods(),
            "pack_size": "",
            "custom": "",
        })
    return out


def _group_members(customers):
    buckets = {}
    for row in customers:
        group = row.get("group") or ""
        if not group:
            continue
        slot = buckets.setdefault(group, [])
        slot.append(row)
    out = []
    for name, rows in buckets.items():
        out.append(_combine(name, rows, group=name))
    return out


def _combine(name, rows, salesperson="", group=""):
    inactive = sum(1 for row in rows if row.get("inactive"))
    balances = [row.get("balance") for row in rows if row.get("balance") is not None]
    overdue = [row.get("overdue_30") for row in rows if row.get("overdue_30") is not None]
    priorities = [row.get("priority") for row in rows if row.get("priority") is not None]
    ytds = [row.get("ytd") for row in rows if row.get("ytd") is not None]
    return {
        "name": name,
        "salesperson": salesperson,
        "group": group,
        "sales": _sum_periods([row.get("sales") or {} for row in rows]),
        "collections": _sum_periods([row.get("collections") or {} for row in rows]),
        "ytd": round(sum(ytds), 2) if ytds else None,
        "balance": round(sum(balances), 2) if balances else None,
        "overdue_30": round(sum(overdue), 2) if overdue else None,
        "priority": max(priorities) if priorities else None,
        "inactive": inactive or None,
        "pack_size": "",
        "custom": "",
    }


def _rep_members(store, tables, windows, customers, rep_of, fy, custom_column):
    buckets = {}

    def slot(rep):
        rep = clean_text(rep)
        if not rep:
            return None
        return buckets.setdefault(rep, {
            "sales": _blank_periods(),
            "collections": _blank_periods(),
            "ytd": None,
            "customers": [],
        })

    sales = tables.get("sales")
    if sales and "Sales Rep" in sales.index:
        for row in sales.rows:
            when = sales.get(row, "Date")
            when = when if hasattr(when, "year") else parse_date(when)
            if not when or when > fy["reportDate"]:
                continue
            party = clean_text(sales.get(row, "Party Name"))
            rep = clean_text(sales.get(row, "Sales Rep")) or rep_of.get(party.lower(), "")
            target = slot(rep)
            if not target or not _party_key(party):
                continue
            amount = number_(sales.get(row, "Net Amount"))
            _add_amount(target["sales"], _window_key(when, windows), amount)
            if between_(when, fy["fiscalYearStart"], fy["reportDate"]):
                target["ytd"] = round(float(target["ytd"] or 0) + amount, 2)
    notes = tables.get("credit_note")
    if notes and "Net Amount" in notes.index:
        for row in notes.rows:
            when = notes.get(row, "Date")
            when = when if hasattr(when, "year") else parse_date(when)
            amount = number_(notes.get(row, "Net Amount"))
            if not when or amount <= 0 or when > fy["reportDate"]:
                continue
            party = clean_text(notes.get(row, "Party Name"))
            rep = rep_of.get(party.lower(), "")
            target = slot(rep)
            if not target:
                continue
            _add_amount(target["sales"], _window_key(when, windows), -amount)
            if between_(when, fy["fiscalYearStart"], fy["reportDate"]):
                target["ytd"] = round(float(target["ytd"] or 0) - amount, 2)
    receipts = tables.get("receipt")
    if receipts and "Sales Rep" in receipts.index:
        for row in receipts.rows:
            when = receipts.get(row, "Date")
            when = when if hasattr(when, "year") else parse_date(when)
            if not when or when > fy["reportDate"]:
                continue
            target = slot(receipts.get(row, "Sales Rep"))
            if not target:
                continue
            _add_amount(target["collections"], _window_key(when, windows), number_(receipts.get(row, "Amount")))
    by_rep = {}
    for row in customers:
        rep = row.get("salesperson") or ""
        if rep:
            by_rep.setdefault(rep, []).append(row)
            slot(rep)
    out = []
    for name, data in buckets.items():
        combined = _combine(name, by_rep.get(name) or [], salesperson=name)
        combined["sales"] = data["sales"]
        combined["collections"] = data["collections"]
        combined["ytd"] = data["ytd"]
        combined["custom"] = ""
        out.append(combined)
    return out


def _qty_periods(item_rows, name, windows):
    qty = _blank_periods()
    for row in item_rows or []:
        if (row.get("name") or "").strip().lower() != name.lower():
            continue
        amount = row.get("qty")
        if amount is None:
            continue
        _add_amount(qty, _window_key(row.get("date"), windows), float(amount))
    return qty


def _product_members(store, item_rows, stock, costs, windows, policy, packs, custom_column):
    out = []
    tax = policy.get("sales_tax_inclusive_rate")
    for row in stock.get("rows") or []:
        name = row.get("name") or ""
        if not name:
            continue
        margin, reasons = _margin_for(name, item_rows, costs, windows, tax)
        sales = _blank_periods()
        for item in item_rows or []:
            if (item.get("name") or "").strip().lower() != name.lower():
                continue
            qty = item.get("qty")
            price = item.get("rate")
            if qty is None or price is None:
                continue
            _add_amount(sales, _window_key(item.get("date"), windows), float(qty) * float(price))
        slow_reason = ""
        if row.get("slow") and row.get("slow_value") is None:
            slow_reason = "Missing item cost"
        out.append({
            "name": name,
            "salesperson": "",
            "group": "",
            "sales": sales,
            "collections": _blank_periods(),
            "ytd": None,
            "balance": None,
            "overdue_30": None,
            "priority": None,
            "inactive": None,
            "qty": _qty_periods(item_rows, name, windows),
            "cover_days": row.get("cover_days"),
            "cover_label": row.get("cover_label") or "",
            "slow_value": row.get("slow_value"),
            "slow_reason": slow_reason,
            "margin": margin,
            "margin_reason": reasons,
            "pack_size": packs.get(name.lower(), ""),
            "custom": _custom_value(store, "product", custom_column, name),
        })
    return out


def execute(store, definition, report_date):
    policy = get_org_policy(store)
    limit = (policy.get("thresholds") or {}).get("cover_days")
    if limit in ("", None):
        limit = 30
    from vay.eligibility import evaluate
    eligibility = evaluate(store, str(report_date)[:10])
    members = build_members(store, report_date, definition.get("dimension") or "customer", definition.get("custom_column") or "")
    result = run_definition(members, definition, eligibility, cover_limit=limit)
    result["report_date"] = str(report_date)[:10]
    result["name"] = definition.get("name") or ""
    return result


def dataset_csv(result):
    lines = ["name,metric,value,status,reason,metric_version"]
    versions = result.get("metric_versions") or {}
    labels = {row["id"]: row.get("label") or row["id"] for row in result.get("metrics") or []}
    for row in result.get("rows") or []:
        for mid, cell in (row.get("cells") or {}).items():
            value = "" if cell.get("value") is None else cell.get("value")
            reason = (cell.get("reason") or "").replace('"', "'")
            lines.append('"%s","%s","%s","%s","%s",%s' % (
                (row.get("name") or "").replace('"', "'"),
                labels.get(mid, mid),
                value,
                cell.get("status") or "",
                reason,
                versions.get(mid, ""),
            ))
    if result.get("show_pack_size"):
        for row in result.get("rows") or []:
            lines.append('"%s","Pack size","%s","eligible","",' % (
                (row.get("name") or "").replace('"', "'"),
                "" if row.get("pack_size") in (None, "") else row.get("pack_size"),
            ))
    return "\n".join(lines) + "\n"


def scheduled_sheets(store, report_date):
    """Sheets for approved reports marked for the weekly run. Does not create a run."""
    sheets = []
    for definition in list_definitions(store):
        if definition.get("status") != "approved" or not definition.get("schedule"):
            continue
        try:
            result = execute(store, definition, report_date)
        except (TypeError, ValueError):
            continue
        name_header = {
            "sales_rep": "Sales Rep",
            "product": "Item",
            "group": "Group",
        }.get(definition.get("dimension"), "Customer")
        headers = [name_header]
        for metric in result.get("metrics") or []:
            headers.append(metric.get("label") or metric["id"])
        headers.append("Reason")
        if result.get("show_pack_size"):
            headers.append("Pack size")
        if result.get("custom_column"):
            headers.append(result["custom_column"])
            TEXT_HEADERS.add(result["custom_column"])
        rows = []
        for row in result.get("rows") or []:
            line = [row.get("name") or ""]
            reasons = []
            for metric in result.get("metrics") or []:
                cell = (row.get("cells") or {}).get(metric["id"]) or {}
                if cell.get("status") == "unavailable" or cell.get("value") is None:
                    line.append("")
                    if cell.get("reason"):
                        reasons.append("%s: %s" % (metric.get("label") or metric["id"], cell.get("reason")))
                else:
                    line.append(cell.get("value"))
            line.append("; ".join(reasons))
            if result.get("show_pack_size"):
                line.append("" if row.get("pack_size") in (None, "") else row.get("pack_size"))
            if result.get("custom_column"):
                line.append(row.get("custom") or "")
            rows.append(line)
        if not rows:
            reason = ""
            for metric in result.get("metrics") or []:
                if metric.get("reason"):
                    reason = metric["reason"]
                    break
            rows.append([reason or "No rows"] + [""] * (len(headers) - 1))
        sheets.append({
            "id": "saved_%s" % definition["id"][:12],
            "title": definition.get("name") or "Saved report",
            "headers": headers,
            "rows": rows,
        })
    return sheets
