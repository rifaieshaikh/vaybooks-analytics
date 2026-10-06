"""JSON-safe report snapshot for GridFS and the UI."""

from datetime import date, datetime

from server.labels import friendly_title, report_group, report_id


def json_cell(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return value
    if isinstance(value, (int, bool, str)):
        return value
    return str(value)


def serialize_report(report):
    out = {
        "id": report_id(report),
        "title": report.get("title"),
        "friendly_title": friendly_title(report),
        "group": report_group(report),
        "headers": list(report.get("headers") or []),
        "header_row1": list(report.get("header_row1") or []),
        "rows": [[json_cell(c) for c in row] for row in (report.get("rows") or [])],
        "total": [json_cell(c) for c in report["total"]] if report.get("total") else None,
        "key_col": report.get("key_col", 0),
        "status_header": report.get("status_header") or "",
        "wide": report.get("wide"),
        "label_cols": report.get("label_cols"),
        "n_fy": report.get("n_fy"),
        "trailing": report.get("trailing"),
        "followup": bool(report.get("followup")),
    }
    return out


def serialize_result(result):
    reports = [serialize_report(r) for r in (result.get("reports") or [])]
    return {
        "fy_label": result.get("fy_label") or "",
        "statuses": result.get("statuses") or [],
        "reports": reports,
    }
