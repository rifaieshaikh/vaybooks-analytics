# collection_rate

| Field | Value |
|---|---|
| **id** | `collection_rate` |
| **owner** | Finance |
| **formula** | `collections_mtd / sales_mtd` for the same window (or paired period windows on the dashboard). `sales_mtd` is net of credit notes. Credit notes are not added to collections. |
| **date basis** | Same as component metrics |
| **exclusions** | Inherited from sales_mtd and collections_mtd |
| **sources** | sales, credit_note, receipt |
| **dimensions** | optional: sales_rep, group |
| **drill-down grain** | Component sales and receipt rows |
| **if missing** | Unavailable if either component unavailable or sales_mtd is 0 (show n/a, not 0%) |
