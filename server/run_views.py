"""Persist and load 360 view snapshots attached to a report run."""

from __future__ import annotations

import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy

from vay.dates import clean_text
from vay.settlement import BUCKET_KEYS

from server.customers import (
    NOTE_TYPE,
    _customer_doc,
    account_uk,
    customer_directory_rows,
    ensure_detail_settlements,
    get_customer,
    list_activity_assignees,
    list_activity_kinds,
    party_type_label,
)
from server.groups360 import get_group, list_groups
from server.items360 import (
    _apply_buy_fields,
    _build_insight,
    _hold_map,
    _holding_for,
    get_item,
    list_items,
)
from server.reps360 import get_rep, list_reps


_CACHE = {}


def _json_safe(value):
    return json.loads(json.dumps(value, default=str))


def _latest_succeeded(store):
    for doc in store.list_runs() or []:
        if doc.get("status") == "succeeded":
            return doc
    return None


def resolve_run(store, run_id=None):
    if run_id:
        doc = store.get_run(run_id)
        if doc and doc.get("status") == "succeeded":
            return doc
        return None
    return _latest_succeeded(store)


def build_views_snapshot(store, on_progress=None, include_repurchase=True, only=None):
    # Re-import so Create jobs always use current settlement helpers (avoid stale reload).
    from server.book import load_book
    from server.customers import customer_directory_rows
    from server.groups360 import _group_rows, get_group
    from server.reps360 import _rep_rows, get_rep

    selected_steps = None if only is None else {str(name) for name in only}

    def emit(step_id, title, state, fraction=0):
        if selected_steps is not None and step_id not in selected_steps:
            return
        if not on_progress:
            return
        try:
            on_progress(step_id, title, "360 View", state, fraction)
        except TypeError as exc:
            if "argument" not in str(exc):
                raise
            on_progress(step_id, title, "360 View", state)

    def tick(step_id, title, index, total):
        if total <= 0:
            return
        stride = max(1, total // 40)
        if index not in (1, total) and index % stride:
            return
        emit(step_id, "%s · %d of %d" % (title, index, total), "running", index / float(total))
        time.sleep(0)

    emit("360-customers", "Customers 360", "running")
    book = load_book(store)
    directory = customer_directory_rows(store)
    from server.ar_balance import annotate_customer, party_ledgers
    from server.org_policy import get_org_policy
    from server.view_workers import (
        _stop_executor,
        bundle_dimension,
        build_item_cards_job,
        choose_workers,
        item_card_book,
        open_pool,
        settle_customers,
    )
    ledgers = party_ledgers(store)
    tolerance = get_org_policy(store)["ar_balance_tolerance"]
    store._ar_ledgers = ledgers
    store._ar_tolerance = tolerance
    customer_rows = [row for row in (directory.get("rows") or []) if row.get("uk")]
    customer_total = len(customer_rows)
    workers = choose_workers(customer_total)
    overlap_items = workers >= 2
    customer_workers = workers - 1 if overlap_items else workers
    executor = open_pool(workers) if overlap_items else None
    item_future = None
    try:
        for row in directory.get("rows") or []:
            row.update(annotate_customer(store, row.get("name"), ledgers=ledgers, tolerance=tolerance))
        if executor is not None:
            emit("360-items", "Items 360", "running")
            item_future = executor.submit(build_item_cards_job, item_card_book(book))

        def on_customer(index, total):
            tick("360-customers", "Customers 360", index, total)

        customers = settle_customers(
            store,
            book,
            customer_rows,
            workers=customer_workers,
            ledgers=ledgers,
            tolerance=tolerance,
            on_tick=on_customer,
            executor=executor if customer_workers >= 2 else None,
        )
        if customers:
            sample = next(iter(customers.values()))
            if not isinstance((sample or {}).get("settlements"), dict):
                raise RuntimeError("360 snapshot missing settlements on customer detail")
            missing = sum(1 for d in customers.values() if not isinstance((d or {}).get("settlements"), dict))
            if missing:
                raise RuntimeError("360 snapshot missing settlements on %d customers" % missing)
        book["_settled_customers"] = customers
    except Exception:
        _stop_executor(executor)
        executor = None
        raise
    finally:
        store._ar_ledgers = None
        store._ar_tolerance = None
    emit("360-customers", "Customers 360", "done")

    item_cards = None
    default_min = 0
    default_max_days = 60
    try:
        emit("360-groups", "Customer groups 360", "running")
        _data, group_rows = _group_rows(store)
        groups_payload = {
            "groups": group_rows,
            "options": {
                "rep": sorted({r for row in group_rows for r in (row.get("reps") or [])}, key=str.lower),
                "status": sorted({row.get("status_label") for row in group_rows if row.get("status_label")}),
            },
        }
        group_details = {}
        group_work = [row for row in group_rows if row.get("uk")]
        group_total = len(group_work)
        for index, row in enumerate(group_work, start=1):
            uk = row.get("uk") or ""
            detail = get_group(store, uk)
            if detail:
                group_details[uk] = detail
            tick("360-groups", "Customer groups 360", index, group_total)
        emit("360-groups", "Customer groups 360", "done")

        emit("360-reps", "Sales reps 360", "running")
        _data, _books, _by_rep, rep_rows = _rep_rows(store)
        reps_payload = {
            "reps": rep_rows,
            "options": {
                "group": sorted({g for row in rep_rows for g in (row.get("groups") or [])}, key=str.lower),
                "status": sorted({row.get("status_label") for row in rep_rows if row.get("status_label")}),
            },
        }
        rep_details = {}
        rep_work = [row for row in rep_rows if row.get("uk")]
        rep_total = len(rep_work)
        for index, row in enumerate(rep_work, start=1):
            uk = row.get("uk") or ""
            detail = get_rep(store, uk)
            if detail:
                rep_details[uk] = detail
            tick("360-reps", "Sales reps 360", index, rep_total)
        emit("360-reps", "Sales reps 360", "done")

        if item_future is not None:
            item_cards, default_min, default_max_days = item_future.result()
        else:
            emit("360-items", "Items 360", "running")
            from server.items360 import _build_item_cards
            book = load_book(store)
            item_cards, default_min, default_max_days = _build_item_cards(book)
    finally:
        _stop_executor(executor)
        executor = None
        item_future = None

    item_details = {}
    item_work = [card for card in item_cards if card.get("uk")]
    item_total = len(item_work)
    for index, card in enumerate(item_work, start=1):
        uk = card.get("uk") or ""
        detail = get_item(store, uk)
        if detail:
            item_details[uk] = detail
        tick("360-items", "Items 360", index, item_total)
    buy_cards = [c for c in item_cards if c.get("status") in ("low", "soon") and (c.get("buy_qty") or 0) > 0]
    items_payload = {
        "items": item_cards,
        "options": {
            "item": sorted({c["name"] for c in item_cards if c.get("name")}),
            "status": sorted({c["status_label"] for c in item_cards if c.get("status_label")}),
            "position": sorted({c["stock_position_label"] for c in item_cards if c.get("stock_position_label")}),
        },
        "default_min": default_min,
        "default_max_days": default_max_days,
        "low_count": sum(1 for c in item_cards if c.get("status") == "low"),
        "soon_count": sum(1 for c in item_cards if c.get("status") == "soon"),
        "under_count": sum(1 for c in item_cards if c.get("stock_position") == "under"),
        "over_count": sum(1 for c in item_cards if c.get("stock_position") == "over"),
        "dead_count": sum(1 for c in item_cards if c.get("stock_position") == "dead"),
        "out_of_stock_count": sum(1 for c in item_cards if not c.get("in_stock")),
        "buy_count": len(buy_cards),
        "buy_qty_sum": round(sum(float(c.get("buy_qty") or 0) for c in buy_cards), 2),
        "buy_value_sum": round(sum(
            float(c.get("buy_qty") or 0) * float(c.get("rate") or 0) for c in buy_cards
        ), 2),
    }
    emit("360-items", "Items 360", "done")

    from server.item_dims import DIMENSIONS, _bundle, dimension_inputs
    dim_cards, dim_attrs, dim_rolls = dimension_inputs(store, book, item_cards)
    item_dims = {}

    def _pack_dimension(key, built):
        spec = DIMENSIONS[key]
        item_dims[key] = {
            "dimension": built["dimension"],
            "label": built["label"],
            "plural": built["plural"],
            "none_label": built["none_label"],
            "hash": built["hash"],
            "rows": [{
                k: v for k, v in row.items()
                if k not in ("members", "months", "fy_years", "groups", "reps")
            } for row in built["rows"]],
            "details": built["details"],
        }
        emit("360-" + key, spec["label"] + " 360", "done")

    dim_payloads = [
        {
            "cards": dim_cards,
            "attrs": dim_attrs,
            "key": key,
            "spec": spec,
            "rolls": dim_rolls,
            "as_of": book.get("as_of"),
            "start_month": book.get("fiscal_year_start_month"),
        }
        for key, spec in DIMENSIONS.items()
    ]
    if workers >= 2 and len(dim_payloads) > 1:
        for key, spec in DIMENSIONS.items():
            emit("360-" + key, spec["label"] + " 360", "running")
        with ProcessPoolExecutor(max_workers=min(workers, len(dim_payloads))) as pool:
            futures = [pool.submit(bundle_dimension, payload) for payload in dim_payloads]
            for future in as_completed(futures):
                key, built = future.result()
                _pack_dimension(key, built)
    else:
        for key, spec in DIMENSIONS.items():
            emit("360-" + key, spec["label"] + " 360", "running")
            built = _bundle(
                dim_cards, dim_attrs, key, spec, dim_rolls, keep_members=False,
            )
            _pack_dimension(key, built)

    if include_repurchase:
        from server.repurchase import ensure_repurchase, stamp_saved_details
        emit("360-repurchase", "Repeat purchases", "running")
        saved = ensure_repurchase(book)
        for dim_key, packed in item_dims.items():
            stamp_saved_details(saved, packed.get("details"), dim_key)
        emit("360-repurchase", "Repeat purchases", "done")

    return _json_safe({
        "as_of": _iso_as_of(directory.get("as_of")),
        "directory": {
            "ver": directory.get("ver"),
            "rows": directory.get("rows") or [],
            "counts": directory.get("counts") or {},
            "attention": directory.get("attention") or [],
            "options": directory.get("options") or {},
        },
        "customers": customers,
        "groups": groups_payload.get("groups") or [],
        "group_details": group_details,
        "group_options": groups_payload.get("options") or {},
        "reps": reps_payload.get("reps") or [],
        "rep_details": rep_details,
        "rep_options": reps_payload.get("options") or {},
        "items": items_payload.get("items") or [],
        "item_details": item_details,
        "item_options": items_payload.get("options") or {},
        "default_min": items_payload.get("default_min") or 0,
        "default_max_days": items_payload.get("default_max_days") or 60,
        "low_count": items_payload.get("low_count") or 0,
        "soon_count": items_payload.get("soon_count") or 0,
        "under_count": items_payload.get("under_count") or 0,
        "over_count": items_payload.get("over_count") or 0,
        "dead_count": items_payload.get("dead_count") or 0,
        "out_of_stock_count": items_payload.get("out_of_stock_count") or 0,
        "buy_count": items_payload.get("buy_count") or 0,
        "buy_qty_sum": items_payload.get("buy_qty_sum") or 0,
        "buy_value_sum": items_payload.get("buy_value_sum") or 0,
        "item_dims": item_dims,
    })


def _iso_as_of(value):
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value or "")


