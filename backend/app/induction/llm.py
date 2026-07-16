"""LLM enrichment of a heuristically-induced workflow.

The heuristic layer already produced a structurally-valid spec. The LLM's job
is judgment, not structure:

 1. PROVENANCE  — for each parameterized fill, check whether the demonstrated
    value appeared in the page_text of an earlier NAVIGATE snapshot. If so,
    the value was READ from that page, not invented: replace the parameter
    with an EXTRACT step (read the element on the source page) + a
    {{extract.key}} reference. Result: a run needs only e.g. `invoice_id`,
    and every other value is pulled live from the source system.
 2. NAMING     — rewrite step intents and parameter descriptions so a finance
    reviewer can audit the procedure ("Enter the invoice total into Amount",
    not "Enter value into textbox 'Amount'").
 3. SEGMENTING — group steps into named phases (ALLOY-style sub-tasks),
    carried in the description.

Output contract: the model must return the SAME WorkflowSpec JSON shape; we
validate with pydantic and run spec.validate_references(). On any failure we
fall back to the heuristic spec — enrichment is strictly best-effort.
"""
from __future__ import annotations

import json
import os

from ..models.trace import Trace
from ..models.workflow import WorkflowSpec

MODEL = os.environ.get("UNDERSTUDY_MODEL", "claude-sonnet-4-6")

SYSTEM = """\
You improve a browser-workflow specification that was mechanically induced
from a user demonstration. You will receive the demonstration trace (with
page-text snapshots) and the draft spec. Return ONLY a JSON object with the
same schema as the draft spec. Rules:

1. Keep every step's `target` object EXACTLY as given — never invent selectors.
2. Rewrite each `intent` as one clear sentence a finance reviewer would write.
3. Provenance: if a parameter's example value appears verbatim in an earlier
   page's page_text, the user READ it there. Insert an `extract` step at the
   right position (action="extract", target = the element that showed the
   value if identifiable from data-testids in the trace, extract_key =
   snake_case name) and change the fill's value to {{extract.<key>}}.
   Remove the now-unneeded parameter. Keep genuinely external inputs
   (e.g. which record to process) as parameters.
4. Never change `requires_approval: true` to false. You may add `true` to a
   step that commits state.
5. Give the spec a concise professional `name` and a `description` that lists
   the phases of the procedure.
"""


class InductionError(RuntimeError):
    pass


async def enrich_with_llm(trace: Trace, draft: WorkflowSpec) -> WorkflowSpec:
    """Best-effort enrichment. Raises InductionError only on hard failures;
    callers should catch and fall back to the draft."""
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:
        raise InductionError("anthropic sdk not installed") from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise InductionError("ANTHROPIC_API_KEY not set")

    client = AsyncAnthropic()
    payload = {
        "trace": trace.condensed().model_dump(mode="json"),
        "draft_spec": draft.model_dump(mode="json"),
    }
    msg = await client.messages.create(
        model=MODEL,
        max_tokens=4000,
        temperature=0,
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload)}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text

    enriched = WorkflowSpec.model_validate_json(text)

    # Hard safety invariants the LLM is not allowed to violate:
    problems = enriched.validate_references()
    if problems:
        raise InductionError(f"enriched spec inconsistent: {problems}")
    draft_gated = {s.target.testid for s in draft.steps
                   if s.requires_approval and s.target}
    kept_gated = {s.target.testid for s in enriched.steps
                  if s.requires_approval and s.target}
    if not draft_gated <= kept_gated:
        raise InductionError("enrichment removed an approval gate — rejected")

    enriched.id = draft.id
    enriched.source_trace_ids = draft.source_trace_ids
    return enriched


async def induce(trace: Trace, name: str | None = None) -> WorkflowSpec:
    """Full pipeline: heuristic baseline, then best-effort LLM enrichment."""
    from .heuristic import induce_heuristic

    draft = induce_heuristic(trace, name=name)
    try:
        return await enrich_with_llm(trace, draft)
    except InductionError:
        return draft
