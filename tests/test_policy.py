"""Policy-governed approvals: the executor may auto-resolve a gate when the
workflow's policy says so, but only when it can confidently evaluate the rule.
Everything else falls through to a human — fail safe, never open.
"""
from __future__ import annotations

import asyncio

import pytest

from app.domain.trace import TargetInfo
from app.domain.workflow import (
    ActionType,
    ApprovalMode,
    ApprovalPolicy,
    RiskLevel,
    WorkflowSpec,
    WorkflowStep,
)
from app.engine.runner import Run, Runner, RunStatus
from tests.test_executor import FakeSink


def _policy_spec(mode: ApprovalMode, threshold: float | None = None) -> WorkflowSpec:
    return WorkflowSpec(
        name="policy",
        approval_policy=ApprovalPolicy(mode=mode, auto_approve_below=threshold,
                                       amount_key="amount"),
        steps=[
            WorkflowStep(intent="read amount", action=ActionType.EXTRACT,
                         target=TargetInfo(testid="inv-amount"),
                         extract_key="amount"),
            WorkflowStep(intent="post the bill", action=ActionType.CLICK,
                         target=TargetInfo(testid="post-bill", role="button"),
                         risk=RiskLevel.COMMIT, requires_approval=True),
        ],
    )


async def _await_status(run, status, tries=200):
    for _ in range(tries):
        if run.status == status:
            return True
        await asyncio.sleep(0.01)
    return False


@pytest.mark.asyncio
async def test_policy_auto_approves_below_threshold():
    spec = _policy_spec(ApprovalMode.AUTO_BELOW_AMOUNT, threshold=5000)
    run = Run(workflow_id=spec.id)
    sink = FakeSink(extract_values={"inv-amount": "100.00"})
    result = await Runner(spec, run, sink).execute()

    assert result.status == RunStatus.COMPLETED
    assert ("click", "post-bill") in sink.actions          # it did post
    ev = [(e.kind, e.actor) for e in result.events]
    assert ("auto_approved", "policy") in ev               # by policy, not human
    assert not any(k == "awaiting_approval" for k, _ in ev)  # never waited


@pytest.mark.asyncio
async def test_policy_escalates_at_or_above_threshold():
    spec = _policy_spec(ApprovalMode.AUTO_BELOW_AMOUNT, threshold=5000)
    run = Run(workflow_id=spec.id)
    sink = FakeSink(extract_values={"inv-amount": "9999.00"})
    runner = Runner(spec, run, sink)
    task = asyncio.create_task(runner.execute())

    assert await _await_status(run, RunStatus.AWAITING_APPROVAL)
    assert ("click", "post-bill") not in sink.actions      # gate held
    runner.approve()
    result = await asyncio.wait_for(task, timeout=2)
    assert result.status == RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_unparseable_amount_falls_through_to_human():
    spec = _policy_spec(ApprovalMode.AUTO_BELOW_AMOUNT, threshold=5000)
    run = Run(workflow_id=spec.id)
    sink = FakeSink(extract_values={"inv-amount": "N/A"})
    runner = Runner(spec, run, sink)
    task = asyncio.create_task(runner.execute())
    assert await _await_status(run, RunStatus.AWAITING_APPROVAL)  # safe default
    runner.reject()
    result = await asyncio.wait_for(task, timeout=2)
    assert result.status == RunStatus.REJECTED


@pytest.mark.asyncio
async def test_default_policy_always_asks():
    spec = _policy_spec(ApprovalMode.ALWAYS_ASK)  # the safe default
    run = Run(workflow_id=spec.id)
    sink = FakeSink(extract_values={"inv-amount": "1.00"})  # tiny, still asks
    runner = Runner(spec, run, sink)
    task = asyncio.create_task(runner.execute())
    assert await _await_status(run, RunStatus.AWAITING_APPROVAL)
    runner.approve()
    assert (await asyncio.wait_for(task, timeout=2)).status == RunStatus.COMPLETED


@pytest.mark.asyncio
async def test_awaiting_state_is_persisted_at_the_gate():
    """The approval inbox reads persisted status, so reaching a gate must fire
    the persist hook with status=awaiting_approval (not just start + terminal)."""
    spec = _policy_spec(ApprovalMode.ALWAYS_ASK)
    run = Run(workflow_id=spec.id)
    seen: list[RunStatus] = []
    runner = Runner(spec, run, FakeSink(),
                    on_state_change=lambda: seen.append(run.status))
    task = asyncio.create_task(runner.execute())
    assert await _await_status(run, RunStatus.AWAITING_APPROVAL)
    assert RunStatus.AWAITING_APPROVAL in seen
    runner.approve()
    await asyncio.wait_for(task, timeout=2)


def test_policy_cannot_remove_the_gate_from_a_commit_step():
    """Even with an auto-approve policy, the commit step must still declare
    requires_approval — the structural invariant is independent of policy."""
    spec = _policy_spec(ApprovalMode.AUTO_BELOW_AMOUNT, threshold=5000)
    spec.steps[-1].requires_approval = False
    assert any("requires_approval" in p for p in spec.validate_references())
