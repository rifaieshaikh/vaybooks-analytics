"""Same-item repurchase cycles. Built once into the 360 snapshot."""

from __future__ import annotations

import bisect

from vay.dates import clean_text, fiscal_year_start, fy_label

from server.customers import (
    _fmt_day,
    _iso,
    _month_label,
    account_uk,
)
from server.item_attrs import resolved_attr

LINE_CAP = 200
MEMBER_CAP = 30
WAIT_CAP = 20
SAME_CAP = 12
OVERDUE_CAP = 40

_ATTRS = (
    ("Category", "category", "category_uk"),
    ("Item Group", "item_group", "item_group_uk"),
    ("Brand", "brand", "brand_uk"),
    ("Supplier", "supplier", "supplier_uk"),
)

_BUCKETS = (
    ("party", "party_uk"),
    ("group", "group_uk"),
    ("rep", "rep_uk"),
    ("item", "item_uk"),
    ("category", "category_uk"),
    ("item_group", "item_group_uk"),
    ("brand", "brand_uk"),
    ("supplier", "supplier_uk"),
)

_FILTERS = (
    ("party", "party_uk", "party"),
    ("group", "group_uk", "group"),
    ("rep", "rep_uk", "rep"),
    ("item", "item_uk", "item"),
    ("category", "category_uk", "category"),
    ("item_group", "item_group_uk", "item_group"),
    ("brand", "brand_uk", "brand"),
    ("supplier", "supplier_uk", "supplier"),
)

_INTERVENE = (
    ("n0", "Nothing else"),
    ("n1", "1 other order"),
    ("n2_3", "2–3 other orders"),
    ("n4", "4 or more"),
)

GAP_BANDS = (
    {"key": "w2", "label": "Under 2 weeks", "max_days": 14},
    {"key": "w4", "label": "2–4 weeks", "max_days": 28},
    {"key": "m2", "label": "1–2 months", "max_days": 60},
    {"key": "m3", "label": "2–3 months", "max_days": 90},
    {"key": "longer", "label": "3 months or more", "max_days": None},
)


