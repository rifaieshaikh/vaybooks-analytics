# collections_mtd

| Field | Value |
|---|---|
| **id** | `collections_mtd` |
| **owner** | Finance |
| **formula** | Sum of receipt `Amount` in calendar month through report date, for **customer** Account Names only, excluding receipts attributed to the investment/sentinel rep (`DEFAULT_RECEIPT_REP`, typically `INVESTMENT`) |
| **date basis** | Receipt Date |
| **exclusions** | Non-customer parties; investment/sentinel rep receipts; dates after report date |
| **sources** | receipt |
| **dimensions** | customer (Account Name), sales_rep |
| **drill-down grain** | Receipt row |
| **if missing** | Unavailable when receipt source absent |
