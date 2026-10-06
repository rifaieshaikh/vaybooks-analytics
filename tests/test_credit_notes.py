"""Credit notes reduce customer sales and balances, not item movement."""

from datetime import datetime

from vay.credit_notes import resolve_credit_party
from server.ar_balance import build_ar_statement, party_ledgers
from server.book import build_book
from server.customers import _activity
from server.preview import guess_type, suggest_column_map
from server.rows import query_rows
from server.store import MemoryStore


def test_guess_credit_note_sheet_not_sales():
    headers = [
        "SlNo", "Invoice No.", "Date", "Party Name", "Sales Amount",
        "SGST", "CGST", "IGST", "Net Amount", "Cash",
    ]
    assert guess_type("Sheet1", headers) == "credit_note"
    mapped = suggest_column_map(headers, "credit_note")
    assert mapped["Invoice No."] == "Invoice No"
    assert mapped["Cash"] == "__skip__"
    assert mapped["Net Amount"] == "Net Amount"


def test_activity_nets_credit_note_and_keeps_last_sale():
    store = MemoryStore()
    store.insert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {
            "Date": datetime(2026, 9, 1, 12),
            "Party Name": "Acme",
            "Sales Rep": "Ravi",
            "Net Amount": 1000,
            "Invoice No": "INV-1",
        },
    })
    store.insert_row({
        "type": "credit_note",
        "uk": "c1",
        "fields": {
            "Date": datetime(2026, 9, 10, 12),
            "Party Name": "Acme",
            "Invoice No": "CN-1",
            "Net Amount": 200,
            "Sales Amount": 169.49,
            "SGST": 15.25,
            "CGST": 15.26,
        },
    })
    store.insert_row({
        "type": "items",
        "uk": "i1",
        "fields": {
            "Date": datetime(2026, 9, 1, 12),
            "Item Name": "Board",
            "Qty": 4,
            "Rate": 100,
            "Invoice No": "INV-1",
        },
    })
    book = build_book(store)
    assert book["credit_notes_by_party"]["acme"]
    assert book["credit_notes_by_rep"]["ravi"]
    lines = book["buying_lines_by_party"].get("acme") or []
    assert lines and all(line.get("name") == "Board" for line in lines)
    joined = " ".join(str(line) for line in (book.get("item_lines_by_uk") or {}).values())
    assert "CN-1" not in joined
    as_of = datetime(2026, 10, 2, 12)
    act = _activity(store, "acme", as_of, book=book)
    assert any(e["kind"] == "credit_note" and e["amount"] == 200 for e in act["events"])
    assert act["ytd_sales"] == 800
    assert act["last_sale"] == "2026-09-01"
    assert act["ytd_collection"] == 0
    listed = query_rows(store, {"type": "credit_note"})
    assert listed["total"] == 1
    assert listed["rows"][0]["party"] == "Acme"
    assert listed["rows"][0]["invoice"] == "CN-1"
    assert listed["rows"][0]["amount"] == 200


def test_mismatch_flag_subtracts_credit_notes():
    store = MemoryStore()
    store.insert_row({
        "type": "customer",
        "uk": "edge-point",
        "fields": {"Account Name": "Edge Point"},
    })
    store.insert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {"Date": datetime(2026, 9, 1, 12), "Party Name": "Edge Point", "Net Amount": 1000, "Sales Rep": "Ravi"},
    })
    store.insert_row({
        "type": "receipt",
        "uk": "r1",
        "fields": {"Date": datetime(2026, 9, 2, 12), "Account Name": "Edge Point", "Amount": 100, "Sales Rep": "Ravi"},
    })
    store.insert_row({
        "type": "credit_note",
        "uk": "c1",
        "fields": {"Date": datetime(2026, 9, 3, 12), "Party Name": "EDGE POINT B.P ANGADI", "Invoice No": "CN-1", "Net Amount": 200},
    })
    store.insert_row({
        "type": "arr",
        "uk": "a1",
        "fields": {"Account Name": "Edge Point", "Balance": 700},
    })
    entry = party_ledgers(store)["edge point"]
    assert entry["credit_notes"] == 200
    assert entry["gap"] == 700
    from server.ar_balance import classify_ledger
    assert classify_ledger(entry, 0.5) == ""
    entry["arr"] = 900
    # 200 of the balance has no sale. That is the opening, so it is not a mismatch.
    assert classify_ledger(entry, 0.5) == ""
    from server.ar_balance import fields_for
    assert fields_for(entry, 0.5)["ledger_opening"] == 200
    entry["arr"] = 400
    assert classify_ledger(entry, 0.5) == "mismatch"


