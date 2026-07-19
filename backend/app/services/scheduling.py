"""Scheduling use-cases + the tick the background scheduler runs.

A schedule fires a workflow every `interval_minutes`, unattended. Crucially it
automates *starting* a run, never *approving* one — a scheduled run still pauses
at its approval gate for a human, exactly like a manual run. `run_due` is the
pure-ish tick (testable by freezing `now` and stubbing the manager); the loop
just calls it on an interval when the scheduler is enabled.
"""
from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from ..engine.manager import RunManager
from ..repos import ScheduleRepo, WorkflowRepo
from .errors import Invalid, NotFound


class ScheduleService:
    def __init__(self, schedules: ScheduleRepo, workflows: WorkflowRepo):
        self.schedules = schedules
        self.workflows = workflows

    def list(self, org_id: str) -> list[dict]:
        return self.schedules.list(org_id)

    def create(self, org_id: str, workflow_id: str, params: dict,
               interval_minutes: int) -> dict:
        if interval_minutes < 1:
            raise Invalid("interval_minutes must be at least 1")
        if not self.workflows.load(workflow_id, org_id):
            raise NotFound("workflow not found")
        return self.schedules.create(org_id, workflow_id, params, interval_minutes)

    def set_enabled(self, sched_id: str, org_id: str, enabled: bool) -> None:
        if not self.schedules.set_enabled(sched_id, org_id, enabled):
            raise NotFound("schedule not found")

    def delete(self, sched_id: str, org_id: str) -> None:
        if not self.schedules.delete(sched_id, org_id):
            raise NotFound("schedule not found")


def run_due(now: datetime, schedules: ScheduleRepo, workflows: WorkflowRepo,
            runs: RunManager) -> int:
    """Start a run for every schedule that's due, each in its owning org, then
    re-arm it. Returns how many runs were started. A missing workflow or a
    launch error advances the schedule anyway (so it can't spin), and never
    breaks the loop."""
    fired = 0
    for sch in schedules.due(now):
        schedules.mark_fired(sch["id"], now)  # advance first: never spin on a bad one
        # Don't pile up: skip if a prior run for this workflow is still live
        # (running / awaiting approval). Otherwise an unapproved gated workflow,
        # fired every tick, would hold every worker-pool slot until a human acts.
        if runs.has_active_run(sch["workflow_id"], sch["org_id"]):
            continue
        spec = workflows.load(sch["workflow_id"], sch["org_id"])
        if spec is None:
            continue
        with contextlib.suppress(Exception):
            runs.start_run(spec, sch["params"], sch["org_id"])
            fired += 1
    return fired


async def scheduler_loop(schedules: ScheduleRepo, workflows: WorkflowRepo,
                         runs: RunManager, tick_seconds: int = 30) -> None:
    """Background loop: fire due schedules every `tick_seconds`. Started from the
    app lifespan only when UNDERSTUDY_SCHEDULER_ENABLED is set."""
    while True:
        with contextlib.suppress(Exception):
            run_due(datetime.now(UTC), schedules, workflows, runs)
        await asyncio.sleep(tick_seconds)
