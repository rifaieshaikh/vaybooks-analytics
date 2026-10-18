"""Opening assessment from imported rows, and the report-create preflight."""

from server.jobs import enqueue_run
from server.opening_check import assess_rows
from server.preview import guess_type
from server.store import get_store


def _row(type_name, uk, fields):
    return {"type": type_name, "uk": uk, "fields": fields}


def test_sheet_names_select_the_new_import_types():
    assert guess_type("Opening stock", [], None) == "stock_opening"
    assert guess_type("Customer opening", [], None) == "customer_opening"
    assert guess_type("Purchases", [], None) == "purchases"
    assert guess_type("Stock movements", [], None) == "stock_movement"


def test_voucher_receipts_pay_oldest_invoices_and_due_is_not_an_opening():
    books = assess_rows(
        [
            _row("sales", "old", {
                "Date": "2026-04-13", "Party Name": "East", "Net Amount": "100", "Invoice No": "91",
            }),
            _row("sales", "mid", {
                "Date": "2026-07-29", "Party Name": "East", "Net Amount": "50", "Invoice No": "839",
            }),
            _row("sales", "b", {
                "Date": "2026-09-26", "Party Name": "East", "Net Amount": "80", "Invoice No": "1246",
            }),
            _row("receipt", "fy-r", {
                "Date": "2026-09-30", "Account Name": "East", "Amount": "120", "Invoice No": "0096",
            }),
            _row("arr", "east", {"Account Name": "East", "Balance": "110"}),
        ],
        as_of="2026-10-18",
        organization_id="org",
        currency="INR",
        terms_days=30,
        fy_start="2026-04-01",
        settlement_mode="oldest",
    )
    customer = books["customers"][0]
    assert customer["opening"]["status"] == "unresolved"
    opens = {row["invoice_number"]: row["remaining"] for row in customer["settlement"]["open_debits"]}
    assert "91" not in opens
    assert opens["839"] == "30.00"
    assert opens["1246"] == "80.00"
    assert not any(row.get("opening") for row in customer["settlement"]["open_debits"])


def test_missing_customer_opening_stays_unknown_and_stock_is_not_estimated():
    books = assess_rows(
        [
            _row("sales", "s1", {
                "Date": "2024-05-01", "Party Name": "Acme", "Net Amount": "100", "Invoice No": "INV-1",
            }),
            _row("arr", "acme", {"Account Name": "Acme", "Balance": "100"}),
            _row("stock", "widget", {"Item Name": "Widget", "Qty": "8", "P.Price": "10"}),
            _row("purchases", "p1", {
                "Date": "2024-05-02", "Item Name": "Widget", "Qty": "4", "Unit": "pcs",
                "Invoice No": "PI-1", "Receipt Status": "received",
            }),
        ],
        as_of="2026-03-31",
        organization_id="org",
        currency="INR",
        terms_days=30,
    )
    customer = books["customers"][0]
    assert customer["opening"]["status"] == "unresolved"
    assert customer["opening"]["amount"] is None
    assert "sales" in customer["allowed_outputs"]
    assert "exact_balance" in customer["withheld_outputs"]
    item = books["items"][0]
    assert item["opening_status"] == "unresolved"
    assert item["bridge"]["calculated_closing"] is None
    assert "current_stock" in item["allowed_outputs"]


