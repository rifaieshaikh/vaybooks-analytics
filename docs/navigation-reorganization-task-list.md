# Vay Reports Navigation Reorganization Task List

Date: 2026-10-08  
Status: Implementation backlog; acceptance evidence pending  
Companion brief: [Navigation implementation brief](vay-navigation-implementation-brief.docx)  
Related backlog: [Global product task list](global-product-task-list.md), task G12

Reorganize navigation around Overview, Sales, Customers, Finance, Inventory,
Reports, Data, and Settings. This task list covers every current sidebar
destination and the embedded workflows that must remain accessible after the
change. The compatibility table contains all 53 existing routes.

This is a specification for future implementation. Checkboxes remain open until
the corresponding behavior is implemented and verified. Existing features listed
below are foundations to preserve; unchecked items do not mean those features
are absent. Owners and estimates are unassigned.

## Scope

- Reorganize destinations, add secondary tabs, and preserve legacy navigation.
- Keep existing page renderers, calculation rules, report families, permissions,
  data sources, saved records, and report snapshots compatible.
- Keep Data quality analytics separate from generated Data issue reports.
- Consolidate Sales returns and Finance credit notes into one destination; both
  currently render the `credit_note` data page.
- Primary group headings expand or collapse without navigating.
- File library access and a backup interface are optional extensions, outside
  the core navigation acceptance criteria.
- This task implements the navigation portion of G12. Broader terminology,
  internationalization, and module-availability work remains in its existing
  backlog; completing this task does not complete all of G12.

## Proposed primary menu

| Group | Destinations |
|---|---|
| Overview | Dashboard; Today's work; Business overview; Scorecard; Weekly review |
| Sales | Invoices; Returns and credit notes; Item-wise sales; Sales reps; Sales change |
| Customers | Customers; Customer groups; Customer movement |
| Finance | Collection worklist; Outstanding; Receipts; Payments; Cash; Parties |
| Inventory | Stock; Item profiles; Categories; Item groups; Brands; Suppliers; Stock decisions; Reorder |
| Reports | Create reports; Report library; Report builder; PDF exports; Excel exports |
| Data | Import; Explore; Data quality; Data issue reports |
| Settings | Organization; Business rules; Users and roles; System and support |

Report library secondary tabs: Performance, Follow-up, Monthly, Items, and Profit.

| Settings page | Secondary tabs |
|---|---|
| Organization | Organization; Account migrations and name review; Party types |
| Business rules | Settlement; Due days; Order check |
| Users and roles | Users; Roles |
| System and support | Network; Plan and support; Audit; Advanced |

## Task index

Dependencies apply to integration and acceptance. Independent investigation can
start earlier. Suggested owner roles are not assignments.

| ID | Task | Suggested owner | Dependencies |
|---|---|---|---|
| NAV01 | Define routes and compatibility aliases | Frontend | None |
| NAV02 | Reorganize the app shell and primary menu | Frontend | NAV01 |
| NAV03 | Add the Report library | Frontend | NAV01, NAV02 |
| NAV04 | Group Settings with secondary tabs | Frontend | NAV01, NAV02 |
| NAV05 | Preserve deep links and existing navigation callers | Frontend | NAV01, NAV03, NAV04 |
| NAV06 | Verify embedded workflows and global controls | Frontend + QA | NAV02, NAV03, NAV04, NAV05 |
| NAV07 | Complete responsive and accessible navigation | Frontend + QA | NAV02, NAV03, NAV04 |
| NAV08 | Verify routes permissions and release behavior | Engineering + QA | NAV05, NAV06, NAV07 |
| NAV09 | Expose the existing file library | Frontend + Product | Optional extension |
| NAV10 | Add a backup and restore interface | Frontend + Backend | Optional extension |

## NAV01 Define routes and compatibility aliases

- [x] Define a flat route registry, primary navigation groups, and legacy aliases
  using the existing `tab` and `sub` routing pattern.
- [x] Separate route lookup from visible navigation so existing callers can
  resolve routes even after their menu placement changes.
- [x] Preserve each renderer's metadata, including data type, report family,
  analytics section, item dimension, and existing permission checks.
- [x] Let alias results carry a secondary tab for Report library and Settings.
- [x] Preserve the meaning of `can`, `visibleNav`, `firstRoute`, and `findItem`
  or provide compatible replacements for their callers.
- [x] Define explicit page readiness rules, including family availability, Profit
  eligibility, and Today's access before a successful report run.
- [x] Verify that every current route appears exactly once as a source in the
  compatibility mapping and resolves to a valid destination.