def invalidate_views_cache(run_id=None):
    if run_id is None:
        _CACHE.clear()
        return
    _CACHE.pop(str(run_id), None)


def _persist_split(store, run, data):
    """Turn one saved 360 file into separate page documents, once."""
    from server.view_parts import SnapshotViews, save_view_parts
    rid = str(run.get("_id") or run.get("id") or "")
    save_view_parts(store, rid, data)
    store.update_run(rid, {"views_split": True})
    run["views_split"] = True
    return SnapshotViews(store, rid)


def load_run_views(store, run_id=None):
    run = resolve_run(store, run_id)
    if not run:
        return None, None
    rid = str(run.get("_id") or run.get("id") or "")
    if run.get("views_split"):
        from server.view_parts import SnapshotViews
        return run, SnapshotViews(store, rid)
    book_id = run.get("book_json_id")
    if not book_id:
        return run, None
    cache_key = "%s:%s" % (rid, book_id)
    cached = _CACHE.get(cache_key)
    if getattr(cached, "split", False):
        return run, cached
    if isinstance(cached, dict):
        views = _persist_split(store, run, cached)
        _CACHE[cache_key] = views
        return run, views
    stale = [k for k in _CACHE if k == rid or k.startswith(rid + ":")]
    for k in stale:
        _CACHE.pop(k, None)
    blob = store.get_blob(book_id)
    if not blob or not blob.get("data"):
        return run, None
    try:
        data = json.loads(blob["data"].decode("utf-8"))
    except (TypeError, ValueError, AttributeError, json.JSONDecodeError):
        return run, None
    views = _persist_split(store, run, data)
    _CACHE[cache_key] = views
    return run, views


def import_newer_than(store, run, uploads=None):
    if not run:
        return False
    run_at = run.get("created_at")
    if uploads is None:
        uploads = store.list_uploads() or []
    if not uploads:
        return False
    latest = uploads[0].get("created_at")
    if not latest or not run_at:
        return False
    try:
        return latest > run_at
    except TypeError:
        return str(latest) > str(run_at)


