"""The canonical demonstration trace.

A faithful, hand-built replica of what inject.js emits when a user demonstrates
the invoice task: open portal -> open INV-1001 -> (read values) -> go to ERP ->
fill the bill form -> post. It's the single source of the seed demonstration, used
by both the seed script and the test suite, so demo and tests exercise the exact
same data path. (Lives in the app, not tests/, so runtime code never imports test
modules — importing test code pulls in test-only env setup.)
"""
from __future__ import annotations

from .domain.trace import (
    EventType,
    ReadableField,
    SemanticEvent,
    TargetInfo,
    Trace,
)

DEFAULT_BASE = "http://localhost:8000"

# What the recorder snapshots on the INV-1001 detail page: labelled, testid'd
# values (see mockapps/templates/portal_detail.html). Induction matches typed
# values against these to produce `extract` steps with real targets.
INV1001_FIELDS = [
    ReadableField(testid="inv-number", label="Invoice number", value="INV-1001"),
    ReadableField(testid="inv-vendor", label="Vendor", value="Northwind Logistics"),
    ReadableField(testid="inv-date", label="Invoice date", value="2026-06-02"),
    ReadableField(testid="inv-amount", label="Amount", value="4820.00"),
    ReadableField(testid="inv-currency", label="Currency", value="USD"),
    ReadableField(testid="inv-gl", label="Suggested GL code", value="6100"),
    ReadableField(testid="inv-memo", label="Memo", value="Freight"),
]


def build_demo_trace(base: str = DEFAULT_BASE) -> Trace:
    ts = iter(range(1_000, 100_000, 1_500))
    ev: list[SemanticEvent] = []

    def add(type_: EventType, url: str, *, target=None, value=None,
            page_title=None, page_text=None, readable_fields=None) -> None:
        ev.append(SemanticEvent(
            type=type_, url=url, ts_ms=next(ts), target=target, value=value,
            page_title=page_title, page_text=page_text,
            readable_fields=readable_fields or []))

    add(EventType.NAVIGATE, f"{base}/portal", page_title="Vendra — Invoices",
        page_text="Received invoices INV-1001 Northwind Logistics 2026-06-02 "
                  "USD 4820.00 Open INV-1002 Cloudpeak Hosting …")
    add(EventType.CLICK, f"{base}/portal",
        target=TargetInfo(role="link", name="Open", testid="open-INV-1001", tag="a"))
    add(EventType.NAVIGATE, f"{base}/portal/invoice/INV-1001",
        page_title="Vendra — INV-1001",
        page_text="Invoice INV-1001 Invoice number INV-1001 Vendor "
                  "Northwind Logistics Invoice date 2026-06-02 Amount 4820.00 "
                  "Currency USD Suggested GL code 6100 Memo Freight",
        readable_fields=INV1001_FIELDS)
    add(EventType.NAVIGATE, f"{base}/erp/new", page_title="LedgerOne — New bill",
        page_text="Enter new bill Vendor name Invoice number Invoice date "
                  "Amount GL code Post bill")
    add(EventType.FILL, f"{base}/erp/new", value="Northwind Logistics",
        target=TargetInfo(role="textbox", name="Vendor name",
                          testid="field-vendor", tag="input"))
    add(EventType.FILL, f"{base}/erp/new", value="INV-1001",
        target=TargetInfo(role="textbox", name="Invoice number",
                          testid="field-invoice-number", tag="input"))
    add(EventType.FILL, f"{base}/erp/new", value="2026-06-02",
        target=TargetInfo(role="textbox", name="Invoice date",
                          testid="field-invoice-date", tag="input"))
    add(EventType.FILL, f"{base}/erp/new", value="4820.00",
        target=TargetInfo(role="textbox", name="Amount",
                          testid="field-amount", tag="input"))
    add(EventType.SELECT, f"{base}/erp/new", value="6100",
        target=TargetInfo(role="combobox", name="GL code",
                          testid="field-gl-code", tag="select"))
    add(EventType.SUBMIT, f"{base}/erp/new",
        target=TargetInfo(role="button", name="Post bill",
                          testid="post-bill", tag="button"))

    return Trace(name="Post vendor invoice to LedgerOne", events=ev,
                 start_url=f"{base}/portal")


def build_vendor_trace(base: str = DEFAULT_BASE) -> Trace:
    """A second demonstration: onboard a vendor in LedgerOne. Every value is
    operator-supplied (no source page to read from), so induction learns a
    MULTI-PARAMETER workflow — the counterpoint to the read-live invoice task."""
    ts = iter(range(1_000, 100_000, 1_500))
    ev: list[SemanticEvent] = []

    def add(type_, url, *, target=None, value=None, page_title=None, page_text=None):
        ev.append(SemanticEvent(type=type_, url=url, ts_ms=next(ts), target=target,
                                value=value, page_title=page_title,
                                page_text=page_text, readable_fields=[]))

    add(EventType.NAVIGATE, f"{base}/erp/vendors/new",
        page_title="LedgerOne — New vendor",
        page_text="Onboard a vendor Vendor name Billing email Payment terms "
                  "Tax ID Create vendor")
    add(EventType.FILL, f"{base}/erp/vendors/new", value="Aurora Instruments Ltd",
        target=TargetInfo(role="textbox", name="Vendor name",
                          testid="field-vendor-name", tag="input"))
    add(EventType.FILL, f"{base}/erp/vendors/new", value="ap@aurora-instruments.example",
        target=TargetInfo(role="textbox", name="Billing email",
                          testid="field-email", tag="input"))
    add(EventType.SELECT, f"{base}/erp/vendors/new", value="Net 30",
        target=TargetInfo(role="combobox", name="Payment terms",
                          testid="field-payment-terms", tag="select"))
    add(EventType.FILL, f"{base}/erp/vendors/new", value="TX-99-4471",
        target=TargetInfo(role="textbox", name="Tax ID",
                          testid="field-tax-id", tag="input"))
    add(EventType.SUBMIT, f"{base}/erp/vendors/new",
        target=TargetInfo(role="button", name="Create vendor",
                          testid="create-vendor", tag="button"))
    return Trace(name="Onboard a vendor in LedgerOne", events=ev,
                 start_url=f"{base}/erp/vendors/new")


