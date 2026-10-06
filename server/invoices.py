"""Sales invoices and item lines. Does not feed generate()."""

from __future__ import annotations

import base64
import re

from vay.dates import clean_text, fiscal_year_start, number_, parse_date

from server.customers import _fmt_day, _iso, account_uk
from server.settings import ROW_PAGE_CAP, ROW_PAGE_DEFAULT

# Separates invoice number from fiscal-year token inside encoded ids / scope keys.
_FY_SEP = "\x1f"

_INVOICE_HEADER = {
    "invoice no",
    "invoice number",
    "invoice",
    "bill no",
    "bill number",
    "voucher no",
    "voucher number",
    "voucher",
    "vch no",
    "inv no",
    "reference",
    "ref no",
}
_TRAILING_DOT_ZERO = re.compile(r"^-?\d+\.0+$")
_AMOUNT_HEADERS = {"net amount", "invoice amount", "gross amount", "amount"}
_BEFORE_TAX_HEADERS = {
    "taxable amount",
    "taxable",
    "taxable value",
    "assessable value",
    "assessable",
    "amount before tax",
    "before tax",
}
_TAX_HEADERS = {"tax amount", "tax", "gst amount", "gst"}
_TAX_PARTS = {
    "cgst",
    "sgst",
    "igst",
    "cess",
    "cgst amount",
    "sgst amount",
    "igst amount",
    "cess amount",
}


def _b64(text):
    raw = base64.urlsafe_b64encode(str(text or "").encode("utf-8")).decode("ascii").rstrip("=")
    return raw or "x"


def _unb64(text):
    pad = "=" * ((4 - len(text or "") % 4) % 4)
    return base64.urlsafe_b64decode((text or "") + pad).decode("utf-8")


def _header_key(name):
    text = clean_text(name).lower().replace(".", " ").replace("_", " ")
    return " ".join(text.split())


def normalize_invoice_no(value):
    text = clean_text(value)
    if not text:
        return ""
    if _TRAILING_DOT_ZERO.match(text):
        return text.split(".", 1)[0]
    return text


def invoice_key(value):
    return normalize_invoice_no(value).lower()


def _fy_start_month(store=None, start_month=None):
    if start_month is not None:
        from vay.dates import normalize_fy_start_month
        return normalize_fy_start_month(start_month)
    if store is not None:
        from server.org_policy import get_org_policy
        return get_org_policy(store)["fiscal_year_start_month"]
    from vay.dates import DEFAULT_FY_START_MONTH
    return DEFAULT_FY_START_MONTH


def fy_year_token(date_value, start_month=None):
    """Fiscal-year start calendar year for a date, or '' when undated."""
    d = date_value if hasattr(date_value, "year") else parse_date(date_value)
    if not d:
        return ""
    return str(fiscal_year_start(d, start_month).year)


def invoice_scope_key(inv, date_value=None, start_month=None):
    """Stable key: invoice_no + fiscal year. Same number in different FYs stay apart."""
    ik = invoice_key(inv)
    if not ik:
        return ""
    return ik + _FY_SEP + fy_year_token(date_value, start_month)


def money2(value):
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _money_from(fields, names):
    want = set(names)
    for src, val in (fields or {}).items():
        if _header_key(src) not in want:
            continue
        if val in ("", None):
            continue
        return money2(number_(val))
    return None


def _before_tax(fields):
    return _money_from(fields, _BEFORE_TAX_HEADERS)


def _tax_amount(fields):
    found = _money_from(fields, _TAX_HEADERS)
    if found is not None:
        return found
    parts = []
    for src, val in (fields or {}).items():
        if val in ("", None):
            continue
        if _header_key(src) in _TAX_PARTS:
            parts.append(number_(val))
    if not parts:
        return None
    return money2(sum(parts))


def _sale_amount(fields):
    found = _money_from(fields, _AMOUNT_HEADERS)
    if found is not None:
        return found
    return money2(number_((fields or {}).get("Net Amount")))


def _line_amount(fields):
    found = _money_from(fields, _AMOUNT_HEADERS)
    if found is not None:
        return found
    qty = number_((fields or {}).get("Qty"))
    rate = number_((fields or {}).get("Rate"))
    return money2(qty * rate)


def _sum_opt(values):
    present = [v for v in values if v is not None]
    if not present:
        return None
    return money2(sum(present))


def _invoice_no(fields):
    fields = fields or {}
    for src, val in fields.items():
        if val in ("", None):
            continue
        if _header_key(src) in _INVOICE_HEADER:
            return normalize_invoice_no(val)
    return ""


