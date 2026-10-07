# Vay Reports: Global Product Task List

Date: 2026-10-07  
Status: Planning backlog; all acceptance checks below remain unverified  
Product direction: [Global product strategy](global-product-strategy.md)

## 1. How to use this backlog

- Check a task only after its acceptance criteria have evidence recorded.
- Existing workflows are foundations to reuse, not proof that an international
  acceptance criterion is complete.
- Assign a named owner and estimate before starting. Owner roles below are recommendations.
- P0 means required for the stated release's data correctness or operation; P1
  means required for usable adoption; P2 means expansion driven by customer demand.
- R0 is pilot definition; R1 is the international export-based offer; R2 is hosted
  self-service; R3 is later expansion. Hosted gates do not block a desktop-only R1.
- Dependencies refer to completed prerequisites, except where a task explicitly
  permits independent discovery. Keep this checklist local until issue-tracker
  publication is requested.

## 2. Task index

| ID | Task | Priority | Release | Owner role | Dependencies |
|---|---|---|---|---|---|
| G01 | Define first cohort and support matrix | P0 | R0 | Product + Sales | None |
| G02 | Collect overseas pilot exports and controls | P0 | R0 | Product + Pilot operators | G01 |
| G03 | Define stable source identities and migration | P0 | R1 | Backend | G02 |
| G04 | Add source-specific date and number parsing | P0 | R1 | Backend + Frontend | G02 |
| G05 | Enforce reporting currency and precision | P0 | R1 | Backend + Product | G02 |
| G06 | Preserve source tax basis | P0 | R1 | Backend + Pilot finance lead | G05 |
| G07 | Confirm and validate organization policy | P0 | R1 | Backend + Frontend | G01, G04, G05 |
| G08 | Replace new-company legacy expense seeds | P0 | R1 | Backend + Frontend | G07 |
| G09 | Make field requirements metric-specific | P0 | R1 | Backend + Product | G03 |
| G10 | Define units, packs, and stock scope | P0 | R1 | Backend + Purchasing lead | G03, G05 |
| G11 | Implement optional module availability | P1 | R1 | Backend + Frontend | G01, G09 |
| G12 | Simplify navigation and apply terminology | P1 | R1 | Frontend + Product | G07, G11 |
| G13 | Complete generic onboarding and refresh | P1 | R1 | Frontend + Backend | G02, G04, G05, G07, G08, G09, G11 |
| G14 | Make international exports consistent | P0 | R1 | Backend + Frontend | G04, G05, G07, G12 |
| G15 | Verify international workflows and legacy parity | P0 | R1 | Engineering + QA | G03, G04, G05, G06, G07, G08, G09, G10, G11, G12, G13, G14 |
| G16 | Build hosted workspace/account lifecycle | P0 | R2 | Backend + Frontend | G03, G07, G11 |
| G17 | Verify hosted organization and role isolation | P0 | R2 | Backend + QA | G03, G11, G16 |
| G18 | Complete hosted recovery and operations | P0 | R2 | Operations + Backend | G17 |
| G19 | Implement commercial entitlement lifecycle | P0 | R2 | Product + Backend | G11, G16, G17 |
| G20 | Publish support and data-handling procedures | P1 | R1; hosted addendum R2 | Product + Support | G01, G13 |
| G21 | Run measured international pilots | P0 | R1 | Product + Pilot owners | G02, G13, G14, G15 |
| G22 | Prepare and gate the first international launch | P1 | R1 | Product + Sales + Engineering | G20, G21 |
| G23 | Select and deliver one demanded connector | P2 | R3 | Product + Integrations | G21 |
| G24 | Extend to mixed-currency reporting | P2 | R3 | Backend + Finance domain lead | G05, G06, G21 |
| G25 | Add a demanded UI language | P2 | R3 | Frontend + Localization | G07, G12, G14, G21 |
| G26 | Add a validated sector module | P2 | R3 | Product + Engineering | G11, G21 |

## 3. R0: Customer definition and evidence

### G01: Define first cohort and support matrix

- [ ] G01 complete. Owner: unassigned. Evidence: search list only; no external candidate has been named. See [global support matrix](global-support-matrix.md).

Choose the first overseas cohort among wholesalers, distributors, and compatible
product-selling SMBs. Record countries, source systems, languages, currencies and
precision, date/number formats, fiscal calendars, tax conventions, units,
locations, deployment preference, and unsupported use cases.

**Acceptance:** A written matrix names the supported first offer and exclusions;
at least two external pilot candidates fit it; desktop and hosted release scopes
are distinguished. The English, single-reporting-currency offer is a proposal to
validate, not a current compatibility claim.

