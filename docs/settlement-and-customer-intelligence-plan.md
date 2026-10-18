# Settlement and customer intelligence implementation plan

Date: 2026-10-17  
Status: Phases 0–7 are implemented. A recovery forecast is released only after
completed collection periods pass the recorded backtest. Assigned targets and
promises stay usable without that forecast.

## Outcome and scope

Provide consistent answers to: what each customer owes, what their receipts
settled, how they pay and buy, whom staff should contact, and how much cash to
target collecting. All application modules must consume the same versioned
settlement result. Keep inferred allocation distinct from confirmed evidence.
Import customer and stock opening positions, deriving missing customer openings
from available evidence but never deriving stock openings. Add item-wise purchase
imports and verify changes over a selected duration against dated
closing checkpoints. A reconstruction with incomplete evidence remains estimated
or unresolved; creating a record does not make its balance verified.

This is an application-wide shared service with source adapters. External
systems can supply the same contracts; connecting or replacing their accounting
ledgers is outside this plan. Sales exports establish invoiced purchases, not
order creation, unless actual order records are supplied.

## Agreed decisions and execution defaults

These decisions incorporate the final conversation and supersede any earlier
suggestion of reconstructing stock openings or a separate future-advance automation.

| Topic | Required behavior |
|---|---|
| Customer opening | Import if supplied; otherwise attempt signed derivation from available transactions and a dated ARR checkpoint. Disclose missing evidence; do not invent old invoice detail. |
| Stock opening | Import only. Do not reconstruct or estimate even if purchases and closing stock exist. |
| Purchases | Support item-wise purchase imports; count received goods once as physical inward. |
| Report readiness | Always assess customer/stock openings and movement coverage before generating dependent reports. Missing stock openings do not block independent sales or current-stock views. |
| No receipt references | Opening-first, invoice-issue-date FIFO within the customer account; label allocations inferred. |
| Explicit unresolved reference | Preserve and flag; no silent unrelated FIFO fallback. |
| Negative ARR | Report net customer advance and reconcile it to existing credits without generating a duplicate receipt or advance. |
| Future invoices | No prediction, background future-invoice allocation or new automation. Use only imported transactions effective through the report cutoff. Carry unused credit; replay eligible settlement when later data is imported or a new report is generated. Preserve explicit restrictions. |
| Aging | Separate invoice age from days overdue; unknown opening dates stay unknown. |
| Cash outcome | Keep receipt cash separate from credit notes and other non-cash debt reductions. |
| Historical results | Version new calculations and preserve existing saved report snapshots. |

No further business decision is required to begin Phases 0–2. Resolve routine schema,
API and UI details within these rules and record them alongside the implementation.
Phase 0 is an implementation deliverable, not a request to reopen agreed policies.
Optional policy extensions (such as due-date-priority allocation or actual order
imports) must not delay the agreed FIFO/specific baseline.

## Existing foundations

| Area | Existing code | Main change needed |
|---|---|---|
| Settlement | `vay/settlement.py` | Chronological ledger, opening credits, unresolved references, reversals, evidence |
| Customer profiles and ordering | `server/customers.py` | Consume shared historical settlement instead of reconstructing separately |
| Analytics and quality | `server/phase2.py`, `vay/phase2.py`, `vay/eligibility.py` | Coverage-aware metrics and common balance basis |
| Collection follow-up | `server/collection.py` | Separate invoice allocation from promise attribution; cash from non-cash resolution |
| Daily work and review | `server/worklist.py`, `server/actions.py` | Common targets, unique attribution, evidence-aware outcomes |
| Cash planning | `server/cash.py` | Clearly identified planned inflows and recovery target integration |
| Buying and credit checks | `server/repurchase.py`, `server/order_check.py` | Coverage-aware behavior and historical exposure |
| Reports and persistence | `server/jobs.py`, `server/run_views.py`, `server/view_parts.py`, `server/store.py` | Versioned results, immutable historical snapshots, migration |

## Delivery sequence

| Phase | Deliverable | Dependency |
|---|---|---|
| 0 | Agreed contracts, formulas and acceptance fixtures | None |
| 1 | Customer opening derivation, stock opening/purchase imports, preflight and coverage | Phase 0 |
| 2 | Deterministic settlement engine | Phases 0–1 |
| 3 | Persistence, shadow comparison and application-wide integration | Phase 2 |
| 4 | Customer payment intelligence | Phase 3 |
| 5 | Weekly collection targets and outcomes | Phase 3; uses Phase 4 when available |
| 6 | Buying intelligence and credit recommendations | Phase 3; payment context from Phase 4 |
| 7 | Recovery forecasting and production acceptance | Phase 5 outcome history; Phases 4–6 acceptance |

