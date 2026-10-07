"""FastAPI application setup and router registration."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from server.routers import actions, analytics, auth, demo, hosted, mappers, phase5, runs, saved_reports, settings_api, uploads, users, views
from server.settings import MAX_UPLOAD_BYTES, cors_origins, lan_ips, listen_port, web_dist
from server.startup import fail_orphaned_jobs
from server.store import get_store


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store = get_store()
    claimed = fail_orphaned_jobs(store)
    from server.route_helpers import start_export_job, start_import_job, start_job
    for rid in claimed.get("run_ids") or []:
        start_job(rid)
    for rid in claimed.get("export_ids") or []:
        start_export_job(rid)
    for jid in claimed.get("import_ids") or []:
        start_import_job(jid)
    from server.weekly import ensure_weekly_run_once
    ensure_weekly_run_once(store)
    yield


app = FastAPI(title="Vay Reports API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def org_context(request: Request, call_next):
    from server.hosted import allow_request
    from server.tenant import DEFAULT_ORG, reset_org, set_org
    ip = request.client.host if request.client else ""
    if not allow_request(ip):
        return JSONResponse({"detail": "Too many requests"}, status_code=429)
    token = set_org(DEFAULT_ORG)
    try:
        return await call_next(request)
    finally:
        reset_org(token)


@app.middleware("http")
async def limit_upload(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and int(length) > MAX_UPLOAD_BYTES:
        return JSONResponse({"detail": "File too large"}, status_code=413)
    return await call_next(request)


@app.get("/api/health")
def health():
    from server.hosted import hosted_mode
    return {"ok": True, "hosted": hosted_mode()}


def _request_port(request: Request):
    host = request.headers.get("host") or ""
    if ":" in host:
        try:
            return int(host.rsplit(":", 1)[-1])
        except ValueError:
            pass
    return listen_port()


@app.get("/api/info")
def info(request: Request):
    port = _request_port(request)
    return {
        "ok": True,
        "port": port,
        "lan_urls": ["http://%s:%s" % (ip, port) for ip in lan_ips()],
    }


for api_router in (
    auth.router,
    demo.router,
    analytics.router,
    actions.router,
    saved_reports.router,
    phase5.router,
    hosted.router,
    mappers.router,
    uploads.router,
    runs.router,
    views.router,
    users.router,
    settings_api.router,
):
    app.include_router(api_router)


def mount_frontend(application: FastAPI):
    dist = web_dist()
    if (dist / "index.html").is_file():
        application.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")


mount_frontend(app)
