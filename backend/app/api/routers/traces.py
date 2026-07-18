"""Traces — recorded demonstrations, and the rrweb session replays captured
alongside them. All org-scoped behind auth."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ...db.repositories import ReplayRepo, TraceRepo
from ...models.trace import Trace
from ..deps import User, current_user, get_replays, get_traces
from ..schemas import ReplayBody

router = APIRouter(prefix="/api", tags=["traces"])


@router.get("/traces")
def list_traces(user: User = Depends(current_user),
                traces: TraceRepo = Depends(get_traces)):
    return [{"id": t.id, "name": t.name, "events": len(t.events),
             "started_at": t.started_at} for t in traces.list(user.org_id)]


@router.post("/traces")
def upload_trace(trace: Trace, user: User = Depends(current_user),
                 traces: TraceRepo = Depends(get_traces)):
    """Accept a trace recorded elsewhere (in-page recorder on the hosted mock
    apps, or the local demonstration browser)."""
    traces.save(trace, user.org_id)
    return {"id": trace.id, "events": len(trace.events)}


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str, user: User = Depends(current_user),
              traces: TraceRepo = Depends(get_traces),
              replays: ReplayRepo = Depends(get_replays)):
    t = traces.load(trace_id, user.org_id)
    if not t:
        raise HTTPException(404)
    return {**t.model_dump(mode="json"),
            "has_replay": replays.exists(trace_id, user.org_id)}


@router.post("/traces/{trace_id}/replay")
def save_replay(trace_id: str, body: ReplayBody,
                user: User = Depends(current_user),
                traces: TraceRepo = Depends(get_traces),
                replays: ReplayRepo = Depends(get_replays)):
    """Store the rrweb session-replay captured while recording."""
    if not traces.load(trace_id, user.org_id):
        raise HTTPException(404, "trace not found")
    replays.save(trace_id, user.org_id, body.events)
    return {"ok": True, "events": len(body.events)}


@router.get("/traces/{trace_id}/replay")
def get_replay(trace_id: str, user: User = Depends(current_user),
               replays: ReplayRepo = Depends(get_replays)):
    events = replays.get(trace_id, user.org_id)
    if events is None:
        raise HTTPException(404, "no replay for this trace")
    return {"events": events}
