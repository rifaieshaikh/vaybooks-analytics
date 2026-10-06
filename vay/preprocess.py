"""In-memory preprocess. Only arr / sales / receipt / items. Does not rewrite source files."""

from vay.config import DEFAULT_GROUP, DEFAULT_PARTY, DEFAULT_SALES_REP
from vay.dates import clean_text, parse_date
from vay.table import Table


def _drop_total_rows(rows, col_index):
    if col_index is None:
        return rows
    next_rows = []
    for row in rows:
        value = clean_text(row[col_index]) if col_index < len(row) else ""
        if value.lower() != "total":
            next_rows.append(row)
    return next_rows


def _fill_blank(rows, col_index, default):
    if col_index is None:
        return
    for row in rows:
        if col_index >= len(row):
            continue
        v = row[col_index]
        if v == "" or v is None:
            row[col_index] = default


def _normalize_dates(rows, col_index):
    if col_index is None:
        return
    for row in rows:
        if col_index >= len(row):
            continue
        d = parse_date(row[col_index])
        if d:
            row[col_index] = d


def _has_value(rows, col_index, value):
    if col_index is None:
        return False
    for row in rows:
        if col_index < len(row) and clean_text(row[col_index]) == value:
            return True
    return False


def preprocess(tables):
    arr = tables.get("arr")
    if arr is not None:
        name_i = arr.index.get("Account Name")
        rows = [r[:] for r in arr.rows]
        rows = _drop_total_rows(rows, name_i)
        _fill_blank(rows, arr.index.get("Balance"), 0)
        _fill_blank(rows, arr.index.get("Days"), 0)
        if not _has_value(rows, name_i, DEFAULT_PARTY):
            row = [""] * len(arr.headers)
            if name_i is not None:
                row[name_i] = DEFAULT_PARTY
            if "Balance" in arr.index:
                row[arr.index["Balance"]] = 0
            if "Days" in arr.index:
                row[arr.index["Days"]] = 0
            if "Group" in arr.index:
                row[arr.index["Group"]] = DEFAULT_GROUP
            rows.append(row)
        tables["arr"] = Table("arr", arr.headers, rows)

    group_map = {}
    arr = tables.get("arr")
    if arr is not None:
        for r in arr.rows:
            account = clean_text(arr.get(r, "Account Name"))
            if account:
                group_map[account.lower()] = clean_text(arr.get(r, "Group")) or DEFAULT_GROUP

    sales = tables.get("sales")
    if sales is not None:
        headers = list(sales.headers)
        rows = [r[:] for r in sales.rows]
        rows = _drop_total_rows(rows, sales.index.get("Party Name"))
        _fill_blank(rows, sales.index.get("Sales Rep"), DEFAULT_SALES_REP)
        _fill_blank(rows, sales.index.get("Party Name"), DEFAULT_PARTY)
        _normalize_dates(rows, sales.index.get("Date"))
        group_index = sales.index.get("Group")
        if group_index is None:
            headers.append("Group")
            group_index = len(headers) - 1
            for row in rows:
                while len(row) < len(headers):
                    row.append("")
        party_i = sales.index.get("Party Name")
        for row in rows:
            while len(row) <= group_index:
                row.append("")
            key = clean_text(row[party_i]).lower() if party_i is not None else ""
            row[group_index] = group_map.get(key, DEFAULT_GROUP)
        tables["sales"] = Table("sales", headers, rows)

    receipt = tables.get("receipt")
    if receipt is not None:
        rows = [r[:] for r in receipt.rows]
        rows = _drop_total_rows(rows, receipt.index.get("Account Name"))
        _fill_blank(rows, receipt.index.get("Sales Rep"), DEFAULT_SALES_REP)
        _normalize_dates(rows, receipt.index.get("Date"))
        tables["receipt"] = Table("receipt", receipt.headers, rows)

    credit = tables.get("credit_note")
    if credit is not None:
        from vay.credit_notes import rep_index
        from vay.row_defaults import stamp_fields

        headers = list(credit.headers)
        rows = [r[:] for r in credit.rows]
        for col in ("Sales Rep", "Group"):
            if col not in credit.index:
                headers.append(col)
        sales = tables.get("sales")
        pairs = []
        known = set(group_map)
        if sales is not None:
            for row in sales.rows:
                party = clean_text(sales.get(row, "Party Name"))
                if party:
                    known.add(party.lower())
                pairs.append((party, parse_date(sales.get(row, "Date")), sales.get(row, "Sales Rep")))
        reps = rep_index(pairs)
        stamped = []
        width = len(headers)
        index = {name: i for i, name in enumerate(headers)}
        for row in rows:
            while len(row) < width:
                row.append("")
            fields = {name: row[i] if i < len(row) else "" for name, i in index.items()}
            filled = stamp_fields(fields, "credit_note", groups=group_map, reps=reps, known=known)
            for name, i in index.items():
                if name in filled:
                    row[i] = filled[name]
            stamped.append(row)
        tables["credit_note"] = Table("credit_note", headers, stamped)

    items = tables.get("items")
    if items is not None:
        rows = [r[:] for r in items.rows]
        rows = _drop_total_rows(rows, items.index.get("Item Name"))
        _normalize_dates(rows, items.index.get("Date"))
        tables["items"] = Table("items", items.headers, rows)

    return tables
