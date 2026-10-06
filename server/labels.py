"""Friendly titles and groups by report id. No Streamlit import."""

FRIENDLY_TITLES = {
    "sales_rep_performance_report": "Sales by person",
    "account_performance_report": "Sales by customer",
    "group_performance_report": "Sales by group",
    "fiscal_monthly_sales_rep_performance_report": "This year by month — people",
    "fiscal_monthly_account_performance_report": "This year by month — customers",
    "fiscal_monthly_group_performance_report": "This year by month — groups",
    "item_wise_sales": "Item sales",
    "item_cost_exceptions": "Items missing cost",
    "item_wise_monthly_qty": "Item quantity by month",
    "item_wise_profit": "Item profit",
    "item_wise_monthly_profit": "Item profit by month",
    "monthly_profit_report": "Profit and loss",
    "expense_by_category": "Expenses by category",
    "expense_by_account": "Expenses by account",
    "unmapped_payment_accounts": "Unmapped payments",
    "source_data_warnings": "Data issues",
    "phase2_scorecard": "Scorecard",
    "phase2_sales_change": "Sales change",
    "phase2_customer_movement": "Customer movement",
    "phase2_collection": "Collection worklist",
    "phase2_stock": "Stock decisions",
    "phase2_quality": "Data quality",
}

PERFORMANCE_IDS = (
    "sales_rep_performance_report",
    "account_performance_report",
    "group_performance_report",
)
ITEMS_IDS = (
    "item_wise_sales",
    "item_cost_exceptions",
    "item_wise_monthly_qty",
)
PROFIT_IDS = (
    "monthly_profit_report",
    "expense_by_category",
    "expense_by_account",
    "unmapped_payment_accounts",
    "item_wise_profit",
    "item_wise_monthly_profit",
)
SALES_FOLLOW_PREFIX = "sales_follow_up_"
COLLECTION_FOLLOW_PREFIX = "collection_follow_up_"
GROUP_ORDER = ("Performance", "Follow-up", "Monthly", "Items", "Profit", "Data issues")


def report_id(report):
    return report.get("id") or ""


def friendly_title(report):
    rid = report_id(report)
    if rid.startswith(SALES_FOLLOW_PREFIX):
        return "Who to follow up — sales"
    if rid.startswith(COLLECTION_FOLLOW_PREFIX):
        return "Who to follow up — collections"
    return FRIENDLY_TITLES.get(rid, report.get("title") or rid)


def report_group(report):
    rid = report_id(report)
    if rid in ("phase2_scorecard", "phase2_sales_change", "phase2_customer_movement"):
        return "Scorecard"
    if rid == "phase2_collection":
        return "Follow-up"
    if rid == "phase2_stock":
        return "Items"
    if rid == "phase2_quality":
        return "Data issues"
    if rid.startswith(SALES_FOLLOW_PREFIX) or rid.startswith(COLLECTION_FOLLOW_PREFIX) or report.get("followup"):
        return "Follow-up"
    if rid.startswith("fiscal_monthly_"):
        return "Monthly"
    if rid == "source_data_warnings":
        return "Data issues"
    if rid in PERFORMANCE_IDS:
        return "Performance"
    if rid in ITEMS_IDS:
        return "Items"
    if rid in PROFIT_IDS:
        return "Profit"
    return "Performance"
