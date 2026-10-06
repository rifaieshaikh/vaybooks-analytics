# Load shape

`tests/test_roadmap_close.py` inserts 500 sales rows and requests `GET /api/rows?type=sales&limit=50`.

The response page contains 50 rows. `total` is 500. The page size is capped at 200 by `ROW_PAGE_CAP`. Runs use the same style of page on `GET /api/runs?limit=50`.
