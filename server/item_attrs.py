"""Optional item attributes. A blank uses that field's default label."""

from __future__ import annotations

from vay.dates import clean_text

from server.customers import account_uk
from server.mappers import is_skip_dest
from server.settings import ITEM_ATTR_FIELDS

ATTR_TYPE = "item_attr"
NONE_UK = "__none__"
DEFAULT_ATTR_VALUES = {
    "Category": "No category",
    "Item Group": "No item group",
    "Brand": "No brand",
    "Supplier": "No supplier",
}


def resolved_attr(name, value):
    """Stored text, or the default for that field when it is missing."""
    text = clean_text(value)
    if text:
        return text, account_uk(text)
    return DEFAULT_ATTR_VALUES[name], NONE_UK


def _source_key(name):
    return name + " Source"


def mapped_attr_names(column_map, headers=None):
    """Attr fields this file actually maps. A canonical header counts; a skipped one does not."""
    column_map = column_map or {}
    names = []
    claimed = set()
    for src, dest in column_map.items():
        src_name = str(src or "").strip()
        if is_skip_dest(dest):
            claimed.add(src_name)
            continue
        dest_name = str(dest or "").strip()
        claimed.add(src_name)
        if dest_name in ITEM_ATTR_FIELDS and dest_name not in names:
            names.append(dest_name)
    for header in headers or []:
        header = str(header or "").strip()
        if not header or header in claimed:
            continue
        if header in ITEM_ATTR_FIELDS and header not in names:
            names.append(header)
    return names


def _load(store, uk):
    row = store.find_row(ATTR_TYPE, uk)
    return row, dict((row or {}).get("fields") or {})


def attr_map(store):
    out = {}
    for row in store.rows_of_type(ATTR_TYPE):
        uk = (row.get("uk") or "").lower()
        if not uk:
            continue
        fields = row.get("fields") or {}
        out[uk] = {name: clean_text(fields.get(name)) for name in ITEM_ATTR_FIELDS}
    return out


def attrs_for(store, uk):
    uk = account_uk(uk)
    _row, fields = _load(store, uk)
    return {name: clean_text(fields.get(name)) for name in ITEM_ATTR_FIELDS}


def public_attrs(store, uk):
    """Names plus link ids. A blank links to that field's default row."""
    values = attrs_for(store, uk)
    out = {}
    for name, key, uk_key in (
        ("Category", "category", "category_uk"),
        ("Item Group", "item_group", "item_group_uk"),
        ("Brand", "brand", "brand_uk"),
        ("Supplier", "supplier", "supplier_uk"),
    ):
        text, link = resolved_attr(name, values.get(name))
        out[key] = text
        out[uk_key] = link
    return out


def sync_item_attrs(store, type_name, prepared, column_map, headers, upload_id):
    """Write mapped attr columns only.

    Stock owns a field once it maps it, including a mapped blank.
    Item lines fill a field only when stock has not mapped it.
    """
    if type_name not in ("stock", "items"):
        return {"attrs_updated": 0}
    names = mapped_attr_names(column_map, headers)
    if not names:
        return {"attrs_updated": 0}
    updated = 0
    for fields, _uk in prepared or []:
        item_name = clean_text((fields or {}).get("Item Name"))
        if not item_name:
            continue
        item_uk = account_uk(item_name)
        _existing, prev = _load(store, item_uk)
        changed = False
        for name in names:
            source = clean_text(prev.get(_source_key(name))).lower()
            if type_name == "items" and source == "stock":
                continue
            value = clean_text((fields or {}).get(name))
            if type_name == "items" and not value and source != "items":
                continue
            origin = "stock" if type_name == "stock" else "items"
            if prev.get(name, "") != value or source != origin:
                prev[name] = value
                prev[_source_key(name)] = origin
                changed = True
        if not changed:
            continue
        prev["Item Name"] = item_name
        store.upsert_row({
            "type": ATTR_TYPE,
            "uk": item_uk,
            "source_upload_id": str(upload_id or ""),
            "fields": prev,
        })
        updated += 1
    return {"attrs_updated": updated}
