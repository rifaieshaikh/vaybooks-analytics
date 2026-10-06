"""Landscape A4 PDFs for official reports, plus a date-folder zip."""

from __future__ import annotations

import logging
import os
import re
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from vay.config import STATUS_COLORS, TEXT_HEADERS
from vay.dates import round2
from vay.export_excel import ILLEGAL

from server.auth import report_allowed
from server.labels import GROUP_ORDER, PROFIT_IDS
from server.settings import export_dir

log = logging.getLogger("vay.pdf_export")
MARGIN = 12.7


def pdf_filename(report_id):
    cleaned = ILLEGAL.sub("-", str(report_id or "report")).strip(" .")
    cleaned = re.sub(r"[<>|\"']", "-", cleaned)
    return (cleaned or "report") + ".pdf"


def zip_filename(folder_name):
    return "vay_reports_%s.zip" % folder_name


def profit_pdf_names():
    return {pdf_filename(rid) for rid in PROFIT_IDS}


def zip_without_profit(data):
    omit = profit_pdf_names()
    out = BytesIO()
    with ZipFile(BytesIO(data), "r") as src, ZipFile(out, "w", ZIP_DEFLATED) as dest:
        for info in src.infolist():
            if info.filename in omit:
                continue
            dest.writestr(info.filename, src.read(info.filename))
    return out.getvalue()


def zip_keep_names(data, keep):
    keep = set(keep or [])
    out = BytesIO()
    with ZipFile(BytesIO(data), "r") as src, ZipFile(out, "w", ZIP_DEFLATED) as dest:
        for info in src.infolist():
            if info.filename not in keep:
                continue
            dest.writestr(info.filename, src.read(info.filename))
    return out.getvalue()


def export_title(report):
    rid = (report or {}).get("id") or ""
    if rid.startswith("sales_follow_up_"):
        return "Who to follow up — sales (%s)" % rid[len("sales_follow_up_"):]
    if rid.startswith("collection_follow_up_"):
        return "Who to follow up — collections (%s)" % rid[len("collection_follow_up_"):]
    return (report or {}).get("friendly_title") or (report or {}).get("title") or rid


def visible_reports(reports, perms):
    out = []
    perms = perms or []
    for report in reports or []:
        if not report_allowed(report, perms):
            continue
        out.append(report)
    return out


def catalog_rows(reports, folder, progress=None):
    progress = progress or {}
    by_id = {row.get("id"): row for row in (progress.get("reports") or [])}
    rows = []
    for report in reports or []:
        rid = report.get("id") or ""
        exists = bool(folder and rid and (folder / pdf_filename(rid)).is_file())
        prev = by_id.get(rid) or {}
        state = prev.get("state") or ("done" if exists else "idle")
        rows.append({
            "id": rid,
            "title": export_title(report),
            "group": report.get("group") or "",
            "exists": bool(exists or state == "done"),
            "state": state,
        })
    order = {name: i for i, name in enumerate(GROUP_ORDER)}
    rows.sort(key=lambda row: (order.get(row.get("group") or "", 99), row.get("title") or ""))
    return rows


def catalog_entries(reports):
    return [{
        "id": (report or {}).get("id") or "",
        "title": export_title(report),
        "group": (report or {}).get("group") or "",
    } for report in reports or []]


def dated_folder(dt):
    folder_name = dt.strftime("%d-%m-%Y")
    return export_dir() / folder_name, folder_name


def folder_for_date(dt):
    folder, folder_name = dated_folder(dt)
    folder.mkdir(parents=True, exist_ok=True)
    return folder, folder_name