def build_payment_trace(base: str = DEFAULT_BASE) -> Trace:
    """A third demonstration: record a payment against a posted bill in
    LedgerOne. The click on a specific bill's "Record payment" link opens a
    run-varying URL (`/erp/payments/AP-5001`), which induction rewrites into a
    parameterized navigate; the payment date + method are operator inputs. The
    final "Confirm payment" is a COMMIT — money moves — so it's gated by default.
    This exercises the *gated state-change* shape, distinct from create-a-record."""
    ts = iter(range(1_000, 100_000, 1_500))
    ev: list[SemanticEvent] = []

    def add(type_, url, *, target=None, value=None, page_title=None, page_text=None):
        ev.append(SemanticEvent(type=type_, url=url, ts_ms=next(ts), target=target,
                                value=value, page_title=page_title,
                                page_text=page_text, readable_fields=[]))

    add(EventType.NAVIGATE, f"{base}/erp/payments",
        page_title="LedgerOne — Payments",
        page_text="Payments Record payments against posted bills Ref Vendor "
                  "Invoice Status Amount")
    add(EventType.CLICK, f"{base}/erp/payments",
        target=TargetInfo(role="link", name="Record payment",
                          testid="pay-AP-5001", tag="a"))
    add(EventType.NAVIGATE, f"{base}/erp/payments/AP-5001",
        page_title="LedgerOne — Record payment",
        page_text="Record payment Vendor Invoice number Amount Payment date "
                  "Payment method Confirm payment")
    add(EventType.FILL, f"{base}/erp/payments/AP-5001", value="2026-07-01",
        target=TargetInfo(role="textbox", name="Payment date",
                          testid="field-paid-date", tag="input"))
    add(EventType.SELECT, f"{base}/erp/payments/AP-5001", value="ACH",
        target=TargetInfo(role="combobox", name="Payment method",
                          testid="field-payment-method", tag="select"))
    add(EventType.SUBMIT, f"{base}/erp/payments/AP-5001",
        target=TargetInfo(role="button", name="Confirm payment",
                          testid="confirm-payment", tag="button"))
    return Trace(name="Record a bill payment in LedgerOne", events=ev,
                 start_url=f"{base}/erp/payments")


DEMO_EMAIL = "demo@understudy.app"
DEMO_PASSWORD = "understudy"


def seed_demo_account(auth) -> str:
    """Ensure the demo account exists; return its org_id. The demo login on the
    sign-in screen uses these credentials so evaluators can get in with one
    click (no real data behind it)."""
    existing = auth.authenticate(DEMO_EMAIL, DEMO_PASSWORD)
    if existing is not None:
        return existing.org_id
    org = auth.create_org(name="Understudy demo")
    user = auth.create_user(DEMO_EMAIL, DEMO_PASSWORD, "Demo user", org.id)
    return user.org_id


# The seed workflows, keyed by a stable trace id. Idempotent per-entry so a
# deployment that already has some of them picks up newly-added ones on boot
# without wiping user data.
_SEED_BUILDERS = (
    ("demo-seed-001", build_demo_trace),        # read-live, 1 input
    ("demo-vendor-001", build_vendor_trace),    # multi-parameter
    ("demo-payment-001", build_payment_trace),  # gated state change
)


def seed_if_empty(traces, workflows, org_id: str,
                  base: str = DEFAULT_BASE) -> bool:
    """Idempotent boot-time seed: install any demonstration workflow the org is
    missing (by stable id) so a fresh deploy is immediately demoable and an
    existing one gains newly-added showcases on the next boot. Uses the offline
    heuristic inducer (no network / API key needed at boot); the LLM legibility
    pass is available on demand via the induce endpoint. Returns True if it
    seeded anything."""
    from .induction.heuristic import induce_heuristic

    existing = {w.id for w in workflows.list(org_id)}
    seeded = False
    for trace_id, builder in _SEED_BUILDERS:
        wf_id = f"wf-{trace_id}"  # same scheme as induce, so re-learning updates it
        if wf_id in existing:
            continue
        trace = builder(base=base)
        trace.id = trace_id
        traces.save(trace, org_id)
        spec = induce_heuristic(trace)
        spec.id = wf_id
        workflows.save(spec, org_id)
        seeded = True
    return seeded
