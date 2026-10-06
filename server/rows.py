"""GET /api/rows projection. Does not feed generate()."""

from vay.dates import clean_text, number_, parse_date

from server.settings import ROW_PAGE_CAP, ROW_PAGE_DEFAULT, SNAPSHOT_TYPES


def _group_map(store):
    mapping = {}
    for type_name in ("party", "arr"):
        for row in store.rows_of_type(type_name):
            fields = row.get("fields") or {}
            name = clean_text(fields.get("Account Name") or fields.get("Party Name")).lower()
            if name:
                mapping[name] = clean_text(fields.get("Group"))
    return mapping


def _party(fields, type_name):
    if type_name in ("sales", "credit_note"):
        return clean_text(fields.get("Party Name") or fields.get("Account Name"))
    if type_name in ("receipt", "payments", "arr", "party"):
        return clean_text(fields.get("Account Name") or fields.get("Party Name"))
    if type_name == "items":
        return clean_text(fields.get("Account Name") or fields.get("Party Name"))
    if type_name == "stock":
        return clean_text(fields.get("Item Name"))
    return ""


def _group_for(fields, type_name, groups):
    if type_name in ("arr", "party"):
        return clean_text(fields.get("Group"))
    if type_name == "stock":
        return ""
    return groups.get(_party(fields, type_name).lower(), "") or clean_text(fields.get("Group"))


def _iso(d):
    return d.strftime("%Y-%m-%d") if d else ""


def _amount(fields, type_name):
    if type_name in ("sales", "credit_note"):
        return number_(fields.get("Net Amount") or fields.get("Amount"))
    if type_name in ("receipt", "payments"):
        return number_(fields.get("Amount"))
    if type_name in ("arr", "party"):
        return number_(fields.get("Balance"))
    if type_name == "stock":
        return number_(fields.get("Qty"))
    if type_name == "items":
        if fields.get("Amount") not in ("", None):
            return number_(fields.get("Amount"))
        return number_(fields.get("Qty")) * number_(fields.get("Rate"))
    return 0


def _eq(value, want):
    if not clean_text(want):
        return True
    return clean_text(value).lower() == clean_text(want).lower()


def _in_date_range(day, date_from, date_to):
    if date_from and (day or "") < date_from:
        return False
    if date_to and (day or "") > date_to:
        return False
    return True


def _opt_number(value):
    text = clean_text(value)
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _with_stock_attrs(fields, saved):
    """Show category, item group, brand, and supplier. A blank uses that field's default."""
    from server.item_attrs import DEFAULT_ATTR_VALUES
    out = dict(fields or {})
    saved = saved or {}
    for name, label in DEFAULT_ATTR_VALUES.items():
        raw = clean_text(out.get(name)) or clean_text(saved.get(name))
        out[name] = raw or label
    return out


def _in_amount_range(amount, lo, hi):
    if lo is not None and amount < lo:
        return False
    if hi is not None and amount > hi:
        return False
    return True


