# Pilot baselines and Phase 0 gate

## Baselines to record (method)

| Measure | How to capture during assisted onboardings |
|---|---|
| Time to first trusted report | Start at first upload; stop when a decision-maker views a reconciled sales + AR view |
| Reconciliation pass rate | For each pilot period: compare Create sales totals and AR balance to agreed source export totals |
| Weekly active decision-makers | Count distinct authorized users who open Dashboard / Create / follow-up weekly |
| Action completion | When Phase 3 actions exist; until then track manual follow-ups completed outside the product |

Numeric targets are set after at least one assisted onboarding per pilot — do not invent benchmarks from Vay alone.

Recorded values: **not set**. Edge Point, Plymax, and EFF YES Traders still have no workbook in this repository, so time to first trusted report, reconciliation pass rate, and weekly active decision-makers stay blank.

## Onboarding checklist (per pilot)

1. Collect exports listed in [`samples/<pilot>/MANIFEST.md`](samples/).
2. Map native headers using [`03_source_field_matrix.md`](03_source_field_matrix.md).
3. Set Organization policy (FY, timezone, currency, tax) — defaults remain Vay-compatible.
4. Confirm expense map: keep `vay_wholesale` seed for Vay; start empty/custom for others as needed.
5. Import → Create (core at minimum) → reconcile sales MTD/YTD and AR balance.
6. Record blockers (missing sheets, grain gaps) in the pilot manifest.

## Phase 0 exit gate

| Criterion | Status | Evidence |
|---|---|---|
| Shared data model describes all four pilots without hard-coded business names in formula modules | Pass | [`04_shared_data_model.md`](04_shared_data_model.md), [`vay/domain.py`](../../vay/domain.py) |
| Metric specs (10–15) exist | Pass | [`05_metric_catalogue.md`](05_metric_catalogue.md), [`metrics/`](metrics/) |
| Org policy in product (FY, TZ, currency, tax, terminology) | Pass | Settings → Organization; [`server/org_policy.py`](../../server/org_policy.py) |
| Expense account names not hard-coded in formula modules | Pass | [`vay/packs/vay_wholesale.py`](../../vay/packs/vay_wholesale.py) seed + settings API |
| Vay sample schema present | Pass | [`samples/vay/`](samples/vay/) |
| Edge Point / Plymax / EFF YES field matrix filled from real exports | Blocker | Manifests mark **BLOCKER — workbook not yet received**; model still applies without pilot-specific report modules |
| No pilot-specific report Python module required for Edge Point, Plymax, or EFF YES Traders | Pass | Same packs/engine; configuration + mappers only |

### Gate assertion

Edge Point, Plymax, and EFF YES Traders are onboarded through the **shared canonical model + mappers + org policy**, not by adding `vay/reports/edge_point.py`-style modules. Outstanding work is **sample collection**, not model forks.

## Related docs

- [`01_buyer_and_pilots.md`](01_buyer_and_pilots.md)
- [`02_vay_assumption_catalogue.md`](02_vay_assumption_catalogue.md)
- [`06_org_policy_and_terminology.md`](06_org_policy_and_terminology.md)
- Product roadmap: [`Vay_Reports_Business_Analytics_Roadmap.md`](../../Vay_Reports_Business_Analytics_Roadmap.md)
