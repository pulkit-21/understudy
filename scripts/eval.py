"""Eval harness: run the learned workflow over EVERY seeded invoice and score it.

Success criterion per invoice: the run completes AND the ERP row matches the
portal's source-of-truth field-for-field (vendor is checked only when the
spec carries it). This is the quantitative "does it actually work" signal —
run it after any change to the recorder, inducer, or executor.

Usage:  python scripts/eval.py            (spins up its own server)
Output: a per-invoice table and an overall success rate.
"""
from __future__ import annotations

import asyncio
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn

from app.engine.runner import PlaywrightSink, Run, Runner, RunStatus
from app.induction.heuristic import induce_heuristic
from app.main import app
from app.mockapps.seed import ERP, INVOICES
from app.seed import DEFAULT_BASE, build_demo_trace

PORT = 8778
BASE = f"http://127.0.0.1:{PORT}"


def start_server() -> uvicorn.Server:
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    return server


async def run_one(spec, invoice, pw) -> tuple[bool, str]:
    # Only the invoice id is supplied; vendor/date/amount/GL are read live off
    # this invoice's own page. So a PASS means the learned procedure correctly
    # located, read, and posted each invoice's real data — not that we fed it.
    params = {"invoice_id": invoice.id}
    before = len(ERP.posted)
    browser = await pw.chromium.launch(headless=True)
    try:
        page = await browser.new_page()
        run = Run(workflow_id=spec.id, params=params)
        runner = Runner(spec, run, PlaywrightSink(page))
        task = asyncio.create_task(runner.execute())
        while run.status == RunStatus.RUNNING:
            await asyncio.sleep(0.05)
        if run.status == RunStatus.AWAITING_APPROVAL:
            runner.approve()  # eval auto-approves; production never does
        result = await asyncio.wait_for(task, timeout=60)
    finally:
        await browser.close()

    if result.status != RunStatus.COMPLETED:
        detail = result.events[-1].detail if result.events else ""
        return False, f"run {result.status.value}: {detail}"
    new = ERP.posted[before:]
    if len(new) != 1:
        return False, f"expected exactly 1 new bill, got {len(new)}"
    bill = new[0]
    mismatches = [
        f"{field}: erp={got!r} portal={want!r}"
        for field, got, want in [
            ("vendor", bill.vendor, invoice.vendor),
            ("invoice_number", bill.invoice_number, invoice.id),
            ("invoice_date", bill.invoice_date, invoice.date),
            ("amount", bill.amount, invoice.amount),
            ("gl_code", bill.gl_code, invoice.gl_code),
        ]
        if got != want
    ]
    return (not mismatches), ("; ".join(mismatches) or "ok")


async def run_bad_invoice(spec, pw) -> tuple[bool, str]:
    """Feed an invoice id that doesn't exist. A correct system fails the run
    WITHOUT posting anything — safe degradation is a success here, not a pass/
    fail of the happy path."""
    before = len(ERP.posted)
    browser = await pw.chromium.launch(headless=True)
    try:
        page = await browser.new_page()
        run = Run(workflow_id=spec.id, params={"invoice_id": "INV-9999"})
        runner = Runner(spec, run, PlaywrightSink(page))
        result = await asyncio.wait_for(runner.execute(), timeout=60)
    finally:
        await browser.close()
    safe = result.status == RunStatus.FAILED and len(ERP.posted) == before
    return safe, ("failed safely, nothing posted" if safe
                  else f"UNSAFE: status={result.status.value}, "
                       f"posted={len(ERP.posted) - before}")


async def main() -> int:
    from playwright.async_api import async_playwright

    server = start_server()
    ERP.reset()

    trace = build_demo_trace()
    for e in trace.events:
        e.url = e.url.replace(DEFAULT_BASE, BASE)
    spec = induce_heuristic(trace)
    problems = spec.validate_references()
    if problems:
        print("SPEC INVALID:", problems)
        return 1

    passed = 0
    async with async_playwright() as pw:
        print(f"{'invoice':<10} {'result':<6} detail")
        print("-" * 60)
        for invoice in INVOICES.values():
            ok, detail = await run_one(spec, invoice, pw)
            passed += ok
            print(f"{invoice.id:<10} {'PASS' if ok else 'FAIL':<6} {detail}")

        # failure-mode row: a bad invoice must degrade safely
        safe, detail = await run_bad_invoice(spec, pw)
        print(f"{'INV-9999':<10} {'SAFE' if safe else 'UNSAFE':<6} {detail}")

    total = len(INVOICES)
    print("-" * 60)
    print(f"success rate: {passed}/{total} ({100 * passed / total:.0f}%)  "
          f"| bad-invoice degrades safely: {'yes' if safe else 'NO'}")
    server.should_exit = True
    return 0 if passed == total and safe else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
