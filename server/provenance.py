"""Import-batch provenance helpers (Phase 1 gate)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from vay.dates import parse_date


EVENT_MODES = ("skip", "update", "replace_batch", "replace_period")


def normalize_event_mode(mode):
    m = (mode or "skip").strip().lower()
    return m if m in EVENT_MODES else "skip"


def file_sha256(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def mapper_version(mapper: dict | None) -> str:
    payload = {
        "column_map": (mapper or {}).get("column_map") or {},
        "unique_key": list((mapper or {}).get("unique_key") or []),
    }
    raw = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def parse_effective_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    d = parse_date(value)
    if d:
        return d.strftime("%Y-%m-%d")
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    return None


def infer_max_event_date(prepared_rows):
    """prepared_rows: list of (fields, uk)."""
    latest = None
    for fields, _uk in prepared_rows or []:
        d = parse_date((fields or {}).get("Date"))
        if d and (latest is None or d > latest):
            latest = d
    return latest.strftime("%Y-%m-%d") if latest else None
