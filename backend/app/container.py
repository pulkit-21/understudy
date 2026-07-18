"""Composition root — the single place the application's long-lived objects are
constructed and wired together.

Importing this module (a) provisions the database schema and (b) constructs the
one instance of each repository, the run manager, and the auth repo that the
whole process shares. `main.py` assembles the ASGI app from these; `api/deps.py`
hands them to routers via FastAPI's dependency injection. Keeping construction
here means the wiring is described in exactly one file, and the routers never
reach for a global.
"""
from __future__ import annotations

from .auth import AuthRepo, bind_auth_repo
from .config import get_settings
from .db import (
    ConversationRepo,
    ReplayRepo,
    RunRepo,
    ScheduleRepo,
    SessionLocal,
    TraceRepo,
    UsageRepo,
    WorkflowRepo,
    run_migrations,
)
from .engine.manager import RunManager

settings = get_settings()

# Provision the schema before any repository reads or writes (idempotent).
run_migrations()

# --- singletons --------------------------------------------------------------
auth = AuthRepo(SessionLocal)
bind_auth_repo(auth)  # the current_user dependency resolves against this repo

traces = TraceRepo(SessionLocal)
workflows = WorkflowRepo(SessionLocal)
usage = UsageRepo(SessionLocal)
replays = ReplayRepo(SessionLocal)
conversations = ConversationRepo(SessionLocal)
schedules = ScheduleRepo(SessionLocal)
runs = RunManager(
    base_url=settings.base_url,
    run_repo=RunRepo(SessionLocal),
    headless=not settings.headful,
)
