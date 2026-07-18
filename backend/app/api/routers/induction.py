"""Induction — learn a WorkflowSpec from a recorded trace. Thin controller over
InductionService."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ...ratelimit import limiter
from ...services.induction import InductionService
from ..deps import User, current_user, get_induction_service
from ..schemas import InduceBody, InduceMultiBody

router = APIRouter(prefix="/api", tags=["induction"])


@router.post("/traces/{trace_id}/induce")
@limiter.limit("20/minute")
async def induce(trace_id: str, body: InduceBody, request: Request,
                 user: User = Depends(current_user),
                 svc: InductionService = Depends(get_induction_service)):
    return await svc.induce(trace_id, user.org_id,
                            use_llm=body.use_llm, name=body.name)


@router.post("/induce/multi")
@limiter.limit("20/minute")
async def induce_multi(body: InduceMultiBody, request: Request,
                       user: User = Depends(current_user),
                       svc: InductionService = Depends(get_induction_service)):
    """Learn from 2+ recordings of the same task — the diff between them tells
    parameters (values that vary) from literals (values that stay constant)."""
    return await svc.induce_multi(body.trace_ids, user.org_id,
                                  use_llm=body.use_llm, name=body.name)
