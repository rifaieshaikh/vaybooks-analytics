# Backup and restore

Two copies are required for a desktop install:

1. The MongoDB data directory (bundled `mongod` data under the app data folder). Copy that directory while the app is quit, and restore it onto a clean install by putting it back before the next launch.
2. An organization snapshot from `GET /api/backup`, restored with `POST /api/backup/restore`. The snapshot replaces the current organization’s rows and leaves other organizations in place.

`tests/test_roadmap_close.py` restores a snapshot onto a clean in-memory store. The directory copy is the operator step for the database files themselves.
