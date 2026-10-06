# Business Analytics Platform Roadmap

**Starting point:** Vay Reports v3.0.0, as described in the product overview  
**Purpose:** Turn an AppSheet-export reporting application into a configurable business analytics product that can be sold to multiple businesses.  
**Status:** Product plan; repository implementation has not been independently reviewed.  
**Planning horizon:** 12–18 months, adjusted after external pilots.

## Product vision

Businesses should be able to import data they already export, trust the resulting metrics, understand what changed, decide what to do, assign the work, and measure the outcome.

AppSheet Excel is the first data source, and Vay is the first pilot. Neither is a required part of the eventual product. The first target segment should be product-selling small and medium businesses with invoices, receipts, customers, and stock. Add other segments through optional industry packs after the common platform proves reusable.

## Guiding product rules

1. **One definition per metric.** Dashboard, report, profile, API, and export use the same versioned metric definition.
2. **Show provenance.** Every number can be traced to source files, import batches, mappings, calculation version, and report date.
3. **Respect data grain.** Invoice headers, invoice lines, receipts, allocations, payments, stock movements, and balance snapshots are different records.
4. **Keep history honest.** Transactions are limited by their relevant dates. Outstanding and stock exports are dated snapshots; current snapshots cannot reconstruct earlier balances without suitable transaction history.
5. **No false precision.** Missing costs, unmatched receipts, incomplete periods, and stale stock are visible. Unsupported metrics are labelled unavailable, not zero.
6. **Actions complete the loop.** An insight can be assigned, resolved, and evaluated against a subsequent outcome.
7. **Configuration before customization.** Fiscal year, tax treatment, terminology, currency, units, credit policy, and thresholds belong to each organization.
8. **Secure separation.** Data, report jobs, files, exports, users, and settings remain within the owning organization.

## Target architecture

| Layer | Responsibility | Initial direction |
|---|---|---|
| Sources | Import business exports | Excel/CSV, starting with AppSheet exports; add templates and integrations based on demand |
| Import | Map, validate, deduplicate, reconcile | Versioned mapping and batch provenance; append/replace/update policies |
| Business model | Normalize common entities | Organizations, customers, products, invoices, invoice lines, receipts, allocations, locations, employees, suppliers, snapshots |
| Metrics | Govern business calculations | Versioned definitions, eligibility rules, dimensions, and calculation explanations |
| Analytics | Compare and diagnose | Trends, cohorts, price-volume drivers, aging, stock cover, opportunities, forecasts |
| Experience | Present and act | Dashboards, 360 profiles, templates, report builder, assignments, exports |
| Operations | Run reliably | Durable jobs, audit trail, backups, restoration, migrations, monitoring |

Preserve the existing Python engine where it remains useful. Move Vay-specific policy into configuration or a wholesale pack. Keep exploratory filters separate from official run calculations; introduce explicitly scoped official runs only when their scope is saved and prominently labelled.

## Report catalogue

Each report needs an owner, formula, source requirements, date basis, comparison period, dimensions, drill-down, and a decision it supports.

### Executive and business health

| Report | Question answered | Minimum source data |
|---|---|---|
| Business scorecard | Are revenue, margin, collections, receivables, and inventory improving? | Sales, receipts; other sources conditional |
| Period comparison | How do current period, prior period, prior year, and target compare? | Dated transactions; optional targets |
| Change explanation | Which customers, products, prices, quantities, or locations caused a movement? | Invoice lines with stable entities |
| Cash and working capital | How much cash is tied up in receivables and inventory? | Comparable dated AR and stock balances |
| Management exceptions | What requires attention now? | Quality rules, targets, overdue invoices, inventory policies |

### Sales and customers

| Report | Question answered | Important caveat |
|---|---|---|
| Sales trend and mix | Where is growth or decline occurring? | Decide whether sales means order, delivery, or invoice |
| Price-volume bridge | Did value change through quantity, price, or mix? | Needs comparable items and units |
| New/repeat/inactive/reactivated customers | Who joined, stayed, left, or returned? | Define customer identity and observation window |
| Buying frequency | Whose usual ordering cycle is overdue? | Requires enough history to establish a pattern |
| Customer concentration | How dependent is revenue on top accounts? | Handle related customer entities deliberately |
| Returns and discounts | Where is invoice value lost? | Requires return/credit-note and discount fields |
| Rep/channel/location performance | Where is performance changing? | Assignment and territory history may change |

### Receivables and collections

