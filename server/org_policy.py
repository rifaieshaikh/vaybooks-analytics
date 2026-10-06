"""Organization policy and expense category settings (Phase 0)."""

from __future__ import annotations

import json

from vay.dates import DEFAULT_TIMEZONE, default_org_policy, normalize_fy_start_month
from vay.packs import DEFAULT_EXPENSE_PACK, default_expense_account_map

SETTING_TYPE = "app_setting"
ORG_POLICY_UK = "org_policy"
EXPENSE_UK = "expense_categories"


def _fields(store, uk):
    row = store.find_row(SETTING_TYPE, uk)
    if not row:
        return {}
    return dict(row.get("fields") or {})


def _parse_json(raw, fallback):
    if raw is None or raw == "":
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _parse_columns(raw):
    data = _parse_json(raw, [])
    out = []
    if isinstance(data, dict):
        data = [{"entity": key, "header": value} for key, value in data.items()]
    if not isinstance(data, list):
        return []
    for item in data:
        if not isinstance(item, dict):
            continue
        entity = str(item.get("entity") or "").strip()
        header = str(item.get("header") or "").strip()
        if entity in ("customer", "product") and header:
            out.append({"entity": entity, "header": header})
    return out


def _flag(raw):
    if isinstance(raw, bool):
        return raw
    return str(raw or "").strip().lower() in ("1", "true", "yes", "on")


def _parse_targets(raw):
    data = _parse_json(raw, {})
    if not isinstance(data, dict):
        return {}
    out = {}
    for key, value in data.items():
        if value in ("", None):
            continue
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def normalize_terminology(raw):
    base = default_org_policy()["terminology"]
    if not isinstance(raw, dict):
        return dict(base)
    out = dict(base)
    for key in base:
        val = raw.get(key)
        if val is not None and str(val).strip():
            out[key] = str(val).strip()
    return out


def normalize_expense_map(raw):
    if not isinstance(raw, dict):
        return default_expense_account_map()
    out = {}
    for category, names in raw.items():
        cat = str(category).strip()
        if not cat:
            continue
        if isinstance(names, list):
            out[cat] = [str(n).strip() for n in names if str(n).strip()]
        elif isinstance(names, str) and names.strip():
            out[cat] = [names.strip()]
    return out if out else default_expense_account_map()


def normalize_ar_balance_tolerance(raw, default=0.50):
    if raw in ("", None):
        raw = default
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("ar_balance_tolerance must be a number") from exc
    if value < 0:
        raise ValueError("ar_balance_tolerance must be 0 or more")
    return round(value, 2)


def get_org_policy(store):
    defaults = default_org_policy()
    fields = _fields(store, ORG_POLICY_UK)
    fy = normalize_fy_start_month(fields.get("FiscalYearStartMonth") or fields.get("fiscal_year_start_month"))
    try:
        tax = float(fields.get("SalesTaxInclusiveRate") or fields.get("sales_tax_inclusive_rate") or defaults["sales_tax_inclusive_rate"])
    except (TypeError, ValueError):
        tax = defaults["sales_tax_inclusive_rate"]
    try:
        tolerance = normalize_ar_balance_tolerance(
            fields.get("ArBalanceTolerance")
            if fields.get("ArBalanceTolerance") not in ("", None)
            else fields.get("ar_balance_tolerance"),
            defaults["ar_balance_tolerance"],
        )
    except ValueError:
        tolerance = defaults["ar_balance_tolerance"]
    terminology = normalize_terminology(
        _parse_json(fields.get("Terminology") or fields.get("terminology"), defaults["terminology"])
    )
    return {
        "fiscal_year_start_month": fy,
        "timezone": (fields.get("Timezone") or fields.get("timezone") or defaults["timezone"]).strip() or DEFAULT_TIMEZONE,
        "currency_code": (fields.get("CurrencyCode") or fields.get("currency_code") or defaults["currency_code"]).strip() or "INR",
        "currency_symbol": (fields.get("CurrencySymbol") or fields.get("currency_symbol") or defaults["currency_symbol"]) or "₹",
        "sales_tax_inclusive_rate": tax,
        "ar_balance_tolerance": tolerance,
        "expense_pack": (fields.get("ExpensePack") or fields.get("expense_pack") or DEFAULT_EXPENSE_PACK).strip() or DEFAULT_EXPENSE_PACK,
        "terminology": terminology,
        "targets": _parse_targets(fields.get("Targets") or fields.get("targets")),
        "thresholds": _parse_targets(fields.get("Thresholds") or fields.get("thresholds")),
        "weekly_run": _flag(fields.get("WeeklyRun") if fields.get("WeeklyRun") not in ("", None) else fields.get("weekly_run")),
        "last_weekly_report_date": str(fields.get("LastWeeklyReportDate") or fields.get("last_weekly_report_date") or "")[:10],
        "wholesale_pack": _flag(fields.get("WholesalePack") if fields.get("WholesalePack") not in ("", None) else fields.get("wholesale_pack")),
        "retail_pack": _flag(fields.get("RetailPack") if fields.get("RetailPack") not in ("", None) else fields.get("retail_pack")),
        "custom_columns": _parse_columns(fields.get("CustomColumns") or fields.get("custom_columns")),
        "entitlements": _parse_json(fields.get("Entitlements") or fields.get("entitlements"), {}),
    }


