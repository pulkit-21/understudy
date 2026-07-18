"""Understudy — learn a browser workflow by watching, then run it with guardrails.

App layout:
  /portal, /erp   — the two deterministic mock finance apps (the demo stage)
  /api/...        — traces, workflows, runs (see api/routes.py)
  /               — minimal control panel (React app replaces this; Day 3)
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
from .api.routes import build_router
from .config import get_settings
from .container import (
    auth,
    conversations,
    replays,
    runs,
    traces,
    usage,
    workflows,
)
from .mockapps.routes import router as mockapps_router
from .ratelimit import limiter
from .seed import seed_demo_account, seed_if_empty

# `auth`, `runs`, and the repos are constructed in container.py (the composition
# root); re-exported here because tests and tooling import them from app.main.
settings = get_settings()
DATA_DIR = settings.data_dir
BASE_URL = settings.base_url
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # A fresh deploy seeds a demo account + workflow so it's demoable on load.
    demo_org = seed_demo_account(auth)
    seed_if_empty(traces, workflows, demo_org, base=BASE_URL)
    yield


app = FastAPI(title="Understudy", version="0.1.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mockapps_router)
app.include_router(build_auth_router(auth))
app.include_router(build_router(traces, workflows, runs, usage, replays,
                                conversations))


@app.get("/healthz")
def healthz():
    return {"ok": True}


# ---- serve the built React control panel same-origin (one service) ----------
# In dev the Vite server proxies /api etc. to this backend; in production the
# built assets are served here so there's one URL and no CORS. If the frontend
# hasn't been built, fall back to a minimal dev launcher.
_RESERVED = ("api/", "portal", "erp", "docs", "openapi.json", "healthz",
             "assets/")

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"),
              name="assets")
    _INDEX = FRONTEND_DIST / "index.html"

    @app.get("/", response_class=FileResponse)
    def spa_root():
        return FileResponse(_INDEX)

    @app.get("/{full_path:path}", response_class=FileResponse)
    def spa_fallback(full_path: str):
        # Client-side routes (/workflows/:id, /runs/:id) resolve to the SPA;
        # unknown API/mock paths stay 404 rather than returning HTML.
        if full_path.startswith(_RESERVED):
            raise HTTPException(404)
        return FileResponse(_INDEX)
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
