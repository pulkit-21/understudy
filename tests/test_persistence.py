"""Persistence layer: repositories round-trip domain models faithfully and the
run history survives beyond the in-memory run.

These run against the temp SQLite DB from conftest (schema reset per test).
"""
from __future__ import annotations

from app.db import RunRepo, SessionLocal, TraceRepo, WorkflowRepo
from app.executor.runner import Run, RunEvent, RunStatus
from app.induction.heuristic import induce_heuristic


def test_trace_repo_roundtrip(demo_trace):
    repo = TraceRepo(SessionLocal)
    repo.save(demo_trace)
    got = repo.load(demo_trace.id)
    assert got is not None
    # full-fidelity round-trip, not just the id
    assert got.model_dump() == demo_trace.model_dump()
    assert [t.id for t in repo.list()] == [demo_trace.id]


def test_load_missing_returns_none():
    assert TraceRepo(SessionLocal).load("nope") is None
    assert WorkflowRepo(SessionLocal).load("nope") is None
    assert RunRepo(SessionLocal).get("nope") is None


def test_workflow_repo_roundtrip_and_versioning(demo_trace):
    repo = WorkflowRepo(SessionLocal)
    spec = induce_heuristic(demo_trace)
    repo.save(spec)
    got = repo.load(spec.id)
    assert got is not None and got.model_dump() == spec.model_dump()

    # a resave (edit) overwrites in place, not a duplicate row
    spec.version = 2
    repo.save(spec)
    assert len(repo.list()) == 1
    assert repo.load(spec.id).version == 2


def test_run_repo_persists_and_lists_summary():
    repo = RunRepo(SessionLocal)
    run = Run(workflow_id="wf-1", params={"invoice_id": "INV-1005"})
    run.events.append(RunEvent(kind="step_started", detail="open portal"))
    run.status = RunStatus.COMPLETED
    repo.save(run)

    got = repo.get(run.id)
    assert got is not None
    assert got.status == RunStatus.COMPLETED
    assert got.params == {"invoice_id": "INV-1005"}

    summaries = repo.list()
    assert len(summaries) == 1
    assert summaries[0]["id"] == run.id
    assert summaries[0]["workflow_id"] == "wf-1"
    assert summaries[0]["status"] == "completed"


def test_run_list_is_newest_first():
    repo = RunRepo(SessionLocal)
    ids = []
    for i in range(3):
        run = Run(workflow_id=f"wf-{i}")
        repo.save(run)
        ids.append(run.id)
    listed = [s["id"] for s in repo.list()]
    # created_at desc — most recent first
    assert listed[0] == ids[-1]
    assert set(listed) == set(ids)
