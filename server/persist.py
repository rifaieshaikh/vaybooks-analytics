"""Persist prepared ingest rows. Events: skip|update|replace_batch|replace_period; snapshots upsert."""

from pymongo.errors import DuplicateKeyError

from server.ingest import SKIP_REASON_LABELS, compact_fields, prepare_rows
from server.provenance import (
    infer_max_event_date,
    mapper_version,
    normalize_event_mode,
    parse_effective_date,
)
from server.settings import EVENT_TYPES, SNAPSHOT_TYPES
from server.store import DuplicateUk
from vay.dates import parse_date

PREVIEW_ROW_CAP = 500
REASON_ALREADY_EXISTS = "already_exists"
REASON_WOULD_REPLACE_BATCH = "would_replace_batch"
REASON_WOULD_REPLACE_PERIOD = "would_replace_period"


def _date_bounds(prepared):
    dates = []
    for fields, _uk in prepared:
        d = parse_date((fields or {}).get("Date"))
        if d:
            dates.append(d)
    if not dates:
        return None, None
    return min(dates), max(dates)


def _preview_item(fields, uk, reason=None):
    item = {"uk": uk or "", "fields": compact_fields(fields)}
    if reason:
        item["reason"] = reason
        item["reason_label"] = SKIP_REASON_LABELS.get(reason, reason)
    return item


def _cap_bucket(rows, cap=PREVIEW_ROW_CAP):
    truncated = len(rows) > cap
    return rows[:cap], truncated


def _empty_preview():
    return {
        "added": [],
        "updated": [],
        "upserted": [],
        "skipped": [],
        "would_delete": [],
    }


def _iter_rows_in_date_range(store, type_name, start, end, limit=None):
    """Yield store rows in [start, end]; stop early when limit reached."""
    n = 0
    for row in store.rows_of_type(type_name):
        raw = row.get("Date")
        if raw is None:
            raw = (row.get("fields") or {}).get("Date")
        d = parse_date(raw)
        if d is None or not (start <= d <= end):
            continue
        yield row
        n += 1
        if limit is not None and n >= limit:
            return


def preview_persist(store, type_name, prepared, event_mode="skip", rejects=None):
    """Return planned counts + capped preview_rows without writing."""
    mode = normalize_event_mode(event_mode)
    counts = {
        "added": 0,
        "updated": 0,
        "upserted": 0,
        "skipped": 0,
        "would_delete": 0,
        "dry_run": True,
        "event_mode": mode,
        "mapper_version": None,
    }
    preview = _empty_preview()
    truncated = {k: False for k in preview}

    # Ingest rejects → skipped bucket
    reject_rows = []
    for rej in rejects or []:
        item = {
            "uk": rej.get("uk") or "",
            "fields": rej.get("fields") or {},
            "reason": rej.get("reason"),
            "reason_label": SKIP_REASON_LABELS.get(rej.get("reason"), rej.get("reason") or ""),
        }
        reject_rows.append(item)

    if type_name in SNAPSHOT_TYPES:
        for fields, uk in prepared:
            if store.find_row(type_name, uk):
                counts["upserted"] += 1
                preview["upserted"].append(_preview_item(fields, uk))
            else:
                counts["added"] += 1
                preview["added"].append(_preview_item(fields, uk))
    elif mode == "replace_batch":
        uk_set = set(uk for _f, uk in prepared)
        would = []
        existing_n = 0
        for row in store.rows_of_type(type_name):
            uk = row.get("uk")
            if uk not in uk_set:
                continue
            existing_n += 1
            if len(would) < PREVIEW_ROW_CAP:
                would.append(_preview_item(row.get("fields") or {}, uk, REASON_WOULD_REPLACE_BATCH))
        counts["would_delete"] = existing_n
        counts["added"] = len(prepared)
        preview["would_delete"] = would
        truncated["would_delete"] = existing_n > PREVIEW_ROW_CAP
        for fields, uk in prepared:
            preview["added"].append(_preview_item(fields, uk))
    elif mode == "replace_period":
        start, end = _date_bounds(prepared)
        would = []
        if start and end:
            counts["would_delete"] = store.count_rows_in_date_range(type_name, start, end)
            for row in _iter_rows_in_date_range(store, type_name, start, end, limit=PREVIEW_ROW_CAP):
                would.append(_preview_item(
                    row.get("fields") or {}, row.get("uk") or "", REASON_WOULD_REPLACE_PERIOD,
                ))
            truncated["would_delete"] = counts["would_delete"] > PREVIEW_ROW_CAP
        counts["added"] = len(prepared)
        preview["would_delete"] = would
        for fields, uk in prepared:
            preview["added"].append(_preview_item(fields, uk))
    elif mode == "update":
        for fields, uk in prepared:
            if store.find_row(type_name, uk):
                counts["updated"] += 1
                preview["updated"].append(_preview_item(fields, uk))
            else:
                counts["added"] += 1
                preview["added"].append(_preview_item(fields, uk))
    else:
        # skip
        for fields, uk in prepared:
            if store.find_row(type_name, uk):
                counts["skipped"] += 1
                preview["skipped"].append(_preview_item(fields, uk, REASON_ALREADY_EXISTS))
            else:
                counts["added"] += 1
                preview["added"].append(_preview_item(fields, uk))

    # Merge rejects into skipped (rejects first so ingest reasons are visible)
    skipped_merged = reject_rows + preview["skipped"]
    preview["skipped"], trunc_skip = _cap_bucket(skipped_merged)
    truncated["skipped"] = trunc_skip or truncated.get("skipped", False)

    for key in ("added", "updated", "upserted", "would_delete"):
        preview[key], trunc = _cap_bucket(preview[key])
        truncated[key] = truncated.get(key, False) or trunc

    ingest_reject_count = (
        int(counts.get("total_skipped") or 0)
        + int(counts.get("blank_skipped") or 0)
        + int(counts.get("failed_row") or 0)
        + int(counts.get("clash") or 0)
    )
    # When called standalone, ingest counters may already be on counts from prepare_rows
    counts["skipped_total"] = ingest_reject_count + int(counts.get("skipped") or 0)
    counts["preview_rows"] = preview
    counts["preview_truncated"] = truncated
    return counts


