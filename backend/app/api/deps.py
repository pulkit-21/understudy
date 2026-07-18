"""FastAPI dependency providers — the DI seam between routers and the wiring.

Routers declare what they need (`svc: WorkflowService = Depends(get_workflow_service)`)
instead of closing over module globals. That keeps each router independently
importable and testable, and lets a test override a dependency via
`app.dependency_overrides[...] = ...` without patching internals.

Providers return objects built from the process-wide singletons in
`container.py`. Repository providers are the low-level seam; service providers
compose them into the use-case layer that routers actually depend on.
`current_user` (authn) lives in `auth.py` and is re-exported here so routers have
one import site for everything.
"""
from __future__ import annotations

from .. import container
from ..auth import User, current_user, user_from_token
from ..engine.manager import RunManager
from ..repos import (
    ConversationRepo,
    ReplayRepo,
    TraceRepo,
    UsageRepo,
    WorkflowRepo,
)
from ..services.agent import AgentService
from ..services.induction import InductionService
from ..services.metrics import MetricsService
from ..services.runs import RunService
from ..services.scheduling import ScheduleService
from ..services.traces import TraceService
from ..services.workflows import WorkflowService

__all__ = [
    "User",
    "current_user",
    "get_agent_service",
    "get_conversations",
    "get_induction_service",
    "get_metrics_service",
    "get_replays",
    "get_run_service",
    "get_runs",
    "get_schedule_service",
    "get_trace_service",
    "get_traces",
    "get_usage",
    "get_workflow_service",
    "get_workflows",
    "user_from_token",
]


# --- repositories (low-level seam) -------------------------------------------
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


# --- services (the use-case layer routers depend on) -------------------------
def get_trace_service() -> TraceService:
    return TraceService(container.traces, container.replays)


def get_workflow_service() -> WorkflowService:
    return WorkflowService(container.workflows)


def get_run_service() -> RunService:
    return RunService(container.runs, container.workflows)


def get_induction_service() -> InductionService:
    return InductionService(container.traces, container.workflows, container.usage)


def get_metrics_service() -> MetricsService:
    return MetricsService(container.runs, container.workflows, container.usage)


def get_agent_service() -> AgentService:
    return AgentService(container.conversations, container.workflows,
                        container.runs, container.traces, container.usage)


def get_schedule_service() -> ScheduleService:
    return ScheduleService(container.schedules, container.workflows)