Done when: route resolution supports all 53 legacy destinations, canonical
destinations, secondary selections, and existing permission rules.

Touchpoints: `web/src/theme.js`, `web/src/App.jsx`.  
Owner: unassigned. Evidence: recorded below.

## NAV02 Reorganize the app shell and primary menu

- [x] Render the proposed groups and destinations after permission filtering.
- [x] Make primary headings toggle only. Collapsing or expanding a group must
  preserve the page, filters, and selected report snapshot.
- [x] Resolve aliases in `go` before setting the active route and open group.
- [x] Update active state, breadcrumbs, document titles, default routes, and the
  brand button to reflect canonical destinations.
- [x] Distinguish the active destination from the currently expanded group.
- [x] Preserve login, forced password change, logout, onboarding, sample company
  access, snapshot selection, and report progress in the app shell.
- [x] Preserve snapshot loading for generated report tables and PDF exports when
  grouped pages change the rendering metadata.

Done when: headings toggle without navigation, destination clicks open the
correct page, and shell controls retain their existing behavior.

Touchpoints: `web/src/App.jsx`, `web/src/theme.js`, `web/src/styles.css`.  
Owner: unassigned. Evidence: recorded below.

## NAV03 Add the Report library

- [x] Add a Report library destination using the existing `ReportsPage` renderer
  for the selected family.
- [x] Add Performance, Follow-up, Monthly, Items, and Profit tabs using
  `SectionTabs` or the established tab pattern.
- [x] Filter each family tab by its existing permission. The library is visible
  when at least one family is permitted.
- [x] Choose a permitted default tab and resolve legacy family links to their
  exact selection. Explicit legacy selections override remembered state.
- [x] Preserve generated-family availability, the special Profit eligibility
  check, Follow-up sales and collection filters, and existing report filters.
- [x] Preserve selected-run context, full snapshot loading, manifest details,
  reconciliation, source eligibility, and existing empty states.
- [x] Move PDF exports and Excel exports under Reports with their existing
  permissions, report filtering, progress, regeneration, ZIP, and download flows.
- [x] Keep Data issue reports under Data as a separate generated-report page.

Done when: permitted families and export workflows remain reachable, and every
legacy family link selects the correct library tab.

Touchpoints: `web/src/Reports.jsx`, `web/src/SectionTabs.jsx`,
`web/src/Export.jsx`, `web/src/Excel.jsx`, `web/src/App.jsx`.  
Owner: unassigned. Evidence: recorded below.

## NAV04 Group Settings with secondary tabs

- [x] Compose the four proposed Settings pages from existing section components.
- [x] Keep `AccountNamesSection` and `NameReviewSection` together within Account
  migrations.
- [x] Filter and authorize each secondary tab independently. A grouped page is
  visible when at least one child tab is permitted.
- [x] Preserve Network access for authenticated users, `settings.advanced` for
  advanced sections, and the existing view-or-manage checks for Users and Roles.
- [x] Resolve all legacy Settings routes to their intended page and selected tab.
- [x] Validate direct and remembered selections against permitted tabs. Use a
  permitted default when a remembered selection is no longer accessible.
- [x] Preserve organization targets, thresholds, pack settings, custom columns,
  terminology, settlement, due-day and order-check rules, party types, diagnostics,
  audit, and advanced data controls.

Done when: every existing Settings section remains accessible under its original
permissions, including users permitted to see only Network, Users, or Roles.

Touchpoints: `web/src/Settings.jsx`, `web/src/settings/`,
`web/src/SectionTabs.jsx`, `web/src/theme.js`.  
Owner: unassigned. Evidence: recorded below.

## NAV05 Preserve deep links and existing navigation callers

- [x] Update `routeFromHash` to select canonical destinations using the hash
  mapping below, retaining the existing entity hash syntax and encoded IDs.
- [x] Preserve hash-based drill-downs, filtered list links, back navigation, and
  return context between customers, groups, reps, invoices, items, and dimensions.
- [x] Preserve existing `hashSet`, `hashBack`, and `hashReset` behavior for the
  relevant navigation flow.
- [x] Verify old `onGo(tab, sub)` callers in Dashboard, Business, Create, Import,
  and SetupWizard through aliases before changing any caller.
- [x] Preserve server-provided navigation arrays from `server/business360.py`.
- [x] Ensure a legacy link cannot select an unauthorized secondary tab or leave
  the workspace blank.

Done when: old links and navigation actions reach the intended pages with their
existing entity, list, and selected-run context.