def test_blank_rep_and_group_are_filled_on_ingest():
    from vay.row_defaults import stamp_fields

    groups = {"edge point": "South"}
    known = set(groups)
    reps = {"edge point": [(datetime(2026, 9, 1, 12), "Ravi")]}
    sale = stamp_fields(
        {"Party Name": "Edge Point", "Net Amount": 10},
        "sales",
        groups=groups,
        known=known,
    )
    assert sale["Sales Rep"] == "NO_REP"
    assert sale["Group"] == "South"
    receipt = stamp_fields(
        {"Account Name": "Edge Point", "Amount": 5, "Sales Rep": "INVESTMENT"},
        "receipt",
        groups=groups,
        known=known,
    )
    assert receipt["Sales Rep"] == "INVESTMENT"
    assert receipt["Group"] == "South"
    note = stamp_fields(
        {"Party Name": "EDGE POINT B.P ANGADI", "Date": datetime(2026, 9, 10, 12), "Net Amount": 20},
        "credit_note",
        groups=groups,
        reps=reps,
        known=known,
    )
    assert note["Sales Rep"] == "Ravi"
    assert note["Group"] == "South"
    orphan = stamp_fields(
        {"Party Name": "Unknown Co", "Date": datetime(2026, 9, 10, 12), "Net Amount": 20},
        "credit_note",
        groups=groups,
        reps=reps,
        known=known,
    )
    assert orphan["Sales Rep"] == "NO_REP"
    assert orphan["Group"] == "NO_GROUP"


def test_mismatch_includes_receipts_without_rep():
    store = MemoryStore()
    store.insert_row({"type": "customer", "uk": "p", "fields": {"Account Name": "Plymax", "Group": "South"}})
    store.insert_row({
        "type": "sales", "uk": "s",
        "fields": {"Date": datetime(2026, 9, 1, 12), "Party Name": "Plymax", "Net Amount": 1000, "Sales Rep": "Ravi"},
    })
    store.insert_row({
        "type": "receipt", "uk": "r",
        "fields": {"Date": datetime(2026, 9, 2, 12), "Account Name": "Plymax", "Amount": 115, "Sales Rep": ""},
    })
    store.insert_row({"type": "arr", "uk": "a", "fields": {"Account Name": "Plymax", "Balance": 885, "Group": "South"}})
    entry = party_ledgers(store)["plymax"]
    assert entry["collection"] == 115
    assert entry["gap"] == 885
    from server.ar_balance import classify_ledger
    assert classify_ledger(entry, 0.5) == ""


def test_credit_note_party_extends_customer_name():
    known = {"edge point", "ias agency", "ias agency plywood &hardware"}
    assert resolve_credit_party("EDGE POINT B.P ANGADI", known) == "edge point"
    assert resolve_credit_party("EDGE POINT", known) == "edge point"
    assert resolve_credit_party("IAS AGENCY", known) == "ias agency"
    assert resolve_credit_party("MERTO HOME DESINGH THIRUNNAVAYA", known) == "merto home desingh thirunnavaya"


def test_ar_statement_balance_by_fy_and_month():
    sales = [
        (datetime(2026, 3, 15, 12), 400),
        (datetime(2026, 9, 1, 12), 1000),
    ]
    receipts = [(datetime(2026, 10, 1, 12), 300)]
    credits = [(datetime(2026, 9, 10, 12), 200)]
    as_of = datetime(2026, 10, 2, 12)
    statement = build_ar_statement(sales, receipts, credits, 600, as_of, start_month=4, tolerance=0.5)
    assert statement["sales"] == 1400
    assert statement["collection"] == 300
    assert statement["credit_notes"] == 200
    assert statement["ledger"] == 900
    assert statement["opening"] == 0
    assert statement["balance"] == 900
    assert statement["outstanding"] == 600
    assert statement["balance_diff"] == 300
    assert statement["balance_issue"] == "mismatch"
    assert [year["label"] for year in statement["years"]] == ["FY 2025-26", "FY 2026-27"]
    fy25, fy26 = statement["years"]
    assert fy25["complete"] is True
    assert [m["label"] for m in fy25["months"]] == ["Mar 2026"]
    march = fy25["months"][0]
    assert march["opening"] == 0
    assert march["sales"] == 400
    assert march["balance"] == 400
    assert fy25["opening"] == 0
    assert fy25["sales"] == 400
    assert fy25["balance"] == 400
    assert fy26["complete"] is False
    assert [m["label"] for m in fy26["months"]] == ["Sep 2026", "Oct 2026"]
    assert fy26["months"][0]["opening"] == march["balance"]
    sep, oct_ = fy26["months"]
    assert sep["opening"] == 400
    assert sep["sales"] == 1000
    assert sep["credit_notes"] == 200
    assert sep["balance"] == 1200
    assert oct_["opening"] == 1200
    assert oct_["collection"] == 300
    assert oct_["balance"] == 900
    brought = build_ar_statement(
        sales, receipts, credits, 600, as_of, start_month=4, tolerance=0.5, opening=50,
    )
    assert brought["opening"] == 50
    assert brought["opening_month"] == "Mar 2026"
    assert brought["years"][0]["months"][0]["opening"] == 50
    assert brought["years"][0]["months"][0]["balance"] == 450
    assert brought["balance"] == 950