| Report | Question answered | Minimum source data |
|---|---|---|
| Invoice aging | Which invoices are open and how overdue are they? | Invoice, due date, receipt allocation or reconcilable ledger |
| Payment behaviour | Who pays late or inconsistently? | Invoice and settlement history |
| Collection priority | Who should be contacted first? | Open invoices, recent activity, ownership |
| Promise tracking | Did the customer pay as promised? | Recorded promises and receipts |
| AR movement | Why did outstanding rise or fall? | Opening/closing snapshots plus transactions |
| Expected receipts | What may arrive over the next weeks? | Payment history, open items, recorded promises |

### Product, stock, and purchasing

| Report | Question answered | Minimum source data |
|---|---|---|
| Item velocity | Which products sell steadily, seasonally, or rarely? | Dated item sales |
| Stock cover | How long could current stock last? | Recent demand and dated on-hand quantity |
| Slow/dead stock | Which items tie up cash? | Stock position, cost, sales history |
| Inventory turnover | How efficiently is stock used? | Historical stock values and appropriate cost of sales |
| Reorder proposal | What, when, and how much should be purchased? | Demand, stock, lead time, pack size, order constraints |
| Supplier reliability | How predictable are delivery and price? | Purchase orders, expected/actual receipt dates, prices |

### Profit, expenses, and cash

| Report | Question answered | Minimum source data |
|---|---|---|
| Gross margin | Which products and customers are profitable? | Historical selling value and defensible historical cost |
| Margin bridge | Did cost, price, discounts, or mix change profit? | Consistent costs and item-level sales |
| Expense trend | Which expense categories are growing? | Categorized expense transactions |
| Contribution by customer/order | Does revenue cover attributable costs? | Clearly allocated variable costs |
| Cash outlook | Can planned payments and purchases be funded? | Cash position, due receivables/payables, commitments |

Payments are cash movements and do not automatically form an accrual profit-and-loss statement. Current product purchase price must not silently become historical cost of goods sold.

### Industry packs

| Pack | Examples |
|---|---|
| Wholesale/distribution | Territory and rep performance, credit exposure, supplier-ready purchase orders, pack rounding |
| Retail/e-commerce | Basket combinations, repeat buying, channel mix, returns |
| Services | Project margin, billable utilisation, client retention, unbilled work |
| Manufacturing | Material consumption, production yield, work-in-progress, job costing |

## Phased delivery

Ranges are planning estimates for a small focused team, not commitments. Progress depends on release gates rather than calendar alone.

### Phase 0 — Product definition and external pilot design (weeks 1–3)

**Deliverables**

- Define the initial buyer, operator, and three decisions the product must improve.
- Collect representative exports from Vay and at least two other businesses with differing formats.
- Catalogue current Vay-specific assumptions, report formulas, required fields, and configuration points.
- Define 10–15 common metrics, including dates, exclusions, source requirements, and drill-down grain.
- Design neutral terminology and configurable fiscal year, currency, tax, units, and credit rules.
- Establish pilot baselines for onboarding time, reconciliation, usage, and action completion.

**Gate:** The shared data model describes all pilot businesses without hard-coded business names or one-off report code.

### Phase 1 — Trusted data foundation (weeks 4–10)

**Deliverables**

- Import-batch provenance: source, file hash, upload time, effective date, row counts, and mapping version.
- Append, replace-batch, replace-period, and update-by-key import modes with previews and rollback.
- Canonical entity IDs with alias resolution and a review queue for uncertain matches.
- Distinct transaction and snapshot models; as-of eligibility rules for each metric.
- Reconciliation checks, data freshness, exception severity, and affected-report indicators.
- Versioned metric definitions and report-run manifests recording data and calculation versions.
- Regression fixtures from multiple businesses, including returns, duplicate imports, partial receipts, and missing costs.

**Gate:** Repeat imports are controlled; headline sales and AR reconcile with each pilot's source; an earlier report can be reproduced and explained.

### Phase 2 — Sellable core analytics (weeks 11–18)

**Deliverables**

- Executive scorecard with current, prior-period, prior-year, and target comparisons where data permits.
- Sales change explanation and customer movement reports.
- Invoice-level aging and prioritized collection worklist.
- Item velocity, stock cover, and slow-stock analysis.
- Data-quality dashboard with guided fixes.
- Saved views, drill-down, exports, and organization-specific access controls.
- Guided onboarding that previews what can and cannot be calculated from each import.

**Gate:** A pilot business can onboard with assistance, reconcile its core metrics, explain a major change, and identify three practical actions without developer intervention.

