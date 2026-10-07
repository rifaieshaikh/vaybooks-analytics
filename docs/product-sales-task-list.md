# Vay Reports: Product Sales Feature Task List

Date: 2026-10-07  
Status: Implementation backlog; completion evidence pending  
Feature recommendations: [Features that help sell the product](product-sales-features.md)

## Gap record (SF00)

Recorded: 2026-10-07. Owners and estimates are still unassigned. Checkboxes stay open until a result is verified.

Initial offer for the demonstration: wholesale and distribution staff can open a labeled sample, see whom to collect from, and record the next collection step. The buyer is the owner. The operator imports exports. Collection and sales staff carry out Today's Work. Source exports are Excel or CSV. Deployment for the demo is the desktop install, which uses the default organization. Company settings keep Asia/Kolkata until a company confirms another timezone.

Demo scenarios, dated from the company today on each seed and reset:

- Harbour Traders: overdue balance and a collection follow-up due today.
- North Mill: a promise dated yesterday with a partial receipt and a remaining balance.
- Lane and Co: purchases down from an earlier period to a small recent sale.
- Oak Board 18mm: stock below its selling pace, with an assigned purchase action.

| Feature | Status | Where to extend |
|---|---|---|
| One-click demo company | Missing | No demo seed. Desktop has no organization switcher, so the seed belongs in the default organization. |
| Today's Work | Incomplete | `server/worklist.py`, `web/src/Analytics.jsx`. Staff filter exists. Work-type, due status, capped stock rows, and assign-from-the-list do not. |
| Collection mini-CRM | Incomplete | `server/collection.py`, `web/src/CollectionFollowUp.jsx`. Promises, disputes, and allocations exist. Confirmed received is not shown beside promised and remaining. Promise staff is dropped by the request body. Collection reads are not rep-scoped. Edits are not written to `server/audit.py`. |
| Explain important numbers | Incomplete | `server/explain.py`. Dashboard headlines freeze with the report. Worklist, customer AR, and purchase quantity do not open that explanation. |
| Smart reorder assistant | Incomplete | `server/reorder.py` already uses Item 360 `buy_qty`. Pack size is still a proposal edit. The screen does not show the inputs that formula uses. |
| Salesperson mobile view | Incomplete | `web/src/styles.css` stacks the shell under 900px. Follow-up forms are not a phone layout, and a failed save does not keep the form. |
| Guided onboarding | Incomplete | `web/src/SetupWizard.jsx`, `web/src/Import.jsx`, `server/phase2.py`. Import and control totals exist. Policy confirmation is a separate settings screen. |
| Management review | Incomplete | `server/actions.py`, Weekly review in `web/src/Analytics.jsx`. Open, overdue, and promise counts exist. Owner comparison, sales recovery, and non-inflating receipt attribution do not. |
| Customer-ready exports | Incomplete | Statement and reminder PDFs are in `server/customers.py`. They omit company name and currency, and Share downloads without a preview. |
| Pricing, license, and support | Incomplete | `server/hosted.py` `license_view` and Settings → Plan and support show packs, version, and a diagnostics download. Renewal stays unset until a commercial policy is written. `support_gate` remains the support-hours trend check. |

Automated checks for the demo seed, promise staff, partial confirmation, audit, and stock filter are in `tests/test_sales_demo.py`. Checkboxes below stay open until a person verifies each result.

## How to use this checklist

- Assign a named owner and estimate before starting each task group.
- Check an item after its result is verified; record the implementation or evidence link.
- Existing code is a foundation to inspect and extend. Unchecked items do not mean
  that the corresponding feature is absent.
- First means needed for the initial demonstration and pilot. Next means a
  following improvement. Launch means needed before the proposed paid rollout.
- Reuse tasks in the [product improvement plan](product-improvement-plan.md) and
  [global product task list](global-product-task-list.md) when their scope overlaps.
  Link shared evidence rather than creating a second implementation.

