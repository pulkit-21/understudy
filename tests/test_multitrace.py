"""Multi-trace parameter discovery.

Two recordings of the SAME task with different data reveal what's a parameter
(varies) vs a literal (constant) — something a single recording can only guess.
"""
from __future__ import annotations

from app.domain.trace import EventType, SemanticEvent, TargetInfo, Trace
from app.induction.multitrace import diff_input_fields, induce_from_traces


def _vendor_trace(name: str, email: str, terms: str, tax: str) -> Trace:
    base = "http://localhost:8000"
    ev = [
        SemanticEvent(type=EventType.NAVIGATE, url=f"{base}/erp/vendors/new", ts_ms=0),
        SemanticEvent(type=EventType.FILL, url=f"{base}/erp/vendors/new", ts_ms=1,
                      value=name, target=TargetInfo(role="textbox", name="Vendor name",
                                                    testid="field-vendor-name")),
        SemanticEvent(type=EventType.FILL, url=f"{base}/erp/vendors/new", ts_ms=2,
                      value=email, target=TargetInfo(role="textbox", name="Billing email",
                                                     testid="field-email")),
        SemanticEvent(type=EventType.SELECT, url=f"{base}/erp/vendors/new", ts_ms=3,
                      value=terms, target=TargetInfo(role="combobox", name="Payment terms",
                                                     testid="field-payment-terms")),
        SemanticEvent(type=EventType.FILL, url=f"{base}/erp/vendors/new", ts_ms=4,
                      value=tax, target=TargetInfo(role="textbox", name="Tax ID",
                                                   testid="field-tax-id")),
        SemanticEvent(type=EventType.SUBMIT, url=f"{base}/erp/vendors/new", ts_ms=5,
                      target=TargetInfo(role="button", name="Create vendor",
                                        testid="create-vendor")),
    ]
    return Trace(name="Onboard a vendor", events=ev, start_url=f"{base}/erp/vendors/new")


# two recordings: vendor/email/tax differ; payment terms is "Net 30" in both
T1 = _vendor_trace("Aurora Instruments", "ap@aurora.example", "Net 30", "TX-99-4471")
T2 = _vendor_trace("Borealis Tooling", "billing@borealis.example", "Net 30", "TX-11-2200")


def test_diff_flags_varying_fields_as_parameters():
    report = diff_input_fields([T1, T2])
    assert report.aligned is True and report.trace_count == 2
    by_label = {f.label: f for f in report.fields}
    assert by_label["Vendor name"].varies is True
    assert by_label["Billing email"].varies is True
    assert by_label["Tax ID"].varies is True
    # constant across both recordings -> a literal, not a parameter
    assert by_label["Payment terms"].varies is False


def test_induce_from_traces_demotes_the_constant_field():
    """Single-trace induction makes ALL four operator inputs parameters; the
    second recording proves 'Payment terms' is constant, so it becomes a literal."""
    from app.induction.heuristic import induce_heuristic

    single = induce_heuristic(T1)
    assert "payment_terms" in {p.key for p in single.parameters}  # single-trace guess

    spec, report = induce_from_traces([T1, T2])
    keys = {p.key for p in spec.parameters}
    assert keys == {"vendor_name", "billing_email", "tax_id"}  # payment_terms demoted
    # the demoted field is now a hard-coded literal in its step
    terms_step = next(s for s in spec.steps
                      if s.target and s.target.testid == "field-payment-terms")
    assert terms_step.value == "Net 30"
    assert spec.validate_references() == []
    assert report.parameters == ["Vendor name", "Billing email", "Tax ID"]


def test_unalignable_traces_fall_back_to_single_trace():
    short = _vendor_trace("X", "x@x", "Net 30", "T")
    short.events = short.events[:3]  # different structure
    spec, report = induce_from_traces([T1, short])
    assert report.aligned is False
    # still a valid spec (the single-trace draft)
    assert spec.validate_references() == []


def test_induce_multi_via_service_persists_refined_spec(org_id):
    """End-to-end through the service: two saved recordings -> a workflow whose
    parameters exclude the constant field, persisted for the org."""
    import asyncio

    from app.db import SessionLocal, TraceRepo, UsageRepo, WorkflowRepo
    from app.services.induction import InductionService

    traces = TraceRepo(SessionLocal)
    t1 = T1.model_copy(update={"id": "vt-1"})
    t2 = T2.model_copy(update={"id": "vt-2"})
    traces.save(t1, org_id)
    traces.save(t2, org_id)

    svc = InductionService(traces, WorkflowRepo(SessionLocal), UsageRepo(SessionLocal))
    res = asyncio.run(svc.induce_multi(["vt-1", "vt-2"], org_id, use_llm=False))

    assert res["induced_by"] == "multi-trace"
    spec = res["workflow"]
    assert {p.key for p in spec.parameters} == {"vendor_name", "billing_email", "tax_id"}
    assert spec.source_trace_ids == ["vt-1", "vt-2"]
    assert res["parameter_report"]["aligned"] is True
    # persisted + reloadable
    assert WorkflowRepo(SessionLocal).load(spec.id, org_id) is not None


def test_induce_multi_needs_two_traces(org_id):
    import asyncio

    import pytest

    from app.db import SessionLocal, TraceRepo, UsageRepo, WorkflowRepo
    from app.services.errors import Invalid
    from app.services.induction import InductionService

    svc = InductionService(TraceRepo(SessionLocal), WorkflowRepo(SessionLocal),
                           UsageRepo(SessionLocal))
    with pytest.raises(Invalid):
        asyncio.run(svc.induce_multi(["only-one"], org_id, use_llm=False))


def test_url_only_parameter_is_not_dropped():
    """Regression: a param that lives only in a navigate URL (never re-typed into
    a field) must survive multi-trace induction — _rebuild_parameters scans
    step.url, not just step.value."""
    from app.domain.trace import EventType, SemanticEvent, TargetInfo, Trace

    def order_trace(order_id: str) -> Trace:
        b = "http://x"
        return Trace(name="open order", start_url=f"{b}/portal", events=[
            SemanticEvent(type=EventType.NAVIGATE, url=f"{b}/portal", ts_ms=0),
            SemanticEvent(type=EventType.CLICK, url=f"{b}/portal", ts_ms=1,
                          target=TargetInfo(role="link", name="Open",
                                            testid=f"open-{order_id}", tag="a")),
            SemanticEvent(type=EventType.NAVIGATE, url=f"{b}/portal/order/{order_id}",
                          ts_ms=2),
            SemanticEvent(type=EventType.FILL, url=f"{b}/portal/order/{order_id}",
                          ts_ms=3, value="memo",  # constant across both -> literal
                          target=TargetInfo(role="textbox", name="Note",
                                            testid="field-note")),
            SemanticEvent(type=EventType.SUBMIT, url=f"{b}/portal/order/{order_id}",
                          ts_ms=4, target=TargetInfo(role="button", name="Save",
                                                     testid="save")),
        ])

    spec, report = induce_from_traces([order_trace("101"), order_trace("102")])
    keys = {p.key for p in spec.parameters}
    assert "order_id" in keys                 # URL-only param kept
    assert "note" not in keys                 # constant fill demoted to literal
    assert spec.validate_references() == []   # and the spec is internally consistent
