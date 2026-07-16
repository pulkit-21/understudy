"""Repositories: the only layer that touches the ORM.

Each repo maps between a domain Pydantic model and its row, exposing the same
small interface the old file-stores had (save / load / list) so nothing above
had to change when persistence moved into a database. Every call uses a
short-lived session (open, do one thing, commit, close) — simplest correct unit
of work at this scale.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..executor.runner import Run
from ..models.trace import Trace
from ..models.workflow import WorkflowSpec
from .models import RunRow, TraceRow, WorkflowRow

SessionFactory = Callable[[], Session]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TraceRepo:
    def __init__(self, session_factory: SessionFactory):
        self._sf = session_factory

    def save(self, trace: Trace) -> None:
        with self._sf() as s:
            row = s.get(TraceRow, trace.id) or TraceRow(id=trace.id)
            row.name = trace.name
            row.started_at = trace.started_at
            row.event_count = len(trace.events)
            row.payload = trace.model_dump(mode="json")
            s.add(row)
            s.commit()

    def load(self, trace_id: str) -> Optional[Trace]:
        with self._sf() as s:
            row = s.get(TraceRow, trace_id)
            return Trace.model_validate(row.payload) if row else None

    def list(self) -> list[Trace]:
        with self._sf() as s:
            rows = s.execute(
                select(TraceRow).order_by(TraceRow.started_at)
            ).scalars().all()
            return [Trace.model_validate(r.payload) for r in rows]


class WorkflowRepo:
    def __init__(self, session_factory: SessionFactory):
        self._sf = session_factory

    def save(self, spec: WorkflowSpec) -> None:
        with self._sf() as s:
            row = s.get(WorkflowRow, spec.id)
            now = _now()
            if row is None:
                row = WorkflowRow(id=spec.id, created_at=now)
            row.name = spec.name
            row.version = spec.version
            row.param_keys = [p.key for p in spec.parameters]
            row.updated_at = now
            row.payload = spec.model_dump(mode="json")
            s.add(row)
            s.commit()

    def load(self, wf_id: str) -> Optional[WorkflowSpec]:
        with self._sf() as s:
            row = s.get(WorkflowRow, wf_id)
            return WorkflowSpec.model_validate(row.payload) if row else None

    def list(self) -> list[WorkflowSpec]:
        with self._sf() as s:
            rows = s.execute(
                select(WorkflowRow).order_by(WorkflowRow.updated_at.desc())
            ).scalars().all()
            return [WorkflowSpec.model_validate(r.payload) for r in rows]


class RunRepo:
    def __init__(self, session_factory: SessionFactory):
        self._sf = session_factory

    def save(self, run: Run) -> None:
        with self._sf() as s:
            row = s.get(RunRow, run.id)
            now = _now()
            if row is None:
                row = RunRow(id=run.id, created_at=now)
            row.workflow_id = run.workflow_id
            row.status = run.status.value
            row.params = run.params
            row.updated_at = now
            row.payload = run.model_dump(mode="json")
            s.add(row)
            s.commit()

    def get(self, run_id: str) -> Optional[Run]:
        with self._sf() as s:
            row = s.get(RunRow, run_id)
            return Run.model_validate(row.payload) if row else None

    def list(self, limit: int = 100) -> list[dict]:
        """Lightweight summaries for the runs history — no need to hydrate the
        full event log just to render a list."""
        with self._sf() as s:
            rows = s.execute(
                select(RunRow).order_by(RunRow.created_at.desc()).limit(limit)
            ).scalars().all()
            return [
                {"id": r.id, "workflow_id": r.workflow_id, "status": r.status,
                 "created_at": r.created_at, "params": r.params,
                 "steps": len(r.payload.get("events", []))}
                for r in rows
            ]