def expected_pdf_names(reports):
    names = []
    seen = set()
    for report in reports or []:
        name = pdf_filename((report or {}).get("id"))
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _pdf_family(pdf):
    pairs = [
        (r"C:\Windows\Fonts\Nirmala.ttf", r"C:\Windows\Fonts\NirmalaB.ttf"),
        (r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\segoeuib.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for regular, bold in pairs:
        if os.path.isfile(regular):
            pdf.add_font("Ui", "", regular)
            pdf.add_font("Ui", "B", bold if os.path.isfile(bold) else regular)
            return "Ui"
    return "Helvetica"


def _safe_pdf(text, family="Helvetica"):
    s = str("" if text is None else text).replace("\x00", " ")
    if family == "Helvetica":
        return s.encode("latin-1", "replace").decode("latin-1")
    return s


def _rgb(hex_color):
    raw = str(hex_color or "").replace("#", "")
    if len(raw) != 6:
        return None
    try:
        return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)
    except ValueError:
        return None


def _sizes(ncols):
    if ncols <= 8:
        return 8, 5.5
    if ncols <= 16:
        return 6, 4.5
    if ncols <= 28:
        return 5, 4.0
    return 4, 3.5


def _widths(usable, ncols):
    if ncols <= 1:
        return [usable]
    first = min(usable * 0.22, 52)
    rest = max((usable - first) / (ncols - 1), 4)
    return [first] + [rest] * (ncols - 1)


def _display_cell(value, header):
    if value == "" or value is None:
        return ""
    if header in TEXT_HEADERS or header in ("", None):
        return value
    if isinstance(value, bool):
        return value
    try:
        num = float(value)
    except (TypeError, ValueError):
        return value
    if num != num:
        return ""
    return "{:,.2f}".format(round2(num))


def _clip(pdf, text, width, size, family, bold=False):
    pdf.set_font(family, "B" if bold else "", size)
    s = _safe_pdf(text, family)
    pad = 0.8
    if pdf.get_string_width(s) <= width - pad:
        return s
    ell = "..."
    while s and pdf.get_string_width(s + ell) > width - pad:
        s = s[:-1]
    return (s + ell) if s else ""


class ReportPDF(FPDF):
    def __init__(self):
        super().__init__(orientation="L", unit="mm", format="A4")
        self._ui_family = "Helvetica"

    def footer(self):
        self.set_y(-10)
        try:
            self.set_font(self._ui_family, "", 8)
        except Exception:
            self.set_font("Helvetica", "", 8)
        self.set_text_color(120, 113, 108)
        self.cell(0, 8, "%s / %s" % (self.page_no(), getattr(self, "pages_count", self.page_no())), align="C")


def report_pdf_bytes(report):
    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=False)
    pdf.set_margins(MARGIN, MARGIN, MARGIN)
    pdf.add_page()
    family = _pdf_family(pdf)
    pdf._ui_family = family

    title = report.get("friendly_title") or report.get("title") or report.get("id") or "Report"
    headers = list(report.get("headers") or [])
    header_row1 = list(report.get("header_row1") or [])
    body = list(report.get("rows") or [])
    if report.get("total"):
        body = body + [list(report["total"])]
    ncols = max(len(headers), 1)
    if header_row1:
        ncols = max(ncols, len(header_row1))
        while len(headers) < ncols:
            headers.append("")
        while len(header_row1) < ncols:
            header_row1.append("")
    size, row_h = _sizes(ncols)
    widths = _widths(pdf.epw, ncols)
    status_header = report.get("status_header") or ""
    status_idx = headers.index(status_header) if status_header in headers else -1
    bottom = pdf.h - MARGIN

    def draw_headers():
        if header_row1:
            pdf.set_font(family, "B", size)
            pdf.set_fill_color(15, 61, 46)
            pdf.set_text_color(255, 255, 255)
            for i, val in enumerate(header_row1[:ncols]):
                pdf.cell(widths[i], row_h, _clip(pdf, val, widths[i], size, family, True), border=0, fill=True)
            pdf.ln()
        pdf.set_font(family, "B", size)
        pdf.set_fill_color(15, 61, 46)
        pdf.set_text_color(255, 255, 255)
        for i, val in enumerate(headers[:ncols]):
            pdf.cell(widths[i], row_h, _clip(pdf, val, widths[i], size, family, True), border=0, fill=True)
        pdf.ln()
        pdf.set_text_color(28, 25, 23)

    pdf.set_font(family, "B", 11)
    pdf.set_text_color(28, 25, 23)
    pdf.cell(0, 7, _safe_pdf(title, family), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    draw_headers()

    for ridx, row in enumerate(body):
        if pdf.get_y() + row_h > bottom:
            pdf.add_page()
            draw_headers()
        cells = list(row or [])
        while len(cells) < ncols:
            cells.append("")
        is_total = str(cells[0] or "").strip().lower() == "total"
        fill = ridx % 2 == 1 or is_total
        if is_total:
            pdf.set_fill_color(236, 253, 245)
        elif fill:
            pdf.set_fill_color(248, 250, 249)
        else:
            pdf.set_fill_color(255, 255, 255)
        pdf.set_font(family, "B" if is_total else "", size)
        for i in range(ncols):
            rgb = _rgb(STATUS_COLORS.get(str(cells[i]), "")) if i == status_idx else None
            if rgb:
                pdf.set_fill_color(*rgb)
            elif is_total:
                pdf.set_fill_color(236, 253, 245)
            elif fill:
                pdf.set_fill_color(248, 250, 249)
            else:
                pdf.set_fill_color(255, 255, 255)
            header = headers[i] if i < len(headers) else ""
            shown = _display_cell(cells[i], header)
            pdf.cell(
                widths[i],
                row_h,
                _clip(pdf, shown, widths[i], size, family, is_total),
                border=0,
                fill=True,
            )
        pdf.ln()

    raw = pdf.output()
    return bytes(raw) if isinstance(raw, (bytes, bytearray)) else raw.encode("latin-1")


def write_zip(folder, folder_name, names):
    data = BytesIO()
    with ZipFile(data, "w", ZIP_DEFLATED) as zf:
        for name in names:
            path = folder / name
            if path.is_file():
                zf.write(path, name)
    payload = data.getvalue()
    (folder / zip_filename(folder_name)).write_bytes(payload)
    return payload, zip_filename(folder_name)


def export_message(count, skipped, failed, folder_name):
    message = "%s PDFs exported to vay_reports/%s" % (count, folder_name)
    if skipped:
        message += ". %s already existed and were skipped." % skipped
    if failed:
        message += " %s failed — run Export again after a few minutes." % failed
    return message


def export_reports(reports, dt, replace=False, zip_reports=None, on_progress=None):
    folder, folder_name = folder_for_date(dt)
    selected = list(reports or [])
    names = expected_pdf_names(selected)
    if replace:
        for name in names:
            path = folder / name
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
    exported = 0
    skipped = 0
    failed = 0
    by_name = {}
    for report in selected:
        by_name[pdf_filename((report or {}).get("id"))] = report
    for index, report in enumerate(selected):
        name = pdf_filename((report or {}).get("id"))
        path = folder / name
        if path.is_file() and not replace:
            skipped += 1
            if on_progress:
                on_progress(index, report, "done")
            continue
        if on_progress:
            on_progress(index, report, "running")
        try:
            path.write_bytes(report_pdf_bytes(by_name[name]))
            exported += 1
            if on_progress:
                on_progress(index, report, "done")
        except Exception:
            log.exception("PDF export failed for %s", name)
            failed += 1
            if on_progress:
                on_progress(index, report, "failed")
            if path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
    if on_progress:
        on_progress(len(selected), None, "zip")
    zip_names = expected_pdf_names(zip_reports if zip_reports is not None else selected)
    zip_bytes, zip_name = write_zip(folder, folder_name, zip_names)
    return {
        "count": exported,
        "skipped": skipped,
        "failed": failed,
        "folder": "vay_reports/%s" % folder_name,
        "folder_name": folder_name,
        "zip_bytes": zip_bytes,
        "zip_name": zip_name,
        "message": export_message(exported, skipped, failed, folder_name),
    }
