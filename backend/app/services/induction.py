"""Induction use-case: turn a recorded trace into a WorkflowSpec. The heuristic
pass is deterministic and always runs; the LLM legibility pass is best-effort."""
from __future__ import annotations

from ..induction.heuristic import induce_heuristic
from ..induction.llm import InductionError, enrich_with_llm
from ..repos import TraceRepo, UsageRepo, WorkflowRepo
from .errors import Invalid, NotFound


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

    async def induce_multi(self, trace_ids: list[str], org_id: str, *,
                           use_llm: bool = True, name: str | None = None) -> dict:
        """Learn from 2+ recordings of the same task, using what varies between
        them to tell parameters from literals (see induction.multitrace)."""
        from ..induction.multitrace import induce_from_traces

        if len(trace_ids) < 2:
            raise Invalid("multi-trace induction needs at least two recordings")
        traces = []
        for tid in trace_ids:
            t = self.traces.load(tid, org_id)
            if not t:
                raise NotFound(f"trace not found: {tid}")
            traces.append(t)

        spec, report = induce_from_traces(traces, name=name)
        spec.source_trace_ids = trace_ids
        induced_by = "multi-trace"
        if use_llm:
            try:
                spec = await enrich_with_llm(
                    traces[0], spec,
                    on_usage=lambda u: self.usage.record(
                        org_id, u["model"], u["input_tokens"],
                        u["output_tokens"], u["cost_usd"]),
                )
                spec.source_trace_ids = trace_ids  # enrich carries id/version, re-pin
                induced_by = "multi-trace+llm"
            except InductionError:
                pass

        spec.id = f"wf-{trace_ids[0]}"
        existing = self.workflows.load(spec.id, org_id)
        if existing:
            spec.version = existing.version + 1
        self.workflows.save(spec, org_id)
        return {"workflow": spec, "induced_by": induced_by,
                "problems": spec.validate_references(),
                "parameter_report": report.model_dump()}
