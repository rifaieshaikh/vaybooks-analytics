"""Stock item 360 and holding. Does not feed generate()."""

from __future__ import annotations

from datetime import timedelta

from vay.dates import clean_text, number_, parse_date

from server.customers import (
    _as_of,
    _fmt_day,
    _in_period,
    _iso,
    _period_bounds,
    account_uk,
)
from server.invoices import _group_map, _invoice_no, invoice_id_for_sale, money2
from server.settings import ROW_PAGE_CAP, ROW_PAGE_DEFAULT

HOLD_TYPE = "item_hold"
DEFAULT_UK = "__default__"
PACE_DAYS = 90
PACE_FALLBACK_DAYS = 365
MAX_DAYS_HOLD_DEFAULT = 60
TREND_PCT = 0.20
OVER_FILL_RATIO = 1.25
OVER_COVER_RATIO = 1.5
TIGHT_COVER_RATIO = 0.75

_STATUS_LABELS = {
    "low": "Below min",
    "soon": "Buy this week",
    "watch": "Plan to buy",
    "excess": "More than needed",
    "ok": "On track",
    "idle": "No recent sales",
    "stopped": "Discontinued",
}

_POSITION_LABELS = {
    "under": "Understocked",
    "tight": "Running tight",
    "balanced": "Balanced",
    "over": "Overstocked",
    "dead": "Dead stock",
    "stopped": "Discontinued",
}

_TREND_LABELS = {
    "up": "Demand up",
    "down": "Demand down",
    "flat": "Steady",
}

_VELOCITY_WINDOWS = (
    ("d7", 7, "7 days"),
    ("d30", 30, "30 days"),
    ("d90", 90, "90 days"),
    ("d365", 365, "365 days"),
)


