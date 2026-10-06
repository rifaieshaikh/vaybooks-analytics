"""Run selected phases. Phases choose outputs; aggregators do not share ctx.phase math.

Profit packs are gated by user permissions in the product API, not by a password here.
Missing columns fail that report and continue.
"""

from vay.dates import build_report_context, iter_fiscal_years, min_dated_source
from vay.passwords import hash_password, password_ok  # noqa: F401 — re-exported for callers
from vay.preprocess import preprocess
from vay.reports import core, fiscal, items, profit
from vay.reports.rounding import round_report


def _need(tables, names):
    missing = [n for n in names if n not in tables]
    if missing:
        raise KeyError("Missing source sheets: " + ", ".join(missing))


def generate(tables, report_date, phases, password=None, password_hash=None, on_progress=None, settlement_mode=None, aging_bands=None, org_policy=None, only_reports=None):
    # password / password_hash kept for call-site compatibility; profit is not password-gated.
    _ = (password, password_hash)
    phases = [p for p in phases if p]
    reports = []
    statuses = []

    tables = preprocess(dict(tables))
    ctx = build_report_context(report_date, org_policy=org_policy)
    fy_month = ctx.get("fiscalYearStartMonth")
    ctx["fiscalYears"] = iter_fiscal_years(
        min_dated_source(tables, ctx["reportDate"]), ctx["reportDate"], start_month=fy_month,
    )
    if settlement_mode:
        from vay.settlement import normalize_mode
        ctx["settlement_mode"] = normalize_mode(settlement_mode)
    if aging_bands is not None:
        from vay.settlement import normalize_aging_bands
        ctx["aging_bands"] = normalize_aging_bands(aging_bands)
    else:
        from vay.settlement import default_aging_bands
        ctx["aging_bands"] = default_aging_bands()
    if not ctx.get("payment_categories"):
        from vay.packs import default_expense_account_map
        ctx["payment_categories"] = default_expense_account_map()

    runnable = list(phases)
    only = {str(name) for name in (only_reports or []) if name} or None

    def selected(name):
        return only is None or name in only

    def add_status(name, status, rows=0, message=""):
        statuses.append({"report": name, "status": status, "rows": rows, "message": message})

    def emit(step_id, title, group, state, message=""):
        if on_progress:
            on_progress(step_id, title, group, state, 0, message)

    def fail(name, group, message):
        add_status(name, "FAILED", 0, message)
        emit(name, name, group, "failed", message)

    def run(name, fn, group="Reports"):
        if not selected(name):
            return None
        step_id = name
        emit(step_id, name, group, "running")
        try:
            result = fn()
            if result is None:
                emit(step_id, name, group, "done")
                return None
            if isinstance(result, list):
                reports.extend(result)
                n = sum(len(r.get("rows") or []) for r in result)
            else:
                reports.append(result)
                n = len(result.get("rows") or [])
            add_status(name, "SUCCESS", n, "")
            emit(step_id, name, group, "done")
            return result
        except Exception as exc:
            fail(name, group, str(exc))
            return None

    core_names = (
        "Account performance",
        "Group performance",
        "Sales rep performance",
        "Sales follow-up",
        "Collection follow-up",
    )
    if "core" in runnable and any(selected(name) for name in core_names):
        try:
            _need(tables, ["sales", "receipt", "arr"])
        except Exception as exc:
            for name, group in (
                ("Account performance", "Performance"),
                ("Group performance", "Performance"),
                ("Sales rep performance", "Performance"),
                ("Sales follow-up", "Follow-up"),
                ("Collection follow-up", "Follow-up"),
            ):
                if selected(name):
                    fail(name, group, str(exc))
        else:
            need_accounts = any(selected(name) for name in (
                "Account performance", "Group performance", "Sales follow-up", "Collection follow-up", "Sales rep performance",
            ))
            if need_accounts and not selected("Account performance"):
                try:
                    core.account_performance(tables, ctx)
                except Exception as exc:
                    ctx["_account_error"] = str(exc)
            else:
                run("Account performance", lambda: core.account_performance(tables, ctx), "Performance")
            if ctx.get("accounts"):
                run("Group performance", lambda: core.group_performance(ctx), "Performance")
                run("Sales rep performance", lambda: core.sales_rep_performance(tables, ctx), "Performance")
                run("Sales follow-up", lambda: core.sales_follow_ups(ctx), "Follow-up")
                run("Collection follow-up", lambda: core.collection_follow_ups(ctx), "Follow-up")
            else:
                reason = ctx.get("_account_error") or "Account performance data is not available"
                for name, group in (
                    ("Group performance", "Performance"),
                    ("Sales rep performance", "Performance"),
                    ("Sales follow-up", "Follow-up"),
                    ("Collection follow-up", "Follow-up"),
                ):
                    if selected(name):
                        fail(name, group, reason)

    fiscal_names = (
        "Fiscal monthly sales and collection",
        "Fiscal monthly account performance",
        "Fiscal monthly group performance",
    )
    if "fiscal" in runnable and any(selected(name) for name in fiscal_names):
        try:
            _need(tables, ["sales", "receipt", "arr"])
        except Exception as exc:
            for name in fiscal_names:
                if selected(name):
                    fail(name, "Monthly", str(exc))
        else:
            run("Fiscal monthly sales and collection", lambda: fiscal.fiscal_sales_rep(tables, ctx), "Monthly")
            if selected("Fiscal monthly group performance") and not selected("Fiscal monthly account performance"):
                try:
                    fiscal.fiscal_account(tables, ctx)
                except Exception as exc:
                    ctx["_fiscal_account_error"] = str(exc)
            else:
                run("Fiscal monthly account performance", lambda: fiscal.fiscal_account(tables, ctx), "Monthly")
            if ctx.get("fiscalAccounts"):
                run("Fiscal monthly group performance", lambda: fiscal.fiscal_group(ctx), "Monthly")
            elif selected("Fiscal monthly group performance"):
                fail(
                    "Fiscal monthly group performance",
                    "Monthly",
                    ctx.get("_fiscal_account_error") or "Fiscal account data is not available",
                )

    inventory = None
    item_data = None
    item_names = ("Item-wise sales", "Item cost exceptions", "Item monthly quantity")
    profit_item_names = ("Item-wise profit", "Item monthly profit")
    expense_names = ("Expense by category", "Unmapped payment accounts", "Expense by account")
    needs_items = (
        ("items" in runnable and any(selected(name) for name in item_names))
        or ("itemprofit" in runnable and any(selected(name) for name in profit_item_names))
        or ("profit" in runnable and selected("Monthly profit"))
    )
    if needs_items:
        try:
            _need(tables, ["items", "stock"])
            inventory = items.stock_map(tables)
            ctx["inventory"] = inventory
        except Exception as exc:
            for name in item_names + profit_item_names + ("Monthly profit",):
                if selected(name):
                    fail(name, "Items" if name in item_names else "Profit", str(exc))

    if "items" in runnable and inventory is not None and any(selected(name) for name in item_names):
        try:
            item_data = items.item_summaries(tables, ctx, compute_profit=False)
        except Exception as exc:
            for name in item_names:
                if selected(name):
                    fail(name, "Items", str(exc))
        else:
            run("Item-wise sales", lambda: items.item_wise_sales(item_data), "Items")
            run("Item cost exceptions", lambda: items.item_cost_exceptions(item_data), "Items")
            run("Item monthly quantity", lambda: items.item_monthly_qty(item_data), "Items")

    if "itemprofit" in runnable and inventory is not None and any(selected(name) for name in profit_item_names):
        try:
            profit_data = items.item_summaries(tables, ctx, compute_profit=True)
        except Exception as exc:
            for name in profit_item_names:
                if selected(name):
                    fail(name, "Profit", str(exc))
        else:
            run("Item-wise profit", lambda: items.item_wise_profit(profit_data), "Profit")
            run("Item monthly profit", lambda: items.item_monthly_profit(profit_data), "Profit")

    if "profit" in runnable and selected("Monthly profit") and inventory is not None:
        try:
            _need(tables, ["sales", "payments", "items", "stock"])
        except Exception as exc:
            fail("Monthly profit", "Profit", str(exc))
        else:
            run(
                "Monthly profit",
                lambda: profit.monthly_profit_report(profit.payment_summaries(tables, ctx, include_cogs=True), ctx),
                "Profit",
            )

    if "expenses" in runnable and any(selected(name) for name in expense_names):
        try:
            _need(tables, ["payments"])
            exp = profit.payment_summaries(tables, ctx, include_cogs=False)
        except Exception as exc:
            for name in expense_names:
                if selected(name):
                    fail(name, "Profit", str(exc))
        else:
            run("Expense by category", lambda: profit.expense_by_category(exp), "Profit")
            run("Unmapped payment accounts", lambda: profit.unmapped_payment_accounts(exp), "Profit")
            run("Expense by account", lambda: profit.expense_by_account(exp), "Profit")

    if ("core" in runnable or "items" in runnable) and selected("Source data warnings"):
        run(
            "Source data warnings",
            lambda: core.source_data_warnings(tables, ctx, runnable, inventory),
            "Data issues",
        )

    for report in reports:
        round_report(report)

    return {
        "reports": reports,
        "statuses": statuses,
        "ctx": ctx,
        "fy_label": "%s … %s" % (
            ctx["fiscalYears"][0].strftime("%Y") + "-" + str(ctx["fiscalYears"][0].year + 1)[2:],
            ctx["fiscalYears"][-1].strftime("%Y") + "-" + str(ctx["fiscalYears"][-1].year + 1)[2:],
        ) if ctx["fiscalYears"] else "",
    }


