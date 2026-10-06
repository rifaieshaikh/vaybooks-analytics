# Vay assumption catalogue

Extracted from the v3.0.0 codebase. Each item is marked **org policy**, **industry pack**, or **retire**.

## Required fields (canonical import)

Source: [`server/settings.py`](../../server/settings.py) `REQUIRED_FIELDS` / [`vay/config.py`](../../vay/config.py) `REQUIRED_COLUMNS`.

| Source type | Required fields | Disposition |
|---|---|---|
| sales | Date, Party Name, Sales Rep, Net Amount | **org policy** (canonical names; mappers already remap) |
| receipt | Date, Account Name, Sales Rep, Amount | **org policy** |
| credit_note | Date, Party Name, Invoice No, Net Amount | **org policy** (SlNo, Sales Amount, SGST, CGST, IGST stored; Cash ignored) |
| arr | Account Name, Group, Balance | **org policy** (Days optional) |
| items | Date, Item Name, Qty, Rate | **org policy** |
| stock | Item Name, Qty, P.Price | **org policy** |
| payments | Date, Account Name, Amount | **org policy** |
| party | Account Name, Group | **org policy** |
| customer | Account Name, Group, Balance | **org policy** |

## Hard-coded policy (before Phase 0)

| Assumption | Location | Disposition |
|---|---|---|
| Fiscal year 1 Apr – 31 Mar | `vay/dates.py` `fiscal_year_start` | **org policy** (`fiscal_year_start_month`) |
| Timezone Asia/Kolkata; today = IST | `vay/dates.py` | **org policy** (`timezone`) |
| Inclusive sales tax 18% | `vay/config.py` `SALES_TAX_INCLUSIVE_RATE` | **org policy** (`sales_tax_inclusive_rate`) |
| Expense account → category name map (Vay people, banks, vendors) | Was `PAYMENT_CATEGORIES` in `vay/config.py` | **industry pack** (`vay_wholesale` seed) |
| Receipt rep `INVESTMENT` excluded from collections | `vay/config.py` `DEFAULT_RECEIPT_REP` | **org policy** / pack default |
| Collection only on customer Account Names | `ctx.customer_accounts` from customer + party type `customer` | **hard rule** |
| Defaults `NO_REP`, `NO_PARTY_NAME`, `NO_GROUP` | `vay/config.py` | **org policy** (keep neutral sentinels) |
| Skip Excel “Total” name rows | `server/ingest.py` | **org policy** (import hygiene) |
| COGS = current stock `P.Price` × qty | items/profit reports | Keep with **no false precision**: label historical cost unavailable when only snapshot cost exists |
| Follow-up bands (0–15 / 15–30 / 30–60; URGENT 30+) | `vay/reports/core.py` | **org policy** (later; aging bands already configurable) |
| Currency symbol ₹ strip in dashboard | `server/dashboard.py` | **org policy** (`currency_symbol`) |
| Product branding “Vay Reports” | README / UI | **retire** from shared model docs; keep product name until rebrand |

## Already configurable (retain)

| Surface | Where |
|---|---|
| Column mappers + unique keys | Settings / Import |
| Settlement mode + aging bands | Settings → Settlement |
| Due days (global + overrides) | Settings → Due days |
| Order-check policy | Settings → Order check |
| Party types | Settings → Party types |
| Item holding (min/fill/lead) | Items 360 |
| Users / roles / permissions | Settings |

## Event vs snapshot

| Kind | Types | Import behaviour today |
|---|---|---|
| Event | sales, receipt, credit_note, items, payments | Append / UK clash handling |
| Snapshot | arr, stock, party, customer | Collapse / upsert by UK |

Disposition: keep distinction as **shared model law** (not Vay-specific).

## Report packs (formula homes)

| Pack | Reports | Notes |
|---|---|---|
| core | Rep / account / group performance; sales & collection follow-ups | Keep; metric specs version later |
| fiscal | FY monthly by rep / account / group | Uses org FY start |
| items | Item-wise sales, cost exceptions, monthly qty | |
| profit | P&L, expenses, item profit | Tax rate + expense map from policy/pack |

## Terminology to neutralize

| Current label | Neutral default | Configurable? |
|---|---|---|
| Party Name | Customer / Account | Yes (terminology map) |
| ARR | Outstanding | Yes |
| Sales Rep | Sales rep | Yes |
| Group | Customer group | Yes |
| P.Price | Unit cost | Canonical field rename later; mapper alias now |
