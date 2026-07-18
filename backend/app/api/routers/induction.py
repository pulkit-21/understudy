"""Induction — learn a WorkflowSpec from a recorded trace. The heuristic pass is
deterministic and always runs; the LLM legibility pass is best-effort and never
load-bearing."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ...db.repositories import TraceRepo, UsageRepo, WorkflowRepo
from ...induction.heuristic import induce_heuristic
from ...induction.llm import InductionError, enrich_with_llm
from ...ratelimit import limiter
from ..deps import User, current_user, get_traces, get_usage, get_workflows
from ..schemas import InduceBody

router = APIRouter(prefix="/api", tags=["induction"])


@router.post("/traces/{trace_id}/induce")
@limiter.limit("20/minute")
async def induce(trace_id: str, body: InduceBody, request: Request,
                 user: User = Depends(current_user),
                 traces: TraceRepo = Depends(get_traces),
                 workflows: WorkflowRepo = Depends(get_workflows),
                 usage: UsageRepo = Depends(get_usage)):
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
    # Deterministic id per trace: re-learning the same demonstration updates the
    # same workflow (bumping its version) instead of piling up duplicates.
    spec.id = f"wf-{trace_id}"
    existing = workflows.load(spec.id, user.org_id)
    if existing:
        spec.version = existing.version + 1
    workflows.save(spec, user.org_id)
    return {"workflow": spec, "induced_by": enriched_by,
            "problems": spec.validate_references()}
