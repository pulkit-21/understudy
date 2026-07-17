"""Batch runs: one workflow fanned out over many inputs, each its own governed
run tagged with a shared batch_id. Executor is stubbed so the test doesn't
launch real browsers — we're testing the fan-out + bounded pool wiring."""
from __future__ import annotations

import pytest

from app.executor.runner import RunStatus


@pytest.fixture()
def stub_executor(monkeypatch):
    """Replace the browser-driving _execute with an instant no-op success."""
    from app.main import runs as run_manager

    async def fake_execute(spec, run, queue, org_id, batch_id):
        run.status = RunStatus.COMPLETED
        await queue.put(None)
        run_manager.repo.save(run, org_id, batch_id=batch_id)

    monkeypatch.setattr(run_manager, "_execute", fake_execute)
    return run_manager


def test_batch_fans_out_one_run_per_value(authed_client, demo_trace, stub_executor):
    client, org_id = authed_client
    from app.db import SessionLocal, TraceRepo
    TraceRepo(SessionLocal).save(demo_trace, org_id)
    wf = client.post(f"/api/traces/{demo_trace.id}/induce",
                     json={"use_llm": False}).json()["workflow"]

    values = ["INV-1002", "INV-1003", "INV-1004"]
    r = client.post(f"/api/workflows/{wf['id']}/batch",
                    json={"param_values": values})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 3
    assert len(set(body["run_ids"])) == 3
    batch_id = body["batch_id"]

    # all three are listable under the batch, and carry the right params
    listed = client.get(f"/api/runs?batch_id={batch_id}").json()
    assert len(listed) == 3
    assert {r["params"]["invoice_id"] for r in listed} == set(values)
    assert all(r["batch_id"] == batch_id for r in listed)


def test_batch_requires_a_parameter(authed_client, demo_trace, stub_executor):
    client, org_id = authed_client
    from app.db import SessionLocal, WorkflowRepo
    from app.models.workflow import WorkflowSpec
    # a workflow with no parameters can't be batched
    spec = WorkflowSpec(name="no-params", steps=[])
    WorkflowRepo(SessionLocal).save(spec, org_id)
    r = client.post(f"/api/workflows/{spec.id}/batch",
                    json={"param_values": ["a", "b"]})
    assert r.status_code == 422


def test_worker_pool_bounds_concurrency():
    """The semaphore caps simultaneous browsers regardless of how many runs
    are in flight."""
    from app.executor.manager import RunManager

    mgr = RunManager(base_url="http://x", run_repo=None, max_concurrency=2)  # type: ignore[arg-type]
    assert mgr._sem._value == 2
    assert mgr.max_concurrency == 2
