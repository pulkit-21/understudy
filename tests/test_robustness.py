"""Robustness: the real world, not the happy path.

These are the "above and beyond" tests — the failure modes an actual AP
automation hits: a redesigned page that dropped our selectors, a bad invoice
id, an action that throws mid-run, concurrent runs, and a client that connects
to the audit stream late. Each asserts the system degrades *safely*: it never
posts a bill it shouldn't, always settles the run, and always leaves an
attributable audit trail.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest
import uvicorn

from app.executor.runner import (
    PlaywrightSink,
    Run,
    Runner,
    RunStatus,
)
from app.induction.heuristic import induce_heuristic
from app.main import app
from app.mockapps.seed import ERP
from app.models.trace import TargetInfo
from app.models.workflow import (
    ActionType,
    RiskLevel,
    WorkflowParameter,
    WorkflowSpec,
    WorkflowStep,
)

PORT = 8778
BASE = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="module")
def live_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    yield BASE
    server.should_exit = True
    thread.join(timeout=5)


def _learn(demo_trace, base):
    for e in demo_trace.events:
        e.url = e.url.replace("http://localhost:8000", base)
    return induce_heuristic(demo_trace)


# ---- 1. self-healing when the page drops our test hooks ----------------------

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_self_heals_when_erp_drops_testids(live_server, demo_trace):
    """The ERP 'got redesigned' and removed every data-testid. The learned
    workflow must still post the right bill by falling back to accessible
    role+name — and the audit trail must record that it healed."""
    from playwright.async_api import async_playwright

    ERP.reset()
    spec = _learn(demo_trace, live_server)
    # point the ERP navigation at the testid-stripped variant of the same form
    for step in spec.steps:
        if step.action == ActionType.NAVIGATE and step.url and "/erp/new" in step.url:
            step.url = step.url + "?resilience=drop-testids"

    run = Run(workflow_id=spec.id, params={"invoice_id": "INV-1005"})
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        runner = Runner(spec, run, PlaywrightSink(page))
        task = asyncio.create_task(runner.execute())
        for _ in range(400):
            if run.status == RunStatus.AWAITING_APPROVAL:
                break
            await asyncio.sleep(0.05)
        assert run.status == RunStatus.AWAITING_APPROVAL, run.status
        runner.approve()
        result = await asyncio.wait_for(task, timeout=30)
        await browser.close()

    # it still worked, on the exact same data, despite the missing testids
    assert result.status == RunStatus.COMPLETED
    assert len(ERP.posted) == 1
    assert ERP.posted[0].vendor == "Osaka Components KK"
    # and it told us how: at least one ERP step healed via role+name
    healed = [e for e in result.events if e.kind == "healed"]
    assert healed, "expected self-healing events when testids were removed"
    assert any("role+name" in e.detail for e in healed)


# ---- 2. bad input: an invoice that doesn't exist -----------------------------

@pytest.mark.e2e
@pytest.mark.asyncio
async def test_unknown_invoice_fails_safely_without_posting(live_server,
                                                            demo_trace):
    """A run for an invoice that isn't in the portal must fail cleanly: no bill
    posted, the run settles FAILED with an audit event, and it never reaches the
    approval gate (there's nothing valid to approve)."""
    from playwright.async_api import async_playwright

    ERP.reset()
    spec = _learn(demo_trace, live_server)
    run = Run(workflow_id=spec.id, params={"invoice_id": "INV-9999"})
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        runner = Runner(spec, run, PlaywrightSink(page))
        result = await asyncio.wait_for(runner.execute(), timeout=30)
        await browser.close()

    assert result.status == RunStatus.FAILED
    assert ERP.posted == []                       # nothing committed
    # never asked a human to approve a run built on missing data
    assert not any(e.kind == "awaiting_approval" for e in result.events)
    assert any(e.kind == "run_failed" for e in result.events)


# ---- 3. an action throws mid-run ---------------------------------------------

class _ExplodingSink:
    """Fails on fill — simulates a locator/timeout error partway through."""
    def __init__(self):
        self.actions: list[tuple] = []

    async def navigate(self, url):
        self.actions.append(("navigate", url))

    async def click(self, target):
        self.actions.append(("click", target.testid))
        return "testid"

    async def fill(self, target, value):
        raise RuntimeError("element detached / timeout")

    async def select(self, target, value):
        return "testid"

    async def extract(self, target):
        return "x", "testid"

    async def assert_text(self, target, expected):
        return "testid"

    async def screenshot(self):
        return None


@pytest.mark.asyncio
async def test_midrun_failure_settles_failed_and_never_commits():
    spec = WorkflowSpec(
        name="explodes",
        parameters=[WorkflowParameter(key="amount")],
        steps=[
            WorkflowStep(intent="fill amount", action=ActionType.FILL,
                         target=TargetInfo(testid="field-amount", role="textbox",
                                           name="Amount"),
                         value="{{amount}}", risk=RiskLevel.WRITE),
            WorkflowStep(intent="post the bill", action=ActionType.CLICK,
                         target=TargetInfo(testid="post-bill", role="button",
                                           name="Post bill"),
                         risk=RiskLevel.COMMIT, requires_approval=True),
        ],
    )
    run = Run(workflow_id=spec.id, params={"amount": "10.00"})
    sink = _ExplodingSink()
    result = await Runner(spec, run, sink).execute()

    assert result.status == RunStatus.FAILED
    assert ("click", "post-bill") not in sink.actions   # commit never reached
    assert not any(e.kind == "awaiting_approval" for e in result.events)
    failed = [e for e in result.events if e.kind == "run_failed"]
    assert failed and "RuntimeError" in failed[0].detail


# ---- 4. concurrent runs stay isolated ----------------------------------------

def _provenance_gated_spec() -> WorkflowSpec:
    return WorkflowSpec(
        name="concurrent",
        steps=[
            WorkflowStep(intent="read amount", action=ActionType.EXTRACT,
                         target=TargetInfo(testid="inv-amount"),
                         extract_key="amount"),
            WorkflowStep(intent="type it", action=ActionType.FILL,
                         target=TargetInfo(testid="field-amount"),
                         value="{{extract.amount}}", risk=RiskLevel.WRITE),
            WorkflowStep(intent="post", action=ActionType.CLICK,
                         target=TargetInfo(testid="post-bill", role="button"),
                         risk=RiskLevel.COMMIT, requires_approval=True),
        ],
    )


@pytest.mark.asyncio
async def test_concurrent_runs_have_isolated_state_and_approvals():
    """Two runs in flight at once: each reads its own value, and approving one
    while rejecting the other resolves them independently."""
    from tests.test_executor import FakeSink

    spec = _provenance_gated_spec()
    run_a = Run(workflow_id=spec.id)
    run_b = Run(workflow_id=spec.id)
    sink_a = FakeSink(extract_values={"inv-amount": "111.00"})
    sink_b = FakeSink(extract_values={"inv-amount": "222.00"})
    runner_a = Runner(spec, run_a, sink_a)
    runner_b = Runner(spec, run_b, sink_b)

    task_a = asyncio.create_task(runner_a.execute())
    task_b = asyncio.create_task(runner_b.execute())
    for _ in range(200):
        if run_a.status == run_b.status == RunStatus.AWAITING_APPROVAL:
            break
        await asyncio.sleep(0.01)
    assert run_a.status == RunStatus.AWAITING_APPROVAL
    assert run_b.status == RunStatus.AWAITING_APPROVAL

    # state didn't cross-contaminate
    assert run_a.extracts == {"amount": "111.00"}
    assert run_b.extracts == {"amount": "222.00"}

    runner_a.approve()
    runner_b.reject()
    res_a = await asyncio.wait_for(task_a, timeout=2)
    res_b = await asyncio.wait_for(task_b, timeout=2)

    assert res_a.status == RunStatus.COMPLETED
    assert res_b.status == RunStatus.REJECTED
    assert ("fill", "field-amount", "111.00") in sink_a.actions
    assert ("click", "post-bill") in sink_a.actions       # a committed
    assert ("click", "post-bill") not in sink_b.actions   # b did not


# ---- 5. a client connects to the audit stream late (SSE reconnect) -----------

def test_sse_replays_full_history_for_a_late_subscriber():
    """Reconnecting to a run that already finished must replay its entire audit
    log, not start blank — the property a dropped SSE connection relies on."""
    from fastapi.testclient import TestClient

    from app.executor.runner import RunEvent

    client = TestClient(app)
    run = Run(workflow_id="wf-x", params={"invoice_id": "INV-1005"})
    run.events = [
        RunEvent(kind="step_started", detail="open portal"),
        RunEvent(kind="extracted", detail="amount = '18990.00'"),
        RunEvent(kind="approved", actor="human", detail="Human approved."),
        RunEvent(kind="run_done", detail="Workflow completed."),
    ]
    run.status = RunStatus.COMPLETED
    # persist so the endpoint (memory miss) hydrates it from the DB
    from app.main import runs as run_manager
    run_manager.repo.save(run)

    body = client.get(f"/api/runs/{run.id}/events").text
    assert "open portal" in body
    assert "amount = '18990.00'" in body
    assert "Human approved." in body
    assert "Workflow completed." in body
