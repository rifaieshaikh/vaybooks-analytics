"""Recovery forecasts stay withheld until completed periods pass a fixed backtest."""

import time
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from server.backup import snapshot_org
from server.main import app
from server.store import get_store
from tests.test_phase3 import _receipt, client
from vay.ledger import settle
from vay.recovery_forecast import (
    MAX_ABS_BIAS_RATIO,
    MIN_BACKTEST_ORIGINS,
    MIN_CLOSED_PERIODS,
    MIN_INTERVAL_COVERAGE,
    collect_outcomes,
    recovery_forecast,
)

WEEKS = [
    ("2024-01-01", "2024-01-07"),
    ("2024-01-08", "2024-01-14"),
    ("2024-01-15", "2024-01-21"),
    ("2024-01-22", "2024-01-28"),
    ("2024-01-29", "2024-02-04"),
    ("2024-02-05", "2024-02-11"),
]
AS_OF = "2024-03-01"
DEBT = [{"id": "INV-1", "remaining": 100, "overdue": True}]


def _target(start, end, cash, owner="ada"):
    return {
        "id": start,
        "customer_name": "Acme",
        "owner": owner,
        "period_start": start,
        "period_end": end,
        "assigned_amount": "100",
        "status": "open",
    }


def _weeks(amounts, owner="ada"):
    targets = []
    receipts = []
    for (start, end), amount in zip(WEEKS, amounts):
        targets.append(_target(start, end, amount, owner))
        receipts.append({
            "id": start,
            "name": "Acme",
            "date": start,
            "amount": str(amount),
            "cash": True,
            "source_type": "receipt",
        })
    return targets, receipts


def _forecast(amounts, as_of=AS_OF, coverage="2024-02-11", extra_receipts=None, owner=""):
    targets, receipts = _weeks(amounts)
    if extra_receipts:
        receipts.extend(extra_receipts)
    collected = collect_outcomes(targets, receipts, as_of=as_of, coverage=coverage)
    return recovery_forecast(
        collected["outcomes"],
        as_of=as_of,
        horizon_days=7,
        owner=owner,
        exclusions=collected["exclusions"],
    )


def test_limits_are_fixed_before_a_result_is_released():
    assert MIN_CLOSED_PERIODS == 3
    assert MIN_BACKTEST_ORIGINS == 3
    assert MAX_ABS_BIAS_RATIO == Decimal("0.50")
    assert MIN_INTERVAL_COVERAGE == Decimal("0.50")
    short = _forecast([40, 40])
    assert short["released"] is False
    assert short["expected_cash"] is None
    assert short["limits"]["min_closed_periods"] == MIN_CLOSED_PERIODS
    assert short["commitments_unchanged"] is True


def test_steady_history_releases_the_median_and_ignores_later_cash():
    released = _forecast([40, 40, 40, 40, 40, 40], extra_receipts=[{
        "id": "later",
        "name": "Acme",
        "date": "2024-04-01",
        "amount": "5000",
        "cash": True,
    }])
    assert released["released"] is True
    assert released["expected_cash"] == Decimal("40.00")
    assert released["interval"]["low"] == Decimal("40.00")
    assert released["interval"]["high"] == Decimal("40.00")
    assert released["backtest"]["bias_ratio"] == Decimal("0.0000")
    assert released["backtest"]["interval_coverage"] == Decimal("1.0000")
    origin = released["backtest"]["rows"][0]
    assert origin["period_start"] == "2024-01-22"
    assert origin["predicted"] == Decimal("40.00")
    varied = _forecast([10, 20, 30, 40, 50, 60])
    assert varied["backtest"]["rows"][0]["predicted"] == Decimal("20.00")
    assert varied["backtest"]["rows"][0]["actual"] == Decimal("40.00")


def test_bias_outside_the_limit_withholds_the_amount():
    withheld = _forecast([10, 10, 10, 10, 10, 100])
    assert withheld["released"] is False
    assert withheld["expected_cash"] is None
    assert withheld["backtest"]["accepted"] is False
    assert "Bias" in withheld["reason"]


def test_missing_coverage_credit_notes_and_overlaps_are_not_outcomes():
    targets, receipts = _weeks([40, 40, 40, 40, 40, 40])
    receipts.append({
        "id": "note",
        "name": "Acme",
        "date": "2024-01-02",
        "amount": "15",
        "cash": False,
        "source_type": "credit_note",
    })
    collected = collect_outcomes(targets, receipts, as_of=AS_OF, coverage="")
    assert all(row["usable"] is False for row in collected["outcomes"])
    covered = collect_outcomes(targets, receipts, as_of=AS_OF, coverage="2024-02-11")
    assert covered["outcomes"][0]["cash"] == Decimal("40.00")
    overlap = collect_outcomes(
        targets[:1] + [_target("2024-01-07", "2024-01-13", 40)],
        receipts,
        as_of=AS_OF,
        coverage="2024-02-11",
    )
    assert all(row["usable"] is False for row in overlap["outcomes"])
    early = _forecast([40, 40, 40, 40, 40, 40], as_of="2024-01-20")
    assert early["released"] is False
    assert early["evidence"]["closed_periods"] == 2