Do not release new payment-delay or recovery metrics before the common settlement
and coverage gates pass. Forecasts are optional and must not block reliable
balances, worklists or explicit collection targets. Assign owners and estimates
after Phase 0 fixtures and migration volumes are known.

## Phase 0 — Define the accounting and product contracts

- [x] Define debit items, credit items, allocation links, reversals, balance
  checkpoints, opening items and source coverage records.
- [x] Define customer opening balances and stock opening quantities/value as separate
  dated contracts. Stock identity includes location, unit of measure and lot where
  supplied; distinguish on-hand inventory from reservations and expected incoming.
- [x] Scope each account by organization, legal entity, stable customer ID and
  currency. Specify adapters and approved aliases; prohibit implicit cross-account
  or cross-currency settlement.
- [x] Define decimal money precision, source IDs, deterministic ordering, invoice
  matching keys and same-day ordering when source timestamps are absent.
- [x] Define policy versions: invoice-date FIFO, due-date priority and explicit-only.
  Default referenced-receipt remainders to unapplied; no silent unrelated fallback.
- [x] Define allocation evidence (source-confirmed, manually confirmed, inferred),
  balance reconciliation state, coverage state and unknown-age debt independently.
- [x] Define invoice age versus days overdue. Due date is source-provided or derived
  from effective-dated credit terms; retain the terms used for each calculation.
- [x] Specify separate measures for cash receipts, non-cash debt reduction, invoice
  settlement, promise fulfilment and action attribution.
- [x] Create hand-calculated fixtures covering the scenario matrix below.

Exit gate: formulas, policies and expected fixture outputs are reviewable before
implementation. No opaque customer reliability score or arbitrary recovery rate.

## Phase 1 — Import trustworthy opening positions and coverage

- [x] Add opening unpaid invoices with remaining amounts, dates/due dates and
  references; opening credits; and aggregate opening balances with unknown details.
- [x] Add dedicated customer-opening and stock-opening import types, reusable mappings,
  templates, preview and corrections. Customer openings carry signed balances/currency;
  stock openings carry quantity/unit/location, optional cost/value and valuation basis.
  Preserve supplied invoice-level openings rather than replacing them with aggregates.
- [x] Declare the coverage boundary per account/scope. Prevent overlap between
  opening items and imported historical invoices or receipts.
- [x] Define an opening as the position immediately before the coverage start; include
  events from that start through the closing cutoff exactly once. Preserve effective
  date, scope, origin, source checkpoint, formula, assumptions and calculation version.
  Support different coverage starts explicitly; do not silently combine incompatible
  item/customer periods into a company-wide duration comparison.
- [x] Record complete-through date, coverage start, branch/account scope, explicit
  completeness declaration and optional source control totals per import.
- [x] Add preview validation for duplicate IDs, ambiguous accounts, reused invoice
  numbers, invalid currencies and conflicting opening totals.
- [x] Allow a reconstructed signed opening only when the closing checkpoint and
  all relevant period movements are complete. Retain evidence and label it inferred.
- [x] When imported customer openings are absent, automatically attempt customer
  reconstruction from the available data using the rules below. Persist a versioned
  result with verified/imported, reconstructed, estimated or unresolved status; never
  fill a missing opening with an unexplained zero or balancing adjustment.
- [x] Stock openings must be imported, never reconstructed or estimated. Add item-wise
  purchase report imports and normalization as specified below; absent stock openings
  remain unresolved for duration-based inventory verification.
- [x] Treat missing opening evidence as unknown, not zero. Do not infer export
  completeness from its upload time or latest receipt date.
- [x] Preserve corrected-import lineage and existing undo/reimport behavior.

Exit gate: every customer/item in the report scope has an opening assessment and
coverage boundary; reconstructable customer openings are created before dependent reports.
Unresolved openings identify missing evidence and disable only unsupported outputs.
Missing old invoice details do not create fabricated aging.

### Opening reconstruction rules

Customer reconstruction uses a reliable closing net receivable and complete actual
movements over the same account, currency and duration:

```text
Opening net receivable = closing net receivable - debit movements + credit movements
```

Include invoices, debit/credit adjustments, receipts, refunds and reversals with their
correct signs. Keep negative openings as customer credits. Aggregate reconstruction
does not establish the identity or age of old invoices. Preserve separate gross debt
and credits when supplied; a net checkpoint alone cannot establish both.

