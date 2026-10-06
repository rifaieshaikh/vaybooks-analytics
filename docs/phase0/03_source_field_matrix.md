# Cross-pilot source field matrix

Rows = canonical fields. Columns = native headers observed (or expected) per pilot.  
Update Edge Point / Plymax / EFF YES when sample workbooks arrive.

## Legend

- Value = native header string that maps to the canonical field  
- `—` = not observed / not required for that pilot yet  
- `(blocker)` = pilot sample not received  

## Sales (event)

| Canonical | Vay | Edge Point | Plymax | EFF YES Traders |
|---|---|---|---|---|
| Date | Date | (blocker) | (blocker) | (blocker) |
| Party Name | Party Name | (blocker) | (blocker) | (blocker) |
| Sales Rep | Sales Rep | (blocker) | (blocker) | (blocker) |
| Net Amount | Net Amount | (blocker) | (blocker) | (blocker) |

## Receipt (event)

| Canonical | Vay | Edge Point | Plymax | EFF YES Traders |
|---|---|---|---|---|
| Date | Date | (blocker) | (blocker) | (blocker) |
| Account Name | Account Name | (blocker) | (blocker) | (blocker) |
| Sales Rep | Sales Rep | (blocker) | (blocker) | (blocker) |
| Amount | Amount | (blocker) | (blocker) | (blocker) |

## Outstanding / AR (snapshot)

| Canonical | Vay | Edge Point | Plymax | EFF YES Traders |
|---|---|---|---|---|
| Account Name | Account Name | (blocker) | (blocker) | (blocker) |
| Group | Group | (blocker) | (blocker) | (blocker) |
| Balance | Balance | (blocker) | (blocker) | (blocker) |
| Days (optional) | Days | (blocker) | (blocker) | (blocker) |

## Item-wise sales (event)

| Canonical | Vay | Edge Point | Plymax | EFF YES Traders |
|---|---|---|---|---|
| Date | Date | (blocker) | (blocker) | (blocker) |
| Item Name | Item Name | (blocker) | (blocker) | (blocker) |
| Qty | Qty | (blocker) | (blocker) | (blocker) |
| Rate | Rate | (blocker) | (blocker) | (blocker) |

## Stock (snapshot)

| Canonical | Vay | Edge Point | Plymax | EFF YES Traders |
|---|---|---|---|---|
| Item Name | Item Name | (blocker) | (blocker) | (blocker) |
| Qty | Qty | (blocker) | (blocker) | (blocker) |
| P.Price (unit cost) | P.Price | (blocker) | (blocker) | (blocker) |

## Credit note (event)

Sales return. `Net Amount` reduces net sales and outstanding. It is not a collection and it does not move items. `Cash` is not a field.

| Canonical | Vay | Edge Point | Plymax | EFF YES Traders |
|---|---|---|---|---|
| SlNo | SlNo | (blocker) | (blocker) | (blocker) |
| Invoice No | Invoice No. | (blocker) | (blocker) | (blocker) |
| Date | Date | (blocker) | (blocker) | (blocker) |
| Party Name | Party Name | (blocker) | (blocker) | (blocker) |
| Sales Amount | Sales Amount | (blocker) | (blocker) | (blocker) |
| SGST | SGST | (blocker) | (blocker) | (blocker) |
| CGST | CGST | (blocker) | (blocker) | (blocker) |
| IGST | IGST | (blocker) | (blocker) | (blocker) |
| Net Amount | Net Amount | (blocker) | (blocker) | (blocker) |

## Payments (event)

| Canonical | Vay | Edge Point | Plymax | EFF YES Traders |
|---|---|---|---|---|
| Date | Date | (blocker) | (blocker) | (blocker) |
| Account Name | Account Name | (blocker) | (blocker) | (blocker) |
| Amount | Amount | (blocker) | (blocker) | (blocker) |

## Grain and coverage gaps

| Topic | Vay | Other pilots |
|---|---|---|
| Invoice header vs line | Sales often header `Net Amount`; lines in `items` | TBD |
| Returns / credit notes | `credit_note` event; net sales and AR; not items | TBD |
| Historical COGS | Snapshot `P.Price` only | TBD — mark gross_margin unavailable without defensible cost |
| Receipt ↔ invoice allocation | Computed settlement, not imported ledger | TBD |
| Multi-location | Not modeled | TBD |

## Shared-model readiness

All four pilots are described by the same canonical types in [`04_shared_data_model.md`](04_shared_data_model.md). Native header fill-in for Edge Point, Plymax, and EFF YES is a **collection blocker**, not a model fork.
