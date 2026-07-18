"""Runs — start single/batch runs, the approval gate, retry, and the live SSE
audit stream. Thin controllers over RunService; the SSE endpoint stays here
because it is inherently HTTP (Request lifecycle + StreamingResponse)."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ...engine.manager import RunManager
from ...ratelimit import limiter
from ...services.runs import RunService
from ..deps import (
    User,
    current_user,
    get_run_service,
    get_runs,
    user_from_token,
)
from ..schemas import BatchBody, RunBody

router = APIRouter(prefix="/api", tags=["runs"])


@router.post("/workflows/{wf_id}/runs")
@limiter.limit("30/minute")
async def start_run(wf_id: str, body: RunBody, request: Request,
                    user: User = Depends(current_user),
                    svc: RunService = Depends(get_run_service)):
    # async so RunManager.start_run's asyncio.create_task has a running loop.
    return {"run_id": svc.start(wf_id, body.params, user.org_id).id}


@router.post("/workflows/{wf_id}/batch")
@limiter.limit("10/minute")
async def start_batch(wf_id: str, body: BatchBody, request: Request,
                      user: User = Depends(current_user),
                      svc: RunService = Depends(get_run_service)):
    return svc.start_batch(wf_id, body.param_values, body.param_key,
                           body.defaults, user.org_id)


@router.get("/runs")
def list_runs(user: User = Depends(current_user),
              status: str | None = None, batch_id: str | None = None,
              svc: RunService = Depends(get_run_service)):
    return svc.list(user.org_id, status=status, batch_id=batch_id)


@router.post("/runs/{run_id}/retry")
@limiter.limit("30/minute")
async def retry_run(run_id: str, request: Request,
                    user: User = Depends(current_user),
                    svc: RunService = Depends(get_run_service)):
    return {"run_id": svc.retry(run_id, user.org_id).id}


@router.get("/runs/{run_id}")
def get_run(run_id: str, user: User = Depends(current_user),
            svc: RunService = Depends(get_run_service)):
    return svc.get(run_id, user.org_id)


@router.post("/runs/{run_id}/approve")
async def approve(run_id: str, user: User = Depends(current_user),
                  svc: RunService = Depends(get_run_service)):
    # async so the asyncio.Event is set on the loop thread and reliably wakes the
    # paused runner (a threadpool set() can miss the waiter).
    svc.approve(run_id, user.org_id)
    return {"ok": True}


@router.post("/runs/{run_id}/reject")
async def reject(run_id: str, user: User = Depends(current_user),
                 svc: RunService = Depends(get_run_service)):
    svc.reject(run_id, user.org_id)
    return {"ok": True}


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, token: str | None = None,
                     runs: RunManager = Depends(get_runs)):
    """SSE stream of the run's audit log, live. The browser EventSource API
    can't set an Authorization header, so the JWT arrives as ?token=."""
    user = user_from_token(token) if token else None
    if user is None:
        raise HTTPException(401, "missing or invalid token")
    run = runs.get(run_id, user.org_id)
    if run is None:
        raise HTTPException(404)
    queue = runs.queues.get(run_id) if runs._owns(run_id, user.org_id) else None

    async def stream():
        for evt in run.events:  # replay history for late subscribers
            yield f"data: {evt.model_dump_json()}\n\n"
        if queue is None:
            return
        while True:
            if await request.is_disconnected():
                return
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=15)
            except TimeoutError:
                yield ": keepalive\n\n"
                continue
            if evt is None:
                yield f"data: {json.dumps({'kind': 'stream_end'})}\n\n"
                return
            yield f"data: {evt.model_dump_json()}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")
