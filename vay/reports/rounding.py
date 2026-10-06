"""Round official report numbers to 2 decimals before they are stored.

Body-row month and year totals are the sum of the rounded cells in that row.
The report total row is the sum of those rounded body cells, column by column.
"""

from vay.config import TEXT_HEADERS
from vay.dates import round2


def _is_num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def _numeric_cols(headers):
    cols = []
    for i, header in enumerate(headers or []):
        if header in TEXT_HEADERS or header in ("", None):
            continue
        cols.append(i)
    return cols


def _round_cells(row, cols):
    for i in cols:
        if i < len(row) and _is_num(row[i]):
            row[i] = round2(row[i])


def _sum_nums(values):
    return round2(sum(value for value in values if _is_num(value)))


def _fy_count(report):
    n = report.get("n_fy")
    if n:
        return n
    headers = report.get("headers") or []
    label = report.get("label_cols") or 1
    trailing = report.get("trailing") or 0
    wide = report.get("wide")
    if wide == "pair":
        return max((len(headers) - label - 2) // 26, 0)
    if wide == "month":
        return max((len(headers) - label - 1 - trailing) // 13, 0)
    return 0


def _recompute_row_totals(row, report):
    """Make wide-row subtotals equal the rounded month cells on that row."""
    wide = report.get("wide")
    n = _fy_count(report)
    if not wide or not n:
        return
    label = report.get("label_cols") or 1
    if wide == "pair":
        all_sales = 0.0
        all_coll = 0.0
        for yi in range(n):
            base = label + yi * 26
            if base + 25 >= len(row):
                return
            sales = _sum_nums(row[base + i] for i in range(0, 24, 2))
            coll = _sum_nums(row[base + i] for i in range(1, 24, 2))
            row[base + 24] = sales
            row[base + 25] = coll
            all_sales += sales
            all_coll += coll
        all_at = label + n * 26
        if all_at + 1 < len(row):
            row[all_at] = round2(all_sales)
            row[all_at + 1] = round2(all_coll)
        return
    if wide == "month":
        overall_at = label + n * 13
        if overall_at >= len(row):
            return
        overall = 0.0
        for yi in range(n):
            base = label + yi * 13
            if base + 12 >= len(row):
                return
            total = _sum_nums(row[base + i] for i in range(12))
            row[base + 12] = total
            overall += total
        row[overall_at] = round2(overall)


def _recompute_total_row(report, cols):
    total = report.get("total")
    if not total:
        return
    rows = report.get("rows") or []
    for i in cols:
        if i >= len(total) or not _is_num(total[i]):
            continue
        total[i] = _sum_nums(row[i] for row in rows if i < len(row))


def round_report(report):
    cols = _numeric_cols(report.get("headers") or [])
    for row in report.get("rows") or []:
        _round_cells(row, cols)
        _recompute_row_totals(row, report)
    _recompute_total_row(report, cols)
    return report
