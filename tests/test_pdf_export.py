from server.customers import customer_pdf
from server.pdf_export import catalog_rows, pdf_filename, report_pdf_bytes, zip_keep_names, zip_without_profit


def test_pdf_filename_sanitizes_illegal_chars():
    assert pdf_filename("sales_follow_up_A/B") == "sales_follow_up_A-B.pdf"
    assert pdf_filename("sales_rep_performance_report") == "sales_rep_performance_report.pdf"
    assert pdf_filename("group:south") == "group-south.pdf"


def test_customer_pdf_accepts_rupee_and_dashes():
    detail = {
        "name": "Alqwa Althakya",
        "company_name": "Vay Books",
        "due": 1250.5,
        "currency_symbol": "₹",
        "as_of_label": "17 Oct 2026",
        "insight": {"headline": "Still open — 90–120 days", "action": "Call today"},
        "open_invoices": [{
            "date_label": "1 Jun 2026",
            "invoice": "INV-1",
            "what": "Sale",
            "due": 1250.5,
            "age_days": 100,
        }],
    }
    statement = customer_pdf(detail, view="customer")
    brief = customer_pdf(detail, view="rep")
    reminder = customer_pdf(detail, view="reminder")
    assert statement.startswith(b"%PDF")
    assert brief.startswith(b"%PDF")
    assert reminder.startswith(b"%PDF")


def test_report_pdf_bytes_are_pdf():
    data = report_pdf_bytes({
        "id": "sales_rep_performance_report",
        "friendly_title": "Sales by person",
        "headers": ["Sales Rep", "YTD Sales"],
        "rows": [["R", 100]],
        "total": ["Total", 100],
        "status_header": "",
    })
    assert data[:4] == b"%PDF"


def test_zip_without_profit_drops_profit_pdfs():
    from io import BytesIO
    from zipfile import ZipFile

    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("sales_rep_performance_report.pdf", b"%PDF-sales")
        zf.writestr("monthly_profit_report.pdf", b"%PDF-profit")
        zf.writestr("item_wise_profit.pdf", b"%PDF-item")
    names = ZipFile(BytesIO(zip_without_profit(buf.getvalue()))).namelist()
    assert names == ["sales_rep_performance_report.pdf"]


def test_zip_keep_names_keeps_only_visible():
    from io import BytesIO
    from zipfile import ZipFile

    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("sales_rep_performance_report.pdf", b"%PDF-sales")
        zf.writestr("monthly_profit_report.pdf", b"%PDF-profit")
    names = ZipFile(BytesIO(zip_keep_names(buf.getvalue(), ["monthly_profit_report.pdf"]))).namelist()
    assert names == ["monthly_profit_report.pdf"]


def test_catalog_rows_mark_existing_and_progress(tmp_path):
    folder = tmp_path
    (folder / "monthly_profit_report.pdf").write_bytes(b"%PDF")
    rows = catalog_rows(
        [
            {"id": "sales_rep_performance_report", "group": "Performance", "friendly_title": "Sales by person"},
            {"id": "monthly_profit_report", "group": "Profit", "friendly_title": "Profit and loss"},
        ],
        folder,
        {"reports": [{"id": "sales_rep_performance_report", "state": "running"}]},
    )
    by_id = {row["id"]: row for row in rows}
    assert by_id["sales_rep_performance_report"]["exists"] is False
    assert by_id["sales_rep_performance_report"]["state"] == "running"
    assert by_id["monthly_profit_report"]["exists"] is True
    assert by_id["monthly_profit_report"]["state"] == "done"
