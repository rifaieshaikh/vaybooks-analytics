# Vay Reports: Features That Help Sell the Product

Date: 2026-10-07  
Status: Proposed priorities; delivery scope and customer outcomes need validation

Implementation checklist: [Product sales feature task list](product-sales-task-list.md).

## Product promise

For wholesale and distribution businesses, the strongest sales message is:

> Know whom to collect from, what stock to buy, and what work your team must do today.

Sell the value of completing these daily decisions. Demonstrate the workflow with
realistic sample data, then validate it using a customer's own exports.

This document records the feature recommendations from the product discussion.
Some recommendations already have foundations in the application. Use the
[global product strategy](global-product-strategy.md) for that inventory and the
[product improvement plan](product-improvement-plan.md) for detailed requirements.
Treat these as candidate additions or improvements, not a list of absent features.

## Recommended features

| Feature | Why it helps sell | Proposed scope | Priority |
|---|---|---|---|
| One-click demo company | Prospects can see useful decisions before supplying their data | Isolated sample company with sales, overdue balances, stock, and assigned work; repeatable reset | First |
| Today's Work page | Gives staff a clear reason to open Vay every day | Due collections, missed promises, customer recovery, and stock attention with owners and next actions | First |
| Collection mini-CRM | Makes payment follow-up visible and accountable | Contact history, promises, disputes, partial payments, next follow-up, statement exports, and reminder drafts | First |
| Explain This Number | Helps customers trust figures and recommendations | Calculation inputs, source rows, date range, data freshness, reconciliation, and assumptions | Basic coverage first |
| Smart reorder assistant | Connects inventory reporting to purchasing decisions | Suggested quantity and buy date, selling pace, holding policy, pack sizes, incoming stock, and budget context | Next |
| Salesperson mobile view | Helps field staff act without returning to the office | Responsive assigned work, customer balances, contact actions, and follow-up updates with role-based access | Next |
| Onboarding checklist | Reduces effort between installation and the first useful report | Company policy, source templates, mapping, validation, first import, and guided refresh | First, alongside demo |
| Management review | Helps the owner review team follow-through and business results | Assigned and overdue work, promises kept, confirmed receipts, sales recovery signals, and weekly comparisons | Next |
| Customer-ready exports | Makes Vay useful in conversations outside the application | Branded statements, readable PDF/Excel reports, report date, currency, and supporting details | Basic coverage first |
| Pricing, license, and support screen | Makes the commercial offer and support path understandable | Plan, enabled modules, license status, renewal information, support contact, and diagnostics export | Before paid rollout |

Priority is a product recommendation, not an engineering estimate. Reuse existing
workflows and verify remaining gaps before assigning implementation tasks.

## Build the first sales demonstration

Start with **One-click demo company + Today's Work + Collection mini-CRM**.
Together, these show how Vay turns imported data into work that staff can complete.

### 1. One-click demo company

- Provide a clearly labeled sample business with representative sales, receipts,
  stock, customer history, payment promises, and follow-up tasks.
- Include examples of an overdue customer, a missed promise, a customer whose
  purchases have declined, and an item approaching its reorder point.
- Let a prospect open a useful dashboard without preparing an import.
- Keep demo records separate from customer records and allow a repeatable reset.

Completion check: a fresh installation can open the demo and follow each example
through its source details and next action without manual setup.

### 2. Today's Work page

- Extend the existing daily-work foundation with a consistent priority view.
- Show the customer or item, reason for attention, relevant amount or quantity,
  owner, due date, and available action.
- Allow filtering by staff member, work type, and due status.
- Let staff record progress, assign work, or schedule a follow-up from the list.
- Show when a recommendation depends on data awaiting a refresh.

Completion check: staff can identify their due work, understand each reason, and
record the next step without losing the customer or item context.

### 3. Collection mini-CRM

- Extend the existing contacts, promises, disputes, and allocation workflows.
- Keep the conversation history and next follow-up visible on the customer page.
- Show promised, confirmed received, and remaining amounts separately.
- Link payments using source allocations or explicit confirmation; identify
  inferred matches and prevent receipt reuse from inflating progress.
- Prepare a statement or reminder draft for staff to review and share.

Completion check: staff can record a promise, confirm a partial payment, and
schedule the remaining follow-up. Completing a call must not mark a balance paid.

## Suggested delivery order

1. Review the existing workflows and identify gaps against the demonstration above.
2. Add the demo company, guided first import, and essential number explanations.
3. Complete the daily-work and collection experience across its main screens.
4. Validate the demonstration and first refresh with representative pilot businesses.
5. Improve reorder decisions, mobile use, and the owner's weekly review.
6. Finalize customer-facing exports, commercial packaging, and support information.

Proposed packaging can group capabilities into a core sales/reporting offer,
collections and inventory modules, and advanced management options. Set prices
after checking customer demand, delivery costs, and the support commitment.

## Evidence to collect before expanding

- Time required to import a customer's data and produce the first useful report.
- Whether staff can complete the demo tasks without assistance.
- Whether imports and refreshes reconcile with the customer's source records.
- Whether owners and staff return to the daily-work and review screens.
- Which workflows customers are willing to pay for, and why.

Use pilot observations to refine priorities. Revenue increases, faster collections,
or inventory savings should become sales claims only when customer evidence
supports them.

## Market references

These references informed the product discussion; they do not establish Vay's
readiness or customer outcomes.

- [TallyPrime](https://resources.tallysolutions.com/global/tally-prime/) and its
  [dashboard documentation](https://help.tallysolutions.com/dashboard/) illustrate
  reporting, drill-down, and sharing expectations in business software.
- [Zoho Analytics features](https://www.zoho.com/analytics/features/?src=analytics-header)
  illustrate the wider reporting and data-connection capabilities buyers may compare.
- [QuickBooks custom roles](https://quickbooks.intuit.com/learn-support/en-global/help-article/access-permissions/add-manage-custom-roles-quickbooks-online-advanced/L8Ugph7xl_ROW_en?uid=lx7jio8n)
  illustrate granular access controls for teams.
