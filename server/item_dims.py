"""Category, item group, brand, and supplier rollups. Does not feed generate()."""

from __future__ import annotations

from vay.dates import clean_text, fiscal_year_start, fy_label

from server.customers import account_uk
from server.item_attrs import NONE_UK, attr_map, resolved_attr

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
from server.items360 import _TREND_LABELS, _build_item_cards, _trend_from_pace

DIMENSIONS = {
    "category": {
        "field": "Category",
        "label": "Category",
        "plural": "categories",
        "none_label": "No category",
        "hash": "category",
    },
    "item_group": {
        "field": "Item Group",
        "label": "Item group",
        "plural": "item groups",
        "none_label": "No item group",
        "hash": "item-group",
    },
    "brand": {
        "field": "Brand",
        "label": "Brand",
        "plural": "brands",
        "none_label": "No brand",
        "hash": "brand",
    },
    "supplier": {
        "field": "Supplier",
        "label": "Supplier",
        "plural": "suppliers",
        "none_label": "No supplier",
        "hash": "supplier",
    },
}


def dimension_spec(dimension):
    return DIMENSIONS.get(clean_text(dimension).lower().replace(" ", "_").replace("-", "_"))


def _page_limit(params):
    try:
        page = max(1, int((params or {}).get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    return page, 50


_ATTR_KEYS = (
    ("Category", "category"),
    ("Item Group", "item_group"),
    ("Brand", "brand"),
    ("Supplier", "supplier"),
)


def _attr_bits(fields):
    out = {}
    for name, key in _ATTR_KEYS:
        text, link = resolved_attr(name, (fields or {}).get(name))
        out[key] = text
        out[key + "_uk"] = link
    return out


def _member(card, fields):
    rate = card.get("rate")
    buy_qty = card.get("buy_qty") or 0
    value = card.get("value")
    pace = float(card.get("pace") or 0)
    member = {
        "uk": card.get("uk") or "",
        "name": card.get("name") or "",
        "qty": card.get("qty") or 0,
        "value": value if value is not None else None,
        "sales_qty": card.get("ytd_qty") or 0,
        "sales_value": card.get("ytd_amount") or 0,
        "buy_qty": buy_qty,
        "buy_value": round(float(buy_qty) * float(rate or 0), 2),
        "days_cover": card.get("days_cover"),
        "pace": pace,
        "status": card.get("status") or "",
        "status_label": card.get("status_label") or "",
        "stock_position": card.get("stock_position") or "",
        "stock_position_label": card.get("stock_position_label") or "",
        "in_stock": bool(card.get("in_stock")),
        "discontinued": bool(card.get("discontinued")),
        "trend": card.get("trend") or "flat",
        "trend_pct": card.get("trend_pct") or 0,
        "trend_label": card.get("trend_label") or _TREND_LABELS.get(card.get("trend") or "flat", "Steady"),
        "last_sale": card.get("last_sale") or "",
        "last_sale_label": card.get("last_sale_label") or "",
    }
    member.update(_attr_bits(fields))
    return member


def _remember_mix(slot, member):
    mix = slot.setdefault("_mix", {})
    for _name, key in _ATTR_KEYS:
        text = member.get(key) or ""
        if not text:
            continue
        bag = mix.setdefault(key, {})
        bag[text.lower()] = text


def _party_add(bag, name, qty, amount, blank_label):
    text = clean_text(name)
    blank = not text
    label = blank_label if blank else text
    key = "__none__" if blank else text.lower()
    row = bag.get(key)
    if row is None:
        row = {
            "uk": "" if blank else account_uk(text),
            "name": label,
            "none": blank,
            "qty": 0.0,
            "amount": 0.0,
            "times": 0,
        }
        bag[key] = row
    row["qty"] += qty
    row["amount"] += amount
    row["times"] += 1


def _round_sales(row):
    row["qty"] = round(row["qty"], 2)
    row["amount"] = round(row["amount"], 2)
    return row


def _party_rows(bag):
    rows = [_round_sales(row) for row in (bag or {}).values()]
    rows.sort(key=lambda row: (-(row.get("amount") or 0), (row.get("name") or "").lower()))
    return rows


def _sale_rollup(lines, as_of, start_month):
    """One pass over an item's sales. Shared by every dimension."""
    roll = {
        "overall_qty": 0.0,
        "overall_amount": 0.0,
        "overall_times": 0,
        "months": {},
        "fys": {},
        "groups": {},
        "reps": {},
    }
    for line in lines or []:
        d = line.get("date")
        if not d or (as_of is not None and d > as_of):
            continue
        qty = float(line.get("qty") or 0)
        amount = float(line.get("amount") or 0)
        roll["overall_qty"] += qty
        roll["overall_amount"] += amount
        roll["overall_times"] += 1
        month_key = "%04d-%02d" % (d.year, d.month)
        month = roll["months"].get(month_key)
        if month is None:
            month = {"key": month_key, "label": "%s %d" % (_MONTHS[d.month - 1], d.year), "qty": 0.0, "amount": 0.0, "times": 0}
            roll["months"][month_key] = month
        month["qty"] += qty
        month["amount"] += amount
        month["times"] += 1
        fy = fiscal_year_start(d, start_month)
        fy_key = fy.strftime("%Y-%m-%d")
        year = roll["fys"].get(fy_key)
        if year is None:
            year = {"start": fy_key, "label": fy_label(fy), "qty": 0.0, "amount": 0.0, "times": 0}
            roll["fys"][fy_key] = year
        year["qty"] += qty
        year["amount"] += amount
        year["times"] += 1
        _party_add(roll["groups"], line.get("group"), qty, amount, "No group")
        _party_add(roll["reps"], line.get("rep"), qty, amount, "No salesperson")
    return roll


def _merge_metric(dest, src):
    for key, row in (src or {}).items():
        cur = dest.get(key)
        if cur is None:
            dest[key] = dict(row)
            continue
        cur["qty"] += row.get("qty") or 0
        cur["amount"] += row.get("amount") or 0
        cur["times"] += row.get("times") or 0


def _merge_sales(slot, roll):
    if not roll:
        return
    slot["overall_qty"] += roll.get("overall_qty") or 0
    slot["overall_amount"] += roll.get("overall_amount") or 0
    slot["overall_times"] += roll.get("overall_times") or 0
    _merge_metric(slot["_months"], roll.get("months"))
    _merge_metric(slot["_fys"], roll.get("fys"))
    _merge_metric(slot["_groups"], roll.get("groups"))
    _merge_metric(slot["_reps"], roll.get("reps"))


def _item_rolls(cards, lines_by_uk, as_of, start_month):
    rolls = {}
    lines_by_uk = lines_by_uk or {}
    for card in cards or []:
        uk = (card.get("uk") or "").lower()
        if not uk or uk in rolls:
            continue
        rolls[uk] = _sale_rollup(lines_by_uk.get(uk) or [], as_of, start_month)
    return rolls


def _add(slot, card, fields, roll, keep_members=True):
    member = _member(card, fields)
    slot["items"] += 1
    slot["qty"] += member["qty"] or 0
    slot["sales_qty"] += member["sales_qty"] or 0
    slot["sales_value"] += member["sales_value"] or 0
    slot["buy_qty"] += member["buy_qty"] or 0
    slot["buy_value"] += member["buy_value"] or 0
    if member["pace"] > 0:
        slot["pace"] += member["pace"]
        slot["paced_qty"] += member["qty"] or 0
    slot["pace_30"] += float(card.get("pace_30") or 0)
    slot["pace_90"] += float(card.get("pace_90") or 0)
    if member["trend"] == "up":
        slot["up_count"] += 1
    elif member["trend"] == "down":
        slot["down_count"] += 1
    else:
        slot["flat_count"] += 1
    if member["value"] is not None:
        slot["stock_value"] += member["value"] or 0
        slot["valued_items"] += 1
    if member["status"] == "low":
        slot["low_count"] += 1
    elif member["status"] == "soon":
        slot["soon_count"] += 1
    position = member["stock_position"]
    if position == "under":
        slot["under_count"] += 1
    elif position == "over":
        slot["over_count"] += 1
    elif position == "dead":
        slot["dead_count"] += 1
    if not member["in_stock"]:
        slot["out_count"] += 1
    if member["discontinued"]:
        slot["stopped_count"] += 1
    if member["last_sale"] and member["last_sale"] > (slot.get("last_sale") or ""):
        slot["last_sale"] = member["last_sale"]
        slot["last_sale_label"] = member["last_sale_label"]
    _remember_mix(slot, member)
    member.pop("pace", None)
    if keep_members:
        slot["members"].append(member)
    _merge_sales(slot, roll)


def _finish(slot):
    slot["qty"] = round(slot["qty"], 2)
    slot["sales_qty"] = round(slot["sales_qty"], 2)
    slot["sales_value"] = round(slot["sales_value"], 2)
    slot["buy_qty"] = round(slot["buy_qty"], 2)
    slot["buy_value"] = round(slot["buy_value"], 2)
    if slot["valued_items"]:
        slot["stock_value"] = round(slot["stock_value"], 2)
    else:
        slot["stock_value"] = None
    if slot["pace"] > 0:
        slot["days_cover"] = int(round(slot["paced_qty"] / slot["pace"]))
    else:
        slot["days_cover"] = None
    mix = slot.pop("_mix", {})
    slot["category_count"] = len(mix.get("category") or {})
    slot["item_group_count"] = len(mix.get("item_group") or {})
    slot["brand_count"] = len(mix.get("brand") or {})
    slot["supplier_count"] = len(mix.get("supplier") or {})
    slot.pop("valued_items", None)
    slot.pop("pace", None)
    slot.pop("paced_qty", None)
    trend, trend_pct = _trend_from_pace(slot.pop("pace_30", 0.0), slot.pop("pace_90", 0.0))
    slot["trend"] = trend
    slot["trend_pct"] = trend_pct
    slot["trend_label"] = _TREND_LABELS.get(trend, "Steady")
    slot["groups"] = _party_rows(slot.pop("_groups", {}))
    slot["reps"] = _party_rows(slot.pop("_reps", {}))
    slot["overall"] = {
        "qty": round(slot.pop("overall_qty", 0.0), 2),
        "amount": round(slot.pop("overall_amount", 0.0), 2),
        "times": int(slot.pop("overall_times", 0) or 0),
    }
    months = [_round_sales(row) for row in slot.pop("_months", {}).values()]
    months.sort(key=lambda row: row.get("key") or "")
    slot["months"] = months
    years = [_round_sales(row) for row in slot.pop("_fys", {}).values()]
    years.sort(key=lambda row: row.get("start") or "", reverse=True)
    slot["fy_years"] = years
    slot["members"].sort(key=lambda row: (-(row.get("sales_value") or 0), (row.get("name") or "").lower()))
    return slot


def _empty_slot(uk, name, none=False):
    return {
        "uk": uk,
        "name": name,
        "none": none,
        "items": 0,
        "qty": 0.0,
        "stock_value": 0.0,
        "valued_items": 0,
        "sales_qty": 0.0,
        "sales_value": 0.0,
        "buy_qty": 0.0,
        "buy_value": 0.0,
        "low_count": 0,
        "soon_count": 0,
        "under_count": 0,
        "over_count": 0,
        "dead_count": 0,
        "out_count": 0,
        "stopped_count": 0,
        "pace": 0.0,
        "paced_qty": 0.0,
        "pace_30": 0.0,
        "pace_90": 0.0,
        "up_count": 0,
        "down_count": 0,
        "flat_count": 0,
        "_groups": {},
        "_reps": {},
        "last_sale": "",
        "last_sale_label": "",
        "overall_qty": 0.0,
        "overall_amount": 0.0,
        "overall_times": 0,
        "_months": {},
        "_fys": {},
        "members": [],
    }


def rollup_totals(rows):
    totals = {
        "items": 0,
        "qty": 0.0,
        "stock_value": 0.0,
        "sales_qty": 0.0,
        "sales_value": 0.0,
        "buy_qty": 0.0,
        "buy_value": 0.0,
        "low_count": 0,
        "soon_count": 0,
        "under_count": 0,
        "over_count": 0,
        "dead_count": 0,
        "out_count": 0,
        "stopped_count": 0,
        "up_count": 0,
        "down_count": 0,
        "has_stock_value": False,
    }
    for row in rows or []:
        totals["items"] += int(row.get("items") or 0)
        totals["qty"] += float(row.get("qty") or 0)
        totals["sales_qty"] += float(row.get("sales_qty") or 0)
        totals["sales_value"] += float(row.get("sales_value") or 0)
        totals["buy_qty"] += float(row.get("buy_qty") or 0)
        totals["buy_value"] += float(row.get("buy_value") or 0)
        totals["low_count"] += int(row.get("low_count") or 0)
        totals["soon_count"] += int(row.get("soon_count") or 0)
        totals["under_count"] += int(row.get("under_count") or 0)
        totals["over_count"] += int(row.get("over_count") or 0)
        totals["dead_count"] += int(row.get("dead_count") or 0)
        totals["out_count"] += int(row.get("out_count") or 0)
        totals["stopped_count"] += int(row.get("stopped_count") or 0)
        totals["up_count"] += int(row.get("up_count") or 0)
        totals["down_count"] += int(row.get("down_count") or 0)
        if "stock_value" in row and row.get("stock_value") is not None:
            totals["has_stock_value"] = True
            totals["stock_value"] += float(row.get("stock_value") or 0)
    for key in ("qty", "stock_value", "sales_qty", "sales_value", "buy_qty", "buy_value"):
        totals[key] = round(totals[key], 2)
    return totals


def _dimension_key(dimension):
    spec = dimension_spec(dimension)
    if not spec:
        return ""
    for key, item in DIMENSIONS.items():
        if item["field"] == spec["field"]:
            return key
    return ""


def _public_row(slot):
    row = dict(slot)
    for key in ("members", "months", "fy_years", "groups", "reps"):
        row.pop(key, None)
    return row


def _bundle(cards, attrs, key, spec, rolls, keep_members=True):
    field = spec["field"]
    named = {}
    blank = _empty_slot(NONE_UK, spec["none_label"], none=True)
    rolls = rolls or {}
    for card in cards:
        uk = (card.get("uk") or "").lower()
        fields = attrs.get(uk) or {}
        roll = rolls.get(uk)
        value = clean_text(fields.get(field))
        if not value:
            _add(blank, card, fields, roll, keep_members)
            continue
        slot = named.get(value.lower())
        if slot is None:
            slot = _empty_slot(account_uk(value), value, none=False)
            named[value.lower()] = slot
        _add(slot, card, fields, roll, keep_members)
    rows = [_finish(slot) for slot in named.values()]
    rows.sort(key=lambda row: (-(row.get("sales_value") or 0), (row.get("name") or "").lower()))
    details = {row["uk"]: row for row in rows}
    if blank["items"]:
        _finish(blank)
        rows.append(blank)
        details[NONE_UK] = blank
    return {
        "dimension": key,
        "label": spec["label"],
        "plural": spec["plural"],
        "none_label": spec["none_label"],
        "hash": spec["hash"],
        "rows": rows,
        "details": details,
    }


def dimension_inputs(store, book=None, cards=None):
    """Cards, attributes, and one sales rollup per item."""
    if book is None:
        from server.book import load_book
        book = load_book(store)
    if cards is None:
        cards, _default_min, _default_max = _build_item_cards(book)
    attrs = book.get("item_attrs")
    if attrs is None:
        attrs = attr_map(store)
    rolls = _item_rolls(
        cards,
        book.get("item_lines_by_uk") or {},
        book.get("as_of"),
        book.get("fiscal_year_start_month"),
    )
    return cards, attrs, rolls


def bundles(store, book=None, cards=None, keep_members=True):
    if book is None:
        from server.book import load_book
        book = load_book(store)
    cards, attrs, rolls = dimension_inputs(store, book, cards)
    return {
        key: _bundle(cards, attrs, key, spec, rolls, keep_members)
        for key, spec in DIMENSIONS.items()
    }


_CARD_LINK = {
    "category": "category_uk",
    "item_group": "item_group_uk",
    "brand": "brand_uk",
    "supplier": "supplier_uk",
}


def _member_from_card(card):
    """Item row for a dimension page. Uses the card already stored on the snapshot."""
    rate = card.get("rate")
    buy_qty = card.get("buy_qty") or 0
    sales_value = card.get("ytd_amount")
    if sales_value is None:
        sales_value = card.get("sales_value") or 0
    sales_qty = card.get("ytd_qty")
    if sales_qty is None:
        sales_qty = card.get("sales_qty") or 0
    member = {
        "uk": card.get("uk") or "",
        "name": card.get("name") or "",
        "qty": card.get("qty") or 0,
        "value": card.get("value") if card.get("value") is not None else None,
        "sales_qty": sales_qty or 0,
        "sales_value": sales_value or 0,
        "buy_qty": buy_qty,
        "buy_value": round(float(buy_qty) * float(rate or 0), 2),
        "days_cover": card.get("days_cover"),
        "status": card.get("status") or "",
        "status_label": card.get("status_label") or "",
        "stock_position": card.get("stock_position") or "",
        "stock_position_label": card.get("stock_position_label") or "",
        "in_stock": bool(card.get("in_stock")),
        "discontinued": bool(card.get("discontinued")),
        "trend": card.get("trend") or "flat",
        "trend_pct": card.get("trend_pct") or 0,
        "trend_label": card.get("trend_label") or _TREND_LABELS.get(card.get("trend") or "flat", "Steady"),
        "last_sale": card.get("last_sale") or "",
        "last_sale_label": card.get("last_sale_label") or "",
    }
    for _name, key in _ATTR_KEYS:
        member[key] = card.get(key) or ""
        member[key + "_uk"] = card.get(key + "_uk") or ""
    return member


def members_for_slot(cards, dimension, slot_uk):
    link_key = _CARD_LINK.get(dimension)
    if not link_key:
        return []
    want = (slot_uk or "").lower()
    rows = []
    for card in cards or []:
        link = (card.get(link_key) or "").lower()
        if want == NONE_UK:
            if link and link != NONE_UK:
                continue
        elif link != want:
            continue
        rows.append(_member_from_card(card))
    rows.sort(key=lambda row: (-(row.get("sales_value") or 0), (row.get("name") or "").lower()))
    return rows


def filter_members(members, focus):
    focus = clean_text(focus).lower()
    if focus in ("", "all"):
        return list(members or [])
    out = []
    for row in members or []:
        if focus == "low" and row.get("status") == "low":
            out.append(row)
        elif focus == "soon" and row.get("status") == "soon":
            out.append(row)
        elif focus == "buy" and row.get("status") in ("low", "soon"):
            out.append(row)
        elif focus == "under" and row.get("stock_position") == "under":
            out.append(row)
        elif focus == "dead" and row.get("stock_position") == "dead":
            out.append(row)
        elif focus == "out" and row.get("in_stock") is False:
            out.append(row)
        elif focus == "up" and row.get("trend") == "up":
            out.append(row)
        elif focus == "down" and row.get("trend") == "down":
            out.append(row)
    return out


def build_dimension(store, dimension):
    key = _dimension_key(dimension)
    if not key:
        return None
    return bundles(store).get(key)


def _sort_rows(rows, params):
    key = clean_text((params or {}).get("sort") or "sales_value").lower()
    if key in ("name", "category", "group", "brand", "supplier"):
        key = "name"
    if key in ("item", "item_count", "count"):
        key = "items"
    if key in ("on_hand", "onhand"):
        key = "qty"
    if key in ("sales", "sales_amount"):
        key = "sales_value"
    if key in ("stock", "on_hand_value"):
        key = "stock_value"
    if key in ("cover", "days", "days_left"):
        key = "days_cover"
    if key in ("last", "last_sale_label"):
        key = "last_sale"
    if key not in (
        "name", "items", "qty", "stock_value", "sales_qty", "sales_value",
        "buy_qty", "buy_value", "low_count", "soon_count", "under_count",
        "over_count", "dead_count", "out_count", "days_cover", "last_sale",
        "brand_count", "category_count", "item_group_count", "supplier_count",
    ):
        key = "sales_value"
    direction = clean_text((params or {}).get("dir") or "").lower()
    if direction not in ("asc", "desc"):
        direction = "asc" if key == "name" else "desc"

    def sort_val(row):
        if key == "name":
            return (row.get("name") or "").lower()
        if key == "last_sale":
            return row.get("last_sale") or ""
        if key == "days_cover":
            val = row.get("days_cover")
            return val if isinstance(val, (int, float)) else -1
        return row.get(key) or 0

    rows.sort(key=sort_val, reverse=(direction == "desc"))
    return key, direction


def list_item_dims(store, dimension, params):
    built = build_dimension(store, dimension)
    if not built:
        return None
    q = clean_text((params or {}).get("q") or "").lower()
    rows = []
    for slot in built["rows"]:
        if q and q not in (slot.get("name") or "").lower():
            continue
        rows.append(slot)
    sort, direction = _sort_rows(rows, params)
    page, limit = _page_limit(params)
    start = (page - 1) * limit
    public = [_public_row(row) for row in rows]
    return {
        "dimension": built["dimension"],
        "label": built["label"],
        "plural": built["plural"],
        "hash": built["hash"],
        "total": len(public),
        "page": page,
        "limit": limit,
        "rows": public[start:start + limit],
        "totals": rollup_totals(public),
        "sort": sort,
        "dir": direction,
    }


def get_item_dim(store, dimension, uk):
    built = build_dimension(store, dimension)
    if not built:
        return None
    raw = clean_text(uk)
    slot = None
    if raw == NONE_UK or account_uk(raw) == NONE_UK:
        slot = built["details"].get(NONE_UK)
    else:
        want = account_uk(raw).lower()
        for row in built["rows"]:
            if row.get("none"):
                continue
            if (row.get("uk") or "").lower() == want or account_uk(row.get("name")).lower() == want:
                slot = row
                break
    if not slot:
        return None
    detail = dict(slot)
    detail["dimension"] = built["dimension"]
    detail["dimension_label"] = built["label"]
    detail["hash"] = built["hash"]
    from server.repurchase import attach_repurchase
    return attach_repurchase(store, detail, **{built["dimension"]: detail.get("uk") or ""})