def _overlay_customer(store, detail):
    if not detail:
        return detail
    out = deepcopy(detail)
    uk = out.get("uk") or ""
    doc = _customer_doc(store, uk)
    fields = (doc or {}).get("fields") or {}
    party_type = clean_text(fields.get("Party Type"))
    out["party_type"] = party_type
    out["party_type_label"] = party_type_label(store, party_type) if party_type else ""
    from server.order_check import policy_meta_for_customer, read_customer_flags

    flags = read_customer_flags(fields)
    out["premium"] = flags["premium"]
    out["blacklisted"] = flags["blacklisted"]
    out.update(policy_meta_for_customer(store, out))
    out["activity_kinds"] = list_activity_kinds(store)
    out["assignees"] = list_activity_assignees(store)
    notes = []
    name_l = clean_text(out.get("name")).lower()
    cust_uk = account_uk(uk).lower()
    for row in store.rows_of_type(NOTE_TYPE):
        nfields = row.get("fields") or {}
        note_party = clean_text(nfields.get("Account Name")).lower()
        note_cust = account_uk(nfields.get("customer_uk") or "").lower()
        if note_party == name_l or note_cust == cust_uk or note_cust == account_uk(name_l).lower():
            notes.append({
                "kind": clean_text(nfields.get("Kind")),
                "date": nfields.get("Date") or "",
                "date_label": nfields.get("Date") or "",
                "amount": 0,
                "label": clean_text(nfields.get("Kind Label") or nfields.get("Kind")),
                "rep": clean_text(nfields.get("Sales Rep") or nfields.get("Assignee")),
                "invoice": "",
                "invoice_id": "",
                "note": clean_text(nfields.get("Note")),
                "party": clean_text(nfields.get("Account Name")),
                "logged": True,
                "id": row.get("uk") or "",
            })
    activity = [e for e in (out.get("activity") or []) if not e.get("logged")]
    activity.extend(notes)
    activity.sort(key=lambda e: e.get("date") or "", reverse=True)
    out["activity"] = activity
    if name_l and out.get("balance_issue") != "missing_arr":
        from server.customers import ar_mismatch_for_party
        from vay.dates import parse_date

        as_of = parse_date(out.get("as_of"))
        statement = ar_mismatch_for_party(store, name_l, out.get("due") or 0, as_of)
        out["ar_mismatch"] = statement
        if out.get("arr_balance") is not None:
            out["ledger_opening"] = statement.get("opening") or 0
            out["balance_diff"] = statement.get("balance_diff")
            out["balance_issue"] = statement.get("balance_issue") or ""
    return out


def _overlay_party_entity(store, entity, detail):
    """Merge live due-days + order-check policy onto group/rep snapshot detail."""
    if not detail:
        return detail
    out = deepcopy(detail)
    from server.due_days import resolve_entity_due_days
    from server.order_check import policy_meta_for_entity

    name = clean_text(out.get("name") or out.get("uk") or "")
    due_meta = resolve_entity_due_days(store, entity, name)
    out["due_days"] = due_meta["due_days"]
    out["due_days_source"] = due_meta["source"]
    out["due_days_own"] = due_meta.get("own")
    out.update(policy_meta_for_entity(store, entity, out))
    return out


def _overlay_group(store, detail):
    return _overlay_party_entity(store, "group", detail)


def _overlay_rep(store, detail):
    return _overlay_party_entity(store, "rep", detail)

def _overlay_item(store, detail, holds=None, default_min=None, default_max_days=None):
    if not detail:
        return detail
    out = deepcopy(detail)
    uk = account_uk(out.get("uk") or "")
    if holds is None:
        holds, default_min, default_max_days = _hold_map(store)
    holding = _holding_for(holds, default_min, uk, default_max_days)
    as_of = None
    raw_as_of = out.get("as_of")
    if raw_as_of:
        from vay.dates import parse_date
        as_of = parse_date(raw_as_of)
    _apply_buy_fields(out, holding, as_of=as_of)
    out["holding"] = {
        "min_hold": holding["min_hold"],
        "fill_to": holding.get("fill_to"),
        "lead_days": holding.get("lead_days") or 0,
        "max_days_hold": holding.get("max_days_hold") or default_max_days,
        "own_min": holding.get("own_min") or False,
        "own_max_days": holding.get("own_max_days") or False,
        "uses_default_min": not holding.get("own_min"),
        "uses_default_max_days": not holding.get("own_max_days"),
        "discontinued": bool(holding.get("discontinued")),
    }
    out["default_min"] = default_min
    out["default_max_days"] = default_max_days
    buyers = out.get("buyers")
    if buyers is not None or out.get("insight") is not None:
        saved_concentration = ""
        if buyers is None and isinstance(out.get("insight"), dict):
            saved_concentration = out["insight"].get("concentration_bit") or ""
        out["insight"] = _build_insight(out, buyers or [])
        if buyers is None and saved_concentration:
            out["insight"]["concentration_bit"] = saved_concentration
    return out


def snapshot_list_customers(store, params, views):
    from server.customers import list_customers as live_list
    if views is None:
        return live_list(store, params)
    q = clean_text(params.get("q") or "").lower()
    party = clean_text(params.get("party") or params.get("name"))
    group = clean_text(params.get("group"))
    rep = clean_text(params.get("rep"))
    from server.customers import _eq, _status_id
    status_want = _status_id(params.get("status"))
    try:
        page = max(1, int(params.get("page") or 1))
    except (TypeError, ValueError):
        page = 1
    limit = 50
    from server.ar_balance import reconcile_stored_balance
    from server.org_policy import get_org_policy

    tolerance = get_org_policy(store)["ar_balance_tolerance"]
    rows = [
        reconcile_stored_balance(dict(row), tolerance)
        for row in ((views.get("directory") or {}).get("rows") or [])
    ]
    options = dict((views.get("directory") or {}).get("options") or {})
    options["balance_issue"] = ["Mismatch", "Missing ARR"]
    filtered = []
    flag_want = clean_text(params.get("balance_issue")).lower()
    flag_code = {
        "1": "",
        "true": "",
        "yes": "",
        "balance issues": "",
        "mismatch": "mismatch",
        "mismatched": "mismatch",
        "missing arr": "missing_arr",
        "missing_arr": "missing_arr",
    }.get(flag_want, flag_want)
    for row in rows:
        if q and q not in (row.get("name") or "").lower() and q not in (row.get("group") or "").lower() and q not in (row.get("salesperson") or "").lower():
            continue
        if party and not _eq(row.get("name"), party):
            continue
        if group and not _eq(row.get("group"), group):
            continue
        if rep and not _eq(row.get("salesperson"), rep):
            continue
        if status_want and row.get("status") != status_want:
            continue
        if flag_want:
            issue = row.get("balance_issue") or ""
            if flag_code and issue != flag_code:
                continue
            if not flag_code and not issue:
                continue
        filtered.append(row)
    requested = clean_text(params.get("sort") or "due").lower()
    key = requested
    if key in ("ar_diff", "ar diff", "ardiff"):
        key = "balance_diff"
    if flag_code == "mismatch" and key == "due":
        key = "balance_diff"
    if key in ("party", "customer"):
        key = "name"
    if key in ("rep",):
        key = "salesperson"
    if key == "status":
        key = "status_label"
    if key in ("0-15", "0–15"):
        key = "d0_15"
    if key in ("15-30", "15–30", "16-30", "16–30"):
        key = "d15_30"
    if key in ("30-45", "30–45"):
        key = "d30_45"
    if key in ("45-60", "45–60", "31-60", "31–60"):
        key = "d45_60"
    if key in ("60-90", "60–90"):
        key = "d60_90"
    if key in ("90+", "d90_plus", "60+", "d60_plus", "d60"):
        key = "d90"
    direction = clean_text(params.get("dir") or "desc").lower()
    if direction not in ("asc", "desc"):
        direction = "desc"
    numeric = {"due", "balance_diff", "ledger_gap", *BUCKET_KEYS}

    def sort_val(row):
        if key == "balance_diff":
            val = row.get("balance_diff")
            if val is None:
                return float("-inf") if direction == "desc" else float("inf")
            return abs(val)
        val = row.get(key)
        if val is None:
            return float("-inf") if key in numeric else ""
        if isinstance(val, (int, float)):
            return val
        return str(val).lower()

    filtered.sort(key=sort_val, reverse=(direction == "desc"))
    total = len(filtered)
    start = (page - 1) * limit
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "customers": filtered[start:start + limit],
        "options": options,
        "sort": clean_text(params.get("sort") or "due"),
        "dir": direction,
        "counts": (views.get("directory") or {}).get("counts") or {},
        "attention": (views.get("directory") or {}).get("attention") or [],
        "as_of": views.get("as_of") or "",
        "from_snapshot": True,
    }


