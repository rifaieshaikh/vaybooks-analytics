"""360 views saved as separate documents. A page read loads one part, not the report."""

from __future__ import annotations

import json
import time

from server.customers import account_uk

_META_FIELDS = (
    "as_of",
    "default_min",
    "default_max_days",
    "low_count",
    "soon_count",
    "under_count",
    "over_count",
    "dead_count",
    "out_of_stock_count",
    "buy_count",
    "buy_qty_sum",
    "buy_value_sum",
    "group_options",
    "rep_options",
    "item_options",
)

_LISTS = ("groups", "reps", "items")
_DETAILS = (
    ("customers", "customer"),
    ("group_details", "group"),
    ("rep_details", "rep"),
    ("item_details", "item"),
)


def _items_list_body(cards):
    """The stock table does not use each item's sales-pace history."""
    out = []
    for card in cards or []:
        if isinstance(card, dict) and "velocity" in card:
            row = dict(card)
            row.pop("velocity", None)
            out.append(row)
        else:
            out.append(card)
    return out


def _json_body(value):
    return json.dumps(value, default=str, separators=(",", ":"))


def _load_body(body):
    if body is None:
        return None
    if isinstance(body, (dict, list)):
        return body
    try:
        return json.loads(body)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _part_key(uk):
    return account_uk(uk).lower()


def split_business_doc(doc):
    """Keep the company profile small. Settlements and order gaps load with their tabs."""
    if not isinstance(doc, dict):
        return doc, None, None
    if "settlements" not in doc and "sales_gaps" not in doc:
        return doc, None, None
    out = dict(doc)
    settlements = out.pop("settlements", None)
    gaps = out.pop("sales_gaps", None)
    if settlements is not None:
        out["settlements_separate"] = True
    if gaps is not None:
        out["sales_gaps_separate"] = True
    return out, settlements, gaps


def persist_item_tabs(store, run_id, key, profile, tabs):
    """Header stays on the item. Buyers and movement load with their tabs."""
    rid = str(run_id or "")
    part_key = _part_key(key)
    if not rid or not part_key or not tabs:
        return profile
    for section, body in tabs.items():
        store.put_view_part(rid, "item_tab", part_key + ":" + section, _json_body(body))
    store.put_view_part(rid, "item", part_key, _json_body(profile))
    return profile


def persist_rep_tabs(store, run_id, key, profile, tabs):
    """Replace one fat sales-rep document with the header plus one document per tab."""
    rid = str(run_id or "")
    part_key = _part_key(key)
    if not rid or not part_key or not tabs:
        return profile
    for section, body in tabs.items():
        store.put_view_part(rid, "rep_tab", part_key + ":" + section, _json_body(body))
    store.put_view_part(rid, "rep", part_key, _json_body(profile))
    return profile


def persist_group_tabs(store, run_id, key, profile, tabs):
    """Replace one fat group document with the header plus one document per tab."""
    rid = str(run_id or "")
    part_key = _part_key(key)
    if not rid or not part_key or not tabs:
        return profile
    for section, body in tabs.items():
        store.put_view_part(rid, "group_tab", part_key + ":" + section, _json_body(body))
    store.put_view_part(rid, "group", part_key, _json_body(profile))
    return profile


def persist_customer_tabs(store, run_id, key, profile, tabs):
    """Replace one fat customer document with the header plus one document per tab."""
    rid = str(run_id or "")
    part_key = _part_key(key)
    if not rid or not part_key or not tabs:
        return profile
    for section, body in tabs.items():
        store.put_view_part(rid, "customer_tab", part_key + ":" + section, _json_body(body))
    store.put_view_part(rid, "customer", part_key, _json_body(profile))
    return profile


def persist_business_split(store, run_id, doc):
    light, settlements, gaps = split_business_doc(doc)
    if settlements is None and gaps is None:
        return light
    rid = str(run_id or "")
    if not rid:
        return light
    if settlements is not None:
        store.put_view_part(rid, "business_settlements", "root", _json_body(settlements))
    if gaps is not None:
        store.put_view_part(rid, "business_gaps", "root", _json_body(gaps))
    store.put_view_part(rid, "business", "root", _json_body(light))
    return light


def _detach_repurchase(detail):
    if not isinstance(detail, dict):
        return detail, None
    if "repurchase" not in detail:
        out = dict(detail)
        out["repurchase_separate"] = True
        return out, None
    out = dict(detail)
    repurchase = out.pop("repurchase")
    out["repurchase_separate"] = True
    return out, repurchase


