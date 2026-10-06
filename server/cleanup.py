"""Remove imported operational rows. Stock items stay; quantities reset. Factory also clears report runs."""

from vay.dates import number_

from server.run_views import invalidate_views_cache
from server.settings import CLEANUP_TYPES, TYPE_LABELS


def _clear_master_balances(store):
    cleared = 0
    for type_name in ("customer", "party"):
        for row in store.rows_of_type(type_name):
            fields = dict(row.get("fields") or {})
            balance = number_(fields.get("Balance"))
            days = fields.get("Days")
            days_n = number_(days) if days not in ("", None) else 0
            if balance == 0 and days_n == 0:
                continue
            fields["Balance"] = 0.0
            if days not in ("", None):
                fields["Days"] = 0
            store.upsert_row({
                "type": type_name,
                "uk": row.get("uk"),
                "source_upload_id": row.get("source_upload_id") or "",
                "fields": fields,
            })
            cleared += 1
    return cleared


def _reset_stock_qty(store):
    """Keep stock item rows; set Qty to 0 so the catalogue stays in place."""
    reset = 0
    for row in store.rows_of_type("stock"):
        fields = dict(row.get("fields") or {})
        qty = number_(fields.get("Qty"))
        if qty == 0:
            continue
        fields["Qty"] = 0.0
        store.upsert_row({
            "type": "stock",
            "uk": row.get("uk"),
            "source_upload_id": row.get("source_upload_id") or "",
            "fields": fields,
        })
        reset += 1
    return reset


def _normalize_types(types):
    if not types:
        return list(CLEANUP_TYPES)
    allowed = set(CLEANUP_TYPES)
    out = []
    for name in types:
        key = str(name or "").strip().lower()
        if key in allowed and key not in out:
            out.append(key)
    return out or list(CLEANUP_TYPES)


def cleanup_imported_data(store, types=None):
    selected = _normalize_types(types)
    removed = {}
    total = 0
    stock_reset = 0
    for type_name in selected:
        if type_name == "stock":
            stock_reset = _reset_stock_qty(store)
            removed[TYPE_LABELS.get(type_name, type_name)] = stock_reset
            total += stock_reset
            continue
        count = store.delete_rows_of_type(type_name)
        removed[TYPE_LABELS.get(type_name, type_name)] = count
        total += count
    balances_cleared = 0
    if "arr" in selected:
        balances_cleared = _clear_master_balances(store)
    return {
        "removed": removed,
        "total": total,
        "balances_cleared": balances_cleared,
        "stock_reset": stock_reset,
        "types": selected,
    }


def delete_all_runs(store):
    deleted = 0
    for run in list(store.list_runs() or []):
        rid = run.get("_id") or run.get("id")
        if rid is None:
            continue
        store.delete_run(str(rid))
        deleted += 1
    invalidate_views_cache()
    return deleted


def factory_reset(store):
    out = cleanup_imported_data(store, list(CLEANUP_TYPES))
    out["runs_deleted"] = delete_all_runs(store)
    return out
