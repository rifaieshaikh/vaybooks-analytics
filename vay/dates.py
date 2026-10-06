"""Date/number parsers matching Vay_Reports_Fixed.gs date_ / number_ / windows.

Noon-normalize in the org timezone (default Asia/Kolkata). Never convert via UTC.
Default 'today' uses org timezone, not the host timezone (Streamlit Cloud is UTC).
Fiscal year start month is configurable via org policy (default April = 4).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_FY_START_MONTH = 4
IST = ZoneInfo(DEFAULT_TIMEZONE)


def _zone(tz_name=None):
    name = (tz_name or DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(name)
    except Exception:
        return IST


def normalize_fy_start_month(month=None):
    try:
        m = int(month if month is not None else DEFAULT_FY_START_MONTH)
    except (TypeError, ValueError):
        return DEFAULT_FY_START_MONTH
    if m < 1 or m > 12:
        return DEFAULT_FY_START_MONTH
    return m

_DMY = re.compile(r"^(\d{1,2})[-/]([0-9]{1,2})[-/]([0-9]{2}|[0-9]{4})$")
_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")


def today_ist(tz_name=None):
    zone = _zone(tz_name)
    now = datetime.now(zone)
    return normalize_date(datetime(now.year, now.month, now.day, 12), tz_name=tz_name)


def clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def number_(value):
    if value == "" or value is None:
        return 0.0
    try:
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            if value != value:  # NaN
                return 0.0
            return float(value)
        text = str(value).replace(",", "").strip()
        if text == "":
            return 0.0
        return float(text)
    except (TypeError, ValueError):
        return 0.0


def round2(value):
    """Half-up to 2 decimal places. Non-numbers are returned unchanged."""
    if isinstance(value, bool) or value is None or value == "":
        return value
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value
    if num != num or num in (float("inf"), float("-inf")):
        return 0.0
    return float(Decimal(str(num)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def normalize_date(d, tz_name=None):
    if d is None:
        return None
    zone = _zone(tz_name)
    if isinstance(d, datetime):
        if d.tzinfo is not None:
            d = d.astimezone(zone).replace(tzinfo=None)
        return datetime(d.year, d.month, d.day, 12)
    if isinstance(d, date):
        return datetime(d.year, d.month, d.day, 12)
    return None


def parse_date(value, tz_name=None):
    """Port of date_(): dd-MM-yy, dd-MM-yyyy, yyyy-MM-dd, Excel/pandas datetimes."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return normalize_date(value, tz_name=tz_name)
    if isinstance(value, date):
        return normalize_date(value, tz_name=tz_name)
    if hasattr(value, "to_pydatetime"):
        try:
            return normalize_date(value.to_pydatetime(), tz_name=tz_name)
        except Exception:
            pass
    text = str(value).strip()
    if text.lower() in ("nan", "nat", "none"):
        return None
    m = _DMY.match(text)
    if m:
        year = int(m.group(3))
        if year < 100:
            year += 2000
        day = int(m.group(1))
        month = int(m.group(2))
        try:
            return datetime(year, month, day, 12)
        except ValueError:
            return None
    iso = _ISO.match(text)
    if iso:
        try:
            return datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)), 12)
        except ValueError:
            return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return normalize_date(parsed, tz_name=tz_name)
    except ValueError:
        return None


def between_(d, start, end):
    return d is not None and start <= d <= end


def add_days(d, days):
    return normalize_date(d + timedelta(days=days))


def add_months_clamped(d, months):
    target_month = d.month - 1 + months
    year = d.year + target_month // 12
    month = target_month % 12 + 1
    if month == 12:
        last_day = (datetime(year + 1, 1, 1, 12) - timedelta(days=1)).day
    else:
        last_day = (datetime(year, month + 1, 1, 12) - timedelta(days=1)).day
    day = min(d.day, last_day)
    return datetime(year, month, day, 12)


def fiscal_year_start(d, start_month=None):
    sm = normalize_fy_start_month(start_month)
    year = d.year if d.month >= sm else d.year - 1
    return datetime(year, sm, 1, 12)


def fiscal_month_index(calendar_month_js, start_month=None):
    sm = normalize_fy_start_month(start_month)
    return (calendar_month_js - (sm - 1)) % 12


def fiscal_month_index_dt(d, start_month=None):
    return fiscal_month_index(d.month - 1, start_month)


def fiscal_month_numbers(start_month=None):
    sm = normalize_fy_start_month(start_month)
    return [((sm - 1 + i) % 12) + 1 for i in range(12)]


def fy_label(fy_start):
    return "FY %d-%s" % (fy_start.year, str(fy_start.year + 1)[2:])


def iter_fiscal_years(min_date, report_date, start_month=None):
    """Contiguous fiscal years for start_month. No min_date → report-date FY only."""
    sm = normalize_fy_start_month(start_month)
    end = fiscal_year_start(report_date, sm)
    start = fiscal_year_start(min_date, sm) if min_date is not None else end
    years = []
    cur = start
    while cur <= end:
        years.append(cur)
        cur = datetime(cur.year + 1, sm, 1, 12)
    return years