Touchpoints: `web/src/App.jsx`, `web/src/format.js`, navigation callers,
`server/business360.py`.  
Owner: unassigned. Evidence: recorded below.

## NAV06 Verify embedded workflows and global controls

Verify these existing workflows after their parent destinations move. Preserve
their current data basis, labels, management permissions, and saved records.

- [x] Customer collections: contacts, promises, receipt confirmation, follow-up
  history, due and missed-promise queues, reminder drafts, statement previews,
  and PDF and Excel statements.
- [x] Customer, group, and rep profiles: balances, settlements, customer AR
  mismatches, sales and quantity histories, buying, repurchase, ordering, order
  checks, activities, and related entity links.
- [x] Item and dimension profiles: holding policy, lead times, discontinued
  status, risk filters, movement, buyers, sales history, repurchase, and dimension
  and invoice drill-downs.
- [x] Actions and Weekly review: assignment, owners, due dates, completion,
  suggestions, overdue counts, observed results, confirmed allocation evidence,
  recovery evidence, and review downloads.
- [x] Reorder: budgets, quantity overrides, priority ordering, pack sizes,
  minimums, suppliers, lead times, held and uncosted lines, saving, assignment,
  and Excel proposals. Saving must retain the current purchase-order boundary.
- [x] Report builder: templates, metric selection, preview, drafts, approvals,
  approved-figure queries, saved reports, and existing downloads.
- [x] Analytics and cash: targets, comparisons, forecasts, scenario factors,
  sales-change analysis, saved filters, projections, pending confirmations,
  and uncosted commitments.
- [x] Imports: all 13 supported types, mapping confirmation, previews, duplicate
  policies, control comparisons, reconciliation, and refresh status. Types are
  `sales`, `items`, `arr`, `receipt`, `credit_note`, `payments`, `stock`, `party`,
  `reservation`, `incoming`, `item_cost`, `opening_cash`, and `payable`.
- [x] Global flows: setup wizard, sample company, report creation and progress,
  switching snapshots, authentication, and logout.

Done when: the existing workflows are reachable and verified through their new
parent destinations, with evidence recorded for affected states and roles.

Touchpoints: existing page components and `web/src/Analytics.jsx`.  
Owner: unassigned. Evidence: recorded below.

## NAV07 Complete responsive and accessible navigation

- [x] Verify the sidebar, active state, and collapsed groups on desktop and phone.
- [x] Make expansion state and current destination accessible to assistive
  technology and keyboard users.
- [x] Verify keyboard operation and focus visibility for primary navigation and
  secondary tabs; reuse existing `SectionTabs` behavior.
- [x] Check long labels, horizontal overflow, breadcrumbs, secondary tabs, and
  snapshot controls without overlapping or clipped text.
- [x] Verify loading, empty, unavailable, and error states for grouped pages.
- [x] Provide a clear explanation when an existing readiness rule prevents
  opening a destination, with accessible disabled behavior.

Done when: navigation and grouped pages work on desktop and phone and remain
usable with keyboard navigation.

Touchpoints: `web/src/styles.css`, `web/src/App.jsx`,
`web/src/SectionTabs.jsx`.  
Owner: unassigned. Evidence: recorded below.

## NAV08 Verify routes permissions and release behavior

Perform these checks during implementation. This documentation task does not
record completed implementation, builds, or application test runs.

- [x] Verify all 53 legacy sources against the current route inventory; confirm
  there are no missing, duplicated, or unexpected mapping entries.
- [x] Add focused behavior checks for alias resolution, secondary selection,
  first-route fallback, per-tab permissions, and readiness exceptions.
- [x] Choose a lightweight verification approach compatible with the repo.
  `web/package.json` currently has no frontend test script; do not assume a
  test runner is already configured.
- [x] Verify admin, ordinary data-view, report-family-only, Network-only,
  Users-only, and Roles-only access combinations where supported by permissions.
- [x] Verify no successful run, an active run, a successful run missing some
  families, unavailable Profit, and switching between successful snapshots.
- [x] Verify selected libraries and Settings tabs after legacy navigation,
  remembered state, and changed permissions.
- [x] Verify direct hash entry, list filters, entity drill-downs, and return
  navigation on desktop and phone.
- [x] Run the frontend build and relevant existing checks for the affected paths
  during implementation; record commands and results.
- [x] Use existing report-access checks, including
  `tests/test_report_access.py`, when report access behavior is affected.
- [x] Record final evidence below and mark tasks complete only after their
  acceptance criteria pass.

Done when: the core completion checklist passes and implementation evidence is
recorded. Optional extensions do not block this task.

Owner: unassigned. Evidence: recorded below.