def _save_units(views):
    views = views or {}
    total = 2 + len(_LISTS) + 1
    for source, _kind in _DETAILS:
        total += len(views.get(source) or {})
    for packed in (views.get("item_dims") or {}).values():
        if isinstance(packed, dict):
            total += 1 + len(packed.get("details") or {})
    return max(total, 1)


def save_view_parts(store, run_id, views, on_progress=None):
    """Write one document per list, profile, and repurchase block."""
    views = views or {}
    parts = []
    total = _save_units(views)
    seen = 0

    def tick(label):
        nonlocal seen
        seen += 1
        if not on_progress:
            return
        stride = max(1, total // 40)
        if seen not in (1, total) and seen % stride:
            return
        on_progress(0.8 * (min(seen, total) / float(total)), label)
        time.sleep(0)

    def add(kind, key, value, label=""):
        if value is None:
            return
        parts.append((kind, key, _json_body(value)))
        if label:
            tick(label)

    meta = {field: views.get(field) for field in _META_FIELDS if field in views}
    add("meta", "root", meta, "report details")
    add("directory", "root", views.get("directory") or {}, "customer list")
    for name in _LISTS:
        value = views.get(name) or []
        if name == "items":
            value = _items_list_body(value)
        add("list", name, value, name)
    business, settlements, gaps = split_business_doc(views.get("business") or {})
    add("business", "root", business, "business")
    if settlements is not None:
        add("business_settlements", "root", settlements, "settlements")
    if gaps is not None:
        add("business_gaps", "root", gaps, "sales gaps")

    for source, kind in _DETAILS:
        rows = list((views.get(source) or {}).items())
        for index, (uk, detail) in enumerate(rows, start=1):
            key = _part_key(uk)
            if not key:
                tick(kind)
                continue
            slim, repurchase = _detach_repurchase(detail)
            if kind == "customer":
                from server.run_views import split_customer_doc
                profile, tabs = split_customer_doc(slim)
                parts.append((kind, key, _json_body(profile)))
                for section, body in (tabs or {}).items():
                    parts.append(("customer_tab", key + ":" + section, _json_body(body)))
            elif kind == "rep":
                from server.run_views import split_rep_doc
                profile, tabs = split_rep_doc(slim)
                parts.append((kind, key, _json_body(profile)))
                for section, body in (tabs or {}).items():
                    parts.append(("rep_tab", key + ":" + section, _json_body(body)))
            elif kind == "group":
                from server.run_views import split_group_doc
                profile, tabs = split_group_doc(slim)
                parts.append((kind, key, _json_body(profile)))
                for section, body in (tabs or {}).items():
                    parts.append(("group_tab", key + ":" + section, _json_body(body)))
            elif kind == "item":
                from server.run_views import split_item_doc
                profile, tabs = split_item_doc(slim)
                parts.append((kind, key, _json_body(profile)))
                for section, body in (tabs or {}).items():
                    parts.append(("item_tab", key + ":" + section, _json_body(body)))
            else:
                parts.append((kind, key, _json_body(slim)))
            _append_repurchase(parts, kind, key, repurchase)
            tick("%s · %d of %d" % (kind, index, len(rows)))

    for dimension, packed in (views.get("item_dims") or {}).items():
        if not isinstance(packed, dict):
            continue
        listing = {
            "dimension": packed.get("dimension") or dimension,
            "label": packed.get("label") or "",
            "plural": packed.get("plural") or "",
            "none_label": packed.get("none_label") or "",
            "hash": packed.get("hash") or "",
            "rows": packed.get("rows") or [],
        }
        add("dim_list", dimension, listing, dimension)
        details = list((packed.get("details") or {}).items())
        for index, (uk, detail) in enumerate(details, start=1):
            key = _part_key(uk)
            if not key:
                tick(dimension)
                continue
            slim, repurchase = _detach_repurchase(detail)
            parts.append(("dim_detail", dimension + ":" + key, _json_body(slim)))
            _append_repurchase(parts, dimension, key, repurchase)
            tick("%s · %d of %d" % (dimension, index, len(details)))

    def on_write(done_n, total_n):
        if on_progress and total_n:
            frac = 0.8 + 0.19 * (float(done_n) / float(total_n))
            on_progress(frac, "pages · %d of %d" % (done_n, total_n))

    store.replace_view_parts(run_id, parts, on_batch=on_write)
    return len(parts)


class PartMap:
    """One entity kind. ``get`` reads that document only."""

    def __init__(self, store, run_id, kind):
        self.store = store
        self.run_id = str(run_id)
        self.kind = kind
        self._cache = {}

    def get(self, key, default=None):
        part_key = _part_key(key)
        if not part_key:
            return default
        if part_key not in self._cache:
            self._cache[part_key] = _load_body(self.store.get_view_part(self.run_id, self.kind, part_key))
        found = self._cache[part_key]
        return found if found is not None else default

    def items(self):
        rows = []
        for body in self.store.list_view_parts(self.run_id, self.kind):
            loaded = _load_body(body)
            if isinstance(loaded, dict):
                rows.append((loaded.get("uk") or "", loaded))
        return rows

    def __bool__(self):
        return True


class PrefixedMap:
    def __init__(self, store, run_id, kind, prefix):
        self.store = store
        self.run_id = str(run_id)
        self.kind = kind
        self.prefix = prefix
        self._cache = {}

    def get(self, key, default=None):
        part_key = self.prefix + _part_key(key)
        if part_key not in self._cache:
            self._cache[part_key] = _load_body(self.store.get_view_part(self.run_id, self.kind, part_key))
        found = self._cache[part_key]
        return found if found is not None else default

    def values(self):
        out = []
        for body in self.store.list_view_parts(self.run_id, self.kind, prefix=self.prefix):
            loaded = _load_body(body)
            if isinstance(loaded, dict):
                out.append(loaded)
        return out

    def __bool__(self):
        return True


class DimViews:
    def __init__(self, store, run_id):
        self.store = store
        self.run_id = str(run_id)
        self._packs = {}

    def get(self, dimension, default=None):
        if dimension in self._packs:
            return self._packs[dimension]
        pack = _load_body(self.store.get_view_part(self.run_id, "dim_list", dimension))
        if not isinstance(pack, dict):
            self._packs[dimension] = None
            return default
        pack = dict(pack)
        pack["details"] = PrefixedMap(self.store, self.run_id, "dim_detail", dimension + ":")
        self._packs[dimension] = pack
        return pack

    def __contains__(self, dimension):
        return self.get(dimension) is not None

    def __bool__(self):
        return True


class SnapshotViews:
    """Saved 360 parts for one report. Each get loads that part from the store."""

    split = True

    def __init__(self, store, run_id):
        self.store = store
        self.run_id = str(run_id)
        self._meta = None
        self._parts = {}
        self._maps = {}

    def _meta_doc(self):
        if self._meta is None:
            loaded = _load_body(self.store.get_view_part(self.run_id, "meta", "root"))
            self._meta = loaded if isinstance(loaded, dict) else {}
        return self._meta

    def _once(self, kind, key):
        token = (kind, key)
        if token not in self._parts:
            self._parts[token] = _load_body(self.store.get_view_part(self.run_id, kind, key))
        return self._parts[token]

    def _map(self, kind):
        if kind not in self._maps:
            self._maps[kind] = PartMap(self.store, self.run_id, kind)
        return self._maps[kind]

    def get(self, key, default=None):
        if key in _META_FIELDS:
            return self._meta_doc().get(key, default)
        if key == "directory":
            found = self._once("directory", "root")
            return found if found is not None else default
        if key in _LISTS:
            found = self._once("list", key)
            return found if found is not None else default
        if key == "business":
            found = self._once("business", "root")
            return found if found is not None else default
        if key == "customers":
            return self._map("customer")
        if key == "group_details":
            return self._map("group")
        if key == "rep_details":
            return self._map("rep")
        if key == "item_details":
            return self._map("item")
        if key == "item_dims":
            return DimViews(self.store, self.run_id)
        return default


def _period_without_lines(period):
    if not isinstance(period, dict) or "lines" not in period:
        return period, None
    out = dict(period)
    lines = out.pop("lines")
    out["lines_separate"] = True
    return out, lines


def split_repurchase_doc(doc):
    """Summary for the tiles. The history and each period's rows load on their own."""
    if not isinstance(doc, dict):
        return doc, None, []
    if doc.get("timeline_separate") and "timeline" not in doc:
        return doc, None, []
    out = dict(doc)
    timeline = out.pop("timeline", None)
    out["timeline_separate"] = True
    line_parts = []
    for field, token in (("overall", "overall"), ("month", "month"), ("fy", "fy")):
        if field not in out:
            continue
        period, lines = _period_without_lines(out.get(field))
        out[field] = period
        if lines is not None:
            line_parts.append((token, lines))
    months = []
    for row in out.get("months") or []:
        period, lines = _period_without_lines(row)
        months.append(period if period is not None else row)
        if lines is not None:
            line_parts.append(("month:" + str((row or {}).get("key") or ""), lines))
    out["months"] = months
    years = []
    for row in out.get("by_fy") or []:
        period, lines = _period_without_lines(row)
        years.append(period if period is not None else row)
        if lines is not None:
            line_parts.append(("fy:" + str((row or {}).get("key") or ""), lines))
    out["by_fy"] = years
    return out, timeline, line_parts


def _repurchase_key(entity, uk):
    key = str(entity or "") + ":" + _part_key(uk)
    if not key or key.startswith(":"):
        return ""
    return key


def _repurchase_is_heavy(doc):
    if not isinstance(doc, dict) or doc.get("timeline_separate"):
        return False
    if len(doc.get("timeline") or []) > 400:
        return True
    months = doc.get("months") or []
    return len(months) > 8 and any(isinstance(row, dict) and row.get("lines") for row in months)


_TIMELINE_PAGE = 40
_PERIOD_INDEX = (
    "key", "label", "orders", "median", "value", "year", "month",
    "p25", "p75", "lines_separate", "lines_truncated",
)


def _timeline_span(rows):
    min_iso = ""
    max_iso = ""
    for row in rows or []:
        for point in (row or {}).get("points") or []:
            iso = str((point or {}).get("date_iso") or "")[:10]
            if len(iso) < 10:
                continue
            if not min_iso or iso < min_iso:
                min_iso = iso
            if not max_iso or iso > max_iso:
                max_iso = iso
    return min_iso, max_iso


def _timeline_pages(key, timeline):
    rows = list(timeline or [])
    pages = (len(rows) + _TIMELINE_PAGE - 1) // _TIMELINE_PAGE if rows else 0
    min_iso, max_iso = _timeline_span(rows)
    chunks = []
    for index in range(pages):
        start = index * _TIMELINE_PAGE
        chunks.append((key + ":p" + str(index), rows[start:start + _TIMELINE_PAGE]))
    meta = {
        "paged": True,
        "total": len(rows),
        "pages": pages,
        "page_size": _TIMELINE_PAGE,
        "min_iso": min_iso,
        "max_iso": max_iso,
    }
    return meta, chunks


def _write_timeline_pages(store, run_id, key, timeline):
    meta, chunks = _timeline_pages(key, timeline)
    for part_key, chunk in chunks:
        store.put_view_part(run_id, "repurchase_timeline", part_key, _json_body(chunk))
    store.put_view_part(run_id, "repurchase_timeline", key, _json_body(meta))
    return meta


def _months_are_fat(doc):
    if not isinstance(doc, dict):
        return False
    for field in ("months", "by_fy"):
        for row in (doc.get(field) or [])[:1]:
            if isinstance(row, dict) and ("members" in row or "buckets" in row):
                return True
    return False


def _lighten_periods(summary):
    """Keep the month list as an index. Each month's chart loads on its own."""
    out = dict(summary)
    parts = []
    for field, token in (("months", "month"), ("by_fy", "fy")):
        light = []
        for row in out.get(field) or []:
            if not isinstance(row, dict) or ("members" not in row and "buckets" not in row):
                light.append(row)
                continue
            body = dict(row)
            body.pop("lines", None)
            parts.append((token + ":" + str(row.get("key") or ""), body))
            light.append({k: row[k] for k in _PERIOD_INDEX if k in row})
        out[field] = light
    return out, parts


def _append_repurchase(parts, entity, uk, doc):
    if not doc:
        return
    key = _repurchase_key(entity, uk)
    if not key:
        return
    if not _repurchase_is_heavy(doc):
        parts.append(("repurchase", key, _json_body(doc)))
        return
    summary, timeline, line_parts = split_repurchase_doc(doc)
    summary, period_parts = _lighten_periods(summary)
    if timeline is not None:
        meta, chunks = _timeline_pages(key, timeline)
        parts.append(("repurchase_timeline", key, _json_body(meta)))
        for part_key, chunk in chunks:
            parts.append(("repurchase_timeline", part_key, _json_body(chunk)))
    for token, lines in line_parts:
        parts.append(("repurchase_lines", key + ":" + token, _json_body(lines)))
    for token, body in period_parts:
        parts.append(("repurchase_period", key + ":" + token, _json_body(body)))
    parts.append(("repurchase", key, _json_body(summary)))


def persist_repurchase_split(store, run_id, entity, uk, doc):
    summary, timeline, line_parts = split_repurchase_doc(doc)
    key = _repurchase_key(entity, uk)
    rid = str(run_id or "")
    if not key or not rid or summary is doc:
        return summary
    summary, period_parts = _lighten_periods(summary)
    if timeline is not None:
        _write_timeline_pages(store, rid, key, timeline)
    for token, lines in line_parts:
        store.put_view_part(rid, "repurchase_lines", key + ":" + token, _json_body(lines))
    for token, body in period_parts:
        store.put_view_part(rid, "repurchase_period", key + ":" + token, _json_body(body))
    store.put_view_part(rid, "repurchase", key, _json_body(summary))
    return summary


def slim_repurchase_periods(store, run_id, entity, uk, doc):
    key = _repurchase_key(entity, uk)
    rid = str(run_id or "")
    if not key or not rid or not _months_are_fat(doc):
        return doc
    summary, period_parts = _lighten_periods(doc)
    for token, body in period_parts:
        store.put_view_part(rid, "repurchase_period", key + ":" + token, _json_body(body))
    store.put_view_part(rid, "repurchase", key, _json_body(summary))
    return summary


def load_repurchase(store, run_id, entity, uk):
    key = _repurchase_key(entity, uk)
    if not key:
        return None
    doc = _load_body(store.get_view_part(run_id, "repurchase", key))
    if _repurchase_is_heavy(doc):
        doc = persist_repurchase_split(store, run_id, entity, uk, doc)
    if _months_are_fat(doc):
        doc = slim_repurchase_periods(store, run_id, entity, uk, doc)
    return doc


def load_repurchase_timeline(store, run_id, entity, uk, page=0):
    key = _repurchase_key(entity, uk)
    empty = {"timeline": [], "total": 0, "page": 0, "pages": 0, "min_iso": "", "max_iso": ""}
    if not key:
        return empty
    loaded = _load_body(store.get_view_part(run_id, "repurchase_timeline", key))
    if isinstance(loaded, list):
        _write_timeline_pages(store, run_id, key, loaded)
        loaded = _load_body(store.get_view_part(run_id, "repurchase_timeline", key))
    if not isinstance(loaded, dict) or not loaded.get("paged"):
        doc = load_repurchase(store, run_id, entity, uk)
        timeline = doc.get("timeline") if isinstance(doc, dict) else None
        if isinstance(timeline, list) and timeline:
            _write_timeline_pages(store, run_id, key, timeline)
            loaded = _load_body(store.get_view_part(run_id, "repurchase_timeline", key))
        else:
            return empty
    try:
        page = max(0, int(page or 0))
    except (TypeError, ValueError):
        page = 0
    pages = int(loaded.get("pages") or 0)
    chunk = []
    if page < pages:
        found = _load_body(store.get_view_part(run_id, "repurchase_timeline", key + ":p" + str(page)))
        if isinstance(found, list):
            chunk = found
    return {
        "timeline": chunk,
        "total": int(loaded.get("total") or 0),
        "page": page,
        "pages": pages,
        "page_size": int(loaded.get("page_size") or _TIMELINE_PAGE),
        "min_iso": loaded.get("min_iso") or "",
        "max_iso": loaded.get("max_iso") or "",
    }


def load_repurchase_period(store, run_id, entity, uk, period, key):
    base = _repurchase_key(entity, uk)
    if not base:
        return {}
    token = ("fy" if (period or "") == "fy" else "month") + ":" + str(key or "")
    loaded = _load_body(store.get_view_part(run_id, "repurchase_period", base + ":" + token))
    if isinstance(loaded, dict):
        return loaded
    doc = load_repurchase(store, run_id, entity, uk) or {}
    current = doc.get("fy") if (period or "") == "fy" else doc.get("month")
    if isinstance(current, dict) and str(current.get("key") or "") == str(key or ""):
        return current
    return {}


def load_repurchase_lines(store, run_id, entity, uk, period, key):
    base = _repurchase_key(entity, uk)
    if not base:
        return []
    period = (period or "overall").strip()
    token = "overall" if period == "overall" else period + ":" + str(key or "")

    def read():
        loaded = _load_body(store.get_view_part(run_id, "repurchase_lines", base + ":" + token))
        return loaded if isinstance(loaded, list) else None

    found = read()
    if found is not None:
        return found
    doc = load_repurchase(store, run_id, entity, uk) or {}
    found = read()
    if found is not None:
        return found
    if period == "overall":
        return ((doc.get("overall") or {}).get("lines") or [])
    bucket = doc.get("months") if period == "month" else doc.get("by_fy")
    for row in bucket or []:
        if str((row or {}).get("key") or "") == str(key or ""):
            return (row or {}).get("lines") or []
    return []
