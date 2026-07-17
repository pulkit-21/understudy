"""HTTP API: traces -> workflows -> runs, all org-scoped behind auth.

Approval model: a run pauses at any step flagged requires_approval and the
run's SSE stream reports awaiting_approval; a human resumes it via
POST /api/runs/{id}/approve (or stops it via /reject). Actor identity is
recorded in the run's audit log. Every endpoint requires a bearer token and
only ever touches the caller's org.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import User, current_user, user_from_token
from ..db.repositories import ReplayRepo, TraceRepo, UsageRepo, WorkflowRepo
from ..executor.manager import RunManager
from ..induction.heuristic import induce_heuristic
from ..induction.llm import InductionError, enrich_with_llm
from ..models.trace import Trace
from ..models.workflow import WorkflowSpec, WorkflowStatus
from ..ratelimit import limiter
from ..recorder.session import RecordingSession

# Request bodies MUST be module-scope: FastAPI/pydantic v2 cannot build a schema
# for a Pydantic model defined inside a function (its qualname has <locals>), and
# silently degrades such a parameter to a query param — which breaks every
# body-taking endpoint. Keep these here.


class InduceBody(BaseModel):
    name: str | None = None
    use_llm: bool = True


class RunBody(BaseModel):
    params: dict[str, str] = {}


class BatchBody(BaseModel):
    param_values: list[str]          # e.g. a list of invoice ids
    param_key: str | None = None     # which parameter varies; default = sole one
    defaults: dict[str, str] = {}    # values for the workflow's OTHER parameters


class StatusBody(BaseModel):
    status: WorkflowStatus


class StartRecordingBody(BaseModel):
    name: str = "Untitled demonstration"
    start_url: str | None = None


class ReplayBody(BaseModel):
    events: list  # rrweb events


class ChatMessage(BaseModel):
    role: str      # "user" | "assistant"
    content: str


class ChatBody(BaseModel):
    messages: list[ChatMessage]


def build_router(traces: TraceRepo, workflows: WorkflowRepo,
                 runs: RunManager, usage: UsageRepo,
                 replays: ReplayRepo) -> APIRouter:
    r = APIRouter(prefix="/api")

    # ---- traces -----------------------------------------------------------

    @r.get("/traces")
    def list_traces(user: User = Depends(current_user)):
        return [{"id": t.id, "name": t.name, "events": len(t.events),
                 "started_at": t.started_at} for t in traces.list(user.org_id)]

    @r.post("/traces")
    def upload_trace(trace: Trace, user: User = Depends(current_user)):
        """Accept a trace recorded elsewhere (in-page recorder on the hosted
        mock apps, or the local demonstration browser)."""
        traces.save(trace, user.org_id)
        return {"id": trace.id, "events": len(trace.events)}

    # ---- recording (LOCAL use: spawns a headful demonstration browser) ------

    active_recordings: dict[str, RecordingSession] = {}

    @r.post("/recordings/start")
    @limiter.limit("10/minute")
    async def start_recording(request: Request, body: StartRecordingBody,
                              user: User = Depends(current_user)):
        import os
        base = os.environ.get("UNDERSTUDY_BASE_URL", "http://localhost:8000")
        start_url = body.start_url or f"{base}/portal"
        session = RecordingSession(name=body.name, start_url=start_url)
        try:
            await session.start()          # opens the headful window
        except Exception as e:
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
    def list_recordings(user: User = Depends(current_user)):
        return [{"recording_id": rid, "name": s.trace.name,
                 "events": len(s.trace.events)}
                for rid, s in active_recordings.items()]

    @r.post("/recordings/{recording_id}/stop")
    async def stop_recording(recording_id: str,
                             user: User = Depends(current_user)):
        session = active_recordings.pop(recording_id, None)
        if session is None:
            raise HTTPException(404, "no active recording with that id")
        trace = await session.stop()
        traces.save(trace, user.org_id)
        return {"trace_id": trace.id, "name": trace.name,
                "events": len(trace.events)}

    @r.get("/traces/{trace_id}")
    def get_trace(trace_id: str, user: User = Depends(current_user)):
        t = traces.load(trace_id, user.org_id)
        if not t:
            raise HTTPException(404)
        return {**t.model_dump(mode="json"),
                "has_replay": replays.exists(trace_id, user.org_id)}

    @r.post("/traces/{trace_id}/replay")
    def save_replay(trace_id: str, body: ReplayBody,
                    user: User = Depends(current_user)):
        """Store the rrweb session-replay captured while recording."""
        if not traces.load(trace_id, user.org_id):
            raise HTTPException(404, "trace not found")
        replays.save(trace_id, user.org_id, body.events)
        return {"ok": True, "events": len(body.events)}

    @r.get("/traces/{trace_id}/replay")
    def get_replay(trace_id: str, user: User = Depends(current_user)):
        events = replays.get(trace_id, user.org_id)
        if events is None:
            raise HTTPException(404, "no replay for this trace")
        return {"events": events}

    # ---- induction ----------------------------------------------------------

    @r.post("/traces/{trace_id}/induce")
    @limiter.limit("20/minute")
    async def induce(trace_id: str, body: InduceBody, request: Request,
                     user: User = Depends(current_user)):
        t = traces.load(trace_id, user.org_id)
        if not t:
            raise HTTPException(404, "trace not found")
        spec = induce_heuristic(t, name=body.name)
        enriched_by = "heuristic"
        if body.use_llm:
            try:
                spec = await enrich_with_llm(
                    t, spec,
                    on_usage=lambda u: usage.record(
                        user.org_id, u["model"], u["input_tokens"],
                        u["output_tokens"], u["cost_usd"]),
                )
                enriched_by = "heuristic+llm"
            except InductionError:
                pass  # keep the deterministic draft
        # Deterministic id per trace: re-learning the same demonstration updates
        # the same workflow (bumping its version) instead of piling up duplicates.
        spec.id = f"wf-{trace_id}"
        existing = workflows.load(spec.id, user.org_id)
        if existing:
            spec.version = existing.version + 1
        workflows.save(spec, user.org_id)
        return {"workflow": spec, "induced_by": enriched_by,
                "problems": spec.validate_references()}

    # ---- workflows ----------------------------------------------------------

    @r.get("/workflows")
    def list_workflows(user: User = Depends(current_user),
                       include_archived: bool = False):
        statuses = None if include_archived else ["draft", "published"]
        return workflows.list(user.org_id, statuses=statuses)

    @r.get("/workflows/{wf_id}")
    def get_workflow(wf_id: str, user: User = Depends(current_user)):
        spec = workflows.load(wf_id, user.org_id)
        if not spec:
            raise HTTPException(404)
        return spec

    @r.put("/workflows/{wf_id}")
    def update_workflow(wf_id: str, spec: WorkflowSpec,
                        user: User = Depends(current_user)):
        """The edit surface: the UI PUTs the modified spec back. Version bumps;
        reference problems are returned so the UI can block a broken save."""
        existing = workflows.load(wf_id, user.org_id)
        if not existing:
            raise HTTPException(404)
        problems = spec.validate_references()
        if problems:
            raise HTTPException(422, detail=problems)
        spec.id = wf_id
        spec.version = existing.version + 1
        workflows.save(spec, user.org_id)
        return spec

    @r.post("/workflows/{wf_id}/status")
    def set_status(wf_id: str, body: StatusBody,
                   user: User = Depends(current_user)):
        spec = workflows.load(wf_id, user.org_id)
        if not spec:
            raise HTTPException(404)
        spec.status = body.status
        spec.version += 1
        workflows.save(spec, user.org_id)
        return spec

    @r.post("/workflows/{wf_id}/duplicate")
    def duplicate_workflow(wf_id: str, user: User = Depends(current_user)):
        spec = workflows.load(wf_id, user.org_id)
        if not spec:
            raise HTTPException(404)
        from uuid import uuid4
        spec.id = uuid4().hex[:12]
        spec.name = f"{spec.name} (copy)"
        spec.version = 1
        spec.status = WorkflowStatus.DRAFT
        workflows.save(spec, user.org_id)
        return spec

    @r.delete("/workflows/{wf_id}", status_code=204)
    def delete_workflow(wf_id: str, user: User = Depends(current_user)):
        if not workflows.delete(wf_id, user.org_id):
            raise HTTPException(404)

    @r.get("/workflows/{wf_id}/versions")
    def list_versions(wf_id: str, user: User = Depends(current_user)):
        if not workflows.load(wf_id, user.org_id):
            raise HTTPException(404)
        return workflows.versions(wf_id, user.org_id)

    @r.post("/workflows/{wf_id}/rollback/{version}")
    def rollback(wf_id: str, version: int, user: User = Depends(current_user)):
        current = workflows.load(wf_id, user.org_id)
        old = workflows.version_payload(wf_id, user.org_id, version)
        if not current or not old:
            raise HTTPException(404)
        old.id = wf_id
        old.version = current.version + 1  # rollback is a new forward version
        workflows.save(old, user.org_id)
        return old

    # ---- runs ---------------------------------------------------------------

    def _launch(spec: WorkflowSpec, params: dict[str, str], org_id: str,
                batch_id: str | None = None):
        missing = [p.key for p in spec.parameters
                   if p.required and p.key not in params]
        if missing:
            raise HTTPException(422, detail=f"missing parameters: {missing}")
        return runs.start_run(spec, params, org_id, batch_id=batch_id)

    @r.post("/workflows/{wf_id}/runs")
    @limiter.limit("30/minute")
    async def start_run(wf_id: str, body: RunBody, request: Request,
                        user: User = Depends(current_user)):
        # async so RunManager.start_run's asyncio.create_task has a running loop.
        spec = workflows.load(wf_id, user.org_id)
        if not spec:
            raise HTTPException(404)
        run = _launch(spec, body.params, user.org_id)
        return {"run_id": run.id}

    @r.post("/workflows/{wf_id}/batch")
    @limiter.limit("10/minute")
    async def start_batch(wf_id: str, body: BatchBody, request: Request,
                          user: User = Depends(current_user)):
        """Run a workflow over many inputs at once (e.g. a list of invoice ids).
        Each becomes its own governed run; the bounded worker pool throttles
        how many execute simultaneously."""
        spec = workflows.load(wf_id, user.org_id)
        if not spec:
            raise HTTPException(404)
        key = body.param_key or (spec.parameters[0].key
                                 if spec.parameters else None)
        if key is None:
            raise HTTPException(422, "workflow has no parameter to vary")
        from uuid import uuid4
        batch_id = "batch-" + uuid4().hex[:10]
        run_ids = [_launch(spec, {**body.defaults, key: v}, user.org_id,
                           batch_id=batch_id).id
                   for v in body.param_values]
        return {"batch_id": batch_id, "run_ids": run_ids,
                "count": len(run_ids)}

    @r.get("/runs")
    def list_runs(user: User = Depends(current_user),
                  status: str | None = None, batch_id: str | None = None):
        statuses = [status] if status else None
        return runs.list(user.org_id, statuses=statuses, batch_id=batch_id)

    # ---- dashboard ----------------------------------------------------------

    @r.get("/dashboard")
    def dashboard(user: User = Depends(current_user)):
        org = user.org_id
        counts = runs.repo.counts_by_status(org)
        done = counts.get("completed", 0)
        finished = done + counts.get("failed", 0) + counts.get("rejected", 0)
        # ~90s of manual work saved per successfully auto-posted invoice
        minutes_saved = round(done * 1.5)
        return {
            "workflows": len(workflows.list(org, statuses=["draft", "published"])),
            "run_counts": counts,
            "total_runs": sum(counts.values()),
            "pending_approvals": counts.get("awaiting_approval", 0),
            "success_rate": (done / finished) if finished else None,
            "cost_usd": round(usage.total(org), 4),
            "minutes_saved": minutes_saved,
            "recent": runs.list(org, limit=6),
        }

    @r.get("/usage")
    def usage_log(user: User = Depends(current_user)):
        return {"total_usd": round(usage.total(user.org_id), 4),
                "entries": usage.recent(user.org_id)}

    # ---- conversational agent -----------------------------------------------

    @r.post("/agent/chat")
    @limiter.limit("20/minute")
    async def agent_chat(body: ChatBody, request: Request,
                         user: User = Depends(current_user)):
        from ..agent import AgentTools, run_agent
        from ..induction.llm import MODEL
        tools = AgentTools(workflows, runs, traces, usage, user.org_id)
        result = await run_agent(
            [{"role": m.role, "content": m.content} for m in body.messages], tools)
        if result.get("cost_usd"):
            usage.record(user.org_id, MODEL, result.get("input_tokens", 0),
                         result.get("output_tokens", 0), result["cost_usd"],
                         kind="agent")
        return {"reply": result["reply"], "steps": result["steps"],
                "cards": result.get("cards", [])}

    @r.post("/runs/{run_id}/retry")
    @limiter.limit("30/minute")
    async def retry_run(run_id: str, request: Request,
                        user: User = Depends(current_user)):
        prev = runs.get(run_id, user.org_id)
        if prev is None:
            raise HTTPException(404)
        spec = workflows.load(prev.workflow_id, user.org_id)
        if spec is None:
            raise HTTPException(409, "the workflow no longer exists")
        run = _launch(spec, prev.params, user.org_id)
        return {"run_id": run.id}

    @r.get("/runs/{run_id}")
    def get_run(run_id: str, user: User = Depends(current_user)):
        run = runs.get(run_id, user.org_id)
        if not run:
            raise HTTPException(404)
        return run

    @r.post("/runs/{run_id}/approve")
    async def approve(run_id: str, user: User = Depends(current_user)):
        # async so the asyncio.Event is set on the loop thread and reliably
        # wakes the paused runner (a threadpool set() can miss the waiter).
        if not runs.approve(run_id, user.org_id):
            raise HTTPException(409, "run is not active")
        return {"ok": True}

    @r.post("/runs/{run_id}/reject")
    async def reject(run_id: str, user: User = Depends(current_user)):
        if not runs.reject(run_id, user.org_id):
            raise HTTPException(409, "run is not active")
        return {"ok": True}

    @r.get("/runs/{run_id}/events")
    async def run_events(run_id: str, request: Request, token: str | None = None):
        """SSE stream of the run's audit log, live. The browser EventSource API
        can't set an Authorization header, so the JWT arrives as ?token=."""
        user = user_from_token(token) if token else None
        if user is None:
            raise HTTPException(401, "missing or invalid token")
        run = runs.get(run_id, user.org_id)
        if run is None:
            raise HTTPException(404)
        queue = runs.queues.get(run_id) if runs._owns(run_id, user.org_id) \
            else None

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

    return r
