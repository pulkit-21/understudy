"""Mock finance apps: Vendra (invoice portal) and LedgerOne (ERP).

These are deliberately boring, deterministic, and server-rendered. They exist
so the demo never depends on a third-party site: stable data-testids, stable
copy, seeded data, and a reset hook. The two apps get different brand colors
so the demo visibly crosses "system boundaries" like real finance work does.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from .seed import ERP, INVOICES

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

PORTAL_BRAND = {"brand_name": "Vendra", "brand_color": "#31589c"}
ERP_BRAND = {"brand_name": "LedgerOne", "brand_color": "#1f7a5c"}

router = APIRouter()


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
def erp_new_form(request: Request):
    return templates.TemplateResponse(request, "erp_new.html", ERP_BRAND)


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


@router.post("/erp/_reset")
def erp_reset():
    """Test/eval hook: wipe the ledger so runs start from a known state."""
    ERP.reset()
    return {"ok": True}
