"""Multi-trace parameter discovery.

A single recording can't distinguish a constant from a parameter: when the demo
typed "Net 30" into a field, is that *always* Net 30, or just this vendor's
terms? The single-trace heuristic has to guess (typed-but-not-read-off-a-page ->
parameter). Given TWO recordings of the SAME task with different data, we can
*know*: a value that changed between recordings is a parameter; one that stayed
the same is a literal.

This refines the single-trace draft as a post-process:
  * a field that VARIES but the heuristic hard-coded  -> promote to a parameter,
  * a field that is CONSTANT across every recording   -> demote to a literal.
Values read live off a page (`{{extract.*}}`) are orthogonal and left untouched.
Alignment is positional over the fill/select steps; if the recordings don't line
up (different structure), we can't safely diff and fall back to the single-trace
draft.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from ..domain.trace import EventType, Trace
from ..domain.workflow import ActionType, WorkflowParameter, WorkflowSpec
from .heuristic import _slug, induce_heuristic

_INPUT_EVENTS = (EventType.FILL, EventType.SELECT)
_INPUT_ACTIONS = (ActionType.FILL, ActionType.SELECT)
_PARAM_REF = re.compile(r"^\{\{\s*([a-z0-9_]+)\s*\}\}$", re.I)  # {{key}}, not {{extract.x}}


class FieldObservation(BaseModel):
    """One input field's values across the recordings, and whether they vary."""

    label: str
    values: list[str]
    varies: bool
    role: str  # "parameter" | "literal"


class ParameterReport(BaseModel):
    aligned: bool                       # could the recordings be diffed?
    trace_count: int
    fields: list[FieldObservation]

    @property
    def parameters(self) -> list[str]:
        return [f.label for f in self.fields if f.varies]


def _input_values(trace: Trace) -> list[str]:
    return [e.value or "" for e in trace.events if e.type in _INPUT_EVENTS]


def _input_labels(trace: Trace) -> list[str]:
    out = []
    for e in trace.events:
        if e.type in _INPUT_EVENTS:
            t = e.target
            out.append((t.name if t else None) or (t.testid if t else None) or "field")
    return out


def diff_input_fields(traces: list[Trace]) -> ParameterReport:
    """Align the fill/select steps across recordings and flag which vary."""
    seqs = [_input_values(t) for t in traces]
    aligned = len(traces) >= 2 and len({len(s) for s in seqs}) == 1
    if not aligned:
        return ParameterReport(aligned=False, trace_count=len(traces), fields=[])
    labels = _input_labels(traces[0])
    fields: list[FieldObservation] = []
    for i, label in enumerate(labels):
        values = [seq[i] for seq in seqs]
        varies = len(set(values)) > 1
        fields.append(FieldObservation(
            label=label, values=values, varies=varies,
            role="parameter" if varies else "literal"))
    return ParameterReport(aligned=True, trace_count=len(traces), fields=fields)


def _rebuild_parameters(spec: WorkflowSpec,
                        prior: dict[str, WorkflowParameter]) -> None:
    """Set spec.parameters to exactly the {{key}} refs still used by any step,
    preserving prior descriptions/examples where we have them."""
    used: list[str] = []
    for step in spec.steps:
        m = _PARAM_REF.match(step.value or "")
        if m and m.group(1) not in used:
            used.append(m.group(1))
    spec.parameters = [
        prior.get(k) or WorkflowParameter(
            key=k, description=f"Runtime input for {k}.", example="")
        for k in used
    ]


def induce_from_traces(traces: list[Trace],
                       name: str | None = None) -> tuple[WorkflowSpec, ParameterReport]:
    """Single-trace heuristic on the first recording, refined by what varies
    across all of them. Returns (spec, report)."""
    draft = induce_heuristic(traces[0], name=name)
    report = diff_input_fields(traces)
    if not report.aligned:
        return draft, report

    input_steps = [s for s in draft.steps if s.action in _INPUT_ACTIONS]
    if len(input_steps) != len(report.fields):
        # structure didn't line up with the draft — don't risk a bad rewrite
        return draft, ParameterReport(aligned=False,
                                      trace_count=report.trace_count, fields=[])

    prior = {p.key: p for p in draft.parameters}
    for step, field in zip(input_steps, report.fields, strict=True):
        is_extract = (step.value or "").startswith("{{extract.")
        if is_extract:
            continue  # read live off a page — not a param/literal decision
        if field.varies:
            # ensure it's a parameter (promote a hard-coded literal)
            if not _PARAM_REF.match(step.value or ""):
                step.value = f"{{{{{_slug(field.label)}}}}}"
        else:
            # constant across every recording -> a literal, not a parameter
            if _PARAM_REF.match(step.value or ""):
                step.value = field.values[0]

    _rebuild_parameters(draft, prior)
    return draft, report
