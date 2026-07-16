"""HTTP API: traces -> workflows -> runs.

Approval model: a run pauses at any step flagged requires_approval and the
run's SSE stream reports awaiting_approval; a human resumes it via
POST /api/runs/{id}/approve (or stops it via /reject). Actor identity is
recorded in the run's audit log.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..db.repositories import TraceRepo, WorkflowRepo
from ..induction.heuristic import induce_heuristic
from ..induction.llm import InductionError, enrich_with_llm
from ..models.trace import Trace
from ..models.workflow import WorkflowSpec
from ..recorder.session import RecordingSession
from ..executor.manager import RunManager


# Request bodies MUST be module-scope: FastAPI/pydantic v2 cannot build a schema
# for a Pydantic model defined inside a function (its qualname has <locals>), and
# silently degrades such a parameter to a query param — which breaks every
# body-taking endpoint. Keep these here.

class InduceBody(BaseModel):
    name: str | None = None
    use_llm: bool = True


class RunBody(BaseModel):
    params: dict[str, str] = {}


class StartRecordingBody(BaseModel):
    name: str = "Untitled demonstration"
    start_url: str | None = None


def build_router(traces: TraceRepo, workflows: WorkflowRepo,
                 runs: RunManager) -> APIRouter:
    r = APIRouter(prefix="/api")

    # ---- traces -----------------------------------------------------------

    @r.get("/traces")
    def list_traces():
        return [{"id": t.id, "name": t.name, "events": len(t.events),
                 "started_at": t.started_at} for t in traces.list()]

    @r.post("/traces")
    def upload_trace(trace: Trace):
        """Accept a trace recorded elsewhere (in-page recorder on the hosted
        mock apps, or the local demonstration browser)."""
        traces.save(trace)
        return {"id": trace.id, "events": len(trace.events)}

    # ---- recording (LOCAL use: spawns a headful demonstration browser) ------
    # A real demonstration happens in a Chromium window the user drives. This
    # path needs a display, so it's for running Understudy on your own machine;
    # the hosted demo records via inject.js served into the mock apps (the same
    # events land through POST /api/traces).

    active_recordings: dict[str, RecordingSession] = {}

    @r.post("/recordings/start")
    async def start_recording(body: StartRecordingBody):
        import os
        base = os.environ.get("UNDERSTUDY_BASE_URL", "http://localhost:8000")
        start_url = body.start_url or f"{base}/portal"
        session = RecordingSession(name=body.name, start_url=start_url)
        try:
            await session.start()          # opens the headful window
        except Exception as e:  # noqa: BLE001 — no display / no browser, etc.
            raise HTTPException(
                503,
                "could not launch the demonstration browser "
                f"({type(e).__name__}: {e}). Local recording needs a display; "
                "on a headless host, record via the in-page recorder and POST "
                "the trace to /api/traces.",
            ) from e
        active_recordings[session.trace.id] = session
        return {"recording_id": session.trace.id,
                "name": session.trace.name, "start_url": start_url}

    @r.get("/recordings")
    def list_recordings():
        return [{"recording_id": rid, "name": s.trace.name,
                 "events": len(s.trace.events)}
                for rid, s in active_recordings.items()]

    @r.post("/recordings/{recording_id}/stop")
    async def stop_recording(recording_id: str):
        session = active_recordings.pop(recording_id, None)
        if session is None:
            raise HTTPException(404, "no active recording with that id")
        trace = await session.stop()       # closes the window, returns the trace
        traces.save(trace)
        return {"trace_id": trace.id, "name": trace.name,
                "events": len(trace.events)}

    @r.get("/traces/{trace_id}")
    def get_trace(trace_id: str):
        t = traces.load(trace_id)
        if not t:
            raise HTTPException(404)
        return t

    # ---- induction ----------------------------------------------------------

    @r.post("/traces/{trace_id}/induce")
    async def induce(trace_id: str, body: InduceBody):
        t = traces.load(trace_id)
        if not t:
            raise HTTPException(404, "trace not found")
        spec = induce_heuristic(t, name=body.name)
        enriched_by = "heuristic"
        if body.use_llm:
            try:
                spec = await enrich_with_llm(t, spec)
                enriched_by = "heuristic+llm"
            except InductionError:
                pass  # keep the deterministic draft
        workflows.save(spec)
        return {"workflow": spec, "induced_by": enriched_by,
                "problems": spec.validate_references()}

    # ---- workflows ----------------------------------------------------------

    @r.get("/workflows")
    def list_workflows():
        return workflows.list()

    @r.get("/workflows/{wf_id}")
    def get_workflow(wf_id: str):
        spec = workflows.load(wf_id)
        if not spec:
            raise HTTPException(404)
        return spec

    @r.put("/workflows/{wf_id}")
    def update_workflow(wf_id: str, spec: WorkflowSpec):
        """The edit surface: the UI PUTs the modified spec back. Version bumps;
        reference problems are returned so the UI can block a broken save."""
        existing = workflows.load(wf_id)
        if not existing:
            raise HTTPException(404)
        problems = spec.validate_references()
        if problems:
            raise HTTPException(422, detail=problems)
        spec.id = wf_id
        spec.version = existing.version + 1
        workflows.save(spec)
        return spec

    # ---- runs ---------------------------------------------------------------

    @r.post("/workflows/{wf_id}/runs")
    async def start_run(wf_id: str, body: RunBody):
        # async so RunManager.start_run's asyncio.create_task has a running loop
        # (a sync endpoint runs in a threadpool with no loop).
        spec = workflows.load(wf_id)
        if not spec:
            raise HTTPException(404)
        missing = [p.key for p in spec.parameters
                   if p.required and p.key not in body.params]
        if missing:
            raise HTTPException(422, detail=f"missing parameters: {missing}")
        run = runs.start_run(spec, body.params)
        return {"run_id": run.id}

    @r.get("/runs")
    def list_runs():
        """Run history — lightweight summaries, newest first."""
        return runs.list()

    @r.get("/runs/{run_id}")
    def get_run(run_id: str):
        run = runs.get(run_id)
        if not run:
            raise HTTPException(404)
        return run

    @r.post("/runs/{run_id}/approve")
    async def approve(run_id: str):
        # async so the asyncio.Event is set on the loop thread and reliably
        # wakes the paused runner (a threadpool set() can miss the waiter).
        if not runs.approve(run_id):
            raise HTTPException(409, "run is not active")
        return {"ok": True}

    @r.post("/runs/{run_id}/reject")
    async def reject(run_id: str):
        if not runs.reject(run_id):
            raise HTTPException(409, "run is not active")
        return {"ok": True}

    @r.get("/runs/{run_id}/events")
    async def run_events(run_id: str, request: Request):
        """SSE stream of the run's audit log, live."""
        queue = runs.queues.get(run_id)
        run = runs.get(run_id)
        if run is None:
            raise HTTPException(404)

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
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                if evt is None:
                    yield f"data: {json.dumps({'kind': 'stream_end'})}\n\n"
                    return
                yield f"data: {evt.model_dump_json()}\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    return r
