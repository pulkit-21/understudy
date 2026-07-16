"""Deterministic seed data for the mock apps.

Invoices INV-1001/1002 are the "demonstration" pair; the rest exist so the
learned workflow can be run on data it never saw (the generalization proof)
and so an eval harness has a population to measure success-rate over.
"""
from __future__ import annotations

from pydantic import BaseModel


class Invoice(BaseModel):
    id: str
    vendor: str
    date: str        # ISO yyyy-mm-dd
    amount: str      # keep as string: what's on screen is what gets typed
    currency: str
    gl_code: str     # suggested GL code printed on the invoice
    memo: str


INVOICES: dict[str, Invoice] = {
    inv.id: inv
    for inv in [
        Invoice(id="INV-1001", vendor="Northwind Logistics", date="2026-06-02",
                amount="4820.00", currency="USD", gl_code="6100",
                memo="Freight — June consolidation"),
        Invoice(id="INV-1002", vendor="Cloudpeak Hosting", date="2026-06-05",
                amount="1299.00", currency="USD", gl_code="6420",
                memo="Compute reservation, Q3"),
        Invoice(id="INV-1003", vendor="Meridian Legal LLP", date="2026-06-09",
                amount="7500.00", currency="USD", gl_code="6300",
                memo="Contract review retainer"),
        Invoice(id="INV-1004", vendor="Brightline Media", date="2026-06-11",
                amount="2340.50", currency="USD", gl_code="6510",
                memo="Campaign creative, sprint 14"),
        Invoice(id="INV-1005", vendor="Osaka Components KK", date="2026-06-15",
                amount="18990.00", currency="USD", gl_code="5010",
                memo="PCB assemblies, PO-7781"),
        Invoice(id="INV-1006", vendor="Northwind Logistics", date="2026-06-18",
                amount="512.75", currency="USD", gl_code="6100",
                memo="Customs brokerage fee"),
        Invoice(id="INV-1007", vendor="Helios Facilities", date="2026-06-21",
                amount="3105.00", currency="USD", gl_code="6600",
                memo="HVAC maintenance, HQ"),
        Invoice(id="INV-1008", vendor="Cloudpeak Hosting", date="2026-06-26",
                amount="86.40", currency="USD", gl_code="6420",
                memo="Object storage overage"),
    ]
}


class PostedBill(BaseModel):
    """A bill posted into the mock ERP."""

    ref: str          # ERP's own reference, assigned at post time
    vendor: str
    invoice_number: str
    invoice_date: str
    amount: str
    gl_code: str


class ErpState:
    """In-memory ERP ledger with a reset hook for tests and the eval harness."""

    def __init__(self) -> None:
        self.posted: list[PostedBill] = []
        self._seq = 5000

    def post(self, **fields: str) -> PostedBill:
        self._seq += 1
        bill = PostedBill(ref=f"AP-{self._seq}", **fields)
        self.posted.append(bill)
        return bill

    def reset(self) -> None:
        self.posted.clear()
        self._seq = 5000


ERP = ErpState()
