"""
app.py - The Flask web server: REST API + the five web pages.

Flow of one invoice through the system:
    1. Supplier creates an invoice       -> POST /api/invoices          (stored off-chain)
    2. Supplier sends it to a bank       -> POST /api/finance-request
    3. Bank approves it                  -> POST /api/banks/<bank>/approve/<id>
         - duplicate check on the blockchain; if found -> FRAUD ALERT
         - otherwise the record waits in the bank's pending list
    4. Bank mines a block                -> POST /api/banks/<bank>/mine
         - proof-of-work, then broadcast to the other two banks

Run with:  python3 app.py   then open http://127.0.0.1:5050
"""

import os
import re
import threading
from datetime import date, datetime, timedelta

from flask import Flask, jsonify, render_template, request

from bank_node import BANKS, BankNetwork
from fingerprint import clean_date, clean_text, generate_fingerprint
from storage import load_list, save_list

# ---------- Settings ----------
DATA_DIR = os.environ.get("INVOICECHAIN_DATA_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
INVOICES_FILE = os.path.join(DATA_DIR, "invoices.json")
REQUESTS_FILE = os.path.join(DATA_DIR, "requests.json")
GST_RATE = 0.18        # 18% GST added to every invoice
ADVANCE_RATE = 0.80    # banks lend 80% of the invoice value (a typical invoice-financing advance)
# GST numbers are NOT checked against the real Indian GSTIN format, because this is a
# demo project and fake numbers like "DEMO-SUPPLIER-01" are fine. We only limit the length.
MAX_GSTIN_LENGTH = 30

app = Flask(__name__)
network = BankNetwork(os.path.join(DATA_DIR, "nodes"))
# Only one request may change data at a time, so two clicks can never corrupt the JSON files.
lock = threading.Lock()


# ---------- Small helper functions ----------

# Sends back an error message as JSON with an HTTP status code.
def error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


# Returns the bank node for a bank id, or None if the id is unknown.
def get_bank(bank_id):
    return network.get(bank_id)


# Returns the current time as readable text, e.g. "2026-09-29 17:05:12".
def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Finds one item in a list by its "id" field.
def find_by_id(items, item_id):
    for item in items:
        if item["id"] == item_id:
            return item
    return None


# Suggests the next invoice number, e.g. INV-2026-0005.
def next_invoice_number():
    invoices = load_list(INVOICES_FILE)
    return f"INV-{date.today().year}-{len(invoices) + 1:04d}"


# Checks the invoice form, calculates the totals and fingerprint, and saves the invoice.
# Returns (invoice, None) on success or (None, error_message) if something is wrong.
def create_invoice(data):
    required = ["supplier_name", "supplier_gstin", "buyer_name", "buyer_gstin", "invoice_number", "invoice_date", "due_date"]
    for field in required:
        if not str(data.get(field, "")).strip():
            return None, f"'{field}' is required"

    for field in ["supplier_gstin", "buyer_gstin"]:
        if len(clean_text(data[field])) > MAX_GSTIN_LENGTH:
            return None, f"GST number can be at most {MAX_GSTIN_LENGTH} characters"

    try:
        invoice_date = clean_date(data["invoice_date"])
        due_date = clean_date(data["due_date"])
    except ValueError as e:
        return None, str(e)
    if due_date < invoice_date:
        return None, "Due date cannot be before the invoice date"

    # Totals are calculated on the server so nobody can fake them from the browser.
    items = []
    for item in data.get("items", []):
        try:
            quantity, rate = float(item["quantity"]), float(item["rate"])
        except (KeyError, TypeError, ValueError):
            return None, "Each line item needs a numeric quantity and rate"
        if not str(item.get("description", "")).strip() or quantity <= 0 or rate < 0:
            return None, "Each line item needs a description, a quantity above 0 and a rate of 0 or more"
        items.append({"description": item["description"].strip(), "quantity": quantity, "rate": round(rate, 2),
                      "amount": round(quantity * rate, 2)})
    if not items:
        return None, "Add at least one line item"

    subtotal = round(sum(item["amount"] for item in items), 2)
    gst_amount = round(subtotal * GST_RATE, 2)
    total = round(subtotal + gst_amount, 2)

    invoice = {
        "id": f"I{int(datetime.now().timestamp() * 1000)}",
        "invoice_number": clean_text(data["invoice_number"]),
        "supplier_name": data["supplier_name"].strip(),
        "supplier_gstin": clean_text(data["supplier_gstin"]),
        "buyer_name": data["buyer_name"].strip(),
        "buyer_gstin": clean_text(data["buyer_gstin"]),
        "invoice_date": invoice_date,
        "due_date": due_date,
        "items": items,
        "subtotal": subtotal,
        "gst_rate": GST_RATE,
        "gst_amount": gst_amount,
        "total": total,
        "fingerprint": generate_fingerprint(data["supplier_gstin"], data["buyer_gstin"],
                                            data["invoice_number"], invoice_date, total),
        "created_at": now_text(),
    }
    invoices = load_list(INVOICES_FILE)
    # Make sure ids stay unique even if two invoices are created in the same millisecond.
    while find_by_id(invoices, invoice["id"]):
        invoice["id"] += "x"
    invoices.append(invoice)
    save_list(INVOICES_FILE, invoices)
    return invoice, None


# Creates a financing request from a supplier to a bank.
# Returns (request, None) on success or (None, error_message).
def create_finance_request(invoice_id, bank_id):
    node = get_bank(bank_id)
    if node is None:
        return None, "Unknown bank"
    invoice = find_by_id(load_list(INVOICES_FILE), invoice_id)
    if invoice is None:
        return None, "Invoice not found"

    requests_list = load_list(REQUESTS_FILE)
    for existing in requests_list:
        if existing["invoice_id"] == invoice_id and existing["bank_id"] == bank_id and existing["status"] in ("pending", "approved", "financed"):
            return None, f"This invoice is already with {node.name} (status: {existing['status']})"

    finance_request = {
        "id": f"REQ-{len(requests_list) + 1:04d}",
        "invoice_id": invoice_id,
        "invoice_number": invoice["invoice_number"],
        "supplier_name": invoice["supplier_name"],
        "buyer_name": invoice["buyer_name"],
        "invoice_total": invoice["total"],
        "amount_requested": round(invoice["total"] * ADVANCE_RATE, 2),
        "fingerprint": invoice["fingerprint"],
        "bank_id": bank_id,
        "bank_name": node.name,
        "status": "pending",   # pending -> approved -> financed, or rejected / fraud
        "message": "Waiting for the bank to review",
        "block_index": None,
        "created_at": now_text(),
        "updated_at": now_text(),
    }
    requests_list.append(finance_request)
    save_list(REQUESTS_FILE, requests_list)
    return finance_request, None


# Bank approves a request: runs the duplicate check on the blockchain.
# Returns (result_dict, http_status).
def approve_request(bank_id, request_id):
    node = get_bank(bank_id)
    requests_list = load_list(REQUESTS_FILE)
    finance_request = find_by_id(requests_list, request_id)
    if node is None or finance_request is None or finance_request["bank_id"] != bank_id:
        return {"ok": False, "error": "Request not found for this bank"}, 404
    if finance_request["status"] != "pending":
        return {"ok": False, "error": f"Request is already '{finance_request['status']}'"}, 409

    record = {
        "fingerprint": finance_request["fingerprint"],
        "bank_name": node.name,
        "amount_financed": finance_request["amount_requested"],
        "financing_date": date.today().isoformat(),
        "supplier_name": finance_request["supplier_name"],
    }
    approved, duplicate = network.approve(bank_id, record)
    finance_request["updated_at"] = now_text()

    if not approved:
        finance_request["status"] = "fraud"
        finance_request["message"] = f"FRAUD ALERT: {duplicate['message']}"
        save_list(REQUESTS_FILE, requests_list)
        return {"ok": False, "fraud": True, "duplicate": duplicate, "request": finance_request,
                "error": f"FRAUD ALERT: Duplicate invoice. {duplicate['message']}"}, 409

    finance_request["status"] = "approved"
    finance_request["message"] = "Approved - waiting to be mined into a block"
    save_list(REQUESTS_FILE, requests_list)
    return {"ok": True, "request": finance_request,
            "message": "No duplicate found on the blockchain. Record added to pending list."}, 200


# Mines a block at a bank, broadcasts it, and updates the status of every affected request.
# Returns (result_dict, http_status).
def mine_block(bank_id):
    node = get_bank(bank_id)
    if node is None:
        return {"ok": False, "error": "Unknown bank"}, 404
    if not node.blockchain.pending_records:
        return {"ok": False, "error": "No pending records to mine"}, 400
    if not node.blockchain.is_chain_valid():
        return {"ok": False, "error": f"{node.name}'s copy of the chain is invalid (tampered). "
                                      "Use 'Sync Nodes' in the Explorer to repair it first."}, 409

    block, broadcast = network.mine_and_broadcast(bank_id)

    # Requests whose invoice is now in the block become "financed".
    mined = {record["fingerprint"] for record in block.records}
    # Requests that another bank had approved but not mined yet are now duplicates.
    dropped = {(b["bank_id"], fp) for b in broadcast for fp in b["dropped_fingerprints"]}

    requests_list = load_list(REQUESTS_FILE)
    for r in requests_list:
        if r["status"] != "approved":
            continue
        if r["bank_id"] == bank_id and r["fingerprint"] in mined:
            r["status"], r["block_index"] = "financed", block.index
            r["message"] = f"Financed - recorded in block #{block.index}"
            r["updated_at"] = now_text()
        elif (r["bank_id"], r["fingerprint"]) in dropped:
            r["status"] = "fraud"
            r["message"] = f"FRAUD ALERT: Already financed by {node.name} on {date.today().isoformat()} (block #{block.index})"
            r["updated_at"] = now_text()
    save_list(REQUESTS_FILE, requests_list)
    return {"ok": True, "block": block.to_dict(), "broadcast": broadcast}, 200


# Edits a record in an old block of one bank WITHOUT re-mining it (demo of tampering).
# The user picks which record to change: block_index says which block, record_index which
# record inside that block. The financed amount is multiplied by 10 and saved as it is.
def tamper_with_chain(bank_id, block_index, record_index):
    node = get_bank(bank_id)
    if node is None:
        return {"ok": False, "error": "Unknown bank"}, 404
    chain = node.blockchain.chain
    try:
        block_index, record_index = int(block_index), int(record_index)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Choose which invoice to tamper with"}, 400
    if not (1 <= block_index < len(chain)) or not (0 <= record_index < len(chain[block_index].records)):
        return {"ok": False, "error": "That record does not exist on this bank's chain"}, 400

    record = chain[block_index].records[record_index]
    old_amount = record["amount_financed"]
    record["amount_financed"] = round(old_amount * 10, 2)
    node.save()

    # Look up the invoice number (off-chain) so the message says which invoice was changed.
    invoice = next((i for i in load_list(INVOICES_FILE) if i["fingerprint"] == record["fingerprint"]), None)
    invoice_label = invoice["invoice_number"] if invoice else record["fingerprint"][:12] + "…"
    return {"ok": True, "bank_name": node.name, "block_index": block_index,
            "message": f"Changed the financed amount of invoice {invoice_label} in block #{block_index} of "
                       f"{node.name} from {old_amount:,.2f} to {record['amount_financed']:,.2f} without re-mining."}, 200


# Collects the numbers shown on the dashboard.
def get_stats():
    node = network.trusted_node()
    records = [r for block in node.blockchain.chain for r in block.records]
    requests_list = load_list(REQUESTS_FILE)
    return {
        "total_invoices": len(load_list(INVOICES_FILE)),
        "invoices_financed": len(records),
        "total_financed": round(sum(r["amount_financed"] for r in records), 2),
        "fraud_blocked": sum(1 for r in requests_list if r["status"] == "fraud"),
        "chain_length": len(node.blockchain.chain),
        "network": network.compare_chains(),
    }


# Wipes all data and starts every bank from a fresh genesis block.
def reset_everything():
    save_list(INVOICES_FILE, [])
    save_list(REQUESTS_FILE, [])
    network.reset()


# Fills the system with sample invoices, financed blocks, one blocked fraud attempt,
# and one request still waiting at Trust Me Bro Bank.
def load_demo_data():
    reset_everything()
    today = date.today()
    samples = [
        ("Acme Traders", "GST-ACME-001", "Metro Retail Pvt Ltd", "GST-METRO-002",
         [("Steel fasteners (box of 500)", 40, 850), ("Industrial adhesive 5L", 12, 1200)]),
        ("Kaveri Textiles", "GST-KAVERI-003", "Urban Styles LLP", "GST-URBAN-004",
         [("Cotton fabric roll (50m)", 25, 4200)]),
        ("Deccan Steel Works", "GST-DECCAN-005", "BuildRight Infra Ltd", "GST-BUILD-006",
         [("TMT bars 12mm (tonne)", 3, 56000), ("Transport charges", 1, 4500)]),
        ("Lotus Pharma Supplies", "GST-LOTUS-007", "CareWell Hospitals", "GST-CARE-008",
         [("Surgical gloves (carton)", 60, 950)]),
    ]
    invoices = []
    for i, (s_name, s_gstin, b_name, b_gstin, items) in enumerate(samples, start=1):
        invoice, _ = create_invoice({
            "supplier_name": s_name, "supplier_gstin": s_gstin, "buyer_name": b_name, "buyer_gstin": b_gstin,
            "invoice_number": f"INV-{today.year}-{i:04d}",
            "invoice_date": (today - timedelta(days=20 - i)).isoformat(),
            "due_date": (today + timedelta(days=40 + i)).isoformat(),
            "items": [{"description": d, "quantity": q, "rate": r} for d, q, r in items],
        })
        invoices.append(invoice)

    # Block 1: Bank of BrokeChain finances invoice 1.
    req, _ = create_finance_request(invoices[0]["id"], "bank-of-brokechain")
    approve_request("bank-of-brokechain", req["id"])
    mine_block("bank-of-brokechain")

    # Block 2: No Coincidence Bank finances invoices 2 and 3.
    for invoice in invoices[1:3]:
        req, _ = create_finance_request(invoice["id"], "no-coincidence-bank")
        approve_request("no-coincidence-bank", req["id"])
    mine_block("no-coincidence-bank")

    # Fraud attempt: invoice 3 is taken to Trust Me Bro Bank as well -> blocked.
    req, _ = create_finance_request(invoices[2]["id"], "trust-me-bro-bank")
    approve_request("trust-me-bro-bank", req["id"])

    # Invoice 4 is left waiting at Trust Me Bro Bank so the Bank Portal has something to approve.
    create_finance_request(invoices[3]["id"], "trust-me-bro-bank")


# ---------- Web pages ----------

# Each page is an HTML template; the JavaScript on the page calls the API below.

# Home / Dashboard page.
@app.route("/")
def page_dashboard():
    return render_template("dashboard.html", active="dashboard")


# Supplier Portal page (invoice generator).
@app.route("/supplier")
def page_supplier():
    return render_template("supplier.html", active="supplier")


# Bank Portal page (approve requests, mine blocks).
@app.route("/bank")
def page_bank():
    return render_template("bank.html", active="bank")


# Blockchain Explorer page (view, validate and tamper with chains).
@app.route("/explorer")
def page_explorer():
    return render_template("explorer.html", active="explorer")


# Verify Invoice page (public lookup).
@app.route("/verify")
def page_verify():
    return render_template("verify.html", active="verify")


# ---------- API: general ----------

# Lists the three banks (id and display name) for dropdown menus.
@app.get("/api/banks")
def api_banks():
    return jsonify([{"id": bank_id, "name": name} for bank_id, name in BANKS.items()])


# Returns the numbers and node status shown on the dashboard.
@app.get("/api/stats")
def api_stats():
    return jsonify(get_stats())


# ---------- API: supplier ----------

# Creates a new invoice and returns it with its fingerprint.
@app.post("/api/invoices")
def api_create_invoice():
    with lock:
        invoice, message = create_invoice(request.get_json(silent=True) or {})
    if message:
        return error(message)
    return jsonify({"ok": True, "invoice": invoice}), 201


# Lists every invoice, each with the financing requests made for it.
@app.get("/api/invoices")
def api_list_invoices():
    invoices = load_list(INVOICES_FILE)
    requests_list = load_list(REQUESTS_FILE)
    for invoice in invoices:
        invoice["requests"] = [r for r in requests_list if r["invoice_id"] == invoice["id"]]
    return jsonify(list(reversed(invoices)))


# Returns one invoice (used by the bank's "View Invoice" button).
@app.get("/api/invoices/<invoice_id>")
def api_get_invoice(invoice_id):
    invoice = find_by_id(load_list(INVOICES_FILE), invoice_id)
    if invoice is None:
        return error("Invoice not found", 404)
    return jsonify(invoice)


# Suggests the next invoice number for the invoice form.
@app.get("/api/next-invoice-number")
def api_next_invoice_number():
    return jsonify({"invoice_number": next_invoice_number()})


# Supplier sends an invoice to a chosen bank.
@app.post("/api/finance-request")
def api_finance_request():
    data = request.get_json(silent=True) or {}
    with lock:
        finance_request, message = create_finance_request(data.get("invoice_id"), data.get("bank"))
    if message:
        return error(message)
    return jsonify({"ok": True, "request": finance_request}), 201


# ---------- API: banks ----------

# All requests received by one bank (newest first). The page shows actions for pending ones.
@app.get("/api/banks/<bank_id>/requests")
def api_bank_requests(bank_id):
    if get_bank(bank_id) is None:
        return error("Unknown bank", 404)
    requests_list = [r for r in load_list(REQUESTS_FILE) if r["bank_id"] == bank_id]
    return jsonify(list(reversed(requests_list)))


# Bank approves a request -> duplicate check on the blockchain.
@app.post("/api/banks/<bank_id>/approve/<request_id>")
def api_approve(bank_id, request_id):
    with lock:
        result, status = approve_request(bank_id, request_id)
    return jsonify(result), status


# Bank rejects a request (for normal business reasons, not fraud).
@app.post("/api/banks/<bank_id>/reject/<request_id>")
def api_reject(bank_id, request_id):
    with lock:
        requests_list = load_list(REQUESTS_FILE)
        finance_request = find_by_id(requests_list, request_id)
        if finance_request is None or finance_request["bank_id"] != bank_id:
            return error("Request not found for this bank", 404)
        if finance_request["status"] != "pending":
            return error(f"Request is already '{finance_request['status']}'", 409)
        finance_request["status"] = "rejected"
        finance_request["message"] = "Rejected by the bank"
        finance_request["updated_at"] = now_text()
        save_list(REQUESTS_FILE, requests_list)
    return jsonify({"ok": True, "request": finance_request})


# Bank mines its pending records into a new block and broadcasts it.
@app.post("/api/banks/<bank_id>/mine")
def api_mine(bank_id):
    with lock:
        result, status = mine_block(bank_id)
    return jsonify(result), status


# One bank's full chain plus its pending records and validation report.
@app.get("/api/banks/<bank_id>/chain")
def api_chain(bank_id):
    node = get_bank(bank_id)
    if node is None:
        return error("Unknown bank", 404)
    return jsonify({
        "bank_id": bank_id,
        "bank_name": node.name,
        "chain": [block.to_dict() for block in node.blockchain.chain],
        "pending_records": node.blockchain.pending_records,
        "validation": node.blockchain.validate_chain(),
    })


# ---------- API: network, verification and demo tools ----------

# Validates all three chains and reports whether they match.
@app.get("/api/validate")
def api_validate():
    return jsonify(network.compare_chains())


# Runs consensus: any broken or shorter chain is replaced by the longest valid chain.
@app.post("/api/consensus")
def api_consensus():
    with lock:
        updated = network.resolve_conflicts()
    return jsonify({"ok": True, "updated": updated, "network": network.compare_chains()})


# Looks up one fingerprint on the network. Returns its status: "financed" (in a mined block),
# "pending" (approved by a bank but not mined yet) or "not_financed".
def fingerprint_status(fingerprint):
    node = network.trusted_node()
    duplicate = network.check_duplicate(node.bank_id, fingerprint)
    if duplicate is None:
        return {"status": "not_financed", "checked_on": node.name}
    status = "financed" if duplicate["block_index"] is not None else "pending"
    return {"status": status, "checked_on": node.name, **duplicate}


# Anyone can check whether an invoice has already been financed, by invoice number or fingerprint.
# The blockchain only stores fingerprints, so for an invoice number we first find the invoice(s)
# with that number in invoices.json (off-chain), then look up each invoice's fingerprint on the chain.
@app.post("/api/verify")
def api_verify():
    data = request.get_json(silent=True) or {}
    invoices = load_list(INVOICES_FILE)
    invoice_number = clean_text(data.get("invoice_number", ""))
    fingerprint = str(data.get("fingerprint", "")).strip().lower()

    if invoice_number:
        matches = [inv for inv in invoices if inv["invoice_number"] == invoice_number]
        if not matches:
            return error(f"No invoice with number {invoice_number} exists in the system", 404)
    elif fingerprint:
        if not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
            return error("A fingerprint is a 64-character hexadecimal SHA-256 hash")
        matches = [inv for inv in invoices if inv["fingerprint"] == fingerprint] or [{"fingerprint": fingerprint}]
    else:
        return error("Enter an invoice number or a fingerprint")

    # Two invoices can share a number (e.g. from different suppliers), so every match is checked.
    results = []
    for inv in matches:
        results.append({
            "invoice": inv if "id" in inv else None,
            "fingerprint": inv["fingerprint"],
            **fingerprint_status(inv["fingerprint"]),
        })
    return jsonify({"ok": True, "results": results})


# DEMO ONLY: secretly edits a chosen record in one bank's chain so validation fails.
# Body: {bank, block_index, record_index}.
@app.post("/api/tamper")
def api_tamper():
    data = request.get_json(silent=True) or {}
    with lock:
        result, status = tamper_with_chain(data.get("bank", "trust-me-bro-bank"), data.get("block_index"), data.get("record_index", 0))
    return jsonify(result), status


# Resets all banks, invoices and requests to a fresh genesis state.
@app.post("/api/reset")
def api_reset():
    with lock:
        reset_everything()
    return jsonify({"ok": True, "message": "All data cleared. Every bank is back to the genesis block."})


# Loads sample invoices and blocks for a quick demo.
@app.post("/api/demo-data")
def api_demo_data():
    with lock:
        load_demo_data()
    return jsonify({"ok": True, "message": "Demo data loaded.", "stats": get_stats()})


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5050)))