def _num(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _money(value):
    return round(_num(value), 2)


def _day_key(value):
    return (value.year, value.month, value.day)


def _day_dt(key):
    from datetime import datetime
    return datetime(key[0], key[1], key[2], 12)


def _percentile(values, p):
    if not values:
        return None
    vals = sorted(int(v) for v in values)
    if len(vals) == 1:
        return vals[0]
    rank = (len(vals) - 1) * float(p)
    lo = int(rank)
    hi = min(lo + 1, len(vals) - 1)
    frac = rank - lo
    return int(round(vals[lo] * (1 - frac) + vals[hi] * frac))


def _intervene_key(count):
    n = int(count or 0)
    if n <= 0:
        return "n0"
    if n == 1:
        return "n1"
    if n <= 3:
        return "n2_3"
    return "n4"


def _attrs_for(item_uk, item_attrs):
    raw = (item_attrs or {}).get((item_uk or "").lower()) or {}
    out = {}
    for name, key, uk_key in _ATTRS:
        text, link = resolved_attr(name, raw.get(name))
        out[key] = text
        out[uk_key] = link
    return out


def _blank_item():
    return {
        "uk": "",
        "name": "",
        "qty": 0.0,
        "amount": 0.0,
        "times": 0,
        "group": "",
        "rep": "",
        "invoices": [],
        "invoice_id": "",
    }


def _absorb(bag, line):
    uk = account_uk(line.get("uk") or line.get("name"))
    key = uk.lower()
    if not key:
        return
    row = bag.get(key)
    if row is None:
        row = _blank_item()
        row["uk"] = uk
        row["name"] = clean_text(line.get("name")) or uk
        bag[key] = row
    row["qty"] = _money(row["qty"] + _num(line.get("qty")))
    row["amount"] = _money(row["amount"] + _num(line.get("amount")))
    row["times"] += 1
    group = clean_text(line.get("group"))
    rep = clean_text(line.get("rep"))
    if group and not row["group"]:
        row["group"] = group
    if rep and not row["rep"]:
        row["rep"] = rep
    invoice = clean_text(line.get("invoice"))
    if invoice and invoice not in row["invoices"]:
        row["invoices"].append(invoice)
    if not row["invoice_id"] and line.get("invoice_id"):
        row["invoice_id"] = line.get("invoice_id") or ""


def _public_items(rows, skip_uk=""):
    skip = (skip_uk or "").lower()
    out = []
    for row in rows or []:
        if (row.get("uk") or "").lower() == skip:
            continue
        out.append({
            "uk": row.get("uk") or "",
            "name": row.get("name") or "",
            "qty": _money(row.get("qty")),
            "amount": _money(row.get("amount")),
            "times": int(row.get("times") or 0),
        })
    out.sort(key=lambda row: (-(row["times"]), -(row["amount"]), (row["name"] or "").lower()))
    return out


def _merge_days(by_day, days, skip_uk):
    merged = {}
    for day in days:
        for key, row in (by_day.get(day) or {}).items():
            if key == (skip_uk or "").lower():
                continue
            slot = merged.get(key)
            if slot is None:
                slot = {
                    "uk": row.get("uk") or "",
                    "name": row.get("name") or "",
                    "qty": 0.0,
                    "amount": 0.0,
                    "times": 0,
                }
                merged[key] = slot
            slot["qty"] = _money(slot["qty"] + _num(row.get("qty")))
            slot["amount"] = _money(slot["amount"] + _num(row.get("amount")))
            slot["times"] += 1
    return _public_items(merged.values())


def _identity(party, party_uk, item_row, attrs):
    group = item_row.get("group") or ""
    rep = item_row.get("rep") or ""
    out = {
        "party": party,
        "party_uk": party_uk,
        "group": group,
        "group_uk": account_uk(group) if group else "",
        "rep": rep,
        "rep_uk": account_uk(rep) if rep else "",
        "item": item_row.get("name") or "",
        "item_uk": item_row.get("uk") or "",
    }
    out.update(attrs or {})
    return out


def _pairs_for_customer(lines, item_attrs, as_of):
    by_day = {}
    party = ""
    for line in lines or []:
        when = line.get("date")
        if not when or (as_of is not None and when > as_of):
            continue
        name = clean_text(line.get("party"))
        if not name:
            continue
        if not party:
            party = name
        bag = by_day.setdefault(_day_key(when), {})
        _absorb(bag, line)
        if not bag:
            by_day.pop(_day_key(when), None)
    if not party or not by_day:
        return [], []
    party_uk = account_uk(party)
    days = sorted(by_day.keys())
    item_keys = {}
    for day in days:
        for key, row in by_day[day].items():
            item_keys.setdefault(key, row.get("uk") or "")
    cycles = []
    pairs = []
    for item_key, item_uk in item_keys.items():
        bought = [day for day in days if item_key in by_day[day]]
        if not bought:
            continue
        attrs = _attrs_for(item_uk, item_attrs)
        points = []
        gaps = []
        last_row = None
        prev = None
        for day in bought:
            row = by_day[day][item_key]
            last_row = row
            when = _day_dt(day)
            point = {
                "date_iso": _iso(when),
                "date_label": _fmt_day(when),
                "amount": _money(row.get("amount")),
                "gap_days": None,
                "intervene_orders": 0,
            }
            if prev is not None:
                lo = bisect.bisect_right(days, prev)
                hi = bisect.bisect_left(days, day)
                between = days[lo:hi]
                wait = _merge_days(by_day, between, item_uk)
                gap = max(0, (when - _day_dt(prev)).days)
                prev_when = _day_dt(prev)
                ident = _identity(party, party_uk, row, attrs)
                cycles.append({
                    **ident,
                    "when": when,
                    "date_iso": point["date_iso"],
                    "date_label": point["date_label"],
                    "prev_iso": _iso(prev_when),
                    "prev_label": _fmt_day(prev_when),
                    "gap_days": gap,
                    "qty": _money(row.get("qty")),
                    "amount": _money(row.get("amount")),
                    "invoice": ", ".join(row.get("invoices") or []),
                    "invoice_id": row.get("invoice_id") or "",
                    "intervene_orders": len(between),
                    "intervene_items": len(wait),
                    "wait": wait,
                    "same_day": _public_items(by_day[day].values(), item_uk),
                })
                gaps.append(gap)
                point["gap_days"] = gap
                point["intervene_orders"] = len(between)
            points.append(point)
            prev = day
        last_when = _day_dt(bought[-1])
        days_since = max(0, (as_of - last_when).days) if as_of is not None else None
        pairs.append({
            **_identity(party, party_uk, last_row or {}, attrs),
            "purchases": len(bought),
            "gaps": gaps,
            "median": _percentile(gaps, 0.5),
            "points": points,
            "days_since": days_since,
            "last_iso": _iso(last_when),
            "last_label": _fmt_day(last_when),
        })
    return cycles, pairs


def build_repurchase_index(item_lines_by_uk, item_attrs, as_of, start_month=4):
    """Closed cycles and open pairs, one customer and item at a time."""
    by_party = {}
    for lines in (item_lines_by_uk or {}).values():
        for line in lines or []:
            party = account_uk(line.get("party")).lower()
            if not party or not line.get("date"):
                continue
            by_party.setdefault(party, []).append(line)
    cycles = []
    pairs = []
    buckets = {key: {} for key, _uk_key in _BUCKETS}
    for lines in by_party.values():
        got_cycles, got_pairs = _pairs_for_customer(lines, item_attrs, as_of)
        for row in got_cycles:
            cycles.append(row)
            _bucket_row(buckets, row, "cycles")
        for row in got_pairs:
            pairs.append(row)
            _bucket_row(buckets, row, "pairs")
    return {
        "as_of": as_of,
        "start_month": start_month or 4,
        "cycles": cycles,
        "pairs": pairs,
        "by": buckets,
    }


def _bucket_row(buckets, row, kind):
    for key, uk_key in _BUCKETS:
        uk = (row.get(uk_key) or "").lower()
        if not uk:
            continue
        slot = buckets[key].get(uk)
        if slot is None:
            slot = {"cycles": [], "pairs": []}
            buckets[key][uk] = slot
        slot[kind].append(row)


def ensure_repurchase(book):
    cached = (book or {}).get("repurchase_index")
    if cached is not None:
        return cached
    cached = build_repurchase_index(
        (book or {}).get("item_lines_by_uk"),
        (book or {}).get("item_attrs"),
        (book or {}).get("as_of"),
        (book or {}).get("fiscal_year_start_month") or 4,
    )
    if book is not None:
        book["repurchase_index"] = cached
    return cached


def _wants(filters):
    out = {}
    for key, _uk_key, _name_key in _FILTERS:
        text = account_uk((filters or {}).get(key))
        if text:
            out[key] = text.lower()
    return out


def _row_ok(row, wants):
    if not wants:
        return True
    for key, uk_key, name_key in _FILTERS:
        want = wants.get(key)
        if not want:
            continue
        uk = (row.get(uk_key) or "").lower()
        name = (row.get(name_key) or "").lower()
        if want != uk and want != name:
            return False
    return True


def _member_axis(wants):
    if wants.get("party") and not wants.get("item"):
        return "item"
    if wants.get("item"):
        return "customer"
    if wants.get("category") or wants.get("item_group") or wants.get("brand") or wants.get("supplier"):
        return "item"
    return "customer"


def _timeline_kind(wants):
    """Which name the repeat history row should lead with."""
    if not wants:
        return ""
    keys = [key for key in wants if wants.get(key)]
    if keys == ["party"]:
        return "item"
    if keys == ["item"]:
        return "customer"
    return "both"


def _add_companion(bag, row):
    key = ((row.get("uk") or row.get("name") or "").lower())
    if not key:
        return
    slot = bag.get(key)
    if slot is None:
        slot = {
            "uk": row.get("uk") or "",
            "name": row.get("name") or "",
            "qty": 0.0,
            "amount": 0.0,
            "times": 0,
        }
        bag[key] = slot
    slot["qty"] = _money(slot["qty"] + _num(row.get("qty")))
    slot["amount"] = _money(slot["amount"] + _num(row.get("amount")))
    slot["times"] += int(row.get("times") or 0)


def _top_companions(bag, cap):
    rows = list((bag or {}).values())
    for row in rows:
        row["qty"] = _money(row.get("qty"))
        row["amount"] = _money(row.get("amount"))
    rows.sort(key=lambda row: (-(row.get("times") or 0), -(row.get("amount") or 0), (row.get("name") or "").lower()))
    return rows[:cap]


def _gap_key(days):
    days = max(0, int(days or 0))
    for band in GAP_BANDS:
        limit = band.get("max_days")
        if limit is None or days <= limit:
            return band["key"]
    return GAP_BANDS[-1]["key"]


def _gap_buckets():
    return [{
        "key": band["key"],
        "label": band["label"],
        "count": 0,
        "value": 0.0,
    } for band in GAP_BANDS]


def _intervene_buckets():
    return [{"key": key, "label": label, "count": 0, "value": 0.0} for key, label in _INTERVENE]


def _touch(buckets, key, amount):
    for bucket in buckets:
        if bucket["key"] == key:
            bucket["count"] += 1
            bucket["value"] = _money(bucket["value"] + amount)
            return


def _members(cycles, axis):
    grouped = {}
    uk_key = "item_uk" if axis == "item" else "party_uk"
    name_key = "item" if axis == "item" else "party"
    for cycle in cycles or []:
        uk = cycle.get(uk_key) or ""
        key = uk.lower() or (cycle.get(name_key) or "").lower()
        if not key:
            continue
        slot = grouped.get(key)
        if slot is None:
            slot = {
                "uk": uk,
                "name": cycle.get(name_key) or uk,
                "cycles": 0,
                "value": 0.0,
                "gaps": [],
                "waits": [],
            }
            grouped[key] = slot
        slot["cycles"] += 1
        slot["value"] = _money(slot["value"] + _num(cycle.get("amount")))
        slot["gaps"].append(int(cycle.get("gap_days") or 0))
        slot["waits"].append(int(cycle.get("intervene_orders") or 0))
    rows = []
    for slot in grouped.values():
        rows.append({
            "uk": slot["uk"],
            "name": slot["name"],
            "cycles": slot["cycles"],
            "value": slot["value"],
            "median": _percentile(slot["gaps"], 0.5),
            "p25": _percentile(slot["gaps"], 0.25),
            "p75": _percentile(slot["gaps"], 0.75),
            "intervene_median": _percentile(slot["waits"], 0.5),
        })
    rows.sort(key=lambda row: (-row["cycles"], -(row["value"] or 0), (row["name"] or "").lower()))
    return rows[:MEMBER_CAP]


def _period(cycles, axis):
    gaps = []
    waits = []
    buckets = _gap_buckets()
    intervene = _intervene_buckets()
    wait_bag = {}
    same_bag = {}
    lines = []
    value = 0.0
    for cycle in cycles or []:
        amount = _money(cycle.get("amount"))
        gap = int(cycle.get("gap_days") or 0)
        orders = int(cycle.get("intervene_orders") or 0)
        gaps.append(gap)
        waits.append(orders)
        value = _money(value + amount)
        bucket = _gap_key(gap)
        wait_key = _intervene_key(orders)
        _touch(buckets, bucket, amount)
        _touch(intervene, wait_key, amount)
        for row in cycle.get("wait") or []:
            _add_companion(wait_bag, row)
        for row in cycle.get("same_day") or []:
            _add_companion(same_bag, row)
        between = [
            {"uk": row.get("uk") or "", "name": row.get("name") or ""}
            for row in (cycle.get("wait") or [])
            if row.get("name")
        ]
        lines.append({
            "date_iso": cycle.get("date_iso") or "",
            "date_label": cycle.get("date_label") or "",
            "prev_iso": cycle.get("prev_iso") or "",
            "prev_label": cycle.get("prev_label") or "",
            "between": between[:8],
            "party": cycle.get("party") or "",
            "party_uk": cycle.get("party_uk") or "",
            "item": cycle.get("item") or "",
            "item_uk": cycle.get("item_uk") or "",
            "invoice": cycle.get("invoice") or "",
            "invoice_id": cycle.get("invoice_id") or "",
            "gap_days": gap,
            "bucket": bucket,
            "intervene_orders": orders,
            "intervene_items": int(cycle.get("intervene_items") or 0),
            "intervene": wait_key,
            "amount": amount,
            "qty": _money(cycle.get("qty")),
        })
    lines.sort(key=lambda row: (row.get("date_iso") or "", row.get("party") or "", row.get("item") or ""), reverse=True)
    truncated = len(lines) > LINE_CAP
    return {
        "orders": len(cycles or []),
        "value": value,
        "median": _percentile(gaps, 0.5),
        "p25": _percentile(gaps, 0.25),
        "p75": _percentile(gaps, 0.75),
        "intervene_median": _percentile(waits, 0.5),
        "buckets": buckets,
        "intervene": intervene,
        "lines": lines[:LINE_CAP],
        "lines_truncated": truncated,
        "wait_items": _top_companions(wait_bag, WAIT_CAP),
        "same_day_items": _top_companions(same_bag, SAME_CAP),
        "members": _members(cycles, axis),
    }


def _blank_period(axis):
    return _period([], axis)


def _timeline(pairs, kind):
    """Every customer × item in this view, including items bought only once."""
    series = [pair for pair in (pairs or []) if pair.get("points")]
    if kind == "item":
        series.sort(key=lambda pair: ((pair.get("item") or "").lower(), pair.get("last_iso") or ""))
    elif kind == "customer":
        series.sort(key=lambda pair: ((pair.get("party") or "").lower(), pair.get("last_iso") or ""))
    else:
        series.sort(key=lambda pair: ((pair.get("party") or "").lower(), (pair.get("item") or "").lower()))
    out = []
    for pair in series:
        item = pair.get("item") or ""
        party = pair.get("party") or ""
        if kind == "item":
            name, uk = item, pair.get("item_uk") or ""
        elif kind == "customer":
            name, uk = party, pair.get("party_uk") or ""
        else:
            name, uk = (party + " · " + item).strip(" · "), pair.get("party_uk") or ""
        out.append({
            "uk": uk,
            "name": name,
            "kind": kind,
            "party": party,
            "party_uk": pair.get("party_uk") or "",
            "item": item,
            "item_uk": pair.get("item_uk") or "",
            "median": pair.get("median"),
            "purchases": int(pair.get("purchases") or len(pair.get("points") or [])),
            "points": pair.get("points") or [],
        })
    return out


def _overdue(pairs):
    rows = []
    for pair in pairs or []:
        median = pair.get("median")
        days_since = pair.get("days_since")
        if median is None or days_since is None or days_since <= median:
            continue
        rows.append({
            "party": pair.get("party") or "",
            "party_uk": pair.get("party_uk") or "",
            "item": pair.get("item") or "",
            "item_uk": pair.get("item_uk") or "",
            "group": pair.get("group") or "",
            "rep": pair.get("rep") or "",
            "last_iso": pair.get("last_iso") or "",
            "last_label": pair.get("last_label") or "",
            "days_since": int(days_since),
            "median": int(median),
        })
    rows.sort(key=lambda row: (-(row["days_since"] - row["median"]), row.get("party") or "", row.get("item") or ""))
    return rows[:OVERDUE_CAP]


def empty_repurchase():
    blank = _blank_period("customer")
    return {
        "bands": [{"key": band["key"], "label": band["label"]} for band in GAP_BANDS],
        "intervene_bands": [{"key": key, "label": label} for key, label in _INTERVENE],
        "member_axis": "customer",
        "overall": blank,
        "fy": _blank_period("customer"),
        "month": _blank_period("customer"),
        "by_fy": [],
        "months": [],
        "once": 0,
        "repeaters": 0,
        "overdue": [],
        "timeline": [],
    }


def _selected(index, wants):
    """One filter reads its bucket. Several filters scan the full list."""
    if len(wants) == 1:
        key, want = next(iter(wants.items()))
        slot = ((index.get("by") or {}).get(key) or {}).get(want) or {}
        return list(slot.get("cycles") or []), list(slot.get("pairs") or [])
    cycles = [row for row in (index.get("cycles") or []) if _row_ok(row, wants)]
    pairs = [row for row in (index.get("pairs") or []) if _row_ok(row, wants)]
    return cycles, pairs


def repurchase_for(index, **filters):
    """Summarise cached cycles for one customer, group, rep, item, or item dimension."""
    index = index or {}
    wants = _wants(filters)
    axis = _member_axis(wants)
    cycles, pairs = _selected(index, wants)
    as_of = index.get("as_of")
    start_month = index.get("start_month") or 4
    summary = empty_repurchase()
    summary["member_axis"] = axis
    summary["overall"] = _period(cycles, axis)
    summary["once"] = sum(1 for pair in pairs if int(pair.get("purchases") or 0) == 1)
    repeat_keys = set()
    for cycle in cycles:
        repeat_keys.add(((cycle.get("party_uk") or "").lower(), (cycle.get("item_uk") or "").lower()))
    summary["repeaters"] = len(repeat_keys)
    summary["overdue"] = _overdue(pairs)
    summary["as_of"] = _iso(as_of) if as_of is not None else ""
    kind = _timeline_kind(wants)
    summary["timeline"] = _timeline(pairs, kind) if kind else []

    by_fy = {}
    by_month = {}
    current_fy = _iso(fiscal_year_start(as_of, start_month)) if as_of is not None else ""
    current_month = "%04d-%02d" % (as_of.year, as_of.month) if as_of is not None else ""
    for cycle in cycles:
        when = cycle.get("when")
        if not when:
            continue
        fy_start = fiscal_year_start(when, start_month)
        fy_key = _iso(fy_start)
        by_fy.setdefault(fy_key, {"key": fy_key, "label": fy_label(fy_start), "cycles": []})
        by_fy[fy_key]["cycles"].append(cycle)
        month_key = "%04d-%02d" % (when.year, when.month)
        by_month.setdefault(month_key, {
            "key": month_key,
            "label": _month_label(when),
            "year": when.year,
            "month": when.month,
            "cycles": [],
        })
        by_month[month_key]["cycles"].append(cycle)

    def _pack(slot):
        period = _period(slot["cycles"], axis)
        period["key"] = slot["key"]
        period["label"] = slot["label"]
        if slot.get("year") is not None:
            period["year"] = slot["year"]
        if slot.get("month") is not None:
            period["month"] = slot["month"]
        return period

    summary["by_fy"] = [_pack(by_fy[key]) for key in sorted(by_fy.keys(), reverse=True)]
    summary["months"] = [_pack(by_month[key]) for key in sorted(by_month.keys(), reverse=True)]
    summary["fy"] = next((row for row in summary["by_fy"] if row["key"] == current_fy), _blank_period(axis))
    summary["month"] = next((row for row in summary["months"] if row["key"] == current_month), _blank_period(axis))
    return summary


def stamp_saved_details(index, details, field):
    """Write one saved repurchase block per detail. Skips a block already present."""
    for uk, detail in (details or {}).items():
        if not isinstance(detail, dict) or detail.get("repurchase"):
            continue
        detail["repurchase"] = repurchase_for(index, **{field: detail.get("uk") or uk})


def attach_repurchase(store, detail, **filters):
    if not detail:
        return detail
    from server.book import load_book

    book = load_book(store)
    out = dict(detail)
    out["repurchase"] = repurchase_for(ensure_repurchase(book), **filters)
    return out
