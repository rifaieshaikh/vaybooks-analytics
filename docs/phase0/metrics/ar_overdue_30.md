# ar_overdue_30

| Field | Value |
|---|---|
| **id** | `ar_overdue_30` |
| **owner** | Finance |
| **formula** | Portion of open AR with age ≥ 30 days using configured aging bands / due dates |
| **date basis** | Report date vs invoice/due date or aging allocation |
| **exclusions** | Not-yet-due balances |
| **sources** | arr, sales, receipt; due-days settings |
| **dimensions** | customer, group, aging band |
| **drill-down grain** | Customer / invoice |
| **if missing** | Unavailable without arr + enough sales history to age |
