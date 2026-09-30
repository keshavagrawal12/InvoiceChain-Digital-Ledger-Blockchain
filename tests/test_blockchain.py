"""
test_blockchain.py - Stage 1 test: checks the blockchain core on its own.

Run from the project folder:   python3 tests/test_blockchain.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from block import DIFFICULTY
from blockchain import Blockchain
from fingerprint import generate_fingerprint
from merkle import compute_merkle_root, sha256


# Builds a sample financing record for a given invoice number.
def make_record(invoice_number, bank="Bank of BrokeChain"):
    fingerprint = generate_fingerprint("29ABCDE1234F1Z5", "27PQRST5678K1Z2", invoice_number, "2026-09-12", 59000)
    return {
        "fingerprint": fingerprint,
        "bank_name": bank,
        "amount_financed": 47200.00,
        "financing_date": "2026-09-12",
        "supplier_name": "Acme Traders",
    }


# Checks that cleaning makes different spellings of the same invoice give one fingerprint.
def test_fingerprint():
    a = generate_fingerprint("29abcde1234f1z5 ", "27PQRST5678K1Z2", " inv-001", "12/09/2026", 50000)
    b = generate_fingerprint("29ABCDE1234F1Z5", "27pqrst5678k1z2", "INV-001", "2026-09-12", "50000.00")
    c = generate_fingerprint("29ABCDE1234F1Z5", "27PQRST5678K1Z2", "INV-002", "2026-09-12", 50000)
    assert a == b, "Same invoice written differently should give the same fingerprint"
    assert a != c, "Different invoices should give different fingerprints"
    assert len(a) == 64
    print("  fingerprint cleaning ............ OK")


# Checks the Merkle root for 0, 1, 2 and 3 leaves against hand-calculated values.
def test_merkle():
    assert compute_merkle_root([]) == sha256("")
    assert compute_merkle_root(["a"]) == "a"
    assert compute_merkle_root(["a", "b"]) == sha256("ab")
    assert compute_merkle_root(["a", "b", "c"]) == sha256(sha256("ab") + sha256("cc"))
    print("  merkle root ..................... OK")


# Checks mining, proof-of-work, chain links and searching for a fingerprint.
def test_mining_and_search():
    chain = Blockchain()
    assert len(chain.chain) == 1 and chain.is_chain_valid()

    chain.add_record(make_record("INV-001"))
    chain.add_record(make_record("INV-002"))
    start = time.time()
    block = chain.mine_pending_records()
    print(f"  mined block 1 in {time.time() - start:.2f}s (nonce={block.nonce}, difficulty={DIFFICULTY})")

    assert block.hash.startswith("0" * DIFFICULTY)
    assert block.previous_hash == chain.chain[0].hash
    assert chain.pending_records == []
    assert chain.is_chain_valid()
    assert chain.mine_pending_records() is None, "Nothing pending, so nothing to mine"

    found = chain.find_fingerprint(make_record("INV-002")["fingerprint"])
    assert found and found["block_index"] == 1
    assert chain.find_fingerprint("not-a-real-fingerprint") is None
    print("  mining + search ................. OK")
    return chain


# Checks that changing an old record makes validation fail and points at the right block.
def test_tamper_detection(chain):
    chain.add_record(make_record("INV-003"))
    chain.mine_pending_records()
    assert chain.is_chain_valid()

    chain.chain[1].records[0]["amount_financed"] = 1.00  # edit without re-mining
    report = chain.validate_chain()
    assert not report["valid"]
    assert report["errors"][0]["index"] == 1
    print(f"  tamper detected ................. OK ({report['errors'][0]['reason']})")

    chain.chain[1].records[0]["amount_financed"] = 47200.00  # put it back
    assert chain.is_chain_valid()


# Checks a chain survives being turned into a dictionary and back (used for JSON storage).
def test_save_and_load(chain):
    copy = Blockchain.from_dict(chain.to_dict())
    assert copy.is_chain_valid()
    assert [b.hash for b in copy.chain] == [b.hash for b in chain.chain]
    print("  save / load ..................... OK")


# Checks that a block with a bad previous_hash or an already-financed invoice is refused.
def test_add_block_rules():
    bank_a, bank_b = Blockchain(), Blockchain()
    assert bank_a.chain[0].hash == bank_b.chain[0].hash, "All banks must share the same genesis block"

    bank_a.add_record(make_record("INV-010"))
    block = bank_a.mine_pending_records()
    accepted, _ = bank_b.add_block(block)
    assert accepted and len(bank_b.chain) == 2

    accepted, reason = bank_b.add_block(block)  # same block again -> wrong index/previous hash
    assert not accepted
    print(f"  add_block rules ................. OK ({reason})")


if __name__ == "__main__":
    print("Stage 1 - blockchain core tests")
    test_fingerprint()
    test_merkle()
    main_chain = test_mining_and_search()
    test_tamper_detection(main_chain)
    test_save_and_load(main_chain)
    test_add_block_rules()
    print("All blockchain core tests passed.")