### Phase 3 — Action and planning workflows (weeks 19–26)

**Deliverables**

- Weekly management review: what changed, why, owner, proposed action, and due date.
- Assignable follow-ups for collections, customer recovery, purchasing, and data corrections.
- Outcome tracking for money recovered, customers reactivated, and stock risks resolved.
- Editable reorder proposals with lead time, pack size, minimum quantity, supplier, and budget constraints.
- Targets, thresholds, and scheduled generation where supported by deployment mode.

**Gate:** Pilot users complete actions inside the product and can inspect their subsequent outcomes.

### Phase 4 — Custom analytics and wholesale pack (months 7–10)

**Deliverables**

- Report builder over governed metrics and dimensions, with filters, groupings, comparisons, and schedules.
- Reusable report templates and optional custom fields.
- Wholesale/distribution pack tested with Vay and another distributor.
- Dataset/API export for customers with external BI needs.
- Governance for custom metrics: ownership, approval, dependencies, versioning, and visibility.

**Gate:** A new customer can configure its own report and adopt the pack without a code change.

### Phase 5 — Broader market and deployment (months 10–18)

Prioritize by paying-customer demand:

- More import templates and direct integrations.
- A second industry pack, such as retail or services.
- Forecasts and scenarios with visible assumptions and uncertainty.
- Multi-location and multi-entity consolidation.
- Hosted SaaS with explicit tenant isolation, if demand justifies operating it.
- Natural-language questions restricted to approved metrics, with traceable source calculations.

**Gate:** Onboarding and support effort per new customer decline as the customer count grows.

## Cross-cutting release work

| Area | Required work |
|---|---|
| Security | Organization isolation, server-side authorization for every view/job/export, session controls, audit events, secure desktop renderer configuration |
| Reliability | Durable jobs, retries, idempotent imports, progress, cancellation, restart recovery, backup and tested restore |
| Performance | Indexes by organization/date/entity; bounded queries; pagination; precomputed snapshots where needed; load tests with realistic imports |
| Commercial desktop | Installer upgrades, database migration and recovery, support diagnostics, signed releases, third-party license review |
| Hosted option | Tenant model, automated deployment, monitoring, backup/restore, rate limits, billing and entitlement controls |
| Quality | Formula parity where intentional, reconciliation fixtures, permission tests, historical as-of tests, import replacement tests |
| Usability | Plain-language metric definitions, drill-through to source rows, freshness labels, accessible tables and charts |

Review the bundled MongoDB Community licensing approach before commercial desktop distribution; assess the Electron security checklist. For heavy background computation at scale, evaluate a durable worker rather than relying solely on in-process API tasks.

## Product success measures

| Measure | Definition to instrument | Why it matters |
|---|---|---|
| Time to first trusted report | Time from first upload to a reconciled report viewed by a decision-maker | Onboarding value |
| Reconciliation pass rate | Share of pilot periods whose core figures match agreed source totals | Trust |
| Weekly active decision-makers | Distinct authorized people reviewing a report or action weekly | Operational adoption |
| Action completion | Assigned actions completed by due date | Insight to execution |
| Action outcome | Verified receipts, reactivated customers, or resolved stock risks linked to actions | Business impact |
| Configuration-only onboarding | Share of new customers onboarded without code changes | Product repeatability |
| Support effort per customer | Staff hours for onboarding and recurring support | Commercial scalability |

Set numeric targets after observing external pilots; do not invent benchmarks from Vay alone.

## First ten implementation epics

1. Neutral organization model, terminology, and configurable policies.
2. Canonical entities and transaction grains.
3. Import provenance, replacement modes, and dated snapshots.
4. Reconciliation and data-quality dashboard.
5. Versioned metrics and reproducible report manifests.
6. Sales change and price-volume explanation.
7. Customer movement and buying-cycle analytics.
8. Invoice-level collection priorities.
9. Item velocity, stock cover, and purchasing proposals.
10. Weekly management review with assigned actions and outcomes.

## Sources informing architectural choices

- Microsoft Learn, [star schema and explicit measures](https://learn.microsoft.com/en-us/power-bi/guidance/star-schema).
- Microsoft Learn, [multitenant tenancy models](https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/considerations/tenancy-models).
- Oracle NetSuite, [workbook and dataset templates](https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_0801122351.html).
- FastAPI, [background tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/).
- Electron, [security guidance](https://www.electronjs.org/docs/latest/tutorial/security).
- MongoDB, [Community Edition licensing](https://www.mongodb.com/legal/licensing/community-edition).
