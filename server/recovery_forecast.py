"""Read collection history and return the pure recovery forecast."""

from decimal import Decimal

from server.collection import TARGET_TYPE, _key, _load_sources, _rows, _today, coverage_through
from vay.recovery_forecast import collect_outcomes, recovery_forecast


def _public(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _public(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_public(item) for item in value]
    return value


def recovery_forecast_view(store, as_of="", horizon_days=7, owner=""):
    day = _today(as_of or None, store)
    targets = list(_rows(store, TARGET_TYPE))
    coverage = {}
    for row in targets:
        name = row.get("customer_name") or ""
        if name not in coverage:
            through = coverage_through(store, name)
            coverage[name] = through
            coverage[_key(name)] = through
    collected = collect_outcomes(targets, _load_sources(store), as_of=day, coverage=coverage)
    result = recovery_forecast(
        collected["outcomes"],
        as_of=day,
        horizon_days=horizon_days,
        owner=owner or "",
        exclusions=collected["exclusions"],
    )
    return _public(result)
