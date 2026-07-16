"""Shared fixtures.

demo_trace is a faithful, hand-built replica of what inject.js emits when a
user demonstrates: open portal -> open INV-1001 -> (read values) -> go to ERP
-> fill the bill form -> post. It doubles as the seed demonstration for the
deployed demo, so tests and demo exercise the same data path.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import pytest

from app.models.trace import EventType, SemanticEvent, TargetInfo, Trace

BASE = "http://localhost:8000"


def _t(**kw) -> TargetInfo:
    return TargetInfo(**kw)


@pytest.fixture()
def demo_trace() -> Trace:
    ts = iter(range(1_000, 100_000, 1_500))
    ev = []

    def add(type_: EventType, url: str, *, target=None, value=None,
            page_title=None, page_text=None):
        ev.append(SemanticEvent(
            type=type_, url=url, ts_ms=next(ts), target=target, value=value,
            page_title=page_title, page_text=page_text))

    add(EventType.NAVIGATE, f"{BASE}/portal", page_title="Vendra — Invoices",
        page_text="Received invoices INV-1001 Northwind Logistics 2026-06-02 "
                  "USD 4820.00 Open INV-1002 Cloudpeak Hosting …")
    add(EventType.CLICK, f"{BASE}/portal",
        target=_t(role="link", name="Open", testid="open-INV-1001", tag="a"))
    add(EventType.NAVIGATE, f"{BASE}/portal/invoice/INV-1001",
        page_title="Vendra — INV-1001",
        page_text="Invoice INV-1001 Invoice number INV-1001 Vendor "
                  "Northwind Logistics Invoice date 2026-06-02 Amount 4820.00 "
                  "Currency USD Suggested GL code 6100 Memo Freight")
    add(EventType.NAVIGATE, f"{BASE}/erp/new", page_title="LedgerOne — New bill",
        page_text="Enter new bill Vendor name Invoice number Invoice date "
                  "Amount GL code Post bill")
    add(EventType.FILL, f"{BASE}/erp/new", value="Northwind Logistics",
        target=_t(role="textbox", name="Vendor name",
                  testid="field-vendor", tag="input"))
    add(EventType.FILL, f"{BASE}/erp/new", value="INV-1001",
        target=_t(role="textbox", name="Invoice number",
                  testid="field-invoice-number", tag="input"))
    add(EventType.FILL, f"{BASE}/erp/new", value="2026-06-02",
        target=_t(role="textbox", name="Invoice date",
                  testid="field-invoice-date", tag="input"))
    add(EventType.FILL, f"{BASE}/erp/new", value="4820.00",
        target=_t(role="textbox", name="Amount",
                  testid="field-amount", tag="input"))
    add(EventType.SELECT, f"{BASE}/erp/new", value="6100",
        target=_t(role="combobox", name="GL code",
                  testid="field-gl-code", tag="select"))
    add(EventType.SUBMIT, f"{BASE}/erp/new",
        target=_t(role="button", name="Post bill",
                  testid="post-bill", tag="button"))

    return Trace(name="Post vendor invoice to LedgerOne", events=ev,
                 start_url=f"{BASE}/portal")