Stock openings must come from an imported opening stock report. Roll forward using
actual posted movements; do not solve backwards to create an opening:

```text
Calculated closing quantity = imported opening quantity + actual inbound quantity - actual outbound quantity
```

Include purchases/receipts, sales/issues, customer and supplier returns, location
transfers, production/conversions, losses and count adjustments where applicable.
Normalize units, preserve location/lot scope and count each movement once. Expected
incoming and reservations are planning records, not actual stock movements. A credit
note does not prove a physical return. Do not assume every sales line equals a stock
issue unless the adapter's source contract establishes that relationship.

Opening stock value must also be imported when value comparisons are required.
Agree a valuation method and retain historical value movements. Current purchase
price alone cannot establish historical opening value or exact cost of sales.

If stock openings are missing, request the import and create an unresolved assessment,
not a numeric estimate. Current stock and supported sales/purchase reports can still
be viewed independently; opening-to-closing verification is unavailable.

### Item-wise purchase report support

- [x] Add `purchases` as a dedicated event source across domain/settings, mappings,
  unique keys, uploads, preview, persistence, permissions, cleanup and backup/restore.
- [x] Map purchase date, item identity, quantity/unit, supplier, purchase invoice or
  source line ID, cost/rate and amount; support location, receipt date/status and
  explicit supplier-return references where available. Define genuinely required
  fields per adapter and distinguish missing cost from zero cost.
- [x] Use stable document/line identity for deduplication; retain multiple legitimate
  same-item lines and correction/reversal lineage.
- [x] Distinguish invoiced purchases from received goods. Count stock inward only
  when the source contract confirms receipt; avoid counting both invoice and goods
  receipt as separate inward movements. Expected incoming remains separate.
- [x] Connect received purchases to stock movement bridges and supplier/item analysis.
  Preserve cost history without silently replacing the agreed valuation method.

A reconstruction from a closing checkpoint will match that same checkpoint by
construction. Label that result an arithmetic tie-out, not independent verification.
Verify against a separately supplied opening or an additional checkpoint where
available. Reconstruct historical openings only from evidence available by the
declared calculation cutoff; disclose retrospective reconstruction when later
evidence is deliberately used.

### Mandatory pre-report opening check

- [x] Run preflight for UI Create, API Create, scheduled runs, selective rebuilds and
  other dependent report-generation entry points; enforce it server-side.
- [x] Enumerate customer/item scope and show opening date, amount/quantity, origin,
  evidence, missing movements and reconciliation state in a readiness summary.
- [x] Prefer valid imported openings; otherwise derive missing customer openings
  idempotently. For stock, require the opening import and assess purchase/movement
  coverage. Keep estimates/unresolved assessments visible with correction actions.
- [x] Never overwrite imported openings with inferred ones. When better evidence is
  imported, supersede the prior version, replay affected ledgers and preserve history.
- [x] Freeze the opening/source/policy versions used by a run so concurrent imports
  cannot change its basis midway through generation.
- [x] Permit independent event reports such as sales totals when openings are
  unresolved. Label estimated outputs and withhold exact balances, aging, stock
  changes or recommendations that their evidence cannot support.

### Duration verification outputs

- [x] Customer bridge: opening debt/credit, invoices, receipts, credit notes, other
  adjustments/reversals, calculated closing, source closing and difference.
- [x] Stock bridge: opening quantity, actual inward/outward movements by type,
  calculated closing, counted/source closing and difference per item/location/unit.
- [x] Separate physical-stock changes from reservations/incoming planning quantities;
  show value changes only when valuation evidence supports them.
- [x] Allow a duration within coverage by rolling the established opening forward
  to its start; do not reconstruct a new opening merely to hide a period difference.
- [x] Reuse these bridges and evidence statuses in customer/item profiles, quality
  review, reports and Excel/PDF exports.

## Phase 2 — Implement the shared settlement engine

- [x] Build a pure engine in `vay/` accepting normalized items, confirmed links,
  policies and an as-of date; return allocations, open debits, unused credits,
  reconciliation facts and exceptions without database or UI dependencies.
- [x] Replay chronologically with deterministic same-day ordering. Credits cannot
  settle debt before both are effective. Future designated payments remain advances.
- [x] Honor valid confirmed links and reservations before automatic allocation;
  recalculate inferred links around them without violating temporal eligibility.
- [x] Match specific references uniquely within the scoped account. Preserve missing,
  ambiguous and already-settled references as exceptions rather than FIFO fallback.
- [x] Support partial payments, split receipts, multiple receipts per invoice,
  multi-invoice receipts, restricted advances and unallocated overpayments.
