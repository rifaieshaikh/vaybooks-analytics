"""Expected collection cash from completed target periods.

The acceptance limits below are the rule. A result is scored only after they
are fixed. Assigned targets and promises are never rewritten from this figure,
and the figure is never a fixed share of a promise.
"""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from vay.ledger import money

FORECAST_VERSION = "1"
METHOD = "trailing_median_cash"
MIN_CLOSED_PERIODS = 3
MIN_BACKTEST_ORIGINS = 3
MAX_ABS_BIAS_RATIO = Decimal("0.50")
MIN_INTERVAL_COVERAGE = Decimal("0.50")
RATIO = Decimal("0.0001")

COMMITMENT_NOTE = (
    "Assigned targets and promises stay as entered. Expected cash is not added "
    "to planned inflows and is not a percentage of those commitments."
)
ASSUMPTIONS = (
    "Only a target period that has already ended is an outcome.",
    "Cash is the receipt amount inside that period. Credit notes are excluded.",
    "A receipt dated after the forecast date is ignored.",
    "The estimate is the median of earlier periods of the same length.",
    "The interval is the lowest and highest of those same periods.",
    COMMITMENT_NOTE,
)


def _day(value):
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _key(value):
    return " ".join(str(value or "").split()).lower()


def _amount(value):
    parsed = money(value or 0)
    return parsed if parsed is not None else Decimal("0.00")


def _ratio(part, whole):
    if whole == 0:
        return None
    return (part / whole).quantize(RATIO, rounding=ROUND_HALF_UP)


def _add(messages, text):
    if text not in messages:
        messages.append(text)


def horizon_length(start, end):
    first, last = _day(start), _day(end)
    if not first or not last or last < first:
        return None
    return (last - first).days + 1


def _median(values):
    ordered = sorted(values)
    count = len(ordered)
    mid = count // 2
    if count % 2:
        return ordered[mid]
    return money((ordered[mid - 1] + ordered[mid]) / 2)


def _coverage_day(coverage, customer):
    if isinstance(coverage, str):
        return _day(coverage)
    if isinstance(coverage, dict):
        found = coverage.get(_key(customer))
        if found is None:
            found = coverage.get(customer)
        return _day(found)
    return None


def _is_cash(row):
    if str(row.get("source_type") or "receipt") == "credit_note":
        return False
    return row.get("cash") is not False


