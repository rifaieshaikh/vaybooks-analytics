# Sales offer: current evidence

Date: 2026-10-07

The commercial rules are in [commercial policy](commercial-policy.md). Settings → Plan and support shows the same price, status, and renewal note.

## Supported now

A desktop install uses the default organization. The license is active, included with the install, and has no renewal date and no expiry date. Opening the sample builds Vay Demo Traders with Harbour Traders, North Mill, Lane and Co, and Oak Board 18mm. Reset removes only rows marked Demo=yes, and it refuses to run after a real import.

Staff can use Today's Work, record a collection follow-up, confirm part of a promise, and download a statement after reviewing it. Reorder and weekly review each have an Excel copy. Diagnostics contain no credentials.

## Release decision

The desktop offer is approved on the terms in the commercial policy. There is no separate subscription price.

A representative Harbour Traders workbook was imported and reported. That run is not an outside customer interview.

| Observation | Result |
|---|---|
| Import and first-report preparation time | 0.287 seconds in `tests/test_sales_unblock.py` |
| Assistance needed | None |
| Failed steps | A file that is not a workbook is rejected. The valid workbook then imports. |
| Repeat use | Importing the same sales file again skipped both rows and left the original two. |
| Customer feedback | No outside company was interviewed. |
| Workflows included | Today's Work, collection follow-up, statements, reorder, and weekly review. They are included with the desktop install. |

Outstanding for Harbour Traders reconciled to 1100, matching the source balance. Sales were 1500 and the receipt was 400.

Do not claim that a follow-up caused a sale or a payment.

## Evidence

- Commercial rules: `docs/release/commercial-policy.md`
- Representative import, directory copy, and hosted pack change: `tests/test_sales_unblock.py`
- Sample, collection, and Today's Work: `tests/test_sales_demo.py`
- Statement, reorder, and management workbooks: `tests/test_sales_exports.py`
- Demo path, license text, diagnostics, and snapshot restore: `tests/test_sales_offer.py`
- Organization snapshot and database-directory copy: `docs/release/backup.md`

The directory-copy test restores a folder the way the backup guide tells an operator to restore the database directory. The organization snapshot restore is a separate API check.
