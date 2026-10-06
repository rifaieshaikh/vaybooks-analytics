"""In-memory store for tests; Mongo store when MONGODB_URI is set."""

from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime

from bson import ObjectId
from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError
from gridfs import GridFS

from server.settings import mongo_uri, use_memory_store
from server.tenant import DEFAULT_ORG, current_org_id, doc_org, in_org, stamp_org


def now_utc():
    return datetime.utcnow()


def org_filter(extra=None):
    """Mongo filter for the current organization. Unscoped calls keep ``extra`` only."""
    extra = dict(extra or {})
    want = current_org_id()
    if want is None:
        return extra
    clause = {"org_id": want}
    if not extra:
        return clause
    return {"$and": [clause, extra]}


class DuplicateUk(Exception):
    pass


def _seed(store):
    from server.auth import seed_store

    seed_store(store)


class MemoryStore:
    def __init__(self):
        self.lock = threading.Lock()
        self.mappers = {}
        self.rows = []
        self.uploads = {}
        self.blobs = {}
        self.runs = {}
        self.import_jobs = {}
        self.recon_sidecars = {}
        self.users = {}
        self.roles = {}
        self.sessions = {}
        self.audit_events = []
        self.view_parts = {}
        self._360_book = None
        _seed(self)

    def ensure_indexes(self):
        return

    def _mapper_key(self, type_name, org=None):
        org = org or current_org_id() or DEFAULT_ORG
        return "%s\0%s" % (org, type_name)

    def get_mapper(self, type_name):
        doc = self.mappers.get(self._mapper_key(type_name))
        if doc is None and current_org_id() in (None, DEFAULT_ORG):
            doc = self.mappers.get(type_name)
        return deepcopy(doc) if doc else None

    def list_mappers(self):
        want = current_org_id()
        out = []
        for key, doc in self.mappers.items():
            if want is None or in_org(doc) or (want == DEFAULT_ORG and isinstance(key, str) and "\0" not in key):
                item = deepcopy(doc)
                item["type"] = doc.get("type") or (str(key).split("\0")[-1])
                out.append(item)
        return out

    def put_mapper(self, type_name, doc):
        doc = stamp_org(doc)
        doc["type"] = type_name
        self.mappers[self._mapper_key(type_name, doc.get("org_id"))] = doc
        return deepcopy(doc)

    def insert_row(self, doc):
        doc = stamp_org(doc)
        with self.lock:
            for existing in self.rows:
                if existing["type"] == doc["type"] and existing["uk"] == doc["uk"] and doc_org(existing) == doc["org_id"]:
                    raise DuplicateUk()
            stored = dict(doc)
            stored["_id"] = str(ObjectId())
            self.rows.append(stored)
            return stored["_id"]

    def upsert_row(self, doc):
        doc = dict(doc)
        cur = current_org_id()
        with self.lock:
            for i, existing in enumerate(self.rows):
                if existing["type"] == doc["type"] and existing["uk"] == doc["uk"] and in_org(existing):
                    merged = dict(existing)
                    merged.update(doc)
                    merged["org_id"] = cur or doc_org(existing)
                    self.rows[i] = merged
                    return merged["_id"]
            stored = dict(doc)
            stored["org_id"] = cur or stored.get("org_id") or DEFAULT_ORG
            stored["_id"] = str(ObjectId())
            self.rows.append(stored)
            return stored["_id"]

    def find_row(self, type_name, uk):
        for row in self.rows:
            if row["type"] == type_name and row["uk"] == uk and in_org(row):
                return deepcopy(row)
        return None

    def delete_row(self, type_name, uk):
        with self.lock:
            before = len(self.rows)
            self.rows = [
                r for r in self.rows
                if not (r["type"] == type_name and r["uk"] == uk and in_org(r))
            ]
            return before - len(self.rows)

    def rows_of_type(self, type_name):
        return [deepcopy(r) for r in self.rows if r["type"] == type_name and in_org(r)]

    def list_rows(self):
        return [deepcopy(r) for r in self.rows if in_org(r)]

    def delete_rows_by_upload(self, upload_id):
        with self.lock:
            before = len(self.rows)
            self.rows = [
                r for r in self.rows
                if not (r.get("source_upload_id") == upload_id and in_org(r))
            ]
            return before - len(self.rows)

    def count_rows_for_upload(self, upload_id):
        uid = str(upload_id or "")
        if not uid:
            return 0
        return sum(1 for r in self.rows if str(r.get("source_upload_id") or "") == uid and in_org(r))

    def delete_rows_by_uks(self, type_name, uks):
        uk_set = set(uks or [])
        with self.lock:
            before = len(self.rows)
            self.rows = [
                r for r in self.rows
                if not (r.get("type") == type_name and r.get("uk") in uk_set and in_org(r))
            ]
            return before - len(self.rows)

    def _row_date(self, row):
        from vay.dates import parse_date
        raw = row.get("Date")
        if raw is None:
            raw = (row.get("fields") or {}).get("Date")
        return parse_date(raw)

    def delete_rows_in_date_range(self, type_name, start, end):
        with self.lock:
            before = len(self.rows)
            kept = []
            for r in self.rows:
                if r.get("type") != type_name or not in_org(r):
                    kept.append(r)
                    continue
                d = self._row_date(r)
                if d is not None and start <= d <= end:
                    continue
                kept.append(r)
            self.rows = kept
            return before - len(self.rows)

    def count_rows_in_date_range(self, type_name, start, end):
        n = 0
        for r in self.rows_of_type(type_name):
            d = self._row_date(r)
            if d is not None and start <= d <= end:
                n += 1
        return n

    def delete_rows_of_type(self, type_name):
        with self.lock:
            before = len(self.rows)
            self.rows = [r for r in self.rows if not (r["type"] == type_name and in_org(r))]
            return before - len(self.rows)

    def replace_type_rows(self, type_name, docs):
        with self.lock:
            self.rows = [r for r in self.rows if not (r["type"] == type_name and in_org(r))]
            for doc in docs:
                stored = stamp_org(doc)
                stored["_id"] = stored.get("_id") or str(ObjectId())
                self.rows.append(stored)

    def put_blob(self, data, filename, content_type):
        blob_id = str(ObjectId())
        self.blobs[blob_id] = stamp_org({
            "data": data,
            "filename": filename,
            "content_type": content_type,
        })
        return blob_id

    def get_blob(self, blob_id):
        row = self.blobs.get(str(blob_id))
        if not row or not in_org(row):
            return None
        return row

    def delete_blob(self, blob_id):
        self.blobs.pop(str(blob_id), None)

    def replace_view_parts(self, run_id, parts, on_batch=None):
        org = current_org_id() or DEFAULT_ORG
        rid = str(run_id)
        self.view_parts = {
            key: value
            for key, value in self.view_parts.items()
            if not (key[0] == org and key[1] == rid)
        }
        rows = list(parts or [])
        for kind, key, body in rows:
            self.view_parts[(org, rid, str(kind), str(key))] = body
        if on_batch:
            on_batch(len(rows), len(rows))

    def get_view_part(self, run_id, kind, key):
        rid = str(run_id)
        want = (current_org_id() or DEFAULT_ORG, rid, str(kind), str(key))
        body = self.view_parts.get(want)
        if body is None and current_org_id() is None:
            for (org, part_run, part_kind, part_key), value in self.view_parts.items():
                if part_run == rid and part_kind == str(kind) and part_key == str(key):
                    return value
        return body

    def put_view_part(self, run_id, kind, key, body):
        org = current_org_id() or DEFAULT_ORG
        self.view_parts[(org, str(run_id), str(kind), str(key))] = body
        return body

    def list_view_parts(self, run_id, kind, prefix=""):
        rid = str(run_id)
        kind = str(kind)
        prefix = str(prefix or "")
        want = current_org_id()
        out = []
        for (org, part_run, part_kind, part_key), body in self.view_parts.items():
            if part_run != rid or part_kind != kind:
                continue
            if want is not None and org != want:
                continue
            if prefix and not str(part_key).startswith(prefix):
                continue
            out.append(body)
        return out

    def delete_view_parts(self, run_id):
        rid = str(run_id)
        self.view_parts = {
            key: value
            for key, value in self.view_parts.items()
            if key[1] != rid
        }

    def copy_view_parts(self, src_run_id, dest_run_id):
        src = str(src_run_id)
        dest = str(dest_run_id)
        additions = {}
        for (org, part_run, part_kind, part_key), body in list(self.view_parts.items()):
            if part_run == src:
                additions[(org, dest, part_kind, part_key)] = body
        self.view_parts.update(additions)
        return len(additions)

    def insert_upload(self, doc):
        uid = str(ObjectId())
        stored = stamp_org(doc)
        stored["_id"] = uid
        stored["created_at"] = now_utc()
        self.uploads[uid] = stored
        return uid

    def update_upload(self, uid, fields):
        uid = str(uid)
        if uid not in self.uploads or not in_org(self.uploads[uid]):
            return None
        self.uploads[uid].update(fields)
        return deepcopy(self.uploads[uid])

    def get_upload(self, uid):
        row = self.uploads.get(str(uid))
        if not row or not in_org(row):
            return None
        return deepcopy(row)

    def list_uploads(self):
        rows = [v for v in self.uploads.values() if in_org(v)]
        return [deepcopy(v) for v in sorted(rows, key=lambda a: a.get("created_at") or now_utc(), reverse=True)]

    def delete_upload(self, uid):
        uid = str(uid)
        doc = self.uploads.pop(uid, None)
        if not doc:
            return None
        if doc.get("gridfs_id"):
            self.delete_blob(doc["gridfs_id"])
        self.delete_rows_by_upload(uid)
        return doc

    def insert_recon_sidecar(self, doc):
        rid = str(ObjectId())
        stored = stamp_org(doc)
        stored["_id"] = rid
        stored["created_at"] = now_utc()
        self.recon_sidecars[rid] = stored
        return deepcopy(stored)

    def list_recon_sidecars(self):
        rows = [v for v in self.recon_sidecars.values() if in_org(v)]
        return [
            deepcopy(v)
            for v in sorted(rows, key=lambda a: a.get("created_at") or now_utc(), reverse=True)
        ]

    def get_recon_sidecar(self, rid):
        row = self.recon_sidecars.get(str(rid))
        if not row or not in_org(row):
            return None
        return deepcopy(row)

    def insert_run(self, doc):
        rid = str(ObjectId())
        stored = stamp_org(doc)
        stored["_id"] = rid
        stored["created_at"] = now_utc()
        self.runs[rid] = stored
        return deepcopy(stored)

    def peek_run(self, rid):
        row = self.runs.get(str(rid))
        return deepcopy(row) if row else None

    def get_run(self, rid):
        row = self.runs.get(str(rid))
        if not row or not in_org(row):
            return None
        return deepcopy(row)

    def list_runs(self):
        rows = [v for v in self.runs.values() if in_org(v)]
        return [deepcopy(v) for v in sorted(rows, key=lambda a: a.get("created_at") or now_utc(), reverse=True)]

    def update_run(self, rid, fields):
        rid = str(rid)
        if rid not in self.runs or not in_org(self.runs[rid]):
            return None
        self.runs[rid].update(fields)
        return deepcopy(self.runs[rid])

    def update_run_if(self, rid, match, fields):
        rid = str(rid)
        row = self.runs.get(rid)
        if not row or not in_org(row):
            return None
        for key, expected in (match or {}).items():
            if row.get(key) != expected:
                return None
        row.update(fields)
        return deepcopy(row)

    def delete_run(self, rid):
        rid = str(rid)
        doc = self.runs.get(rid)
        if not doc or not in_org(doc):
            return None
        doc = self.runs.pop(rid, None)
        for key in ("xlsx_id", "json_id", "book_json_id", "pdf_zip_id"):
            if doc.get(key):
                self.delete_blob(doc[key])
        for blob_id in doc.get("pdf_export_ids") or []:
            if blob_id:
                self.delete_blob(blob_id)
        self.delete_view_parts(rid)
        return doc

    def active_run(self):
        for row in self.runs.values():
            if in_org(row) and row.get("status") in ("queued", "running"):
                return deepcopy(row)
        return None

    def active_export(self):
        for row in self.runs.values():
            if in_org(row) and row.get("pdf_export_status") in ("queued", "running"):
                return deepcopy(row)
        return None

    def insert_import_job(self, doc):
        rid = str(ObjectId())
        stored = stamp_org(doc)
        stored["_id"] = rid
        stored["created_at"] = now_utc()
        self.import_jobs[rid] = stored
        return deepcopy(stored)

    def peek_import_job(self, rid):
        row = self.import_jobs.get(str(rid))
        return deepcopy(row) if row else None

    def get_import_job(self, rid):
        row = self.import_jobs.get(str(rid))
        if not row or not in_org(row):
            return None
        return deepcopy(row)

    def update_import_job(self, rid, fields):
        rid = str(rid)
        if rid not in self.import_jobs or not in_org(self.import_jobs[rid]):
            return None
        self.import_jobs[rid].update(fields)
        return deepcopy(self.import_jobs[rid])

    def update_import_job_if(self, rid, match, fields):
        rid = str(rid)
        row = self.import_jobs.get(rid)
        if not row or not in_org(row):
            return None
        for key, expected in (match or {}).items():
            if row.get(key) != expected:
                return None
        row.update(fields)
        return deepcopy(row)

    def active_import_job(self):
        for row in self.import_jobs.values():
            if in_org(row) and row.get("status") in ("queued", "running"):
                return deepcopy(row)
        return None

    def list_import_jobs(self):
        return [deepcopy(v) for v in self.import_jobs.values() if in_org(v)]

    def find_succeeded_import(self, file_sha, exclude_job_id=None):
        sha = str(file_sha or "")
        if not sha:
            return None
        for row in self.import_jobs.values():
            if not in_org(row) or row.get("dry_run") or row.get("status") != "succeeded":
                continue
            if str(row.get("_id")) == str(exclude_job_id or ""):
                continue
            if (row.get("file_sha256") or "") == sha:
                return deepcopy(row)
        return None

    def get_user(self, username):
        row = self.users.get(str(username or ""))
        return deepcopy(row) if row else None

    def list_users(self):
        return [deepcopy(v) for v in self.users.values() if in_org(v)]

    def put_user(self, doc):
        stored = dict(doc)
        stored["username"] = str(stored.get("username") or "")
        existing = self.users.get(stored["username"])
        cur = current_org_id()
        if existing and cur is not None and doc_org(existing) != cur:
            raise DuplicateUk()
        if cur is None:
            stored["org_id"] = doc_org(existing) if existing else (stored.get("org_id") or DEFAULT_ORG)
        else:
            stored["org_id"] = cur
        self.users[stored["username"]] = stored
        return deepcopy(stored)

    def delete_user(self, username):
        row = self.users.get(str(username))
        if not row or not in_org(row):
            return None
        return self.users.pop(str(username), None)

    def _role_key(self, name, org=None):
        org = org or current_org_id() or DEFAULT_ORG
        return "%s\0%s" % (org, name)

    def get_role(self, name):
        row = self.roles.get(self._role_key(name))
        if row is None and current_org_id() in (None, DEFAULT_ORG):
            row = self.roles.get(str(name or ""))
        return deepcopy(row) if row else None

    def list_roles(self):
        want = current_org_id()
        out = []
        for key, row in self.roles.items():
            legacy = isinstance(key, str) and "\0" not in key and not row.get("org_id")
            if want is None or in_org(row) or (want == DEFAULT_ORG and legacy):
                out.append(deepcopy(row))
        return out

    def put_role(self, name, doc):
        stored = dict(doc)
        stored["name"] = name
        cur = current_org_id()
        stored["org_id"] = cur or stored.get("org_id") or DEFAULT_ORG
        self.roles[self._role_key(name, stored["org_id"])] = stored
        return deepcopy(stored)

    def append_audit(self, doc):
        stored = stamp_org(doc)
        stored["_id"] = str(ObjectId())
        stored["created_at"] = now_utc()
        self.audit_events.append(stored)
        return deepcopy(stored)

    def list_audit(self, limit=50, offset=0):
        rows = [deepcopy(r) for r in self.audit_events if in_org(r)]
        rows.sort(key=lambda r: r.get("created_at") or now_utc(), reverse=True)
        total = len(rows)
        start = max(0, int(offset or 0))
        size = max(1, min(int(limit or 50), 200))
        return rows[start:start + size], total

    def put_session(self, token, doc):
        stored = dict(doc)
        stored["token"] = token
        self.sessions[token] = stored
        return deepcopy(stored)

    def get_session(self, token):
        row = self.sessions.get(str(token or ""))
        return deepcopy(row) if row else None

    def delete_session(self, token):
        return self.sessions.pop(str(token or ""), None)

    def delete_sessions_for(self, username):
        drop = [k for k, v in self.sessions.items() if v.get("username") == username]
        for k in drop:
            self.sessions.pop(k, None)


