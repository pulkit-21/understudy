"""Runs — starting single/batch runs, the approval gate (approve/reject),
retry, and the live SSE audit stream. Starting a run never bypasses a gate; a
run pauses at any step flagged requires_approval and only a human resumes it."""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from ...executor.manager import RunManager
from ...models.workflow import WorkflowSpec
from ...ratelimit import limiter
from ..deps import (
    User,
    current_user,
    get_runs,
    get_workflows,
    user_from_token,
)
from ..schemas import BatchBody, RunBody

router = APIRouter(prefix="/api", tags=["runs"])


def _launch(runs: RunManager, spec: WorkflowSpec, params: dict[str, str],
            org_id: str, batch_id: str | None = None):
    missing = [p.key for p in spec.parameters
               if p.required and p.key not in params]
    if missing:
        raise HTTPException(422, detail=f"missing parameters: {missing}")
    return runs.start_run(spec, params, org_id, batch_id=batch_id)


@router.post("/workflows/{wf_id}/runs")
@limiter.limit("30/minute")
async def start_run(wf_id: str, body: RunBody, request: Request,
                    user: User = Depends(current_user),
                    runs: RunManager = Depends(get_runs),
                    workflows=Depends(get_workflows)):
    # async so RunManager.start_run's asyncio.create_task has a running loop.
    spec = workflows.load(wf_id, user.org_id)
    if not spec:
        raise HTTPException(404)
    run = _launch(runs, spec, body.params, user.org_id)
    return {"run_id": run.id}


@router.post("/workflows/{wf_id}/batch")
@limiter.limit("10/minute")
async def start_batch(wf_id: str, body: BatchBody, request: Request,
                      user: User = Depends(current_user),
                      runs: RunManager = Depends(get_runs),
                      workflows=Depends(get_workflows)):
    """Run a workflow over many inputs at once (e.g. a list of invoice ids).
    Each becomes its own governed run; the bounded worker pool throttles how
    many execute simultaneously."""
    spec = workflows.load(wf_id, user.org_id)
    if not spec:
        raise HTTPException(404)
    key = body.param_key or (spec.parameters[0].key
                             if spec.parameters else None)
    if key is None:
        raise HTTPException(422, "workflow has no parameter to vary")
    batch_id = "batch-" + uuid4().hex[:10]
    run_ids = [_launch(runs, spec, {**body.defaults, key: v}, user.org_id,
                       batch_id=batch_id).id
               for v in body.param_values]
    return {"batch_id": batch_id, "run_ids": run_ids, "count": len(run_ids)}


@router.get("/runs")
def list_runs(user: User = Depends(current_user),
              status: str | None = None, batch_id: str | None = None,
              runs: RunManager = Depends(get_runs)):
    statuses = [status] if status else None
    return runs.list(user.org_id, statuses=statuses, batch_id=batch_id)


@router.post("/runs/{run_id}/retry")
@limiter.limit("30/minute")
async def retry_run(run_id: str, request: Request,
                    user: User = Depends(current_user),
                    runs: RunManager = Depends(get_runs),
                    workflows=Depends(get_workflows)):
    prev = runs.get(run_id, user.org_id)
    if prev is None:
        raise HTTPException(404)
    spec = workflows.load(prev.workflow_id, user.org_id)
    if spec is None:
        raise HTTPException(409, "the workflow no longer exists")
    run = _launch(runs, spec, prev.params, user.org_id)
    return {"run_id": run.id}


@router.get("/runs/{run_id}")
def get_run(run_id: str, user: User = Depends(current_user),
            runs: RunManager = Depends(get_runs)):
    run = runs.get(run_id, user.org_id)
    if not run:
        raise HTTPException(404)
    return run


@router.post("/runs/{run_id}/approve")
async def approve(run_id: str, user: User = Depends(current_user),
                  runs: RunManager = Depends(get_runs)):
    # async so the asyncio.Event is set on the loop thread and reliably wakes the
    # paused runner (a threadpool set() can miss the waiter).
    if not runs.approve(run_id, user.org_id):
        raise HTTPException(409, "run is not active")
    return {"ok": True}


@router.post("/runs/{run_id}/reject")
async def reject(run_id: str, user: User = Depends(current_user),
                 runs: RunManager = Depends(get_runs)):
    if not runs.reject(run_id, user.org_id):
        raise HTTPException(409, "run is not active")
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