### G02: Collect overseas pilot exports and controls

- [ ] G02 complete. Owner: unassigned. Evidence: template only; no external dataset has been received. See [overseas intake template](phase0/samples/_overseas_intake/MANIFEST.md).

Collect consented or anonymized representative sales, receipt, AR, item, and stock
exports, plus optional cost/tax/payable data. Document grain, stable references,
dates, currencies, units, snapshot coverage, and agreed control totals.

**Acceptance:** At least two external datasets have documented mappings and
control totals; corrected/repeated exports are included; missing sources are
recorded. Update [pilot intake](phase0/07_pilot_baselines_and_gate.md) without
inventing measurements. Use [existing intake support](../server/pilots.py).

## 4. R1: Data correctness and neutral setup

### G03: Define stable source identities and migration

- [ ] G03 complete. Owner: unassigned. Evidence: pending.

Use source/company/transaction/line identifiers where provided. Define a documented
fallback where IDs are absent. Preserve legacy keys, aliases, receipt links,
actions, saved reports, and organization ownership during migration.

**Acceptance:** Two legitimate same-day, same-amount invoices remain distinct;
reimporting one transaction is idempotent; corrections update only intended
records; another company's matching source ID does not collide; legacy records
remain accessible. Touchpoints: [keys](../server/keys.py),
[mapping](../server/mappers.py), [import](../server/ingest.py),
[identity tests](../tests/test_uk.py).

### G04: Add source-specific date and number parsing

- [ ] G04 complete. Owner: unassigned. Evidence: pending.

Save source date order and numeric separators in mapping metadata. Normalize once
at ingestion and preserve source text/provenance. Replace unsafe ad hoc parsing
in affected totals, snapshots, reports, and planning paths using the same contract.

**Acceptance:** `1,234.56` and `1.234,56` both become 1234.56 under their selected
formats; `03/04/2026` follows an explicit DMY/MDY choice; malformed input produces
a visible reject; decimal-comma CSV fields respect the delimiter; repeated imports
retain the same interpretation; original Vay fixtures retain their meanings.
Touchpoints: [date/number helpers](../vay/dates.py), [ingestion](../server/ingest.py),
[mappers](../server/mappers.py), [import UI](../web/src/Import.jsx),
[date tests](../tests/test_dates.py), [ingest tests](../tests/test_ingest.py).

### G05: Enforce reporting currency and precision

- [ ] G05 complete. Owner: unassigned. Evidence: pending.

Declare one reporting currency per company and the supported currency precision.
Require a currency basis for monetary sources, including AR, stock costs, promises,
payables, and budgets. Preserve supplied original amounts and currency metadata.

**Acceptance:** Unexplained mixed currencies cannot enter a headline total;
source-provided reporting amounts reconcile; changing a symbol alone never
converts amounts; unsupported precision is rejected or explicitly excluded;
calculations and exports use the agreed rounding rule; saved runs retain their
currency basis. Touchpoints: [policy](../server/org_policy.py),
[domain model](../vay/domain.py), [formatting](../web/src/format.js),
[collection](../server/collection.py), [cash](../server/cash.py),
[planning](../server/planning.py).

### G06: Preserve source tax basis

- [ ] G06 complete. Owner: unassigned. Evidence: pending.

Define source net, tax, and gross fields and their meaning. Make the inclusive-rate
fallback explicit and restrict it to compatible sources. Keep country-specific
tax fields in adapters without breaking existing stored fields.

**Acceptance:** Mixed-rate, tax-exempt, tax-exclusive, and tax-inclusive examples
match agreed controls; net/gross values are not confused; zero tax remains zero;
returns preserve the source basis; unavailable tax information does not produce
unqualified profit figures. Touchpoints: [preview aliases](../server/preview.py),
[profit reports](../vay/reports/profit.py), [credit-note tests](../tests/test_credit_notes.py).

### G07: Confirm and validate organization policy

- [ ] G07 complete. Owner: unassigned. Evidence: pending.

Extend existing settings with an explicit onboarding confirmation of timezone,
reporting currency, fiscal year, display locale, tax basis, and terminology.
Source parsing settings can differ from display locale.

**Acceptance:** Invalid timezones/configuration are reported rather than silently
replaced; non-April fiscal years and supported timezone boundaries work across
reports and due states; existing companies keep their saved policy; subsequent
policy changes do not silently relabel old reports. Touchpoints:
[organization policy](../server/org_policy.py), [schemas](../server/schemas.py),
[organization settings UI](../web/src/settings/OrganizationSection.jsx),
[fiscal tests](../tests/test_fiscal.py).