def _saved_detail(views, field, uk):
    """One saved profile. A split store reads that document only."""
    uk = account_uk(uk)
    bucket = (views or {}).get(field) or {}
    detail = bucket.get(uk) or bucket.get(uk.lower())
    if detail or getattr(bucket, "kind", None):
        return detail
    want = uk.lower()
    for key, value in bucket.items():
        if account_uk(key).lower() == want:
            return value
    return None


def _stamp_live_flags(store, detail):
    """Party flags and due days from one customer row. Does not scan sales or notes."""
    if not detail:
        return detail
    out = dict(detail)
    uk = account_uk(out.get("uk") or "")
    doc = store.find_row("customer", uk) if uk else None
    fields = (doc or {}).get("fields") or {}
    party_type = clean_text(fields.get("Party Type"))
    if party_type:
        out["party_type"] = party_type
        out["party_type_label"] = party_type_label(store, party_type)
    from server.order_check import policy_meta_for_customer
    out.update(policy_meta_for_customer(store, out))
    from server.due_days import resolve_entity_due_days
    due_meta = resolve_entity_due_days(
        store,
        "customer",
        out.get("name") or uk,
        group=out.get("group") or "",
        rep=out.get("salesperson") or "",
        customer_uk=uk,
    )
    out["due_days"] = due_meta["due_days"]
    out["due_days_source"] = due_meta["source"]
    out["due_days_own"] = due_meta.get("own")
    if "repurchase" in out:
        out.pop("repurchase", None)
        out["repurchase_separate"] = True
    return out


def snapshot_get_customer(store, uk, views):
    if views is None:
        return get_customer(store, uk)
    detail = _saved_detail(views, "customers", uk)
    if not detail:
        return None
    if detail.get("tabs_separate"):
        detail = _attach_customer_tabs(store, getattr(views, "run_id", ""), detail)
    return _stamp_live_flags(store, detail)


def _ordering_brief(ordering):
    """Hero and order-check totals. Line lists stay on the ordering and sales tabs."""
    ordering = ordering or {}
    overall = ordering.get("overall") or {}

    def period(row):
        if not isinstance(row, dict):
            return None
        return {
            "key": row.get("key") or "",
            "label": row.get("label") or "",
            "flagged_count": row.get("flagged_count") or 0,
            "flagged_value": row.get("flagged_value") or 0,
        }

    return {
        "badge": ordering.get("badge") or {},
        "default_month": ordering.get("default_month") or "",
        "due_days": ordering.get("due_days"),
        "due_days_source": ordering.get("due_days_source") or "",
        "overall": {
            "sales_count": overall.get("sales_count") or 0,
            "sales_value": overall.get("sales_value") or 0,
        },
        "months": [row for row in (period(item) for item in (ordering.get("months") or [])) if row],
        "by_fy": [row for row in (period(item) for item in (ordering.get("by_fy") or [])) if row],
    }


def _avg_gap_days(buying):
    periods = (buying or {}).get("periods") or {}
    for key in ("this_year", "all", "last_year"):
        items = (periods.get(key) or {}).get("items") or []
        gaps = []
        for item in items:
            try:
                gap = float((item or {}).get("avg_gap_days") or 0)
            except (TypeError, ValueError):
                gap = 0
            if gap > 0:
                gaps.append(gap)
        if gaps:
            return int(round(sum(gaps) / len(gaps)))
    return 0


def customer_profile(detail):
    """Header, due list, and the small figures other tabs need to know they exist."""
    if not detail:
        return detail
    buying = detail.get("buying") if isinstance(detail.get("buying"), dict) else {}
    if detail.get("tabs_separate") and "ordering" not in detail and "periods" not in buying:
        return detail
    out = dict(detail)
    ordering = out.pop("ordering", None) or {}
    buying = out.pop("buying", None) or {}
    out.pop("settlements", None)
    out.pop("activity", None)
    out.pop("ar_mismatch", None)
    out.pop("sales_gaps", None)
    out["ordering_brief"] = _ordering_brief(ordering)
    out["buying"] = {"last_order": buying.get("last_order") or []}
    out["avg_gap_days"] = _avg_gap_days(buying)
    out["sections"] = {
        "settlements": True,
        "sales": True,
        "ordering": True,
        "buying": True,
        "activity": True,
        "ar-mismatch": True,
    }
    return out


def split_customer_doc(detail):
    """Header stays on the customer document. Each tab is its own document."""
    if not isinstance(detail, dict):
        return detail, None
    buying = detail.get("buying") if isinstance(detail.get("buying"), dict) else {}
    heavy = any(key in detail for key in ("ordering", "settlements", "activity", "ar_mismatch")) or "periods" in buying
    if detail.get("tabs_separate") and not heavy:
        return detail, None
    profile = customer_profile(detail)
    profile["tabs_separate"] = True
    ordering = detail.get("ordering") if isinstance(detail.get("ordering"), dict) else {}
    ordering_body = dict(ordering)
    ordering_body.pop("sales_gaps", None)
    tabs = {
        "settlements": {"settlements": detail.get("settlements") or {}},
        "sales": {"sales_gaps": ordering.get("sales_gaps") or detail.get("sales_gaps") or {}},
        "ordering": {"ordering": ordering_body},
        "buying": {"buying": detail.get("buying") or {}},
        "activity": {
            "activity": detail.get("activity") or [],
            "activity_kinds": detail.get("activity_kinds") or [],
        },
        "ar-mismatch": {"ar_mismatch": detail.get("ar_mismatch") or {}},
    }
    return profile, tabs