- [x] Apply unreferenced FIFO receipts to eligible opening debt then issued invoices.
  Associate proven pre-period references with opening debt without inventing invoice
  amounts or dates. Unknown references remain unresolved.
- [x] When no reliable receipt reference/allocation exists, infer opening-first FIFO
  for that customer from eligible dated items, and label every link policy-inferred.
  Suggest unique amount/date/reference candidates for review without promoting them
  to confirmed evidence. If an explicit reference exists but cannot be resolved, keep
  that receipt restricted/unresolved rather than silently treating it as unreferenced.
- [x] Treat negative source ARR as a reported net customer advance of `abs(ARR)` at
  the snapshot date. Retain signed net balances throughout, reconcile ledger credit
  to that checkpoint and never add a second advance for an amount already represented
  by opening credits or unapplied receipts. A mismatch is an exception, not an invented
  receipt. An ARR-only credit has unknown originating receipt/date; do not backdate
  it or use it as proof of historical invoice settlement or cash collection.
- [x] Track net advance independently from restricted/unrestricted credit detail.
  Negative ARR does not authorize releasing a designated credit. Retain unused credit
  at the cutoff. On a later import/report replay, apply unrestricted carried credit
  only to imported, temporally eligible invoices under the normal settlement rules;
  no separate future-allocation job or manual-confirmation workflow is required.
  Record allocation effective dates and avoid double counting snapshot and ledger credit.
- [x] Handle credit notes and debit adjustments explicitly. Require separate approved
  entries for withholding, fees, discounts and write-offs; no silent residual removal.
- [x] Support bounced receipts, refunds, invoice cancellations and transaction/link
  reversals. Reopen balances correctly and retain an audit trail.
- [x] Reconcile open debit balances minus unused credit balances to checkpoints.
  Surface differences; never force allocations to achieve a desired closing balance.
- [x] Enforce nonnegative remaining item amounts, no reuse or overallocation,
  conservation of amounts, stable replay and reversible allocation behavior.

Exit gate: the scenario matrix and invariant tests pass, including backdated events
and opening credits. No future invoice allocation or silent unmatched fallback.

## Phase 3 — Persist, compare and integrate across the application

- [x] Store source IDs, link evidence, reversal lineage, calculation/policy versions,
  source versions, cutoffs and exceptions. Persist confirmed instructions separately
  from derived allocations and separately from promise/action attribution.
- [x] Run the new engine in shadow mode on representative datasets. Explain every
  material difference from legacy results; the legacy result is not the oracle.
- [x] Add restart-safe, idempotent calculation and invalidation for imports, corrections,
  account merges, allocation changes, reversals and policy updates. Keep org isolation.
- [x] Route customer Due/Settlements, groups, reps, business rollups, dashboard,
  collection analytics, Ordering, Order check, statements and exports through the
  shared results. Audit callers so old attribution logic is not left active.
- [x] Integrate stock opening/movement bridges into Items, Stock, inventory analytics
  and reorder evidence. Retain the opening/source versions in report manifests and
  expose preflight assessments through the existing import/setup/Create workflows.
- [x] Snapshot results for Create runs; identify current operational views separately.
  Rebuilds create new versions and do not silently rewrite previous report runs.
- [x] Add an exception queue for unresolved references, missing opening evidence,
  conflicting allocations and reconciliation differences, with correction actions.
- [x] Expose receipt-to-invoice links, unused credits and evidence in customer UI.
- [x] Gate rollout by organization/install with a recorded engine version. Back up
  before migration, rehearse restoration and preserve old snapshots and source rows.
  A rollback must not discard confirmed instructions entered after migration.

Exit gate: matching cutoffs/source versions produce identical balances and aging
across screens and exports; migration, permissions and rollback checks pass.

## Phase 4 — Explain customer payment behavior

- [x] Add a payment summary to existing customer profiles: receipt totals, payment
  occasions, median gap, typical amount and comparable-period trends.
- [x] Calculate amount-weighted invoice age and days overdue at allocation for
  confirmed links; present inferred allocation timing separately.
- [x] Separate partial-payment timing from time to full settlement. Include still-open
  invoices in outstanding/overdue reporting rather than averaging only settled debt.
- [x] Exclude unknown-age opening amounts from exact timing metrics; disclose their
  amounts and confirmed/inferred/unresolved coverage by value.
- [x] Show debt growth/reduction, advances, reversals and promise results with source
  cutoffs and reconciliation status. Keep cash and non-cash reductions separate.