def query_rows(store, params):
    type_name = clean_text(params.get("type") or "sales").lower()
    upload = clean_text(params.get("upload"))
    date_from = clean_text(params.get("date_from"))
    date_to = clean_text(params.get("date_to"))
    party = clean_text(params.get("party") or params.get("account"))
    party_type = clean_text(params.get("party_type"))
    rep = clean_text(params.get("rep"))
    group = clean_text(params.get("group"))
    item = clean_text(params.get("item"))
    balance_from = _opt_number(params.get("balance_from"))
    balance_to = _opt_number(params.get("balance_to"))
    try:
        page = max(1, int(params.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = int(params.get("limit") or ROW_PAGE_DEFAULT)
    except (TypeError, ValueError):
        limit = ROW_PAGE_DEFAULT
    limit = max(1, min(limit, ROW_PAGE_CAP))

    groups = _group_map(store)
    type_labels = {}
    if type_name == "party":
        from server.customers import list_party_types
        type_labels = {item["id"]: item["label"] for item in list_party_types(store)}
    attr_by_uk = {}
    if type_name == "stock":
        from server.item_attrs import attr_map
        attr_by_uk = attr_map(store)
    projected = []
    for row in store.rows_of_type(type_name):
        fields = row.get("fields") or {}
        if upload and str(row.get("source_upload_id")) != upload:
            continue
        d = parse_date(fields.get("Date"))
        party_name = _party(fields, type_name)
        item_name = clean_text(fields.get("Item Name"))
        if type_name == "stock":
            item_name = party_name or item_name
        type_id = clean_text(fields.get("Party Type")) if type_name == "party" else ""
        if type_name == "stock":
            fields = _with_stock_attrs(fields, attr_by_uk.get((row.get("uk") or "").lower()))
        projected.append({
            "uk": row.get("uk"),
            "source_upload_id": row.get("source_upload_id"),
            "fields": fields,
            "party": party_name,
            "group": _group_for(fields, type_name, groups),
            "party_type": type_id,
            "party_type_label": type_labels.get(type_id, type_id) if type_id else "",
            "rep": clean_text(fields.get("Sales Rep")),
            "item": item_name,
            "category": clean_text(fields.get("Category")) if type_name == "stock" else "",
            "item_group": clean_text(fields.get("Item Group")) if type_name == "stock" else "",
            "brand": clean_text(fields.get("Brand")) if type_name == "stock" else "",
            "supplier": clean_text(fields.get("Supplier")) if type_name == "stock" else "",
            "invoice": clean_text(fields.get("Invoice No")),
            "date": _iso(d),
            "amount": _amount(fields, type_name),
            "qty": number_(fields.get("Qty")),
            "rate": number_(fields.get("P.Price") or fields.get("Rate")),
            "days": number_(fields.get("Days")) if fields.get("Days") not in ("", None) else None,
        })

    options = {}
    for key in ("party", "group", "rep", "item"):
        vals = sorted({clean_text(r.get(key)) for r in projected if clean_text(r.get(key))}, key=str.lower)
        options[key] = vals
    if type_name == "party":
        options["party_type"] = sorted({
            clean_text(r.get("party_type_label") or r.get("party_type"))
            for r in projected
            if clean_text(r.get("party_type_label") or r.get("party_type"))
        }, key=str.lower)

    matched = []
    for row in projected:
        if type_name not in SNAPSHOT_TYPES and (date_from or date_to):
            if not _in_date_range(row.get("date") or "", date_from, date_to):
                continue
        if not _eq(row.get("party"), party):
            continue
        if not _eq(row.get("rep"), rep):
            continue
        if not _eq(row.get("item"), item):
            continue
        if not _eq(row.get("group"), group):
            continue
        if type_name == "party" and party_type:
            if not (_eq(row.get("party_type"), party_type) or _eq(row.get("party_type_label"), party_type)):
                continue
        if type_name in ("party", "arr") and not _in_amount_range(row.get("amount") or 0, balance_from, balance_to):
            continue
        matched.append(row)

    key = clean_text(params.get("sort") or ("date" if type_name not in SNAPSHOT_TYPES else "party")).lower()
    if key == "salesperson":
        key = "rep"
    direction = clean_text(params.get("dir") or ("desc" if key in ("date", "amount") else "asc")).lower()
    if direction not in ("asc", "desc"):
        direction = "desc"
    numeric = {"amount", "qty", "rate", "days"}
    def sort_val(row):
        if key == "party_type":
            val = row.get("party_type_label") or row.get("party_type")
        else:
            val = row.get(key)
        if val is None and key not in numeric:
            val = (row.get("fields") or {}).get(key)
        if val is None:
            return float("-inf") if key in numeric else ""
        if isinstance(val, (int, float)):
            return val
        return str(val).lower()
    matched.sort(key=sort_val, reverse=(direction == "desc"))
    total = len(matched)
    start = (page - 1) * limit
    out = {
        "total": total,
        "page": page,
        "limit": limit,
        "rows": matched[start:start + limit],
        "options": options,
        "sort": key,
        "dir": direction,
    }
    if type_name == "party":
        from server.customers import list_party_types
        out["party_types"] = list_party_types(store)
    return out