def _attach_customer_tabs(store, run_id, detail):
    """Put saved tabs back for a full customer read (PDF and the default API)."""
    if not detail or not detail.get("tabs_separate"):
        return detail
    from server.view_parts import _load_body, _part_key
    key = _part_key(detail.get("uk") or "")
    if not key:
        return detail

    def tab(section):
        loaded = _load_body(store.get_view_part(str(run_id), "customer_tab", key + ":" + section))
        return loaded if isinstance(loaded, dict) else {}

    out = dict(detail)
    settlements = tab("settlements")
    if "settlements" in settlements:
        out["settlements"] = settlements.get("settlements") or {}
    ordering_tab = tab("ordering")
    ordering = dict(ordering_tab.get("ordering") or {}) if "ordering" in ordering_tab else None
    sales = tab("sales")
    if ordering is not None:
        if "sales_gaps" in sales and "sales_gaps" not in ordering:
            ordering["sales_gaps"] = sales.get("sales_gaps") or {}
        out["ordering"] = ordering
    elif "sales_gaps" in sales:
        out["sales_gaps"] = sales.get("sales_gaps") or {}
    buying_tab = tab("buying")
    if "buying" in buying_tab and isinstance(buying_tab.get("buying"), dict):
        out["buying"] = buying_tab["buying"]
    activity = tab("activity")
    if "activity" in activity:
        out["activity"] = activity.get("activity") or []
    if activity.get("activity_kinds"):
        out["activity_kinds"] = activity.get("activity_kinds")
    mismatch = tab("ar-mismatch")
    if "ar_mismatch" in mismatch:
        out["ar_mismatch"] = mismatch.get("ar_mismatch") or {}
    return out


def customer_slice(store, views, uk, section=""):
    """Header or one tab. Does not parse the other tabs."""
    from server.view_parts import _load_body, _part_key, persist_customer_tabs
    run_id = str(getattr(views, "run_id", "") or "")
    key = _part_key(uk)
    if section and run_id and key:
        loaded = _load_body(store.get_view_part(run_id, "customer_tab", key + ":" + section))
        if isinstance(loaded, dict):
            return loaded
    detail = _saved_detail(views, "customers", uk)
    if not detail:
        return None
    profile, tabs = split_customer_doc(detail)
    if tabs is not None and run_id:
        persist_customer_tabs(store, run_id, detail.get("uk") or uk, profile, tabs)
    if section:
        return (tabs or {}).get(section) or {}
    return _stamp_live_flags(store, profile)


def customer_section(detail, section):
    """One tab from the saved customer profile."""
    if not detail:
        return {}
    ordering = detail.get("ordering") or {}
    if section == "settlements":
        return {"settlements": detail.get("settlements") or {}}
    if section == "sales":
        return {"sales_gaps": ordering.get("sales_gaps") or detail.get("sales_gaps") or {}}
    if section == "ordering":
        body = dict(ordering)
        body.pop("sales_gaps", None)
        return {"ordering": body}
    if section == "buying":
        return {"buying": detail.get("buying") or {}}
    if section == "activity":
        return {
            "activity": detail.get("activity") or [],
            "activity_kinds": detail.get("activity_kinds") or [],
        }
    if section == "ar-mismatch":
        return {"ar_mismatch": detail.get("ar_mismatch") or {}}
    return {}


_CUSTOMER_LIST_FIELDS = (
    "uk", "name", "group", "salesperson", "status", "status_label",
    "last_sale", "last_sale_label", "due", "credit",
    "balance_diff", "balance_issue", "ordered_overdue", "premium", "blacklisted",
    "d0_15", "d15_30", "d30_45", "d45_60", "d60_90", "d90",
)


_ITEM_LIST_FIELDS = (
    "uk", "name", "in_stock",
    "category", "category_uk", "item_group", "item_group_uk",
    "brand", "brand_uk", "supplier", "supplier_uk",
    "qty", "pace_30", "pace_90", "days_cover", "buy_qty", "min_hold",
    "stock_position", "stock_position_label",
    "status", "status_label",
    "last_sale", "last_sale_label", "value",
)


def slim_item_list(payload):
    """Columns the stock table shows. Counts and filters stay on the payload."""
    out = dict(payload or {})
    out["items"] = [
        {key: (row or {}).get(key) for key in _ITEM_LIST_FIELDS}
        for row in (out.get("items") or [])
    ]
    return out


def slim_customer_list(payload):
    """Columns the directory table shows. The saved directory stays complete."""
    out = dict(payload or {})
    out.pop("attention", None)
    out["customers"] = [
        {key: (row or {}).get(key) for key in _CUSTOMER_LIST_FIELDS}
        for row in (out.get("customers") or [])
    ]
    return out


def snapshot_list_groups(store, params, views):
    if views is None:
        return list_groups(store, params)
    from server.groups360 import page_limit, sort_rows
    from server.customers import _eq, _status_id
    q = clean_text(params.get("q") or "").lower()
    rep = clean_text(params.get("rep"))
    status_want = _status_id(params.get("status"))
    page, limit = page_limit(params)
    rows = list(views.get("groups") or [])
    filtered = []
    for row in rows:
        if q and q not in (row.get("name") or "").lower() and not any(q in r.lower() for r in (row.get("reps") or [])):
            continue
        if rep and not any(_eq(r, rep) for r in (row.get("reps") or [])):
            continue
        if status_want and row.get("status") != status_want:
            continue
        filtered.append(row)
    sort_rows(filtered, params, "due", {"due", "customers", "rep_count", *BUCKET_KEYS})
    start = (page - 1) * limit
    return {
        "total": len(filtered),
        "page": page,
        "limit": limit,
        "groups": filtered[start:start + limit],
        "options": views.get("group_options") or {},
        "sort": clean_text(params.get("sort") or "due"),
        "dir": clean_text(params.get("dir") or "desc") or "desc",
        "from_snapshot": True,
    }


def _stamp_entity(store, entity, detail):
    """Due days and order-check policy. The saved profile is not copied in full."""
    if not detail:
        return detail
    out = dict(detail)
    if "repurchase" in out:
        out.pop("repurchase", None)
        out["repurchase_separate"] = True
    from server.due_days import resolve_entity_due_days
    from server.order_check import policy_meta_for_entity
    name = clean_text(out.get("name") or out.get("uk") or "")
    due_meta = resolve_entity_due_days(store, entity, name)
    out["due_days"] = due_meta["due_days"]
    out["due_days_source"] = due_meta["source"]
    out["due_days_own"] = due_meta.get("own")
    out.update(policy_meta_for_entity(store, entity, out))
    return out


def snapshot_get_group(store, uk, views):
    if views is None:
        return _overlay_group(store, get_group(store, uk))
    detail = _saved_detail(views, "group_details", uk)
    if not detail:
        return None
    if detail.get("tabs_separate"):
        detail = _attach_group_tabs(store, getattr(views, "run_id", ""), detail)
    return _stamp_entity(store, "group", detail)