def test_api_keeps_the_assigned_target_when_the_forecast_is_withheld_or_released():
    c = client()
    empty = c.get("/api/recovery-forecast", params={"as_of": "2026-10-17"})
    assert empty.status_code == 200, empty.text
    assert empty.json()["released"] is False
    assert empty.json()["expected_cash"] is None
    current = c.post("/api/collection/targets", json={
        "customer_name": "Acme",
        "owner": "ada",
        "period_start": "2099-01-01",
        "period_end": "2099-01-07",
        "assigned_amount": 80,
        "debts": DEBT,
    })
    assert current.status_code == 200, current.text
    held = c.get("/api/collection", params={"customer": "Acme"}).json()
    assert held["assigned_targets"] == 80
    assert "stays as entered" in held["forecast_note"]
    for index, (start, end) in enumerate(WEEKS):
        created = c.post("/api/collection/targets", json={
            "customer_name": "Acme",
            "owner": "ada",
            "period_start": start,
            "period_end": end,
            "assigned_amount": 100,
            "debts": DEBT,
        })
        assert created.status_code == 200, created.text
        _receipt("r-%s" % index, 40, invoice="INV-1", date=start)
    get_store().upsert_row({
        "type": "customer_opening",
        "uk": "coverage-acme",
        "fields": {"Account Name": "Acme", "Kind": "coverage", "Complete Through": "2024-02-11"},
    })
    forecast = c.get("/api/recovery-forecast", params={"as_of": "2026-10-17"}).json()
    assert forecast["released"] is True
    assert forecast["expected_cash"] == 40
    assert forecast["version"] == "1"
    follow = c.get("/api/collection", params={"customer": "Acme"}).json()
    current_row = next(row for row in follow["targets"] if row["period_start"] == "2099-01-01")
    assert follow["assigned_targets"] == 80
    assert current_row["assigned_amount"] == 80
    assert current_row["baseline_amount"] == 80
    cash = c.get("/api/cash").json()
    assert "expected_cash" not in cash
    assert round(sum(week["promises"] for week in cash["weeks"]), 2) == current_row["remaining"]
    assert current_row["remaining"] != forecast["expected_cash"]
    blocked = c.get("/api/recovery-forecast", params={"horizon_days": "0"})
    assert blocked.status_code == 400


def test_forecast_requires_a_cash_permission_and_restore_keeps_the_result():
    c = client()
    for index, (start, end) in enumerate(WEEKS):
        assert c.post("/api/collection/targets", json={
            "customer_name": "Acme",
            "owner": "ada",
            "period_start": start,
            "period_end": end,
            "assigned_amount": 100,
            "debts": DEBT,
        }).status_code == 200
        _receipt("r-%s" % index, 40, invoice="INV-1", date=start)
    get_store().upsert_row({
        "type": "customer_opening",
        "uk": "coverage-acme",
        "fields": {"Account Name": "Acme", "Kind": "coverage", "Complete Through": "2024-02-11"},
    })
    before = c.get("/api/recovery-forecast", params={"as_of": "2026-10-17"}).json()
    assert before["expected_cash"] == 40
    snap = snapshot_org(get_store())
    get_store().delete_row("receipt", "r-0")
    get_store().delete_row("receipt", "r-1")
    get_store().delete_row("receipt", "r-2")
    changed = c.get("/api/recovery-forecast", params={"as_of": "2026-10-17"}).json()
    assert changed["expected_cash"] != 40 or changed["released"] is False
    restored = c.post("/api/backup/restore", json=snap)
    assert restored.status_code == 200, restored.text
    after = c.get("/api/recovery-forecast", params={"as_of": "2026-10-17"}).json()
    assert after["expected_cash"] == before["expected_cash"]
    assert after["released"] is True
    role = c.post("/api/roles", json={"name": "Clerk", "permissions": ["sales.view"]})
    assert role.status_code == 200, role.text
    assert c.post("/api/users", json={"username": "clerk", "password": "clerk12345", "role": "Clerk"}).status_code == 200
    clerk = TestClient(app)
    assert clerk.post("/api/auth/login", json={"username": "clerk", "password": "clerk12345"}).status_code == 200
    assert clerk.get("/api/recovery-forecast").status_code == 403


def test_two_full_replays_match_on_a_larger_ledger():
    scope = {
        "organization_id": "org",
        "legal_entity_id": "org",
        "customer_id": "acme",
        "currency": "INR",
    }
    debits = []
    credits = []
    for index in range(1500):
        debits.append({
            **scope,
            "source_id": "d-%s" % index,
            "amount": "100.00",
            "invoice_date": date(2024, 1, 1 + (index % 27)).isoformat(),
            "effective_date": date(2024, 1, 1 + (index % 27)).isoformat(),
            "invoice_number": "INV-%s" % index,
        })
        if index % 2 == 0:
            credits.append({
                **scope,
                "source_id": "c-%s" % index,
                "kind": "receipt",
                "cash": True,
                "amount": "40.00",
                "effective_date": date(2024, 2, 1 + (index % 27)).isoformat(),
            })
    started = time.perf_counter()
    first = settle(debits, credits, policy="invoice_date_fifo", as_of="2024-03-31", **scope)
    second = settle(debits, credits, policy="invoice_date_fifo", as_of="2024-03-31", **scope)
    elapsed = time.perf_counter() - started
    assert [(row["debit_id"], str(row["amount"])) for row in first["allocations"]] == [
        (row["debit_id"], str(row["amount"])) for row in second["allocations"]
    ]
    assert elapsed < 5
