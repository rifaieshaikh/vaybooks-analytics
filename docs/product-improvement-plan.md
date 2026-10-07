# Vay Reports: Product Improvement Plan

Date: 2026-10-07  
Status: Proposed improvements; implementation and customer validation pending  
Audience: Product owner, engineering team, sales, and pilot operators

For international customer targeting and implementation tasks, see the
[Global product strategy](global-product-strategy.md) and
[Global product task list](global-product-task-list.md). Their current-code
inventory includes foundations added since this improvement assessment; recheck
implementation evidence before treating an earlier proposal as unimplemented.

## 1. Purpose and customer promise

Make Vay more valuable to wholesale and distribution businesses by helping them
complete three recurring decisions:

1. Whom to collect from and what to follow up next.
2. Which customers need attention to recover or retain sales.
3. What stock to buy, how much to buy, and when.

The customer promise is:

> Turn your business data into a weekly plan to collect cash, recover sales,
> and control stock.

The buyer is the owner or general manager. The operator imports data and prepares
reports. Salespeople, collection staff, and purchasing staff carry out the work.
This follows the existing [buyer definition](phase0/01_buyer_and_pilots.md).

Sell improvements through observable customer outcomes: less preparation,
clearer decisions, and more consistent follow-through. Quantified revenue,
collection, or inventory benefits require pilot evidence.

## 2. Current foundation

The following capabilities exist in the inspected code. This is an implementation
inventory, not certification of production readiness or evidence of customer ROI.

| Capability | Existing foundation | Improvement opportunity |
|---|---|---|
| Collections | Aging, customer profiles, collection worklists, assigned actions | Contact history, promises, disputes, and invoice-linked progress |
| Customer recovery | Sales comparisons, customer movement, repurchase analysis | A daily worklist combining these signals with credit and stock context |
| Purchasing | Item holding policies, selling pace, buy quantities, reorder drafts, pack rounding, budgets | Consistent quantities between Item 360 and Reorder; clearer assumptions |
| Onboarding | Import wizard, saved mappings, previews, eligibility checks | Tested source templates and a repeatable refresh workflow |
| Trust | Reconciliation, run manifests, provenance, data warnings | Number explanations and freshness for each source |
| Management review | Weekly suggestions, owners, due dates, statuses, observed outcomes | Clearer progress measurement and receipt attribution |

Key implementation references:

- [Analytics and action screens](../web/src/Analytics.jsx).
- [Actions and observed outcomes](../server/actions.py).
- [Action, review, and reorder API](../server/routers/actions.py).
- [Item planning](../server/items360.py).
- [Reorder draft calculation](../server/reorder.py).
- [Import wizard](../web/src/Import.jsx) and [onboarding checks](../server/phase2.py).
- [Dashboard](../server/dashboard.py) and [reconciliation](../server/reconcile.py).

This plan complements the broader [business analytics roadmap](../Vay_Reports_Business_Analytics_Roadmap.md).
Existing roadmap features should be extended through their current modules.

## 3. Priorities

Priority reflects recommended business value and dependencies, not measured ROI.
Assign delivery dates after engineering estimates and pilot intake.

| ID | Improvement | Delivery priority | Customer value | Dependencies |
|---|---|---|---|---|
| IMP-01 | Complete collection follow-up | First release | Payment promises and next steps stay visible | Customer identity, actions, receipts, allocation evidence |
| IMP-02 | Dependable reorder quantities | First release | Purchase quantities reflect demand and holding policy | Item sales, dated stock, holding settings, cost eligibility |
| IMP-03 | Easier onboarding and refresh | First release | Reach useful reports sooner and refresh consistently | Real customer exports, mapping, reconciliation |
| IMP-04 | Daily salesperson worklist | Following release | Know which accounts to contact and why | IMP-01, repurchase signals, customer access rules |
| IMP-05 | Explain important numbers | Basic coverage in first release; extend afterward | Understand and verify decisions | Saved run metadata, provenance, reconciliation |
| IMP-06 | Management results view | Baseline capture in first release; extend afterward | Review progress and observed results | IMP-01, action history, fresh imports |

