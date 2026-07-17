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
async def test_batch_is_two_phase_confirm(demo_trace, org_id, monkeypatch):
    """Bulk actions preview first and only run after explicit confirmation."""
    from app.main import runs

    started = []
    monkeypatch.setattr(runs, "start_run",
                        lambda *a, **k: started.append(1) or _Stub())
    spec = induce_heuristic(demo_trace)
    WorkflowRepo(SessionLocal).save(spec, org_id)
    tools = _tools(org_id)

    preview = await tools.dispatch("run_batch", {
        "workflow_id": spec.id, "values": ["INV-1002", "INV-1003"]})
    assert preview["needs_confirmation"] is True and preview["count"] == 2
    assert started == []  # nothing started yet

    done = await tools.dispatch("run_batch", {
        "workflow_id": spec.id, "values": ["INV-1002", "INV-1003"], "confirmed": True})
    assert done["count"] == 2 and len(started) == 2


class _Stub:
    id = "run-stub"


@pytest.mark.asyncio
async def test_keyless_mock_agent_works_offline(demo_trace, org_id, monkeypatch):
    """The chat must work with no API key (deterministic fallback), like the
    reference's mock LLM — and still route through the gated tools."""
    monkeypatch.setenv("UNDERSTUDY_AGENT_MOCK", "1")
    from app.agent import run_agent
    WorkflowRepo(SessionLocal).save(induce_heuristic(demo_trace), org_id)
    tools = _tools(org_id)

    r1 = await run_agent([{"role": "user", "content": "what workflows do I have?"}], tools)
    assert "workflow" in r1["reply"].lower()
    assert any(s["tool"] == "list_workflows" for s in r1["steps"])

    r2 = await run_agent([{"role": "user", "content": "run the workflow on INV-1002"}], tools)
    assert any(s["tool"] == "run_workflow" for s in r2["steps"])
    assert any(c["type"] == "run" for c in r2["cards"])  # actionable card returned


def test_chat_persists_conversation_history(authed_client, demo_trace, monkeypatch):
    """A chat turn creates/updates a persisted conversation; it survives reload."""
    monkeypatch.setenv("UNDERSTUDY_AGENT_MOCK", "1")
    client, org_id = authed_client
    WorkflowRepo(SessionLocal).save(induce_heuristic(demo_trace), org_id)

    r = client.post("/api/agent/chat", json={"message": "what workflows do I have?"})
    assert r.status_code == 200
    cid = r.json()["conversation_id"]

    convs = client.get("/api/agent/conversations").json()
    assert any(c["id"] == cid for c in convs)

    full = client.get(f"/api/agent/conversations/{cid}").json()
    assert [m["role"] for m in full["messages"]] == ["user", "assistant"]
    assert "workflow" in full["messages"][1]["content"].lower()

    # a follow-up appends to the same conversation
    client.post("/api/agent/chat", json={"message": "thanks", "conversation_id": cid})
    assert len(client.get(f"/api/agent/conversations/{cid}").json()["messages"]) == 4

    client.delete(f"/api/agent/conversations/{cid}")
    assert client.get("/api/agent/conversations").json() == []


@pytest.mark.asyncio
async def test_unknown_tool_is_handled():
    res = await _tools("org-x").dispatch("delete_everything", {})
    assert "error" in res
