"""Non-technical Streamlit shell. Route reports by id and flags, never by exact title."""

import pandas as pd
import streamlit as st

from vay.config import STATUS_COLORS, TEXT_HEADERS

# Screen labels keyed by engine id. Follow-up ids are prefixes (sales_follow_up_*).
FRIENDLY_TITLES = {
    "sales_rep_performance_report": "Sales by person",
    "account_performance_report": "Sales by customer",
    "group_performance_report": "Sales by group",
    "fiscal_monthly_sales_rep_performance_report": "This year by month — people",
    "fiscal_monthly_account_performance_report": "This year by month — customers",
    "fiscal_monthly_group_performance_report": "This year by month — groups",
    "item_wise_sales": "Item sales",
    "item_cost_exceptions": "Items missing cost",
    "item_wise_monthly_qty": "Item quantity by month",
    "item_wise_profit": "Item profit",
    "item_wise_monthly_profit": "Item profit by month",
    "monthly_profit_report": "Profit and loss",
    "expense_by_category": "Expenses by category",
    "expense_by_account": "Expenses by account",
    "unmapped_payment_accounts": "Unmapped payments",
    "source_data_warnings": "Data issues",
}

PERFORMANCE_IDS = (
    "sales_rep_performance_report",
    "account_performance_report",
    "group_performance_report",
)
ITEMS_IDS = (
    "item_wise_sales",
    "item_cost_exceptions",
    "item_wise_monthly_qty",
)
PROFIT_IDS = (
    "monthly_profit_report",
    "expense_by_category",
    "expense_by_account",
    "unmapped_payment_accounts",
    "item_wise_profit",
    "item_wise_monthly_profit",
)

SALES_FOLLOW_PREFIX = "sales_follow_up_"
COLLECTION_FOLLOW_PREFIX = "collection_follow_up_"
GROUP_ORDER = ("Performance", "Follow-up", "Monthly", "Items", "Profit", "Data issues")

SALES_LEGEND = (
    ("URGENT", "Urgent"),
    ("FOLLOW UP", "Follow up"),
    ("NEWLY INACTIVE", "Newly inactive"),
    ("DORMANT", "Dormant"),
)
COLLECTION_LEGEND = (
    ("URGENT", "Urgent"),
    ("FOLLOW UP", "Follow up"),
    ("WATCH", "Watch"),
)

CSS = """
<style>
    .stButton button { width: 100%; min-height: 2.75rem; border-radius: 0.5rem; }
    [data-testid="stHeader"] { background: transparent; }
    .block-container { padding-top: 1.25rem; padding-bottom: 2.5rem; __WIDTH__ }
    div[data-testid="stDataFrame"] { overflow-x: auto; }
    .stAppDeployButton { display: none; }
    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }
    .legend-chip {
        display: inline-block; padding: 0.2rem 0.7rem; margin: 0.15rem 0.25rem 0.15rem 0;
        border-radius: 999px; font-size: 0.9rem;
    }
</style>
"""


def inject_css(compact=False):
    width = "max-width: 44rem;" if compact else ""
    st.markdown(CSS.replace("__WIDTH__", width), unsafe_allow_html=True)


def _two_decimals(val):
    if val is None or val == "":
        return ""
    if isinstance(val, bool):
        return val
    try:
        n = float(val)
    except (TypeError, ValueError):
        return val
    if n != n:
        return ""
    return "{:.2f}".format(n)


def style_status(df, column=""):
    numeric_cols = [c for c in df.columns if c not in TEXT_HEADERS]
    styler = df.style
    if numeric_cols:
        styler = styler.format(_two_decimals, subset=numeric_cols, na_rep="")
    if not column or column not in df.columns:
        return styler
    def color(val):
        hex_color = STATUS_COLORS.get(str(val))
        if not hex_color:
            return ""
        return "background-color: %s" % hex_color
    if hasattr(styler, "map"):
        return styler.map(color, subset=[column])
    return styler.applymap(color, subset=[column])


