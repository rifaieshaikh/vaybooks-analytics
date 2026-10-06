# Shared data model

Code mirror: [`vay/domain.py`](../../vay/domain.py) (entities, grains, source-type mapping).

## Principles

1. One organization owns its imported rows. `org_id` isolates organizations. A desktop install uses the default organization.
2. Events and snapshots are different grains; snapshots cannot invent past balances.
3. Canonical field names are stable; native headers map via mappers.
4. Missing cost / incomplete periods → metric **unavailable**, not zero.

## Entities

| Entity | Description | Typical sources |
|---|---|---|
| Organization | Policy: FY, timezone, currency, tax, terminology, expense map | Settings (not an import sheet) |
| Customer / Party | Buyer account | party, customer, sales Party Name, receipt Account Name, arr |
| CustomerGroup | Territory / grouping | arr/party Group |
| SalesRep | Attribution for sales and collections | sales/receipt Sales Rep |
| Product / Item | Stock-keeping unit | items, stock |
| Invoice | Sales document (header) | sales |
| InvoiceLine | Item quantities and rates | items |
| Receipt | Cash/collection event | receipt |
| CreditNote | Sales-return credit; reduces net sales and AR, not collections or items | credit_note |
| Allocation | Computed settlement of receipts to invoices | derived (settlement engine) |
| Payment | Cash-out / expense / bank movement | payments |
| ArSnapshot | Outstanding balances as-of | arr, customer |
| StockSnapshot | On-hand qty and unit cost as-of | stock |
| Location | Optional site | not imported yet |
| Supplier | Optional vendor | may appear as payment account names |
| Employee | Optional | may appear as payment salary accounts |

## Source types and grain

| Source type | Grain | Kind |
|---|---|---|
| sales | Invoice header (amount) | event |
| receipt | Receipt event | event |
| credit_note | Credit note (sales return) | event |
| items | Invoice line / item movement | event |
| payments | Payment / expense event | event |
| arr | AR balance snapshot | snapshot |
| stock | Stock position snapshot | snapshot |
| party | Party master snapshot | snapshot |
| customer | Customer + balance snapshot | snapshot |

## Relationships (logical)

```text
Organization
  └── Customer ── CustomerGroup
  │      └── Invoice ── InvoiceLine ── Product
  │      └── Receipt ── Allocation ── Invoice
  │      └── CreditNote (reduces Invoice remainder; not a Receipt)
  │      └── ArSnapshot (dated)
  └── SalesRep (on Invoice / Receipt)
  └── Product ── StockSnapshot (dated)
  └── Payment (categorized via expense map)
```

## As-of eligibility

| Data | Valid for |
|---|---|
| Dated sales / receipts / credit notes / items / payments | Period metrics ending at report date |
| AR snapshot | Outstanding **as of snapshot date** (treat import effective date carefully in Phase 1) |
| Stock snapshot | Cover / slow stock **as of snapshot**; not historical stock series |

## What is explicitly out of the core model (packs later)

- Purchase orders and supplier reliability
- Manufacturing WIP / BOM
- Multi-entity consolidation
- Imported allocation ledgers (until a pilot supplies them)
