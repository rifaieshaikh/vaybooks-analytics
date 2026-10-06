"""Load uploaded Excel/CSV. pandas is OK here; not for report aggregations."""

from __future__ import annotations

import io

import pandas as pd

from vay.config import REQUIRED_COLUMNS, SOURCE_SHEETS
from vay.dates import clean_text, parse_date
from vay.table import MissingColumnsError, Table


def _normalize_sheet_name(name):
    return clean_text(name).lower()


def _read_frame(uploaded, filename=""):
    name = (getattr(uploaded, "name", None) or filename or "").lower()
    data = uploaded.read() if hasattr(uploaded, "read") else uploaded
    if hasattr(uploaded, "seek"):
        try:
            uploaded.seek(0)
        except Exception:
            pass
    raw = data if isinstance(data, (bytes, bytearray)) else data
    buf = io.BytesIO(raw if isinstance(raw, (bytes, bytearray)) else str(raw).encode("utf-8"))
    if name.endswith(".csv"):
        return {"data": pd.read_csv(buf, dtype=object, keep_default_na=False)}
    xl = pd.ExcelFile(buf)
    frames = {}
    for sheet in xl.sheet_names:
        frames[_normalize_sheet_name(sheet)] = pd.read_excel(
            xl, sheet_name=sheet, dtype=object, keep_default_na=False
        )
    return frames


def _frame_to_table(name, frame, required):
    if frame is None or frame.empty:
        headers = list(frame.columns) if frame is not None else []
        headers = [clean_text(h) for h in headers]
        return Table(name, headers, [])
    headers = [clean_text(h) for h in list(frame.columns)]
    index = {}
    for i, h in enumerate(headers):
        if h and h not in index:
            index[h] = i
    missing = [h for h in required if h not in index]
    if missing:
        raise MissingColumnsError(name, missing)
    rows = []
    for values in frame.itertuples(index=False, name=None):
        row = list(values)
        while len(row) < len(headers):
            row.append("")
        if "Date" in index:
            parsed = parse_date(row[index["Date"]])
            if parsed:
                row[index["Date"]] = parsed
        rows.append(row)
    return Table(name, headers, rows)


def load_sources(files_by_sheet=None, combined_file=None):
    """files_by_sheet: {sheet_name: uploaded file}. combined_file: workbook with those tabs."""
    frames = {}
    if combined_file is not None:
        loaded = _read_frame(combined_file, getattr(combined_file, "name", "upload.xlsx"))
        if "data" in loaded and len(loaded) == 1:
            frames["data"] = loaded["data"]
        else:
            frames.update(loaded)
    files_by_sheet = files_by_sheet or {}
    for sheet, uploaded in files_by_sheet.items():
        if uploaded is None:
            continue
        key = _normalize_sheet_name(sheet)
        loaded = _read_frame(uploaded, getattr(uploaded, "name", key + ".xlsx"))
        if key + ".csv" in (getattr(uploaded, "name", "") or "").lower() or (
            len(loaded) == 1 and "data" in loaded
        ):
            frames[key] = loaded.get("data") or list(loaded.values())[0]
        else:
            if key in loaded:
                frames[key] = loaded[key]
            elif len(loaded) == 1:
                frames[key] = list(loaded.values())[0]
            else:
                frames.update(loaded)

    tables = {}
    errors = {}
    for name in SOURCE_SHEETS:
        key = _normalize_sheet_name(name)
        frame = frames.get(key)
        if frame is None:
            continue
        try:
            tables[name] = _frame_to_table(name, frame, REQUIRED_COLUMNS[name])
        except MissingColumnsError as exc:
            errors[name] = str(exc)
    return tables, errors
