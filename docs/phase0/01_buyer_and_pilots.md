# Buyer, operator, and pilots

Phase 0 product framing for the business analytics platform.  
Pilots: **Vay**, **Edge Point**, **Plymax**, **EFF YES Traders**.

## Buyer

**Owner / GM** of a product-selling wholesale or trading SMB who needs weekly visibility on sales, collections, and cash tied in stock.

They care that numbers reconcile to their exports, not that the product looks like a BI suite.

## Operator

**Office / admin** user who:

1. Exports Excel (or similar) from their operational system
2. Maps columns once
3. Runs Create for a report date
4. Reviews dashboards / follow-ups and assigns collection or stock actions

## Three decisions the product must improve

| # | Decision | Why it matters |
|---|---|---|
| 1 | Whom to collect from first this week | Cash and overdue risk |
| 2 | Which customers or products drove the sales change | Diagnose before reacting |
| 3 | What to reorder before stock-outs or dead stock | Working capital |

## Pilot profiles

### Vay (first / reference pilot)

| Field | Value |
|---|---|
| Segment | Wholesale / distribution |
| Systems | AppSheet → Excel export |
| Export shapes | sales, receipt, arr (outstanding), items, stock, payments, party/customer |
| Fiscal / tax defaults | Apr–Mar FY, Asia/Kolkata, INR, 18% inclusive sales tax |
| Status | Live product user; formulas and expense account names originated here |

### Edge Point

| Field | Value |
|---|---|
| Segment | Product trading / distribution (pilot) |
| Systems | To confirm from export (Excel/CSV expected) |
| Export shapes | TBD — collect sales, receipts, AR/outstanding, items/stock; payments if available |
| Status | Named pilot; representative workbook collection in progress — see [`samples/edge_point/MANIFEST.md`](samples/edge_point/MANIFEST.md) |

### Plymax

| Field | Value |
|---|---|
| Segment | Product trading / distribution (pilot) |
| Systems | To confirm from export |
| Export shapes | TBD — same canonical source types as shared model |
| Status | Named pilot; representative workbook collection in progress — see [`samples/plymax/MANIFEST.md`](samples/plymax/MANIFEST.md) |

### EFF YES Traders

| Field | Value |
|---|---|
| Segment | Trading SMB (pilot) |
| Systems | To confirm from export |
| Export shapes | TBD — same canonical source types as shared model |
| Status | Named pilot; representative workbook collection in progress — see [`samples/eff_yes_traders/MANIFEST.md`](samples/eff_yes_traders/MANIFEST.md) |

## Success baselines (method now; numeric targets after assisted onboardings)

| Measure | How to record during pilots |
|---|---|
| Time to first trusted report | Clock from first upload to decision-maker viewing a reconciled scorecard |
| Reconciliation pass rate | Share of periods where sales + AR match agreed source totals |
| Weekly active decision-makers | Distinct authorized users reviewing a report or action weekly |
| Action completion | Assigned collection / stock / data-fix actions completed by due date |

See [`07_pilot_baselines_and_gate.md`](07_pilot_baselines_and_gate.md) for the gate checklist.
