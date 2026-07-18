"""Understudy — learn a browser workflow by watching, then run it with guardrails.

This module is the **composition root's HTTP face**: an application factory
(`create_app`) that assembles the ASGI app from the pieces built elsewhere —
middleware, the auth router, the domain routers (`api/routers/`), lifespan
seeding, and same-origin serving of the built React panel. The long-lived
singletons themselves live in `container.py`.

App layout:
  /portal, /erp   — the two deterministic mock finance apps (the demo stage)
  /api/...        — traces, workflows, runs, agent (see api/routers/)
  /               — the React control panel (built assets served here in prod)
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .api.auth_routes import build_auth_router
from .api.routers import all_routers
from .config import get_settings
from .container import auth, runs, traces, workflows
from .mockapps.routes import router as mockapps_router
from .ratelimit import limiter
from .seed import seed_demo_account, seed_if_empty
from .services.errors import register_error_handlers

# The singletons are constructed in container.py (the composition root). `auth`,
# `traces`, and `workflows` are used below; `runs` (and `app`) are re-exported
# via __all__ because tests and tooling import them from app.main.
__all__ = ["app", "auth", "create_app", "runs", "traces", "workflows"]

settings = get_settings()
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# Paths owned by the API / mock apps: the SPA catch-all must NOT shadow them.
_RESERVED = ("api/", "portal", "erp", "docs", "openapi.json", "healthz", "assets/")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # A fresh deploy seeds a demo account + workflows so it's demoable on load.
    demo_org = seed_demo_account(auth)
    seed_if_empty(traces, workflows, demo_org, base=settings.base_url)
    yield


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built React panel same-origin (one service, no CORS). In dev the
    Vite server proxies /api to this backend; in prod the built assets are served
    here. If the frontend isn't built, fall back to a minimal dev launcher."""
    if FRONTEND_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"),
                  name="assets")
        index = FRONTEND_DIST / "index.html"

        @app.get("/", response_class=FileResponse)
        def spa_root():
            return FileResponse(index)

        @app.get("/{full_path:path}", response_class=FileResponse)
        def spa_fallback(full_path: str):
            # Client-side routes (/workflows/:id, /runs/:id) resolve to the SPA;
            # unknown API/mock paths stay 404 rather than returning HTML.
            if full_path.startswith(_RESERVED):
                raise HTTPException(404)
            return FileResponse(index)
    else:
        @app.get("/", response_class=HTMLResponse)
        def dev_index():
            return """<!doctype html><meta charset=utf-8>
            <title>Understudy</title>
            <body style="font:15px/1.6 system-ui;max-width:640px;margin:60px auto;color:#1c2430">
            <h1 style="font-size:22px">Understudy <span style="color:#67707d;font-weight:400">— dev index</span></h1>
            <p>The React control panel isn't built yet. Run
            <code>cd frontend && npm install && npm run build</code>, or use the Vite
            dev server (<code>npm run dev</code>). Meanwhile:</p>
            <ul>
              <li><a href="/portal">Vendra — mock invoice portal</a></li>
              <li><a href="/erp">LedgerOne — mock ERP</a></li>
              <li><a href="/docs">API docs (OpenAPI)</a></li>
            </ul></body>"""


def create_app() -> FastAPI:
    """Application factory: assemble and return the ASGI app."""
    settings.require_secure()  # refuse to boot with the dev secret on a real deploy
    app = FastAPI(title="Understudy", version="0.1.0", lifespan=lifespan)

    # rate limiting (auth + expensive endpoints opt in via @limiter.limit)
    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware, allow_origins=settings.cors_origins,
        allow_methods=["*"], allow_headers=["*"],
    )

    # domain errors raised by the service layer -> HTTP status codes
    register_error_handlers(app)

    # routers: mock apps, auth, then the domain API surface
    app.include_router(mockapps_router)
    app.include_router(build_auth_router(auth))
    for router in all_routers:
        app.include_router(router)

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    _mount_frontend(app)  # keep last: the SPA catch-all is greedy
    return app


app = create_app()
