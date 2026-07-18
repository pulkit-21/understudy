"""Induction use-case: turn a recorded trace into a WorkflowSpec. The heuristic
pass is deterministic and always runs; the LLM legibility pass is best-effort."""
from __future__ import annotations

from ..induction.heuristic import induce_heuristic
from ..induction.llm import InductionError, enrich_with_llm
from ..repos import TraceRepo, UsageRepo, WorkflowRepo
from .errors import NotFound


class InductionService:
    def __init__(self, traces: TraceRepo, workflows: WorkflowRepo,
                 usage: UsageRepo):
        self.traces = traces
        self.workflows = workflows
        self.usage = usage

    async def induce(self, trace_id: str, org_id: str, *, use_llm: bool = True,
                     name: str | None = None) -> dict:
        trace = self.traces.load(trace_id, org_id)
        if not trace:
            raise NotFound("trace not found")

        spec = induce_heuristic(trace, name=name)
        induced_by = "heuristic"
        if use_llm:
            try:
                spec = await enrich_with_llm(
                    trace, spec,
                    on_usage=lambda u: self.usage.record(
                        org_id, u["model"], u["input_tokens"],
                        u["output_tokens"], u["cost_usd"]),
                )
                induced_by = "heuristic+llm"
            except InductionError:
                pass  # keep the deterministic draft — the LLM is never load-bearing

        # Deterministic id per trace: re-learning the same demonstration updates
        # the same workflow (bumping its version) rather than piling up copies.
        spec.id = f"wf-{trace_id}"
        existing = self.workflows.load(spec.id, org_id)
        if existing:
            spec.version = existing.version + 1
        self.workflows.save(spec, org_id)
        return {"workflow": spec, "induced_by": induced_by,
                "problems": spec.validate_references()}
