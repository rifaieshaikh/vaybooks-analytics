# Overseas pilot intake template

**Status:** Template only. This folder is not a pilot.  
**Copy to:** `docs/phase0/samples/<business>/MANIFEST.md` when a business is named.  
**PII:** Sanitize names and amounts before any file is committed.

Do not add this folder to `PILOTS` in `server/pilots.py`. Edge Point, Plymax, and EFF YES Traders stay the only names that intake code walks. Header mapping for those three stays in [`../../03_source_field_matrix.md`](../../03_source_field_matrix.md). Fill the tables in the copied manifest first. Update the shared field matrix only after a real overseas export exists.

Search context: [`../../../global-support-matrix.md`](../../../global-support-matrix.md).

## Business

| Field | Value |
|---|---|
| Business | |
| Country | |
| Source system and export procedure | |
| Reporting currency | |
| Precision shown in the files | |
| Date order confirmed for ambiguous values such as 03/04/2026 | |
| Number format confirmed (`1,234.56` or `1.234,56`) | |
| Deployment choice (desktop or hosted) | |
| Consent or anonymization note | |

## Files to collect

Required: sales, receipts, and an AR or outstanding snapshot.  
Strongly preferred: item sales and stock.  
Optional: cost, tax, and payables.

Leave a row blank when the source has no file. Record that gap in Missing sources.

| File | Canonical type | Priority | Grain | Stable source ids | Date range or snapshot date | Currency and precision in the file | Units | Corrected or repeated export |
|---|---|---|---|---|---|---|---|---|
| | sales | Required | | | | | | |
| | receipt | Required | | | | | | |
| | arr | Required | | | | | | |
| | items | Strongly preferred | | | | | | |
| | stock | Strongly preferred | | | | | | |
| | cost, tax, or payables | Optional | | | | | | |

Corrected or repeated export: name the second file here when the business sends a fix or a later extract of the same period. Leave the cell blank until that file exists.

## Native headers

One row per canonical field that appears in a received file. Leave Native header blank until the file is in hand. A blank native header means the source did not provide that field.

### Sales

| Canonical field | Native header | Notes |
|---|---|---|
| Date | | |
| Party Name | | |
| Sales Rep | | |
| Net Amount | | |
| Transaction ID | | |
| Currency | | |

### Receipt

| Canonical field | Native header | Notes |
|---|---|---|
| Date | | |
| Account Name | | |
| Sales Rep | | |
| Amount | | |
| Transaction ID | | |
| Currency | | |

### AR or outstanding snapshot

| Canonical field | Native header | Notes |
|---|---|---|
| Account Name | | |
| Group | | |
| Balance | | |
| Days | | |
| Snapshot date | | |
| Currency | | |

### Item sales

| Canonical field | Native header | Notes |
|---|---|---|
| Date | | |
| Item Name | | |
| Qty | | |
| Unit | | |
| Rate | | |
| Line ID | | |

### Stock snapshot

| Canonical field | Native header | Notes |
|---|---|---|
| Item Name | | |
| Qty | | |
| Unit | | |
| Unit cost | | |
| Snapshot date | | |
| Location | | |

## Control totals

Agree the definition with the pilot before writing an amount. Leave every value blank in this template.

| Control | Period | Net or gross | Tax included (yes or no) | Agreed amount |
|---|---|---|---|---|
| Sales | | | | |
| Receipts | | | | |
| AR / outstanding | | | | |

## Missing sources

| Source | Why it is missing | Workflow it blocks |
|---|---|---|
| | | |
