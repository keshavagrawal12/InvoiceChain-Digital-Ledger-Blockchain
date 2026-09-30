"""
test_bank_nodes.py - Stage 2 test: three banks, broadcasting, fraud check and consensus.

Run from the project folder:   python3 tests/test_bank_nodes.py
Uses a temporary folder, so it never touches the real data/ folder.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from bank_node import BankNetwork
from fingerprint import generate_fingerprint


# Builds a financing record for an invoice number at a given bank.
def make_record(invoice_number, bank_name):
    return {
        "fingerprint": generate_fingerprint("29ABCDE1234F1Z5", "27PQRST5678K1Z2", invoice_number, "2026-09-12", 59000),
        "bank_name": bank_name,
        "amount_financed": 47200.00,
        "financing_date": "2026-09-12",
        "supplier_name": "Acme Traders",
    }


if __name__ == "__main__":
    print("Stage 2 - bank node tests")
    data_dir = tempfile.mkdtemp()
    network = BankNetwork(data_dir)
    brokechain = network.get("bank-of-brokechain")
    coincidence = network.get("no-coincidence-bank")
    trustmebro = network.get("trust-me-bro-bank")
    assert network.compare_chains()["all_match"]
    print("  3 nodes start in sync ........... OK")

    # 1. BrokeChain approves and mines an invoice -> all three chains get the block.
    ok, _ = network.approve("bank-of-brokechain", make_record("INV-001", "Bank of BrokeChain"))
    assert ok
    block, broadcast = network.mine_and_broadcast("bank-of-brokechain")
    assert all(b["accepted"] for b in broadcast)
    assert len(coincidence.blockchain.chain) == 2 and len(trustmebro.blockchain.chain) == 2
    assert network.compare_chains()["all_match"]
    print("  mine + broadcast ................ OK")

    # 2. No Coincidence tries to finance the same invoice -> fraud detected.
    ok, duplicate = network.approve("no-coincidence-bank", make_record("INV-001", "No Coincidence Bank"))
    assert not ok
    assert duplicate["message"] == "Already financed by Bank of BrokeChain on 2026-09-12"
    print(f"  fraud alert ..................... OK ({duplicate['message']})")

    # 3. Data survives a restart: build a new network from the same folder.
    restarted = BankNetwork(data_dir)
    assert len(restarted.get("trust-me-bro-bank").blockchain.chain) == 2
    assert restarted.compare_chains()["all_match"]
    print("  saved to JSON, reload ........... OK")

    # 4. Tamper with Trust Me Bro's copy -> it becomes invalid and out of sync.
    trustmebro.blockchain.chain[1].records[0]["bank_name"] = "Trust Me Bro Bank"
    report = network.compare_chains()
    trustmebro_report = [b for b in report["banks"] if b["bank_id"] == "trust-me-bro-bank"][0]
    assert not report["all_match"] and not trustmebro_report["valid"] and not trustmebro_report["in_sync"]
    print("  tampered node detected .......... OK")

    # 5. Consensus replaces the broken chain with the longest valid one.
    updated = network.resolve_conflicts()
    assert updated == ["Trust Me Bro Bank"]
    assert network.compare_chains()["all_match"]
    trustmebro.blockchain.chain[1].records[0]["bank_name"] = "X"  # repaired copy must be independent
    assert brokechain.blockchain.is_chain_valid()
    network.resolve_conflicts()
    print("  consensus repairs node .......... OK")

    # 6. A shorter chain is replaced by a longer valid chain.
    network.approve("no-coincidence-bank", make_record("INV-002", "No Coincidence Bank"))
    coincidence.mine()  # mined but NOT broadcast
    assert not network.compare_chains()["all_match"]
    assert sorted(network.resolve_conflicts()) == ["Bank of BrokeChain", "Trust Me Bro Bank"]
    assert network.compare_chains()["all_match"]
    print("  longest valid chain wins ........ OK")

    # 7. BrokeChain approves but does NOT mine yet. No Coincidence must still be blocked,
    #    because approvals are visible to every bank (pending pool), not only mined blocks.
    ok, _ = network.approve("bank-of-brokechain", make_record("INV-003", "Bank of BrokeChain"))
    assert ok
    ok, duplicate = network.approve("no-coincidence-bank", make_record("INV-003", "No Coincidence Bank"))
    assert not ok and "Already approved by Bank of BrokeChain" in duplicate["message"]
    print(f"  approved-but-not-mined blocked .. OK ({duplicate['message']})")

    # 8. Safety net: two banks approve at the exact same moment (simulated by writing to
    #    Trust Me Bro's pending list directly). BrokeChain mines first, so Trust Me Bro's copy is dropped.
    trustmebro.blockchain.add_record(make_record("INV-003", "Trust Me Bro Bank"))
    block, broadcast = network.mine_and_broadcast("bank-of-brokechain")
    trustmebro_result = [b for b in broadcast if b["bank_id"] == "trust-me-bro-bank"][0]
    assert trustmebro_result["dropped_fingerprints"] == [make_record("INV-003", "")["fingerprint"]]
    assert trustmebro.blockchain.pending_records == []
    print("  pending race handled ............ OK")

    print("All bank node tests passed.")