## Task index

| ID | Task group | Priority | Suggested owner | Dependencies |
|---|---|---|---|---|
| SF00 | Confirm scope and existing gaps | First | Product + Engineering | None |
| SF01 | One-click demo company | First | Backend + Frontend | SF00 |
| SF07 | Guided onboarding and refresh | First | Backend + Frontend | SF00 |
| SF04 | Explain important numbers | First | Backend + Frontend | SF00 |
| SF03 | Complete collection mini-CRM | First | Backend + Frontend | SF00 |
| SF02 | Complete Today's Work | First | Backend + Frontend | SF03 |
| SF09 | Customer-ready exports | First; extend for launch | Backend + Frontend | SF03, SF04 |
| SF11 | Validate the demo and first pilot | First | Product + Pilot operators | SF01, SF02, SF03, SF04, SF07, basic SF09 |
| SF05 | Smart reorder assistant | Next | Backend + Purchasing lead | SF04 |
| SF06 | Salesperson mobile view | Next | Frontend + QA | SF02, SF03 |
| SF08 | Management review | Next | Backend + Product | SF02, SF03, SF04 |
| SF10 | Pricing, license, and support | Launch | Product + Engineering + Support | SF00 |
| SF12 | Verify the proposed paid offer | Launch | Product + Engineering + QA | SF05, SF06, SF08, SF09, SF10, SF11 |

Dependencies apply to acceptance and integration. Independent design and discovery
can start earlier. SF12 assumes the offer includes all ten recommended features;
record an explicit reduced scope if a smaller offer is selected.

## First: Demonstration and pilot

### SF00: Confirm scope and existing gaps

- [ ] Record the initial buyer, operator roles, source exports, enabled modules,
  deployment mode, and supported company settings.
- [ ] Review all ten recommendations against existing screens, APIs, and tests;
  mark each requirement as verified, incomplete, or missing with supporting links.
- [ ] Link overlapping global/improvement tasks and assign owners and estimates
  to the remaining work.
- [ ] Define a repeatable demo covering an overdue customer, missed promise,
  declining customer purchases, and an item needing stock attention.

Done when: the team has an agreed offer and an actionable gap list.
Owner: unassigned. Evidence: pending.

### SF01: One-click demo company

- [ ] Prepare synthetic sales, receipts, AR, stock, customers, promises, and actions
  with documented control totals and internally consistent dates.
- [ ] Create an isolated, clearly labeled demo company with a repeatable seed/reset
  process that affects only demo records.
- [ ] Add the entry point to open the demo and produce its first useful report
  without requiring a prospect to prepare files.
- [ ] Keep due dates and sample report dates consistent across repeated demos;
  include all four scenarios defined in SF00.
- [ ] Verify fresh setup, reopening, reset, and separation from customer data.

Done when: the complete demo can run on a fresh supported installation.
Owner: unassigned. Evidence: pending.

### SF07: Guided onboarding and refresh

- [ ] Reuse the import wizard and onboarding checks to show setup progress.
- [ ] Guide company-policy confirmation, source selection, mapping, preview,
  validation, and first report creation.
- [ ] Provide representative source templates and explain missing data in terms
  of the reports or decisions it prevents.
- [ ] Reuse saved mappings for refresh; show source freshness, validation errors,
  and control totals with a clear correction path.
- [ ] Verify first import, repeated import, corrected data, failed import, and
  refresh without duplicated transactions or lost follow-up records.

Done when: an operator can import and refresh supported exports successfully.
Owner: unassigned. Evidence: pending.

### SF04: Explain important numbers

- [ ] Audit existing number explanations and cover headline sales, collections,
  receivables, stock signals, and proposed purchase quantities.
- [ ] Show the saved report date, calculation window, formula, inputs, source
  references, freshness, and relevant assumptions.
- [ ] Make explanations accessible from the dashboard, worklist, customer view,
  and reorder view where the corresponding figures appear.
