# Settlement contracts

Engine version `1`. These are the Phase 0 contracts for the shared ledger in
`vay/ledger.py`. The hand-calculated expectations live in `tests/test_ledger.py`
and `tests/test_opening_check.py`.

## Scope and precision

An account is organization, legal entity, customer, and currency. This install
uses the organization as the legal entity. The customer id is the alias-resolved
account name. The currency is the organization currency unless the row names
another one. A row in another currency is a different account and is not settled
here.

Money is decimal, half-up to `0.01`. Quantity is decimal, half-up to `0.0001`.
Blank amounts and quantities stay missing.

Same-day order is effective date, then debits, credits, and reversals, then the
source sequence, then the source id. Opening items are replayed before period
items. Their invoice date is used for aging and FIFO order, not to place them
after a later receipt.

## Policies

`invoice_date_fifo` is the default. Unreferenced credits pay opening debt first,
then invoices by issue date. Every one of those links is `inferred`.

`due_date_priority` orders automatic allocation by due date. Unknown due dates
are last. It is available and does not change the default.

`explicit_only` applies confirmed links and unique references only.

A receipt that names an invoice keeps any remainder unapplied. If that name is
missing, ambiguous, or already settled, the credit stays unresolved. It is not
applied to a different invoice. A reference marked pre-period may pay opening
debt and does not invent an invoice. A reference to an invoice after the cutoff
is carried.

Confirmed links are `source_confirmed` or `manually_confirmed` and are applied
before automatic allocation. A unique invoice reference on the source receipt is
`source_confirmed`. FIFO and pre-period associations are `inferred`. A unique
amount hint is a suggestion and is not an allocation.

## Openings

Customer opening net = closing net − debit movements + credit movements.

That result is an arithmetic tie-out to the checkpoint it was built from. It is
used only when the checkpoint exists and the account declares its movements
complete. Otherwise the opening is unresolved and the amount is missing. An
imported opening is never replaced by a derived one. A derived aggregate has no
invoice identity and no age.

Stock opening quantity is imported. Closing quantity = opening + inbound −
outbound. A missing stock opening stays unresolved. A purchase counts as inward
only when `Receipt Status` says the goods were received. An invoice and a goods
receipt that share `Movement Key` count once. A purchase without that status
stays expected incoming. Reservations, expected incoming, and a financial credit
note are not stock movements. Stock value is reported only when an opening value
was imported.

## Aging and cash

Invoice age is the cutoff minus the invoice date. Days overdue is the cutoff
minus the due date, and it is zero while the invoice is not yet due. A missing
date stays unknown. The due date is the source due date, or the invoice date
plus the terms stored on that calculation.

Receipt allocations are cash. Credit notes and opening credits are not. A
negative accounts-receivable checkpoint is a net advance of its absolute value.
If the ledger already has that credit, no second credit is created. If it does
not, the advance is reported with unknown receipt and unknown date.
