"""Persistence layer: repositories round-trip domain models faithfully, are
org-scoped (one tenant can't read another's data), and the run history survives
beyond the in-memory run.

Run against the temp SQLite DB from conftest (schema reset per test).
"""
from __future__ import annotations

from app.db import RunRepo, SessionLocal, TraceRepo, WorkflowRepo
from app.executor.runner import Run, RunEvent, RunStatus
from app.induction.heuristic import induce_heuristic


def test_trace_repo_roundtrip(demo_trace, org_id):
    repo = TraceRepo(SessionLocal)
    repo.save(demo_trace, org_id)
    got = repo.load(demo_trace.id, org_id)
    assert got is not None
    assert got.model_dump() == demo_trace.model_dump()
    assert [t.id for t in repo.list(org_id)] == [demo_trace.id]


def test_load_missing_returns_none(org_id):
    assert TraceRepo(SessionLocal).load("nope", org_id) is None
    assert WorkflowRepo(SessionLocal).load("nope", org_id) is None
    assert RunRepo(SessionLocal).get("nope", org_id) is None


def test_repos_are_org_scoped(demo_trace, org_id):
    """A second org must not see the first org's trace."""
    from app.main import auth
    other_org = auth.create_org("other").id
    TraceRepo(SessionLocal).save(demo_trace, org_id)
    assert TraceRepo(SessionLocal).load(demo_trace.id, other_org) is None
    assert TraceRepo(SessionLocal).list(other_org) == []


def test_workflow_repo_roundtrip_and_versioning(demo_trace, org_id):
    repo = WorkflowRepo(SessionLocal)
    spec = induce_heuristic(demo_trace)
    repo.save(spec, org_id)
    got = repo.load(spec.id, org_id)
    assert got is not None and got.model_dump() == spec.model_dump()

    spec.version = 2
    repo.save(spec, org_id)
    assert len(repo.list(org_id)) == 1          # overwrite in place
    assert repo.load(spec.id, org_id).version == 2
    assert len(repo.versions(spec.id, org_id)) == 2  # both snapshots kept


def test_workflow_rollback_restores_old_payload(demo_trace, org_id):
    repo = WorkflowRepo(SessionLocal)
    spec = induce_heuristic(demo_trace)
    original_name = spec.name
    repo.save(spec, org_id)                       # v1
    spec.name = "renamed"
    spec.version = 2
    repo.save(spec, org_id)                       # v2
    v1 = repo.version_payload(spec.id, org_id, 1)
    assert v1 is not None and v1.name == original_name


def test_run_repo_persists_and_lists_summary(org_id):
    repo = RunRepo(SessionLocal)
    run = Run(workflow_id="wf-1", params={"invoice_id": "INV-1005"})
    run.events.append(RunEvent(kind="step_started", detail="open portal"))
    run.status = RunStatus.COMPLETED
    repo.save(run, org_id)

    got = repo.get(run.id, org_id)
    assert got is not None
    assert got.status == RunStatus.COMPLETED
    assert got.params == {"invoice_id": "INV-1005"}

    summaries = repo.list(org_id)
    assert len(summaries) == 1
    assert summaries[0]["id"] == run.id
    assert summaries[0]["status"] == "completed"


def test_run_list_is_newest_first(org_id):
    repo = RunRepo(SessionLocal)
    ids = []
    for i in range(3):
        run = Run(workflow_id=f"wf-{i}")
        repo.save(run, org_id)
        ids.append(run.id)
    listed = [s["id"] for s in repo.list(org_id)]
    assert listed[0] == ids[-1]
    assert set(listed) == set(ids)


def test_seed_is_idempotent_and_backfills_new_workflows(org_id):
    """seed_if_empty installs all showcase workflows on a fresh org, does
    nothing on a second run, and — critically — backfills only a missing one
    (so a deployed org gains newly-added workflows without losing data)."""
    from app.seed import seed_if_empty

    traces, workflows = TraceRepo(SessionLocal), WorkflowRepo(SessionLocal)
    assert seed_if_empty(traces, workflows, org_id) is True
    assert len(workflows.list(org_id)) == 3
    # second run is a no-op
    assert seed_if_empty(traces, workflows, org_id) is False
    assert len(workflows.list(org_id)) == 3
    # simulate an older deploy missing the payment workflow -> it gets backfilled
    workflows.delete("wf-demo-payment-001", org_id)
    assert len(workflows.list(org_id)) == 2
    assert seed_if_empty(traces, workflows, org_id) is True
    assert len(workflows.list(org_id)) == 3


