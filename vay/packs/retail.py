"""Retail pack. Templates only. The expense map is empty so Vay account names are not copied."""

PACK_ID = "retail"
PACK_LABEL = "Retail"

EXPENSE_ACCOUNT_MAP = {}

TEMPLATES = (
    {
        "id": "returns_by_customer",
        "name": "Returns by customer",
        "metric_ids": ["sales_mtd"],
        "dimension": "customer",
        "comparison": "current",
        "filters": [],
        "show_pack_size": False,
        "row_filter": "returns",
        "custom_column": "",
    },
    {
        "id": "repeat_customers",
        "name": "Repeat customers",
        "metric_ids": ["sales_mtd"],
        "dimension": "customer",
        "comparison": "current",
        "filters": [],
        "show_pack_size": False,
        "row_filter": "repeat",
        "custom_column": "",
    },
)