def _stamp_prepared(store, type_name, prepared):
    """Write NO_REP and NO_GROUP onto rows before they are saved."""
    from vay.credit_notes import rep_index
    from vay.dates import clean_text, parse_date
    from vay.row_defaults import stamp_fields

    groups = {}
    known = set()
    pairs = []
    for type_name_src in ("arr", "party", "customer"):
        for row in store.rows_of_type(type_name_src):
            fields = row.get("fields") or {}
            name = clean_text(fields.get("Account Name") or fields.get("Party Name")).lower()
            group = clean_text(fields.get("Group"))
            if name:
                known.add(name)
                if group and group != "NO_GROUP" and name not in groups:
                    groups[name] = group
    for row in store.rows_of_type("sales"):
        fields = row.get("fields") or {}
        name = clean_text(fields.get("Party Name") or fields.get("Account Name"))
        if name:
            known.add(name.lower())
        pairs.append((name, parse_date(fields.get("Date")), fields.get("Sales Rep")))
    reps = rep_index(pairs)
    return [(stamp_fields(fields, type_name, groups=groups, reps=reps, known=known), uk) for fields, uk in prepared]


def persist_prepared(
    store,
    type_name,
    prepared,
    upload_id,
    counts,
    event_mode="skip",
    dry_run=False,
    effective_date=None,
    rejects=None,
):
    mode = normalize_event_mode(event_mode)
    counts.setdefault("added", 0)
    counts.setdefault("updated", 0)
    counts.setdefault("upserted", 0)
    counts.setdefault("skipped", 0)
    counts.setdefault("deleted", 0)
    counts["event_mode"] = mode
    if type_name in ("sales", "receipt", "credit_note", "arr"):
        prepared = _stamp_prepared(store, type_name, prepared)

    if dry_run:
        # Preserve ingest counters; preview_persist overwrites action counts
        ingest_bits = {
            "total_skipped": counts.get("total_skipped", 0),
            "blank_skipped": counts.get("blank_skipped", 0),
            "failed_row": counts.get("failed_row", 0),
            "clash": counts.get("clash", 0),
        }
        preview = preview_persist(store, type_name, prepared, mode, rejects=rejects or [])
        counts.update(preview)
        counts.update(ingest_bits)
        counts["skipped_total"] = (
            int(ingest_bits["total_skipped"] or 0)
            + int(ingest_bits["blank_skipped"] or 0)
            + int(ingest_bits["failed_row"] or 0)
            + int(ingest_bits["clash"] or 0)
            + int(counts.get("skipped") or 0)
        )
        return counts

    eff = parse_effective_date(effective_date) or infer_max_event_date(prepared)

    if type_name in SNAPSHOT_TYPES:
        for fields, uk in prepared:
            fields = dict(fields)
            if eff:
                fields["EffectiveDate"] = eff
            if type_name == "party":
                from server.customers import preserve_party_fields
                fields = preserve_party_fields(store, uk, fields)
            doc = {
                "type": type_name,
                "uk": uk,
                "source_upload_id": str(upload_id),
                "fields": fields,
                "effective_date": eff,
            }
            try:
                store.upsert_row(doc)
                counts["upserted"] += 1
            except DuplicateUk:
                counts["skipped"] += 1
        return counts

    if mode == "replace_batch":
        uks = [uk for _f, uk in prepared]
        counts["deleted"] = store.delete_rows_by_uks(type_name, uks)
    elif mode == "replace_period":
        start, end = _date_bounds(prepared)
        if start and end:
            counts["deleted"] = store.delete_rows_in_date_range(type_name, start, end)

    for fields, uk in prepared:
        fields = dict(fields)
        doc = {
            "type": type_name,
            "uk": uk,
            "source_upload_id": str(upload_id),
            "fields": fields,
        }
        if "Date" in fields:
            doc["Date"] = fields.get("Date")
        if mode == "update" and type_name in EVENT_TYPES:
            existing = store.find_row(type_name, uk)
            try:
                store.upsert_row(doc)
                if existing:
                    counts["updated"] = counts.get("updated", 0) + 1
                else:
                    counts["added"] += 1
            except DuplicateUk:
                counts["skipped"] += 1
            except DuplicateKeyError:
                counts["skipped"] += 1
        else:
            # skip, replace_batch, replace_period → insert
            try:
                store.insert_row(doc)
                counts["added"] += 1
            except DuplicateUk:
                counts["skipped"] += 1
            except DuplicateKeyError:
                counts["skipped"] += 1
    return counts


