"""Repositories: the only layer that touches the ORM.

Every method is **org-scoped** — it takes an `org_id` and filters/stamps by it,
so one tenant can never read or overwrite another's data. Each call uses a
short-lived session (open, do one thing, commit, close).
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..executor.runner import Run
from ..models.trace import Trace
from ..models.workflow import WorkflowSpec
from .models import (
    ConversationRow,
    ReplayRow,
    RunRow,
    TraceRow,
    UsageRow,
    WorkflowRow,
    WorkflowVersionRow,
)

SessionFactory = Callable[[], Session]


def _now() -> datetime:
    return datetime.now(UTC)


class TraceRepo:
    def __init__(self, session_factory: SessionFactory):
        self._sf = session_factory

    def save(self, trace: Trace, org_id: str) -> None:
        with self._sf() as s:
            row = s.get(TraceRow, trace.id)
            if row is not None and row.org_id != org_id:
                raise PermissionError("trace belongs to another org")
            row = row or TraceRow(id=trace.id, org_id=org_id)
            row.org_id = org_id
            row.name = trace.name
            row.started_at = trace.started_at
            row.event_count = len(trace.events)
            row.payload = trace.model_dump(mode="json")
            s.add(row)
            s.commit()

    def load(self, trace_id: str, org_id: str) -> Trace | None:
        with self._sf() as s:
            row = s.get(TraceRow, trace_id)
            if row is None or row.org_id != org_id:
                return None
            return Trace.model_validate(row.payload)

    def list(self, org_id: str) -> list[Trace]:
        with self._sf() as s:
            rows = s.execute(
                select(TraceRow).where(TraceRow.org_id == org_id)
                .order_by(TraceRow.started_at)
            ).scalars().all()
            return [Trace.model_validate(r.payload) for r in rows]


class WorkflowRepo:
    def __init__(self, session_factory: SessionFactory):
        self._sf = session_factory

    def save(self, spec: WorkflowSpec, org_id: str) -> None:
        with self._sf() as s:
            row = s.get(WorkflowRow, spec.id)
            if row is not None and row.org_id != org_id:
                raise PermissionError("workflow belongs to another org")
            now = _now()
            if row is None:
                row = WorkflowRow(id=spec.id, org_id=org_id, created_at=now)
            row.org_id = org_id
            row.name = spec.name
            row.version = spec.version
            row.status = spec.status.value
            row.tags = list(spec.tags)
            row.param_keys = [p.key for p in spec.parameters]
            row.updated_at = now
            row.payload = spec.model_dump(mode="json")
            s.add(row)
            # immutable version snapshot for history / rollback
            s.add(WorkflowVersionRow(
                workflow_id=spec.id, org_id=org_id, version=spec.version,
                created_at=now, payload=spec.model_dump(mode="json")))
            s.commit()

    def load(self, wf_id: str, org_id: str) -> WorkflowSpec | None:
        with self._sf() as s:
            row = s.get(WorkflowRow, wf_id)
            if row is None or row.org_id != org_id:
                return None
            return WorkflowSpec.model_validate(row.payload)

    def list(self, org_id: str,
             statuses: list[str] | None = None) -> list[WorkflowSpec]:
        with self._sf() as s:
            q = select(WorkflowRow).where(WorkflowRow.org_id == org_id)
            if statuses is not None:
                q = q.where(WorkflowRow.status.in_(statuses))
            rows = s.execute(q.order_by(WorkflowRow.updated_at.desc())) \
                .scalars().all()
            return [WorkflowSpec.model_validate(r.payload) for r in rows]

    def delete(self, wf_id: str, org_id: str) -> bool:
        with self._sf() as s:
            row = s.get(WorkflowRow, wf_id)
            if row is None or row.org_id != org_id:
                return False
            s.delete(row)
            s.commit()
            return True

    # Sequence, not list[...]: the `list` method above shadows the builtin in
    # annotations that follow it within this class.
    def versions(self, wf_id: str, org_id: str) -> Sequence[dict]:
        with self._sf() as s:
            rows = s.execute(
                select(WorkflowVersionRow)
                .where(WorkflowVersionRow.workflow_id == wf_id,
                       WorkflowVersionRow.org_id == org_id)
                .order_by(WorkflowVersionRow.version.desc())
            ).scalars().all()
            return [{"version": r.version, "created_at": r.created_at,
                     "name": r.payload.get("name", ""),
                     "steps": len(r.payload.get("steps", []))} for r in rows]

    def version_payload(self, wf_id: str, org_id: str,
                        version: int) -> WorkflowSpec | None:
        with self._sf() as s:
            row = s.execute(
                select(WorkflowVersionRow).where(
                    WorkflowVersionRow.workflow_id == wf_id,
                    WorkflowVersionRow.org_id == org_id,
                    WorkflowVersionRow.version == version)
            ).scalar_one_or_none()
            return WorkflowSpec.model_validate(row.payload) if row else None


class RunRepo:
    def __init__(self, session_factory: SessionFactory):
        self._sf = session_factory

    def save(self, run: Run, org_id: str, batch_id: str | None = None,
             cost_usd: float = 0.0) -> None:
        with self._sf() as s:
            row = s.get(RunRow, run.id)
            if row is not None and row.org_id != org_id:
                raise PermissionError("run belongs to another org")
            now = _now()
            if row is None:
                row = RunRow(id=run.id, org_id=org_id, created_at=now,
                             batch_id=batch_id)
            row.org_id = org_id
            row.workflow_id = run.workflow_id
            row.status = run.status.value
            row.params = run.params
            row.cost_usd = cost_usd
            row.updated_at = now
            row.payload = run.model_dump(mode="json")
            s.add(row)
            s.commit()

    def get(self, run_id: str, org_id: str) -> Run | None:
        with self._sf() as s:
            row = s.get(RunRow, run_id)
            if row is None or row.org_id != org_id:
                return None
            return Run.model_validate(row.payload)

    def list(self, org_id: str, limit: int = 100,
             statuses: list[str] | None = None,
             batch_id: str | None = None) -> list[dict]:
        with self._sf() as s:
            q = select(RunRow).where(RunRow.org_id == org_id)
            if statuses is not None:
                q = q.where(RunRow.status.in_(statuses))
            if batch_id is not None:
                q = q.where(RunRow.batch_id == batch_id)
            rows = s.execute(
                q.order_by(RunRow.created_at.desc()).limit(limit)
            ).scalars().all()
            return [self._summary(r) for r in rows]

    def counts_by_status(self, org_id: str) -> dict[str, int]:
        from sqlalchemy import func
        with self._sf() as s:
            rows = s.execute(
                select(RunRow.status, func.count())
                .where(RunRow.org_id == org_id).group_by(RunRow.status)
            ).all()
            return {status: n for status, n in rows}

    def total_cost(self, org_id: str) -> float:
        from sqlalchemy import func
        with self._sf() as s:
            v = s.execute(
                select(func.coalesce(func.sum(RunRow.cost_usd), 0.0))
                .where(RunRow.org_id == org_id)
            ).scalar_one()
            return float(v)

    @staticmethod
    def _summary(r: RunRow) -> dict:
        return {"id": r.id, "workflow_id": r.workflow_id, "status": r.status,
                "created_at": r.created_at, "params": r.params,
                "batch_id": r.batch_id, "cost_usd": r.cost_usd,
                "steps": len(r.payload.get("events", []))}


class UsageRepo:
    def __init__(self, session_factory: SessionFactory):
        self._sf = session_factory

    def record(self, org_id: str, model: str, input_tokens: int,
               output_tokens: int, cost: float, kind: str = "induction") -> None:
        with self._sf() as s:
            s.add(UsageRow(org_id=org_id, kind=kind, model=model,
                           input_tokens=input_tokens, output_tokens=output_tokens,
                           cost_usd=cost, created_at=_now()))
            s.commit()

    def total(self, org_id: str) -> float:
        from sqlalchemy import func
        with self._sf() as s:
            v = s.execute(
                select(func.coalesce(func.sum(UsageRow.cost_usd), 0.0))
                .where(UsageRow.org_id == org_id)
            ).scalar_one()
            return float(v)

    def recent(self, org_id: str, limit: int = 50) -> list[dict]:
        with self._sf() as s:
            rows = s.execute(
                select(UsageRow).where(UsageRow.org_id == org_id)
                .order_by(UsageRow.created_at.desc()).limit(limit)
            ).scalars().all()
            return [{"kind": r.kind, "model": r.model,
                     "input_tokens": r.input_tokens,
                     "output_tokens": r.output_tokens,
                     "cost_usd": r.cost_usd, "created_at": r.created_at}
                    for r in rows]


class ReplayRepo:
    def __init__(self, session_factory: SessionFactory):
        self._sf = session_factory

    def save(self, trace_id: str, org_id: str, events: list) -> None:
        with self._sf() as s:
            row = s.get(ReplayRow, trace_id)
            if row is None:
                row = ReplayRow(trace_id=trace_id, org_id=org_id, created_at=_now())
            row.org_id = org_id
            row.events = events
            s.add(row)
            s.commit()

    def get(self, trace_id: str, org_id: str) -> list | None:
        with self._sf() as s:
            row = s.get(ReplayRow, trace_id)
            if row is None or row.org_id != org_id:
                return None
            return row.events

    def exists(self, trace_id: str, org_id: str) -> bool:
        with self._sf() as s:
            row = s.get(ReplayRow, trace_id)
            return row is not None and row.org_id == org_id


class ConversationRepo:
    def __init__(self, session_factory: SessionFactory):
        self._sf = session_factory

    def create(self, org_id: str, title: str) -> ConversationRow:
        from uuid import uuid4
        with self._sf() as s:
            now = _now()
            row = ConversationRow(id="conv-" + uuid4().hex[:10], org_id=org_id,
                                  title=title[:80] or "New chat", created_at=now,
                                  updated_at=now, messages=[])
            s.add(row)
            s.commit()
            s.refresh(row)
            s.expunge(row)
            return row

    def get(self, conv_id: str, org_id: str) -> ConversationRow | None:
        with self._sf() as s:
            row = s.get(ConversationRow, conv_id)
            if row is None or row.org_id != org_id:
                return None
            s.expunge(row)
            return row

    def save_messages(self, conv_id: str, org_id: str, messages: list) -> None:
        with self._sf() as s:
            row = s.get(ConversationRow, conv_id)
            if row is None or row.org_id != org_id:
                return
            row.messages = messages
            row.updated_at = _now()
            s.add(row)
            s.commit()

    def list(self, org_id: str, limit: int = 50) -> list[dict]:
        with self._sf() as s:
            rows = s.execute(
                select(ConversationRow).where(ConversationRow.org_id == org_id)
                .order_by(ConversationRow.updated_at.desc()).limit(limit)
            ).scalars().all()
            return [{"id": r.id, "title": r.title, "updated_at": r.updated_at,
                     "messages": len(r.messages)} for r in rows]

    def delete(self, conv_id: str, org_id: str) -> bool:
        with self._sf() as s:
            row = s.get(ConversationRow, conv_id)
            if row is None or row.org_id != org_id:
                return False
            s.delete(row)
            s.commit()
            return True
