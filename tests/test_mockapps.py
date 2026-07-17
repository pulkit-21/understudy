"""Mock-app contract tests.

The mock apps are the demo stage; if a testid or route drifts, recorded
traces and learned workflows silently break. These tests pin the contract.
"""
from fastapi.testclient import TestClient

from app.main import app
from app.mockapps.seed import ERP

client = TestClient(app)


def setup_function(_):
    ERP.reset()


def test_portal_lists_all_seeded_invoices():
    html = client.get("/portal").text
    for inv_id in ("INV-1001", "INV-1005", "INV-1008"):
        assert inv_id in html
        assert f'data-testid="open-{inv_id}"' in html


def test_portal_detail_exposes_provenance_testids():
    html = client.get("/portal/invoice/INV-1003").text
    for tid in ("inv-number", "inv-vendor", "inv-date", "inv-amount", "inv-gl"):
        assert f'data-testid="{tid}"' in html
    assert "Meridian Legal LLP" in html


def test_portal_404_for_unknown_invoice():
    assert client.get("/portal/invoice/INV-9999").status_code == 404


def test_erp_post_bill_roundtrip():
    resp = client.post("/erp/new", data={
        "vendor": "Northwind Logistics", "invoice_number": "INV-1001",
        "invoice_date": "2026-06-02", "amount": "4820.00", "gl_code": "6100",
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "posted to accounts payable" in resp.text
    assert 'data-testid="bill-INV-1001"' in resp.text
    assert len(ERP.posted) == 1
    assert ERP.posted[0].ref == "AP-5001"


def test_erp_reset_gives_clean_slate_for_evals():
    client.post("/erp/new", data={
        "vendor": "x", "invoice_number": "i", "invoice_date": "d",
        "amount": "1", "gl_code": "6100"})
    client.post("/erp/_reset")
    assert ERP.posted == []
    # ref sequence restarts too — evals depend on deterministic refs
    client.post("/erp/new", data={
        "vendor": "x", "invoice_number": "i", "invoice_date": "d",
        "amount": "1", "gl_code": "6100"})
    assert ERP.posted[0].ref == "AP-5001"


# ---- enriched invoice fields (PO, tax, due date, status, line items) --------

def test_portal_detail_exposes_enriched_testids():
    html = client.get("/portal/invoice/INV-1001").text
    for tid in ("inv-po", "inv-due", "inv-tax", "inv-status", "inv-total"):
        assert f'data-testid="{tid}"' in html
    assert "PO-4471" in html               # PO number rendered
    assert 'data-testid="line-items"' in html   # line-item breakdown present


def test_portal_list_has_status_and_search_controls():
    html = client.get("/portal").text
    assert 'data-testid="invoice-search"' in html
    assert 'data-testid="status-filter"' in html
    assert "badge" in html                 # status badges rendered


# ---- payment lifecycle (posted -> paid), the gated third task ---------------

def _post_a_bill():
    client.post("/erp/new", data={
        "vendor": "Northwind Logistics", "invoice_number": "INV-1001",
        "invoice_date": "2026-06-02", "amount": "4820.00", "gl_code": "6100"})
    return ERP.posted[0].ref


def test_payments_page_lists_posted_bills():
    ref = _post_a_bill()
    html = client.get("/erp/payments").text
    assert f'data-testid="payable-{ref}"' in html
    assert f'data-testid="pay-{ref}"' in html   # a "record payment" action
    assert "Posted" in html


def test_record_payment_flips_bill_to_paid():
    ref = _post_a_bill()
    resp = client.post(f"/erp/payments/{ref}", data={
        "paid_date": "2026-07-01", "payment_method": "ACH"},
        follow_redirects=True)
    assert resp.status_code == 200
    assert "Payment recorded" in resp.text
    bill = ERP.find_bill(ref)
    assert bill.status == "Paid"
    assert bill.paid_date == "2026-07-01" and bill.payment_method == "ACH"


def test_record_payment_is_idempotent_guarded():
    ref = _post_a_bill()
    client.post(f"/erp/payments/{ref}",
                data={"paid_date": "2026-07-01", "payment_method": "ACH"})
    # paying an already-paid bill is rejected (no double payment)
    resp = client.post(f"/erp/payments/{ref}",
                       data={"paid_date": "2026-07-02", "payment_method": "Wire"})
    assert resp.status_code == 404


def test_payment_form_404_for_unknown_bill():
    assert client.get("/erp/payments/AP-9999").status_code == 404