### G08: Replace new-company legacy expense seeds

- [ ] G08 complete. Owner: unassigned. Evidence: pending.

Start neutral companies with empty or generic expense categories and explicit
account mapping. Preserve the original-business pack as an opt-in legacy template.

**Acceptance:** Fresh companies receive no original-customer account names;
intentionally empty mappings stay empty after save/reload; unmapped payments
remain visible; existing expense mappings and financial reports remain intact.
Touchpoints: [expense pack](../vay/packs/vay_wholesale.py),
[policy persistence](../server/org_policy.py), [pack helpers](../vay/packs/__init__.py).

### G09: Make field requirements metric-specific

- [ ] G09 complete. Owner: unassigned. Evidence: pending.

Separate minimum record fields from fields needed for a particular report or
dimension. Define how anonymous sales, missing reps, and incomplete product detail
are represented for the selected cohort; do not invent those entities.

**Acceptance:** A valid sales/receipt source without salesperson data imports;
rep analysis is unavailable or explicitly unassigned as appropriate; customer
totals reconcile where identity exists; missing cost blocks costing without
blocking supported stock quantities; no missing field is silently substituted
with a misleading value. Touchpoints: [required fields](../server/settings.py),
[eligibility](../vay/eligibility.py), [domain](../vay/domain.py),
[onboarding](../server/phase2.py).

### G10: Define units, packs, and stock scope

- [ ] G10 complete. Owner: unassigned. Evidence: pending.

Record supported product units, conversions, quantity precision, and stock
location scope. Reuse current holding/demand rules with normalized inputs.
Preserve dated reservation, incoming, and cost evidence.

**Acceptance:** A supported case-to-unit conversion agrees across sales, stock,
and reorder; incompatible units are not totaled as one physical quantity; quantity
precision follows the declared unit contract; consolidated stock is labeled;
late incoming deliveries do not resolve earlier shortages; manual adjustments
remain distinguishable from suggestions. Touchpoints:
[planning](../server/planning.py), [Item 360](../server/items360.py),
[reorder](../server/reorder.py), [item tests](../tests/test_items.py).

## 5. R1: Modules, experience, and exports

### G11: Implement optional module availability

- [ ] G11 complete. Owner: unassigned. Evidence: pending.

Define availability for Sales, Collections, Inventory/Purchasing, Management
Finance, and Advanced Analytics. Build on existing packs and permissions.

**Acceptance:** Collections works without inventory; disabled modules retain data;
module access is enforced server-side; entitlements, user permissions, and data
eligibility are independent checks; unsupported metrics show their requirements.
Touchpoints: [hosted entitlements](../server/hosted.py),
[report access](../server/auth.py), [navigation](../web/src/theme.js),
[access tests](../tests/test_report_access.py).

### G12: Simplify navigation and apply terminology

- [ ] G12 complete. Owner: unassigned. Evidence: pending.

Implement the proposed Overview, Work, Customers, Products, Reports, and
Administration structure with contextual finance/purchasing views. Apply selected
business terminology consistently, including reports and readiness messages.

**Acceptance:** Users reach a collection or purchase decision through a clear
primary destination; administration tools respect role access; enabled modules
and data readiness govern visibility; existing deep links and report IDs continue
to work; mobile layouts remain usable. Touchpoints:
[navigation](../web/src/theme.js), [app shell](../web/src/App.jsx),
[analytics](../web/src/Analytics.jsx), [UI tests](../tests/test_ui.py).

### G13: Complete generic onboarding and refresh

- [ ] G13 complete. Owner: unassigned. Evidence: pending.

Reuse the import wizard, existing checklist, remembered modes, and source preset.
Add tested pilot-specific templates and readiness for the enabled modules.
Distinguish import success from a new report using the imported data.

**Acceptance:** A pilot operator configures policy, maps compatible exports,
checks controls, and generates a useful report without code changes; missing
optional sheets do not block unrelated workflows; changed headers trigger review;
repeat/corrected exports follow their chosen mode; both source coverage and
report freshness are visible. Touchpoints: [import UI](../web/src/Import.jsx),
[setup wizard](../web/src/SetupWizard.jsx), [mappers](../server/mappers.py),
[onboarding tests](../tests/test_imp03.py).

### G14: Make international exports consistent

- [ ] G14 complete. Owner: unassigned. Evidence: pending.

Apply the same currency, precision, terminology, and date/number display policy
across UI, Excel, and PDF. Package supported fonts and define the supported
character repertoire for customer and product names.

