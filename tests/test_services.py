"""Service-layer unit tests.

Services hold the app's use-cases and raise domain errors (services/errors.py)
rather than HTTPException, so they're testable without the web stack. These
exercise the orchestration and — importantly — the error paths, which the
exception handler then maps to status codes (see test_api for the HTTP mapping).
"""
from __future__ import annotations

import asyncio

import pytest

from app.db import SessionLocal, TraceRepo, UsageRepo, WorkflowRepo
from app.domain.workflow import WorkflowStatus
from app.induction.heuristic import induce_heuristic
from app.services.agent import AgentService
from app.services.errors import Conflict, Invalid, NotFound
from app.services.induction import InductionService
from app.services.metrics import MetricsService
from app.services.runs import RunService
from app.services.traces import TraceService
from app.services.workflows import WorkflowService


def _wf_service():
    return WorkflowService(WorkflowRepo(SessionLocal))


def _saved_workflow(demo_trace, org_id):
    spec = induce_heuristic(demo_trace)
    WorkflowRepo(SessionLocal).save(spec, org_id)
    return spec


# ---- WorkflowService --------------------------------------------------------

def test_workflow_get_unknown_raises_not_found(org_id):
    with pytest.raises(NotFound):
        _wf_service().get("nope", org_id)


def test_workflow_update_rejects_ungated_commit(demo_trace, org_id):
    spec = _saved_workflow(demo_trace, org_id)
    for step in spec.steps:
        if step.risk.value == "commit":
            step.requires_approval = False
    with pytest.raises(Invalid):
        _wf_service().update(spec.id, spec, org_id)


def test_workflow_update_bumps_version(demo_trace, org_id):
    spec = _saved_workflow(demo_trace, org_id)
    before = spec.version
    updated = _wf_service().update(spec.id, spec, org_id)
    assert updated.version == before + 1


def test_workflow_duplicate_is_a_fresh_draft(demo_trace, org_id):
    spec = _saved_workflow(demo_trace, org_id)
    dup = _wf_service().duplicate(spec.id, org_id)
    assert dup.id != spec.id and dup.status == WorkflowStatus.DRAFT
    assert dup.version == 1 and dup.name.endswith("(copy)")


def test_workflow_delete_unknown_raises(org_id):
    with pytest.raises(NotFound):
        _wf_service().delete("nope", org_id)


def test_workflow_rollback_restores_old_payload(demo_trace, org_id):
    svc = _wf_service()
    spec = _saved_workflow(demo_trace, org_id)
    original_name = spec.name
    spec.name = "renamed"
    svc.update(spec.id, spec, org_id)          # v2
    rolled = svc.rollback(spec.id, 1, org_id)  # back to v1's payload
    assert rolled.name == original_name


# ---- RunService -------------------------------------------------------------

def test_run_start_unknown_workflow_raises_not_found(org_id):
    from app.main import runs
    with pytest.raises(NotFound):
        RunService(runs, WorkflowRepo(SessionLocal)).start("nope", {}, org_id)


def test_run_start_missing_params_raises_invalid(demo_trace, org_id):
    from app.main import runs
    spec = _saved_workflow(demo_trace, org_id)
    with pytest.raises(Invalid):
        RunService(runs, WorkflowRepo(SessionLocal)).start(spec.id, {}, org_id)


def test_run_approve_unknown_raises_conflict(org_id):
    from app.main import runs
    with pytest.raises(Conflict):
        RunService(runs, WorkflowRepo(SessionLocal)).approve("nope", org_id)


def test_run_reject_unknown_raises_conflict(org_id):
    from app.main import runs
    with pytest.raises(Conflict):
        RunService(runs, WorkflowRepo(SessionLocal)).reject("nope", org_id)


def test_run_batch_starts_one_run_per_value(demo_trace, org_id, monkeypatch):
    from app.main import runs
    spec = _saved_workflow(demo_trace, org_id)

    started: list[dict] = []

    class _Stub:
        id = "run-stub"

    def fake_start(spec, params, org_id, batch_id=None, dry_run=False):
        started.append(params)
        return _Stub()

    monkeypatch.setattr(runs, "start_run", fake_start)
    svc = RunService(runs, WorkflowRepo(SessionLocal))
    result = svc.start_batch(spec.id, ["INV-1002", "INV-1003"], None, {}, org_id)
    assert result["count"] == 2 and len(started) == 2
    assert result["batch_id"].startswith("batch-")
    # the varying parameter is threaded into each run
    assert {p["invoice_id"] for p in started} == {"INV-1002", "INV-1003"}


# ---- TraceService -----------------------------------------------------------

def test_trace_get_unknown_raises_not_found(org_id):
    svc = TraceService(TraceRepo(SessionLocal), _replays())
    with pytest.raises(NotFound):
        svc.get("nope", org_id)


def test_trace_replay_roundtrip(demo_trace, org_id):
    TraceRepo(SessionLocal).save(demo_trace, org_id)
    svc = TraceService(TraceRepo(SessionLocal), _replays())
    svc.save_replay(demo_trace.id, [{"type": 2}], org_id)
    assert svc.get_replay(demo_trace.id, org_id)["events"] == [{"type": 2}]
    assert svc.get(demo_trace.id, org_id)["has_replay"] is True


# ---- InductionService -------------------------------------------------------

def test_induction_unknown_trace_raises_not_found(org_id):
    svc = InductionService(TraceRepo(SessionLocal), WorkflowRepo(SessionLocal),
                           UsageRepo(SessionLocal))
    with pytest.raises(NotFound):
        asyncio.run(svc.induce("nope", org_id, use_llm=False))


def test_induction_without_llm_saves_heuristic_spec(demo_trace, org_id):
    TraceRepo(SessionLocal).save(demo_trace, org_id)
    svc = InductionService(TraceRepo(SessionLocal), WorkflowRepo(SessionLocal),
                           UsageRepo(SessionLocal))
    result = asyncio.run(svc.induce(demo_trace.id, org_id, use_llm=False))
    assert result["induced_by"] == "heuristic"
    assert result["problems"] == []
    assert [p.key for p in result["workflow"].parameters] == ["invoice_id"]


# ---- MetricsService ---------------------------------------------------------

def test_metrics_dashboard_shape(demo_trace, org_id):
    from app.main import runs
    _saved_workflow(demo_trace, org_id)
    svc = MetricsService(runs, WorkflowRepo(SessionLocal), UsageRepo(SessionLocal))
    d = svc.dashboard(org_id)
    assert d["workflows"] >= 1
    assert set(d) >= {"run_counts", "total_runs", "pending_approvals",
                      "success_rate", "cost_usd", "minutes_saved", "recent"}


# ---- AgentService -----------------------------------------------------------

def test_agent_get_unknown_conversation_raises(org_id):
    svc = _agent_service()
    with pytest.raises(NotFound):
        svc.get_conversation("nope", org_id)


def test_agent_delete_unknown_conversation_raises(org_id):
    with pytest.raises(NotFound):
        _agent_service().delete_conversation("nope", org_id)


# ---- helpers ----------------------------------------------------------------

def _replays():
    from app.db import ReplayRepo
    return ReplayRepo(SessionLocal)


def _agent_service():
    from app.db import ConversationRepo
    from app.main import runs
    return AgentService(ConversationRepo(SessionLocal), WorkflowRepo(SessionLocal),
                        runs, TraceRepo(SessionLocal), UsageRepo(SessionLocal))