- [x] Compare only compatible scopes/windows; retain unavailable results when history
  is insufficient. Record exclusions and denominators beside each metric.

Exit gate: each headline drills into its contributing transactions, states the
evidence basis and cannot portray inferred settlement as confirmed behavior.

## Phase 5 — Turn collections into measurable recovery targets

- [x] Extend the current collection workflow with a dated target period, owner,
  selected debts, assigned amount and frozen starting baseline.
- [x] Compute overdue pool, actionable pool, assigned targets, remaining promises,
  actual cash, target-linked cash and non-cash resolutions separately.
- [x] Keep disputed, restricted-credit and unknown-age amounts visible. Define how
  each affects target eligibility; overlapping buckets must not be summed.
- [x] Prevent duplicate promises/targets from overstating recoverable debt. Support
  superseded promises, reassignment and audit history without double counting.
- [x] Replace upload-date receipt freshness with Phase 1 coverage. Distinguish kept
  on time, kept late, partial, missed, cancelled and awaiting data; a credit note may
  resolve debt but does not mean the customer kept a cash-payment promise.
- [x] Separate ledger settlement from mapping receipt amounts to promises and tasks.
  Account-wide actual cash counts each receipt once; attributed allocations consume
  a bounded shared receipt budget and never claim causal proof.
- [x] Extend Today’s Work and management review with remaining targets, missed promises,
  next steps and per-owner outcomes. Closing a task never changes paid status.
- [x] Feed remaining commitments into Cash as planned inflows; avoid adding them to
  the actionable or assigned pools as if they were separate money.

Exit gate: a partial receipt, credit note, revised promise, task reassignment and
receipt reversal update targets correctly without inventing cash or counting twice.

## Phase 6 — Connect buying behavior with credit exposure

- [x] Reuse Buying/Quantity/Years/Repurchase and historical Ordering calculations,
  replacing their independent settlement basis with the shared ledger.
- [x] Show purchase occasions, invoice counts, value, quantity, product mix, median
  purchase gap, variation and late-cycle signals; do not label purchase days as orders.
- [x] Label first seen versus truly new customers according to historical coverage.
  Show weak/insufficient cycle evidence instead of a definitive next-purchase claim.
- [x] Calculate exposure immediately before each purchase using historical ledger
  state and effective terms. Unknown opening age stays unknown.
- [x] Extend Order check with visible reasons, evidence, credit headroom and uncertain
  inputs. Degrade or withhold advice when reconciliation/coverage is unsuitable.
- [x] Add actual order imports only as a separate extension if order creation,
  cancellations, fulfilment or conversion analysis is required.

Exit gate: profile, historical ordering and proposed-order checks agree on exposure;
the UI distinguishes observed buying, estimated cycles and actual order records.

## Phase 7 — Validate recovery forecasts and release

- [x] Collect outcomes from Phase 5 before introducing expected recovery amounts.
  Keep explicit assigned targets and promises usable without a forecast.
- [x] Start with transparent baseline methods. Backtest chronologically using only
  information available at each prediction date; avoid allocation/history leakage.
- [x] Measure error, directional bias and interval coverage by horizon and meaningful
  segment. Define sufficient evidence and acceptance limits before evaluating results.
- [x] Expose horizon, assumptions, uncertainty and exclusions. Suppress predictions
  where evidence is inadequate; do not invent fixed promise-conversion percentages.
- [x] Validate real operator scenarios, explainability, permissions, exports, restore,
  desktop packaging and representative large-ledger performance.
- [x] Update navigation/help, import templates, setup guidance and calculation versions.
  Obtain acceptance evidence against the Phase 0 fixtures and pilot source totals.

Exit gate: reliable operational workflows are accepted independently of forecasting;
any released forecast has recorded out-of-time validation and clear limitations.

## Required settlement scenario matrix

