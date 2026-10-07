# Vay Reports: Global Product Strategy

Date: 2026-10-07  
Status: Proposed direction; international release readiness is not yet verified  
Audience: Product, engineering, sales, support, and pilot customers

Execution backlog: [Global product task list](global-product-task-list.md).

## 1. Product direction

Build a configurable management analytics product with a shared core and optional
industry modules. Help owners understand performance, identify work needing
attention, and review the team's progress using data from existing business systems.

Customer promise:

> Connect your business data, understand what needs attention, and turn it into
> clear actions for your team.

The initial international customer is a wholesale, distribution, or product-selling
small or medium business. The strongest workflows are collections, customer
recovery, and inventory decisions. The buyer is an owner or general manager; office
staff prepare data; sales, collection, and purchasing staff execute actions.

Choose the first overseas market through access to representative pilot customers
and their source data. Validate that cohort before extending to more markets.
The current search list is the GCC, the European Union, and the Americas, in the
[global support matrix](global-support-matrix.md). The supported offer is the
fit of two named businesses recorded there.

## 2. Existing foundation and remaining gaps

The current code contains more functionality than the earlier
[product improvement plan](product-improvement-plan.md) describes as proposed.
Use that plan for customer-value requirements; use the inventory below as the
starting point for this internationalization backlog. Presence in code does not
establish that a feature is ready for international production use.

| Foundation present | Evidence | Work needed for international use |
|---|---|---|
| Collection contacts, promises, disputes, and allocations | [Collection workflow](../server/collection.py) | Validate currency, dates, source identity, access, and progress attribution |
| Item holding and demand planning, reservations, incoming stock, and dated costs | [Planning](../server/planning.py), [Item 360](../server/items360.py) | Validate units, source coverage, calculations, and purchase cost currency |
| Daily work, scorecards, weekly review, and report building | [Navigation](../web/src/theme.js), [Analytics](../web/src/Analytics.jsx) | Organize around enabled modules and user roles |
| Cash reporting | [Cash calculations](../server/cash.py) | Validate currency, coverage, payables, and report-date behavior |
| Organization policy | [Policy settings](../server/org_policy.py) | Explicit locale, validated configuration, neutral new-company defaults |
| Saved mappings and a plain-sales preset | [Mappers](../server/mappers.py) | Representative overseas fixtures, source IDs, locale-aware parsing |
| Organization scoping and hosted controls | [Tenant context](../server/tenant.py), [Hosted controls](../server/hosted.py) | Complete hosted onboarding and operational verification |
| Audit and organization backup endpoints | [Hosted API](../server/routers/hosted.py), [Backup guide](release/backup.md) | Test full recovery, including artifacts and settings, for each deployment |

Observed gaps include day-first slash-date parsing, comma stripping in numeric
parsing, global two-decimal helpers, original-business expense seeds, mandatory
sales-representative fields, and overlapping navigation. The backlog covers
these gaps without rebuilding the existing workflows.

## 3. What to keep

| Capability | Product decision | Customer benefit |
|---|---|---|
| Business overview and period comparisons | Keep in the core | A consistent management review |
| Customer profiles and sales trends | Keep in the sales module | Understand account performance |
| Receivables, aging, and collections | Keep in the collections module | Prioritize credit and payment follow-up |
| Contacts, promises, actions, and assignments | Keep as shared workflow capabilities | Turn findings into accountable work |
| Product movement, stock cover, and purchasing | Keep in the inventory module | Connect buying to demand and available stock |
| Excel/CSV import, mapping, and reconciliation | Keep in the core | Use compatible exports from different systems |
| Saved views, exports, and report history | Keep in the core, subject to metric access | Repeat reviews and explain earlier results |
| Roles, audit history, and backup/restore | Keep in the core | Support teams and dependable operation |
| Desktop/LAN deployment | Keep as a supported option | Serve customers preferring local operation |
| Forecasting, consolidation, and custom reports | Keep as advanced options | Serve customers with suitable data and needs |

## 4. What to remove, simplify, or make configurable

These are changes to default behavior, presentation, or packaging. Preserve
existing customer data, identifiers, deep links, and saved definitions.

