# data_freshness

| Field | Value |
|---|---|
| **id** | `data_freshness` |
| **owner** | Operations |
| **formula** | Status of last successful imports / Create run vs report date; reconciliation flag when core sales and AR totals match agreed source checks |
| **date basis** | Upload time, run time, report date |
| **exclusions** | Explorer filters do not affect official Create numbers |
| **sources** | All imported types + run metadata |
| **dimensions** | source type |
| **drill-down grain** | Import batch / run (Phase 1 provenance) |
| **if missing** | Show stale / never-imported per source type; never invent freshness |