def save_org_policy(store, body):
    body = body or {}
    current = get_org_policy(store)
    fy = normalize_fy_start_month(body.get("fiscal_year_start_month", current["fiscal_year_start_month"]))
    try:
        tax = float(body.get("sales_tax_inclusive_rate", current["sales_tax_inclusive_rate"]))
    except (TypeError, ValueError) as exc:
        raise ValueError("sales_tax_inclusive_rate must be a number") from exc
    if tax < 0 or tax > 1:
        raise ValueError("sales_tax_inclusive_rate must be between 0 and 1")
    tolerance = normalize_ar_balance_tolerance(
        body.get("ar_balance_tolerance", current["ar_balance_tolerance"]),
        current["ar_balance_tolerance"],
    )
    terminology = normalize_terminology(body.get("terminology", current["terminology"]))
    if body.get("targets") is None:
        targets = current.get("targets") or {}
    else:
        targets = _parse_targets(body.get("targets"))
    if body.get("thresholds") is None:
        thresholds = current.get("thresholds") or {}
    else:
        thresholds = _parse_targets(body.get("thresholds"))
    if body.get("weekly_run") is None:
        weekly_run = bool(current.get("weekly_run"))
    else:
        weekly_run = _flag(body.get("weekly_run"))
    if body.get("last_weekly_report_date") is None:
        last_weekly = current.get("last_weekly_report_date") or ""
    else:
        last_weekly = str(body.get("last_weekly_report_date") or "")[:10]
    if body.get("wholesale_pack") is None:
        wholesale_pack = bool(current.get("wholesale_pack"))
    else:
        wholesale_pack = _flag(body.get("wholesale_pack"))
    if body.get("retail_pack") is None:
        retail_pack = bool(current.get("retail_pack"))
    else:
        retail_pack = _flag(body.get("retail_pack"))
    if body.get("custom_columns") is None:
        custom_columns = current.get("custom_columns") or []
    else:
        custom_columns = _parse_columns(body.get("custom_columns"))
    if body.get("entitlements") is None:
        entitlements = current.get("entitlements") or {}
    else:
        raw_ent = body.get("entitlements")
        entitlements = raw_ent if isinstance(raw_ent, dict) else {}
    timezone = (body.get("timezone") or current["timezone"] or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    currency_code = (body.get("currency_code") or current["currency_code"] or "INR").strip() or "INR"
    currency_symbol = body.get("currency_symbol")
    if currency_symbol is None:
        currency_symbol = current["currency_symbol"]
    currency_symbol = str(currency_symbol) if currency_symbol is not None else "₹"
    expense_pack = (body.get("expense_pack") or current["expense_pack"] or DEFAULT_EXPENSE_PACK).strip() or DEFAULT_EXPENSE_PACK
    fields = {
        "FiscalYearStartMonth": str(fy),
        "Timezone": timezone,
        "CurrencyCode": currency_code,
        "CurrencySymbol": currency_symbol,
        "SalesTaxInclusiveRate": str(tax),
        "ArBalanceTolerance": str(tolerance),
        "ExpensePack": expense_pack,
        "Terminology": json.dumps(terminology),
        "Targets": json.dumps(targets),
        "Thresholds": json.dumps(thresholds),
        "WeeklyRun": "1" if weekly_run else "0",
        "LastWeeklyReportDate": last_weekly,
        "WholesalePack": "1" if wholesale_pack else "0",
        "RetailPack": "1" if retail_pack else "0",
        "CustomColumns": json.dumps(custom_columns),
        "Entitlements": json.dumps(entitlements if isinstance(entitlements, dict) else {}),
    }
    store.upsert_row({
        "type": SETTING_TYPE,
        "uk": ORG_POLICY_UK,
        "source_upload_id": "",
        "fields": fields,
    })
    return get_org_policy(store)


def get_expense_categories(store):
    fields = _fields(store, EXPENSE_UK)
    raw = fields.get("Categories") or fields.get("categories")
    if not raw:
        seeded = default_expense_account_map()
        save_expense_categories(store, seeded, pack=DEFAULT_EXPENSE_PACK)
        return {"categories": seeded, "pack": DEFAULT_EXPENSE_PACK, "seeded": True}
    categories = normalize_expense_map(_parse_json(raw, None))
    pack = (fields.get("Pack") or fields.get("pack") or DEFAULT_EXPENSE_PACK).strip() or DEFAULT_EXPENSE_PACK
    return {"categories": categories, "pack": pack, "seeded": False}


def save_expense_categories(store, categories, pack=None):
    categories = normalize_expense_map(categories)
    pack = (pack or DEFAULT_EXPENSE_PACK).strip() or DEFAULT_EXPENSE_PACK
    store.upsert_row({
        "type": SETTING_TYPE,
        "uk": EXPENSE_UK,
        "source_upload_id": "",
        "fields": {
            "Categories": json.dumps(categories),
            "Pack": pack,
        },
    })
    return {"categories": categories, "pack": pack, "seeded": False}


def org_policy_for_generate(store):
    """Policy dict passed into vay.engine.generate."""
    policy = get_org_policy(store)
    expense = get_expense_categories(store)
    policy["payment_categories"] = expense["categories"]
    policy["expense_pack"] = expense.get("pack") or policy.get("expense_pack")
    policy["customer_accounts"] = list(collection_customer_keys(store))
    return policy


def collection_customer_keys(store):
    """Account Name keys (lowercase) that may count toward collection."""
    from vay.dates import clean_text
    from server.customers import CUSTOMER_PARTY_TYPE

    keys = set()
    for row in store.rows_of_type("customer"):
        fields = row.get("fields") or {}
        name = clean_text(fields.get("Account Name") or fields.get("Party Name"))
        if name:
            keys.add(name.lower())
    for row in store.rows_of_type("party"):
        fields = row.get("fields") or {}
        if clean_text(fields.get("Party Type")) != CUSTOMER_PARTY_TYPE:
            continue
        name = clean_text(fields.get("Account Name") or fields.get("Party Name"))
        if name:
            keys.add(name.lower())
    return keys
