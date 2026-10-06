# sales_mtd

| Field | Value |
|---|---|
| **id** | `sales_mtd` |
| **owner** | Sales |
| **formula** | Sum of sales `Net Amount` where invoice date is between calendar month start and report date, minus credit-note `Net Amount` dated in the same window |
| **date basis** | Invoice / sales Date and credit-note Date; compared to report date |
| **exclusions** | Rows with missing/invalid dates; dates after report date; credit notes are not collections |
| **sources** | sales, credit_note |
| **dimensions** | customer, sales_rep, group |
| **drill-down grain** | Invoice / sales row |
| **if missing** | Unavailable (do not show 0) when sales source absent |