| Current assumption or presentation | Decision |
|---|---|
| Original customer account names seeded into new companies | Remove from neutral onboarding; retain an explicitly selected legacy template |
| AppSheet as the general product identity | Present supported sources and export templates; retain the AppSheet adapter |
| INR, Asia/Kolkata, April fiscal year, and inclusive 18% tax as unexplained defaults | Ask the new company to confirm its policy; preserve existing saved policies |
| Sales representative required for all sales/receipt imports | Define minimum canonical input and report-specific requirements; leave unsupported dimensions unavailable |
| Customer terms such as Party, ARR, and P.Price exposed everywhere | Use familiar configurable labels while preserving canonical stored fields |
| Related information split across several top-level sections | Give each management workflow one main destination with drill-downs |
| Mapping maintenance, network settings, and reset tools in everyday flows | Put them in administration with appropriate access |
| All report packs shown to every customer | Enable relevant modules and show data readiness for their metrics |
| Advanced report creation during first use | Offer guided templates first; expose advanced controls when relevant |
| Current-cost margin or inferred settlement presented as confirmed history | Keep the analysis with explicit evidence labels or mark it unavailable |

Vay remains the product brand. Remove original-customer assumptions from fresh
installations rather than renaming or discarding the application.

## 5. Product modules and target segments

Use one application and one governed calculation model. Modules change available
workflows, terminology, and templates, not the meaning of the same metric.

| Module | Typical customers | Scope | Minimum data |
|---|---|---|---|
| Sales | Product-selling businesses | Sales comparisons, customer movement, account profiles | Dated sales and supported customer identity |
| Collections | Businesses selling on credit | Receivables, aging, promises, follow-up | Dated sales/receipts and eligible AR/allocation evidence |
| Inventory and Purchasing | Wholesalers, distributors, retailers | Product movement, holding, cover, reorder proposals | Item sales, dated stock, supported units; costs for budgets |
| Management Finance | Businesses with suitable financial exports | Cash, expenses, supported margin analysis | Appropriate dated cash/payables/expense/cost data per metric |
| Advanced Analytics | Customers with deeper reporting needs | Custom reports, scenarios, forecasts, consolidation | Eligible metrics and compatible company data |

Access requires all three of module availability, user permission, and data
eligibility. Enabling a module does not make missing data available or grant a
user additional permissions. Disabling a module must not delete its records.

Initial market order:

1. Wholesalers and distributors, using the existing operational strengths.
2. Other product-selling businesses with compatible invoice and stock data.
3. Additional sectors after pilot evidence establishes the domain requirements.

Services need project, time, and service-revenue models. Manufacturing needs
materials, production, and work-in-progress models. Existing inventory reports
alone do not establish support for those sectors.

## 6. International data contract

### Company policy

Confirm reporting currency, timezone, fiscal-year convention, display locale,
source date/number formats, terminology, and tax basis during onboarding.
Validate unsupported settings explicitly. Existing companies keep their saved
policy; changed calculation policy is versioned with subsequent reports.

Start with documented fiscal years beginning on a calendar-month boundary.
Other fiscal calendars require separate support rather than an approximate label.

### Dates and numbers

- Store normalized business dates and typed values separately from source text.
- Save date and number parsing conventions per source, not only per company.
- Preview ambiguous dates such as `03/04/2026` and require a format choice.
- Interpret `1,234.56` and `1.234,56` using the selected convention; reject
  unsupported or malformed values with a correction path.
- Keep business dates distinct from UTC event timestamps. Apply company timezone
  consistently to today, due status, report windows, and scheduled work.

### Currency

The first international release supports one reporting currency per company.
Each source must establish its currency basis. Accept source-provided reporting
amounts where they reconcile; preserve original amount/currency when supplied.
Do not add mixed-currency amounts without an agreed conversion basis.

Currency code selection alone is not exchange-rate support. Define the supported
currency precision explicitly; current two-decimal helpers need review. Currency
and precision must agree across input, calculations, screens, Excel, and PDFs.
Additional precisions and foreign-exchange calculations are later tasks unless
required by the first pilot cohort.

