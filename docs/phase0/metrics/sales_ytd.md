# sales_ytd

| Field | Value |
|---|---|
| **id** | `sales_ytd` |
| **owner** | Sales |
| **formula** | Sum of sales `Net Amount` from org fiscal year start through report date, minus credit-note `Net Amount` in the same window |
| **date basis** | Sales Date and credit-note Date; FY start from org policy `fiscal_year_start_month` |
| **exclusions** | Dates after report date; invalid dates; credit notes do not reset last-sale |
| **sources** | sales, credit_note |
| **dimensions** | customer, sales_rep, group |
| **drill-down grain** | Invoice / sales row |
| **if missing** | Unavailable when sales source absent |
