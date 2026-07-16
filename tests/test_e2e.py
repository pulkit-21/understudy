"""End-to-end proof: demonstration trace -> induced workflow -> REAL headless
Chromium replays it against the live mock apps ON DATA THE DEMO NEVER TOUCHED
-> pauses at the approval gate -> human approves -> the bill lands in the ERP.

This one test is the product working. It runs in CI (headless chromium) and
doubles as the generalization proof: the demo used INV-1001, the run posts
INV-1005 with completely different values.
"""
import asyncio
import threading

import pytest
import uvicorn

from app.executor.runner import PlaywrightSink, Run, Runner, RunStatus
from app.induction.heuristic import induce_heuristic
from app.main import app
from app.mockapps.seed import ERP

PORT = 8777
BASE = f"http://127.0.0.1:{PORT}"

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def live_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    import time
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    yield BASE
    server.should_exit = True
    thread.join(timeout=5)


@pytest.mark.asyncio
async def test_learned_workflow_generalizes_to_unseen_invoice(
        live_server, demo_trace):
    from playwright.async_api import async_playwright

    ERP.reset()

    # 1. Learn from the demonstration (which was performed on INV-1001)
    for e in demo_trace.events:   # retarget fixture URLs at the test server
        e.url = e.url.replace("http://localhost:8000", live_server)
    spec = induce_heuristic(demo_trace)
    assert spec.validate_references() == []

    # 2. Run it on an invoice the demonstration never touched. We pass ONLY the
    #    invoice id — vendor/date/amount/GL are read live off INV-1005's own
    #    page by the learned `extract` steps. Feeding those values would prove
    #    nothing; reading them is the whole point.
    params = {"invoice_id": "INV-1005"}
    run = Run(workflow_id=spec.id, params=params)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        runner = Runner(spec, run, PlaywrightSink(page))
        task = asyncio.create_task(runner.execute())

        # 3. It must stop at the gate with nothing posted yet
        for _ in range(200):
            if run.status == RunStatus.AWAITING_APPROVAL:
                break
            await asyncio.sleep(0.05)
        assert run.status == RunStatus.AWAITING_APPROVAL
        assert ERP.posted == []

        # 4. Human approves; the commit goes through
        runner.approve()
        result = await asyncio.wait_for(task, timeout=30)
        await browser.close()

    assert result.status == RunStatus.COMPLETED
    assert len(ERP.posted) == 1
    bill = ERP.posted[0]
    # Every field below the invoice id was READ LIVE off INV-1005's own page by
    # the learned extract steps — none of it was passed in.
    assert bill.invoice_number == "INV-1005"
    assert bill.vendor == "Osaka Components KK"
    assert bill.invoice_date == "2026-06-15"
    assert bill.amount == "18990.00"
    assert bill.gl_code == "5010"
    # the demo's own data (INV-1001) must NOT have leaked into the run
    assert bill.vendor != "Northwind Logistics"
    assert bill.amount != "4820.00"
    # extraction actually happened (audit trail records each read)
    assert any(e.kind == "extracted" for e in result.events)
