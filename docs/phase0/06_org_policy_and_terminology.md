# Org policy and terminology

## Defaults (Vay-compatible)

| Key | Default | Notes |
|---|---|---|
| `fiscal_year_start_month` | `4` (April) | 1–12 |
| `timezone` | `Asia/Kolkata` | Used for “today” and report context |
| `currency_code` | `INR` | |
| `currency_symbol` | `₹` | Display / parse hints |
| `sales_tax_inclusive_rate` | `0.18` | Inclusive tax extracted from sales value in P&L |
| `expense_pack` | `vay_wholesale` | Seeds expense account map on first load |
| Terminology | see below | Display labels only in Phase 0 |

## Terminology map

| Key | Default label |
|---|---|
| `customer` | Customer |
| `party` | Party |
| `outstanding` | Outstanding |
| `sales_rep` | Sales Rep |
| `group` | Group |
| `item` | Item |

Pilots may rename labels without changing canonical field names.

## Storage

- Persisted as `app_setting` rows (same pattern as settlement / due days).
- API: `GET/POST /api/settings/org-policy`
- Expense account map: `GET/POST /api/settings/expense-categories` (seeded from pack if empty)

## Engine threading

`generate(..., org_policy=...)` passes policy into `build_report_context`, which sets:

- `fiscalYearStart` / fiscal iterators using `fiscal_year_start_month`
- `timezone`
- `sales_tax_inclusive_rate`
- `payment_categories` (expense map)
- `currency_code` / `currency_symbol` / `terminology`

## Non-goals for Phase 0

- Per-tenant database isolation
- Changing canonical column names in Mongo rows
- UI localization beyond Settings → Organization
