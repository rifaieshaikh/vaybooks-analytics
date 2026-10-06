"""Validate mapper documents. Two headers must not map to one field."""

from server.settings import SOURCE_TYPES

SKIP_DESTS = frozenset({"", "__skip__", "(skip)", "skip"})

# Source headers that are not the AppSheet names. Destinations stay canonical.
SALES_HEADER_PRESET = {
    "id": "plain_sales",
    "label": "Plain sales headers",
    "type": "sales",
    "column_map": {
        "Invoice Date": "Date",
        "Customer": "Party Name",
        "Rep": "Sales Rep",
        "Amount": "Net Amount",
    },
    "unique_key": ["Date", "Party Name", "Sales Rep", "Net Amount"],
}

PRESETS = (SALES_HEADER_PRESET,)


def preset_by_id(preset_id):
    for preset in PRESETS:
        if preset["id"] == preset_id:
            return preset
    return None


def sales_total(rows, amount_field="Net Amount"):
    total = 0.0
    for row in rows or []:
        raw = row.get(amount_field)
        try:
            total += float(str(raw).replace(",", "").strip() or 0)
        except (TypeError, ValueError):
            continue
    return round(total, 2)


def is_skip_dest(dest):
    return str(dest or "").strip().lower() in SKIP_DESTS


def validate_mapper(type_name, body):
    if type_name not in SOURCE_TYPES:
        return "Unknown type %s" % type_name
    column_map = body.get("column_map") or {}
    unique_key = list(body.get("unique_key") or [])
    if not unique_key:
        return "unique_key is required"
    targets = {}
    for src, dest in column_map.items():
        dest = str(dest or "").strip()
        src = str(src or "").strip()
        if not src or is_skip_dest(dest):
            continue
        if dest in targets and targets[dest] != src:
            return "Two columns map to %s" % dest
        targets[dest] = src
    return ""


def apply_column_map(row_dict, column_map):
    """Map uploaded headers to canonical/extra names. Identity when header already matches.

    Destinations that are empty / __skip__ / skip are omitted from the output.
    """
    column_map = column_map or {}
    out = {}
    used_src = set()
    for src, dest in column_map.items():
        if src not in row_dict:
            continue
        if is_skip_dest(dest):
            used_src.add(src)
            continue
        dest = str(dest or "").strip()
        out[dest] = row_dict[src]
        used_src.add(src)
    for src, val in row_dict.items():
        if src in used_src:
            continue
        if src not in out:
            out[src] = val
    return out
