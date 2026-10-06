"""Current-FY slice vs checked-in engine or Apps Script goldens, keyed by entity."""

from pathlib import Path

import pytest

GOLDEN = Path(__file__).parent / "fixtures" / "gs_golden" / "reports.xlsx"
META = Path(__file__).parent / "fixtures" / "gs_golden" / "meta.txt"
SOURCE = Path(__file__).parent / "fixtures" / "gs_golden" / "source.xlsx"

TOL = 0.005  # #,##0.00


def _has_golden():
    return GOLDEN.exists() and META.exists() and SOURCE.exists()


@pytest.mark.skipif(not _has_golden(), reason="Generate or export goldens into tests/fixtures/gs_golden/")
def test_current_fy_slice_matches_gs_golden():
    from datetime import datetime

    import pandas as pd

    from vay.engine import generate
    from vay.load import load_sources
    from vay.reports.fiscal import current_fy_pair_slice

    date_text = META.read_text(encoding="utf-8").strip()
    y, m, d = [int(p) for p in date_text.split("-")]
    report_date = datetime(y, m, d, 12)
    with open(SOURCE, "rb") as fh:
        tables, errors = load_sources(combined_file=fh)
    assert not errors
    out = generate(tables, report_date, ["core", "fiscal"])
    n_fy = len(out["ctx"]["fiscalYears"])
    xl = pd.ExcelFile(GOLDEN)

    def num_eq(a, b):
        if pd.isna(a):
            a = ""
        if pd.isna(b):
            b = ""
        try:
            return abs(float(a or 0) - float(b or 0)) <= TOL
        except (TypeError, ValueError):
            return str(a) == str(b)

    mapping = {
        "fiscal_monthly_sales_rep_performance_report": ("fy_sales_rep", 1),
        "fiscal_monthly_group_performance_report": ("fy_group", 1),
        "fiscal_monthly_account_performance_report": ("fy_account", 2),
    }
    compared = 0
    for rid, (sheet, labels) in mapping.items():
        names = {s.lower(): s for s in xl.sheet_names}
        sheet_name = names.get(sheet) or names.get(rid.lower())
        if not sheet_name:
            pytest.skip("golden missing " + rid)
        gold = pd.read_excel(xl, sheet_name=sheet_name, header=None)
        report = next(r for r in out["reports"] if r["id"] == rid)
        gold_by_key = {}
        for _, grow in gold.iterrows():
            key = grow.iloc[0]
            if key in ("Total", "TOTAL") or key == report["headers"][0]:
                if key in ("Total", "TOTAL"):
                    gold_by_key["__total__"] = list(grow.values)
                continue
            gold_by_key[str(key)] = list(grow.values)
        for row in report["rows"]:
            key = str(row[0])
            sliced = current_fy_pair_slice(row, labels, n_fy)
            if key not in gold_by_key:
                continue
            g = gold_by_key[key]
            # Engine exports contain all fiscal years. A real GS fixture may
            # contain only the current FY, so accept either workbook shape.
            if len(g) >= labels + n_fy * 26:
                g = current_fy_pair_slice(g, labels, n_fy)
            else:
                g = g[: labels + 26]
            for i, val in enumerate(sliced):
                if i < labels:
                    continue
                assert num_eq(val, g[i] if i < len(g) else 0), (rid, key, i, val, g[i] if i < len(g) else None)
                compared += 1
    assert compared > 0, "golden workbook had no matching fiscal entities"
