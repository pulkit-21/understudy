"""HTTP API: traces -> workflows -> runs.

Approval model: a run pauses at any step flagged requires_approval and the
run's SSE stream reports awaiting_approval; a human resumes it via
POST /api/runs/{id}/approve (or stops it via /reject). Actor identity is
recorded in the run's audit log.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..induction.heuristic import induce_heuristic
from ..induction.llm import InductionError, enrich_with_llm
from ..models.trace import Trace
from ..models.workflow import WorkflowSpec
from ..recorder.session import TraceStore
from ..executor.manager import RunManager


class WorkflowStore:
    """Filesystem-backed workflow storage (JSON: diffable, versionable)."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, spec: WorkflowSpec) -> None:
        (self.root / f"{spec.id}.json").write_text(
            spec.model_dump_json(indent=2))

    def load(self, wf_id: str) -> WorkflowSpec | None:
        p = self.root / f"{wf_id}.json"
        return WorkflowSpec.model_validate_json(p.read_text()) if p.exists() else None

    def list(self) -> list[WorkflowSpec]:
        return [WorkflowSpec.model_validate_json(p.read_text())
                for p in sorted(self.root.glob("*.json"))]


def build_router(traces: TraceStore, workflows: WorkflowStore,
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

    @r.get("/traces/{trace_id}")
    def get_trace(trace_id: str):
        t = traces.load(trace_id)
        if not t:
            raise HTTPException(404)
        return t

    # ---- induction ----------------------------------------------------------

    class InduceBody(BaseModel):
        name: str | None = None
        use_llm: bool = True

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

    class RunBody(BaseModel):
        params: dict[str, str] = {}

    @r.post("/workflows/{wf_id}/runs")
    def start_run(wf_id: str, body: RunBody):
        spec = workflows.load(wf_id)
        if not spec:
            raise HTTPException(404)
        missing = [p.key for p in spec.parameters
                   if p.required and p.key not in body.params]
        if missing:
            raise HTTPException(422, detail=f"missing parameters: {missing}")
        run = runs.start_run(spec, body.params)
        return {"run_id": run.id}

    @r.get("/runs/{run_id}")
    def get_run(run_id: str):
        run = runs.get(run_id)
        if not run:
            raise HTTPException(404)
        return run

    @r.post("/runs/{run_id}/approve")
    def approve(run_id: str):
        if not runs.approve(run_id):
            raise HTTPException(409, "run is not active")
        return {"ok": True}

    @r.post("/runs/{run_id}/reject")
    def reject(run_id: str):
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