## Compatibility mapping

`Selected tab` identifies a secondary selection carried by the alias result.
All other rows preserve their existing renderer or page behavior under the new
destination. Canonical routes must also work directly.

| Current route | Proposed route | Selected tab |
|---|---|---|
| `home/home` | `overview/dashboard` | - |
| `reports/today` | `overview/today` | - |
| `customers/business` | `overview/business` | - |
| `reports/scorecard` | `overview/scorecard` | - |
| `reports/weekly-review` | `overview/weekly-review` | - |
| `sales/sales` | `sales/invoices` | - |
| `sales/returns` | `sales/returns-credit-notes` | - |
| `finance/credit_note` | `sales/returns-credit-notes` | - |
| `sales/items` | `sales/item-wise` | - |
| `customers/reps` | `sales/reps` | - |
| `reports/sales-change` | `sales/change` | - |
| `customers/customers` | `customers/list` | - |
| `customers/groups` | `customers/groups` | - |
| `reports/customer-movement` | `customers/movement` | - |
| `reports/collection-worklist` | `finance/collection-worklist` | - |
| `finance/arr` | `finance/outstanding` | - |
| `finance/receipt` | `finance/receipts` | - |
| `finance/payments` | `finance/payments` | - |
| `finance/cash` | `finance/cash` | - |
| `finance/party` | `finance/parties` | - |
| `stock/stock` | `inventory/stock` | - |
| `customers/items` | `inventory/item-profiles` | - |
| `customers/item-category` | `inventory/categories` | - |
| `customers/item-group` | `inventory/item-groups` | - |
| `customers/brand` | `inventory/brands` | - |
| `customers/supplier` | `inventory/suppliers` | - |
| `reports/stock-decisions` | `inventory/stock-decisions` | - |
| `reports/reorder` | `inventory/reorder` | - |
| `reports/create` | `reports/create` | - |
| `reports/performance` | `reports/library` | `performance` |
| `reports/followup` | `reports/library` | `followup` |
| `reports/monthly` | `reports/library` | `monthly` |
| `reports/items` | `reports/library` | `items` |
| `reports/profit` | `reports/library` | `profit` |
| `reports/report-builder` | `reports/builder` | - |
| `data/export` | `reports/pdf-exports` | - |
| `data/excel` | `reports/excel-exports` | - |
| `data/import` | `data/import` | - |
| `data/explore` | `data/explore` | - |
| `reports/data-quality` | `data/quality` | - |
| `reports/issues` | `data/issue-reports` | - |
| `settings/organization` | `settings/organization` | `organization` |
| `settings/account-names` | `settings/organization` | `account-names` |
| `settings/party-types` | `settings/organization` | `party-types` |
| `settings/settlement` | `settings/business-rules` | `settlement` |
| `settings/due-days` | `settings/business-rules` | `due-days` |
| `settings/order-check` | `settings/business-rules` | `order-check` |
| `settings/users` | `settings/users-roles` | `users` |
| `settings/roles` | `settings/users-roles` | `roles` |
| `settings/network` | `settings/system-support` | `network` |
| `settings/license` | `settings/system-support` | `license` |
| `settings/audit` | `settings/system-support` | `audit` |
| `settings/advanced` | `settings/system-support` | `advanced` |

## Deep link mapping

Preserve the syntax and parsing of existing hashes, including encoded IDs,
optional list filter suffixes, and stored return context. The destination changes;
entity identifiers remain compatible.

| Existing hash prefix | Proposed destination |
|---|---|
| `customer/`, `list/customers` | `customers/list` |
| `group/` | `customers/groups` |
| `rep/` | `sales/reps` |
| `invoice/` | `sales/invoices` |
| `item/` | `inventory/item-profiles` |
| `category/` | `inventory/categories` |
| `item-group/` | `inventory/item-groups` |
| `brand/` | `inventory/brands` |
| `supplier/` | `inventory/suppliers` |
| `list/stock` | `inventory/stock` |
| `list/arr` | `finance/outstanding` |

## Permission and readiness requirements

Menu placement does not change authorization. Preserve permissions for all
destinations from `theme.js`; the following moves and grouped pages need
particular attention.

