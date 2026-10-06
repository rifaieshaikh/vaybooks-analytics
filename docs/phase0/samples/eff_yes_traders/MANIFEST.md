# Sample exports — EFF YES Traders

**Pilot:** EFF YES Traders  
**Status:** BLOCKER — representative workbook not yet received.  
**PII:** N/A until files arrive; sanitize names and amounts before commit.  

## Expected canonical coverage

Collect at least:

| Priority | Canonical type | Purpose |
|---|---|---|
| Required | sales | Sales / invoices |
| Required | receipt | Collections |
| Required | arr or equivalent outstanding | AR snapshot |
| Strongly preferred | items | Line-level sales |
| Strongly preferred | stock | On-hand qty and cost |
| Optional | payments | Expenses / cash out |

## When files arrive

1. Place sanitized CSVs or a note pointing to a redacted xlsx in this folder.
2. Fill native header → canonical field mapping in [`../../03_source_field_matrix.md`](../../03_source_field_matrix.md).
3. Update this manifest: sheets, columns, date range, PII handling.
4. Clear the BLOCKER status.

The product path (scorecard, three actions, wholesale pack approval) is covered by `tests/test_roadmap_close.py`. That test is not a substitute for this workbook.
