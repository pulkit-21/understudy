"""Understudy — learn a browser workflow by watching, then run it with guardrails.

App layout:
  /portal, /erp   — the two deterministic mock finance apps (the demo stage)
  /api/...        — traces, workflows, runs (see api/routes.py)
  /               — minimal control panel (React app replaces this; Day 3)
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import build_router
from .db import RunRepo, SessionLocal, TraceRepo, WorkflowRepo, run_migrations
from .executor.manager import RunManager
from .mockapps.routes import router as mockapps_router
from .seed import seed_if_empty

DATA_DIR = Path(os.environ.get("UNDERSTUDY_DATA", "./data"))
BASE_URL = os.environ.get("UNDERSTUDY_BASE_URL", "http://localhost:8000")
FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# Provision the schema before anything reads/writes (idempotent).
run_migrations()

traces = TraceRepo(SessionLocal)
workflows = WorkflowRepo(SessionLocal)
runs = RunManager(base_url=BASE_URL, run_repo=RunRepo(SessionLocal),
                  headless=os.environ.get("UNDERSTUDY_HEADFUL") != "1")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # A fresh deploy seeds itself so it's demoable on first load.
    seed_if_empty(traces, workflows, base=BASE_URL)
    yield


app = FastAPI(title="Understudy", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(mockapps_router)
app.include_router(build_router(traces, workflows, runs))


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
