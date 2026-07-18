"""Metrics — read-only aggregates for the dashboard, the org-wide audit feed,
and the LLM cost meter."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ...db.repositories import UsageRepo, WorkflowRepo
from ...executor.manager import RunManager
from ..deps import User, current_user, get_runs, get_usage, get_workflows

router = APIRouter(prefix="/api", tags=["metrics"])


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user),
              runs: RunManager = Depends(get_runs),
              workflows: WorkflowRepo = Depends(get_workflows),
              usage: UsageRepo = Depends(get_usage)):
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


@router.get("/audit")
def audit_log(user: User = Depends(current_user),
              runs: RunManager = Depends(get_runs)):
    """Org-wide audit feed — every run event, newest first."""
    return {"events": runs.repo.recent_events(user.org_id)}


@router.get("/usage")
def usage_log(user: User = Depends(current_user),
              usage: UsageRepo = Depends(get_usage)):
    return {"total_usd": round(usage.total(user.org_id), 4),
            "entries": usage.recent(user.org_id)}
