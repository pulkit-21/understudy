"""LLM enrichment of a heuristically-induced workflow.

The heuristic layer already did the load-bearing work deterministically:
structure, parameterized navigation, and provenance (extract steps). That means
the workflow is already correct and runnable with no API key. The LLM's job here
is deliberately narrow — LEGIBILITY, not correctness:

  * rewrite each step's `intent` into one sentence a finance reviewer would
    write ("Read the vendor name off the invoice", not "Read Vendor from the
    source page"),
  * give the workflow a professional `name` and a `description` that lays out
    the procedure's phases.

It is NOT allowed to change what the workflow *does*. We enforce that as a hard
invariant: the enriched spec must be structurally identical to the draft
(same actions, targets, values, extract keys, risk levels, and — critically —
approval gates); only human-readable text may differ. Any deviation, any
malformed output, or a missing key → we discard the LLM result and ship the
deterministic draft. The stochastic layer can make the workflow nicer to read;
it can never make it wrong.

(Fuzzy provenance — matching a typed value to a page value across formatting
differences the exact-match heuristic misses — is a natural next extension of
this layer; see decisions.md.)
"""
from __future__ import annotations

import json
import os
from collections.abc import Callable

from ..models.trace import Trace
from ..models.workflow import WorkflowSpec

MODEL = os.environ.get("UNDERSTUDY_MODEL", "claude-opus-4-8")

# USD per input / output token, by model-id prefix. Used to meter induction cost
# (the only place Understudy calls an LLM — runs are deterministic and free).
_PRICING = {
    "claude-opus": (5.0 / 1e6, 25.0 / 1e6),
    "claude-sonnet": (3.0 / 1e6, 15.0 / 1e6),
    "claude-haiku": (1.0 / 1e6, 5.0 / 1e6),
    "claude-fable": (5.0 / 1e6, 25.0 / 1e6),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    for prefix, (pin, pout) in _PRICING.items():
        if model.startswith(prefix):
            return input_tokens * pin + output_tokens * pout
    return 0.0

SYSTEM = """\
You are improving the READABILITY of an already-correct browser-workflow spec
that was mechanically induced from a user demonstration. You receive the
demonstration trace (with page snapshots) and the draft spec. Return ONLY a
JSON object with the exact same schema as the draft spec.

You MAY change, and ONLY these:
  - the top-level `name`: a concise, professional title for the procedure.
  - the top-level `description`: 1-3 sentences naming the phases of the
    procedure (e.g. "Open the invoice, read its fields, then post a bill to the
    ERP — pausing for approval before posting.").
  - each step's `intent`: one clear sentence a finance reviewer would write,
    describing what the step does and, where relevant, why. For `extract` steps,
    say what is being read and from where. For the gated commit step, make the
    irreversibility explicit.
  - each parameter's `description`.

You MUST NOT change anything else. Keep every step's `action`, `target`,
`value`, `url`, `extract_key`, `risk`, and `requires_approval` EXACTLY as given,
in the same order. Never add, remove, or reorder steps. Never invent selectors.
Never change a `requires_approval: true` to false. Do not touch `id`, `version`,
`source_trace_ids`, or the set of parameter keys.
"""


class InductionError(RuntimeError):
    pass


def _structure(spec: WorkflowSpec) -> list:
    """The invariant skeleton the LLM must preserve — everything except the
    human-readable text (name/description/intent/param descriptions)."""
    return [
        (s.action, s.value, s.url, s.extract_key, s.risk, s.requires_approval,
         None if s.target is None else
         (s.target.testid, s.target.role, s.target.name, s.target.css))
        for s in spec.steps
    ]


def validate_enrichment(draft: WorkflowSpec, enriched: WorkflowSpec) -> None:
    """Enforce that enrichment only touched human-readable text. Raises
    InductionError on any structural change, so the caller can fall back to the
    deterministic draft. Pure (no network) — this is the safety boundary and is
    unit-tested directly."""
    if _structure(enriched) != _structure(draft):
        raise InductionError("enrichment altered workflow structure — rejected")
    if {p.key for p in enriched.parameters} != {p.key for p in draft.parameters}:
        raise InductionError("enrichment changed the parameter set — rejected")
    if enriched.validate_references():
        raise InductionError("enriched spec inconsistent — rejected")


async def enrich_with_llm(
    trace: Trace, draft: WorkflowSpec,
    on_usage: Callable[[dict], None] | None = None,
) -> WorkflowSpec:
    """Best-effort legibility pass. Raises InductionError on any hard failure or
    invariant violation; callers should catch and fall back to the draft.

    If `on_usage` is given, it's called once with token/cost metering for the
    call — the caller records it (observability without coupling this module to
    the DB)."""
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
        system=SYSTEM,
        messages=[{"role": "user", "content": json.dumps(payload)}],
    )
    if on_usage is not None:
        u = msg.usage
        on_usage({
            "model": MODEL,
            "input_tokens": u.input_tokens,
            "output_tokens": u.output_tokens,
            "cost_usd": cost_usd(MODEL, u.input_tokens, u.output_tokens),
        })
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text

    try:
        enriched = WorkflowSpec.model_validate_json(text)
    except Exception as e:
        raise InductionError(f"LLM returned invalid spec JSON: {e}") from e

    # Hard invariants. The LLM may only touch human-readable text.
    validate_enrichment(draft, enriched)

    # Carry forward identity the LLM isn't allowed to set.
    enriched.id = draft.id
    enriched.version = draft.version
    enriched.source_trace_ids = draft.source_trace_ids
    return enriched


async def induce(trace: Trace, name: str | None = None) -> WorkflowSpec:
    """Full pipeline: deterministic draft, then best-effort LLM legibility pass."""
    from .heuristic import induce_heuristic

    draft = induce_heuristic(trace, name=name)
    try:
        return await enrich_with_llm(trace, draft)
    except InductionError:
        return draft
