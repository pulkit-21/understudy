"""Deterministic seed data for the mock apps.

Invoices INV-1001/1002 are the "demonstration" pair; the rest exist so the
learned workflow can be run on data it never saw (the generalization proof)
and so an eval harness has a population to measure success-rate over.

The data is intentionally richer than the demo strictly needs — PO numbers, tax,
due dates, a workflow status, and line-item breakdowns — so the mock apps read
like real finance software and so more varied workflows can be demonstrated over
them (e.g. reading the PO number, filtering by status, recording a payment).
"""
from __future__ import annotations

from pydantic import BaseModel

# Invoice lifecycle in the Vendra portal. "Approved" invoices are the ones AP is
# cleared to post; the demo/eval operate on those.
INVOICE_STATUSES = ("Approved", "Pending review", "On hold", "Paid")


class LineItem(BaseModel):
    description: str
    quantity: str
    unit_price: str
    amount: str


class Invoice(BaseModel):
    id: str
    vendor: str
    date: str          # ISO yyyy-mm-dd
    due_date: str      # ISO yyyy-mm-dd — net terms applied to the invoice date
    amount: str        # gross total; string so what's on screen is what's typed
    tax: str           # tax portion of the gross total
    currency: str
    gl_code: str       # suggested GL code printed on the invoice
    po_number: str     # purchase order this invoice bills against ("" if none)
    status: str        # one of INVOICE_STATUSES
    memo: str
    line_items: list[LineItem] = []


def _li(description: str, quantity: str, unit_price: str, amount: str) -> LineItem:
    return LineItem(description=description, quantity=quantity,
                    unit_price=unit_price, amount=amount)


INVOICES: dict[str, Invoice] = {
    inv.id: inv
    for inv in [
        Invoice(id="INV-1001", vendor="Northwind Logistics", date="2026-06-02",
                due_date="2026-07-02", amount="4820.00", tax="0.00",
                currency="USD", gl_code="6100", po_number="PO-4471",
                status="Approved", memo="Freight — June consolidation",
                line_items=[
                    _li("Ocean freight, 2x 40ft container", "2", "2100.00", "4200.00"),
                    _li("Customs handling & documentation", "1", "620.00", "620.00"),
                ]),
        Invoice(id="INV-1002", vendor="Cloudpeak Hosting", date="2026-06-05",
                due_date="2026-07-05", amount="1299.00", tax="99.00",
                currency="USD", gl_code="6420", po_number="PO-4488",
                status="Approved", memo="Compute reservation, Q3",
                line_items=[
                    _li("Reserved compute, 3-month", "1", "1200.00", "1200.00"),
                    _li("Sales tax", "1", "99.00", "99.00"),
                ]),
        Invoice(id="INV-1003", vendor="Meridian Legal LLP", date="2026-06-09",
                due_date="2026-07-24", amount="7500.00", tax="0.00",
                currency="USD", gl_code="6300", po_number="",
                status="Pending review", memo="Contract review retainer"),
        Invoice(id="INV-1004", vendor="Brightline Media", date="2026-06-11",
                due_date="2026-07-11", amount="2340.50", tax="140.50",
                currency="USD", gl_code="6510", po_number="PO-4501",
                status="Approved", memo="Campaign creative, sprint 14"),
        Invoice(id="INV-1005", vendor="Osaka Components KK", date="2026-06-15",
                due_date="2026-08-14", amount="18990.00", tax="0.00",
                currency="USD", gl_code="5010", po_number="PO-7781",
                status="Approved", memo="PCB assemblies, PO-7781"),
        Invoice(id="INV-1006", vendor="Northwind Logistics", date="2026-06-18",
                due_date="2026-07-18", amount="512.75", tax="0.00",
                currency="USD", gl_code="6100", po_number="PO-4471",
                status="On hold", memo="Customs brokerage fee"),
        Invoice(id="INV-1007", vendor="Helios Facilities", date="2026-06-21",
                due_date="2026-07-21", amount="3105.00", tax="205.00",
                currency="USD", gl_code="6600", po_number="PO-4520",
                status="Approved", memo="HVAC maintenance, HQ"),
        Invoice(id="INV-1008", vendor="Cloudpeak Hosting", date="2026-06-26",
                due_date="2026-07-26", amount="86.40", tax="6.40",
                currency="USD", gl_code="6420", po_number="",
                status="Paid", memo="Object storage overage"),
    ]
}


class PostedBill(BaseModel):
    """A bill posted into the mock ERP."""

    ref: str            # ERP's own reference, assigned at post time
    vendor: str
    invoice_number: str
    invoice_date: str
    amount: str
    gl_code: str
    status: str = "Posted"      # Posted -> Paid once a payment is recorded
    paid_date: str = ""         # set when a payment is recorded
    payment_method: str = ""    # set when a payment is recorded


class Vendor(BaseModel):
    """A vendor onboarded into the mock ERP — a second, multi-field task whose
    values are all operator-supplied (nothing read from a source page), so the
    learned workflow needs several parameters."""

    ref: str
    vendor_name: str
    email: str
    payment_terms: str
    tax_id: str


class ErpState:
    """In-memory ERP ledger with a reset hook for tests and the eval harness."""

    def __init__(self) -> None:
        self.posted: list[PostedBill] = []
        self.vendors: list[Vendor] = []
        self._seq = 5000
        self._vseq = 200

    def post(self, **fields: str) -> PostedBill:
        self._seq += 1
        bill = PostedBill(ref=f"AP-{self._seq}", **fields)
        self.posted.append(bill)
        return bill

    def find_bill(self, ref: str) -> PostedBill | None:
        return next((b for b in self.posted if b.ref == ref), None)

    def record_payment(self, ref: str, paid_date: str,
                       payment_method: str) -> PostedBill | None:
        """Flip a posted bill to Paid. The irreversible, gated step of the
        payment workflow — money leaves the building here."""
        bill = self.find_bill(ref)
        if bill is None or bill.status == "Paid":
            return None
        bill.status = "Paid"
        bill.paid_date = paid_date
        bill.payment_method = payment_method
        return bill

    def add_vendor(self, **fields: str) -> Vendor:
        self._vseq += 1
        vendor = Vendor(ref=f"VEN-{self._vseq}", **fields)
        self.vendors.append(vendor)
        return vendor

    def reset(self) -> None:
        self.posted.clear()
        self.vendors.clear()
        self._seq = 5000
        self._vseq = 200


ERP = ErpState()
