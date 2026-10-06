# Metric catalogue (Phase 0)

Authoritative specs live in [`metrics/`](metrics/). Each metric has: id, owner, formula, date basis, exclusions, sources, dimensions, drill-down grain, and eligibility when data is missing.

| ID | Title | Owner |
|---|---|---|
| [`sales_mtd`](metrics/sales_mtd.md) | Sales MTD | Sales |
| [`sales_ytd`](metrics/sales_ytd.md) | Sales YTD (fiscal) | Sales |
| [`collections_mtd`](metrics/collections_mtd.md) | Collections MTD | Finance |
| [`collection_rate`](metrics/collection_rate.md) | Collection rate | Finance |
| [`ar_balance`](metrics/ar_balance.md) | AR balance | Finance |
| [`ar_overdue_30`](metrics/ar_overdue_30.md) | AR overdue 30+ | Finance |
| [`dso`](metrics/dso.md) | Days sales outstanding | Finance |
| [`sales_change_drivers`](metrics/sales_change_drivers.md) | Sales change drivers | Sales |
| [`inactive_customers`](metrics/inactive_customers.md) | Inactive customers | Sales |
| [`collection_priority_score`](metrics/collection_priority_score.md) | Collection priority | Finance |
| [`item_velocity`](metrics/item_velocity.md) | Item velocity | Stock |
| [`stock_cover_days`](metrics/stock_cover_days.md) | Stock cover days | Stock |
| [`slow_stock_value`](metrics/slow_stock_value.md) | Slow stock value | Stock |
| [`gross_margin`](metrics/gross_margin.md) | Gross margin | Finance |
| [`data_freshness`](metrics/data_freshness.md) | Data freshness / reconciliation | Operations |

Implementation today: several of these appear as dashboard KPIs or report columns in `vay/reports/` and `server/dashboard.py`. Phase 1 will version them as runtime manifests; Phase 0 locks the definitions.
