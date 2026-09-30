"""
test_api.py - Stage 3 test: runs the full demo flow through the REST API.

Run from the project folder:   python3 tests/test_api.py
Uses a temporary data folder, so your real data/ folder is not touched.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["INVOICECHAIN_DATA_DIR"] = tempfile.mkdtemp()

from app import app  # noqa: E402  (must be imported after setting the data folder)

client = app.test_client()

INVOICE = {
    "supplier_name": "Acme Traders", "supplier_gstin": "29ABCDE1234F1Z5",
    "buyer_name": "Metro Retail Pvt Ltd", "buyer_gstin": "27PQRST5678K1Z2",
    "invoice_number": "INV-2026-0100", "invoice_date": "2026-09-12", "due_date": "2026-10-12",
    "items": [{"description": "Steel fasteners", "quantity": 10, "rate": 5000}],
}


# Sends a POST request with JSON and returns (status code, JSON body).
def post(url, body=None):
    response = client.post(url, json=body or {})
    return response.status_code, response.get_json()


# Sends a GET request and returns the JSON body.
def get(url):
    return client.get(url).get_json()


if __name__ == "__main__":
    print("Stage 3 - API demo flow")
    post("/api/reset")

    # Fake GST numbers are accepted (demo project), but an empty one is rejected.
    status, body = post("/api/invoices", {**INVOICE, "supplier_gstin": "fake-gst 123", "buyer_gstin": "DEMO"})
    assert status == 201 and body["invoice"]["supplier_gstin"] == "FAKE-GST123"
    status, body = post("/api/invoices", {**INVOICE, "supplier_gstin": "  "})
    assert status == 400

    # Step 1: supplier creates an invoice and sends it to Bank of BrokeChain.
    status, body = post("/api/invoices", INVOICE)
    assert status == 201
    invoice = body["invoice"]
    assert invoice["subtotal"] == 50000 and invoice["gst_amount"] == 9000 and invoice["total"] == 59000
    print(f"  1. invoice created, fingerprint {invoice['fingerprint'][:16]}...")
    status, body = post("/api/finance-request", {"invoice_id": invoice["id"], "bank": "bank-of-brokechain"})
    assert status == 201
    request_1 = body["request"]

    # Step 2: Bank of BrokeChain approves and mines. All 3 chains update.
    status, body = post(f"/api/banks/bank-of-brokechain/approve/{request_1['id']}")
    assert status == 200 and body["ok"]
    status, body = post("/api/banks/bank-of-brokechain/mine")
    assert status == 200 and all(b["accepted"] for b in body["broadcast"])
    for bank in ["bank-of-brokechain", "no-coincidence-bank", "trust-me-bro-bank"]:
        assert len(get(f"/api/banks/{bank}/chain")["chain"]) == 2
    assert get("/api/validate")["all_match"]
    print("  2. approved + mined by Bank of BrokeChain, all 3 chains have 2 blocks")

    # Step 3: supplier sends the SAME invoice to No Coincidence Bank.
    status, body = post("/api/finance-request", {"invoice_id": invoice["id"], "bank": "no-coincidence-bank"})
    assert status == 201
    request_2 = body["request"]

    # Step 4: No Coincidence approves -> fraud alert.
    status, body = post(f"/api/banks/no-coincidence-bank/approve/{request_2['id']}")
    assert status == 409 and body["fraud"]
    assert "Already financed by Bank of BrokeChain" in body["error"]
    print(f"  3-4. {body['error']}")

    # A re-typed copy of the invoice (lowercase, different date format) is caught too.
    status, body = post("/api/invoices", {**INVOICE, "invoice_number": " inv-2026-0100", "invoice_date": "12/09/2026",
                                          "supplier_gstin": "29abcde1234f1z5"})
    assert body["invoice"]["fingerprint"] == invoice["fingerprint"]
    _, body = post("/api/finance-request", {"invoice_id": body["invoice"]["id"], "bank": "trust-me-bro-bank"})
    status, body = post(f"/api/banks/trust-me-bro-bank/approve/{body['request']['id']}")
    assert status == 409
    print("  re-typed copy of the invoice also blocked")

    # Approved at one bank but NOT mined yet -> a second bank must still get a fraud alert.
    _, body = post("/api/invoices", {**INVOICE, "invoice_number": "INV-2026-0200"})
    invoice_2 = body["invoice"]
    _, body = post("/api/finance-request", {"invoice_id": invoice_2["id"], "bank": "bank-of-brokechain"})
    status, _ = post(f"/api/banks/bank-of-brokechain/approve/{body['request']['id']}")
    assert status == 200
    _, body = post("/api/finance-request", {"invoice_id": invoice_2["id"], "bank": "no-coincidence-bank"})
    status, body = post(f"/api/banks/no-coincidence-bank/approve/{body['request']['id']}")
    assert status == 409 and "Already approved by Bank of BrokeChain" in body["error"]
    post("/api/banks/bank-of-brokechain/mine")
    print("  approved-but-not-mined blocked .. OK")

    # Verify page: lookup by fingerprint and by invoice details.
    # By invoice number only (typed messily). Three invoices share this number: the original and the
    # re-typed copy (same fingerprint -> financed) plus the fake-GST invoice (different fingerprint).
    _, body = post("/api/verify", {"invoice_number": " inv-2026-0100 "})
    statuses = sorted(r["status"] for r in body["results"])
    assert statuses == ["financed", "financed", "not_financed"]
    assert all(r["bank_name"] == "Bank of BrokeChain" for r in body["results"] if r["status"] == "financed")
    _, body = post("/api/verify", {"fingerprint": invoice["fingerprint"]})
    assert body["results"][0]["status"] == "financed"
    _, body = post("/api/verify", {"fingerprint": "a" * 64})
    assert body["results"][0]["status"] == "not_financed"
    status, _ = post("/api/verify", {"invoice_number": "DOES-NOT-EXIST"})
    assert status == 404
    # An approved-but-not-mined invoice shows as pending.
    _, body = post("/api/invoices", {**INVOICE, "invoice_number": "INV-2026-0300"})
    _, body = post("/api/finance-request", {"invoice_id": body["invoice"]["id"], "bank": "trust-me-bro-bank"})
    post(f"/api/banks/trust-me-bro-bank/approve/{body['request']['id']}")
    _, body = post("/api/verify", {"invoice_number": "INV-2026-0300"})
    assert body["results"][0]["status"] == "pending" and body["results"][0]["bank_name"] == "Trust Me Bro Bank"
    post("/api/banks/trust-me-bro-bank/mine")
    print("  verify endpoint ................. OK")

    # Step 5: tamper demo -> validation catches it and Trust Me Bro falls out of sync.
    status, _ = post("/api/tamper", {"bank": "trust-me-bro-bank", "block_index": 9, "record_index": 0})
    assert status == 400  # a block that does not exist
    status, body = post("/api/tamper", {"bank": "trust-me-bro-bank", "block_index": 1, "record_index": 0})
    assert "INV-2026-0100" in body["message"]
    assert status == 200
    report = get("/api/validate")
    trustmebro = [b for b in report["banks"] if b["bank_id"] == "trust-me-bro-bank"][0]
    assert not report["all_match"] and not trustmebro["valid"] and trustmebro["errors"][0]["index"] == 1
    status, body = post("/api/banks/trust-me-bro-bank/mine")  # nothing pending
    print(f"  5. tamper detected: {trustmebro['errors'][0]['reason']}")

    # Consensus repairs the tampered node.
    _, body = post("/api/consensus")
    assert body["updated"] == ["Trust Me Bro Bank"] and body["network"]["all_match"]
    print("  consensus repaired Trust Me Bro Bank")

    # Stats and demo data.
    stats = get("/api/stats")
    assert stats["fraud_blocked"] == 3 and stats["invoices_financed"] == 3 and stats["chain_length"] == 4
    status, body = post("/api/demo-data")
    assert status == 200
    stats = body["stats"]
    assert stats["total_invoices"] == 4 and stats["chain_length"] == 3 and stats["fraud_blocked"] == 1
    assert stats["network"]["all_match"]
    assert len([r for r in get("/api/banks/trust-me-bro-bank/requests") if r["status"] == "pending"]) == 1
    print(f"  demo data: {stats['total_invoices']} invoices, chain length {stats['chain_length']}, "
          f"{stats['fraud_blocked']} fraud blocked")

    # Every page loads.
    for page in ["/", "/supplier", "/bank", "/explorer", "/verify"]:
        assert client.get(page).status_code == 200, page
    print("  all 5 pages load ................ OK")
    print("All API tests passed.")