def group_profile(detail):
    """Header and the small figures. Customer rows and the heavy tabs load on their own."""
    if not detail:
        return detail
    if detail.get("tabs_separate") and "ordering" not in detail and "customers" not in detail and "settlements" not in detail:
        return detail
    out = dict(detail)
    ordering = out.pop("ordering", None) or {}
    out.pop("settlements", None)
    out.pop("buying", None)
    out.pop("customers", None)
    out.pop("open_invoices", None)
    out.pop("sales_gaps", None)
    out["ordering_brief"] = _ordering_brief(ordering)
    out["sections"] = {
        "customers": True,
        "due": True,
        "settlements": True,
        "sales": True,
        "ordering": True,
        "buying": True,
    }
    return out


def split_group_doc(detail):
    if not isinstance(detail, dict):
        return detail, None
    heavy = any(key in detail for key in ("ordering", "settlements", "buying", "customers", "open_invoices"))
    if detail.get("tabs_separate") and not heavy:
        return detail, None
    profile = group_profile(detail)
    profile["tabs_separate"] = True
    ordering = detail.get("ordering") if isinstance(detail.get("ordering"), dict) else {}
    ordering_body = dict(ordering)
    ordering_body.pop("sales_gaps", None)
    tabs = {
        "customers": {"customers": detail.get("customers") or []},
        "due": {"open_invoices": detail.get("open_invoices") or []},
        "settlements": {"settlements": detail.get("settlements") or {}},
        "sales": {"sales_gaps": ordering.get("sales_gaps") or detail.get("sales_gaps") or {}},
        "ordering": {"ordering": ordering_body},
        "buying": {"buying": detail.get("buying") or {}},
    }
    return profile, tabs


def _attach_group_tabs(store, run_id, detail):
    if not detail or not detail.get("tabs_separate"):
        return detail
    from server.view_parts import _load_body, _part_key
    key = _part_key(detail.get("uk") or "")
    if not key:
        return detail

    def tab(section):
        loaded = _load_body(store.get_view_part(str(run_id), "group_tab", key + ":" + section))
        return loaded if isinstance(loaded, dict) else {}

    out = dict(detail)
    customers = tab("customers")
    if "customers" in customers:
        out["customers"] = customers.get("customers") or []
    due = tab("due")
    if "open_invoices" in due:
        out["open_invoices"] = due.get("open_invoices") or []
    settlements = tab("settlements")
    if "settlements" in settlements:
        out["settlements"] = settlements.get("settlements") or {}
    ordering_tab = tab("ordering")
    ordering = dict(ordering_tab.get("ordering") or {}) if "ordering" in ordering_tab else None
    sales = tab("sales")
    if ordering is not None:
        if "sales_gaps" in sales and "sales_gaps" not in ordering:
            ordering["sales_gaps"] = sales.get("sales_gaps") or {}
        out["ordering"] = ordering
    elif "sales_gaps" in sales:
        out["sales_gaps"] = sales.get("sales_gaps") or {}
    buying_tab = tab("buying")
    if "buying" in buying_tab and isinstance(buying_tab.get("buying"), dict):
        out["buying"] = buying_tab["buying"]
    return out


def group_slice(store, views, uk, section=""):
    """Header or one tab. Does not parse the other tabs."""
    from server.view_parts import _load_body, _part_key, persist_group_tabs
    run_id = str(getattr(views, "run_id", "") or "")
    key = _part_key(uk)
    if section and run_id and key:
        loaded = _load_body(store.get_view_part(run_id, "group_tab", key + ":" + section))
        if isinstance(loaded, dict):
            return loaded
    detail = _saved_detail(views, "group_details", uk)
    if not detail:
        return None
    profile, tabs = split_group_doc(detail)
    if tabs is not None and run_id:
        persist_group_tabs(store, run_id, detail.get("uk") or uk, profile, tabs)
    if section:
        return (tabs or {}).get(section) or {}
    return _stamp_entity(store, "group", profile)


def snapshot_list_reps(store, params, views):
    if views is None:
        return list_reps(store, params)
    from server.groups360 import page_limit, sort_rows
    from server.customers import _eq, _status_id
    q = clean_text(params.get("q") or "").lower()
    group = clean_text(params.get("group"))
    status_want = _status_id(params.get("status"))
    page, limit = page_limit(params)
    rows = list(views.get("reps") or [])
    filtered = []
    for row in rows:
        if q and q not in (row.get("name") or "").lower() and not any(q in g.lower() for g in (row.get("groups") or [])):
            continue
        if group and not any(_eq(g, group) for g in (row.get("groups") or [])):
            continue
        if status_want and row.get("status") != status_want:
            continue
        filtered.append(row)
    sort_rows(filtered, params, "ytd_sales", {"due", "customers", "ytd_sales", "ytd_collection", "group_count", *BUCKET_KEYS})
    start = (page - 1) * limit
    return {
        "total": len(filtered),
        "page": page,
        "limit": limit,
        "reps": filtered[start:start + limit],
        "options": views.get("rep_options") or {},
        "sort": clean_text(params.get("sort") or "ytd_sales"),
        "dir": clean_text(params.get("dir") or "desc") or "desc",
        "from_snapshot": True,
    }


def snapshot_get_rep(store, uk, views):
    if views is None:
        return _overlay_rep(store, get_rep(store, uk))
    detail = _saved_detail(views, "rep_details", uk)
    if not detail:
        return None
    if detail.get("tabs_separate"):
        detail = _attach_rep_tabs(store, getattr(views, "run_id", ""), detail)
    return _stamp_entity(store, "rep", detail)


def rep_profile(detail):
    """Header and the small figures. Customer rows and the heavy tabs load on their own."""
    if not detail:
        return detail
    if detail.get("tabs_separate") and "ordering" not in detail and "customers" not in detail and "settlements" not in detail and "activity" not in detail:
        return detail
    out = dict(detail)
    ordering = out.pop("ordering", None) or {}
    out.pop("settlements", None)
    out.pop("buying", None)
    out.pop("customers", None)
    out.pop("open_invoices", None)
    out.pop("sales_gaps", None)
    out.pop("activity", None)
    out["ordering_brief"] = _ordering_brief(ordering)
    out["sections"] = {
        "customers": True,
        "due": True,
        "settlements": True,
        "sales": True,
        "ordering": True,
        "buying": True,
        "activity": True,
    }
    return out


def split_rep_doc(detail):
    if not isinstance(detail, dict):
        return detail, None
    heavy = any(key in detail for key in ("ordering", "settlements", "buying", "customers", "open_invoices", "activity"))
    if detail.get("tabs_separate") and not heavy:
        return detail, None
    profile = rep_profile(detail)
    profile["tabs_separate"] = True
    ordering = detail.get("ordering") if isinstance(detail.get("ordering"), dict) else {}
    ordering_body = dict(ordering)
    ordering_body.pop("sales_gaps", None)
    tabs = {
        "customers": {"customers": detail.get("customers") or []},
        "due": {"open_invoices": detail.get("open_invoices") or []},
        "settlements": {"settlements": detail.get("settlements") or {}},
        "sales": {"sales_gaps": ordering.get("sales_gaps") or detail.get("sales_gaps") or {}},
        "ordering": {"ordering": ordering_body},
        "buying": {"buying": detail.get("buying") or {}},
        "activity": {"activity": detail.get("activity") or []},
    }
    return profile, tabs


