"""Vay Reports Streamlit app. Does not write to the AppSheet workbook."""

from datetime import datetime

import streamlit as st

from vay.dates import today_ist
from vay.engine import generate
from vay.export_excel import write_workbook
from vay.load import load_sources
import importlib

from vay import ui as vay_ui

importlib.reload(vay_ui)
from vay.ui import (
    find_followup,
    followup_groups,
    friendly_title,
    inject_css,
    missing_pack_notes,
    profit_skipped_note,
    render_legend,
    render_report_table,
    report_id,
    reports_in_group,
    unique_by_id,
    upload_hint,
    visible_groups,
)

st.set_page_config(page_title="Vay Reports", layout="wide", initial_sidebar_state="collapsed")

if "result" not in st.session_state:
    st.session_state.result = None
    st.session_state.xlsx = None
    st.session_state.report_dt = None
    st.session_state.run_meta = None
    st.session_state.create_error = ""


def _phases(packs):
    phases = []
    if packs.get("core"):
        phases.append("core")
    if packs.get("fiscal"):
        phases.append("fiscal")
    if packs.get("items"):
        phases.append("items")
    if packs.get("profit"):
        phases.extend(["profit", "expenses", "itemprofit"])
    return phases


def _raw_details(load_errors, statuses):
    lines = []
    for sheet, err in (load_errors or {}).items():
        lines.append("%s: %s" % (sheet, err))
    for row in statuses or []:
        if row.get("status") in ("FAILED", "SKIPPED") and row.get("message"):
            lines.append("%s: %s" % (row.get("report"), row.get("message")))
    return lines


def render_setup():
    today = today_ist().date()
    report_date = st.date_input("Report date", value=today, help="Usually leave this as today.")
    pack_core = st.checkbox("Sales, collections, and follow-up", value=True)
    pack_fiscal = st.checkbox("Month-by-month by year", value=True)
    pack_items = st.checkbox("Items and stock", value=False)
    pack_profit = st.checkbox("Profit and expenses", value=False)
    packs = {"core": pack_core, "fiscal": pack_fiscal, "items": pack_items, "profit": pack_profit}
    combined = st.file_uploader("Your Excel file", type=["xlsx", "xls"], help=upload_hint(packs))
    files = {}
    with st.expander("Need to upload sheets one by one?"):
        for name in ("sales", "receipt", "arr", "items", "stock", "payments"):
            files[name] = st.file_uploader(name, type=["xlsx", "xls", "csv"], key="up_" + name)
    return {
        "report_date": report_date,
        "packs": packs,
        "combined": combined,
        "files": files,
    }


def _run(setup):
    st.session_state.create_error = ""
    packs = setup["packs"]
    if not any(packs.values()):
        st.session_state.create_error = "Choose at least one set of reports."
        st.session_state.result = None
        st.session_state.xlsx = None
        return
    with st.spinner("Creating reports… this can take a minute."):
        tables, load_errors = load_sources(setup["files"], setup["combined"])
        dt = datetime(setup["report_date"].year, setup["report_date"].month, setup["report_date"].day, 12)
        st.session_state.run_meta = {
            "packs": dict(packs),
            "sheets": list(tables.keys()),
            "load_errors": dict(load_errors or {}),
        }
        st.session_state.report_dt = dt
        if not tables:
            st.session_state.result = {"reports": [], "statuses": [], "fy_label": ""}
            st.session_state.xlsx = None
            st.session_state.create_error = "No sheets could be read from that file."
            return
        result = generate(tables, dt, _phases(packs))
        st.session_state.result = result
        st.session_state.xlsx = write_workbook(result["reports"]) if result.get("reports") else None
        if not result.get("reports"):
            st.session_state.create_error = "No reports could be created from that file."


def render_browse(result, xlsx):
    meta = st.session_state.run_meta or {}
    dt = st.session_state.report_dt
    reports = result.get("reports") or []
    packs = meta.get("packs") or {}
    sheets = meta.get("sheets") or []
    st.caption("Showing reports for **%s**." % dt.strftime("%d %b %Y") if dt else "")
    if result.get("fy_label"):
        st.caption("Years: **%s**" % result["fy_label"])
    for note in missing_pack_notes(packs, sheets):
        st.info(note)
    profit_reps = reports_in_group(reports, "Profit")
    skip = profit_skipped_note(packs, sheets, True, profit_reps)
    if skip:
        st.info(skip)
    if xlsx and dt:
        st.download_button(
            "Download Excel",
            data=xlsx,
            file_name="vay_reports_%s.xlsx" % dt.strftime("%Y-%m-%d"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    details = _raw_details(meta.get("load_errors"), result.get("statuses"))
    if details:
        with st.expander("Details"):
            for line in details:
                st.text(line)

    groups = visible_groups(reports)
    if not groups:
        st.info("No reports to show.")
        return
    group = st.radio("Report type", groups, index=0, horizontal=True)
    report = None
    query_key = "find"
    year_key = "fy"
    if group == "Follow-up":
        types = []
        if followup_groups(reports, "sales"):
            types.append(("Sales", "sales"))
        if followup_groups(reports, "collection"):
            types.append(("Collections", "collection"))
        if not types:
            st.info("No rows for this report.")
            return
        if len(types) == 1:
            kind_label, kind = types[0]
            st.caption(kind_label)
        else:
            kind_label = st.radio("Follow-up", [t[0] for t in types], horizontal=True)
            kind = dict(types)[kind_label]
        names = followup_groups(reports, kind)
        group_name = st.selectbox("Group", names, key="follow_group_" + kind)
        report = find_followup(reports, kind, group_name)
        render_legend(kind)
        query_key = "find_follow_" + kind
        year_key = "fy_follow"
    else:
        choices = unique_by_id(reports_in_group(reports, group))
        if not choices:
            st.info("No rows for this report.")
            return
        labels = [friendly_title(r) for r in choices]
        picked = st.selectbox("Report", labels, key="rep_" + group)
        report = choices[labels.index(picked)]
        query_key = "find_" + report_id(report)
        year_key = "fy_" + report_id(report)
    if not report:
        st.info("No rows for this report.")
        return
    query = st.text_input("Find a name", key=query_key)
    render_report_table(report, query, year_key=year_key)


has_reports = bool(st.session_state.result and st.session_state.result.get("reports"))
inject_css(compact=not has_reports)
st.title("Vay Reports")

if has_reports:
    render_browse(st.session_state.result, st.session_state.xlsx)
    with st.expander("Change file or date"):
        setup = render_setup()
        if st.button("Create reports", key="create_again"):
            _run(setup)
            st.rerun()
else:
    st.caption("Upload your Excel and create the reports.")
    setup = render_setup()
    if st.button("Create reports", key="create_first"):
        _run(setup)
        st.rerun()
    if st.session_state.create_error:
        st.error(st.session_state.create_error)
        meta = st.session_state.run_meta or {}
        for note in missing_pack_notes(meta.get("packs") or {}, meta.get("sheets") or []):
            st.info(note)
        details = _raw_details(meta.get("load_errors"), (st.session_state.result or {}).get("statuses"))
        if details:
            with st.expander("Details"):
                for line in details:
                    st.text(line)
