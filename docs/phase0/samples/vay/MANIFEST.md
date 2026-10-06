# Sample exports — Vay

**Pilot:** Vay  
**Status:** Schema samples present (header-only CSVs mirroring product required fields). Replace with sanitized full-period extracts when available for reconciliation fixtures.  
**PII:** No customer names or amounts in these header stubs.  
**Source system:** AppSheet Excel export  

## Sheets

| File | Canonical type | Grain | Columns (canonical) |
|---|---|---|---|
| `sales.csv` | sales | Invoice header (typical) | Date, Party Name, Sales Rep, Net Amount |
| `receipt.csv` | receipt | Receipt event | Date, Account Name, Sales Rep, Amount |
| `arr.csv` | arr | AR snapshot | Account Name, Group, Balance |
| `items.csv` | items | Invoice line / item sale | Date, Item Name, Qty, Rate |
| `stock.csv` | stock | Stock snapshot | Item Name, Qty, P.Price |
| `payments.csv` | payments | Payment / expense event | Date, Account Name, Amount |
| `party.csv` | party | Party master snapshot | Account Name, Group |
| `customer.csv` | customer | Customer snapshot | Account Name, Group, Balance |

## Notes

- Optional ARR column `Days` is supported by the engine but not required.
- Expense category names for Vay live in the seeded pack `vay_wholesale` (not in formula modules).
- Date range for full extracts: record here when a real sanitized workbook is added.