## 4. Improvement specifications

### IMP-01: Complete collection follow-up

**Problem:** An assigned collection task does not capture the full conversation.
The current action statuses are `open`, `done`, and `dropped`. A salesperson can
mark work done without recording the customer's promise or the remaining amount.

**Proposed scope**

- Add a contact timeline with date, staff member, channel, note, and next step.
- Record payment promises with amount, promised date, and related invoices when known.
- Track disputes and partial payments separately from task completion.
- Add a next follow-up date and lists for due follow-ups and missed promises.
- Link receipts to promises or invoices using source allocations or explicit,
  auditable confirmation. Clearly label inferred matching.
- Provide a customer statement and reminder draft using existing PDF/export
  capabilities, with staff review before sending.

Keep task status and payment status separate. Completing a call does not mean an
invoice is paid. Existing actions should remain readable without new fields.

**Example:** A customer promises 40,000 by Friday. An allocated receipt of 15,000
leaves 25,000 against the promise and a follow-up due. These are illustrative
amounts, not customer results.

**Acceptance criteria**

- Staff can record a contact, promise, dispute, and next follow-up from the customer
  profile or collection worklist.
- Partial payments update the remaining promised amount without automatically
  completing unrelated work.
- Receipt reuse cannot inflate totals across several tasks for the same customer.
- A missed promise requires the relevant receipt data to be current; otherwise
  the view explains that payment confirmation is pending a refresh.
- Contact edits and payment confirmations preserve who changed them and when.
- Viewing, editing, and exports respect organization and customer access rules.

**Engineering touchpoints:** Extend `server/actions.py`, `server/schemas.py`,
`server/routers/actions.py`, and the existing customer/analytics screens. Add
focused coverage to [action tests](../tests/test_phase3.py) for partial payments,
multiple promises, corrected imports, access, and existing records.

**Sales message:** Every collection conversation has a next step, and payment
promises stay visible.

### IMP-02: Dependable reorder quantities

**Problem:** Item 360 already calculates a buy quantity from holding settings.
However, `build_reorder()` currently uses `on_hand` as the default draft quantity
when no manual quantity is supplied. The draft can therefore differ from the item
recommendation. Lead days are stored in the draft but do not size that quantity.

**Proposed scope**

- Use one planning result across Item 360, Stock decisions, and Reorder.
- Start with the existing holding-based `buy_qty` and buy-by date rather than
  using on-hand stock as a proposed purchase quantity.
- Show selling pace, holding target, stock date, lead time, and the reason to buy.
- Allow documented overrides; preserve both the calculated and edited quantity.
- Apply pack rounding and minimum order quantities only to a positive purchase
  requirement. Respect discontinued items and zero-buy recommendations.
- Prioritize budget allocation by an explicit, visible rule, with manual ordering
  available. Explain deferred lines and quantities increased by pack rounding.
- Treat missing purchase costs as uncosted lines, not free purchases.

**Later extension:** When customer exports provide reservations and incoming
purchase orders, add inventory position and a demand-based target. Incoming stock
must have a quantity and expected arrival date; a late delivery cannot resolve an
earlier shortage. Disclose missing inputs instead of silently treating them as zero.

Illustrative demand-based rule, subject to pilot policy agreement:

```text
target units = daily demand * (lead days + review days) + safety stock units
inventory position = on-hand - reservations + eligible confirmed incoming units
purchase requirement = max(0, target units - inventory position)
proposed quantity = pack-rounded positive requirement, respecting the order minimum
```

For illustration, demand of 10 units/day, lead time of 5 days, a 7-day review
interval, and safety stock of 20 units produce a target of 140. With confirmed
inventory position of 90, the requirement is 50; a pack size of 12 produces 60.
This extension is not the current implemented formula.

**Acceptance criteria**

- Item 360 and Reorder agree on the unedited base recommendation for the same
  data, report date, and policy. Pack/minimum adjustments are shown separately.