- [ ] Handle older saved reports and missing inputs explicitly; keep source detail
  within the viewer's existing permissions.
- [ ] Verify explanations agree with saved figures and reconciliation evidence;
  refreshing data must not silently rewrite an older report's explanation.

Done when: a user can trace a supported figure to the evidence that produced it.
Owner: unassigned. Evidence: pending.

### SF03: Complete collection mini-CRM

- [ ] Review and complete the existing contact timeline, promises, disputes,
  allocations, and next-follow-up flows in the customer and worklist screens.
- [ ] Show promised, confirmed received, and remaining amounts; keep task
  completion separate from payment status.
- [ ] Complete due-follow-up and missed-promise queues with owner and freshness
  context, using the company's dates and reporting currency.
- [ ] Support partial payments, corrected or reversed allocations, and reviewed
  reminder drafts without reusing a receipt to inflate progress.
- [ ] Verify persistence, audit history, assigned-customer access, multiple
  promises, corrected imports, and unchanged readability of existing records.

Done when: staff can record a promise, confirm a partial payment, and schedule
the remaining follow-up from the same customer context.
Owner: unassigned. Evidence: pending.

### SF02: Complete Today's Work

- [ ] Reuse the worklist to combine due collections, missed promises, customer
  recovery, and stock attention with a visible priority rule.
- [ ] Show reason, customer/item, owner, due date, amount/quantity, and next action.
- [ ] Add staff, work-type, and due-status filters that respect access rules.
- [ ] Support assignment, progress updates, and follow-up scheduling without
  duplicate tasks or losing the selected customer/item context.
- [ ] Verify empty, stale-data, loading, error, and completed-work states; confirm
  an unauthorized staff filter cannot expose another person's restricted work.

Done when: staff can identify and complete their due work from one destination.
Owner: unassigned. Evidence: pending.

### SF09: Customer-ready exports

- [ ] Audit existing statement, reminder, PDF, and Excel output and define the
  templates needed for the initial offer.
- [ ] Add company identity, customer details, reporting currency, report date,
  readable line items, and relevant calculation or allocation notes.
- [ ] Provide statement and reminder previews for staff review before sharing.
- [ ] Verify totals, permissions, long names, empty reports, large datasets, and
  PDF pagination against the corresponding screen/source figures.
- [ ] Extend the launch templates to reorder proposals and management summaries
  once SF05 and SF08 are complete.

Done when: basic statements/reminders are usable for the pilot, and all templates
included in the paid offer are verified before SF12.
Owner: unassigned. Evidence: pending.

### SF11: Validate the demo and first pilot

- [ ] Run the complete demo from fresh setup through a contact, promise, partial
  payment, follow-up, source explanation, and statement export.
- [ ] Run onboarding and a refresh with representative customer exports and
  reconcile the results with agreed source totals.
- [ ] Record import/report preparation time, assistance needed, failed steps,
  repeat use, and customer feedback without inventing results.
- [ ] Record which workflows the buyer would pay for and resolve blockers to the
  core demonstration and daily use.

Done when: the demo is repeatable and the pilot has documented results and feedback.
Owner: unassigned. Evidence: pending.

## Next: Daily operational value

### SF05: Smart reorder assistant

- [ ] Reuse existing planning and align the base recommendation across Item 360,
  stock decisions, and reorder drafts for identical data and policy.
- [ ] Show selling pace, dated stock, reservations, eligible incoming stock,
  holding/lead-time assumptions, suggested quantity, and buy date.
- [ ] Apply pack/minimum rules to positive requirements; retain manual overrides
  separately from calculated quantities and explain budget deferrals.
- [ ] Handle missing costs, stale stock, discontinued items, late incoming stock,
  zero demand, and unknown inputs without presenting unsupported certainty.
- [ ] Verify quantity agreement, pack rounding, budget totals, and saved proposal
  behavior with representative cases.

