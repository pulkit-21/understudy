"""The canonical demonstration trace.

A faithful, hand-built replica of what inject.js emits when a user demonstrates
the invoice task: open portal -> open INV-1001 -> (read values) -> go to ERP ->
fill the bill form -> post. It's the single source of the seed demonstration, used
by both the seed script and the test suite, so demo and tests exercise the exact
same data path. (Lives in the app, not tests/, so runtime code never imports test
modules — importing test code pulls in test-only env setup.)
"""
from __future__ import annotations

from .models.trace import (
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


def seed_if_empty(traces, workflows, org_id: str,
                  base: str = DEFAULT_BASE) -> bool:
    """Idempotent boot-time seed: if the org has no workflows yet, install the
    demonstration trace and a deterministic induced workflow so a fresh deploy
    is immediately demoable. Uses the offline heuristic inducer (no network /
    API key needed at boot); the LLM legibility pass is available on demand via
    the induce endpoint. Returns True if it seeded."""
    from .induction.heuristic import induce_heuristic

    if workflows.list(org_id):
        return False
    trace = build_demo_trace(base=base)
    trace.id = "demo-seed-001"
    traces.save(trace, org_id)
    spec = induce_heuristic(trace)
    spec.id = "wf-demo-invoice"
    workflows.save(spec, org_id)
    return True