def test_run_cost_and_totals_are_metered_and_summed(org_id):
    repo = RunRepo(SessionLocal)
    repo.save(Run(workflow_id="wf-1"), org_id, cost_usd=0.02)
    repo.save(Run(workflow_id="wf-2"), org_id, cost_usd=0.05)
    assert round(repo.total_cost(org_id), 2) == 0.07


def test_run_counts_by_status(org_id):
    repo = RunRepo(SessionLocal)
    for wf, status in [("wf-1", RunStatus.COMPLETED),
                       ("wf-2", RunStatus.COMPLETED),
                       ("wf-3", RunStatus.AWAITING_APPROVAL)]:
        run = Run(workflow_id=wf)
        run.status = status
        repo.save(run, org_id)
    counts = repo.counts_by_status(org_id)
    assert counts["completed"] == 2 and counts["awaiting_approval"] == 1


def test_recent_events_are_flattened_and_newest_first(org_id):
    repo = RunRepo(SessionLocal)
    run = Run(workflow_id="wf-1")
    run.events.append(RunEvent(kind="step_started", detail="one"))
    run.events.append(RunEvent(kind="approval_granted", detail="two", actor="alice"))
    repo.save(run, org_id)
    feed = repo.recent_events(org_id)
    assert [e["kind"] for e in feed][:2] == ["approval_granted", "step_started"]
    assert feed[0]["actor"] == "alice" and feed[0]["run_id"] == run.id


def test_batch_filtering_groups_runs(org_id):
    repo = RunRepo(SessionLocal)
    repo.save(Run(workflow_id="wf-1"), org_id, batch_id="batch-A")
    repo.save(Run(workflow_id="wf-1"), org_id, batch_id="batch-A")
    repo.save(Run(workflow_id="wf-1"), org_id, batch_id="batch-B")
    assert len(repo.list(org_id, batch_id="batch-A")) == 2
    assert len(repo.list(org_id, batch_id="batch-B")) == 1


def test_usage_repo_records_meters_and_is_org_scoped(org_id):
    from app.db import UsageRepo
    other = _other_org()
    repo = UsageRepo(SessionLocal)
    repo.record(org_id, "claude-sonnet-5", 1000, 500, 0.01, kind="agent")
    repo.record(org_id, "claude-opus-4-8", 2000, 800, 0.03, kind="induction")
    repo.record(other, "claude-sonnet-5", 100, 50, 0.99, kind="agent")
    assert round(repo.total(org_id), 2) == 0.04       # other org excluded
    recent = repo.recent(org_id)
    assert len(recent) == 2 and recent[0]["kind"] == "induction"  # newest first


def test_replay_repo_roundtrip_and_org_scoping(org_id):
    from app.db import ReplayRepo
    other = _other_org()
    repo = ReplayRepo(SessionLocal)
    repo.save("trace-1", org_id, [{"type": 2, "data": {}}])
    assert repo.exists("trace-1", org_id) is True
    assert repo.get("trace-1", org_id) == [{"type": 2, "data": {}}]
    assert repo.get("trace-1", other) is None          # can't read another org's
    assert repo.exists("trace-1", other) is False


def test_conversation_repo_lifecycle(org_id):
    from app.db import ConversationRepo
    repo = ConversationRepo(SessionLocal)
    conv = repo.create(org_id, "Ask about invoices")
    repo.save_messages(conv.id, org_id, [{"role": "user", "content": "hi"}])
    assert repo.get(conv.id, org_id).messages == [{"role": "user", "content": "hi"}]
    assert repo.list(org_id)[0]["id"] == conv.id
    assert repo.delete(conv.id, org_id) is True
    assert repo.get(conv.id, org_id) is None


def _other_org() -> str:
    from app.main import auth
    return auth.create_org("other-tenant").id