def _customer(store, name, balance):
    store.insert_row({
        "type": "customer",
        "uk": name.lower(),
        "fields": {"Account Name": name, "Group": "South", "Balance": balance},
    })


def test_customer_360_follows_org_fiscal_year():
    """January year-start keeps Dec and Jan in different years. April would merge them."""
    from server.customers import get_customer
    from server.org_policy import save_org_policy

    store = MemoryStore()
    save_org_policy(store, {"fiscal_year_start_month": 1})
    store._force_as_of = datetime(2026, 2, 15, 12)
    _customer(store, "Acme", 260)
    store.insert_row({
        "type": "sales",
        "uk": "s-dec",
        "fields": {
            "Date": datetime(2025, 12, 1, 12),
            "Party Name": "Acme",
            "Sales Rep": "Ravi",
            "Net Amount": 200,
            "Invoice No": "OLD",
        },
    })
    store.insert_row({
        "type": "sales",
        "uk": "s-jan",
        "fields": {
            "Date": datetime(2026, 1, 20, 12),
            "Party Name": "Acme",
            "Sales Rep": "Ravi",
            "Net Amount": 100,
            "Invoice No": "NEW",
        },
    })
    store.insert_row({
        "type": "receipt",
        "uk": "r-dec",
        "fields": {"Date": datetime(2025, 12, 10, 12), "Account Name": "Acme", "Sales Rep": "Ravi", "Amount": 10},
    })
    store.insert_row({
        "type": "receipt",
        "uk": "r-jan",
        "fields": {"Date": datetime(2026, 1, 25, 12), "Account Name": "Acme", "Sales Rep": "Ravi", "Amount": 40},
    })
    store.insert_row({
        "type": "items",
        "uk": "i-dec",
        "fields": {
            "Date": datetime(2025, 12, 1, 12),
            "Party Name": "Acme",
            "Item Name": "Board",
            "Qty": 2,
            "Rate": 100,
            "Invoice No": "OLD",
        },
    })
    store.insert_row({
        "type": "items",
        "uk": "i-jan",
        "fields": {
            "Date": datetime(2026, 1, 20, 12),
            "Party Name": "Acme",
            "Item Name": "Board",
            "Qty": 1,
            "Rate": 100,
            "Invoice No": "NEW",
        },
    })
    detail = get_customer(store, "acme")
    assert detail["fiscal_year_start_month"] == 1
    assert detail["ytd_sales"] == 100
    assert detail["ytd_collection"] == 40
    by_start = {year["start"]: year for year in detail["fy_years"]}
    assert by_start["2026-01-01"]["sales"] == 100
    assert by_start["2026-01-01"]["collection"] == 40
    assert by_start["2025-01-01"]["sales"] == 200
    assert by_start["2025-01-01"]["collection"] == 10
    assert detail["opening_date"].startswith("2025-01-01")
    settle = {row["start"]: row["total"] for row in detail["settlements"]["by_fy"]}
    assert settle["2026-01-01"] == 40
    assert settle["2025-01-01"] == 10
    this_year = {item["name"]: item for item in detail["buying"]["periods"]["this_year"]["items"]}
    last_year = {item["name"]: item for item in detail["buying"]["periods"]["last_year"]["items"]}
    assert this_year["Board"]["qty"] == 1
    assert last_year["Board"]["qty"] == 2
    assert "2026-01-01" in [row["key"] for row in detail["ordering"]["by_fy"]]


def test_snapshot_settlements_include_credit_notes():
    from copy import deepcopy

    from server.customers import ensure_detail_settlements, get_customer

    store = MemoryStore()
    store._force_as_of = datetime(2026, 6, 1, 12)
    _customer(store, "Acme", -60)
    store.insert_row({
        "type": "sales",
        "uk": "s1",
        "fields": {
            "Date": datetime(2026, 1, 1, 12),
            "Party Name": "Acme",
            "Sales Rep": "Ravi",
            "Net Amount": 100,
            "Invoice No": "INV-1",
        },
    })
    store.insert_row({
        "type": "credit_note",
        "uk": "c1",
        "fields": {
            "Date": datetime(2026, 4, 1, 12),
            "Party Name": "Acme",
            "Invoice No": "CN-1",
            "Net Amount": 100,
        },
    })
    store.insert_row({
        "type": "receipt",
        "uk": "r1",
        "fields": {
            "Date": datetime(2026, 5, 1, 12),
            "Account Name": "Acme",
            "Sales Rep": "Ravi",
            "Amount": 60,
        },
    })
    live = get_customer(store, "acme")
    overall = live["settlements"]["overall"]
    assert overall["total"] == 0
    assert overall["credit"] == 60
    rebuilt = ensure_detail_settlements(store, deepcopy(live), force=True)
    assert rebuilt["settlements"]["overall"]["total"] == 0
    assert rebuilt["settlements"]["overall"]["credit"] == 60
    assert rebuilt["collection_buckets"] == live["collection_buckets"]
