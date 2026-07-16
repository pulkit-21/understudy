"""RunManager: owns live runs, their SSE queues, and browser lifecycles.

In-memory by design — a run is an ephemeral process; the durable artifacts
are the trace, the spec, and the run's event log (persisted on completion).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

from ..models.workflow import WorkflowSpec
from .runner import Run, Runner, PlaywrightSink


class RunManager:
    def __init__(self, base_url: str, log_dir: Path, headless: bool = True):
        self.base_url = base_url
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.headless = headless
        self.runs: dict[str, Run] = {}
        self.runners: dict[str, Runner] = {}
        self.queues: dict[str, asyncio.Queue] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def start_run(self, spec: WorkflowSpec, params: dict[str, str]) -> Run:
        run = Run(workflow_id=spec.id, params=params)
        queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self.runs[run.id] = run
        self.queues[run.id] = queue
        self._tasks[run.id] = asyncio.create_task(
            self._execute(spec, run, queue))
        return run

    async def _execute(self, spec: WorkflowSpec, run: Run,
                       queue: asyncio.Queue) -> None:
        from playwright.async_api import async_playwright

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=self.headless)
                page = await browser.new_page()
                runner = Runner(spec, run, PlaywrightSink(page), queue)
                self.runners[run.id] = runner
                await runner.execute()
                await browser.close()
        except Exception as e:  # startup failures (browser missing, etc.)
            run.status = run.status.FAILED
            run.events.append(type(run.events[0])(  # RunEvent
                kind="run_failed", detail=f"{type(e).__name__}: {e}"
            ) if run.events else _failed_event(e))
        finally:
            await queue.put(None)  # SSE sentinel: stream is over
            self._persist(run)
            self.runners.pop(run.id, None)

    def approve(self, run_id: str) -> bool:
        runner = self.runners.get(run_id)
        if runner is None:
            return False
        runner.approve()
        return True

    def reject(self, run_id: str) -> bool:
        runner = self.runners.get(run_id)
        if runner is None:
            return False
        runner.reject()
        return True

    def get(self, run_id: str) -> Optional[Run]:
        return self.runs.get(run_id)

    def _persist(self, run: Run) -> None:
        path = self.log_dir / f"{run.id}.json"
        path.write_text(json.dumps(run.model_dump(mode="json"), indent=2,
                                   default=str))


def _failed_event(e: Exception):
    from .runner import RunEvent
    return RunEvent(kind="run_failed", detail=f"{type(e).__name__}: {e}")