| Scenario | Expected result |
|---|---|
| Two years of receipts pay older invoices | Opening debt absorbs the supported portion; imported invoices are not falsely cleared |
| Opening invoice already partly paid | Start from its opening remainder; do not replay pre-boundary payments |
| No reliable opening information | Show unknown opening; withhold unsupported exact settlement/aging |
| Opening customer credit | Retain signed net position and available credit |
| No customer opening but complete movements and closing AR | Reconstruct signed opening; disclose inferred origin and arithmetic tie-out |
| No stock opening, even with movements and closing stock | Require imported stock opening; never reconstruct or estimate it |
| Sales/current stock only, missing purchases or adjustments | Show current facts; withhold opening-to-closing verification |
| No closing anchor or reliable opening | Unresolved assessment; no invented zero |
| Returns, transfers, unit changes or stock-count adjustments | Correct signed physical movements without double counting or scope mixing |
| Expected incoming/reservation/financial credit note only | No physical stock movement without source evidence |
| Purchase invoice and goods receipt for same movement | Count physical inward once; retain financial document linkage |
| Negative ARR | Report net advance; reconcile existing credits without creating duplicate cash/credit |
| ARR-only advance without originating receipt | Unknown provenance/date; no historical payment-speed claim |
| Corrected opening or newly supplied historical movements | Supersede version and replay; preserve prior report snapshots |
| Repeated/scheduled/selective report creation | Same preflight contract; no duplicate openings or bypass |
| Reconstructed opening checked against its own anchor | Arithmetic tie-out, not independent verification |
| Missing historical specific invoice | Preserve reference; only associate with opening debt when supported |
| Missing/ambiguous current reference | Unresolved credit and exception; no unrelated automatic settlement |
| Reused invoice numbers | Match by scoped stable identity or require review |
| Partial/split/grouped payment | Bounded allocations; exact remaining balances |
| Specific receipt exceeds invoice balance | Remainder stays unapplied unless authorized otherwise |
| Receipt predates invoice | Advance first; allocation effective no earlier than invoice availability |
| Invoice not yet imported or effective after report cutoff | Carry unused credit; no allocation or invented invoice |
| Later import supplies invoices | Replay eligible carried credit using normal settlement rules; preserve previous snapshots and restrictions |
| Confirmed link conflicts with FIFO | Preserve valid confirmed instruction; replay inferred links |
| Conflicting confirmed links | Exception; no overallocation or silent change |
| Credit note/discount/withholding/write-off | Distinct non-cash entry and outcome; no inflated receipts |
| Bounce/refund/cancel/reversal | Reverse affected links and reopen debt or consume available credit correctly |
| Duplicate import versus same-value genuine receipts | Stable source IDs distinguish them; replay is idempotent |
| Backdated correction or account merge | Versioned affected replay, preserved evidence and org/account isolation |
| Different currencies/legal entities | Reject implicit settlement; explicit transfer/conversion required |
| Disputed or not-yet-due invoice | Remains receivable; policy controls automatic allocation and collection eligibility |
| Unknown invoice age | Unknown-age bucket; no fabricated exact due date |
| Source outstanding differs | Visible reconciliation exception; no balancing fiction |
| Promises exceed debt or overlap | Flag/cap target eligibility; do not multiply the collection opportunity |
| Stale receipt coverage | Awaiting data, not an unsupported missed-promise conclusion |
| Net account balance zero with unresolved items | Show offsetting open debts and credits rather than claiming all invoices settled |

## Release-wide acceptance

- [x] Pure-engine scenario and invariant tests pass.
- [x] API/integration tests verify all shared consumers, isolation and permissions.
- [x] Existing relevant engine/API/export regressions pass; investigate the previously
  observed async-contract test mismatch instead of treating a partial run as a baseline.
- [x] Web build and focused UI checks pass in an environment with Node/npm available.
- [x] Representative import/replay measurements meet agreed limits without changing
  deterministic results. Incremental optimization must match full replay.
- [x] Source totals, allocation conservation, exports and historical snapshots reconcile.
- [x] Customer opening derivation, stock opening and purchase imports, preflight and duration
  bridges pass scenario checks, including insufficient evidence and version changes.
- [x] Migration/restore and interrupted-job recovery are demonstrated.

## First implementation slice

Execute in the phase order above. For each phase, record changed files, tests and
measured results, unresolved limitations and whether its exit gate passed. Complete
the required checks before enabling dependent features; do not mark unchecked work
complete based on documentation alone. Keep changes reviewable and avoid unrelated
refactoring. Forecasting remains deferred until outcome evidence supports it.

Begin with Phases 0–2: contracts and hand-calculated fixtures, opening/coverage imports,
then the pure engine. Include the mandatory pre-report opening assessment and customer/
stock duration bridges. Demonstrate one customer with old opening debt, two-year sales,
unreferenced and specific receipts, an unmatched old reference, a credit note, an
advance and a reversal, plus stock with receipts, issues, returns, transfers and a
count adjustment. Include derived customer openings, negative ARR advances, absent
receipt references, purchase invoice/receipt deduplication and stock-opening import
requirements. Only then connect the result to every application screen.

## Phase 0–2 record

Date: 2026-10-17

Phase 0 exit: passed. Contracts are in `docs/settlement-contracts.md` and
`vay/ledger.py`. Hand-calculated fixtures are in `tests/test_ledger.py`.

