"""Workflow executor.

Architecture: the Runner walks the spec and makes decisions (template
resolution, approval gates, event emission); an ActionSink performs the
actual browser actions. Two sinks exist:

  * PlaywrightSink — the real thing, with a self-healing target-resolution
    chain (testid -> role+name -> css) so cosmetic DOM changes don't break
    replays; each hop is reported so the UI can show "healed via role".
  * FakeSink (in tests) — records intended actions, letting us test approval
    gating, param resolution, and ordering without launching Chromium.

Determinism first: the executor replays the spec's literal targets. An LLM
is a *fallback* for when all three locator strategies fail (stretch goal —
see CLAUDE.md), not the main path. Deterministic replays are reproducible,
cheap, auditable — and auditability is the point in finance.
"""
from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from ..domain.trace import TargetInfo
from ..domain.workflow import (
    ActionType,
    ApprovalMode,
    WorkflowSpec,
    WorkflowStep,
    render_template,
)

# ---- run state & events ------------------------------------------------------

class RunStatus(str, Enum):
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class RunEvent(BaseModel):
    """One audit-log entry. actor is 'agent' or 'human' — every state change
    is attributable, which is the audit-trail property finance teams need."""

    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor: str = "agent"
    kind: str  # step_started | step_done | awaiting_approval | approved |
               # rejected | extracted | healed | run_done | run_failed
    step_id: str | None = None
    detail: str = ""


