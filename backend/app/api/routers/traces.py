"""Traces — recorded demonstrations and their rrweb replays. Thin controllers
over TraceService."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...models.trace import Trace
from ...services.traces import TraceService
from ..deps import User, current_user, get_trace_service
from ..schemas import ReplayBody

router = APIRouter(prefix="/api", tags=["traces"])


@router.get("/traces")
def list_traces(user: User = Depends(current_user),
                svc: TraceService = Depends(get_trace_service)):
    return svc.summaries(user.org_id)


@router.post("/traces")
def upload_trace(trace: Trace, user: User = Depends(current_user),
                 svc: TraceService = Depends(get_trace_service)):
    """Accept a trace recorded elsewhere (in-page recorder on the hosted mock
    apps, or the local demonstration browser)."""
    return svc.save(trace, user.org_id)


@router.get("/traces/{trace_id}")
def get_trace(trace_id: str, user: User = Depends(current_user),
              svc: TraceService = Depends(get_trace_service)):
    return svc.get(trace_id, user.org_id)


@router.post("/traces/{trace_id}/replay")
def save_replay(trace_id: str, body: ReplayBody,
                user: User = Depends(current_user),
                svc: TraceService = Depends(get_trace_service)):
    """Store the rrweb session-replay captured while recording."""
    return svc.save_replay(trace_id, body.events, user.org_id)


@router.get("/traces/{trace_id}/replay")
def get_replay(trace_id: str, user: User = Depends(current_user),
               svc: TraceService = Depends(get_trace_service)):
    return svc.get_replay(trace_id, user.org_id)