def test_complete_books_reconstruct_the_customer_and_roll_stock_forward():
    books = assess_rows(
        [
            _row("customer_opening", "cov", {
                "Date": "2024-04-01", "Account Name": "Acme", "Balance": "0",
                "Kind": "coverage", "Complete": "yes", "Complete Through": "2026-03-31",
            }),
            _row("sales", "s1", {
                "Date": "2024-05-01", "Party Name": "Acme", "Net Amount": "500", "Invoice No": "INV-1",
            }),
            _row("receipt", "r1", {
                "Date": "2024-06-01", "Account Name": "Acme", "Amount": "400",
            }),
            _row("arr", "acme", {"Account Name": "Acme", "Balance": "200"}),
            _row("stock_opening", "open", {
                "Date": "2024-04-01", "Item Name": "Widget", "Qty": "10", "Unit": "pcs", "Value": "100",
            }),
            _row("purchases", "pi", {
                "Date": "2024-05-02", "Item Name": "Widget", "Qty": "4", "Unit": "pcs",
                "Invoice No": "PI-1", "Movement Key": "M1", "Receipt Status": "invoiced",
            }),
            _row("purchases", "gr", {
                "Date": "2024-05-03", "Item Name": "Widget", "Qty": "4", "Unit": "pcs",
                "Invoice No": "PI-1", "Movement Key": "M1", "Receipt Status": "received",
            }),
            _row("stock_movement", "issue", {
                "Date": "2024-06-01", "Item Name": "Widget", "Qty": "3", "Unit": "pcs", "Movement": "issue",
            }),
            _row("stock_movement", "ret", {
                "Date": "2024-06-02", "Item Name": "Widget", "Qty": "1", "Unit": "pcs", "Movement": "customer return",
            }),
            _row("stock_movement", "xfer", {
                "Date": "2024-06-03", "Item Name": "Widget", "Qty": "2", "Unit": "pcs", "Movement": "transfer out",
            }),
            _row("stock_movement", "count", {
                "Date": "2024-06-04", "Item Name": "Widget", "Qty": "1", "Unit": "pcs",
                "Movement": "count", "Signed Qty": "1",
            }),
            _row("stock", "widget", {"Item Name": "Widget", "Qty": "11", "Unit": "pcs"}),
        ],
        as_of="2026-03-31",
        organization_id="org",
        currency="INR",
        terms_days=30,
    )
    customer = books["customers"][0]
    # 200 closing − 500 invoices + 400 receipts = 100 opening.
    assert customer["opening"]["status"] == "reconstructed"
    assert customer["opening"]["amount"] == "100.00"
    assert customer["opening"]["tie_out"] is True
    assert customer["bridge"]["calculated_closing"] == "200.00"
    assert customer["bridge"]["difference"] == "0.00"
    item = next(row for row in books["items"] if row["item_id"] == "Widget" and row["unit"] == "pcs")
    assert item["bridge"]["calculated_closing"] == "11.0000"
    assert item["bridge"]["difference"] == "0.0000"
    assert item["bridge"]["movements"]["purchase_receipt"] == "4.0000"


def test_imported_customer_opening_is_kept():
    books = assess_rows(
        [
            _row("customer_opening", "old", {
                "Date": "2024-04-01", "Account Name": "Acme", "Balance": "150",
                "Kind": "invoice", "Invoice No": "OLD", "Invoice Date": "2023-06-01", "Due Date": "2023-07-01",
            }),
            _row("receipt", "r1", {"Date": "2024-06-01", "Account Name": "Acme", "Amount": "100"}),
            _row("arr", "acme", {"Account Name": "Acme", "Balance": "50"}),
        ],
        as_of="2026-03-31",
        organization_id="org",
        currency="INR",
        terms_days=30,
    )
    customer = books["customers"][0]
    assert customer["opening"]["status"] == "imported"
    assert customer["opening"]["amount"] == "150.00"
    assert customer["settlement"]["reconciliation"]["state"] == "reconciled"
    assert customer["settlement"]["open_debits"][0]["unknown_age"] is False


def test_negative_arr_without_a_receipt_is_an_advance_of_unknown_origin():
    books = assess_rows(
        [_row("arr", "acme", {"Account Name": "Acme", "Balance": "-150"})],
        as_of="2026-03-31",
        organization_id="org",
        currency="INR",
        terms_days=30,
    )
    reconciliation = books["customers"][0]["settlement"]["reconciliation"]
    assert reconciliation["state"] == "arr_only_advance"
    assert reconciliation["net_advance"] == "150.00"
    assert reconciliation["advance_provenance"] == "unknown"
    assert books["customers"][0]["settlement"]["allocations"] == []


def test_create_stores_the_assessment_and_still_queues_the_report():
    store = get_store()
    store.upsert_row({
        "type": "sales",
        "uk": "s1",
        "source_upload_id": "u",
        "fields": {"Date": "2025-05-01", "Party Name": "Acme", "Sales Rep": "R", "Net Amount": "25", "Invoice No": "INV-1"},
    })
    run_id, err = enqueue_run(store, {"core": True}, "2026-03-31")
    assert err == ""
    stored = store.get_run(run_id)
    assessment = stored["opening_assessment"]
    assert assessment["engine_version"] == "1"
    assert assessment["policy"] == "invoice_date_fifo"
    assert assessment["customers"][0]["opening"]["status"] == "unresolved"
    assert stored["status"] == "queued"