- A zero requirement stays zero even when the supplier has an order minimum.
- Discontinued items are excluded from automatic purchase suggestions.
- Budget totals use eligible source costs. An uncosted line cannot be reported
  as fitting a fixed budget.
- Manual quantities are nonnegative, remain distinguishable from suggestions,
  and are marked for review when refreshed data changes the calculation.
- Stock and demand freshness are visible. Insufficient data produces a reason
  or an explicitly qualified recommendation.
- Saving a proposal retains the existing boundary: it does not post a purchase
  order into the operational system.

**Engineering touchpoints:** Reuse `server/items360.py`; align
`server/reorder.py`, `server/routers/actions.py`, and `vay/phase3.py`. Cover policy
agreement, zero demand, pack/minimum behavior, missing costs, and budget selection
in the existing item and action tests.

**Sales message:** Understand how much to buy, when to buy it, and why.

### IMP-03: Easier onboarding and refresh

**Problem:** Saved mappings help repeat imports, but each new business still needs
its source exports understood and validated. The current flow requires exports,
imports, and report creation; it has no live AppSheet connection.

**Proposed scope**

- Collect representative exports from at least two external businesses and ship
  tested mapping presets for those actual formats.
- Provide a source checklist covering required sheets, fields, transaction dates,
  snapshot effective dates, and control totals.
- Guide the operator through import, identity issues, reconciliation, and the
  first useful report. Explain which decisions the available data supports.
- Remember the import mode and settings for each source while previewing changed
  formats, duplicates, and replacements before commit.
- Offer a concise refresh sequence and show whether a new successful report
  includes the latest imported batches.