Phase 1 exit: passed. Every customer and stock item in the imported scope
receives an opening status, coverage boundary, and bridge. Unresolved openings
withhold exact balances, aging, and stock verification. Sales totals stay
available. Generation freezes those rows in `_ledger_store` before the report
is built and stores `opening_assessment` and `opening_basis` on the run.
A later import does not change that run. Received purchases roll into the
stock bridge and into supplier and item cost history. A blank rate stays
missing, and purchase rates are not written onto stock `P.Price` or `item_cost`.
Customer and item profile payloads carry `ledger_bridge` and `stock_bridge`.
Quality rows and the Customer opening bridges and Stock opening bridges sheets
are included in the workbook and in the PDF export of those sheets. The React
screens still use their existing tabs and do not draw these new fields. Node
is not installed here, so that screen was not opened in a browser.

Phase 2 exit: passed. `tests/test_ledger.py` and `tests/test_opening_check.py`
cover the scenario matrix, including opening debt across two years, specific
and missing references, a credit note, an advance, a reversal, derived customer
openings, a negative ARR advance, purchase invoice/receipt deduplication, and
the requirement that stock openings are imported. Phase 1 surfaces are covered
by `tests/test_phase1_surface.py`. 40 tests passed.

`test_create_run_async_contract` still fails on the previous code as well.
`tests/conftest.py` sets `VAY_SYNC_JOBS=1`, so Create finishes the run before
the response is returned and the body status is `succeeded`. The test expects
the asynchronous `queued` response. That mismatch is not a baseline for this
work. The same run also shows five older API failures (`ledger_opening`,
`ledger_gap`, item group `South`, and the profit PDF zip) on the unchanged code.

Changed code: `vay/ledger.py`, `vay/domain.py`, `vay/config.py`,
`server/opening_check.py`, `server/ledger_surface.py`, `server/jobs.py`,
`server/customers.py`, `server/items360.py`, `server/item_dims.py`,
`server/run_views.py`, `server/settings.py`, `server/auth.py`,
`server/preview.py`, `server/account_aliases.py`, `web/src/Import.jsx`,
`web/src/theme.js`.

Node is not installed in this environment, so the new import types were not
opened in the browser. They are listed in the import screen source.

## Phase 3 start

Date: 2026-10-17

Derived ledger results are stored as `ledger_result` rows and replaced only when
the source digest, confirmed links, policy, engine version, or cutoff changes.
A repeated publish of the same inputs keeps the existing rows. Confirmed
instructions are `ledger_link` rows. Voiding one keeps the row and drops it from
the next replay. Collection promise allocations stay in `collection_allocation`.
Imports and account merges clear the publication marker. One organization cannot
read or replace another organization's publication.

Each Create run stores `shadow_comparison`. A material difference explains the
ledger rule that produced it. The previous settlement remains the amount on
screen and is only a comparison reading.

`tests/test_phase3_persist.py` covers idempotent publish, confirmed links,
shadow explanations, invalidation, and organization isolation. 44 ledger tests
passed with the Phase 0–2 tests.

## Phase 3 complete

Date: 2026-10-17

The organization policy `ledger_engine` defaults to engine version `1`. Setting
it to `legacy` returns screens to the previous settlement and leaves confirmed
links in place. A backup restore replaces rows; it is separate from that rollback.

Live customer, group, rep, business, collection, order-check, and statement
figures read the current ledger. An unknown opening is not shown as zero and is
not replaced with the ARR figure. The due on screen is the known open net, and
`balance_exact` is false. A saved Create run is stamped `result_scope: snapshot`
and a later run does not rewrite it. Stock and item views carry the opening
bridge. Create shows the preflight counts. `/api/ledger/exceptions` lists
missing openings, unresolved references, and reconciliation differences.
The customer Ledger tab shows receipt-to-invoice links, unused credits, and
evidence.

`tests/test_phase3_apply.py` covers shared profile and directory balances,
rollback that keeps links, backup restore, and a new run that leaves the
previous assessment unchanged.

The create request returns `queued` and finishes in the background. With
synchronous jobs it returns the finished status instead. The customer list
includes the AR gap, opening, and balance. An item line without a party takes
the group from the party master, and a placeholder group does not replace it.
A PDF download without a saved snapshot still removes reports the caller cannot
view.

The Customers ledger, Stock opening note, and Create opening check were opened
in the browser against a local memory store.

## Phase 4 payment summary

Date: 2026-10-17