class Run(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    workflow_id: str
    params: dict[str, str] = Field(default_factory=dict)
    status: RunStatus = RunStatus.RUNNING
    current_step: int = 0
    events: list[RunEvent] = Field(default_factory=list)
    extracts: dict[str, str] = Field(default_factory=dict)


# ---- the sink boundary -------------------------------------------------------

class ActionSink(Protocol):
    async def navigate(self, url: str) -> None: ...
    async def click(self, target: TargetInfo) -> str: ...
    async def fill(self, target: TargetInfo, value: str) -> str: ...
    async def select(self, target: TargetInfo, value: str) -> str: ...
    async def extract(self, target: TargetInfo) -> tuple[str, str]: ...
    async def assert_text(self, target: TargetInfo, expected: str) -> str: ...
    async def screenshot(self) -> bytes | None: ...


# ---- runner -------------------------------------------------------------------

class ApprovalRejected(Exception):
    pass


class Runner:
    def __init__(self, spec: WorkflowSpec, run: Run, sink: ActionSink,
                 event_queue: asyncio.Queue | None = None,
                 on_state_change: Callable[[], None] | None = None):
        self.spec = spec
        self.run = run
        self.sink = sink
        self._queue = event_queue
        # persist hook: fires when the run reaches/leaves a gate so the DB (and
        # thus the approval inbox + dashboard) reflect awaiting_approval, not
        # just start + terminal states.
        self._on_state_change = on_state_change
        self._approval = asyncio.Event()
        self._rejected = False

    def _persist(self) -> None:
        if self._on_state_change:
            self._on_state_change()

    # -- external control (called by the API layer) --
    def approve(self) -> None:
        self._log("approved", actor="human",
                  detail="Human approved the gated step.")
        self._approval.set()

    def reject(self) -> None:
        self._rejected = True
        self._log("rejected", actor="human",
                  detail="Human rejected the gated step; run stopped.")
        self._approval.set()

    # -- main loop --
    async def execute(self) -> Run:
        try:
            for i, step in enumerate(self.spec.steps):
                self.run.current_step = i
                await self._gate_if_needed(step)
                await self._do(step)
            self.run.status = RunStatus.COMPLETED
            self._log("run_done", detail="Workflow completed.")
        except ApprovalRejected:
            self.run.status = RunStatus.REJECTED
        except Exception as e:
            self.run.status = RunStatus.FAILED
            self._log("run_failed", detail=f"{type(e).__name__}: {e}")
        return self.run

    def _policy_auto_approve(self) -> tuple[bool, str]:
        """Consult the workflow's approval policy against live extracts. Returns
        (auto_approve, reason). Anything it can't confidently evaluate returns
        False so the step falls through to a human — fail safe, never open."""
        p = self.spec.approval_policy
        if p.mode != ApprovalMode.AUTO_BELOW_AMOUNT or p.auto_approve_below is None:
            return False, ""
        raw = self.run.extracts.get(p.amount_key)
        if raw is None:
            return False, f"no '{p.amount_key}' value to check — needs a human"
        try:
            amount = float(str(raw).replace(",", "").replace("$", "").strip())
        except ValueError:
            return False, f"amount {raw!r} isn't a number — needs a human"
        if amount < p.auto_approve_below:
            return True, (f"amount {amount:g} is below the "
                          f"{p.auto_approve_below:g} auto-approve threshold")
        return False, (f"amount {amount:g} is at/above the "
                       f"{p.auto_approve_below:g} threshold — needs a human")

    async def _gate_if_needed(self, step: WorkflowStep) -> None:
        if not step.requires_approval:
            return
        auto, reason = self._policy_auto_approve()
        if auto:
            self._log("auto_approved", actor="policy",
                      detail=f"Auto-approved by policy: {reason}")
            return
        detail = f"Paused before: {step.intent}"
        if reason:
            detail += f" — {reason}"
        self.run.status = RunStatus.AWAITING_APPROVAL
        self._log("awaiting_approval", step_id=step.id, detail=detail)
        self._persist()                      # DB now shows awaiting -> inbox
        self._approval.clear()
        await self._approval.wait()          # hard pause — no timeout bypass
        if self._rejected:
            raise ApprovalRejected()
        self.run.status = RunStatus.RUNNING
        self._persist()                      # left the gate

    async def _do(self, step: WorkflowStep) -> None:
        self._log("step_started", step_id=step.id, detail=step.intent)
        params = {**self.run.params,
                  **{f"extract.{k}": v for k, v in self.run.extracts.items()}}

        how = ""
        if step.action == ActionType.NAVIGATE:
            await self.sink.navigate(render_template(step.url or "", params))
        elif step.action == ActionType.CLICK:
            how = await self.sink.click(step.target)          # type: ignore[arg-type]
        elif step.action == ActionType.FILL:
            value = render_template(step.value or "", params)
            how = await self.sink.fill(step.target, value)    # type: ignore[arg-type]
        elif step.action == ActionType.SELECT:
            value = render_template(step.value or "", params)
            how = await self.sink.select(step.target, value)  # type: ignore[arg-type]
        elif step.action == ActionType.EXTRACT:
            text, how = await self.sink.extract(step.target)  # type: ignore[arg-type]
            self.run.extracts[step.extract_key or "value"] = text
            self._log("extracted", step_id=step.id,
                      detail=f"{step.extract_key} = {text!r}")
        elif step.action == ActionType.ASSERT_TEXT:
            expected = render_template(step.value or "", params)
            how = await self.sink.assert_text(step.target, expected)  # type: ignore[arg-type]

        if how and how != "testid":
            self._log("healed", step_id=step.id,
                      detail=f"Located target via fallback strategy: {how}")
        self._log("step_done", step_id=step.id, detail=step.intent)
        await self._capture_frame(step)

    async def _capture_frame(self, step: WorkflowStep) -> None:
        """Best-effort live screenshot streamed to watchers (queue-only, never
        persisted — base64 frames would bloat the audit log). Shows the agent
        actually driving the browser."""
        if self._queue is None:
            return
        try:
            img = await self.sink.screenshot()
        except Exception:
            return
        if not img:
            return
        import base64
        frame = RunEvent(kind="frame", step_id=step.id,
                         detail=base64.b64encode(img).decode())
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(frame)

    def _log(self, kind: str, actor: str = "agent",
             step_id: str | None = None, detail: str = "") -> None:
        evt = RunEvent(kind=kind, actor=actor, step_id=step_id, detail=detail)
        self.run.events.append(evt)
        if self._queue is not None:
            with contextlib.suppress(asyncio.QueueFull):
                self._queue.put_nowait(evt)


# ---- the real sink -------------------------------------------------------------

class PlaywrightSink:
    """Executes actions against a live page with a self-healing locator chain."""

    def __init__(self, page) -> None:
        self.page = page

    async def _locate(self, t: TargetInfo):
        """testid -> role+name -> css. Returns (locator, strategy_name)."""
        if t.testid:
            loc = self.page.get_by_test_id(t.testid)
            if await loc.count():
                return loc.first, "testid"
        if t.role and t.name:
            loc = self.page.get_by_role(t.role, name=t.name)
            if await loc.count():
                return loc.first, "role+name"
        if t.css:
            loc = self.page.locator(t.css)
            if await loc.count():
                return loc.first, "css"
        raise LookupError(f"could not locate {t.describe()}")

    async def navigate(self, url: str) -> None:
        await self.page.goto(url, wait_until="load")

    async def click(self, target: TargetInfo) -> str:
        loc, how = await self._locate(target)
        await loc.click()
        await self.page.wait_for_load_state("load")
        return how

    async def fill(self, target: TargetInfo, value: str) -> str:
        loc, how = await self._locate(target)
        await loc.fill(value)
        return how

    async def select(self, target: TargetInfo, value: str) -> str:
        loc, how = await self._locate(target)
        await loc.select_option(value)
        return how

    async def extract(self, target: TargetInfo) -> tuple[str, str]:
        loc, how = await self._locate(target)
        return (await loc.inner_text()).strip(), how

    async def assert_text(self, target: TargetInfo, expected: str) -> str:
        loc, how = await self._locate(target)
        actual = (await loc.inner_text()).strip()
        if expected not in actual:
            raise AssertionError(
                f"validation failed: expected {expected!r} in {actual!r}")
        return how

    async def screenshot(self) -> bytes | None:
        try:
            return await self.page.screenshot(type="jpeg", quality=60)
        except Exception:
            return None