def _page_limit(params):
    try:
        page = max(1, int(params.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    try:
        limit = min(ROW_PAGE_CAP, max(1, int(params.get("limit") or ROW_PAGE_DEFAULT)))
    except (TypeError, ValueError):
        limit = ROW_PAGE_DEFAULT
    return page, limit


def _num(value):
    if value in ("", None):
        return None
    try:
        return money2(number_(value))
    except (TypeError, ValueError):
        return None


_PARTY_HEADERS = {
    "party name",
    "party",
    "account name",
    "customer",
    "customer name",
    "buyer",
    "buyer name",
}


def _header_key(name):
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum() or ch.isspace()).strip()


def _party_from_fields(fields):
    for src, val in (fields or {}).items():
        if val in ("", None):
            continue
        if _header_key(src) in _PARTY_HEADERS:
            return clean_text(val)
    return clean_text((fields or {}).get("Party Name") or (fields or {}).get("Account Name"))


def _qty_of(fields):
    q = _num((fields or {}).get("Qty"))
    return money2(q or 0)


def _rate_of(fields):
    return _num((fields or {}).get("P.Price") or (fields or {}).get("Rate"))


def _line_amount(fields, qty, rate):
    amount = _num((fields or {}).get("Amount"))
    if amount is not None:
        return amount
    return money2((qty or 0) * (rate or 0))


def _is_yes(value):
    return clean_text(value).lower() in ("1", "true", "yes", "y")


def _hold_map(store):
    out = {}
    default_min = 0.0
    default_max_days = MAX_DAYS_HOLD_DEFAULT
    for row in store.rows_of_type(HOLD_TYPE):
        uk = account_uk(row.get("uk"))
        fields = row.get("fields") or {}
        min_hold = _num(fields.get("Min Hold"))
        fill_to = _num(fields.get("Fill To"))
        lead = _num(fields.get("Lead Days"))
        max_days = _num(fields.get("Max Days Hold"))
        if uk == DEFAULT_UK:
            default_min = money2(min_hold or 0)
            if max_days is not None:
                default_max_days = max(1, int(max_days))
            continue
        out[uk.lower()] = {
            "min_hold": money2(min_hold) if min_hold is not None else None,
            "fill_to": fill_to,
            "lead_days": int(lead) if lead is not None else None,
            "max_days_hold": int(max_days) if max_days is not None else None,
            "discontinued": _is_yes(fields.get("Discontinued")),
        }
    return out, default_min, default_max_days


def _holding_for(holds, default_min, uk, default_max_days=None):
    raw = holds.get((uk or "").lower()) or {}
    min_hold = raw.get("min_hold")
    if min_hold is None:
        min_hold = default_min
    raw_max = raw.get("max_days_hold")
    own_max_days = raw_max is not None
    if raw_max is None:
        raw_max = default_max_days if default_max_days is not None else MAX_DAYS_HOLD_DEFAULT
    try:
        max_days_hold = max(1, int(raw_max))
    except (TypeError, ValueError):
        max_days_hold = MAX_DAYS_HOLD_DEFAULT
    return {
        "min_hold": money2(min_hold or 0),
        "fill_to": raw.get("fill_to"),
        "lead_days": int(raw.get("lead_days") or 0),
        "max_days_hold": max_days_hold,
        "own_min": raw.get("min_hold") is not None,
        "own_fill": raw.get("fill_to") is not None,
        "own_lead": raw.get("lead_days") is not None,
        "own_max_days": own_max_days,
        "uses_default_max_days": not own_max_days,
        "discontinued": bool(raw.get("discontinued")),
    }


def _invalidate_book(store):
    if hasattr(store, "_360_book"):
        store._360_book = None


def save_holding(
    store,
    uk,
    min_hold=None,
    fill_to=None,
    lead_days=None,
    max_days_hold=None,
    discontinued=None,
    clear_fill=False,
    clear_max_days=False,
):
    uk = account_uk(uk)
    if not uk or uk == DEFAULT_UK:
        return None
    existing = store.find_row(HOLD_TYPE, uk) or {}
    fields = dict(existing.get("fields") or {})
    fields["Item Name"] = uk
    if min_hold is not None:
        fields["Min Hold"] = money2(min_hold)
    if fill_to is not None:
        fields["Fill To"] = money2(fill_to)
    elif clear_fill:
        fields.pop("Fill To", None)
    if lead_days is not None:
        fields["Lead Days"] = int(lead_days)
    if max_days_hold is not None:
        fields["Max Days Hold"] = max(1, int(max_days_hold))
    elif clear_max_days:
        fields.pop("Max Days Hold", None)
    if discontinued is not None:
        fields["Discontinued"] = "Yes" if discontinued else "No"
    store.upsert_row({
        "type": HOLD_TYPE,
        "uk": uk,
        "fields": fields,
        "source_upload_id": existing.get("source_upload_id") or "",
    })
    _invalidate_book(store)
    return store.find_row(HOLD_TYPE, uk)


def save_default_min(store, min_hold):
    return save_default_holding(store, min_hold=min_hold)


def save_default_holding(store, min_hold=None, max_days_hold=None):
    existing = store.find_row(HOLD_TYPE, DEFAULT_UK) or {}
    fields = dict(existing.get("fields") or {})
    if min_hold is not None:
        fields["Min Hold"] = money2(min_hold or 0)
    if max_days_hold is not None:
        fields["Max Days Hold"] = max(1, int(max_days_hold))
    store.upsert_row({
        "type": HOLD_TYPE,
        "uk": DEFAULT_UK,
        "fields": fields,
        "source_upload_id": "",
    })
    _invalidate_book(store)
    return {
        "min_hold": money2(fields.get("Min Hold") or 0),
        "max_days_hold": int(fields["Max Days Hold"]) if fields.get("Max Days Hold") not in ("", None) else MAX_DAYS_HOLD_DEFAULT,
    }


def _resolved_group(fields, party, groups):
    """Prefer a real group on the row, then the party/ARR/customer map. NO_GROUP is unknown."""
    from vay.row_defaults import real_group

    direct = real_group((fields or {}).get("Group"))
    if direct:
        return direct
    if party:
        mapped = real_group((groups or {}).get(party.lower()))
        if mapped:
            return mapped
    return ""


def _item_lines_from_rows(item_rows, sales_rows, groups, start_month=None):
    from server.invoices import invoice_scope_key

    by_uk = {}
    for row in item_rows or []:
        fields = row.get("fields") or {}
        name = clean_text(fields.get("Item Name"))
        uk = account_uk(name)
        if not uk:
            continue
        d = parse_date(fields.get("Date"))
        qty = _qty_of(fields)
        rate = _num(fields.get("Rate"))
        party = _party_from_fields(fields)
        line = {
            "date": d,
            "name": name,
            "uk": uk,
            "qty": qty,
            "rate": rate,
            "amount": _line_amount(fields, qty, rate),
            "party": party,
            "group": _resolved_group(fields, party, groups),
            "rep": clean_text(fields.get("Sales Rep")),
            "invoice": _invoice_no(fields),
            "invoice_id": "",
        }
        by_uk.setdefault(uk.lower(), []).append(line)
    sales_by_no = {}
    for row in sales_rows or []:
        fields = row.get("fields") or {}
        inv = _invoice_no(fields)
        if not inv:
            continue
        party = _party_from_fields(fields) or clean_text(fields.get("Party Name") or fields.get("Account Name"))
        sales_by_no.setdefault(invoice_scope_key(inv, fields.get("Date"), start_month), {
            "invoice_id": invoice_id_for_sale(fields, row.get("uk"), start_month=start_month),
            "party": party,
            "group": _resolved_group(fields, party, groups),
            "rep": clean_text(fields.get("Sales Rep")),
        })
    for lines in by_uk.values():
        for line in lines:
            sale = (
                sales_by_no.get(invoice_scope_key(line["invoice"], line.get("date"), start_month))
                if line["invoice"] else None
            )
            if sale:
                line["invoice_id"] = sale.get("invoice_id") or ""
                if not line["party"] and sale.get("party"):
                    line["party"] = sale["party"]
                if not line["group"] and sale.get("group"):
                    line["group"] = sale["group"]
                if not line["rep"] and sale.get("rep"):
                    line["rep"] = sale["rep"]
            if not line["group"] and line["party"]:
                line["group"] = groups.get(line["party"].lower()) or ""
        lines.sort(key=lambda x: x["date"] or parse_date("1900-01-01"), reverse=True)
    return by_uk


def _qty_in(lines, start, end, as_of):
    qty = 0.0
    amount = 0.0
    times = 0
    for line in lines:
        d = line.get("date")
        if not _in_period(d, start, end if end else as_of):
            continue
        if d and d > as_of:
            continue
        qty = money2(qty + (line.get("qty") or 0))
        amount = money2(amount + (line.get("amount") or 0))
        times += 1
    return qty, amount, times


def _inclusive_window_start(as_of, days):
    """Start of an inclusive N-day window ending on as_of (N calendar days)."""
    n = max(1, int(days or 1))
    return as_of - timedelta(days=n - 1)


def _active_divisor(lines, start, end, as_of, cap_days=None):
    """Average over days from first sale in the window to as_of, capped at cap_days.

    Avoids diluting velocity when an item only started selling partway through the window.
    """
    end = end or as_of
    first = None
    for line in lines:
        d = line.get("date")
        if not d or d > as_of:
            continue
        if not _in_period(d, start, end):
            continue
        if first is None or d < first:
            first = d
    if first is None:
        return max(1, int(cap_days or 1))
    span = max(1, (min(end, as_of) - first).days + 1)
    if cap_days is None:
        return span
    return max(1, min(int(cap_days), span))


def _pace(lines, as_of):
    start_90 = _inclusive_window_start(as_of, PACE_DAYS)
    qty90, _, _ = _qty_in(lines, start_90, as_of, as_of)
    if qty90 > 0:
        div = _active_divisor(lines, start_90, as_of, as_of, PACE_DAYS)
        return money2(qty90 / div), div, qty90
    start_365 = _inclusive_window_start(as_of, PACE_FALLBACK_DAYS)
    qty365, _, _ = _qty_in(lines, start_365, as_of, as_of)
    if qty365 > 0:
        div = _active_divisor(lines, start_365, as_of, as_of, PACE_FALLBACK_DAYS)
        return money2(qty365 / div), div, qty365
    return 0.0, 0, 0.0


def _window_bucket(lines, as_of, key, days, label, on_hand):
    start = _inclusive_window_start(as_of, days)
    qty, amount, times = _qty_in(lines, start, as_of, as_of)
    divisor = _active_divisor(lines, start, as_of, as_of, days) if qty > 0 else days
    per_day = money2(qty / divisor) if qty > 0 and divisor > 0 else 0.0
    cover = int(round(on_hand / per_day)) if per_day > 0 else None
    return {
        "id": key,
        "label": label,
        "window_days": days,
        "days": divisor,
        "qty": qty,
        "amount": amount,
        "times": times,
        "per_day": per_day,
        "days_cover": cover,
    }


def _calendar_bucket(lines, as_of, key, start, end, label, on_hand):
    end = end or as_of
    qty, amount, times = _qty_in(lines, start, end, as_of)
    if start:
        span = max(1, (min(end, as_of) - start).days + 1)
    else:
        span = max(1, times or 1)
    divisor = _active_divisor(lines, start, end, as_of, span) if qty > 0 else span
    per_day = money2(qty / divisor) if qty > 0 and divisor > 0 else 0.0
    cover = int(round(on_hand / per_day)) if per_day > 0 else None
    return {
        "id": key,
        "label": label,
        "window_days": span,
        "days": divisor,
        "qty": qty,
        "amount": amount,
        "times": times,
        "per_day": per_day,
        "days_cover": cover,
    }


def _trend_from_pace(pace_30, pace_90):
    if pace_90 <= 0 and pace_30 <= 0:
        return "flat", 0.0
    if pace_90 <= 0 and pace_30 > 0:
        return "up", 1.0
    if pace_30 <= 0 and pace_90 > 0:
        return "down", -1.0
    pct = (pace_30 - pace_90) / pace_90
    if pct >= TREND_PCT:
        return "up", money2(pct)
    if pct <= -TREND_PCT:
        return "down", money2(pct)
    return "flat", money2(pct)


def _velocity(lines, as_of, on_hand):
    buckets = {}
    for key, days, label in _VELOCITY_WINDOWS:
        buckets[key] = _window_bucket(lines, as_of, key, days, label, on_hand)
    bounds = _period_bounds(as_of)
    for key in ("this_month", "last_month"):
        start, end, label = bounds[key]
        buckets[key] = _calendar_bucket(lines, as_of, key, start, end, label, on_hand)
    pace_30 = buckets["d30"]["per_day"]
    pace_90 = buckets["d90"]["per_day"]
    trend, trend_pct = _trend_from_pace(pace_30, pace_90)
    return {
        "buckets": buckets,
        "pace_7": buckets["d7"]["per_day"],
        "pace_30": pace_30,
        "pace_90": pace_90,
        "pace_365": buckets["d365"]["per_day"],
        "trend": trend,
        "trend_pct": trend_pct,
        "trend_label": _TREND_LABELS.get(trend, "Steady"),
    }


def _effective_fill(holding, on_hand, pace):
    if holding.get("fill_to") is not None:
        return money2(holding["fill_to"])
    min_hold = money2(holding.get("min_hold") or 0)
    days = int(holding.get("max_days_hold") or MAX_DAYS_HOLD_DEFAULT)
    extra = money2(pace * days) if pace else 0.0
    return money2(max(min_hold, money2(min_hold + extra)))


def _target_cover_days(holding, fill_to, pace):
    if pace <= 0:
        return None
    if holding.get("own_fill") and fill_to:
        return int(round(fill_to / pace))
    return int(holding.get("max_days_hold") or MAX_DAYS_HOLD_DEFAULT)


def _status(on_hand, min_hold, fill_to, pace, days_until_min, lead_days, holding):
    if holding.get("discontinued"):
        return "stopped"
    if pace <= 0:
        if on_hand + 1e-9 < min_hold:
            return "low"
        return "idle"
    if on_hand + 1e-9 < min_hold:
        return "low"
    until = days_until_min
    if until is not None and until - lead_days <= 7:
        return "soon"
    if until is not None and until - lead_days <= 21:
        return "watch"
    has_target = holding.get("own_fill") or min_hold > 0 or bool(fill_to)
    if has_target and fill_to and on_hand > money2(fill_to * OVER_FILL_RATIO) and on_hand > min_hold:
        return "excess"
    return "ok"


def _stock_position(on_hand, min_hold, fill_to, pace, days_cover, lead_days, holding):
    if holding.get("discontinued"):
        return "stopped", None, None, None
    if pace <= 0:
        if on_hand + 1e-9 > 0:
            return "dead", None, None, money2(on_hand) if on_hand else None
        if on_hand + 1e-9 < min_hold:
            return "under", None, money2(max(0.0, min_hold - on_hand)), None
        return "balanced", None, None, None
    target_days = _target_cover_days(holding, fill_to, pace)
    target_qty = money2(fill_to or 0)
    cover_gap = (days_cover - target_days) if days_cover is not None and target_days is not None else None
    under_qty = money2(max(0.0, min_hold - on_hand))
    over_qty = money2(max(0.0, on_hand - target_qty)) if target_qty else None
    if on_hand + 1e-9 < min_hold:
        return "under", cover_gap, under_qty, over_qty
    if days_cover is not None and days_cover < max(lead_days + 7, 1):
        return "under", cover_gap, under_qty or money2(max(0.0, target_qty - on_hand)), over_qty
    if target_qty and on_hand > money2(target_qty * OVER_FILL_RATIO) and on_hand > min_hold:
        return "over", cover_gap, under_qty, over_qty
    if days_cover is not None and target_days and days_cover > int(round(target_days * OVER_COVER_RATIO)):
        return "over", cover_gap, under_qty, over_qty
    if days_cover is not None and target_days and days_cover < int(round(target_days * TIGHT_COVER_RATIO)):
        return "tight", cover_gap, under_qty, over_qty
    return "balanced", cover_gap, under_qty, over_qty


def _qty_label(n):
    try:
        value = float(n or 0)
    except (TypeError, ValueError):
        return "0"
    if abs(value - round(value)) < 0.001:
        return str(int(round(value)))
    return "{:.2f}".format(value)


def _pace_label(n):
    return "%s/day" % _qty_label(n)


def _headline(card):
    name = card["name"]
    on_hand = card["qty"]
    min_hold = card["min_hold"]
    buy_qty = card["buy_qty"]
    buy_label = card.get("buy_by_label") or ""
    days = card.get("days_cover")
    status = card["status"]
    position = card.get("stock_position")
    if status == "stopped":
        return "%s is discontinued. Do not buy more." % name
    if status == "low":
        if buy_qty:
            return "On hand is %s, below the min of %s. Buy %s now." % (
                _qty_label(on_hand), _qty_label(min_hold), _qty_label(buy_qty),
            )
        return "On hand is %s, below the min of %s." % (_qty_label(on_hand), _qty_label(min_hold))
    if status == "soon" and buy_qty:
        when = "by " + buy_label if buy_label else "this week"
        return "Buy %s %s so %s stays above the min of %s." % (
            _qty_label(buy_qty), when, name, _qty_label(min_hold),
        )
    if status == "watch" and buy_qty and buy_label:
        return "Plan to buy %s by %s. About %s days of cover left." % (
            _qty_label(buy_qty), buy_label, days if days is not None else "—",
        )
    if position == "over" or status == "excess":
        over = card.get("over_qty")
        if over:
            return "Overstocked: on hand %s is about %s above the fill target of %s." % (
                _qty_label(on_hand), _qty_label(over), _qty_label(card.get("fill_to")),
            )
        return "On hand %s is more than needed (min %s). Hold off on buying." % (
            _qty_label(on_hand), _qty_label(min_hold),
        )
    if position == "dead" or status == "idle":
        age = card.get("last_sale_age_days")
        if on_hand:
            if age is not None:
                return "No sales in %s days. Holding %s." % (age, _qty_label(on_hand))
            return "No recent sales. Holding %s with a min of %s." % (_qty_label(on_hand), _qty_label(min_hold))
        return "No stock and no recent sales for %s." % name
    if days is not None:
        return "On hand %s. At this pace you have about %s days. No need to buy yet." % (
            _qty_label(on_hand), days,
        )
    return "On hand %s. Min holding is %s." % (_qty_label(on_hand), _qty_label(min_hold))


def _velocity_bit(card):
    pace_30 = card.get("pace_30")
    pace_90 = card.get("pace_90")
    trend = card.get("trend") or "flat"
    trend_pct = card.get("trend_pct") or 0
    if not pace_30 and not pace_90:
        return "No sell-through in the last 90 days."
    parts = []
    if pace_30:
        parts.append("Selling %s (30d)" % _pace_label(pace_30))
    elif pace_90:
        parts.append("Selling %s (90d)" % _pace_label(pace_90))
    if trend == "up" and pace_90:
        parts.append("up %s%% vs 90d" % _qty_label(abs(trend_pct) * 100))
    elif trend == "down" and pace_90:
        parts.append("down %s%% vs 90d" % _qty_label(abs(trend_pct) * 100))
    elif pace_30 and pace_90:
        parts.append("steady vs 90d")
    return ". ".join(parts) + "."


def _cover_bit(card):
    days = card.get("days_cover")
    target = card.get("target_days")
    position = card.get("stock_position")
    if days is None:
        if position == "dead":
            return "No velocity to size cover against."
        return ""
    if target:
        gap = card.get("cover_gap_days")
        if gap is not None and gap > 0:
            return "%s days on hand vs %s-day target — over by about %s days." % (days, target, gap)
        if gap is not None and gap < 0:
            return "%s days on hand vs %s-day target — short by about %s days." % (days, target, abs(gap))
        return "%s days on hand, near the %s-day target." % (days, target)
    return "About %s days of cover at the current pace." % days


def _risk_bit(card):
    if card.get("discontinued") or card.get("status") == "stopped":
        return ""
    until = card.get("days_until_min")
    lead = int(card.get("lead_days") or 0)
    pace_30 = card.get("pace_30") or 0
    pace = card.get("pace") or 0
    if until is not None and pace > 0:
        if until - lead <= 0:
            return "At this pace stock is already inside lead time to the min."
        if until - lead <= 7:
            return "If pace holds, hits min in about %s days (lead %s)." % (until, lead)
    if pace_30 and pace and pace_30 > pace * (1 + TREND_PCT) and until is not None:
        faster = int(round((float(card.get("qty") or 0) - float(card.get("min_hold") or 0)) / pace_30)) if pace_30 else None
        if faster is not None and faster < until:
            return "30d pace is faster; could hit min in about %s days." % max(0, faster)
    return ""


def _concentration_bit(buyers):
    if not buyers:
        return ""
    total = sum(float(b.get("qty") or 0) for b in buyers)
    if total <= 0:
        return ""
    top = buyers[0]
    share = money2((float(top.get("qty") or 0) / total) * 100)
    if share < 35:
        return ""
    return "Top buyer %s is %s%% of qty." % (top.get("name") or "—", _qty_label(share))


def _next_move(card):
    if card.get("discontinued") or card["status"] == "stopped":
        return "Do not buy. This item is discontinued."
    if card.get("stock_position") == "dead":
        return "Review whether to keep, discount, or write off this stock."
    if card.get("stock_position") == "over" or card["status"] == "excess":
        return "Do not buy more yet."
    if card["status"] == "low" and card["buy_qty"]:
        return "Buy %s now." % _qty_label(card["buy_qty"])
    if card["buy_qty"] and card.get("buy_by_label"):
        return "Buy %s by %s." % (_qty_label(card["buy_qty"]), card["buy_by_label"])
    if card["status"] == "idle":
        return "Set a min if you want a reminder when stock runs low."
    return "No purchase needed right now."


def _build_insight(card, buyers=None):
    next_move = _next_move(card)
    velocity_bit = _velocity_bit(card)
    cover_bit = _cover_bit(card)
    risk_bit = _risk_bit(card)
    concentration_bit = _concentration_bit(buyers or [])
    action = next_move
    if card.get("trend") == "up" and card.get("stock_position") in ("under", "tight") and card.get("buy_qty"):
        action = "Demand is up — buy %s sooner." % _qty_label(card["buy_qty"])
    elif card.get("trend") == "down" and card.get("stock_position") == "over":
        action = "Demand is slowing — hold off and work down excess."
    return {
        "headline": card.get("headline") or _headline(card),
        "health_label": card.get("status_label") or _STATUS_LABELS.get(card.get("status"), "On track"),
        "stock_label": card.get("stock_position_label") or _POSITION_LABELS.get(card.get("stock_position"), ""),
        "next_move": next_move,
        "velocity_bit": velocity_bit,
        "cover_bit": cover_bit,
        "risk_bit": risk_bit,
        "concentration_bit": concentration_bit,
        "action": action,
        "trend_label": card.get("trend_label") or _TREND_LABELS.get(card.get("trend"), "Steady"),
    }


def _apply_buy_fields(card, holding, as_of=None):
    """Recompute buy/status/position fields after holding changes (e.g. snapshot overlay)."""
    on_hand = float(card.get("qty") or 0)
    pace = float(card.get("pace") or 0)
    min_hold = money2(holding.get("min_hold") or 0)
    lead_days = int(holding.get("lead_days") or 0)
    fill_to = _effective_fill(holding, on_hand, pace)
    days_cover = int(round(on_hand / pace)) if pace > 0 else None
    days_until_min = int(round((on_hand - min_hold) / pace)) if pace > 0 else None
    buy_qty = money2(max(0.0, fill_to - on_hand))
    if on_hand + 1e-9 >= fill_to and on_hand + 1e-9 >= min_hold:
        buy_qty = 0.0
    if holding.get("discontinued"):
        buy_qty = 0.0
    buy_by = None
    if buy_qty > 0 and as_of is not None:
        if pace > 0 and days_until_min is not None:
            buy_in = days_until_min - lead_days
            buy_by = as_of + timedelta(days=max(0, buy_in))
        elif on_hand + 1e-9 < min_hold:
            buy_by = as_of
    status = _status(on_hand, min_hold, fill_to, pace, days_until_min, lead_days, holding)
    position, cover_gap, under_qty, over_qty = _stock_position(
        on_hand, min_hold, fill_to, pace, days_cover, lead_days, holding,
    )
    target_days = _target_cover_days(holding, fill_to, pace)
    card["min_hold"] = min_hold
    card["fill_to"] = fill_to
    card["lead_days"] = lead_days
    card["max_days_hold"] = int(holding.get("max_days_hold") or MAX_DAYS_HOLD_DEFAULT)
    card["own_min"] = holding.get("own_min") or False
    card["own_fill"] = holding.get("own_fill") or False
    card["own_lead"] = holding.get("own_lead") or False
    card["own_max_days"] = holding.get("own_max_days") or False
    card["uses_default_max_days"] = not holding.get("own_max_days")
    card["discontinued"] = bool(holding.get("discontinued"))
    card["days_cover"] = days_cover
    card["days_until_min"] = days_until_min
    card["buy_qty"] = buy_qty
    if buy_by is not None:
        card["buy_by"] = _iso(buy_by)
        card["buy_by_label"] = _fmt_day(buy_by)
    if buy_qty <= 0:
        card["buy_by"] = None
        card["buy_by_label"] = ""
    card["status"] = status
    card["status_label"] = _STATUS_LABELS.get(status, "On track")
    card["stock_position"] = position
    card["stock_position_label"] = _POSITION_LABELS.get(position, "")
    card["target_days"] = target_days
    card["cover_gap_days"] = cover_gap
    card["under_qty"] = under_qty
    card["over_qty"] = over_qty
    card["headline"] = _headline(card)
    return card


def _card(name, stock_fields, lines, holding, as_of):
    uk = account_uk(name)
    on_hand = _qty_of(stock_fields) if stock_fields else 0.0
    rate = _rate_of(stock_fields) if stock_fields else None
    value = money2(on_hand * (rate or 0)) if rate is not None else None
    last = None
    for line in lines:
        if line.get("date") and (last is None or line["date"] > last):
            last = line["date"]
    pace, pace_days, pace_qty = _pace(lines, as_of)
    velocity = _velocity(lines, as_of, on_hand)
    min_hold = money2(holding.get("min_hold") or 0)
    lead_days = int(holding.get("lead_days") or 0)
    max_days_hold = int(holding.get("max_days_hold") or MAX_DAYS_HOLD_DEFAULT)
    fill_to = _effective_fill(holding, on_hand, pace)
    days_cover = int(round(on_hand / pace)) if pace > 0 else None
    days_until_min = int(round((on_hand - min_hold) / pace)) if pace > 0 else None
    last_sale_age = (as_of - last).days if last else None
    buy_qty = money2(max(0.0, fill_to - on_hand))
    if on_hand + 1e-9 >= fill_to and on_hand + 1e-9 >= min_hold:
        buy_qty = 0.0
    if holding.get("discontinued"):
        buy_qty = 0.0
    buy_by = None
    if buy_qty > 0:
        if pace > 0 and days_until_min is not None:
            buy_in = days_until_min - lead_days
            buy_by = as_of + timedelta(days=max(0, buy_in))
        elif on_hand + 1e-9 < min_hold:
            buy_by = as_of
    status = _status(on_hand, min_hold, fill_to, pace, days_until_min, lead_days, holding)
    position, cover_gap, under_qty, over_qty = _stock_position(
        on_hand, min_hold, fill_to, pace, days_cover, lead_days, holding,
    )
    target_days = _target_cover_days(holding, fill_to, pace)
    card = {
        "uk": uk,
        "name": name or uk,
        "qty": on_hand,
        "rate": rate,
        "value": value,
        "min_hold": min_hold,
        "fill_to": fill_to,
        "lead_days": lead_days,
        "max_days_hold": max_days_hold,
        "own_min": holding.get("own_min") or False,
        "own_fill": holding.get("own_fill") or False,
        "own_lead": holding.get("own_lead") or False,
        "own_max_days": holding.get("own_max_days") or False,
        "uses_default_max_days": not holding.get("own_max_days"),
        "pace": pace,
        "pace_days": pace_days,
        "pace_qty": pace_qty,
        "pace_7": velocity["pace_7"],
        "pace_30": velocity["pace_30"],
        "pace_90": velocity["pace_90"],
        "pace_365": velocity["pace_365"],
        "trend": velocity["trend"],
        "trend_pct": velocity["trend_pct"],
        "trend_label": velocity["trend_label"],
        "velocity": velocity,
        "days_cover": days_cover,
        "days_until_min": days_until_min,
        "target_days": target_days,
        "cover_gap_days": cover_gap,
        "under_qty": under_qty,
        "over_qty": over_qty,
        "stock_position": position,
        "stock_position_label": _POSITION_LABELS.get(position, ""),
        "buy_qty": buy_qty,
        "buy_by": _iso(buy_by),
        "buy_by_label": _fmt_day(buy_by),
        "last_sale": _iso(last),
        "last_sale_label": _fmt_day(last),
        "last_sale_age_days": last_sale_age,
        "status": status,
        "status_label": _STATUS_LABELS.get(status, "On track"),
        "discontinued": bool(holding.get("discontinued")),
        "in_stock": bool(stock_fields),
    }
    year_start, year_end, _year_label = _period_bounds(as_of)["this_year"]
    ytd_qty, ytd_amount, _ytd_times = _qty_in(lines, year_start, year_end, as_of)
    card["ytd_qty"] = ytd_qty
    card["ytd_amount"] = ytd_amount
    card["headline"] = _headline(card)
    return card


def _roll(lines, as_of, field):
    grouped = {}
    for line in lines:
        d = line.get("date")
        name = clean_text(line.get(field))
        if not name or not d or d > as_of:
            continue
        row = grouped.setdefault(name.lower(), {
            "name": name,
            "qty": 0.0,
            "amount": 0.0,
            "times": 0,
            "last": d,
        })
        row["qty"] = money2(row["qty"] + (line.get("qty") or 0))
        row["amount"] = money2(row["amount"] + (line.get("amount") or 0))
        row["times"] += 1
        if d > row["last"]:
            row["last"] = d
    out = []
    for row in grouped.values():
        out.append({
            "name": row["name"],
            "uk": account_uk(row["name"]),
            "qty": row["qty"],
            "amount": row["amount"],
            "times": row["times"],
            "last_date": _iso(row["last"]),
            "last_label": _fmt_day(row["last"]),
        })
    out.sort(key=lambda r: (-r["qty"], -r["amount"], r["name"]))
    return out


def _buyers(lines, as_of):
    return _roll(lines, as_of, "party")


def _periods(lines, as_of):
    out = {}
    for key, (start, end, label) in _period_bounds(as_of).items():
        qty, amount, times = _qty_in(lines, start, end, as_of)
        names = set()
        for line in lines:
            d = line.get("date")
            if line.get("party") and _in_period(d, start, end if end else as_of) and (not d or d <= as_of):
                names.add(line["party"].lower())
        if start:
            span_end = end or as_of
            span = max(1, (min(span_end, as_of) - start).days + 1)
        else:
            span = None
        if qty > 0:
            divisor = _active_divisor(lines, start, end, as_of, span)
            per_day = money2(qty / divisor)
        else:
            divisor = span
            per_day = 0.0 if span is not None else None
        out[key] = {
            "id": key,
            "label": label,
            "qty": qty,
            "amount": amount,
            "times": times,
            "buyers": len(names),
            "window_days": span,
            "days": divisor,
            "per_day": per_day,
        }
    return out


def _movement(lines, as_of, limit=40):
    ranked = []
    for line in lines:
        d = line.get("date")
        if d and d > as_of:
            continue
        ranked.append(line)
    ranked.sort(key=lambda line: line.get("date") or "", reverse=True)
    out = []
    for line in ranked[:limit]:
        d = line.get("date")
        out.append({
            "date": _iso(d),
            "date_label": _fmt_day(d),
            "party": line.get("party") or "",
            "party_uk": account_uk(line.get("party")) if line.get("party") else "",
            "group": line.get("group") or "",
            "group_uk": account_uk(line.get("group")) if line.get("group") else "",
            "rep": line.get("rep") or "",
            "rep_uk": account_uk(line.get("rep")) if line.get("rep") else "",
            "qty": line.get("qty") or 0,
            "rate": line.get("rate"),
            "amount": line.get("amount") or 0,
            "invoice": line.get("invoice") or "",
            "invoice_id": line.get("invoice_id") or "",
        })
    return out


def _stock_rows_from_docs(docs):
    rows = []
    seen = set()
    for row in docs or []:
        fields = row.get("fields") or {}
        name = clean_text(fields.get("Item Name"))
        uk = account_uk(name or row.get("uk"))
        if not uk:
            continue
        key = uk.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append((uk, name or uk, fields))
    return rows


def _stamp_stock_attrs(card, values):
    """Category, item group, brand, and supplier. A blank uses that field's default."""
    from server.item_attrs import resolved_attr
    values = values or {}
    for name, key, uk_key in (
        ("Category", "category", "category_uk"),
        ("Item Group", "item_group", "item_group_uk"),
        ("Brand", "brand", "brand_uk"),
        ("Supplier", "supplier", "supplier_uk"),
    ):
        text, link = resolved_attr(name, values.get(name))
        card[key] = text
        card[uk_key] = link
    return card


def _build_item_cards(book):
    """Cards for stocked SKUs plus sales-only (out-of-stock) items."""
    as_of = book["as_of"]
    holds, default_min = book["holds"], book["default_min"]
    default_max_days = book.get("default_max_days", MAX_DAYS_HOLD_DEFAULT)
    lines_map = book["item_lines_by_uk"] or {}
    attrs = book.get("item_attrs") or {}
    cards = []
    seen = set()
    for uk, name, fields in book["stock_rows"] or []:
        key = (uk or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        holding = _holding_for(holds, default_min, uk, default_max_days)
        card = _card(name, fields, lines_map.get(key) or [], holding, as_of)
        cards.append(_stamp_stock_attrs(card, attrs.get(key)))
    for key, lines in lines_map.items():
        if not key or key in seen or not lines:
            continue
        seen.add(key)
        name = lines[0].get("name") or key
        uk = account_uk(name)
        holding = _holding_for(holds, default_min, uk, default_max_days)
        card = _card(name, None, lines, holding, as_of)
        cards.append(_stamp_stock_attrs(card, attrs.get(key) or attrs.get(uk.lower())))
    return cards, default_min, default_max_days


def purchase_plans(store):
    """Holding-based buy fields. The same buy_qty Item 360 shows for each item."""
    from server.book import load_book
    book = load_book(store)
    cards, _, _ = _build_item_cards(book)
    plans = []
    for card in cards:
        plans.append({
            "name": card.get("name") or "",
            "buy_qty": card.get("buy_qty") or 0.0,
            "buy_by": card.get("buy_by") or "",
            "buy_by_label": card.get("buy_by_label") or "",
            "pace": card.get("pace") or 0,
            "pace_days": card.get("pace_days") or 0,
            "fill_to": card.get("fill_to") or 0,
            "min_hold": card.get("min_hold") or 0,
            "lead_days": int(card.get("lead_days") or 0),
            "on_hand": card.get("qty") or 0,
            "discontinued": bool(card.get("discontinued")),
            "reason": _next_move(card),
            "unit_cost": card.get("rate"),
            "supplier": card.get("supplier") or "",
        })
    return plans


def list_items(store, params):
    from server.book import load_book
    book = load_book(store)
    page, limit = _page_limit(params)
    as_of = book["as_of"]
    cards, default_min, default_max_days = _build_item_cards(book)
    options = {
        "item": sorted({c["name"] for c in cards if c["name"]}),
        "status": sorted({c["status_label"] for c in cards if c["status_label"]}),
        "position": sorted({c["stock_position_label"] for c in cards if c.get("stock_position_label")}),
    }
    item_f = clean_text(params.get("item"))
    status_f = clean_text(params.get("status"))
    position_f = clean_text(params.get("position"))
    in_stock_f = clean_text(params.get("in_stock")).lower()
    filtered = []
    for card in cards:
        if item_f and card["name"] != item_f:
            continue
        if status_f and card["status_label"] != status_f:
            continue
        if position_f and card.get("stock_position_label") != position_f:
            continue
        if in_stock_f in ("yes", "1", "true"):
            if not card.get("in_stock"):
                continue
        elif in_stock_f in ("no", "0", "false"):
            if card.get("in_stock"):
                continue
        filtered.append(card)
    sort_key = clean_text(params.get("sort") or "name")
    direction = clean_text(params.get("dir") or "asc")
    if direction not in ("asc", "desc"):
        direction = "asc"

    def sort_val(card):
        if sort_key == "qty":
            return card.get("qty") or 0
        if sort_key == "min_hold":
            return card.get("min_hold") or 0
        if sort_key == "days_cover":
            return card.get("days_cover") if card.get("days_cover") is not None else -1
        if sort_key == "value":
            return card.get("value") or 0
        if sort_key == "last_sale":
            return card.get("last_sale") or ""
        if sort_key == "status":
            return card.get("status_label") or ""
        if sort_key == "position":
            return card.get("stock_position_label") or ""
        if sort_key == "buy_qty":
            return card.get("buy_qty") or 0
        if sort_key == "pace_30":
            return card.get("pace_30") or 0
        if sort_key in ("category", "item_group", "brand", "supplier"):
            return (card.get(sort_key) or "").lower()
        return (card.get("name") or "").lower()

    numeric = sort_key in ("qty", "min_hold", "days_cover", "value", "buy_qty", "pace_30")
    filtered.sort(key=sort_val, reverse=(direction == "desc") if numeric or sort_key == "last_sale" else (direction == "desc"))
    total = len(filtered)
    start = (page - 1) * limit
    buy_cards = [c for c in cards if c.get("status") in ("low", "soon") and (c.get("buy_qty") or 0) > 0]
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": filtered[start:start + limit],
        "options": options,
        "sort": sort_key or "name",
        "dir": direction,
        "default_min": default_min,
        "as_of": _iso(as_of),
        "low_count": sum(1 for c in cards if c["status"] == "low"),
        "soon_count": sum(1 for c in cards if c["status"] == "soon"),
        "under_count": sum(1 for c in cards if c.get("stock_position") == "under"),
        "over_count": sum(1 for c in cards if c.get("stock_position") == "over"),
        "dead_count": sum(1 for c in cards if c.get("stock_position") == "dead"),
        "out_of_stock_count": sum(1 for c in cards if not c.get("in_stock")),
        "default_max_days": default_max_days,
        "buy_count": len(buy_cards),
        "buy_qty_sum": round(sum(float(c.get("buy_qty") or 0) for c in buy_cards), 2),
        "buy_value_sum": round(sum(
            float(c.get("buy_qty") or 0) * float(c.get("rate") or 0)
            for c in buy_cards
        ), 2),
    }


def get_item(store, uk):
    from server.book import load_book
    uk = account_uk(uk)
    if not uk:
        return None
    book = load_book(store)
    as_of = book["as_of"]
    holds, default_min = book["holds"], book["default_min"]
    default_max_days = book.get("default_max_days", MAX_DAYS_HOLD_DEFAULT)
    lines_map = book["item_lines_by_uk"]
    stock_fields = None
    name = uk
    for row_uk, row_name, fields in book["stock_rows"]:
        if row_uk.lower() == uk.lower():
            stock_fields = fields
            name = row_name
            uk = row_uk
            break
    lines = None
    for key, value in lines_map.items():
        if key == uk.lower():
            lines = value
            if value and value[0].get("name"):
                name = value[0]["name"]
            break
    lines = lines or []
    if stock_fields is None and not lines:
        return None
    holding = _holding_for(holds, default_min, uk, default_max_days)
    card = _card(name, stock_fields, lines, holding, as_of)
    buyers = _buyers(lines, as_of)
    usual = ""
    if buyers:
        usual = buyers[0]["name"]
    periods = _periods(lines, as_of)
    detail = {
        **card,
        "as_of": _iso(as_of),
        "as_of_label": _fmt_day(as_of),
        "default_min": default_min,
        "default_max_days": default_max_days,
        "holding": {
            "min_hold": holding["min_hold"],
            "fill_to": holding.get("fill_to"),
            "lead_days": holding.get("lead_days") or 0,
            "max_days_hold": holding.get("max_days_hold") or MAX_DAYS_HOLD_DEFAULT,
            "own_min": holding.get("own_min") or False,
            "own_max_days": holding.get("own_max_days") or False,
            "uses_default_min": not holding.get("own_min"),
            "uses_default_max_days": not holding.get("own_max_days"),
            "discontinued": bool(holding.get("discontinued")),
        },
        "buyers": buyers,
        "groups": _roll(lines, as_of, "group"),
        "reps": _roll(lines, as_of, "rep"),
        "usual_buyer": usual,
        "periods": periods,
        "movement": _movement(lines, as_of),
        "insight": _build_insight(card, buyers),
    }
    from server.item_attrs import public_attrs
    detail.update(public_attrs(store, uk))
    from server.repurchase import attach_repurchase
    return attach_repurchase(store, detail, item=detail.get("uk") or uk)
