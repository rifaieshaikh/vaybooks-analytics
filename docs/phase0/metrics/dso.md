# dso

| Field | Value |
|---|---|
| **id** | `dso` |
| **owner** | Finance |
| **formula** | Approximate days sales outstanding from AR balance and recent average daily sales, net of credit notes (dashboard convention) |
| **date basis** | Report date; sales lookback window as implemented in dashboard |
| **exclusions** | Periods with zero sales in lookback → unavailable |
| **sources** | arr, sales, credit_note |
| **dimensions** | org-level; optional group |
| **drill-down grain** | Supporting sales and AR rows |
| **if missing** | Unavailable when sales lookback or AR missing |