def _attach_rep_tabs(store, run_id, detail):
    if not detail or not detail.get("tabs_separate"):
        return detail
    from server.view_parts import _load_body, _part_key
    key = _part_key(detail.get("uk") or "")
    if not key:
        return detail

    def tab(section):
        loaded = _load_body(store.get_view_part(str(run_id), "rep_tab", key + ":" + section))
        return loaded if isinstance(loaded, dict) else {}

    out = dict(detail)
    customers = tab("customers")
    if "customers" in customers:
        out["customers"] = customers.get("customers") or []
    due = tab("due")
    if "open_invoices" in due:
        out["open_invoices"] = due.get("open_invoices") or []
    settlements = tab("settlements")
    if "settlements" in settlements:
        out["settlements"] = settlements.get("settlements") or {}
    ordering_tab = tab("ordering")
    ordering = dict(ordering_tab.get("ordering") or {}) if "ordering" in ordering_tab else None
    sales = tab("sales")
    if ordering is not None:
        if "sales_gaps" in sales and "sales_gaps" not in ordering:
            ordering["sales_gaps"] = sales.get("sales_gaps") or {}
        out["ordering"] = ordering
    elif "sales_gaps" in sales:
        out["sales_gaps"] = sales.get("sales_gaps") or {}
    buying_tab = tab("buying")
    if "buying" in buying_tab and isinstance(buying_tab.get("buying"), dict):
        out["buying"] = buying_tab["buying"]
    activity = tab("activity")
    if "activity" in activity:
        out["activity"] = activity.get("activity") or []
    return out


def rep_slice(store, views, uk, section=""):
    """Header or one tab. Does not parse the other tabs."""
    from server.view_parts import _load_body, _part_key, persist_rep_tabs
    run_id = str(getattr(views, "run_id", "") or "")
    key = _part_key(uk)
    if section and run_id and key:
        loaded = _load_body(store.get_view_part(run_id, "rep_tab", key + ":" + section))
        if isinstance(loaded, dict):
            return loaded
    detail = _saved_detail(views, "rep_details", uk)
    if not detail:
        return None
    profile, tabs = split_rep_doc(detail)
    if tabs is not None and run_id:
        persist_rep_tabs(store, run_id, detail.get("uk") or uk, profile, tabs)
    if section:
        return (tabs or {}).get(section) or {}
    return _stamp_entity(store, "rep", profile)


def _list_item_cards(views, holds, default_min, default_max_days):
    """Apply current holdings without copying each item's nested history."""
    from vay.dates import parse_date
    as_of = parse_date(views.get("as_of")) if views.get("as_of") else None
    cards = []
    for card in (views.get("items") or []):
        out = dict(card)
        if as_of is None and out.get("as_of"):
            as_of = parse_date(out.get("as_of"))
        holding = _holding_for(holds, default_min, account_uk(out.get("uk") or ""), default_max_days)
        _apply_buy_fields(out, holding, as_of=as_of)
        cards.append(out)
    return cards


def snapshot_list_items(store, params, views):
    if views is None:
        return list_items(store, params)
    from server.items360 import _page_limit
    page, limit = _page_limit(params)
    holds, default_min, default_max_days = _hold_map(store)
    cards = _list_item_cards(views, holds, default_min, default_max_days)
    options = views.get("item_options") or {
        "item": sorted({c["name"] for c in cards if c.get("name")}),
        "status": sorted({c["status_label"] for c in cards if c.get("status_label")}),
        "position": sorted({c["stock_position_label"] for c in cards if c.get("stock_position_label")}),
    }
    if "position" not in options:
        options = dict(options)
        options["position"] = sorted({c["stock_position_label"] for c in cards if c.get("stock_position_label")})
    item_f = clean_text(params.get("item"))
    status_f = clean_text(params.get("status"))
    position_f = clean_text(params.get("position"))
    in_stock_f = clean_text(params.get("in_stock")).lower()
    filtered = []
    for card in cards:
        if item_f and card.get("name") != item_f:
            continue
        if status_f and card.get("status_label") != status_f:
            continue
        if position_f and card.get("stock_position_label") != position_f:
            continue
        if in_stock_f in ("yes", "1", "true"):
            if not card.get("in_stock"):
                continue
        elif in_stock_f in ("no", "0", "false"):
            if card.get("in_stock"):
                continue
        filtered.append(card)
    sort_key = clean_text(params.get("sort") or "name")
    direction = clean_text(params.get("dir") or "asc")
    if direction not in ("asc", "desc"):
        direction = "asc"

    def sort_val(card):
        if sort_key == "qty":
            return card.get("qty") or 0
        if sort_key == "min_hold":
            return card.get("min_hold") or 0
        if sort_key == "days_cover":
            return card.get("days_cover") if card.get("days_cover") is not None else -1
        if sort_key == "value":
            return card.get("value") or 0
        if sort_key == "last_sale":
            return card.get("last_sale") or ""
        if sort_key == "status":
            return card.get("status_label") or ""
        if sort_key == "position":
            return card.get("stock_position_label") or ""
        if sort_key == "buy_qty":
            return card.get("buy_qty") or 0
        if sort_key == "pace_30":
            return card.get("pace_30") or 0
        if sort_key in ("category", "item_group", "brand", "supplier"):
            return (card.get(sort_key) or "").lower()
        return (card.get("name") or "").lower()

    numeric = sort_key in ("qty", "min_hold", "days_cover", "value", "buy_qty", "pace_30")
    filtered.sort(key=sort_val, reverse=(direction == "desc") if numeric or sort_key == "last_sale" else (direction == "desc"))
    total = len(filtered)
    start = (page - 1) * limit
    buy_cards = [c for c in cards if c.get("status") in ("low", "soon") and (c.get("buy_qty") or 0) > 0]
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": filtered[start:start + limit],
        "options": options,
        "sort": sort_key or "name",
        "dir": direction,
        "default_min": default_min if default_min is not None else (views.get("default_min") or 0),
        "default_max_days": default_max_days if default_max_days is not None else (views.get("default_max_days") or 60),
        "as_of": views.get("as_of") or "",
        "low_count": sum(1 for c in cards if c.get("status") == "low"),
        "soon_count": sum(1 for c in cards if c.get("status") == "soon"),
        "under_count": sum(1 for c in cards if c.get("stock_position") == "under"),
        "over_count": sum(1 for c in cards if c.get("stock_position") == "over"),
        "dead_count": sum(1 for c in cards if c.get("stock_position") == "dead"),
        "out_of_stock_count": views.get("out_of_stock_count")
            if views.get("out_of_stock_count") is not None
            else sum(1 for c in cards if not c.get("in_stock")),
        "buy_count": len(buy_cards),
        "buy_qty_sum": round(sum(float(c.get("buy_qty") or 0) for c in buy_cards), 2),
        "buy_value_sum": round(sum(
            float(c.get("buy_qty") or 0) * float(c.get("rate") or 0)
            for c in buy_cards
        ), 2),
        "from_snapshot": True,
    }


