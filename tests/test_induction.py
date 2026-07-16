"""Induction tests: the guarantees that make a learned workflow trustworthy.

These catch the failures that actually break replays:
  * demo data leaking into the spec as constants (no parameterization),
  * a commit step without an approval gate,
  * a spec whose template references don't resolve.
"""
from app.induction.heuristic import induce_heuristic
from app.models.workflow import ActionType, RiskLevel, WorkflowSpec


def test_induces_structurally_valid_spec(demo_trace):
    spec = induce_heuristic(demo_trace)
    assert isinstance(spec, WorkflowSpec)
    assert spec.validate_references() == []
    assert spec.source_trace_ids == [demo_trace.id]


def test_dynamic_values_become_parameters_not_constants(demo_trace):
    spec = induce_heuristic(demo_trace)
    param_keys = {p.key for p in spec.parameters}
    # values containing digits (ids, dates, amounts, GL codes) must be params
    assert {"invoice_number", "invoice_date", "amount", "gl_code"} <= param_keys
    fill_values = [s.value for s in spec.steps
                   if s.action in (ActionType.FILL, ActionType.SELECT)]
    assert "{{invoice_number}}" in fill_values
    assert "4820.00" not in fill_values  # demo literal must NOT be baked in


def test_commit_step_is_flagged_and_gated(demo_trace):
    spec = induce_heuristic(demo_trace)
    post = [s for s in spec.steps if s.target and s.target.testid == "post-bill"]
    assert len(post) == 1
    assert post[0].risk == RiskLevel.COMMIT
    assert post[0].requires_approval is True


def test_first_navigation_becomes_step_but_click_navigations_do_not(demo_trace):
    spec = induce_heuristic(demo_trace)
    navs = [s for s in spec.steps if s.action == ActionType.NAVIGATE]
    # opening the portal is a step; arriving at the invoice page via the
    # recorded click is not (the click already causes it)
    assert len(navs) == 2  # initial portal open + direct jump to /erp/new
    assert navs[0].url.endswith("/portal")


def test_spec_roundtrips_through_json(demo_trace):
    spec = induce_heuristic(demo_trace)
    restored = WorkflowSpec.model_validate_json(spec.model_dump_json())
    assert restored == spec
