# slow_stock_value

| Field | Value |
|---|---|
| **id** | `slow_stock_value` |
| **owner** | Stock |
| **formula** | On-hand qty × unit cost for items with low/no recent velocity (slow/dead stock) |
| **date basis** | Stock snapshot; sales lookback for velocity |
| **exclusions** | Items below threshold velocity stay in set; missing cost → value unavailable for that item |
| **sources** | stock, items |
| **dimensions** | item |
| **drill-down grain** | Item |
| **if missing** | Line unavailable without cost; report total only over costed lines with a coverage note |
