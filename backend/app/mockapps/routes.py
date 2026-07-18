"""Mock finance apps: Vendra (invoice portal) and LedgerOne (ERP).

These are deliberately boring, deterministic, and server-rendered. They exist
so the demo never depends on a third-party site: stable data-testids, stable
copy, seeded data, and a reset hook. The two apps get different brand colors
so the demo visibly crosses "system boundaries" like real finance work does.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .seed import ERP, INVOICES

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
_RECORDER_JS = Path(__file__).parent / "static" / "recorder.js"

# Map a human status label to a CSS badge class (see base.html).
_STATUS_CLASS = {
    "Approved": "approved", "Pending review": "pending", "On hold": "hold",
    "Paid": "paid", "Posted": "posted",
}
templates.env.filters["status_class"] = lambda s: _STATUS_CLASS.get(s, "posted")

PORTAL_BRAND = {"brand_name": "Vendra", "brand_color": "#31589c"}
ERP_BRAND = {"brand_name": "LedgerOne", "brand_color": "#1f7a5c"}

router = APIRouter()


@router.get("/recorder.js")
def recorder_js():
    """The in-browser recorder, served into the mock apps (see base.html)."""
    return FileResponse(_RECORDER_JS, media_type="application/javascript")


@router.get("/rrweb.min.js")
def rrweb_js():
    """Vendored rrweb record bundle — powers the Sentry-style session replay."""
    return FileResponse(Path(__file__).parent / "static" / "rrweb.min.js",
                        media_type="application/javascript")


# ---- Vendra: invoice portal -------------------------------------------------

@router.get("/portal", response_class=HTMLResponse)
def portal_list(request: Request):
    return templates.TemplateResponse(
        request, "portal_list.html",
        {**PORTAL_BRAND, "invoices": list(INVOICES.values())},
    )


@router.get("/portal/invoice/{invoice_id}", response_class=HTMLResponse)
def portal_detail(request: Request, invoice_id: str):
    inv = INVOICES.get(invoice_id)
    if not inv:
        raise HTTPException(404, f"no invoice {invoice_id}")
    return templates.TemplateResponse(
        request, "portal_detail.html", {**PORTAL_BRAND, "inv": inv}
    )


# ---- LedgerOne: mock ERP ----------------------------------------------------

@router.get("/erp", response_class=HTMLResponse)
def erp_list(request: Request, posted: str | None = None):
    flash = f"Bill {posted} posted to accounts payable." if posted else None
    return templates.TemplateResponse(
        request, "erp_list.html",
        {**ERP_BRAND, "bills": ERP.posted, "flash": flash},
    )


@router.get("/erp/new", response_class=HTMLResponse)
def erp_new_form(request: Request, resilience: str | None = None):
    # ?resilience=drop-testids renders the same form WITHOUT data-testid hooks —
    # simulating an ERP redesign that broke our selectors. The executor must then
    # self-heal via accessible role+name. Used by the resilience test and a live
    # UI demo; the labels stay intact so role+name resolution still works.
    return templates.TemplateResponse(
        request, "erp_new.html",
        {**ERP_BRAND, "drop_testids": resilience == "drop-testids"},
    )


@router.post("/erp/new")
def erp_post_bill(
    vendor: str = Form(...),
    invoice_number: str = Form(...),
    invoice_date: str = Form(...),
    amount: str = Form(...),
    gl_code: str = Form(...),
):
    bill = ERP.post(
        vendor=vendor, invoice_number=invoice_number,
        invoice_date=invoice_date, amount=amount, gl_code=gl_code,
    )
    return RedirectResponse(f"/erp?posted={bill.ref}", status_code=303)


# ---- LedgerOne: vendor master (a second, multi-field task) -------------------

@router.get("/erp/vendors", response_class=HTMLResponse)
def erp_vendors(request: Request, created: str | None = None):
    flash = f"Vendor {created} created." if created else None
    return templates.TemplateResponse(
        request, "erp_vendors.html",
        {**ERP_BRAND, "vendors": ERP.vendors, "flash": flash},
    )


@router.get("/erp/vendors/new", response_class=HTMLResponse)
def erp_vendor_new_form(request: Request):
    return templates.TemplateResponse(request, "erp_vendor_new.html", ERP_BRAND)


@router.post("/erp/vendors/new")
def erp_create_vendor(
    vendor_name: str = Form(...),
    email: str = Form(...),
    payment_terms: str = Form(...),
    tax_id: str = Form(...),
):
    v = ERP.add_vendor(vendor_name=vendor_name, email=email,
                       payment_terms=payment_terms, tax_id=tax_id)
    return RedirectResponse(f"/erp/vendors?created={v.ref}", status_code=303)


# ---- LedgerOne: payments (a third task — a gated state change) --------------

@router.get("/erp/payments", response_class=HTMLResponse)
def erp_payments(request: Request, paid: str | None = None):
    flash = f"Payment recorded for {paid}." if paid else None
    return templates.TemplateResponse(
        request, "erp_payments.html",
        {**ERP_BRAND, "bills": ERP.posted, "flash": flash},
    )


@router.get("/erp/payments/{ref}", response_class=HTMLResponse)
def erp_payment_form(request: Request, ref: str):
    bill = ERP.find_bill(ref)
    if bill is None:
        raise HTTPException(404, f"no bill {ref}")
    return templates.TemplateResponse(
        request, "erp_payment_new.html", {**ERP_BRAND, "bill": bill}
    )


@router.post("/erp/payments/{ref}")
def erp_record_payment(
    ref: str,
    paid_date: str = Form(...),
    payment_method: str = Form(...),
):
    bill = ERP.record_payment(ref, paid_date=paid_date, payment_method=payment_method)
    if bill is None:
        raise HTTPException(404, f"no unpaid bill {ref}")
    return RedirectResponse(f"/erp/payments?paid={bill.ref}", status_code=303)


@router.post("/erp/_reset")
def erp_reset():
    """Test/eval hook: wipe the ledger so runs start from a known state. Disabled
    unless UNDERSTUDY_ENABLE_TEST_HOOKS is set — otherwise it's an anonymous,
    destructive endpoint against the shared ledger in production."""
    from ..config import get_settings
    if not get_settings().enable_test_hooks:
        raise HTTPException(404)
    ERP.reset()
    return {"ok": True}
