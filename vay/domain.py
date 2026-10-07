"""Shared business domain model (Phase 0).

Docs: docs/phase0/04_shared_data_model.md
Each stored document carries org_id. Desktop uses the default organization.
"""

from __future__ import annotations

# Logical entities (not Mongo collection names).
ENTITIES = (
    "organization",
    "customer",
    "customer_group",
    "sales_rep",
    "product",
    "invoice",
    "invoice_line",
    "receipt",
    "credit_note",
    "allocation",
    "payment",
    "ar_snapshot",
    "stock_snapshot",
    "location",
    "supplier",
    "employee",
)

# Import source types → grain + kind.
SOURCE_GRAINS = {
    "sales": {"entity": "invoice", "kind": "event", "grain": "invoice_header"},
    "receipt": {"entity": "receipt", "kind": "event", "grain": "receipt_event"},
    "credit_note": {"entity": "credit_note", "kind": "event", "grain": "credit_note"},
    "items": {"entity": "invoice_line", "kind": "event", "grain": "invoice_line"},
    "payments": {"entity": "payment", "kind": "event", "grain": "payment_event"},
    "arr": {"entity": "ar_snapshot", "kind": "snapshot", "grain": "ar_balance"},
    "stock": {"entity": "stock_snapshot", "kind": "snapshot", "grain": "stock_position"},
    "party": {"entity": "customer", "kind": "snapshot", "grain": "party_master"},
    "customer": {"entity": "customer", "kind": "snapshot", "grain": "customer_balance"},
    "reservation": {"entity": "product", "kind": "event", "grain": "reservation"},
    "incoming": {"entity": "product", "kind": "event", "grain": "incoming_stock"},
    "item_cost": {"entity": "product", "kind": "event", "grain": "item_cost"},
    "opening_cash": {"entity": "organization", "kind": "event", "grain": "opening_cash"},
    "payable": {"entity": "payment", "kind": "event", "grain": "payable"},
}

EVENT_SOURCE_TYPES = tuple(k for k, v in SOURCE_GRAINS.items() if v["kind"] == "event")
SNAPSHOT_SOURCE_TYPES = tuple(k for k, v in SOURCE_GRAINS.items() if v["kind"] == "snapshot")

# Canonical field names expected after mapping (mirrors server REQUIRED_FIELDS).
CANONICAL_FIELDS = {
    "sales": ("Date", "Party Name", "Sales Rep", "Net Amount"),
    "receipt": ("Date", "Account Name", "Sales Rep", "Amount"),
    "credit_note": (
        "Date", "Party Name", "Invoice No", "Net Amount",
        "SlNo", "Sales Amount", "SGST", "CGST", "IGST",
    ),
    "arr": ("Account Name", "Group", "Balance"),
    "items": ("Date", "Item Name", "Qty", "Rate"),
    "stock": ("Item Name", "Qty", "P.Price", "Category", "Item Group", "Brand", "Supplier"),
    "payments": ("Date", "Account Name", "Amount"),
    "party": ("Account Name", "Group"),
    "customer": ("Account Name", "Group", "Balance"),
    "reservation": ("Item Name", "Qty", "Need By"),
    "incoming": ("Item Name", "Qty", "Expected Date", "Confirmed"),
    "item_cost": ("Item Name", "Cost", "Effective Date"),
    "opening_cash": ("Date", "Amount"),
    "payable": ("Account Name", "Amount", "Due Date"),
}

METRIC_IDS = (
    "sales_mtd",
    "sales_ytd",
    "collections_mtd",
    "collection_rate",
    "ar_balance",
    "ar_overdue_30",
    "dso",
    "sales_change_drivers",
    "inactive_customers",
    "collection_priority_score",
    "item_velocity",
    "stock_cover_days",
    "slow_stock_value",
    "gross_margin",
    "data_freshness",
)
