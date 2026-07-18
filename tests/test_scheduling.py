"""Scheduling: repo CRUD, the due/fire tick, and the service guards.

The background loop itself isn't run here (it's opt-in via UNDERSTUDY_SCHEDULER_
ENABLED); `run_due` is the unit we test — freeze `now`, stub the run manager.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db import ScheduleRepo, SessionLocal, WorkflowRepo
from app.induction.heuristic import induce_heuristic
from app.services.errors import Invalid, NotFound
from app.services.scheduling import ScheduleService, run_due


def _saved_workflow(demo_trace, org_id):
    spec = induce_heuristic(demo_trace)
    WorkflowRepo(SessionLocal).save(spec, org_id)
    return spec


def test_schedule_repo_crud(org_id):
    repo = ScheduleRepo(SessionLocal)
    s = repo.create(org_id, "wf-1", {"invoice_id": "INV-1002"}, 60)
    assert s["enabled"] is True and s["interval_minutes"] == 60
    assert [x["id"] for x in repo.list(org_id)] == [s["id"]]
    assert repo.set_enabled(s["id"], org_id, False) is True
    assert repo.list(org_id)[0]["enabled"] is False
    assert repo.delete(s["id"], org_id) is True
    assert repo.list(org_id) == []


def test_schedule_repo_is_org_scoped(org_id):
    repo = ScheduleRepo(SessionLocal)
    from app.main import auth
    other = auth.create_org("other").id
    s = repo.create(org_id, "wf-1", {}, 30)
    assert repo.set_enabled(s["id"], other, False) is False   # not other's
    assert repo.delete(s["id"], other) is False
    assert repo.list(other) == []


def test_due_finds_only_passed_schedules(org_id):
    repo = ScheduleRepo(SessionLocal)
    s = repo.create(org_id, "wf-1", {}, 60)   # next_run_at = now + 60m (future)
    now = datetime.now(UTC)
    assert repo.due(now) == []                             # not yet
    later = now + timedelta(minutes=61)
    assert [d["id"] for d in repo.due(later)] == [s["id"]]  # now due


def test_run_due_starts_a_run_and_rearms(demo_trace, org_id, monkeypatch):
    from app.main import runs
    spec = _saved_workflow(demo_trace, org_id)
    repo = ScheduleRepo(SessionLocal)
    repo.create(org_id, spec.id, {"invoice_id": "INV-1002"}, 60)

    started = []
    monkeypatch.setattr(runs, "start_run",
                        lambda spec, params, org_id, **k: started.append((org_id, params)))

    fire_at = datetime.now(UTC) + timedelta(minutes=61)
    fired = run_due(fire_at, repo, WorkflowRepo(SessionLocal), runs)

    assert fired == 1
    assert started == [(org_id, {"invoice_id": "INV-1002"})]
    # re-armed into the future, no longer due at fire_at
    assert repo.due(fire_at) == []
    assert repo.list(org_id)[0]["last_run_at"] is not None


def test_run_due_skips_a_deleted_workflow_without_spinning(org_id, monkeypatch):
    from app.main import runs
    repo = ScheduleRepo(SessionLocal)
    repo.create(org_id, "wf-gone", {}, 30)  # workflow doesn't exist
    started = []
    monkeypatch.setattr(runs, "start_run", lambda *a, **k: started.append(1))
    fire_at = datetime.now(UTC) + timedelta(minutes=31)
    fired = run_due(fire_at, repo, WorkflowRepo(SessionLocal), runs)
    assert fired == 0 and started == []
    assert repo.due(fire_at) == []  # still advanced (won't spin on next tick)


def test_service_guards(demo_trace, org_id):
    svc = ScheduleService(ScheduleRepo(SessionLocal), WorkflowRepo(SessionLocal))
    with pytest.raises(Invalid):
        svc.create(org_id, "wf-1", {}, 0)              # interval too small
    with pytest.raises(NotFound):
        svc.create(org_id, "wf-missing", {}, 60)       # unknown workflow
    spec = _saved_workflow(demo_trace, org_id)
    created = svc.create(org_id, spec.id, {}, 15)
    assert created["interval_minutes"] == 15
    with pytest.raises(NotFound):
        svc.delete("nope", org_id)