def collect_outcomes(targets, receipts, *, as_of, coverage):
    """Closed target periods only. Later receipts cannot enter an earlier period."""
    as_of_day = _day(as_of)
    if not as_of_day:
        raise ValueError("as_of is required")
    exclusions = []
    candidates = []
    for row in targets or []:
        status = str(row.get("status") or "open")
        if status == "superseded":
            _add(exclusions, "Superseded targets stay in the assignment history and are not a second cash result.")
            continue
        if status == "cancelled":
            _add(exclusions, "Cancelled targets are not collection results.")
            continue
        if status != "open":
            _add(exclusions, "Only an open completed period can be a result.")
            continue
        start, end = _day(row.get("period_start")), _day(row.get("period_end"))
        if not start or not end or end < start:
            _add(exclusions, "A target needs a start and an end date.")
            continue
        if end >= as_of_day:
            _add(exclusions, "A period that has not ended is not an outcome.")
            continue
        candidates.append(row)

    blocked = set()
    for left in range(len(candidates)):
        for right in range(left + 1, len(candidates)):
            a, b = candidates[left], candidates[right]
            if _key(a.get("customer_name")) != _key(b.get("customer_name")):
                continue
            a_start, a_end = _day(a.get("period_start")), _day(a.get("period_end"))
            b_start, b_end = _day(b.get("period_start")), _day(b.get("period_end"))
            if a_start <= b_end and b_start <= a_end:
                blocked.add(id(a))
                blocked.add(id(b))
    if blocked:
        _add(exclusions, "Overlapping periods for the same customer are excluded because the cash cannot be separated.")

    by_customer = {}
    for row in receipts or []:
        if not _is_cash(row):
            continue
        day = _day(row.get("date"))
        if day is None:
            _add(exclusions, "A receipt without a date is left out.")
            continue
        if day > as_of_day:
            continue
        by_customer.setdefault(_key(row.get("name")), []).append((day, _amount(row.get("amount"))))

    outcomes = []
    ordered = sorted(candidates, key=lambda row: (str(row.get("period_end") or ""), str(row.get("id") or "")))
    for row in ordered:
        start, end = _day(row.get("period_start")), _day(row.get("period_end"))
        length = horizon_length(start, end)
        reason = ""
        usable = id(row) not in blocked
        if not usable:
            reason = "Overlapping periods for the same customer are excluded because the cash cannot be separated."
        through = _coverage_day(coverage, row.get("customer_name"))
        if usable and (through is None or through < end):
            usable = False
            reason = "Receipt coverage does not reach the end of this period."
            _add(exclusions, reason)
        cash = Decimal("0.00")
        if usable:
            for day, amount in by_customer.get(_key(row.get("customer_name")), []):
                if start <= day <= end:
                    cash = money(cash + amount)
        outcomes.append({
            "id": row.get("id") or "",
            "customer_name": row.get("customer_name") or "",
            "owner": row.get("owner") or "",
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "horizon_days": length,
            "assigned": _amount(row.get("assigned_amount")),
            "cash": cash,
            "usable": usable,
            "reason": reason,
        })
    return {"outcomes": outcomes, "exclusions": exclusions}


def _limits():
    return {
        "min_closed_periods": MIN_CLOSED_PERIODS,
        "min_backtest_origins": MIN_BACKTEST_ORIGINS,
        "max_abs_bias_ratio": MAX_ABS_BIAS_RATIO,
        "min_interval_coverage": MIN_INTERVAL_COVERAGE,
    }


def _predict(history):
    amounts = [row["cash"] for row in history]
    return {"amount": _median(amounts), "low": min(amounts), "high": max(amounts)}


def _backtest(history):
    ordered = sorted(history, key=lambda row: (row["period_end"], row["id"]))
    origins = []
    for index, row in enumerate(ordered):
        start = _day(row["period_start"])
        prior = [item for item in ordered[:index] if _day(item["period_end"]) < start]
        if len(prior) < MIN_CLOSED_PERIODS:
            continue
        predicted = _predict(prior)
        actual = row["cash"]
        origins.append({
            "period_start": row["period_start"],
            "period_end": row["period_end"],
            "predicted": predicted["amount"],
            "low": predicted["low"],
            "high": predicted["high"],
            "actual": actual,
            "covered": predicted["low"] <= actual <= predicted["high"],
        })
    count = len(origins)
    if not count:
        return {
            "origins": 0,
            "required_origins": MIN_BACKTEST_ORIGINS,
            "rows": [],
            "mean_error": None,
            "bias_ratio": None,
            "interval_coverage": None,
            "accepted": False,
            "reason": "Fewer than %s backtest origins." % MIN_BACKTEST_ORIGINS,
        }
    error = Decimal("0.00")
    actual_total = Decimal("0.00")
    covered = 0
    for row in origins:
        error = money(error + row["predicted"] - row["actual"])
        actual_total = money(actual_total + row["actual"])
        if row["covered"]:
            covered += 1
    mean_error = money(error / Decimal(count))
    mean_actual = actual_total / Decimal(count)
    bias = _ratio(mean_error, mean_actual)
    coverage = _ratio(Decimal(covered), Decimal(count))
    accepted = True
    reason = ""
    if count < MIN_BACKTEST_ORIGINS:
        accepted = False
        reason = "Fewer than %s backtest origins." % MIN_BACKTEST_ORIGINS
    elif bias is None:
        accepted = False
        reason = "Bias cannot be measured when collected cash is zero."
    elif abs(bias) > MAX_ABS_BIAS_RATIO:
        accepted = False
        reason = "Bias is outside the acceptance limit."
    elif coverage is None or coverage < MIN_INTERVAL_COVERAGE:
        accepted = False
        reason = "Interval coverage is below the acceptance limit."
    return {
        "origins": count,
        "required_origins": MIN_BACKTEST_ORIGINS,
        "rows": origins,
        "mean_error": mean_error,
        "bias_ratio": bias,
        "interval_coverage": coverage,
        "accepted": accepted,
        "reason": reason,
    }