Done when: purchasing staff can explain and export a supported buy recommendation.
Owner: unassigned. Evidence: pending.

### SF06: Salesperson mobile view

- [ ] Adapt assigned work, customer balances, collection history, and follow-up
  forms for phone-sized screens using the existing web application.
- [ ] Provide useful contact actions and prevent accidental duplicate submissions.
- [ ] Preserve role/customer access and show successful, failed, or pending saves
  clearly during connection interruptions.
- [ ] Verify navigation, readable forms, touch targets, exports, and data updates
  on representative desktop and mobile viewports.

Done when: a salesperson can review assigned work and save a follow-up on a phone.
Owner: unassigned. Evidence: pending.

### SF08: Management review

- [ ] Extend existing results and weekly review with assigned/completed/overdue
  work, promises kept, confirmed receipts, and customer recovery signals.
- [ ] Define each metric's date window, baseline, attribution, and freshness;
  distinguish observed changes from results confirmed against particular work.
- [ ] Add period and staff comparisons with drill-downs to supporting records.
- [ ] Verify that shared receipts, corrected imports, and incomplete data do not
  inflate totals or imply an unsupported cause for a business change.

Done when: the owner can review progress and trace the supporting evidence.
Owner: unassigned. Evidence: pending.

## Launch: Commercial offer and release

### SF10: Pricing, license, and support

- [ ] Define the selected plans/modules, prices, support commitment, deployment
  options, and trial/renewal/expiry behavior using pilot feedback and costs.
- [ ] Reuse existing entitlements where applicable and implement the selected
  license lifecycle for each deployment included in the offer.
- [ ] Show plan, enabled modules, license status, renewal information, product
  version, and support contact in an appropriate settings screen.
- [ ] Provide a reviewed diagnostics export that omits credentials and includes
  only the information needed for support.
- [ ] Verify purchase/activation, renewal, expiry, and entitlement changes against
  the agreed policy while preserving customer records and permitted data access.

Done when: buyers can understand their offer and support route, and its commercial
rules match the application's behavior.
Owner: unassigned. Evidence: pending.

### SF12: Verify the proposed paid offer

- [ ] Verify SF05-SF10 with pilot users and record remaining limitations for the
  selected offer, including any features explicitly deferred.
- [ ] Run focused automated checks for changed calculations, data persistence,
  imports, access rules, allocations, and entitlements, plus workflow checks for
  the screens and exports included in the release.
- [ ] Verify installation/update, restart, backup/restore, and the supported
  deployment configuration using representative data and settings.
- [ ] Prepare the repeatable demo, onboarding materials, release notes, known
  limitations, pricing, and support information.
- [ ] Record the release decision, open blockers, responsible owners, and evidence;
  confirm sales claims match observed results and supported functionality.

Done when: every feature promised in the chosen paid offer has acceptance evidence
and there are no unresolved blockers for that offer.
Owner: unassigned. Evidence: pending.

## Existing implementation references

- Daily work and actions: [worklist](../server/worklist.py),
  [actions](../server/actions.py), [action routes](../server/routers/actions.py),
  and [analytics UI](../web/src/Analytics.jsx).
- Collections: [collection logic](../server/collection.py) and
  [customer UI](../web/src/Customers.jsx).
- Number explanations: [saved-figure explanations](../server/explain.py).
- Onboarding: [import UI](../web/src/Import.jsx) and
  [onboarding checks](../server/phase2.py).
- Purchasing: [planning](../server/planning.py),
  [Item 360](../server/items360.py), and [reorder](../server/reorder.py).
- Exports and commercial controls: [PDF export](../server/pdf_export.py),
  [view/export routes](../server/routers/views.py),
  [hosted controls](../server/hosted.py), and [settings UI](../web/src/Settings.jsx).
- Existing verification: [phase 2 tests](../tests/test_phase2.py),
  [phase 3 tests](../tests/test_phase3.py), and
  [PDF export tests](../tests/test_pdf_export.py).
