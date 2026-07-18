"""Read-only aggregates: dashboard KPIs, the org-wide audit feed, and the cost
meter."""
from __future__ import annotations

from ..engine.manager import RunManager
from ..repos import UsageRepo, WorkflowRepo

# Manual effort saved per successfully auto-posted invoice (~90 seconds).
_MINUTES_SAVED_PER_RUN = 1.5


class MetricsService:
    def __init__(self, runs: RunManager, workflows: WorkflowRepo,
                 usage: UsageRepo):
        self.runs = runs
        self.workflows = workflows
        self.usage = usage

    def dashboard(self, org_id: str) -> dict:
        counts = self.runs.repo.counts_by_status(org_id)
        done = counts.get("completed", 0)
        finished = done + counts.get("failed", 0) + counts.get("rejected", 0)
        return {
            "workflows": len(self.workflows.list(org_id,
                                                 statuses=["draft", "published"])),
            "run_counts": counts,
            "total_runs": sum(counts.values()),
            "pending_approvals": counts.get("awaiting_approval", 0),
            "success_rate": (done / finished) if finished else None,
            "cost_usd": round(self.usage.total(org_id), 4),
            "minutes_saved": round(done * _MINUTES_SAVED_PER_RUN),
            "recent": self.runs.list(org_id, limit=6),
        }

    def audit(self, org_id: str) -> dict:
        return {"events": self.runs.repo.recent_events(org_id)}

    def usage_summary(self, org_id: str) -> dict:
        return {"total_usd": round(self.usage.total(org_id), 4),
                "entries": self.usage.recent(org_id)}