class MongoStore:
    def __init__(self, uri=None):
        self.client = MongoClient(uri or mongo_uri())
        try:
            self.db = self.client.get_default_database()
        except Exception:
            self.db = self.client.get_database("vay-reports")
        self.fs = GridFS(self.db)
        self._360_book = None
        self.ensure_indexes()
        _seed(self)

    def _migrate_org_ids(self):
        for name in ("mapped_rows", "uploads", "runs", "import_jobs", "recon_sidecars", "users", "roles", "mappers"):
            try:
                self.db[name].update_many(
                    {"$or": [{"org_id": {"$exists": False}}, {"org_id": ""}]},
                    {"$set": {"org_id": DEFAULT_ORG}},
                )
            except Exception:
                pass

    def ensure_indexes(self):
        self._migrate_org_ids()
        try:
            self.db.mapped_rows.drop_index("type_1_uk_1")
        except Exception:
            pass
        self.db.mapped_rows.create_index([("org_id", 1), ("type", 1), ("uk", 1)], unique=True)
        self.db.mapped_rows.create_index([("org_id", 1), ("type", 1), ("source_upload_id", 1)])
        self.db.mapped_rows.create_index([("org_id", 1), ("type", 1), ("Date", 1)])
        self.db.runs.create_index([("org_id", 1), ("status", 1)])
        self.db.import_jobs.create_index([("org_id", 1), ("status", 1), ("file_sha256", 1)])
        self.db.audit_events.create_index([("org_id", 1), ("created_at", -1)])
        self.db.users.create_index("username", unique=True)
        self.db.sessions.create_index("token", unique=True)
        self.db.view_parts.create_index(
            [("org_id", 1), ("run_id", 1), ("kind", 1), ("key", 1)],
            unique=True,
        )

    def get_mapper(self, type_name):
        want = current_org_id() or DEFAULT_ORG
        if current_org_id() is None:
            return self.db.mappers.find_one({"type": type_name})
        doc = self.db.mappers.find_one({"_id": "%s\0%s" % (want, type_name)})
        if doc:
            return doc
        if want == DEFAULT_ORG:
            return self.db.mappers.find_one({"_id": type_name})
        return None

    def list_mappers(self):
        out = []
        query = {} if current_org_id() is None else org_filter()
        for doc in self.db.mappers.find(query):
            doc["type"] = doc.get("type") or str(doc.get("_id") or "").split("\0")[-1]
            out.append(doc)
        if current_org_id() == DEFAULT_ORG:
            seen = {row.get("type") for row in out}
            for doc in self.db.mappers.find({"_id": {"$not": {"$regex": "\0"}}}):
                doc["type"] = doc.get("type") or doc.get("_id")
                if doc["type"] not in seen:
                    out.append(doc)
        return out

    def put_mapper(self, type_name, doc):
        stored = stamp_org(doc)
        stored["type"] = type_name
        stored["_id"] = "%s\0%s" % (stored["org_id"], type_name)
        self.db.mappers.replace_one({"_id": stored["_id"]}, stored, upsert=True)
        return stored

    def insert_row(self, doc):
        doc = stamp_org(doc)
        try:
            result = self.db.mapped_rows.insert_one(doc)
            return str(result.inserted_id)
        except DuplicateKeyError:
            raise DuplicateUk()

    def upsert_row(self, doc):
        doc = dict(doc)
        cur = current_org_id()
        doc["org_id"] = cur or doc.get("org_id") or DEFAULT_ORG
        query = {"type": doc["type"], "uk": doc["uk"], "org_id": doc["org_id"]}
        result = self.db.mapped_rows.find_one_and_update(
            query,
            {"$set": doc},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return str(result["_id"])

    def find_row(self, type_name, uk):
        return self.db.mapped_rows.find_one(org_filter({"type": type_name, "uk": uk}))

    def delete_row(self, type_name, uk):
        result = self.db.mapped_rows.delete_many(org_filter({"type": type_name, "uk": uk}))
        return result.deleted_count

    def rows_of_type(self, type_name):
        return list(self.db.mapped_rows.find(org_filter({"type": type_name})))

    def list_rows(self):
        return list(self.db.mapped_rows.find(org_filter()))

    def delete_rows_by_upload(self, upload_id):
        result = self.db.mapped_rows.delete_many(org_filter({"source_upload_id": str(upload_id)}))
        return result.deleted_count

    def count_rows_for_upload(self, upload_id):
        uid = str(upload_id or "")
        if not uid:
            return 0
        return self.db.mapped_rows.count_documents(org_filter({"source_upload_id": uid}))

    def delete_rows_by_uks(self, type_name, uks):
        uk_list = list(uks or [])
        if not uk_list:
            return 0
        result = self.db.mapped_rows.delete_many(org_filter({"type": type_name, "uk": {"$in": uk_list}}))
        return result.deleted_count

    def _mongo_date_filter(self, start, end):
        # Dates may be datetime on Date field or string in fields.Date — match Date field primarily
        return {
            "$or": [
                {"Date": {"$gte": start, "$lte": end}},
                {"fields.Date": {"$gte": start, "$lte": end}},
            ]
        }

    def delete_rows_in_date_range(self, type_name, start, end):
        # Load and filter in Python for consistent parse_date behaviour with memory store
        from vay.dates import parse_date
        deleted = 0
        for row in list(self.db.mapped_rows.find(org_filter({"type": type_name}))):
            raw = row.get("Date")
            if raw is None:
                raw = (row.get("fields") or {}).get("Date")
            d = parse_date(raw)
            if d is not None and start <= d <= end:
                self.db.mapped_rows.delete_one({"_id": row["_id"]})
                deleted += 1
        return deleted

    def count_rows_in_date_range(self, type_name, start, end):
        from vay.dates import parse_date
        n = 0
        for row in self.db.mapped_rows.find(org_filter({"type": type_name})):
            raw = row.get("Date")
            if raw is None:
                raw = (row.get("fields") or {}).get("Date")
            d = parse_date(raw)
            if d is not None and start <= d <= end:
                n += 1
        return n

    def delete_rows_of_type(self, type_name):
        result = self.db.mapped_rows.delete_many(org_filter({"type": type_name}))
        return result.deleted_count

    def replace_type_rows(self, type_name, docs):
        self.db.mapped_rows.delete_many(org_filter({"type": type_name}))
        stamped = [stamp_org(doc) for doc in (docs or [])]
        if stamped:
            self.db.mapped_rows.insert_many(stamped)

    def put_blob(self, data, filename, content_type):
        org = current_org_id() or DEFAULT_ORG
        return str(self.fs.put(data, filename=filename, contentType=content_type, org_id=org))

    def get_blob(self, blob_id):
        try:
            gf = self.fs.get(ObjectId(str(blob_id)))
        except Exception:
            return None
        if not in_org({"org_id": getattr(gf, "org_id", None)}):
            return None
        return {
            "data": gf.read(),
            "filename": gf.filename,
            "content_type": gf.content_type or "application/octet-stream",
        }

    def delete_blob(self, blob_id):
        try:
            self.fs.delete(ObjectId(str(blob_id)))
        except Exception:
            pass

    def replace_view_parts(self, run_id, parts, on_batch=None):
        rid = str(run_id)
        self.db.view_parts.delete_many(org_filter({"run_id": rid}))
        org = current_org_id() or DEFAULT_ORG
        docs = []
        rows = list(parts or [])
        written = 0
        total = len(rows)
        for kind, key, body in rows:
            docs.append({
                "org_id": org,
                "run_id": rid,
                "kind": str(kind),
                "key": str(key),
                "body": body,
            })
            if len(docs) >= 200:
                self.db.view_parts.insert_many(docs, ordered=False)
                written += len(docs)
                docs = []
                if on_batch:
                    on_batch(written, total)
        if docs:
            self.db.view_parts.insert_many(docs, ordered=False)
            written += len(docs)
            if on_batch:
                on_batch(written, total)

    def get_view_part(self, run_id, kind, key):
        row = self.db.view_parts.find_one(org_filter({
            "run_id": str(run_id),
            "kind": str(kind),
            "key": str(key),
        }))
        if not row:
            return None
        return row.get("body")

    def put_view_part(self, run_id, kind, key, body):
        org = current_org_id() or DEFAULT_ORG
        filt = org_filter({
            "run_id": str(run_id),
            "kind": str(kind),
            "key": str(key),
        })
        self.db.view_parts.replace_one(filt, {
            "org_id": org,
            "run_id": str(run_id),
            "kind": str(kind),
            "key": str(key),
            "body": body,
        }, upsert=True)
        return body

    def list_view_parts(self, run_id, kind, prefix=""):
        query = {"run_id": str(run_id), "kind": str(kind)}
        if prefix:
            import re
            query["key"] = {"$regex": "^" + re.escape(str(prefix))}
        rows = self.db.view_parts.find(org_filter(query), {"body": 1})
        return [row.get("body") for row in rows if row.get("body") is not None]

    def delete_view_parts(self, run_id):
        self.db.view_parts.delete_many({"run_id": str(run_id)})

    def copy_view_parts(self, src_run_id, dest_run_id):
        rows = list(self.db.view_parts.find(org_filter({"run_id": str(src_run_id)})))
        docs = []
        for row in rows:
            docs.append({
                "org_id": row.get("org_id") or current_org_id() or DEFAULT_ORG,
                "run_id": str(dest_run_id),
                "kind": row.get("kind"),
                "key": row.get("key"),
                "body": row.get("body"),
            })
        if docs:
            self.db.view_parts.insert_many(docs, ordered=False)
        return len(docs)

    def insert_upload(self, doc):
        stored = stamp_org(doc)
        stored["created_at"] = now_utc()
        result = self.db.uploads.insert_one(stored)
        return str(result.inserted_id)

    def update_upload(self, uid, fields):
        try:
            oid = ObjectId(str(uid))
        except Exception:
            return None
        existing = self.db.uploads.find_one({"_id": oid})
        if not existing or not in_org(existing):
            return None
        self.db.uploads.update_one({"_id": oid}, {"$set": fields})
        return self.get_upload(uid)

    def get_upload(self, uid):
        try:
            doc = self.db.uploads.find_one({"_id": ObjectId(str(uid))})
        except Exception:
            doc = self.db.uploads.find_one({"_id": str(uid)})
        if not doc or not in_org(doc):
            return None
        return doc

    def list_uploads(self):
        return list(self.db.uploads.find(org_filter()).sort("created_at", -1))

    def delete_upload(self, uid):
        doc = self.get_upload(uid)
        if not doc:
            return None
        if doc.get("gridfs_id"):
            self.delete_blob(doc["gridfs_id"])
        self.delete_rows_by_upload(str(doc["_id"]))
        self.db.uploads.delete_one({"_id": doc["_id"]})
        doc["_id"] = str(doc["_id"])
        return doc

    def insert_recon_sidecar(self, doc):
        stored = stamp_org(doc)
        stored["created_at"] = now_utc()
        result = self.db.recon_sidecars.insert_one(stored)
        stored["_id"] = result.inserted_id
        return stored

    def list_recon_sidecars(self):
        return list(self.db.recon_sidecars.find(org_filter()).sort("created_at", -1))

    def get_recon_sidecar(self, rid):
        try:
            doc = self.db.recon_sidecars.find_one({"_id": ObjectId(str(rid))})
        except Exception:
            doc = None
        if not doc or not in_org(doc):
            return None
        return doc

    def insert_run(self, doc):
        stored = stamp_org(doc)
        stored["created_at"] = now_utc()
        result = self.db.runs.insert_one(stored)
        stored["_id"] = result.inserted_id
        return stored

    def peek_run(self, rid):
        try:
            return self.db.runs.find_one({"_id": ObjectId(str(rid))})
        except Exception:
            return None

    def get_run(self, rid):
        doc = self.peek_run(rid)
        if not doc or not in_org(doc):
            return None
        return doc

    def list_runs(self):
        return list(self.db.runs.find(org_filter(), {"dashboard": 0}).sort("created_at", -1))

    def update_run(self, rid, fields):
        doc = self.peek_run(rid)
        if not doc or not in_org(doc):
            return None
        self.db.runs.update_one({"_id": doc["_id"]}, {"$set": fields})
        return self.get_run(rid)

    def update_run_if(self, rid, match, fields):
        doc = self.peek_run(rid)
        if not doc or not in_org(doc):
            return None
        query = {"_id": doc["_id"]}
        for key, expected in (match or {}).items():
            query[key] = expected
        result = self.db.runs.update_one(query, {"$set": fields})
        if not getattr(result, "modified_count", 0):
            return None
        return self.get_run(rid)

    def delete_run(self, rid):
        doc = self.get_run(rid)
        if not doc:
            return None
        for key in ("xlsx_id", "json_id", "book_json_id", "pdf_zip_id"):
            if doc.get(key):
                self.delete_blob(doc[key])
        for blob_id in doc.get("pdf_export_ids") or []:
            if blob_id:
                self.delete_blob(blob_id)
        self.delete_view_parts(str(doc.get("_id") or rid))
        try:
            self.db.runs.delete_one({"_id": ObjectId(str(rid))})
        except Exception:
            self.db.runs.delete_one({"_id": str(rid)})
        return doc

    def active_run(self):
        return self.db.runs.find_one(org_filter({"status": {"$in": ["queued", "running"]}}))

    def active_export(self):
        return self.db.runs.find_one(org_filter({"pdf_export_status": {"$in": ["queued", "running"]}}))

    def insert_import_job(self, doc):
        stored = stamp_org(doc)
        stored["created_at"] = now_utc()
        result = self.db.import_jobs.insert_one(stored)
        stored["_id"] = result.inserted_id
        return stored

    def peek_import_job(self, rid):
        try:
            return self.db.import_jobs.find_one({"_id": ObjectId(str(rid))})
        except Exception:
            return None

    def get_import_job(self, rid):
        doc = self.peek_import_job(rid)
        if not doc or not in_org(doc):
            return None
        return doc

    def update_import_job(self, rid, fields):
        doc = self.peek_import_job(rid)
        if not doc or not in_org(doc):
            return None
        self.db.import_jobs.update_one({"_id": doc["_id"]}, {"$set": fields})
        return self.get_import_job(rid)

    def update_import_job_if(self, rid, match, fields):
        doc = self.peek_import_job(rid)
        if not doc or not in_org(doc):
            return None
        query = {"_id": doc["_id"]}
        for key, expected in (match or {}).items():
            query[key] = expected
        result = self.db.import_jobs.update_one(query, {"$set": fields})
        if not getattr(result, "modified_count", 0):
            return None
        return self.get_import_job(rid)

    def active_import_job(self):
        return self.db.import_jobs.find_one(org_filter({"status": {"$in": ["queued", "running"]}}))

    def list_import_jobs(self):
        return list(self.db.import_jobs.find(org_filter()))

    def find_succeeded_import(self, file_sha, exclude_job_id=None):
        sha = str(file_sha or "")
        if not sha:
            return None
        query = org_filter({"file_sha256": sha, "status": "succeeded", "dry_run": {"$ne": True}})
        for doc in self.db.import_jobs.find(query):
            if str(doc.get("_id")) == str(exclude_job_id or ""):
                continue
            return doc
        return None

    def get_user(self, username):
        return self.db.users.find_one({"username": str(username or "")})

    def list_users(self):
        return list(self.db.users.find(org_filter()))

    def put_user(self, doc):
        stored = dict(doc)
        stored["username"] = str(stored.get("username") or "")
        existing = self.get_user(stored["username"])
        cur = current_org_id()
        if existing and cur is not None and doc_org(existing) != cur:
            raise DuplicateUk()
        if cur is None:
            stored["org_id"] = doc_org(existing) if existing else (stored.get("org_id") or DEFAULT_ORG)
        else:
            stored["org_id"] = cur
        self.db.users.replace_one({"username": stored["username"]}, stored, upsert=True)
        return stored

    def delete_user(self, username):
        doc = self.get_user(username)
        if not doc or not in_org(doc):
            return None
        self.db.users.delete_one({"username": str(username)})
        self.delete_sessions_for(str(username))
        return doc

    def get_role(self, name):
        want = current_org_id() or DEFAULT_ORG
        if current_org_id() is None:
            return self.db.roles.find_one({"name": str(name or "")}) or self.db.roles.find_one({"_id": str(name or "")})
        scoped = self.db.roles.find_one({"_id": "%s\0%s" % (want, name)})
        if scoped:
            return scoped
        legacy = self.db.roles.find_one({"_id": str(name or "")})
        if legacy and doc_org(legacy) == want:
            return legacy
        return None

    def list_roles(self):
        if current_org_id() is None:
            return list(self.db.roles.find())
        return list(self.db.roles.find({"org_id": current_org_id()}))

    def put_role(self, name, doc):
        stored = dict(doc)
        stored["name"] = name
        cur = current_org_id()
        stored["org_id"] = cur or stored.get("org_id") or DEFAULT_ORG
        legacy = None
        if stored["org_id"] == DEFAULT_ORG:
            legacy = self.db.roles.find_one({"_id": str(name), "org_id": DEFAULT_ORG})
        stored["_id"] = legacy["_id"] if legacy else "%s\0%s" % (stored["org_id"], name)
        self.db.roles.replace_one({"_id": stored["_id"]}, stored, upsert=True)
        return stored

    def append_audit(self, doc):
        stored = stamp_org(doc)
        stored["created_at"] = now_utc()
        result = self.db.audit_events.insert_one(stored)
        stored["_id"] = result.inserted_id
        return stored

    def list_audit(self, limit=50, offset=0):
        size = max(1, min(int(limit or 50), 200))
        start = max(0, int(offset or 0))
        query = org_filter()
        total = self.db.audit_events.count_documents(query)
        rows = list(self.db.audit_events.find(query).sort("created_at", -1).skip(start).limit(size))
        return rows, total

    def put_session(self, token, doc):
        stored = dict(doc)
        stored["token"] = token
        stored["_id"] = token
        self.db.sessions.replace_one({"token": token}, stored, upsert=True)
        return stored

    def get_session(self, token):
        return self.db.sessions.find_one({"token": str(token or "")})

    def delete_session(self, token):
        doc = self.get_session(token)
        self.db.sessions.delete_one({"token": str(token or "")})
        return doc

    def delete_sessions_for(self, username):
        self.db.sessions.delete_many({"username": str(username)})


def _wrap_invalidate(cls, names):
    for name in names:
        orig = getattr(cls, name)

        def wrapped(self, *args, _orig=orig, **kwargs):
            self._360_book = None
            return _orig(self, *args, **kwargs)

        setattr(cls, name, wrapped)


_WRITE_METHODS = (
    "insert_row",
    "upsert_row",
    "delete_row",
    "delete_rows_by_upload",
    "delete_rows_of_type",
    "replace_type_rows",
    "insert_run",
    "update_run",
)
_wrap_invalidate(MemoryStore, _WRITE_METHODS)
_wrap_invalidate(MongoStore, _WRITE_METHODS)

_STORE = None


def get_store():
    global _STORE
    if _STORE is None:
        if use_memory_store():
            _STORE = MemoryStore()
        else:
            _STORE = MongoStore()
    return _STORE


def reset_store_for_tests():
    global _STORE
    _STORE = MemoryStore()
    return _STORE