def planned_report_steps(packs, reports=None):
    """Static step list for Create progress UI before generate runs."""
    from server.settings import PACK_PHASES

    phases = []
    for pack, on in (packs or {}).items():
        if on:
            for p in PACK_PHASES.get(pack) or []:
                if p not in phases:
                    phases.append(p)
    steps = []
    if "core" in phases:
        steps.extend([
            {"id": "Sales rep performance", "title": "Sales rep performance", "group": "Performance", "state": "waiting"},
            {"id": "Account performance", "title": "Account performance", "group": "Performance", "state": "waiting"},
            {"id": "Group performance", "title": "Group performance", "group": "Performance", "state": "waiting"},
            {"id": "Sales follow-up", "title": "Sales follow-up", "group": "Follow-up", "state": "waiting"},
            {"id": "Collection follow-up", "title": "Collection follow-up", "group": "Follow-up", "state": "waiting"},
        ])
    if "fiscal" in phases:
        steps.extend([
            {"id": "Fiscal monthly sales and collection", "title": "Fiscal monthly sales and collection", "group": "Monthly", "state": "waiting"},
            {"id": "Fiscal monthly account performance", "title": "Fiscal monthly account performance", "group": "Monthly", "state": "waiting"},
            {"id": "Fiscal monthly group performance", "title": "Fiscal monthly group performance", "group": "Monthly", "state": "waiting"},
        ])
    if "items" in phases:
        steps.extend([
            {"id": "Item-wise sales", "title": "Item-wise sales", "group": "Items", "state": "waiting"},
            {"id": "Item cost exceptions", "title": "Item cost exceptions", "group": "Items", "state": "waiting"},
            {"id": "Item monthly quantity", "title": "Item monthly quantity", "group": "Items", "state": "waiting"},
        ])
    if "itemprofit" in phases or "profit" in phases:
        if "itemprofit" in phases:
            steps.extend([
                {"id": "Item-wise profit", "title": "Item-wise profit", "group": "Profit", "state": "waiting"},
                {"id": "Item monthly profit", "title": "Item monthly profit", "group": "Profit", "state": "waiting"},
            ])
        if "profit" in phases:
            steps.append({"id": "Monthly profit", "title": "Monthly profit", "group": "Profit", "state": "waiting"})
        if "expenses" in phases:
            steps.extend([
                {"id": "Expense by category", "title": "Expense by category", "group": "Profit", "state": "waiting"},
                {"id": "Unmapped payment accounts", "title": "Unmapped payment accounts", "group": "Profit", "state": "waiting"},
                {"id": "Expense by account", "title": "Expense by account", "group": "Profit", "state": "waiting"},
            ])
    if "core" in phases or "items" in phases:
        steps.append({"id": "Source data warnings", "title": "Source data warnings", "group": "Data issues", "state": "waiting"})
    steps.extend([
        {"id": "phase2_scorecard", "title": "Scorecard", "group": "Scorecard", "state": "waiting"},
        {"id": "phase2_sales_change", "title": "Sales change", "group": "Scorecard", "state": "waiting"},
        {"id": "phase2_customer_movement", "title": "Customer movement", "group": "Scorecard", "state": "waiting"},
        {"id": "phase2_collection", "title": "Collection worklist", "group": "Follow-up", "state": "waiting"},
        {"id": "phase2_stock", "title": "Stock decisions", "group": "Items", "state": "waiting"},
        {"id": "phase2_quality", "title": "Data quality", "group": "Data issues", "state": "waiting"},
    ])
    steps.extend([
        {"id": "360-customers", "title": "Customers 360", "group": "360 View", "state": "waiting"},
        {"id": "360-groups", "title": "Customer groups 360", "group": "360 View", "state": "waiting"},
        {"id": "360-reps", "title": "Sales reps 360", "group": "360 View", "state": "waiting"},
        {"id": "360-items", "title": "Items 360", "group": "360 View", "state": "waiting"},
        {"id": "360-category", "title": "Category 360", "group": "360 View", "state": "waiting"},
        {"id": "360-item_group", "title": "Item group 360", "group": "360 View", "state": "waiting"},
        {"id": "360-brand", "title": "Brand 360", "group": "360 View", "state": "waiting"},
        {"id": "360-supplier", "title": "Supplier 360", "group": "360 View", "state": "waiting"},
        {"id": "360-repurchase", "title": "Repeat purchases", "group": "360 View", "state": "waiting"},
        {"id": "360-business", "title": "Business 360", "group": "360 View", "state": "waiting"},
    ])
    steps.extend([
        {"id": "reconcile", "title": "Reconciliation", "group": "Checks", "state": "waiting"},
        {"id": "analytics", "title": "Scorecard, sales change, and data checks", "group": "Checks", "state": "waiting"},
        {"id": "dashboard", "title": "Home dashboard", "group": "Checks", "state": "waiting"},
        {"id": "save-reports", "title": "Save workbook", "group": "Checks", "state": "waiting"},
    ])
    chosen = [str(name) for name in (reports or []) if name]
    if chosen:
        want = set(chosen) | {"save-reports"}
        steps = [row for row in steps if row["id"] in want]
    return steps