Useful source-interface references are [Xero organisation settings](https://developer.xero.com/documentation/api/accounting/organisation/)
and [Xero payment exchange rates](https://developer.xero.com/documentation/api/accounting/payments).
These references do not mean Vay currently has a Xero connector.

### Tax and financial basis

Preserve source net, tax, and gross values with their documented meanings. Support
mixed-rate and tax-exempt transactions where the first cohort's sources provide
them. Retain the existing inclusive-rate calculation only as an explicitly
selected, disclosed fallback for compatible sources.

Keep country-specific fields such as SGST/CGST/IGST in adapters or templates.
The first offer is management reporting; statutory filing, payroll, and tax
calculation remain outside the supported scope.

### Identity, locations, and units

Prefer source system, company, transaction ID, and line ID for record identity.
Retain customer/product aliases and legacy keys during migration. Equal amounts
on the same day do not by themselves prove that two invoices are duplicates.

Document product units, pack sizes, quantity precision, and conversion factors.
Do not aggregate incompatible units as one meaningful physical quantity. Preserve
location identity where supported; label single-location or consolidated stock
scope explicitly and avoid implying unverified warehouse-level support.

## 7. First international offer and navigation

Proposed offer: English-language sales, collections, and inventory analytics for
product-selling SMBs, with tested Excel/CSV onboarding and one reporting currency
per company. Final supported markets, formats, currencies, and deployment modes
are selected through pilot intake.

Proposed primary navigation:

| Destination | Purpose |
|---|---|
| Overview | Management scorecard and important exceptions |
| Work | Personal daily tasks and management review |
| Customers | Sales, buying, receivables, and collection context |
| Products | Movement, stock, and purchasing decisions when enabled |
| Reports | Templates, saved reports, history, and exports |
| Administration | Sources, organization policy, users, modules, and maintenance |

Collections and purchasing remain directly reachable through contextual views.
Users see enabled, authorized workflows and useful readiness states. Report-date
views and live operational work identify their data basis clearly.

English UI is the first supported language. Validate customer/product names and
currency symbols in the supported character repertoire across import, screens,
search, Excel, and bundled PDF fonts. Additional languages and right-to-left
layouts require their own release checks.

## 8. Deployment and commercial operation

An international desktop release and a hosted self-service release have different
gates. The desktop path can serve overseas customers while hosted onboarding and
operations are completed. Confirm customer preference during pilots.

| Area | Desktop/LAN requirement | Hosted requirement |
|---|---|---|
| Customer setup | Install, configure, import, and activate the supported modules | Workspace provisioning, invitations, account recovery, and modules |
| Commercial access | Document license and update/support entitlement | Trials, subscriptions, billing lifecycle, and server-enforced entitlement |
| Recovery | Tested application/database/artifact recovery and upgrades | Automated complete backups, tested tenant restoration, monitoring |
| Data access | Roles and customer/rep scope in the install | Organization isolation across API, jobs, files, exports, and support tools |
| Support | Installation diagnostics and a supported-environment matrix | Service status, support diagnostics, and incident ownership |

Publish clear data-handling, export/deletion, retention, and support practices
appropriate to the offered deployment. Select vendors and operating regions
through customer needs. Regional legal review is a separate commercial launch
decision; this document makes no compliance certification claim.

## 9. Release stages and decision gates

| Release | Scope | Gate |
|---|---|---|
| R0: Define and validate | Customer cohort, support matrix, representative exports, baselines | At least two external pilot businesses with usable source data and agreed controls |
| R1: International export-based product | Neutral setup, locale/currency/tax contract, eligible modules, consistent exports, supportable desktop operation | Critical data controls and regressions pass; pilots complete the core workflows; launch scope documented |
| R2: Hosted self-service | Workspace lifecycle, verified isolation, recovery, billing, and operations | Hosted-specific acceptance criteria and commercial operating decisions completed |
| R3: Expansion | Selected connectors, mixed-currency reporting, languages, additional sectors | Prioritize through paying-customer demand and available source evidence |

Roles and dependencies are detailed in the [task list](global-product-task-list.md).
Estimate dates after R0 intake. Do not infer implementation completion from a
planning document or the presence of a similarly named function.

## 10. Pilot measures and sales evidence

Measure time to first reconciled report, recurring preparation time, control-total
agreement, weekly decision-maker usage, action completion, observed receipts,
customer return, and support hours. Reuse the definitions in the
[improvement plan scorecard](product-improvement-plan.md#6-pilot-scorecard).

Add internationalization checks: locale parsing exceptions, currency/tax coverage,
unsupported fields, exported text/number fidelity, and deployment recovery.
Set commercial improvement targets after recording comparable baselines.

Position Vay around workflow convenience and customer fit. Demonstrate collection,
customer recovery, and purchasing using validated prospect exports. Claim only
released, tested support and measured outcomes. Connector compatibility and
additional industry support must be demonstrated before they appear in sales material.

## 11. Relationship to existing documentation

- [Product improvement plan](product-improvement-plan.md): Customer-value workflows
  and pilot measurements. Some formerly proposed foundations now exist in code.
- [Business analytics roadmap](../Vay_Reports_Business_Analytics_Roadmap.md): Broader
  architecture and expansion direction.
- [Buyer and pilots](phase0/01_buyer_and_pilots.md): Original customer and operator definition.
- [Pilot baselines](phase0/07_pilot_baselines_and_gate.md): Intake and evidence tracking.
- [Global support matrix](global-support-matrix.md): GCC, EU, and Americas search list. Regional cells are typical, and the supported offer waits on two named businesses.
- [Global product task list](global-product-task-list.md): Execution checklist and release gates.
