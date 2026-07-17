"""The conversational agent's tools — org-scoped, and (critically) unable to
approve. The LLM loop itself needs a key and isn't unit-tested here; the tool
layer (what the agent is actually allowed to do) is."""
from __future__ import annotations

import pytest

from app.agent import AgentTools, tool_schemas
from app.db import SessionLocal, TraceRepo, UsageRepo, WorkflowRepo
from app.executor.runner import RunStatus
from app.induction.heuristic import induce_heuristic


def _tools(org_id):
    from app.main import runs
    return AgentTools(WorkflowRepo(SessionLocal), runs, TraceRepo(SessionLocal),
                      UsageRepo(SessionLocal), org_id)


def test_agent_has_no_approval_tool():
    """The whole safety story: the agent can start work but a human alone
    releases the gate. There must be no approve/reject tool."""
    names = [t["name"] for t in tool_schemas()]
    assert not any("approve" in n or "reject" in n for n in names)


@pytest.mark.asyncio
async def test_list_workflows_is_org_scoped(demo_trace, org_id):
    WorkflowRepo(SessionLocal).save(induce_heuristic(demo_trace), org_id)
    res = await _tools(org_id).dispatch("list_workflows", {})
    assert len(res["workflows"]) == 1
    # a different org sees nothing
    from app.main import auth
    other = auth.create_org("other").id
    assert (await _tools(other).dispatch("list_workflows", {}))["workflows"] == []


@pytest.mark.asyncio
async def test_run_workflow_tool_starts_and_flags_the_gate(demo_trace, org_id, monkeypatch):
    from app.main import runs

    async def fake_execute(spec, run, queue, org, batch_id):
        run.status = RunStatus.AWAITING_APPROVAL
        await queue.put(None)
        runs.repo.save(run, org, batch_id=batch_id)

    monkeypatch.setattr(runs, "_execute", fake_execute)
    spec = induce_heuristic(demo_trace)
    WorkflowRepo(SessionLocal).save(spec, org_id)
    res = await _tools(org_id).dispatch(
        "run_workflow", {"workflow_id": spec.id, "params": {"invoice_id": "INV-1002"}})
    assert "run_id" in res
    assert "approval" in res["note"].lower()  # agent is told a human must approve


@pytest.mark.asyncio
async def test_run_workflow_rejects_missing_params(demo_trace, org_id):
    spec = induce_heuristic(demo_trace)
    WorkflowRepo(SessionLocal).save(spec, org_id)
    res = await _tools(org_id).dispatch(
        "run_workflow", {"workflow_id": spec.id, "params": {}})
    assert "error" in res and "invoice_id" in res["error"]


@pytest.mark.asyncio
async def test_unknown_tool_is_handled():
    res = await _tools("org-x").dispatch("delete_everything", {})
    assert "error" in res
