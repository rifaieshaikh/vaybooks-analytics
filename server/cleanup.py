"""Remove imported operational rows. Selective cleanup keeps stock items and zeroes quantities. Factory reset returns the organization to a fresh install, keeping users and roles."""

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


def cleanup_snapshots(store):
    """Drop saved report runs and the 360 snapshot documents stored with them.

    Imported rows, uploads, column maps, and settings stay.
    """
    snapshots_deleted = store.count_view_parts()
    runs_deleted = delete_all_runs(store)
    store.delete_all_view_parts()
    return {
        "runs_deleted": runs_deleted,
        "snapshots_deleted": snapshots_deleted,
    }


def factory_reset(store):
    """Drop stored business data so the organization matches a first-time install."""
    removed = {}
    total = 0
    for row in list(store.list_rows() or []):
        label = TYPE_LABELS.get(row.get("type"), row.get("type") or "other")
        removed[label] = removed.get(label, 0) + 1
        total += 1
    runs_deleted = delete_all_runs(store)
    uploads_deleted = 0
    for upload in list(store.list_uploads() or []):
        uid = upload.get("_id")
        if uid is None:
            continue
        if store.delete_upload(str(uid)):
            uploads_deleted += 1
    store.delete_all_rows()
    mappers_deleted = store.delete_all_mappers()
    jobs_deleted = store.delete_all_import_jobs()
    sidecars_deleted = store.delete_all_recon_sidecars()
    audit_deleted = store.delete_all_audit()
    store.delete_all_view_parts()
    files_deleted = store.delete_all_blobs()
    sessions_deleted = store.delete_org_sessions()
    invalidate_views_cache()
    return {
        "removed": removed,
        "total": total,
        "balances_cleared": 0,
        "stock_reset": 0,
        "types": [],
        "runs_deleted": runs_deleted,
        "uploads_deleted": uploads_deleted,
        "mappers_deleted": mappers_deleted,
        "import_jobs_deleted": jobs_deleted,
        "sidecars_deleted": sidecars_deleted,
        "audit_deleted": audit_deleted,
        "files_deleted": files_deleted,
        "sessions_deleted": sessions_deleted,
    }