def _party(fields, type_name="sales"):
    if type_name == "sales":
        return clean_text(fields.get("Party Name") or fields.get("Account Name"))
    return clean_text(fields.get("Account Name") or fields.get("Party Name"))


def _group_map(store):
    from vay.row_defaults import real_group

    mapping = {}
    for type_name in ("arr", "party", "customer"):
        for row in store.rows_of_type(type_name):
            fields = row.get("fields") or {}
            name = clean_text(fields.get("Account Name") or fields.get("Party Name")).lower()
            group = real_group(fields.get("Group"))
            if name and group and name not in mapping:
                mapping[name] = group
    return mapping


def _group_for(fields, type_name, groups):
    from vay.row_defaults import real_group

    direct = real_group((fields or {}).get("Group"))
    if direct:
        return direct
    mapped = real_group((groups or {}).get(_party(fields, type_name).lower()))
    if mapped:
        return mapped
    return clean_text((fields or {}).get("Group"))


def invoice_id_for_sale(fields, uk, start_month=None):
    inv = _invoice_no(fields)
    if inv:
        scope = invoice_scope_key(inv, (fields or {}).get("Date"), start_month)
        return "n-" + _b64(scope)
    return "s-" + _b64(str(uk or ""))


def decode_invoice_id(invoice_id):
    """Return (kind, invoice_no_or_uk, fy_token).

    fy_token is the fiscal-year start calendar year string when present in the id,
    '' for undated scoped ids, or None for legacy ids (match all years).
    """
    raw = invoice_id or ""
    if raw.startswith("n-"):
        text = _unb64(raw[2:])
        if _FY_SEP in text:
            inv, fy = text.split(_FY_SEP, 1)
            return "n", inv, fy
        return "n", text, None
    if raw.startswith("s-"):
        return "s", _unb64(raw[2:]), None
    return "n", raw, None


def _sale_group_key(fields, uk, start_month=None):
    inv = _invoice_no(fields)
    if inv:
        return "n", invoice_scope_key(inv, fields.get("Date"), start_month), inv
    return "s", str(uk or ""), str(uk or "")


def _item_indexes(store, start_month=None):
    by_no = {}
    by_day_party = {}
    for row in store.rows_of_type("items"):
        fields = row.get("fields") or {}
        inv = _invoice_no(fields)
        if inv:
            by_no.setdefault(invoice_scope_key(inv, fields.get("Date"), start_month), []).append(row)
        d = parse_date(fields.get("Date"))
        party = _party(fields, "items").lower()
        if d and party:
            by_day_party.setdefault((_iso(d), party), []).append(row)
    return by_no, by_day_party


def _lines_for_sale(fields, by_no, by_day_party, start_month=None):
    inv = _invoice_no(fields)
    key = invoice_scope_key(inv, fields.get("Date"), start_month) if inv else ""
    if key and key in by_no:
        return by_no[key]
    d = parse_date(fields.get("Date"))
    party = _party(fields, "sales").lower()
    if not d or not party:
        return []
    return by_day_party.get((_iso(d), party)) or []


def _line_payload(row, groups=None):
    fields = row.get("fields") or {}
    qty = number_(fields.get("Qty"))
    rate = number_(fields.get("Rate"))
    d = parse_date(fields.get("Date"))
    party = _party(fields, "items")
    return {
        "uk": row.get("uk"),
        "date": _iso(d),
        "date_label": _fmt_day(d),
        "item": clean_text(fields.get("Item Name")),
        "qty": qty,
        "rate": money2(rate) if fields.get("Rate") not in ("", None) else None,
        "amount": _line_amount(fields),
        "before_tax": _before_tax(fields),
        "tax": _tax_amount(fields),
        "party": party,
        "group": _group_for(fields, "items", groups),
        "rep": clean_text(fields.get("Sales Rep")),
        "customer_uk": account_uk(party),
        "invoice": _invoice_no(fields),
        "fields": fields,
    }


def _sale_tag(row, groups=None, start_month=None):
    payload = _sale_payload(row, 0, groups, start_month=start_month)
    return {
        "id": payload["id"],
        "party": payload["party"],
        "group": payload["group"],
        "rep": payload["rep"],
        "customer_uk": payload["customer_uk"],
        "invoice": payload["invoice"],
        "date": payload["date"],
    }


