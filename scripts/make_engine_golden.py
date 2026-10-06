"""Generate checked-in engine regression fixtures from the tiny core-test tables."""

from datetime import datetime
from pathlib import Path
import sys

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vay.engine import generate
from vay.export_excel import write_workbook
from vay.table import Table

REPORT_DATE = datetime(2026, 9, 19, 12)
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "gs_golden"


def _table(name, headers, rows):
    return Table(name, headers, [list(row) for row in rows])


def fallback_tiny_tables():
    """Fallback for source archives that do not include the test module."""
    return {
        "arr": _table(
            "arr",
            ["Account Name", "Group", "Balance", "Days"],
            [["Alpha", "South", 1000, 12], ["Beta", "North", 0, 0]],
        ),
        "sales": _table(
            "sales",
            ["Date", "Party Name", "Sales Rep", "Net Amount"],
            [
                [datetime(2026, 9, 19, 12), "Alpha", "Ravi", 1180],
                [datetime(2026, 7, 20, 12), "Alpha", "Ravi", 500],
                [datetime(2026, 7, 19, 12), "Alpha", "Ravi", 100],
                [datetime(2026, 4, 1, 12), "Beta", "Anu", 2000],
                [datetime(2023, 1, 15, 12), "OldCo", "Ravi", 50],
            ],
        ),
        "receipt": _table(
            "receipt",
            ["Date", "Account Name", "Sales Rep", "Amount"],
            [
                [datetime(2026, 9, 19, 12), "Alpha", "Ravi", 100],
                [datetime(2026, 9, 19, 12), "Alpha", "INVESTMENT", 999],
            ],
        ),
    }


def load_tiny_tables():
    tests_dir = ROOT / "tests"
    if (tests_dir / "test_core.py").is_file():
        sys.path.insert(0, str(tests_dir))
        from test_core import tiny_tables

        return tiny_tables()
    return fallback_tiny_tables()


def write_source(tables, destination):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, table in tables.items():
        sheet = workbook.create_sheet(name)
        sheet.append(list(table.headers))
        for row in table.rows:
            sheet.append(list(row))
    workbook.save(destination)


def main():
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    tables = load_tiny_tables()
    write_source(tables, FIXTURE_DIR / "source.xlsx")
    result = generate(tables, REPORT_DATE, ["core", "fiscal"])
    (FIXTURE_DIR / "reports.xlsx").write_bytes(write_workbook(result["reports"]))
    (FIXTURE_DIR / "meta.txt").write_text(REPORT_DATE.strftime("%Y-%m-%d") + "\n", encoding="utf-8")
    print(f"Wrote engine golden fixtures to {FIXTURE_DIR}")


if __name__ == "__main__":
    main()
