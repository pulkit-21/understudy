"""Induction tests: the guarantees that make a learned workflow trustworthy.

The heuristic is deterministic, so these assert exact *structure* (not fuzzy
prose): the learned workflow needs only `invoice_id`, reads every other value
live off the source page via `extract` steps that target the page's REAL
testids, opens the requested record (not the demonstrated one), and never drops
the approval gate. These are the properties that would silently break a replay.
"""
from app.induction.heuristic import induce_heuristic
from app.models.workflow import ActionType, RiskLevel, WorkflowSpec

DEMO_LITERALS = ["INV-1001", "Northwind Logistics", "4820.00", "2026-06-02", "6100"]


def test_induces_structurally_valid_spec(demo_trace):
    spec = induce_heuristic(demo_trace)
    assert isinstance(spec, WorkflowSpec)
    assert spec.validate_references() == []
    assert spec.source_trace_ids == [demo_trace.id]


def test_needs_only_invoice_id(demo_trace):
    """The whole point: one run input. Everything else is read live."""
    spec = induce_heuristic(demo_trace)
    assert {p.key for p in spec.parameters} == {"invoice_id"}


def test_operator_supplied_field_becomes_a_second_parameter(demo_trace):
    """Multi-parameter support: a run-varying value the operator TYPES but that
    isn't found on any source page becomes its own parameter (values that ARE on
    a page become live extracts instead). So workflows can have as many inputs as
    the task genuinely needs — this one just needs one because the rest is read
    live."""
    from app.models.trace import EventType, SemanticEvent, TargetInfo

    trace = demo_trace
    # operator types a cost-centre code (run-varying, not on the invoice page)
    trace.events.insert(-1, SemanticEvent(
        type=EventType.FILL, url=f"{trace.events[-1].url}", ts_ms=99_999,
        value="CC-4102",
        target=TargetInfo(role="textbox", name="Cost center",
                          testid="field-cost-center", tag="input")))
    spec = induce_heuristic(trace)
    keys = {p.key for p in spec.parameters}
    assert "invoice_id" in keys and "cost_center" in keys      # two inputs now
    # vendor is still read live, not turned into an input
    assert any(s.action == ActionType.EXTRACT and s.extract_key == "vendor"
               for s in spec.steps)


def test_vendor_onboarding_is_multi_parameter(demo_trace):
    """The second showcase task: all values are operator-supplied (no source
    page), so it learns a multi-parameter workflow with a gated commit."""
    from app.seed import build_vendor_trace

    spec = induce_heuristic(build_vendor_trace())
    keys = {p.key for p in spec.parameters}
    assert keys == {"vendor_name", "billing_email", "payment_terms", "tax_id"}
    assert not any(s.action == ActionType.EXTRACT for s in spec.steps)  # nothing to read
    commit = [s for s in spec.steps if s.risk == RiskLevel.COMMIT]
    assert len(commit) == 1 and commit[0].requires_approval  # 'Create' is gated
    assert spec.validate_references() == []


def test_payment_workflow_is_a_gated_state_change(demo_trace):
    """The third showcase task: click a specific bill's payment link (a
    run-varying URL -> parameterized navigate), enter payment inputs, and confirm
    — a COMMIT that moves money, so it must be gated."""
    from app.seed import build_payment_trace

    spec = induce_heuristic(build_payment_trace())
    keys = {p.key for p in spec.parameters}
    # the plural collection segment is singularized: payments/AP-1 -> payment_id
    assert keys == {"payment_id", "payment_date", "payment_method"}
    # the bill reference drives a parameterized navigate, not a hardcoded one
    nav = [s for s in spec.steps if s.action == ActionType.NAVIGATE]
    assert any("{{payment_id}}" in (s.url or "") for s in nav)
    commit = [s for s in spec.steps if s.risk == RiskLevel.COMMIT]
    assert len(commit) == 1 and commit[0].requires_approval  # 'Confirm payment' gated
    assert spec.validate_references() == []


