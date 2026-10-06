"""Each generated report is tied to a permission."""

from server.auth import can_generate, filter_report_ids, report_allowed


FINANCE = [
    "reports.create",
    "reports.view.profit",
    "reports.view.issues",
    "reports.view.monthly",
    "reports.view.scorecard",
    "reports.view.quality",
    "customer.view",
]


def test_finance_can_generate_only_its_reports():
    assert can_generate(FINANCE, "Monthly profit")
    assert can_generate(FINANCE, "phase2_scorecard")
    assert can_generate(FINANCE, "phase2_quality")
    assert can_generate(FINANCE, "360-customers")
    assert can_generate(FINANCE, "360-business")
    assert not can_generate(FINANCE, "Sales rep performance")
    assert not can_generate(FINANCE, "phase2_collection")
    assert not can_generate(FINANCE, "360-items")
    assert not can_generate(FINANCE, "phase2_stock")


def test_repurchase_allows_either_customer_or_stock():
    assert can_generate(["stock.view"], "360-repurchase")
    assert can_generate(["customer.view"], "360-repurchase")
    assert not can_generate(["reports.view.performance"], "360-repurchase")


def test_filter_drops_reports_the_role_cannot_create():
    kept = filter_report_ids(
        ["Sales rep performance", "phase2_scorecard", "reconcile", "360-items"],
        FINANCE,
    )
    assert kept == ["phase2_scorecard", "reconcile"]


def test_data_quality_uses_its_own_permission():
    sheet = {"id": "phase2_quality", "group": "Data issues", "title": "Data quality"}
    assert not report_allowed(sheet, ["reports.view.issues"])
    assert report_allowed(sheet, ["reports.view.quality"])
    warnings = {"id": "source_data_warnings", "group": "Data issues", "title": "Source data warnings"}
    assert report_allowed(warnings, ["reports.view.issues"])
    assert not report_allowed(warnings, ["reports.view.quality"])
