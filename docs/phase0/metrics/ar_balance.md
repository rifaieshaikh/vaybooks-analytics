# ar_balance

| Field | Value |
|---|---|
| **id** | `ar_balance` |
| **owner** | Finance |
| **formula** | Sum of outstanding `Balance` from the AR snapshot (arr), after settlement logic where used for open invoices |
| **date basis** | Snapshot as-of (import / report date); not a reconstructed historical ledger unless transactions + opening exist |
| **exclusions** | Non-customer party types if filtered; negative handling per settlement rules |
| **sources** | arr (required); sales, credit_note, and receipt for settled views |
| **dimensions** | customer, group, sales_rep, aging band |
| **drill-down grain** | Customer / open invoice |
| **if missing** | Unavailable when arr source absent |
