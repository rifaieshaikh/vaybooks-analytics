# inactive_customers

| Field | Value |
|---|---|
| **id** | `inactive_customers` |
| **owner** | Sales |
| **formula** | Customers with no qualifying sales in configured inactivity windows (existing follow-up buckets: 0–15, 15–30, 30–60, older) |
| **date basis** | Last sale date vs report date |
| **exclusions** | Credit notes do not count as a sale and do not reset inactivity. New customers inside observation window; sentinel `NO_PARTY_NAME` |
| **sources** | sales, arr/party |
| **dimensions** | sales_rep, group, inactivity bucket |
| **drill-down grain** | Customer |
| **if missing** | Unavailable without sales history |
