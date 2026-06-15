"""FastAPI app factory + Uvicorn entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .crawler.runtime import CrawlRunnerRegistry
from .db import jobs as jobs_db
from .db.settings import get_setting
from .routes import auto_rules as auto_rules_routes
from .routes import collections as collections_routes
from .routes import crawl as crawl_routes
from .routes import crawl_queue as crawl_queue_routes
from .routes import domains as domains_routes
from .routes import edges as edges_routes
from .routes import embed as embed_routes
from .routes import entities as entities_routes
from .routes import fingerprints as fingerprints_routes
from .routes import flags as flags_routes
from .routes import graph as graph_routes
from .routes import graph_filters as graph_filters_routes
from .routes import harvest_search as harvest_search_routes
from .routes import jobs as jobs_routes
from .routes import labels as labels_routes
from .routes import llm as llm_routes
from .routes import monitors as monitors_routes
from .routes import nodes as nodes_routes
from .routes import notes as notes_routes
from .routes import pages as pages_routes
from .routes import projects as projects_routes
from .routes import prompt_templates as prompt_templates_routes
from .routes import retention as retention_routes
from .routes import schedules as schedules_routes
from .routes import search as search_routes
from .routes import search_engines as search_engines_routes
from .routes import seeds as seeds_routes
from .routes import settings as settings_routes
from .routes import sse as sse_routes
from .routes import stats as stats_routes
from .routes import watchlist as watchlist_routes
from .security.auth import (
    COOKIE_NAME,
    ApiAuthMiddleware,
    new_session,
)
from .services.crawl_queue_runner import CrawlQueueRunner
from .services.embed_worker import EmbedWorker
from .services.event_bus import EventBus
from .services.kill_switch import KillSwitch
from .services.llm_worker import LlmWorker
from .services.monitor_daemon import MonitorDaemon
from .services.project_state import ProjectState

HOST = "127.0.0.1"
PORT = 7654
ALLOWED_HOSTS = {f"{HOST}:{PORT}", HOST}

PUBLIC_DIR = Path(__file__).resolve().parent.parent / "public"

CSP_VALUE = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "worker-src blob:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'"
)

INDEX_FALLBACK = (
    b"<!doctype html><html><head><meta charset='utf-8'>"
    b"<title>Onion Rabbithole</title></head>"
    b"<body><p>backend running. frontend bundle not built yet.</p></body></html>"
)


class HostHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.headers.get("host", "") not in ALLOWED_HOSTS:
            return PlainTextResponse("invalid host", status_code=400)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP_VALUE
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Re-attach to whichever project was last active (if any). Failures fall
    # through silently — the frontend renders the project picker when there
    # is no active project.
    await app.state.project_state.load_from_registry()
    await app.state.kill_switch.start()
    await app.state.crawl_queue_runner.start()
    await app.state.monitor_daemon.start()
    # Conditionally auto-start the B8 workers based on per-project settings.
    # Settings are read inside the worker so a no-active-project state is
    # safe — the worker idles until a project comes online.
    db = app.state.project_state.active_db
    if db is not None:
        # Apply job-history retention once at startup. 0 (the default) is a
        # no-op; a positive window deletes terminal job-tracking rows older than
        # N days. Manual runs are available via POST /api/retention/run.
        try:
            days = int(get_setting(db, "retention.jobs_days") or 0)
        except ValueError:
            days = 0
        if days > 0:
            jobs_db.prune_terminal_jobs(db, older_than_days=days)
        if (get_setting(db, "embedding.auto_start") or "true").lower() == "true":
            await app.state.embed_worker.start()
        if (get_setting(db, "llm.auto_start") or "false").lower() == "true":
            await app.state.llm_worker.start()
    try:
        yield
    finally:
        await app.state.llm_worker.stop()
        await app.state.embed_worker.stop()
        await app.state.monitor_daemon.stop()
        await app.state.crawl_queue_runner.stop()
        await app.state.kill_switch.stop()
        # Stop any in-flight crawl before closing its DB handle.
        await app.state.crawl_runners.stop()
        await app.state.project_state.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Onion Rabbithole",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=_lifespan,
    )
    app.state.session = new_session()
    app.state.project_state = ProjectState.new()
    app.state.event_bus = EventBus()
    app.state.kill_switch = KillSwitch(
        project_state=app.state.project_state,
        event_bus=app.state.event_bus,
    )
    app.state.crawl_runners = CrawlRunnerRegistry()
    app.state.crawl_queue_runner = CrawlQueueRunner(
        project_state=app.state.project_state,
        kill_switch=app.state.kill_switch,
        event_bus=app.state.event_bus,
        registry=app.state.crawl_runners,
    )
    app.state.monitor_daemon = MonitorDaemon(
        project_state=app.state.project_state,
        kill_switch=app.state.kill_switch,
        event_bus=app.state.event_bus,
    )
    app.state.embed_worker = EmbedWorker(
        project_state=app.state.project_state,
        kill_switch=app.state.kill_switch,
        event_bus=app.state.event_bus,
    )
    app.state.llm_worker = LlmWorker(
        project_state=app.state.project_state,
        kill_switch=app.state.kill_switch,
        event_bus=app.state.event_bus,
    )

    # Starlette runs middleware in reverse-registration order: Host → SecHeaders → Auth.
    app.add_middleware(ApiAuthMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(HostHeaderMiddleware)

    @app.get("/api/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(projects_routes.router)
    app.include_router(settings_routes.router)
    app.include_router(retention_routes.router)
    app.include_router(stats_routes.router)
    app.include_router(sse_routes.router)
    app.include_router(crawl_routes.router)
    app.include_router(crawl_queue_routes.router)
    app.include_router(jobs_routes.router)
    app.include_router(seeds_routes.router)
    app.include_router(nodes_routes.router)
    app.include_router(pages_routes.router)
    app.include_router(edges_routes.router)
    app.include_router(watchlist_routes.router)
    app.include_router(schedules_routes.router)
    app.include_router(collections_routes.router)
    app.include_router(flags_routes.router)
    app.include_router(notes_routes.router)
    app.include_router(graph_filters_routes.router)
    app.include_router(monitors_routes.router)
    app.include_router(fingerprints_routes.router)
    app.include_router(entities_routes.router)
    app.include_router(domains_routes.router)
    app.include_router(labels_routes.router)
    app.include_router(graph_routes.router)
    app.include_router(llm_routes.router)
    app.include_router(prompt_templates_routes.router)
    app.include_router(auto_rules_routes.router)
    app.include_router(embed_routes.router)
    app.include_router(search_routes.router)
    app.include_router(search_engines_routes.router)
    app.include_router(harvest_search_routes.router)

    @app.get("/{full_path:path}")
    async def spa(request: Request, full_path: str) -> Response:
        # /api/* is handled by the explicit routes above; anything reaching the
        # catch-all under /api/* is an unknown API path → 404 (auth already passed).
        if full_path.startswith("api/"):
            return JSONResponse({"error": "not_found"}, status_code=404)

        if full_path in {"bundle.js", "bundle.css"}:
            asset = PUBLIC_DIR / full_path
            if asset.is_file():
                media = "application/javascript" if full_path.endswith(".js") else "text/css"
                return Response(asset.read_bytes(), media_type=media)
            return PlainTextResponse("not built", status_code=404)

        index = PUBLIC_DIR / "index.html"
        body = index.read_bytes() if index.is_file() else INDEX_FALLBACK
        resp = Response(body, media_type="text/html")
        resp.set_cookie(
            key=COOKIE_NAME,
            value=app.state.session.token,
            httponly=True,
            samesite="strict",
            secure=False,  # loopback over plain HTTP — Secure would block delivery
            path="/",
        )
        return resp

    return app


def run() -> None:
    uvicorn.run("backend.main:create_app", host=HOST, port=PORT, factory=True, log_level="info")
