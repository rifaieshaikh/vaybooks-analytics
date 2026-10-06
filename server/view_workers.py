"""Size and run 360 customer settlement across processes.

One worker stays in-process. More workers each receive only their own parties.
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed

from vay.dates import clean_text
from vay.settlement import empty_buckets

_SHARED_TYPES = ("activity_kind", "activity_assignee", "app_setting", "due_days", "order_check")
_CUSTOMER_CUTOFF = 40
_RAM_RESERVE = int(1.5 * 1024 * 1024 * 1024)
_RAM_PER_WORKER = 400 * 1024 * 1024


def choose_workers(customer_count=0):
    """How many processes this Create should use on this machine."""
    count = max(0, int(customer_count or 0))
    forced = os.environ.get("VAY_360_WORKERS", "").strip()
    if forced:
        try:
            n = int(forced)
        except ValueError:
            n = 1
        n = max(1, n)
        if count:
            n = min(n, count)
        return n
    if os.environ.get("VAY_STORE") == "memory":
        return 1
    if count < _CUSTOMER_CUTOFF:
        return 1
    return worker_budget(count, _logical_cpus(), _available_ram_bytes())


def worker_budget(customer_count, logical, available_bytes):
    """Smallest of the CPU cap, the free-memory cap, and the customer count."""
    logical = max(1, int(logical or 1))
    by_cpu = max(1, min(max(1, logical - 1), max(1, logical // 2)))
    if available_bytes is None:
        by_ram = by_cpu
    elif int(available_bytes) < _RAM_RESERVE:
        by_ram = 1
    else:
        by_ram = max(1, int((int(available_bytes) - _RAM_RESERVE) // _RAM_PER_WORKER))
    chosen = min(by_cpu, by_ram)
    count = max(0, int(customer_count or 0))
    if count:
        chosen = min(chosen, count)
    return max(1, int(chosen))


def _logical_cpus():
    logical = os.cpu_count() or 1
    limited = _cgroup_cpus()
    if limited:
        logical = min(logical, limited)
    return max(1, int(logical))


def _cgroup_cpus():
    text = _read_text("/sys/fs/cgroup/cpu.max")
    if text:
        parts = text.split()
        if parts and parts[0] != "max":
            try:
                quota = int(parts[0])
                period = int(parts[1]) if len(parts) > 1 else 100000
            except ValueError:
                quota = 0
                period = 0
            if quota > 0 and period > 0:
                return max(1, int(quota / period))
    quota = _read_text("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
    period = _read_text("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
    if quota and period and quota.strip() != "-1":
        try:
            q = int(quota.strip())
            p = int(period.strip())
        except ValueError:
            return None
        if q > 0 and p > 0:
            return max(1, int(q / p))
    return None


def _available_ram_bytes():
    available = _host_available_ram()
    limit = _cgroup_memory_limit()
    if limit and available:
        return min(available, limit)
    if limit:
        return limit
    return available


def _cgroup_memory_limit():
    for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        text = _read_text(path)
        if not text or text == "max":
            continue
        try:
            value = int(text)
        except ValueError:
            continue
        if value > 0 and value < 1 << 60:
            return value
    return None


def _host_available_ram():
    if os.name == "nt":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return int(stat.ullAvailPhys)
        return 0
    text = _read_text("/proc/meminfo")
    if not text:
        return 0
    for line in text.splitlines():
        if line.startswith("MemAvailable:"):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    return int(parts[1]) * 1024
                except ValueError:
                    return 0
    return 0


def _read_text(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


class _BatchStore:
    """Settings and one customer slice. Built inside the worker."""

    def __init__(self, rows_by_type, find_index):
        self._rows = {key: list(value or []) for key, value in (rows_by_type or {}).items()}
        self._find = dict(find_index or {})
        self._360_book = None
        self._force_as_of = None
        self._ar_ledgers = None
        self._ar_tolerance = None

    def rows_of_type(self, type_name):
        return list(self._rows.get(type_name) or [])

    def find_row(self, type_name, uk):
        uk = uk or ""
        return self._find.get((type_name, uk)) or self._find.get((type_name, uk.lower()))

    def upsert_row(self, doc):
        doc = dict(doc or {})
        type_name = doc.get("type") or ""
        uk = doc.get("uk") or ""
        self._rows.setdefault(type_name, []).append(doc)
        if uk:
            self._find[(type_name, uk)] = doc
            self._find[(type_name, uk.lower())] = doc
        return doc

    def list_runs(self):
        return []

    def get(self, key, default=None):
        return default


def _index_rows(rows):
    found = {}
    for row in rows or []:
        uk = row.get("uk") or ""
        if not uk:
            continue
        type_name = row.get("type") or ""
        found[(type_name, uk)] = row
        found[(type_name, uk.lower())] = row
    return found


def _shared_rows(store):
    rows = {}
    for type_name in _SHARED_TYPES:
        rows[type_name] = list(store.rows_of_type(type_name) or [])
    return rows


def _doc_for(book, row):
    uk = (row.get("uk") or "").lower()
    name = clean_text(row.get("name")).lower()
    for doc in book.get("customers") or []:
        if (doc.get("uk") or "").lower() == uk and uk:
            return doc
        fields = doc.get("fields") or {}
        if clean_text(fields.get("Account Name")).lower() == name and name:
            return doc
    return {
        "type": "customer",
        "uk": row.get("uk") or "",
        "fields": {
            "Account Name": row.get("name") or "",
            "Group": row.get("group") or "",
            "Balance": row.get("due") or 0,
        },
    }


def _rep_stub(book, key):
    out = {}
    for rep_key, rows in (book.get(key) or {}).items():
        if not rows:
            continue
        fields = (rows[0].get("fields") or {})
        name = clean_text(fields.get("Sales Rep")) or rep_key
        out[rep_key] = [{"fields": {"Sales Rep": name}}]
    return out


def _party_book(book, docs, names):
    def take(mapping):
        return {name: list((mapping or {}).get(name) or []) for name in names}

    arr_due = {}
    arr_by_uk = {}
    for name in names:
        if name in (book.get("arr_due") or {}):
            arr_due[name] = book["arr_due"][name]
    for doc in docs:
        uk = (doc.get("uk") or "").lower()
        hit = (book.get("arr_by_uk") or {}).get(uk)
        if hit is not None:
            arr_by_uk[uk] = hit
        name = clean_text((doc.get("fields") or {}).get("Account Name")).lower()
        hit = (book.get("arr_by_uk") or {}).get(name)
        if hit is not None:
            arr_by_uk[name] = hit
    return {
        "as_of": book.get("as_of"),
        "fy_start": book.get("fy_start"),
        "fiscal_year_start_month": book.get("fiscal_year_start_month"),
        "sales_by_party": take(book.get("sales_by_party")),
        "receipts_by_party": take(book.get("receipts_by_party")),
        "credit_notes_by_party": take(book.get("credit_notes_by_party")),
        "buying_lines_by_party": take(book.get("buying_lines_by_party")),
        "notes_by_party": take(book.get("notes_by_party")),
        "arr_due": arr_due,
        "arr_by_uk": arr_by_uk,
        "customers": docs,
        "sales_by_rep": _rep_stub(book, "sales_by_rep"),
        "receipts_by_rep": _rep_stub(book, "receipts_by_rep"),
        "stock_qty": dict(book.get("stock_qty") or {}),
    }


def _batch_payload(shared, book, directory_rows, ledgers, tolerance):
    from server.customers import account_uk

    docs = []
    names = []
    uks = []
    for row in directory_rows:
        doc = _doc_for(book, row)
        docs.append(doc)
        uks.append(doc.get("uk") or row.get("uk") or "")
        name = clean_text((doc.get("fields") or {}).get("Account Name") or row.get("name")).lower()
        if name:
            names.append(name)
        uk = (doc.get("uk") or "").lower()
        if uk:
            names.append(uk)
            names.append(account_uk(uk).lower())
    rows_by_type = {key: list(value) for key, value in shared.items()}
    rows_by_type["customer"] = docs
    party_ledgers = {}
    for name in names:
        if name in (ledgers or {}):
            party_ledgers[name] = ledgers[name]
    return {
        "rows_by_type": rows_by_type,
        "find_index": _index_rows([row for rows in rows_by_type.values() for row in rows]),
        "book": _party_book(book, docs, names),
        "uks": uks,
        "as_of": book.get("as_of"),
        "ledgers": party_ledgers,
        "tolerance": tolerance,
    }


def settle_customer_batch(payload):
    """Settle one slice. Top-level so Windows can spawn it."""
    store = _BatchStore(payload.get("rows_by_type"), payload.get("find_index"))
    book = payload.get("book") or {}
    store._360_book = book
    store._force_as_of = payload.get("as_of")
    store._ar_ledgers = payload.get("ledgers") or {}
    store._ar_tolerance = payload.get("tolerance")
    from server.customers import ensure_detail_settlements, summarize_customer

    out = []
    for doc in (book.get("customers") or []):
        detail = summarize_customer(store, doc)
        if detail:
            detail = ensure_detail_settlements(store, detail, book=book, force=False)
        uk = (detail or {}).get("uk") or doc.get("uk") or ""
        out.append((uk, detail))
    return out


def _chunks(rows, slots):
    slots = max(1, int(slots or 1))
    if not rows:
        return []
    size = max(1, (len(rows) + slots - 1) // slots)
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def _attach(store, customers):
    from server.repurchase import attach_repurchase

    attached = {}
    for uk, detail in (customers or {}).items():
        if not detail:
            continue
        attached[uk] = attach_repurchase(store, detail, party=detail.get("uk") or detail.get("name"))
    return attached


def _merge_batches(batches):
    customers = {}
    for batch in batches or []:
        for uk, detail in batch or []:
            if uk and detail:
                customers[uk] = detail
    return customers


def settle_customers(store, book, directory_rows, *, workers, ledgers, tolerance, on_tick=None, executor=None):
    """Settle directory rows. `executor` is used when the caller already opened a pool."""
    rows = [row for row in (directory_rows or []) if row.get("uk")]
    total = len(rows)
    shared = _shared_rows(store)
    slots = max(1, int(workers or 1))
    if slots == 1 or total <= 1 or executor is None:
        customers = {}
        for index, row in enumerate(rows, start=1):
            payload = _batch_payload(shared, book, [row], ledgers, tolerance)
            for uk, detail in settle_customer_batch(payload):
                if uk and detail:
                    customers[uk] = detail
            if on_tick:
                on_tick(index, total)
        return _attach(store, customers)

    slice_count = total if total <= slots else min(total, max(slots, 40))
    payloads = [_batch_payload(shared, book, chunk, ledgers, tolerance) for chunk in _chunks(rows, slice_count)]
    futures = [executor.submit(settle_customer_batch, payload) for payload in payloads]
    customers = {}
    done = 0
    try:
        for future in as_completed(futures):
            for uk, detail in future.result():
                if uk and detail:
                    customers[uk] = detail
                done += 1
                if on_tick:
                    on_tick(done, total)
    except Exception:
        _stop_executor(executor)
        raise
    return _attach(store, customers)


def item_card_book(book):
    """Item cards do not need customer ledgers."""
    return {
        "as_of": book.get("as_of"),
        "holds": book.get("holds") or {},
        "default_min": book.get("default_min"),
        "default_max_days": book.get("default_max_days"),
        "item_lines_by_uk": book.get("item_lines_by_uk") or {},
        "item_attrs": book.get("item_attrs") or {},
        "stock_rows": book.get("stock_rows") or [],
    }


def build_item_cards_job(payload):
    from server.items360 import _build_item_cards

    return _build_item_cards(payload)


def bundle_dimension(payload):
    from server.item_dims import _bundle

    built = _bundle(
        payload["cards"],
        payload["attrs"],
        payload["key"],
        payload["spec"],
        payload["rolls"],
        keep_members=False,
    )
    return payload["key"], built


def _stop_executor(executor):
    if executor is None:
        return
    for proc in list(getattr(executor, "_processes", {}).values()):
        try:
            proc.terminate()
        except Exception:
            pass
    try:
        executor.shutdown(wait=False, cancel_futures=True)
    except TypeError:
        executor.shutdown(wait=False)
    except Exception:
        pass


def open_pool(workers):
    if workers < 2:
        return None
    return ProcessPoolExecutor(max_workers=workers)


def settled_member_details(book, members):
    """Customer details already settled for these directory rows, or None."""
    settled = (book or {}).get("_settled_customers") or {}
    if not settled or not members:
        return None
    found = []
    for member in members:
        detail = _lookup_settled(settled, member)
        if not isinstance((detail or {}).get("owe_buckets"), dict):
            return None
        if not isinstance(detail.get("collection_buckets"), dict):
            return None
        found.append(detail)
    return found


def _lookup_settled(settled, member):
    uk = member.get("uk") or ""
    if uk in settled:
        return settled[uk]
    want = uk.lower()
    name = clean_text(member.get("name")).lower()
    for key, value in settled.items():
        if str(key).lower() == want:
            return value
        if str((value or {}).get("uk") or "").lower() == want:
            return value
        if name and clean_text((value or {}).get("name")).lower() == name:
            return value
    return None


def apply_settled_aging(book, members, bands):
    """Sum buckets, open invoices, and settlements. None when a member was not settled."""
    details = settled_member_details(book, members)
    if details is None:
        return None
    owe = empty_buckets(bands)
    collection = empty_buckets(bands)
    open_invoices = []
    for detail, member in zip(details, members):
        for key in list(owe.keys()):
            owe[key] += (detail.get("owe_buckets") or {}).get(key) or 0
            collection[key] += (detail.get("collection_buckets") or {}).get(key) or 0
        for line in detail.get("open_invoices") or []:
            row = dict(line)
            if not row.get("party"):
                row["party"] = member.get("name")
            if not row.get("customer_uk"):
                row["customer_uk"] = member.get("uk")
            open_invoices.append(row)
    from server.business360 import company_settlements

    settlements = company_settlements({
        (detail.get("uk") or str(index)): detail
        for index, detail in enumerate(details)
    })
    orderings = [detail.get("ordering") for detail in details]
    if any(not isinstance(row, dict) for row in orderings):
        orderings = None
    return {
        "owe": owe,
        "collection": collection,
        "open_invoices": open_invoices,
        "invoices_waiting": len(open_invoices),
        "settlements": settlements,
        "orderings": orderings,
    }
