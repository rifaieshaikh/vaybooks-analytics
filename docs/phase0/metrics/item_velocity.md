# item_velocity

| Field | Value |
|---|---|
| **id** | `item_velocity` |
| **owner** | Stock |
| **formula** | Quantity sold per item over recent windows (MTD / rolling months / FY) from item-wise sales |
| **date basis** | items Date |
| **exclusions** | Zero-qty lines; dates after report date |
| **sources** | items |
| **dimensions** | item |
| **drill-down grain** | Item (then line dates) |
| **if missing** | Unavailable without items source |
