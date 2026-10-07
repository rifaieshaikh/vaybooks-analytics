# Vay Reports: Global support matrix

Date: 2026-10-07  
Status: Search list and proposal to validate. This document does not claim that any country, currency, or format is supported in the product.  
Audience: Product, sales, and pilot operators

Related: [Global product strategy](global-product-strategy.md), [Global product task list](global-product-task-list.md), [Overseas intake template](phase0/samples/_overseas_intake/MANIFEST.md).

## 1. What this matrix is

GCC, the European Union, and the Americas are the places to look for the first overseas pilots. The Americas are recorded as three rows — the United States, Canada, and Latin America — because date order, number format, tax, and currency precision differ inside that group.

Every regional cell below is **typical**, drawn from common commercial practice. It is not an observation from a Vay customer export.

The supported first offer is the fit of two named external businesses, once they are recorded in the candidate table and their exports are in hand. Until those two businesses are named, G01 stays open.

## 2. Proposed offer

A pilot has to fit this envelope:

| Item | Proposed offer |
|---|---|
| Language | English UI. Customer and product names may use a wider character set; right-to-left layout is a later task (G25). |
| Currency | One reporting currency per company. Precision is taken from the source file. A currency code does not convert amounts. |
| Onboarding | Excel or CSV export, mapped on intake. |
| Modules | Sales, collections, and inventory. |
| Fiscal year | A start on a calendar-month boundary. |
| Desktop / LAN | R1 deployment scope, after pilots. |
| Hosted self-service | R2 scope (G16–G19). Workspace, billing, and recovery are outside this offer. |

Desktop and hosted are product scopes. This matrix does not assign a deployment preference to a region.

## 3. Typical regional notes

Currency precision follows the export. ISO minor units are a starting note only. Current amount handling assumes two decimal places and strips commas from values such as `1,234.50` ([vay/dates.py](../vay/dates.py), two-decimal rounding covered by [tests/test_core.py](../tests/test_core.py)). Three-decimal and zero-decimal amounts stay outside that behavior until a named pilot’s file shows that precision and G05 defines it.

| Topic | GCC | European Union | United States | Canada | Latin America |
|---|---|---|---|---|---|
| Currencies to expect | AED, SAR, QAR typically 2 decimal places. KWD, BHD, OMR typically 3. | EUR and most other EU currencies typically 2 decimal places. HUF: confirm from the export. | USD, typically 2 decimal places. | CAD, typically 2 decimal places. | MXN and BRL typically 2 decimal places. CLP typically zero-decimal. COP is often treated as zero-decimal in business exports even though the ISO exponent is 2; record the export’s precision. |
| Dates | Typically day-first. | Typically day-first. | Typically month-first. | Date order in exports is often mixed. Confirm per file. | Typically day-first. |
| Numbers | Often `1,234.56` in English exports. Confirm per file. | Often `1.234,56` or `1 234,56`. Parsing is G04, not this task. | Typically `1,234.56`. | Often `1,234.56`. Confirm per file. | Often decimal comma. Parsing is G04, not this task. |
| Fiscal year | Commercial companies often use a January start. Confirm with the company. | Often a January start. Confirm with the company. | Often a January start. Some retailers use another month boundary. | Often a January start. Confirm with the company. | Often a January start. Confirm with the company. |
| Tax basis | VAT differs by country, including countries with no VAT. Keep source net, tax, and gross. Leave the inclusive 18% GST fallback unused. | VAT is typically exclusive, mixed-rate, and sometimes exempt. | Sales tax is jurisdiction-specific. It is not one company rate. | GST, HST, and PST. Separate from one inclusive rate. | Confirm VAT or sales tax from the export. Keep source net, tax, and gross. |
| Units | Metric, plus the pack or case unit the file uses. | Metric, plus the pack or case unit the file uses. | Imperial units and case packs are common. Record the file’s unit. | Metric is common. Record the file’s unit. | Metric, plus the pack or case unit the file uses. |
| Names in source data | Latin and Arabic may both appear. | Latin, including accents. | Latin. | Latin, including French accents. | Latin, including accents. |

## 4. Exclusions for this search

These stay outside the proposed offer:

- Mixed-currency totals and exchange rates
- Treating a currency-code change as a conversion
- Statutory filing, payroll, and tax calculation
- Connectors
- Services and manufacturing models
- Right-to-left UI
- Hosted self-service, including any data-residency or privacy claim for EU or GCC hosting. That review is a commercial decision.

## 5. Release scopes

| Scope | Release | What the offer includes |
|---|---|---|
| Desktop / LAN | R1, after pilot evidence | Install, configure, import, and the modules the pilot’s data can support |
| Hosted | R2 | Workspace provisioning, invitations, recovery, billing, and operations (G16–G19) |

## 6. Candidates

G01 acceptance needs two external businesses that fit the proposed offer. Both rows are blank.

| Business | Country | Source system | Currency and precision from the export | Date format | Number format | Deployment choice |
|---|---|---|---|---|---|---|
| | | | | | | |
| | | | | | | |

When a business is named, copy [the overseas intake template](phase0/samples/_overseas_intake/MANIFEST.md) into that business’s sample folder. Leave Edge Point, Plymax, and EFF YES Traders on their existing manifests.