def _item_dim_missing(dimension, params):
    """A 360 dimension is read from the saved snapshot. Never rebuilt from source rows."""
    from server.item_dims import DIMENSIONS, _dimension_key, _page_limit
    key = _dimension_key(dimension)
    if not key:
        return None
    spec = DIMENSIONS[key]
    page, limit = _page_limit(params)
    return {
        "dimension": key,
        "label": spec["label"],
        "plural": spec["plural"],
        "hash": spec["hash"],
        "total": 0,
        "page": page,
        "limit": limit,
        "rows": [],
        "sort": "sales_value",
        "dir": "desc",
        "from_snapshot": False,
        "needs_rebuild": True,
    }


def snapshot_list_item_dims(store, dimension, params, views):
    from server.item_dims import _dimension_key, _page_limit, _sort_rows, rollup_totals
    key = _dimension_key(dimension)
    packed = (views or {}).get("item_dims") if views else None
    if views is None or packed is None or key not in packed:
        return _item_dim_missing(dimension, params)
    built = packed.get(key) or {}
    q = clean_text((params or {}).get("q") or "").lower()
    rows = []
    for slot in built.get("rows") or []:
        if q and q not in (slot.get("name") or "").lower():
            continue
        rows.append(dict(slot))
    sort, direction = _sort_rows(rows, params)
    page, limit = _page_limit(params)
    start = (page - 1) * limit
    return {
        "dimension": built.get("dimension") or key,
        "label": built.get("label") or "",
        "plural": built.get("plural") or "",
        "hash": built.get("hash") or "",
        "total": len(rows),
        "page": page,
        "limit": limit,
        "rows": rows[start:start + limit],
        "totals": rollup_totals(rows),
        "sort": sort,
        "dir": direction,
        "from_snapshot": True,
    }


def snapshot_get_item_dim(store, dimension, uk, views, params=None):
    from server.item_attrs import NONE_UK
    from server.item_dims import (
        _dimension_key,
        _page_limit,
        filter_members,
        members_for_slot,
    )
    key = _dimension_key(dimension)
    packed = (views or {}).get("item_dims") if views else None
    if views is None or packed is None or key not in packed:
        return None
    built = packed.get(key) or {}
    details = built.get("details") or {}
    raw = clean_text(uk)
    slot = None
    if raw == NONE_UK or account_uk(raw) == NONE_UK:
        slot = details.get(NONE_UK)
    else:
        slot = details.get(raw) or details.get(account_uk(raw).lower())
        if slot is None and not getattr(details, "prefix", None):
            want = account_uk(raw).lower()
            for row in details.values():
                if row.get("none"):
                    continue
                if (row.get("uk") or "").lower() == want or account_uk(row.get("name")).lower() == want:
                    slot = row
                    break
    if not slot:
        return None
    params = params or {}
    detail = dict(slot)
    stored_members = detail.pop("members", None)
    detail["dimension"] = built.get("dimension") or key
    detail["dimension_label"] = built.get("label") or ""
    detail["hash"] = built.get("hash") or ""
    want_members = clean_text(params.get("members")).lower() in ("1", "true", "yes")
    if not want_members:
        detail["members"] = []
        detail["member_total"] = int(detail.get("items") or 0)
        return detail
    if not stored_members:
        stored_members = members_for_slot((views or {}).get("items") or [], key, detail.get("uk"))
    filtered = filter_members(stored_members, params.get("focus"))
    page, limit = _page_limit(params)
    start = (page - 1) * limit
    detail["members"] = filtered[start:start + limit]
    detail["member_total"] = len(filtered)
    detail["member_page"] = page
    return detail


def split_item_doc(detail):
    """Header, velocity, and holding stay on the item. Buyers and movement are separate."""
    if not isinstance(detail, dict):
        return detail, None
    heavy = any(key in detail for key in ("buyers", "movement", "groups", "reps"))
    if detail.get("tabs_separate") and not heavy:
        return detail, None
    profile = dict(detail)
    buyers = profile.pop("buyers", None)
    movement = profile.pop("movement", None)
    groups = profile.pop("groups", None)
    reps = profile.pop("reps", None)
    profile["tabs_separate"] = True
    profile["buyer_count"] = len(buyers or [])
    profile["sections"] = {"buyers": True, "movement": True}
    tabs = {
        "buyers": {"buyers": buyers or []},
        "movement": {
            "movement": movement or [],
            "groups": groups or [],
            "reps": reps or [],
        },
    }
    return profile, tabs


def _attach_item_tabs(store, run_id, detail):
    if not detail or not detail.get("tabs_separate"):
        return detail
    from server.view_parts import _load_body, _part_key
    key = _part_key(detail.get("uk") or "")
    if not key:
        return detail

    def tab(section):
        loaded = _load_body(store.get_view_part(str(run_id), "item_tab", key + ":" + section))
        return loaded if isinstance(loaded, dict) else {}

    out = dict(detail)
    buyers = tab("buyers")
    if "buyers" in buyers:
        out["buyers"] = buyers.get("buyers") or []
    movement = tab("movement")
    if "movement" in movement:
        out["movement"] = movement.get("movement") or []
    if "groups" in movement:
        out["groups"] = movement.get("groups") or []
    if "reps" in movement:
        out["reps"] = movement.get("reps") or []
    return out


def item_slice(store, views, uk, section=""):
    """Header, or buyers, or movement. Does not parse the other tab."""
    from server.view_parts import _load_body, _part_key, persist_item_tabs
    run_id = str(getattr(views, "run_id", "") or "")
    key = _part_key(uk)
    if section and run_id and key:
        loaded = _load_body(store.get_view_part(run_id, "item_tab", key + ":" + section))
        if isinstance(loaded, dict):
            return loaded
    detail = _saved_detail(views, "item_details", uk)
    if not detail:
        return None
    if "repurchase" in detail:
        detail = dict(detail)
        detail.pop("repurchase", None)
        detail["repurchase_separate"] = True
    profile, tabs = split_item_doc(detail)
    if tabs is not None and run_id:
        persist_item_tabs(store, run_id, detail.get("uk") or uk, profile, tabs)
    if section:
        return (tabs or {}).get(section) or {}
    return _overlay_item(store, profile)


def snapshot_get_item(store, uk, views):
    if views is None:
        return get_item(store, uk)
    detail = _saved_detail(views, "item_details", uk)
    if not detail:
        return None
    if detail.get("tabs_separate"):
        detail = _attach_item_tabs(store, getattr(views, "run_id", ""), detail)
    out = dict(detail)
    if "repurchase" in out:
        out.pop("repurchase", None)
        out["repurchase_separate"] = True
    return _overlay_item(store, out)