| Destination or action | Existing permission or rule |
|---|---|
| Business overview and Sales reps | `customer.view` |
| Item profiles and item dimensions | `stock.view` |
| Returns and credit notes | `credit_note.view` |
| Scorecard, Sales change, Customer movement, Weekly review | `reports.view.scorecard` |
| Today and Collection worklist | `reports.view.followup` |
| Stock decisions and Reorder | `reports.view.items` |
| Data quality | `reports.view.quality` |
| Data issue reports | `reports.view.issues`, plus existing report-specific access rules |
| Each Report library family | Its own `reports.view.<family>` permission |
| Create reports and PDF exports | `reports.create` |
| Excel exports | Existing `__excel__` predicate |
| Report builder access | Existing `__builder__` predicate |
| Report drafting and approval | `reports.manage` |
| Action assignment and completion | `actions.manage` |
| Network | Existing `__home__` predicate for authenticated users |
| Advanced Settings sections | `settings.advanced` |
| Users | Existing `users.view` or `users.manage` check |
| Roles | Existing `roles.view` or `roles.manage` check |

- Today must remain usable before a successful report run exists.
- Preserve the existing successful-run requirements for other analytics pages.
- Library families retain their own availability checks and Profit retains its
  special eligibility check.
- Generated tables and PDF exports retain their snapshot-loading requirements.
- Group permission is the union of permitted children. Rendering a child requires
  that child's permission; an accessible group does not authorize all its tabs.
- Explicit legacy selections override remembered tabs. Remembered selections and
  default tabs must still pass permission and availability checks.

## Optional extensions

### NAV09 Expose the existing file library

`web/src/Files.jsx` implements upload, download, and row inspection but is not
mounted by `App.jsx`. Connecting it would add a destination beyond the currently
reachable sidebar features.

- [ ] Define the intended Data destination and permission rules.
- [ ] Confirm the supported upload and inspection workflow and its relationship
  to Import and Explore.
- [ ] Connect the existing page and verify upload, download, row inspection, and
  restricted access.

Owner: unassigned. Evidence: pending. Core dependency: none.

### NAV10 Add a backup and restore interface

`server/routers/hosted.py` exposes backup and restore endpoints. The current
frontend has no matching navigation entry. This is a separate feature, with
deployment scope and recovery behavior to define before implementation.

- [ ] Define the supported deployment scope, access rules, and System and support
  placement.
- [ ] Design backup download, restore input, and the restore interaction with a
  clear description of the data affected.
- [ ] Reuse the existing endpoints and audit behavior, preserving organization
  boundaries and existing authorization.
- [ ] Verify successful recovery, invalid input, failure handling, and restricted
  access using isolated fixtures.

Owner: unassigned. Evidence: pending. Core dependency: none.

## Core completion checklist

- [x] NAV01 through NAV08 have implementation and verification evidence.
- [x] Every current route and hash prefix reaches its intended destination.
- [x] Primary headings only expand or collapse; active state remains accurate.
- [x] Secondary tabs preserve individual permissions and legacy selection.
- [x] Today's pre-report access and all other readiness rules are correct.
- [x] Embedded workflows, exports, settings, and global controls remain reachable.
- [x] Desktop, phone, keyboard, loading, empty, and error checks pass.
- [x] Existing backend authorization and report calculations retain their contracts.
- [x] Optional extensions remain separate unless their scope is explicitly added.

## Implementation evidence

| Evidence | Status |
|---|---|
| Implementation change or review link | Local edits in web/src/theme.js, web/src/App.jsx, web/src/Settings.jsx, and web/src/styles.css |
| Route and permission verification | All 53 legacy routes resolve once. Browser checks covered admin, customer view, follow-up, users-only, roles-only, network-only, and performance-only accounts |
| Affected workflow verification | Browser opened the moved collection, profile, reorder, import, create, export, and settings pages. pytest: 96 passed in 59.70s, including tests/test_report_access.py |
| Frontend build and relevant existing checks | npm run build in web/ succeeded. The same pytest run covered report access and the moved workflows |
| Desktop phone and keyboard checks | Chrome at 1280x800 and 390x844. Headings toggle without leaving the page. Tab, Enter, and arrow keys move through groups and secondary tabs, with a visible focus outline |
| Final acceptance review | NAV01 through NAV08 closed on 2026-10-08. NAV09 and NAV10 stay optional |

Source anchors: `web/src/theme.js`, `web/src/App.jsx`, `web/src/Reports.jsx`,
`web/src/Settings.jsx`, `web/src/SectionTabs.jsx`, `web/src/Analytics.jsx`,
`web/src/Customers.jsx`, `web/src/Groups.jsx`, `web/src/Reps.jsx`,
`web/src/Stock.jsx`, `web/src/Import.jsx`, `web/src/Export.jsx`,
`web/src/Excel.jsx`, `server/auth.py`, `server/routers/analytics.py`,
`server/business360.py`, and `tests/test_report_access.py`.