**Connector decision:** Select one source only after confirming which system
paying customers use. Assess a watched export folder where exports can be
produced reliably, or a supported connector where recurring manual effort is
material. TallyPrime offers documented XML, JSON, and ODBC integration options;
this is a feasibility starting point, not a supported Vay connection today.
See [Tally integration documentation](https://help.tallysolutions.com/integration-methods-and-technologies/)
(consulted 2026-10-07).

**Acceptance criteria**

- Each shipped preset has a representative fixture and documented supported shape.
- A new operator can complete import, reconciliation, and report creation using
  the guide without changing report code.
- Repeat imports do not double-count transactions; corrections follow the
  selected update/replace policy and remain traceable.
- Schema changes are surfaced before a saved mapping is reused incorrectly.
- Headline sales and AR reconcile to agreed export totals; exceptions are visible.
- Upload completion and report completion have distinct states and dates.
- Any automated refresh reuses existing validation and import controls.

**Engineering touchpoints:** Extend `web/src/Import.jsx`, `web/src/SetupWizard.jsx`,
`server/phase2.py`, and `server/import_jobs.py`. Reuse mapper presets and pilot
intake in [server/pilots.py](../server/pilots.py); extend existing import tests.

**Sales message:** Your regular exports become a repeatable management routine.

### IMP-04: Daily salesperson worklist

**Problem:** Useful signals exist across customer profiles, repurchase analysis,
collections, and weekly review. Staff need a convenient view of their next work.

**Proposed scope**

- Combine assigned follow-ups, missed promises, repurchase opportunities, inactive
  accounts, and orders needing review into a personal daily queue.
- Explain each entry with the source signal, age, relevant products, and credit
  position. Distinguish observed sales value from estimated opportunity value.
- Support recording contacts and outcomes directly from the queue.
- Use visible ordering rules and show blocked opportunities, such as insufficient
  stock or unresolved credit issues, with an appropriate next step.
- Support comfortable phone use and retain desktop access for managers.

**Acceptance criteria:** A salesperson sees authorized accounts only; a manager
can review permitted staff queues; duplicate signals do not create duplicate
tasks; completed work leaves the active queue while retaining history; each
recommendation links to its evidence and data date.

**Engineering touchpoints:** Reuse [repurchase analysis](../server/repurchase.py),
customer profiles, actions, and order checks. Define server-side customer/rep
scope before exposing a personal queue; navigation filtering alone is insufficient.

**Sales message:** Start the day knowing which customers need your attention.

### IMP-05: Explain important numbers

**Problem:** Provenance and reconciliation exist, but decision-makers need those
details close to the figures and recommendations they use.

**Proposed scope**

- Add number-detail views for sales, AR, collection progress, and stock decisions.
- Show formula, date window, included source records, and reconciliation result.
- Show freshness per source using effective dates and transaction coverage,
  alongside upload time. A recent upload alone does not prove current coverage.
- Label source-confirmed allocation, inferred settlement, snapshot-cost estimate,
  and unavailable historical cost distinctly.
- Show when a recommendation combines datasets with different coverage dates.

**Acceptance criteria:** An authorized user can explain a headline number using
its source evidence; missing data stays unavailable; saved official reports retain
their original data/calculation basis; live follow-up views identify their latest
data basis; detail screens and exports enforce the same access rules.

**Engineering touchpoints:** Extend run manifests, `server/dashboard.py`,
`server/reconcile.py`, and existing dashboard/analytics screens. Reuse eligibility
rules and metric definitions rather than introducing separate UI calculations.

**Sales message:** You can explain the numbers you use to run the business.

### IMP-06: Management results view

**Problem:** Current outcomes observe receipts or sales after assignment. These
observations are useful, but they do not prove invoice settlement or that an action
caused the payment or sale. Managers also need visibility into incomplete work.

**Proposed scope**

- Show open and overdue actions, contacts completed, and promises kept or missed.
- Separate verified allocated receipts from customer-level receipts observed
  after a follow-up. Prevent duplicate receipt attribution across tasks.
- Show customers who bought again after contact with the relevant transaction.
- Evaluate stock risk using the relevant later stock data and planning policy,
  rather than interpreting every increase in on-hand quantity as a resolved risk.
- Capture preparation time and review usage with consistent definitions.

**Acceptance criteria:** Every result has a date basis and evidence; repeated
follow-ups cannot multiply received totals; missing later imports show pending
confirmation; comparisons use consistent scope; outcome labels describe observed
results without claiming unproven revenue or savings attribution.

**Engineering touchpoints:** Extend `server/actions.py`, `vay/phase3.py`, and weekly
review in `web/src/Analytics.jsx`; reuse action and transaction history.

**Sales message:** Review progress as well as performance.

## 5. Delivery sequence and release gates

### Stage A: Pilot setup and baselines

Collect representative exports, agree control totals and data coverage, and record
the current reporting workflow. Confirm the collection and holding policies with
the owner. Assign a product owner and pilot operator for each business.

**Gate:** At least two external pilot datasets are received, their field mappings
are documented, and agreed sales/AR controls can be checked. Update the existing
[pilot baseline document](phase0/07_pilot_baselines_and_gate.md), whose recorded
numeric baselines are currently unset.

### Stage B: First customer-value release

Deliver IMP-01, the core consistency changes in IMP-02, and the guided/manual
refresh scope of IMP-03. Include source dates, payment matching labels, and
uncosted purchase handling from IMP-05, plus basic measurement from IMP-06.

**Gate:** Pilot users independently record collection conversations, review
consistent reorder quantities, and refresh reconciled reports. Required focused
regressions pass, and no unresolved data ambiguity is presented as a confirmed result.

### Stage C: Daily execution and broader evidence

Deliver IMP-04, richer explanations, and the fuller results view. Choose a connector
only if pilot evidence establishes demand and a supportable source interface.

**Gate:** Pilot staff use their queues repeatedly, managers review progress, and
onboarding/support effort is measured. Set adoption targets after Stage A.

### Later candidates

- Cash planning, once opening cash, payables, payment promises, and commitments
  are available with suitable dates.
- Demand planning with backtesting and explicit seasonality, after consistent
  historical sales and stock coverage are established.
- Historical margin analysis, when historical costs can be justified; current
  purchase-price estimates remain explicitly labeled.

Prioritize these using customer demand and source availability.

## 6. Pilot scorecard

Agree definitions and observation windows before measuring. Targets below are
intentionally unset until baseline evidence exists.

| Measure | Definition | Evidence | Target |
|---|---|---|---|
| Time to first trusted report | Elapsed time from first upload to owner review of reconciled sales/AR | Onboarding timestamps and owner confirmation | Set after baseline |
| Recurring preparation time | Operator minutes to refresh and prepare the agreed review | Time log for comparable reviews | Set after baseline |
| Reconciliation coverage | Agreed period controls that pass / controls checked; report unchecked controls separately | Export totals and run checks | All required controls pass or have an explained, accepted exception |
| Weekly decision-maker usage | Distinct authorized decision-makers reviewing the product in a week | Usage events or pilot log | Set after baseline |
| Action completion | Actions completed by due date / actions due in the window | Action history; show dropped actions separately | Set after baseline |
| Payment promise fulfilment | Fully settled promises due in the window / promises due; show partial and data-pending separately | Promise and allocation records | Set after baseline |
| Collection receipts | Unique allocated receipts against followed-up invoices; show unallocated observations separately | Receipt/allocation evidence | Observe; no causal guarantee |
| Customer return | Contacted inactive customers with a later eligible sale / contacted inactive customers with sufficient follow-up coverage | Contact and sales records | Set after baseline |
| Stock risk resolution | Reviewed risks resolved under the same policy using later eligible stock data | Dated stock and planning evidence | Set after baseline |

Compare similar periods and scope. Record changes in credit policy, territories,
promotions, and source coverage that could affect results. Publish a customer case
study only when the evidence and customer permission support it.

## 7. Shared implementation requirements

- Keep official Create calculations over the full stored dataset and chosen
  report date; exploratory filters do not change official totals.
- Reuse current engine rules, persistence, organization scoping, and permissions.
- Preserve compatibility with existing actions, saved proposals, and report runs.
- Separate transaction dates, snapshot effective dates, upload timestamps, and
  the date an action was recorded.
- Account for returns, credit notes, receipt corrections, and repeated imports
  when determining remaining balances and observed results.
- Do not reconstruct an earlier stock/AR position from a newer snapshot without
  adequate historical evidence.
- Treat contact records, payment promises, and proposals as operational metadata;
  they do not post transactions back to the source system.
- Add focused behavior tests and desktop/phone workflow checks for changed paths.
  Broaden validation where shared calculations, imports, or permissions change.

## 8. Decisions to resolve during pilots

| Decision | Owner | Evidence needed |
|---|---|---|
| First source template and eventual connector | Product and sales | Actual paying-customer systems, export effort, representative files |
| Reliable invoice/receipt linkage | Engineering and pilot finance operator | Stable invoice references and allocation data |
| Collection priority and escalation rules | Pilot owner and collection lead | Credit terms, disputes, contact practice, policy exceptions |
| Demand window, holding target, and lead-time defaults | Pilot purchasing lead | Sales history, supplier lead times, unit/pack conventions |
| Personal queue access and assignment | Product and pilot owner | Territory ownership, shared accounts, manager access |
| Definition of a resolved stock risk | Product and purchasing lead | Consistent policy and comparable later stock snapshots |
| Adoption and time-saving targets | Product and pilot owner | Recorded baseline reviews and follow-up outcomes |

## 9. Sales demonstration for the improved release

Use the prospect's validated exports where possible:

1. Open a customer needing collection and explain the balance and data date.
2. Record a payment promise, assign the next contact, and show how partial payment
   will be confirmed after the next refresh.
3. Open a stock risk and explain the base purchase quantity, pack adjustment,
   budget, and assumptions.
4. Identify a customer recovery opportunity and assign the follow-up.
5. Show the management review with owners, due dates, and evidence of progress.

Position the product around convenience and fit for wholesale operations. Current
ERPs already offer substantial reporting and collection capabilities; differentiation
must be demonstrated through the customer's actual workflow. Use measured pilot
results for quantified claims, and describe proposed features as planned until released.
