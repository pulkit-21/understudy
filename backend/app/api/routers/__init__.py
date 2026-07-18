"""Domain routers for the HTTP API.

The API surface is split one module per resource — the controllers of the app.
`all_routers` is the ordered list `main.py` includes; each is an independent
`APIRouter(prefix="/api")` that resolves its dependencies via `api/deps.py`.
"""
from __future__ import annotations

from fastapi import APIRouter

from . import (
    agent,
    induction,
    metrics,
    recordings,
    runs,
    schedules,
    traces,
    workflows,
)

# Order is cosmetic (paths don't overlap across routers), but grouped read →
# write for a tidy /docs.
all_routers: list[APIRouter] = [
    traces.router,
    recordings.router,
    induction.router,
    workflows.router,
    runs.router,
    schedules.router,
    metrics.router,
    agent.router,
]
