# sales_change_drivers

| Field | Value |
|---|---|
| **id** | `sales_change_drivers` |
| **owner** | Sales |
| **formula** | Explain period-over-period net sales movement by customer, product, and (when units comparable) price vs volume vs mix. Net sales subtract credit notes on the credit-note date. |
| **date basis** | Current period vs prior period / prior year ending at report date |
| **exclusions** | Entities without stable identity; non-comparable units excluded from price-volume |
| **sources** | sales, credit_note; items required for product / price-volume |
| **dimensions** | customer, product, location (if present) |
| **drill-down grain** | Customer or item contribution rows |
| **if missing** | Customer-only driver list if items absent; price-volume **unavailable** without comparable item qty/rate |
| **readiness** | Partial today (performance reports); full bridge is Phase 2 |
