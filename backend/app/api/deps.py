"""FastAPI dependency providers — the DI seam between routers and the wiring.

Routers declare what they need (`workflows: WorkflowRepo = Depends(get_workflows)`)
instead of closing over module globals. That keeps each router independently
importable and testable, and lets a test override a dependency via
`app.dependency_overrides[get_workflows] = ...` without patching internals.

The providers return the process-wide singletons built in `container.py`.
`current_user` (authn) lives in `auth.py` and is re-exported here so routers have
one import site for everything they depend on.
"""
from __future__ import annotations

from .. import container
from ..auth import User, current_user, user_from_token
from ..db.repositories import (
    ConversationRepo,
    ReplayRepo,
    TraceRepo,
    UsageRepo,
    WorkflowRepo,
)
from ..executor.manager import RunManager

__all__ = [
    "User",
    "current_user",
    "get_conversations",
    "get_replays",
    "get_runs",
    "get_traces",
    "get_usage",
    "get_workflows",
    "user_from_token",
]


def get_traces() -> TraceRepo:
    return container.traces


def get_workflows() -> WorkflowRepo:
    return container.workflows


def get_runs() -> RunManager:
    return container.runs


def get_usage() -> UsageRepo:
    return container.usage


def get_replays() -> ReplayRepo:
    return container.replays


def get_conversations() -> ConversationRepo:
    return container.conversations