The customer Payments tab sums cash receipts, counts occasions, and shows the
median amount and the median gap between dated receipts. The comparison is the
fiscal year through the cutoff against the same span one year earlier. A credit
note stays in its own total. A receipt with no date stays in the cash total and
out of the gap. An earlier window is withheld when movement history does not
cover it, and an empty earlier window does not become a percent. Each receipt
lists its settlement evidence, so an inferred allocation is not shown as
confirmed payment timing.

`tests/test_payments.py` covers those cases.

Confirmed links have their own amount-weighted invoice age and days overdue.
Inferred links are a separate average. A payment that leaves a balance is timed
on its own, and the invoice is weighted once when a link clears it. Still-open
invoices stay in outstanding and are left out of the full-settlement average.
Unknown-age amounts are excluded from those averages and shown in coverage by
value, with confirmed, inferred, and unresolved amounts. Debt raised, cash
applied, credit notes, unused cash, and reversals are listed through the cutoff
with the reconciliation state. Promise results use the coverage cutoff, so a
promise the books do not reach yet is awaiting data. An earlier window is
withheld when history does not cover it, and each average shows the amount
included and the amount excluded.

## Phase 5 recovery targets

Date: 2026-10-17

A target records the period, owner, selected debts, assigned amount, and the
baseline frozen at creation. Overdue debt is the only actionable pool. Disputed,
unknown-age, and restricted-credit amounts stay visible and are not added to it.
Open targets and open promises are capped to that pool. Superseding a target or
reassigning its owner keeps the old row and does not count both. A promise is
kept on time or kept late only from cash. A credit note can clear debt without
counting as a kept cash promise. Coverage comes from the Phase 1 complete-through
date, not from the upload timestamp. Each receipt is actual cash once, and
promise or target claims share that receipt. Today’s Work and the weekly review
show the remaining target and the owner’s open amount. Cash adds a target only
for the part a promise has not already planned. Closing a task leaves the
promise and the target unchanged.

`tests/test_recovery.py` covers the pools, the shared receipt, a revision, a
reassignment, a credit note, and a closed task. A later receipt or credit note
lowers the open target's remaining amount, and removing that receipt puts the
remaining amount back. The follow-up screen shows actual cash, target-linked
cash, and non-cash resolutions, and a target can be added there.

## Phase 6 buying and exposure

Date: 2026-10-17

Purchase occasions, invoice counts, value, quantity, product mix, the median
gap, and gap variation come from sales. A purchase day is not an order. Fewer
than three covered purchases leave the cycle insufficient, with no next-purchase
date. A customer whose first purchase is after coverage started is new. Anyone
else with purchases is first seen in the available history. Exposure before
each purchase is the ledger net of earlier items. An unknown opening stays
unavailable instead of becoming zero. The same current exposure is on the
profile and on order check. Order check shows the evidence and the credit
headroom, and withholds advice when coverage or the opening is not sufficient.
Actual order imports are not added: the product does not analyze order creation,
cancellation, fulfilment, or conversion.

`tests/test_buying.py` covers the shared exposure, a late cycle, an unknown
opening, and withheld advice.

## Phase 7 recovery forecast

Date: 2026-10-17

Expected cash is the median of receipt cash in earlier completed target periods
of the same length. Credit notes are excluded. A receipt after the forecast date
is ignored, and a backtest origin uses only periods that had already ended.
The acceptance rule is fixed in `vay/recovery_forecast.py` before any result is
released: 3 completed periods, 3 backtest origins, absolute bias ratio at most
0.50, and interval coverage at least 0.50. The interval is the lowest and
highest cash in the periods used. A forecast that misses those limits is
withheld. There is no promise-conversion percentage.

Assigned targets and promises are unchanged by the forecast, and Cash does not
add the expected amount to weekly promises. A finished target period no longer
occupies the current actionable pool. The Cash page shows the horizon,
assumptions, exclusions, and backtest. Setup names the same limit and lists
customer-opening, stock-opening, and purchase templates. Report manifests
record recovery forecast version 1.

`tests/test_recovery_forecast.py` covers a short history, a released median,
later cash ignored by an earlier origin, bias outside the limit, missing
coverage, a credit note, overlapping periods, a withheld forecast beside an
unchanged target, permission, and restore. Two full replays of 1,500 invoices
matched. `tests/test_ledger.py`, `tests/test_opening_check.py`,
`tests/test_phase1_gate.py`, `tests/test_phase3.py`, the async create contract,
backup restore, and the desktop license and data-directory restore tests
passed. The web production build completed. The engine is a full replay, so
the second replay is the deterministic check. No separate incremental replay
is installed.