def persist_type(
    store,
    type_name,
    headers,
    value_rows,
    mapper,
    upload_id,
    event_mode="skip",
    dry_run=False,
    effective_date=None,
):
    from server.account_aliases import alias_lookup

    prepared, counts, rejects = prepare_rows(
        type_name, headers, value_rows, mapper, aliases=alias_lookup(store),
    )
    counts["mapper_version"] = mapper_version(mapper)
    if not dry_run:
        from server.entities import stamp_prepared_entities

        prepared = stamp_prepared_entities(store, type_name, prepared)
    persist_prepared(
        store,
        type_name,
        prepared,
        upload_id,
        counts,
        event_mode=event_mode,
        dry_run=dry_run,
        effective_date=effective_date,
        rejects=rejects if dry_run else None,
    )
    if dry_run:
        return counts
    if type_name == "arr" and prepared:
        from server.customers import sync_from_arr
        extra = sync_from_arr(store, prepared, upload_id)
        counts.update(extra)
    if type_name in ("sales", "items") and prepared:
        from server.customers import sync_from_sales
        extra = sync_from_sales(store, prepared, upload_id)
        counts["customers_created"] = counts.get("customers_created", 0) + extra.get("customers_created", 0)
        counts["parties_created"] = counts.get("parties_created", 0) + extra.get("parties_created", 0)
    if type_name == "payments" and prepared:
        from server.customers import sync_from_payments
        extra = sync_from_payments(store, prepared, upload_id)
        counts["parties_created"] = counts.get("parties_created", 0) + extra.get("parties_created", 0)
    if type_name in ("stock", "items") and prepared:
        from server.item_attrs import sync_item_attrs
        counts.update(sync_item_attrs(
            store, type_name, prepared, mapper.get("column_map") or {}, headers, upload_id,
        ))
    return counts