def fy_blocks(report):
    """Split a wide pair/month report into per-FY frames (no All FYs pair)."""
    if not report.get("wide"):
        return []
    n = report.get("n_fy")
    headers = report["headers"]
    label_cols = report.get("label_cols") or 1
    trailing = report.get("trailing") or 0
    rows = list(report.get("rows") or [])
    if report.get("total"):
        rows.append(report["total"])
    pair = report.get("wide") == "pair"
    if n is None:
        if pair:
            value_cols = len(headers) - label_cols - 2
            n = value_cols // 26
        else:
            value_cols = len(headers) - label_cols - 1 - trailing
            n = value_cols // 13
    blocks = []
    for yi in range(max(n, 1)):
        if pair:
            start = label_cols + yi * 26
            end = start + 26
        else:
            start = label_cols + yi * 13
            end = start + 13
        cols = list(range(label_cols)) + list(range(start, end))
        if trailing:
            t0 = len(headers) - trailing
            cols.extend(range(t0, len(headers)))
        names = [headers[i] for i in cols]
        data = []
        for row in rows:
            data.append([row[i] if i < len(row) else "" for i in cols])
        fy_headers = report.get("header_row1") or []
        title = fy_headers[start] if start < len(fy_headers) else "FY %d" % (yi + 1)
        blocks.append((title or ("Year %d" % (yi + 1)), names, data))
    return blocks


def report_id(report):
    return report.get("id") or ""


def friendly_title(report):
    rid = report_id(report)
    if rid.startswith(SALES_FOLLOW_PREFIX):
        return "Who to follow up — sales"
    if rid.startswith(COLLECTION_FOLLOW_PREFIX):
        return "Who to follow up — collections"
    return FRIENDLY_TITLES.get(rid, report.get("title") or rid)


def followup_group_name(report):
    rid = report_id(report)
    if rid.startswith(SALES_FOLLOW_PREFIX):
        return rid[len(SALES_FOLLOW_PREFIX):]
    if rid.startswith(COLLECTION_FOLLOW_PREFIX):
        return rid[len(COLLECTION_FOLLOW_PREFIX):]
    return ""


def is_sales_followup(report):
    return report_id(report).startswith(SALES_FOLLOW_PREFIX)


def is_collection_followup(report):
    return report_id(report).startswith(COLLECTION_FOLLOW_PREFIX)


def is_wide_report(report):
    return bool(report.get("wide"))


def report_group(report):
    rid = report_id(report)
    if rid.startswith(SALES_FOLLOW_PREFIX) or rid.startswith(COLLECTION_FOLLOW_PREFIX) or report.get("followup"):
        return "Follow-up"
    if rid.startswith("fiscal_monthly_"):
        return "Monthly"
    if rid == "source_data_warnings":
        return "Data issues"
    if rid in PERFORMANCE_IDS:
        return "Performance"
    if rid in ITEMS_IDS:
        return "Items"
    if rid in PROFIT_IDS:
        return "Profit"
    return "Performance"


def visible_groups(reports):
    present = set()
    for report in reports:
        if report_id(report) == "source_data_warnings" and not (report.get("rows") or []):
            continue
        present.add(report_group(report))
    return [name for name in GROUP_ORDER if name in present]


def reports_in_group(reports, group):
    out = []
    for report in reports:
        if report_group(report) != group:
            continue
        if report_id(report) == "source_data_warnings" and not (report.get("rows") or []):
            continue
        out.append(report)
    return out


def followup_groups(reports, kind):
    names = []
    seen = set()
    for report in reports:
        if kind == "sales" and not is_sales_followup(report):
            continue
        if kind == "collection" and not is_collection_followup(report):
            continue
        name = followup_group_name(report)
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    names.sort(key=lambda a: a.lower())
    return names


def find_followup(reports, kind, group):
    prefix = SALES_FOLLOW_PREFIX if kind == "sales" else COLLECTION_FOLLOW_PREFIX
    want = prefix + group
    for report in reports:
        if report_id(report) == want:
            return report
    return None


def unique_by_id(reports):
    seen = set()
    out = []
    for report in reports:
        rid = report_id(report)
        if rid in seen:
            continue
        seen.add(rid)
        out.append(report)
    return out


def _is_total_label(val):
    return str(val or "").strip().lower() == "total"