def min_dated_source(tables, report_date):
    """min_date from sales / receipt / items / payments only. Not arr/stock."""
    found = None
    for name in ("sales", "receipt", "credit_note", "items", "payments"):
        table = tables.get(name)
        if not table or "Date" not in table.index:
            continue
        di = table.index["Date"]
        for row in table.rows:
            raw = row[di]
            d = raw if isinstance(raw, datetime) else parse_date(raw)
            if d is None or d > report_date:
                continue
            if found is None or d < found:
                found = d
    return found


def default_org_policy():
    return {
        "fiscal_year_start_month": DEFAULT_FY_START_MONTH,
        "timezone": DEFAULT_TIMEZONE,
        "currency_code": "INR",
        "currency_symbol": "₹",
        "sales_tax_inclusive_rate": 0.18,
        "ar_balance_tolerance": 0.50,
        "expense_pack": "vay_wholesale",
        "terminology": {
            "customer": "Customer",
            "party": "Party",
            "outstanding": "Outstanding",
            "sales_rep": "Sales Rep",
            "group": "Group",
            "item": "Item",
        },
        "payment_categories": None,
        "targets": {},
    }


def build_report_context(report_date, org_policy=None):
    policy = default_org_policy()
    if org_policy:
        policy.update({k: v for k, v in org_policy.items() if v is not None})
    tz_name = policy.get("timezone") or DEFAULT_TIMEZONE
    fy_month = normalize_fy_start_month(policy.get("fiscal_year_start_month"))
    d = normalize_date(report_date, tz_name=tz_name)
    month_start = datetime(d.year, d.month, 1, 12)
    if d.month == 1:
        prev_start = datetime(d.year - 1, 12, 1, 12)
    else:
        prev_start = datetime(d.year, d.month - 1, 1, 12)
    prev_end = month_start - timedelta(days=1)
    prev_end = datetime(prev_end.year, prev_end.month, prev_end.day, 12)
    try:
        tax_rate = float(policy.get("sales_tax_inclusive_rate", 0.18))
    except (TypeError, ValueError):
        tax_rate = 0.18
    from vay.settlement import normalize_customer_accounts
    customer_accounts = normalize_customer_accounts(policy.get("customer_accounts"))
    return {
        "reportDate": d,
        "timezone": tz_name,
        "fiscalYearStartMonth": fy_month,
        "currency_code": policy.get("currency_code") or "INR",
        "currency_symbol": policy.get("currency_symbol") or "₹",
        "sales_tax_inclusive_rate": tax_rate,
        "terminology": dict(policy.get("terminology") or default_org_policy()["terminology"]),
        "payment_categories": policy.get("payment_categories"),
        "expense_pack": policy.get("expense_pack") or "vay_wholesale",
        "customer_accounts": customer_accounts,
        "accounts": None,
        "inventory": None,
        "monthStart": month_start,
        "previousMonthStart": prev_start,
        "previousMonthEnd": prev_end,
        "last10Start": add_days(d, -9),
        "last15Start": add_days(d, -14),
        "last20Start": add_days(d, -19),
        "last25Start": add_days(d, -24),
        "last30Start": add_days(d, -29),
        "last45Start": add_days(d, -44),
        "last60Start": add_days(d, -59),
        "last90Start": add_days(d, -89),
        "last2MonthsStart": add_days(add_months_clamped(d, -2), 1),
        "last3MonthsStart": add_days(add_months_clamped(d, -3), 1),
        "fiscalYearStart": fiscal_year_start(d, fy_month),
        "fiscalYears": None,
        "settlement_mode": "oldest",
        "aging_bands": None,
    }


def new_period_summary():
    return {
        "mtdSales": 0.0, "mtdCollection": 0.0, "d15Sales": 0.0, "d15Collection": 0.0,
        "m2Sales": 0.0, "m2Collection": 0.0, "m3Sales": 0.0, "m3Collection": 0.0,
        "ytdSales": 0.0, "ytdCollection": 0.0,
    }


def add_period_amount(s, typ, amount, d, ctx):
    suffix = "Sales" if typ == "sales" else "Collection"
    if between_(d, ctx["monthStart"], ctx["reportDate"]):
        s["mtd" + suffix] += amount
    if between_(d, ctx["last15Start"], ctx["reportDate"]):
        s["d15" + suffix] += amount
    if between_(d, ctx["last2MonthsStart"], ctx["reportDate"]):
        s["m2" + suffix] += amount
    if between_(d, ctx["last3MonthsStart"], ctx["reportDate"]):
        s["m3" + suffix] += amount
    if between_(d, ctx["fiscalYearStart"], ctx["reportDate"]):
        s["ytd" + suffix] += amount


def total_row(rows, width, label, numeric_start):
    total = [0] * width
    total[0] = label
    for c in range(numeric_start, width):
        s = 0.0
        for row in rows:
            s += number_(row[c] if c < len(row) else 0)
        total[c] = s
    for i in range(1, numeric_start):
        total[i] = ""
    return total


def inclusive_tax(amount, rate=0.18):
    if not rate:
        return 0.0
    return amount * rate / (1 + rate)
