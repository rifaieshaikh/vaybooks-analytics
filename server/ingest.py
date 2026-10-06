"""Map a file's rows: skip Total/blank/failed, collapse snapshots, then insert/upsert."""

from vay.dates import clean_text, number_

from server.keys import RowFail, build_uk
from server.mappers import apply_column_map
from server.settings import EVENT_TYPES, SNAPSHOT_TYPES, NAME_FIELDS

# Stable reason codes for dry-run preview (Skipped tab).
REASON_TOTAL_ROW = "total_row"
REASON_BLANK_NAME = "blank_name"
REASON_FAILED_KEY = "failed_key"
REASON_DUPLICATE_IN_FILE = "duplicate_in_file"

SKIP_REASON_LABELS = {
    REASON_TOTAL_ROW: "Total row",
    REASON_BLANK_NAME: "Blank party name",
    REASON_FAILED_KEY: "Missing or invalid unique key",
    REASON_DUPLICATE_IN_FILE: "Duplicate key in this file",
    "already_exists": "Already in database (skip mode)",
    "would_replace_batch": "Would delete (replace matching keys)",
    "would_replace_period": "Would delete (replace date period)",
}


def compact_fields(fields):
    """Mapped fields only; stringify simple values for JSON-safe preview."""
    out = {}
    for key, val in (fields or {}).items():
        if val is None or val == "":
            continue
        if hasattr(val, "strftime"):
            out[key] = val.strftime("%Y-%m-%d")
        else:
            out[key] = val
    return out


def _reject(reason, fields, uk=None):
    item = {"reason": reason, "fields": compact_fields(fields)}
    if uk:
        item["uk"] = uk
    return item


def _name_cell(fields):
    for name in NAME_FIELDS:
        if name in fields:
            return clean_text(fields.get(name))
    return ""


def skip_before_collapse(fields):
    name = _name_cell(fields)
    if name.lower() == "total":
        return "total"
    if not name:
        return "blank"
    return ""


def row_from_values(headers, values):
    row = {}
    for i, h in enumerate(headers):
        key = str(h).strip()
        if not key:
            continue
        row[key] = values[i] if i < len(values) else ""
    return row


def collapse_stock(rows):
    grouped = {}
    order = []
    for fields, uk in rows:
        if uk not in grouped:
            grouped[uk] = {
                "qty": 0.0,
                "value": 0.0,
                "pricedQty": 0.0,
                "fallbackCost": None,
                "fields": dict(fields),
            }
            order.append(uk)
        qty = number_(fields.get("Qty"))
        grouped[uk]["qty"] += qty
        raw_cost = fields.get("P.Price")
        try:
            parsed = float(str(raw_cost).replace(",", "").strip()) if raw_cost not in ("", None) else None
            if parsed != parsed:
                parsed = None
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None:
            grouped[uk]["fallbackCost"] = parsed
            if qty > 0:
                grouped[uk]["value"] += qty * parsed
                grouped[uk]["pricedQty"] += qty
        grouped[uk]["fields"].update(fields)
    out = []
    for uk in order:
        data = grouped[uk]
        fields = data["fields"]
        fields["Qty"] = data["qty"]
        if data["pricedQty"] > 0:
            fields["P.Price"] = data["value"] / data["pricedQty"]
        elif data["fallbackCost"] is not None:
            fields["P.Price"] = data["fallbackCost"]
        out.append((fields, uk))
    return out


def collapse_arr(rows):
    last = {}
    order = []
    for fields, uk in rows:
        if uk not in last:
            order.append(uk)
        last[uk] = fields
    return [(last[uk], uk) for uk in order]


def prepare_rows(type_name, headers, value_rows, mapper, aliases=None):
    """Return (prepared, counts, rejects) before Mongo write.

    rejects: list of {reason, fields, uk?} for dry-run Skipped preview.
    """
    column_map = mapper.get("column_map") or {}
    unique_key = mapper.get("unique_key") or []
    extra_types = mapper.get("extra_types") or {}
    counts = {
        "added": 0,
        "skipped": 0,
        "clash": 0,
        "failed_row": 0,
        "upserted": 0,
        "updated": 0,
        "total_skipped": 0,
        "blank_skipped": 0,
    }
    prepared = []
    rejects = []
    seen_uk = {}
    event_clashes = []

    for values in value_rows:
        raw = row_from_values(headers, values)
        fields = apply_column_map(raw, column_map)
        if aliases:
            from server.account_aliases import apply_alias_fields
            fields = apply_alias_fields(fields, aliases)
        reason = skip_before_collapse(fields)
        if reason == "total":
            counts["total_skipped"] += 1
            rejects.append(_reject(REASON_TOTAL_ROW, fields))
            continue
        if reason == "blank":
            counts["blank_skipped"] += 1
            rejects.append(_reject(REASON_BLANK_NAME, fields))
            continue
        try:
            uk = build_uk(fields, unique_key, extra_types)
        except RowFail:
            counts["failed_row"] += 1
            rejects.append(_reject(REASON_FAILED_KEY, fields))
            continue
        if type_name in EVENT_TYPES:
            if uk in seen_uk:
                counts["clash"] += 1
                event_clashes.append(uk)
                rejects.append(_reject(REASON_DUPLICATE_IN_FILE, fields, uk=uk))
                continue
            seen_uk[uk] = fields
            prepared.append((fields, uk))
        else:
            if uk not in seen_uk:
                seen_uk[uk] = []
            seen_uk[uk].append(fields)

    if type_name in SNAPSHOT_TYPES:
        pairs = []
        for uk, group in seen_uk.items():
            pairs.extend((f, uk) for f in group)
        if type_name == "stock":
            prepared = collapse_stock(pairs)
        else:
            prepared = collapse_arr(pairs)

    return prepared, counts, rejects
