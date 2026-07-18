"""Trace use-cases: list/fetch demonstrations and their rrweb session replays."""
from __future__ import annotations

from ..db.repositories import ReplayRepo, TraceRepo
from ..models.trace import Trace
from .errors import NotFound


class TraceService:
    def __init__(self, traces: TraceRepo, replays: ReplayRepo):
        self.traces = traces
        self.replays = replays

    def summaries(self, org_id: str) -> list[dict]:
        return [{"id": t.id, "name": t.name, "events": len(t.events),
                 "started_at": t.started_at} for t in self.traces.list(org_id)]

    def save(self, trace: Trace, org_id: str) -> dict:
        self.traces.save(trace, org_id)
        return {"id": trace.id, "events": len(trace.events)}

    def get(self, trace_id: str, org_id: str) -> dict:
        t = self.traces.load(trace_id, org_id)
        if not t:
            raise NotFound("trace not found")
        return {**t.model_dump(mode="json"),
                "has_replay": self.replays.exists(trace_id, org_id)}

    def save_replay(self, trace_id: str, events: list, org_id: str) -> dict:
        if not self.traces.load(trace_id, org_id):
            raise NotFound("trace not found")
        self.replays.save(trace_id, org_id, events)
        return {"ok": True, "events": len(events)}

    def get_replay(self, trace_id: str, org_id: str) -> dict:
        events = self.replays.get(trace_id, org_id)
        if events is None:
            raise NotFound("no replay for this trace")
        return {"events": events}
