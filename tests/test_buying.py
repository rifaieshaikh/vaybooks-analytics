"""Phase 6 purchase behavior shares one ledger exposure."""

from decimal import Decimal

from server.order_check import evaluate_order_check
from vay.buying import exposure_before, purchase_behavior


def _sales():
    return [
        {"date": "2024-01-01", "invoice": "A", "amount": "100", "qty": "2", "product": "Board"},
        {"date": "2024-02-01", "invoice": "B", "amount": "50", "qty": "1"},
        {"date": "2024-04-01", "invoice": "C", "amount": "80", "qty": "1"},
    ]


def test_purchases_are_not_orders_and_a_short_history_has_no_next_date():
    behavior = purchase_behavior(
        _sales()[:2],
        as_of="2024-05-01",
        coverage={"complete": True, "start": "2023-04-01"},
        movements=[{"date": "2023-12-01", "amount": "40", "side": "debit"}],
        opening_known=True,
        products=[{"name": "Board", "amount": "100", "qty": "2"}],
        exposure="90",
        exposure_exact=True,
    )
    assert behavior["basis"] == "observed_purchases"
    assert behavior["order_records"] == "none"
    assert behavior["purchase_occasions"] == 2
    assert behavior["invoice_count"] == 2
    assert behavior["value"] == 150.0
    assert behavior["quantity"] == 3.0
    assert behavior["median_gap_days"] is None
    assert behavior["cycle_evidence"] == "insufficient"
    assert behavior["next_purchase"] is None
    assert behavior["customer_kind"] == "new"
    assert behavior["product_mix"][0]["name"] == "Board"
    assert behavior["purchases"][1]["exposure_before"] == 40.0
    assert behavior["exposure"] == 90.0


def test_three_covered_purchases_can_show_a_late_cycle():
    behavior = purchase_behavior(
        _sales(),
        as_of="2024-08-01",
        coverage={"complete": True, "start": "2023-04-01"},
        opening_known=True,
        exposure="10",
        exposure_exact=True,
    )
    assert behavior["median_gap_days"] == 45.5
    assert behavior["cycle_evidence"] == "sufficient"
    assert behavior["late_cycle"] is True
    assert behavior["advice"] == "available"


def test_unknown_opening_does_not_invent_exposure_before_a_purchase():
    before = exposure_before(
        [{"date": "2024-01-01", "amount": "100", "side": "debit", "opening": True, "unknown_age": True}],
        "2024-02-01",
        opening_known=False,
    )
    assert before["available"] is False
    assert before["amount"] is None
    behavior = purchase_behavior(
        _sales(),
        as_of="2024-05-01",
        coverage={"complete": False, "start": "2024-01-01"},
        opening_known=False,
        exposure=None,
        exposure_exact=False,
    )
    assert behavior["customer_kind"] == "first_seen"
    assert behavior["advice"] == "withhold"
    assert behavior["exposure"] is None
    assert behavior["purchases"][0]["exposure_available"] is False


def test_profile_ordering_and_order_check_share_exposure():
    detail = {
        "uk": "acme",
        "name": "Acme",
        "due": 90,
        "due_days": 30,
        "as_of": "2024-05-01",
        "balance_exact": True,
        "ordering": {"overall": {"events": [
            {"date_iso": "2024-01-01", "invoice": "A", "amount": 100},
            {"date_iso": "2024-02-01", "invoice": "B", "amount": 50},
            {"date_iso": "2024-04-01", "invoice": "C", "amount": 80},
        ]}},
        "buying": {"periods": {"all": {"items": [{"name": "Board", "amount": 100, "qty": 2}]}}},
    }
    from server.ledger_apply import attach_purchase_behavior
    attach_purchase_behavior(detail, {
        "coverage": {"complete": True, "start": "2023-04-01"},
        "withheld_outputs": [],
        "movements": [
            {"date": "2023-12-01", "amount": "40", "side": "debit"},
            {"date": "2024-01-01", "amount": "100", "side": "debit"},
            {"date": "2024-01-15", "amount": "50", "side": "credit"},
        ],
    })
    assert detail["purchase_behavior"]["exposure"] == 90
    assert detail["ordering"]["overall"]["events"][1]["exposure_before"] == 90.0
    checked = evaluate_order_check(detail, order_value=20, policy={"credit_limit": 200})
    assert checked["exposure"] == 90
    assert checked["headroom"] == 90
    assert checked["action"] != "withhold"
    detail["purchase_behavior"]["advice"] = "withhold"
    detail["purchase_behavior"]["uncertain"] = ["Opening is unknown. Exposure is not a complete balance."]
    withheld = evaluate_order_check(detail, order_value=20)
    assert withheld["action"] == "withhold"
    assert withheld["exposure"] == 90
