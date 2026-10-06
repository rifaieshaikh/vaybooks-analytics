# Port of VAY_CONFIG from Vay_Reports_Fixed.gs (password hash lives in Streamlit secrets).

SOURCE_SHEETS = ["sales", "receipt", "credit_note", "arr", "stock", "items", "payments"]

FIXED_REPORT_SHEETS = [
    "sales_rep_performance_report",
    "fiscal_monthly_sales_rep_performance_report",
    "fiscal_monthly_account_performance_report",
    "fiscal_monthly_group_performance_report",
    "account_performance_report",
    "group_performance_report",
    "item_wise_sales",
    "item_wise_profit",
    "item_wise_monthly_profit",
    "item_wise_monthly_qty",
    "item_cost_exceptions",
    "source_data_warnings",
    "monthly_profit_report",
    "expense_by_category",
    "expense_by_account",
    "unmapped_payment_accounts",
]

# Default inclusive tax rate; org policy may override at generate time.
SALES_TAX_INCLUSIVE_RATE = 0.18
MAX_WARNING_ROWS = 200
WARNING_KEY_LIMIT = 50
NUMERIC_FORMAT = "#,##0.00"

# Expense account maps live in industry packs / org settings (see vay.packs.vay_wholesale).
# Do not hard-code pilot account names in formula modules.

FOLLOW_UP_PREFIXES = ["sales_follow_up_", "collection_follow_up_"]
DEFAULT_SALES_REP = "NO_REP"
DEFAULT_RECEIPT_REP = "INVESTMENT"
DEFAULT_PARTY = "NO_PARTY_NAME"
DEFAULT_GROUP = "NO_GROUP"

TEXT_HEADERS = {
    "Status", "Stock Status", "Issue", "Type", "Source", "Key", "Detail",
    "Message", "Report", "Customer", "Account Name", "Group", "Sales Rep",
    "Item Name", "Generated At", "Report Date", "Timezone", "Phase", "Export Folder",
    "Line", "Category", "Component",
    "Metric", "Customer", "Movement", "Buying cycle", "Invoices", "Item",
    "Severity", "Fix", "Reason",
}

STATUS_COLORS = {
    "SUCCESS": "#d9ead3",
    "FAILED": "#f4cccc",
    "SKIPPED": "#fff2cc",
    "URGENT": "#f4cccc",
    "FOLLOW UP": "#fff2cc",
    "WATCH": "#cfe2f3",
    "NEWLY INACTIVE": "#ead1dc",
    "DORMANT": "#d9d9d9",
    "EXCESS STOCK": "#f4cccc",
    "LOW STOCK": "#fce5cd",
    "OK": "#d9ead3",
}

# Engine required columns (not the .gs file-header comment). arr.Days is optional.
REQUIRED_COLUMNS = {
    "sales": ["Date", "Party Name", "Sales Rep", "Net Amount"],
    "receipt": ["Date", "Account Name", "Sales Rep", "Amount"],
    "credit_note": [
        "SlNo", "Invoice No", "Date", "Party Name",
        "Sales Amount", "SGST", "CGST", "IGST", "Net Amount",
    ],
    "arr": ["Account Name", "Group", "Balance"],
    "items": ["Date", "Item Name", "Qty", "Rate"],
    "stock": ["Item Name", "Qty", "P.Price"],
    "payments": ["Date", "Account Name", "Amount"],
}

EXCEL_SHEET_NAMES = {
    "sales_rep_performance_report": "sales_rep_perf",
    "account_performance_report": "account_perf",
    "group_performance_report": "group_perf",
    "fiscal_monthly_sales_rep_performance_report": "fy_sales_rep",
    "fiscal_monthly_account_performance_report": "fy_account",
    "fiscal_monthly_group_performance_report": "fy_group",
    "item_wise_sales": "item_wise_sales",
    "item_wise_profit": "item_wise_profit",
    "item_cost_exceptions": "item_cost_exceptions",
    "item_wise_monthly_profit": "item_fy_profit",
    "item_wise_monthly_qty": "item_fy_qty",
    "monthly_profit_report": "monthly_pnl",
    "expense_by_category": "expense_by_category",
    "expense_by_account": "expense_by_account",
    "unmapped_payment_accounts": "unmapped_payments",
    "source_data_warnings": "warnings",
}

PROFIT_PHASES = ("profit", "expenses", "itemprofit")
PHASES = ("core", "fiscal", "items", "profit", "expenses", "itemprofit")
EXPENSE_CATEGORIES = [
    "Travel Expenses", "Courier", "Office Expenses", "Salary", "Compliance Expenses",
    "Investment Returns", "Purchase", "Other", "Bank Inward", "RD",
]
OPERATING_EXPENSE_CATEGORIES = [
    "Travel Expenses", "Courier", "Office Expenses", "Salary", "Compliance Expenses", "Other",
]
FISCAL_MONTH_NAMES = [
    "April", "May", "June", "July", "August", "September",
    "October", "November", "December", "January", "February", "March",
]
WIDE_REPORTS = {
    "fiscal_monthly_sales_rep_performance_report",
    "fiscal_monthly_group_performance_report",
    "fiscal_monthly_account_performance_report",
    "monthly_profit_report",
    "item_wise_monthly_profit",
    "item_wise_monthly_qty",
}
