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