**Acceptance:** Amounts and dates agree across all outputs; Excel numeric cells
remain numeric; representative accented names and supported currency symbols
render/search correctly; PDF fonts work on supported desktop and hosted builds;
permissions filter the same records and metrics in every output. Touchpoints:
[format helpers](../web/src/format.js), [Excel exporter](../vay/export_excel.py),
[PDF exporter](../server/pdf_export.py), [PDF tests](../tests/test_pdf_export.py).

### G15: Verify international workflows and legacy parity

- [ ] G15 complete. Owner: unassigned. Evidence: pending.

Exercise the complete import-to-decision path using overseas fixtures and the
existing Vay fixtures. Verify collection promises, daily work, stock decisions,
cash reporting, saved reports, and observed outcomes within their supported scope.
Test upgrades and restoration for each supported R1 deployment.

**Acceptance:** Agreed sales/AR controls pass or have a visible accepted exception;
explorer filters do not change official totals; receipt corrections and repeated
tasks do not inflate outcome amounts; stale sources are labeled; saved reports
retain their basis; a restored supported install reproduces the required reports
and artifacts. Record focused tests and desktop/mobile workflow evidence.
Use [golden tests](../tests/test_golden.py), [phase gates](../tests/test_phase1_gate.py),
[outcome tests](../tests/test_imp06.py), and [backup guide](release/backup.md).

## 6. R2: Hosted customer operation

### G16: Build hosted workspace/account lifecycle

- [ ] G16 complete. Owner: unassigned. Evidence: pending.

Add workspace provisioning, invitations, verified account recovery, organization
selection, and a clear trial onboarding flow. Keep desktop setup compatible.

**Acceptance:** A new customer reaches a correctly scoped workspace; invite and
recovery credentials expire and cannot be reused; access changes take effect;
switching organizations does not reuse another workspace's cached data. Reuse
[auth](../server/auth.py), [auth API](../server/routers/auth.py),
[tenant context](../server/tenant.py), and [app state](../web/src/App.jsx).

### G17: Verify hosted organization and role isolation

- [ ] G17 complete. Owner: unassigned. Evidence: pending.

Verify isolation for imports, jobs, runs, settings, rows, artifacts, reports,
contact history, backups, diagnostics, and support access, including worker restarts.

**Acceptance:** Two organizations with overlapping IDs/names cannot read or alter
one another's data or download links; permissions are enforced by APIs rather
than navigation; background work retains organization context; support access is
controlled and auditable. Extend [store](../server/store.py),
[tenant context](../server/tenant.py), [jobs](../server/jobs.py), and
[worker tests](../tests/test_view_workers.py) as needed.

### G18: Complete hosted recovery and operations

- [ ] G18 complete. Owner: unassigned. Evidence: pending.

Define complete backup coverage, retention, recovery procedure, service monitoring,
job failure handling, upgrades, and named operational responsibility. Include
rows, settings, users as appropriate, original files, report artifacts, and
required configuration; document exclusions and their recovery path.

**Acceptance:** A restoration drill onto a clean supported environment recovers
the documented customer dataset and artifacts; failures produce actionable
diagnostics; tested recovery time and data-loss exposure are recorded against
agreed service targets; upgrade failure has a documented recovery path.
Touchpoints: [backup implementation](../server/backup.py),
[backup guide](release/backup.md), [jobs](../server/jobs.py).

### G19: Implement commercial entitlement lifecycle

- [ ] G19 complete. Owner: unassigned. Evidence: pending.

Define plans, trials, subscriptions, payment status changes, module entitlements,
cancellation, and authorized account export. Preserve a documented desktop
license/update path where offered.

**Acceptance:** Duplicate/out-of-order billing events are handled consistently;
customers cannot grant themselves paid access; modules enforce entitlement on
APIs; cancellation does not unexpectedly delete data; grace and retention policy
are documented. Existing entitlement helpers are reused but administrator settings
alone are not the billing boundary. Touchpoints: [hosted controls](../server/hosted.py),
[hosted API](../server/routers/hosted.py), [organization policy](../server/org_policy.py).

## 7. R1/R2: Support, pilots, and launch

### G20: Publish support and data-handling procedures

- [ ] G20 complete for R1. Owner: unassigned. Evidence: pending.
- [ ] G20 hosted addendum complete for R2. Evidence: pending; requires G18 and G19.

Publish supported environments, formats, modules, currency/locale limits,
installation/refresh guides, support arrangements, diagnostics, and data
export/deletion/retention procedures. Identify who owns regional commercial review.

