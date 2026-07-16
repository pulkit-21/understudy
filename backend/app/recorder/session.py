"""The demonstration browser: a Playwright-controlled Chromium the user
performs the task in while Understudy watches.

Why this design (vs. a Chrome extension): the recorder runs server-side next
to the executor, needs no store review, and Playwright's expose_binding gives
a clean page->Python event channel. The extension is a stretch goal; its
capture script would be ~this same inject.js.

Local use: headful window pops up for the user. On a server there is no
display — the deploy story records inside the hosted mock apps via the same
inject.js served as a <script>, or falls back to pre-recorded traces (see
CLAUDE.md, "deployed recording").
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from ..models.trace import SemanticEvent, Trace

INJECT_JS = (Path(__file__).parent / "inject.js").read_text()


class RecordingSession:
    """One live demonstration. Owns a browser context and accumulates events."""

    def __init__(self, name: str, start_url: str, headless: bool = False):
        self.trace = Trace(name=name, start_url=start_url)
        self._start_url = start_url
        self._headless = headless
        # Playwright objects are created lazily in start(); typed Any because the
        # import is local (keeps playwright out of the module import path).
        self._pw: Any = None
        self._browser: Any = None
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        from playwright.async_api import async_playwright

        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=self._headless)
        context = await self._browser.new_context()

        async def on_event(_source, payload: str) -> None:
            try:
                data = json.loads(payload)
                self.trace.events.append(SemanticEvent.model_validate(data))
            except Exception:
                pass  # a malformed event must never kill the demonstration

        await context.expose_binding("__understudy_emit", on_event)
        await context.add_init_script(INJECT_JS)

        page = await context.new_page()
        page.on("close", lambda _: self._stopped.set())
        await page.goto(self._start_url)

    async def stop(self) -> Trace:
        self._stopped.set()
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        return self.trace