def _fill_line_from_sale(payload, sale, groups=None):
    sale = sale or {}
    if not payload.get("party") and sale.get("party"):
        payload["party"] = sale["party"]
        payload["customer_uk"] = sale.get("customer_uk") or account_uk(sale["party"])
    if not payload.get("customer_uk") and payload.get("party"):
        payload["customer_uk"] = account_uk(payload["party"])
    if not payload.get("group"):
        if payload.get("party") and groups:
            payload["group"] = groups.get(payload["party"].lower()) or ""
        if not payload.get("group"):
            payload["group"] = sale.get("group") or ""
    if not payload.get("rep"):
        payload["rep"] = sale.get("rep") or ""
    if not payload.get("invoice"):
        payload["invoice"] = sale.get("invoice") or ""
    return payload


def _sale_payload(row, line_count=0, groups=None, start_month=None):
    fields = row.get("fields") or {}
    d = parse_date(fields.get("Date"))
    inv = _invoice_no(fields)
    party = _party(fields, "sales")
    iid = invoice_id_for_sale(fields, row.get("uk"), start_month=start_month)
    return {
        "id": iid,
        "uk": row.get("uk"),
        "date": _iso(d),
        "date_label": _fmt_day(d),
        "invoice": inv,
        "party": party,
        "group": _group_for(fields, "sales", groups),
        "customer_uk": account_uk(party),
        "rep": clean_text(fields.get("Sales Rep")),
        "amount": _sale_amount(fields),
        "before_tax": _before_tax(fields),
        "tax": _tax_amount(fields),
        "line_count": line_count,
        "linked": line_count > 0,
        "fields": fields,
    }