**Acceptance:** Pilot operators can use the guide; diagnostics avoid exposing
unnecessary customer data; recovery and update instructions match supported builds;
sales/support share the same support matrix. Hosted terms and service claims are
finalized only after the R2 operating and billing decisions. Start from
[release documentation](release/backup.md) and G01's matrix.

### G21: Run measured international pilots

- [ ] G21 complete. Owner: unassigned. Evidence: pending.

Run comparable reviews with at least two external businesses. Capture first-report
time, recurring preparation time, control agreement, usage, completed actions,
observed collection/customer outcomes, locale exceptions, and support effort.

**Acceptance:** Operators independently complete the supported workflows;
reconciliation and international formatting checks are recorded; targets are set
from observed baselines; missing data and confounding business changes are
documented. Update the [pilot baseline record](phase0/07_pilot_baselines_and_gate.md).
Receipts observed after contact are not described as proven incremental recovery.

### G22: Prepare and gate the first international launch

- [ ] G22 complete. Owner: unassigned. Evidence: pending.

Prepare a supported-feature page, pricing proposal, demo dataset, onboarding kit,
sales narrative, and pilot evidence. Select the initial market and deployment offer.

**Acceptance:** All required R1 acceptance items have evidence; material unsupported
workflows are listed; sales claims match tested capabilities; any customer case
study has permission; support ownership is assigned. A hosted launch additionally
requires G16-G19 and G20's hosted addendum. No connector or sector is advertised
as supported solely because an import mapper could theoretically be created.

## 8. R3: Expansion driven by demand

### G23: Select and deliver one demanded connector

- [ ] G23 complete. Owner: unassigned. Evidence: pending.

Select the source most often requested by qualified/paying customers. Assess the
actual API or reliable export interface, data grain, access, operating cost, and
support burden before implementation.

**Acceptance:** The adapter reuses normalized import contracts; repeat sync is
idempotent; source corrections and failures are recoverable; currency/tax/identity
controls reconcile; customers see data freshness. Use [import jobs](../server/import_jobs.py)
and [mappers](../server/mappers.py); document source/version coverage.

### G24: Extend to mixed-currency reporting

- [ ] G24 complete. Owner: unassigned. Evidence: pending.

Define original/reporting amounts, rate source and date, invoice/receipt conversion,
rounding, residuals, and historical reproducibility. Include additional currency
precisions through an explicit supported contract when needed.

**Acceptance:** Mixed currencies cannot be added directly; missing rates produce
an unavailable result; supported invoices/receipts reconcile to source totals;
historic reports preserve the rates used. Finance-domain review precedes release.
Build on G05 and [metric definitions](../vay/metrics.py).

### G25: Add a demanded UI language

- [ ] G25 complete. Owner: unassigned. Evidence: pending.

Choose a language through pilot/customer demand. Externalize user-facing strings,
translate terminology and exports, and support right-to-left layouts if applicable.

**Acceptance:** A fluent reviewer validates the core workflow; text fits desktop
and phone layouts; names/search/imports remain unchanged; dates/numbers follow
source and display policies independently; PDF fonts cover the promised repertoire.
Build on [formatting](../web/src/format.js) and [navigation](../web/src/theme.js).

### G26: Add a validated sector module

- [ ] G26 complete. Owner: unassigned. Evidence: pending.

Select the next sector through customer evidence and document its entities,
metrics, source grain, workflows, and eligibility before building templates.

**Acceptance:** At least two representative businesses can use the shared model
or a deliberate extension; sector-specific metrics have definitions and fixtures;
existing sectors retain their results. Services and manufacturing require their
respective project/time or production/material models. Use the
[domain model](../vay/domain.py) and [broader roadmap](../Vay_Reports_Business_Analytics_Roadmap.md).

## 9. Shared definition of done

- Relevant acceptance criteria have recorded evidence and a named reviewer.
- New-company behavior and existing-customer compatibility are both checked.
- Calculations reuse governed rules; source dates, currency, and missingness remain explicit.
- Imports, jobs, views, and exports enforce the relevant organization/role access.
- Focused tests and workflow checks cover changed contracts and failure cases.
- Support matrix and user documentation describe the released behavior.
- A tested migration/recovery path exists when stored data or configuration changes.

## 10. Initial execution order

1. Complete G01-G02 to establish the cohort, formats, and controls.
2. Start G03-G06 from those exports, then G07-G10 as their dependencies complete.
3. Deliver G11-G14 and verify the full path through G15.
4. Complete R1 support documentation, measured pilots, and launch through G20-G22.
5. Progress G16-G19 for hosted delivery with their own gate; publish G20's addendum.
6. Prioritize G23-G26 from paying-customer demand and the recorded pilot evidence.