def search_columns(report, headers):
    """Column indexes to match for Find a name. Follow-ups have no Total row."""
    rid = report_id(report)
    if rid == "source_data_warnings":
        cols = []
        for name in ("Type", "Key", "Detail"):
            if name in headers:
                cols.append(headers.index(name))
        return cols
    key_col = report.get("key_col")
    if key_col is None:
        key_col = 0
    cols = [key_col]
    if rid == "fiscal_monthly_account_performance_report" and 1 not in cols:
        cols.append(1)
    return [i for i in cols if i < len(headers)]


def filter_dataframe(df, report, query):
    if df is None or df.empty or not str(query or "").strip():
        return df
    q = str(query).strip().lower()
    headers = list(df.columns)
    mask = pd.Series(False, index=df.index)
    for i in search_columns(report, headers):
        mask = mask | df.iloc[:, i].astype(str).str.lower().str.contains(q, regex=False, na=False)
    if report.get("total"):
        mask = mask | df.iloc[:, 0].astype(str).map(_is_total_label)
    return df[mask]


def upload_hint(packs):
    need = []
    if packs.get("core") or packs.get("fiscal"):
        need.extend(["sales", "receipt", "arr"])
    if packs.get("items"):
        need.extend(["items", "stock"])
    if packs.get("profit"):
        need.extend(["items", "stock", "payments"])
    ordered = []
    for name in need:
        if name not in ordered:
            ordered.append(name)
    if not ordered:
        return "Export from AppSheet as Excel."
    if len(ordered) == 1:
        sheets = ordered[0]
    elif len(ordered) == 2:
        sheets = "%s and %s" % (ordered[0], ordered[1])
    else:
        sheets = ", ".join(ordered[:-1]) + ", and " + ordered[-1]
    return "Export from AppSheet as Excel. The file should have sheets named %s." % sheets


def missing_pack_notes(packs, sheets):
    sheets = set(sheets or [])
    notes = []
    if packs.get("items"):
        if "items" not in sheets or "stock" not in sheets:
            notes.append("Items need sheets named items and stock.")
    if packs.get("profit"):
        need = ("items", "stock", "payments")
        if any(name not in sheets for name in need):
            if "payments" not in sheets and "items" in sheets and "stock" in sheets:
                notes.append("Profit needs a sheet named payments.")
            else:
                notes.append("Profit needs sheets named items, stock, and payments.")
    return notes


def profit_skipped_note(packs, sheets, password_accepted, profit_reports):
    if not packs.get("profit") or profit_reports:
        return ""
    sheets = set(sheets or [])
    if all(name in sheets for name in ("items", "stock", "payments")) and not password_accepted:
        return "Profit was skipped because the password was not accepted."
    return ""


def render_legend(kind):
    items = SALES_LEGEND if kind == "sales" else COLLECTION_LEGEND
    chips = []
    for code, label in items:
        color = STATUS_COLORS.get(code, "#eeeeee")
        chips.append(
            '<span class="legend-chip" style="background:%s">%s</span>' % (color, label)
        )
    st.markdown(" ".join(chips), unsafe_allow_html=True)


def _to_frame(report, names=None, data=None):
    if names is None:
        headers = report["headers"]
        rows = list(report.get("rows") or [])
        if report.get("total"):
            rows.append(report["total"])
        return pd.DataFrame(rows, columns=headers)
    return pd.DataFrame(data, columns=names)


def render_report_table(report, query, year_key="fy"):
    if is_wide_report(report):
        blocks = fy_blocks(report)
        if not blocks:
            st.info("No rows for this report.")
            return
        labels = [block[0] for block in blocks]
        chosen = st.selectbox("Year", labels, index=len(labels) - 1, key=year_key)
        _title, names, data = blocks[labels.index(chosen)]
        df = _to_frame(report, names, data)
    else:
        df = _to_frame(report)
    filtered = filter_dataframe(df, report, query)
    if filtered is None or filtered.empty:
        st.info("No rows for this report.")
        return
    styled = style_status(filtered, report.get("status_header") or "")
    st.dataframe(styled, use_container_width=True, hide_index=True)
    st.caption("%d row(s)" % len(filtered))
