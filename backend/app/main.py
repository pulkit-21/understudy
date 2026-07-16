"""Understudy — learn a browser workflow by watching, then run it with guardrails.

App layout:
  /portal, /erp   — the two deterministic mock finance apps (the demo stage)
  /api/...        — traces, workflows, runs (see api/routes.py)
  /               — minimal control panel (React app replaces this; Day 3)
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from .api.routes import WorkflowStore, build_router
from .executor.manager import RunManager
from .mockapps.routes import router as mockapps_router
from .recorder.session import TraceStore

DATA_DIR = Path(os.environ.get("UNDERSTUDY_DATA", "./data"))
BASE_URL = os.environ.get("UNDERSTUDY_BASE_URL", "http://localhost:8000")

app = FastAPI(title="Understudy", version="0.1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
    allow_headers=["*"],
)

traces = TraceStore(DATA_DIR / "traces")
workflows = WorkflowStore(DATA_DIR / "workflows")
runs = RunManager(base_url=BASE_URL, log_dir=DATA_DIR / "runs",
                  headless=os.environ.get("UNDERSTUDY_HEADFUL") != "1")

app.include_router(mockapps_router)
app.include_router(build_router(traces, workflows, runs))


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def index():
    return """<!doctype html><meta charset=utf-8>
    <title>Understudy</title>
    <body style="font:15px/1.6 system-ui;max-width:640px;margin:60px auto;color:#1c2430">
    <h1 style="font-size:22px">Understudy <span style="color:#67707d;font-weight:400">— dev index</span></h1>
    <p>Learn a browser workflow by watching a demonstration, then run it
    with approval gates. The React control panel replaces this page.</p>
    <ul>
      <li><a href="/portal">Vendra — mock invoice portal</a></li>
      <li><a href="/erp">LedgerOne — mock ERP</a></li>
      <li><a href="/docs">API docs (OpenAPI)</a></li>
    </ul></body>"""