def _forecast_one(outcomes, *, as_of, horizon_days, exclusions):
    as_of_day = _day(as_of)
    matched = [
        row for row in outcomes or []
        if row.get("usable") and row.get("horizon_days") == horizon_days and _day(row.get("period_end")) < as_of_day
    ]
    completed = [row for row in outcomes or [] if _day(row.get("period_end")) and _day(row.get("period_end")) < as_of_day]
    backtest = _backtest(matched)
    released = False
    expected = None
    interval = {"low": None, "high": None, "label": "Lowest and highest cash in the periods used."}
    if len(matched) < MIN_CLOSED_PERIODS:
        if not completed:
            reason = "No completed collection period yet. Assigned targets and promises still stand."
        elif not any(row.get("usable") for row in completed):
            reason = "Completed periods are missing coverage or overlap, so there is no estimate."
        elif not any(row.get("horizon_days") == horizon_days for row in completed if row.get("usable")):
            reason = "No completed period of this length."
        else:
            reason = "Fewer than %s completed periods of this length." % MIN_CLOSED_PERIODS
    elif not backtest["accepted"]:
        reason = backtest["reason"]
    else:
        predicted = _predict(matched)
        released = True
        expected = predicted["amount"]
        interval = {"low": predicted["low"], "high": predicted["high"], "label": interval["label"]}
        reason = ""
    return {
        "version": FORECAST_VERSION,
        "method": METHOD,
        "method_label": "Median cash collected in earlier completed periods of the same length.",
        "as_of": as_of_day.isoformat() if as_of_day else "",
        "horizon_days": horizon_days,
        "released": released,
        "expected_cash": expected,
        "interval": interval,
        "reason": reason,
        "assumptions": list(ASSUMPTIONS),
        "exclusions": list(exclusions or []),
        "evidence": {
            "closed_periods": len(matched),
            "completed_periods": len(completed),
            "required_periods": MIN_CLOSED_PERIODS,
        },
        "limits": _limits(),
        "backtest": backtest,
        "commitments_unchanged": True,
        "note": COMMITMENT_NOTE,
    }


def recovery_forecast(outcomes, *, as_of, horizon_days, owner="", exclusions=None):
    """Score one horizon. An owner segment uses only that owner's periods."""
    if not _day(as_of):
        raise ValueError("as_of is required")
    length = int(horizon_days)
    if length < 1:
        raise ValueError("horizon_days must be at least 1")
    selected = [row for row in outcomes or [] if not owner or str(row.get("owner") or "") == owner]
    result = _forecast_one(selected, as_of=as_of, horizon_days=length, exclusions=exclusions)
    result["segment"] = ("owner:" + owner) if owner else "all"
    result["outcomes"] = selected
    if owner:
        result["segments"] = []
        return result
    names = sorted({str(row.get("owner") or "") for row in outcomes or [] if row.get("usable")})
    result["segments"] = []
    for name in names:
        segment = _forecast_one(
            [row for row in outcomes or [] if str(row.get("owner") or "") == name],
            as_of=as_of,
            horizon_days=length,
            exclusions=[],
        )
        segment["segment"] = "owner:" + name
        segment.pop("assumptions", None)
        segment.pop("outcomes", None)
        result["segments"].append(segment)
    return result
