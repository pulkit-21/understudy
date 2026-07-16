"""LLM-enrichment safety tests (offline — no network, no key).

The LLM may improve *only* human-readable text. These pin the invariant that
protects correctness: any structural change the model makes is rejected and the
deterministic draft ships instead. The live call itself is exercised manually
with a key (see scripts / README), not in CI.
"""
import asyncio

import pytest

from app.induction.heuristic import induce_heuristic
from app.induction.llm import InductionError, induce, validate_enrichment


def _draft(demo_trace):
    return induce_heuristic(demo_trace)


def test_intent_only_rewrite_is_accepted(demo_trace):
    draft = _draft(demo_trace)
    enriched = draft.model_copy(deep=True)
    enriched.name = "A nicer name"
    enriched.description = "Phase one, phase two, phase three."
    for s in enriched.steps:
        s.intent = "A clearer, reviewer-grade sentence."
    validate_enrichment(draft, enriched)  # must not raise


def test_dropping_the_approval_gate_is_rejected(demo_trace):
    draft = _draft(demo_trace)
    tampered = draft.model_copy(deep=True)
    gated = next(s for s in tampered.steps if s.requires_approval)
    gated.requires_approval = False
    with pytest.raises(InductionError):
        validate_enrichment(draft, tampered)


def test_changing_a_target_is_rejected(demo_trace):
    draft = _draft(demo_trace)
    tampered = draft.model_copy(deep=True)
    tgt = next(s for s in tampered.steps if s.target and s.target.testid)
    tgt.target.testid = "some-invented-selector"
    with pytest.raises(InductionError):
        validate_enrichment(draft, tampered)


def test_changing_a_value_is_rejected(demo_trace):
    draft = _draft(demo_trace)
    tampered = draft.model_copy(deep=True)
    fill = next(s for s in tampered.steps if s.value)
    fill.value = "a-baked-in-constant"
    with pytest.raises(InductionError):
        validate_enrichment(draft, tampered)


def test_changing_the_parameter_set_is_rejected(demo_trace):
    draft = _draft(demo_trace)
    tampered = draft.model_copy(deep=True)
    tampered.parameters = []
    with pytest.raises(InductionError):
        validate_enrichment(draft, tampered)


def test_adding_or_removing_a_step_is_rejected(demo_trace):
    draft = _draft(demo_trace)
    tampered = draft.model_copy(deep=True)
    tampered.steps = tampered.steps[:-1]  # drop the commit step
    with pytest.raises(InductionError):
        validate_enrichment(draft, tampered)


def test_induce_falls_back_to_deterministic_draft_without_a_key(
        demo_trace, monkeypatch):
    """No key -> enrichment errors -> the pipeline still returns a correct,
    invoice_id-only spec. The LLM is never load-bearing."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    spec = asyncio.run(induce(demo_trace))
    assert spec.validate_references() == []
    assert {p.key for p in spec.parameters} == {"invoice_id"}