def _page_limit(params):
    try:
        page = max(1, int(params.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = int(params.get("limit") or ROW_PAGE_DEFAULT)
    except (TypeError, ValueError):
        limit = ROW_PAGE_DEFAULT
    return page, max(1, min(limit, ROW_PAGE_CAP))


def _eq(value, want):
    if not clean_text(want):
        return True
    return clean_text(value).lower() == clean_text(want).lower()


def _in_dates(day, date_from, date_to):
    if date_from and (day or "") < date_from:
        return False
    if date_to and (day or "") > date_to:
        return False
    return True


def _sort_rows(rows, params, default_key, default_dir="desc"):
    key = clean_text(params.get("sort") or default_key).lower()
    if key == "items":
        key = "line_count"
    direction = clean_text(params.get("dir") or default_dir).lower()
    if direction not in ("asc", "desc"):
        direction = default_dir
    numeric = {"amount", "before_tax", "tax", "qty", "line_count"}
    def sort_val(row):
        val = row.get(key)
        if val is None:
            return float("-inf") if key in numeric else ""
        if isinstance(val, (int, float)):
            return val
        return str(val).lower()
    rows.sort(key=sort_val, reverse=(direction == "desc"))
    return rows


def _options(rows, keys):
    out = {}
    for key in keys:
        vals = sorted({clean_text(r.get(key)) for r in rows if clean_text(r.get(key))}, key=str.lower)
        out[key] = vals
    return out


def _filter_invoice(payload, params):
    if not _eq(payload.get("party"), params.get("party")):
        return False
    if not _eq(payload.get("group"), params.get("group")):
        return False
    if not _eq(payload.get("rep"), params.get("rep")):
        return False
    if not _eq(payload.get("invoice"), params.get("invoice")):
        return False
    if not _in_dates(payload.get("date") or "", clean_text(params.get("date_from")), clean_text(params.get("date_to"))):
        return False
    return True


def _filter_line(payload, params):
    if not _filter_invoice(payload, params):
        return False
    if not _eq(payload.get("item"), params.get("item")):
        return False
    return True


def list_invoices(store, params):
    page, limit = _page_limit(params)
    start_month = _fy_start_month(store)
    groups = _group_map(store)
    by_no, by_day_party = _item_indexes(store, start_month)
    grouped = {}
    order = []
    for row in store.rows_of_type("sales"):
        fields = row.get("fields") or {}
        d = parse_date(fields.get("Date"))
        kind, key, _label = _sale_group_key(fields, row.get("uk"), start_month)
        group = grouped.get(key)
        if not group:
            group = {
                "kind": kind,
                "key": key,
                "rows": [],
                "date": d,
                "amounts": [],
                "before": [],
                "tax": [],
            }
            grouped[key] = group
            order.append(key)
        group["rows"].append(row)
        group["amounts"].append(_sale_amount(fields))
        group["before"].append(_before_tax(fields))
        group["tax"].append(_tax_amount(fields))
        if d and (not group["date"] or d > group["date"]):
            group["date"] = d
    invoices = []
    for key in order:
        group = grouped[key]
        first = group["rows"][0]
        fields = first.get("fields") or {}
        lines = _lines_for_sale(fields, by_no, by_day_party, start_month)
        payload = _sale_payload(first, len(lines), groups, start_month=start_month)
        payload["amount"] = money2(sum(group["amounts"]))
        payload["before_tax"] = _sum_opt(group["before"])
        payload["tax"] = _sum_opt(group["tax"])
        payload["date"] = _iso(group["date"])
        payload["date_label"] = _fmt_day(group["date"])
        invoices.append(payload)
    options = _options(invoices, ("party", "group", "rep", "invoice"))
    invoices = [row for row in invoices if _filter_invoice(row, params)]
    _sort_rows(invoices, params, "date", "desc")
    total = len(invoices)
    start = (page - 1) * limit
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "invoices": invoices[start:start + limit],
        "options": options,
        "sort": clean_text(params.get("sort") or "date"),
        "dir": clean_text(params.get("dir") or "desc"),
    }


def get_invoice(store, invoice_id):
    kind, value, fy = decode_invoice_id(invoice_id)
    start_month = _fy_start_month(store)
    groups = _group_map(store)
    by_no, by_day_party = _item_indexes(store, start_month)
    sales_rows = []
    if kind == "n":
        want = invoice_key(value)
        for row in store.rows_of_type("sales"):
            fields = row.get("fields") or {}
            if invoice_key(_invoice_no(fields)) != want:
                continue
            row_fy = fy_year_token(fields.get("Date"), start_month)
            if fy is None or row_fy == fy:
                sales_rows.append(row)
    else:
        for row in store.rows_of_type("sales"):
            if str(row.get("uk") or "") == value:
                sales_rows.append(row)
                break
    if not sales_rows:
        return None
    first = sales_rows[0]
    fields = first.get("fields") or {}
    line_rows = _lines_for_sale(fields, by_no, by_day_party, start_month)
    payload = _sale_payload(first, len(line_rows), groups, start_month=start_month)
    payload["amount"] = money2(sum(_sale_amount(r.get("fields") or {}) for r in sales_rows))
    payload["before_tax"] = _sum_opt([_before_tax(r.get("fields") or {}) for r in sales_rows])
    payload["tax"] = _sum_opt([_tax_amount(r.get("fields") or {}) for r in sales_rows])
    sale = {
        "party": payload["party"],
        "group": payload["group"],
        "rep": payload["rep"],
        "customer_uk": payload["customer_uk"],
        "invoice": payload["invoice"],
    }
    payload["lines"] = [_fill_line_from_sale(_line_payload(r, groups), sale, groups) for r in line_rows]
    payload["link_note"] = ""
    if not line_rows:
        if _invoice_no(fields):
            payload["link_note"] = "No item-wise rows with this invoice number."
        else:
            payload["link_note"] = "No item-wise rows linked. Map the invoice column on sales and item-wise sales, then import again."
    return payload


def list_item_lines(store, params):
    page, limit = _page_limit(params)
    start_month = _fy_start_month(store)
    groups = _group_map(store)
    sales_by_no = {}
    sales_by_id = {}
    sales_by_day_party = {}
    for row in store.rows_of_type("sales"):
        fields = row.get("fields") or {}
        tag = _sale_tag(row, groups, start_month=start_month)
        sales_by_id[tag["id"]] = tag
        if tag["invoice"]:
            sales_by_no.setdefault(
                invoice_scope_key(tag["invoice"], tag.get("date") or fields.get("Date"), start_month),
                tag,
            )
        d = parse_date(fields.get("Date"))
        party = _party(fields, "sales").lower()
        if d and party:
            sales_by_day_party.setdefault((_iso(d), party), []).append(tag["id"])
    lines = []
    for row in store.rows_of_type("items"):
        payload = _line_payload(row, groups)
        inv = payload["invoice"]
        sale = None
        key = invoice_scope_key(inv, payload.get("date") or (row.get("fields") or {}).get("Date"), start_month) if inv else ""
        if key and key in sales_by_no:
            sale = sales_by_no[key]
        elif payload["date"] and payload["party"]:
            ids = sales_by_day_party.get((payload["date"], payload["party"].lower())) or []
            if len(ids) == 1:
                sale = sales_by_id.get(ids[0])
        payload["invoice_id"] = (sale or {}).get("id") or ""
        _fill_line_from_sale(payload, sale, groups)
        lines.append(payload)
    options = _options(lines, ("party", "group", "rep", "invoice", "item"))
    lines = [row for row in lines if _filter_line(row, params)]
    _sort_rows(lines, params, "date", "desc")
    total = len(lines)
    start = (page - 1) * limit
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "lines": lines[start:start + limit],
        "options": options,
        "sort": clean_text(params.get("sort") or "date"),
        "dir": clean_text(params.get("dir") or "desc"),
    }
