"""As-of eligibility for official metrics.

Event metrics are valid through the report date. AR and stock snapshot metrics
are official only when the latest snapshot date equals the report date.
A missing cost makes gross margin unavailable. Unavailable is not zero.
"""

from __future__ import annotations

from vay.dates import clean_text, parse_date
from vay.domain import METRIC_IDS

AR_METRICS = (
    "ar_balance",
    "ar_overdue_30",
    "dso",
    "collection_priority_score",
)
STOCK_METRICS = (
    "stock_cover_days",
    "slow_stock_value",
)
SNAPSHOT_SOURCE = {
    "ar": "arr",
    "stock": "stock",
}


def _ymd(value):
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-":
        return text[:10]
    return ""


def latest_snapshot_date(store, source_type):
    """Latest YYYY-MM-DD for an arr or stock snapshot, or "".

    An explicit effective date wins. Rows imported without one are dated by
    the upload day, so a current outstanding file still has an as-of date.
    """
    upload_day = {}
    dates = []
    for up in store.list_uploads() or []:
        if up.get("dry_run"):
            continue
        uid = str(up.get("_id") or "")
        created = _ymd(up.get("created_at"))
        if uid and created:
            upload_day[uid] = created
        by_type = up.get("effective_dates") or {}
        eff = _ymd(by_type.get(source_type))
        if not eff and (up.get("type") or "") == source_type:
            eff = _ymd(up.get("effective_date"))
        if eff:
            dates.append(eff)
    for row in store.rows_of_type(source_type):
        fields = row.get("fields") or {}
        eff = _ymd(fields.get("EffectiveDate") or row.get("effective_date"))
        if not eff:
            eff = upload_day.get(str(row.get("source_upload_id") or "")) or ""
        if eff:
            dates.append(eff)
    if not dates:
        return ""
    return max(dates)


def _parsed_cost(raw):
    try:
        parsed = float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


def missing_item_cost(store, report_date):
    """True when an item sale on or before the report date has no stock cost."""
    cutoff = parse_date(report_date)
    costs = set()
    for row in store.rows_of_type("stock"):
        fields = row.get("fields") or {}
        name = clean_text(fields.get("Item Name"))
        if name and _parsed_cost(fields.get("P.Price")) is not None:
            costs.add(name)
    for row in store.rows_of_type("items"):
        fields = row.get("fields") or {}
        name = clean_text(fields.get("Item Name"))
        if not name:
            continue
        when = parse_date(fields.get("Date"))
        if cutoff and (not when or when > cutoff):
            continue
        if name not in costs:
            return True
    return False


def _entry(status, reason, as_of):
    return {"status": status, "reason": reason, "as_of": as_of or ""}


def _snapshot_entry(store, report_date, source_type, label):
    as_of = latest_snapshot_date(store, source_type)
    rd = str(report_date or "")[:10]
    if not as_of:
        return _entry("unavailable", "No %s snapshot date" % label, "")
    if rd and as_of != rd:
        return _entry(
            "unavailable",
            "%s snapshot is dated %s; report date is %s" % (label, as_of, rd),
            as_of,
        )
    return _entry("eligible", "", as_of or rd)


def evaluate(store, report_date):
    """{metric_id: {status, reason, as_of}} for every catalog metric."""
    rd = str(report_date or "")[:10]
    ar = _snapshot_entry(store, rd, "arr", "AR")
    stock = _snapshot_entry(store, rd, "stock", "Stock")
    if missing_item_cost(store, rd):
        margin = _entry("unavailable", "Missing item cost", rd)
    else:
        margin = _entry("eligible", "", rd)
    out = {}
    for metric_id in METRIC_IDS:
        if metric_id in AR_METRICS:
            out[metric_id] = dict(ar)
        elif metric_id in STOCK_METRICS:
            out[metric_id] = dict(stock)
        elif metric_id == "gross_margin":
            out[metric_id] = dict(margin)
        else:
            # Dated events, including item_velocity, stay eligible through the report date.
            out[metric_id] = _entry("eligible", "", rd)
    return out
