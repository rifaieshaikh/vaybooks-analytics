# stock_cover_days

| Field | Value |
|---|---|
| **id** | `stock_cover_days` |
| **owner** | Stock |
| **formula** | On-hand qty ÷ recent average daily demand (from item sales); optional holding policy overlays |
| **date basis** | Stock snapshot as-of; demand from dated items |
| **exclusions** | Discontinued items per holding flags; zero demand → cover unavailable or infinite (label explicitly) |
| **sources** | stock, items |
| **dimensions** | item |
| **drill-down grain** | Item |
| **if missing** | Unavailable without stock qty or demand history |
