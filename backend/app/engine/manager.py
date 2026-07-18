"""RunManager: owns live runs, their SSE queues, and browser lifecycles.

In-memory for live control (approve/reject, SSE); durable state lives in the
run repository. Every method is org-scoped: a run is tagged with the org that
started it, and approve/reject/get refuse a run that isn't the caller's.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..domain.workflow import WorkflowSpec
from .runner import PlaywrightSink, Run, RunEvent, Runner, RunStatus

if TYPE_CHECKING:
    from ..repos import RunRepo


class RunManager:
    def __init__(self, base_url: str, run_repo: RunRepo,
                 headless: bool = True, max_concurrency: int = 4):
        self.base_url = base_url
        self.repo = run_repo
        self.headless = headless
        # bounded worker pool: cap simultaneous Chromium instances so a big
        # batch can't exhaust memory. Excess runs queue on the semaphore.
        self._sem = asyncio.Semaphore(max_concurrency)
        self.max_concurrency = max_concurrency
        self.runs: dict[str, Run] = {}
        self.run_org: dict[str, str] = {}
        self.runners: dict[str, Runner] = {}
        self.queues: dict[str, asyncio.Queue] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def start_run(self, spec: WorkflowSpec, params: dict[str, str],
                  org_id: str, batch_id: str | None = None) -> Run:
        run = Run(workflow_id=spec.id, params=params)
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.runs[run.id] = run
        self.run_org[run.id] = org_id
        self.queues[run.id] = queue
        self.repo.save(run, org_id, batch_id=batch_id)  # visible in history now
        self._tasks[run.id] = asyncio.create_task(
            self._execute(spec, run, queue, org_id, batch_id))
        return run

    async def _execute(self, spec: WorkflowSpec, run: Run,
                       queue: asyncio.Queue, org_id: str,
                       batch_id: str | None) -> None:
        from playwright.async_api import async_playwright

        try:
            # self._sem caps concurrent browsers (bounded worker pool)
            async with self._sem, async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.headless)
                page = await browser.new_page()
                runner = Runner(
                    spec, run, PlaywrightSink(page), queue,
                    on_state_change=lambda: self.repo.save(
                        run, org_id, batch_id=batch_id))
                self.runners[run.id] = runner
                await runner.execute()
                await browser.close()
        except Exception as e:  # a run must always settle
            run.status = RunStatus.FAILED
            run.events.append(
                RunEvent(kind="run_failed", detail=f"{type(e).__name__}: {e}"))
        finally:
            await queue.put(None)  # SSE sentinel: stream is over
            self.repo.save(run, org_id, batch_id=batch_id)
            self.runners.pop(run.id, None)

    def _owns(self, run_id: str, org_id: str) -> bool:
        return self.run_org.get(run_id) == org_id

    def approve(self, run_id: str, org_id: str) -> bool:
        if not self._owns(run_id, org_id):
            return False
        runner = self.runners.get(run_id)
        if runner is None:
            return False
        runner.approve()
        return True

    def reject(self, run_id: str, org_id: str) -> bool:
        if not self._owns(run_id, org_id):
            return False
        runner = self.runners.get(run_id)
        if runner is None:
            return False
        runner.reject()
        return True

    def get(self, run_id: str, org_id: str) -> Run | None:
        # live run (in memory) wins, but only for its owning org
        if self._owns(run_id, org_id) and run_id in self.runs:
            return self.runs[run_id]
        return self.repo.get(run_id, org_id)

    def list(self, org_id: str, limit: int = 100,
             statuses: list[str] | None = None,
             batch_id: str | None = None) -> list[dict]:
        return self.repo.list(org_id, limit=limit, statuses=statuses,
                              batch_id=batch_id)