def test_collection_url_segment_is_singularized_for_param_key():
    """/erp/payments/AP-5001 -> 'payment_id' (not 'payments_id'); the invoice
    path (singular already) is unchanged."""
    from app.induction.heuristic import _dynamic_url_token

    assert _dynamic_url_token("/erp/payments/AP-5001") == ("AP-5001", "payment_id")
    assert _dynamic_url_token("/portal/invoice/INV-1001") == ("INV-1001", "invoice_id")


def test_read_values_become_extracts_referenced_by_fills(demo_trace):
    spec = induce_heuristic(demo_trace)
    extract_keys = {s.extract_key for s in spec.steps
                    if s.action == ActionType.EXTRACT}
    # vendor / date / amount / gl were read off the invoice page -> extracts
    assert {"vendor", "date", "amount", "gl"} <= extract_keys
    fill_values = [s.value for s in spec.steps
                   if s.action in (ActionType.FILL, ActionType.SELECT)]
    assert "{{extract.vendor}}" in fill_values
    assert "{{extract.amount}}" in fill_values
    # the invoice number the user typed IS the invoice_id they opened
    assert "{{invoice_id}}" in fill_values


def test_extract_targets_are_real_testids_never_invented(demo_trace):
    """Provenance may only target elements the recorder actually saw — so the
    executor can locate them. Guards against the inducer inventing selectors."""
    seen_testids = {
        f.testid
        for e in demo_trace.events for f in e.readable_fields if f.testid
    }
    for step in induce_heuristic(demo_trace).steps:
        if step.action == ActionType.EXTRACT:
            assert step.target and step.target.testid in seen_testids


def test_open_click_becomes_parameterized_navigate(demo_trace):
    """The demo clicked `open-INV-1001` (a testid baking in one invoice). The
    learned step must navigate to the requested invoice instead."""
    spec = induce_heuristic(demo_trace)
    open_nav = [s for s in spec.steps
                if s.action == ActionType.NAVIGATE
                and s.url and "{{invoice_id}}" in s.url]
    assert len(open_nav) == 1
    assert open_nav[0].url.endswith("/portal/invoice/{{invoice_id}}")
    # the fragile per-invoice click must be gone
    assert not any(s.target and s.target.testid == "open-INV-1001"
                   for s in spec.steps)


def test_no_demo_literals_leak_into_the_spec(demo_trace):
    spec = induce_heuristic(demo_trace)
    # example values live in parameters/descriptions; the STEPS must not carry
    # the demonstration's data as constants.
    for step in spec.steps:
        for text in (step.value, step.url):
            if not text:
                continue
            for lit in DEMO_LITERALS:
                assert lit not in text, f"leaked {lit!r} into {text!r}"


def test_commit_step_is_flagged_and_gated(demo_trace):
    spec = induce_heuristic(demo_trace)
    post = [s for s in spec.steps if s.target and s.target.testid == "post-bill"]
    assert len(post) == 1
    assert post[0].risk == RiskLevel.COMMIT
    assert post[0].requires_approval is True


def test_extracts_precede_the_fills_that_use_them(demo_trace):
    """An extract must run before the step that references its output, or the
    template resolves to nothing. validate_references enforces it; this pins the
    ordering explicitly."""
    spec = induce_heuristic(demo_trace)
    produced_at = {s.extract_key: i for i, s in enumerate(spec.steps)
                   if s.action == ActionType.EXTRACT}
    for i, s in enumerate(spec.steps):
        for ref in s.referenced_params():
            if ref.startswith("extract."):
                assert produced_at[ref.split(".", 1)[1]] < i


def test_spec_roundtrips_through_json(demo_trace):
    spec = induce_heuristic(demo_trace)
    restored = WorkflowSpec.model_validate_json(spec.model_dump_json())
    assert restored == spec
