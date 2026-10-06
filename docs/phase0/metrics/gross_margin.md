# gross_margin

| Field | Value |
|---|---|
| **id** | `gross_margin` |
| **owner** | Finance |
| **formula** | (Sales net of inclusive tax − COGS) / Sales net of tax, when COGS is defensible |
| **date basis** | Sales / items dates within FY or selected window |
| **exclusions** | Tax extraction uses org `sales_tax_inclusive_rate` |
| **sources** | sales, items, stock (for unit cost) |
| **dimensions** | item, customer (when allocatable) |
| **drill-down grain** | Item / month |
| **if missing** | **Unavailable** when only current snapshot `P.Price` is used as historical COGS without an explicit “snapshot cost” disclosure — never present snapshot cost as audited historical COGS without label |
| **caveat** | Current engine uses stock P.Price × qty; Phase 0 marks this as provisional |
