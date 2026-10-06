# collection_priority_score

| Field | Value |
|---|---|
| **id** | `collection_priority_score` |
| **owner** | Finance |
| **formula** | Rank open AR by urgency: overdue amount, age band, and follow-up status (URGENT / FOLLOW UP / WATCH conventions in core follow-ups) |
| **date basis** | Report date |
| **exclusions** | Zero-balance accounts |
| **sources** | arr, sales, receipt |
| **dimensions** | customer, sales_rep, group |
| **drill-down grain** | Customer collection follow-up row |
| **if missing** | Unavailable without arr |
