"""Executor tests via FakeSink — no browser needed.

The properties under test are the safety-critical ones:
  * a requires_approval step HARD-pauses execution until a human approves,
  * a rejection stops the run before the gated action fires,
  * {{param}} and {{extract.*}} references resolve into real typed values,
  * an unresolved reference fails the run instead of typing '{{amount}}'.
"""
import asyncio

import pytest

from app.domain.trace import TargetInfo
from app.domain.workflow import (
    ActionType,
    RiskLevel,
    WorkflowParameter,
    WorkflowSpec,
    WorkflowStep,
)
from app.engine.runner import Run, Runner, RunStatus


class FakeSink:
    def __init__(self, extract_values=None):
        self.actions: list[tuple] = []
        self.extract_values = extract_values or {}

    async def navigate(self, url):
        self.actions.append(("navigate", url))

    async def click(self, target):
        self.actions.append(("click", target.testid))
        return "testid"

    async def fill(self, target, value):
        self.actions.append(("fill", target.testid, value))
        return "testid"

    async def select(self, target, value):
        self.actions.append(("select", target.testid, value))
        return "testid"

    async def extract(self, target):
        self.actions.append(("extract", target.testid))
        return self.extract_values.get(target.testid, ""), "testid"

    async def assert_text(self, target, expected):
        self.actions.append(("assert_text", target.testid, expected))
        return "testid"

    async def screenshot(self):
        return None


def _tid(testid, role="textbox", name="x"):
    return TargetInfo(testid=testid, role=role, name=name)


def spec_with_gate() -> WorkflowSpec:
    return WorkflowSpec(
        name="gated",
        parameters=[WorkflowParameter(key="amount")],
        steps=[
            WorkflowStep(intent="fill amount", action=ActionType.FILL,
                         target=_tid("field-amount"), value="{{amount}}",
                         risk=RiskLevel.WRITE),
            WorkflowStep(intent="post the bill", action=ActionType.CLICK,
                         target=_tid("post-bill", role="button"),
                         risk=RiskLevel.COMMIT, requires_approval=True),
        ],
    )


@pytest.mark.asyncio
async def test_run_pauses_at_gate_and_resumes_on_approval():
    spec = spec_with_gate()
    run = Run(workflow_id=spec.id, params={"amount": "99.50"})
    sink = FakeSink()
    runner = Runner(spec, run, sink)
    task = asyncio.create_task(runner.execute())

    # the run must reach AWAITING_APPROVAL and go no further on its own
    for _ in range(100):
        if run.status == RunStatus.AWAITING_APPROVAL:
            break
        await asyncio.sleep(0.01)
    assert run.status == RunStatus.AWAITING_APPROVAL
    assert ("click", "post-bill") not in sink.actions  # gate held

    runner.approve()
    result = await asyncio.wait_for(task, timeout=2)
    assert result.status == RunStatus.COMPLETED
    assert ("fill", "field-amount", "99.50") in sink.actions  # param resolved
    assert sink.actions[-1] == ("click", "post-bill")

    # audit trail: human approval recorded with actor identity
    kinds = [(e.kind, e.actor) for e in run.events]
    assert ("awaiting_approval", "agent") in kinds
    assert ("approved", "human") in kinds


@pytest.mark.asyncio
async def test_rejection_stops_run_before_commit():
    spec = spec_with_gate()
    run = Run(workflow_id=spec.id, params={"amount": "1.00"})
    sink = FakeSink()
    runner = Runner(spec, run, sink)
    task = asyncio.create_task(runner.execute())
    for _ in range(100):
        if run.status == RunStatus.AWAITING_APPROVAL:
            break
        await asyncio.sleep(0.01)
    runner.reject()
    result = await asyncio.wait_for(task, timeout=2)
    assert result.status == RunStatus.REJECTED
    assert ("click", "post-bill") not in sink.actions  # commit never happened


@pytest.mark.asyncio
async def test_reject_arriving_before_the_gate_stops_without_hanging():
    """Regression: a reject signalled before the run reaches its gate must stop
    the run (REJECTED), not be swallowed by the gate's _approval.clear() and
    leave the runner blocked on wait() forever."""
    spec = spec_with_gate()
    run = Run(workflow_id=spec.id, params={"amount": "1.00"})
    sink = FakeSink()
    runner = Runner(spec, run, sink)
    runner.reject()  # arrives before execution reaches (or starts) the gate
    result = await asyncio.wait_for(runner.execute(), timeout=2)  # must not hang
    assert result.status == RunStatus.REJECTED
    assert ("click", "post-bill") not in sink.actions  # commit never fired


@pytest.mark.asyncio
async def test_extract_output_feeds_later_fill():
    spec = WorkflowSpec(
        name="provenance",
        parameters=[],
        steps=[
            WorkflowStep(intent="read amount off invoice page",
                         action=ActionType.EXTRACT,
                         target=_tid("inv-amount"), extract_key="amount"),
            WorkflowStep(intent="type it into the ERP",
                         action=ActionType.FILL,
                         target=_tid("field-amount"),
                         value="{{extract.amount}}"),
        ],
    )
    run = Run(workflow_id=spec.id)
    sink = FakeSink(extract_values={"inv-amount": "4820.00"})
    result = await Runner(spec, run, sink).execute()
    assert result.status == RunStatus.COMPLETED
    assert ("fill", "field-amount", "4820.00") in sink.actions
    assert run.extracts == {"amount": "4820.00"}


@pytest.mark.asyncio
async def test_unresolved_reference_fails_loudly_not_silently():
    spec = WorkflowSpec(
        name="broken",
        steps=[WorkflowStep(intent="fill", action=ActionType.FILL,
                            target=_tid("field-amount"),
                            value="{{never_declared}}")],
    )
    run = Run(workflow_id=spec.id)
    sink = FakeSink()
    result = await Runner(spec, run, sink).execute()
    assert result.status == RunStatus.FAILED
    # crucially: nothing was typed — '{{never_declared}}' never hit the page
    assert not any(a[0] == "fill" for a in sink.actions)


def test_validate_references_catches_ungated_commit():
    spec = WorkflowSpec(
        name="unsafe",
        steps=[WorkflowStep(intent="pay", action=ActionType.CLICK,
                            target=_tid("pay", role="button"),
                            risk=RiskLevel.COMMIT, requires_approval=False)],
    )
    problems = spec.validate_references()
    assert any("requires_approval" in p for p in problems)
