"""
bank_node.py - Simulates the three banks that share the blockchain.

BankNode    = one bank. It has its OWN copy of the blockchain and its own
              pending records, saved to data/nodes/<bank-id>.json.
BankNetwork = the group of all three banks. It handles:
                * the duplicate check (searches the chain AND every bank's pending records)
                * broadcasting a newly mined block to the other banks
                * consensus: the longest valid chain wins
                * comparing all three copies to see if they are in sync

In a real system each bank would be a separate server talking over the
internet. Here they live in one Python process so the demo is easy to run,
but each bank still keeps and checks its own separate copy of the chain.
"""

import hashlib
import json
import os

from block import Block
from blockchain import Blockchain

BANKS = {
    "bank-of-brokechain": "Bank of BrokeChain",
    "no-coincidence-bank": "No Coincidence Bank",
    "trust-me-bro-bank": "Trust Me Bro Bank",
}


class BankNode:

    def __init__(self, bank_id, data_dir):
        self.bank_id = bank_id
        self.name = BANKS[bank_id]
        self.file_path = os.path.join(data_dir, f"{bank_id}.json")
        self.blockchain = self.load()

    def load(self):
        if os.path.exists(self.file_path):
            with open(self.file_path) as f:
                return Blockchain.from_dict(json.load(f))
        return Blockchain()

    def save(self):
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        with open(self.file_path, "w") as f:
            json.dump(self.blockchain.to_dict(), f, indent=2)

    def mine(self):
        block = self.blockchain.mine_pending_records()
        self.save()
        return block

    # Receives a block broadcast by another bank. The block is checked before it is added.
    # Safety net: if two banks approved the same invoice at the exact same moment, our pending
    # copy is dropped, because the other bank's block got onto the chain first. Returns (accepted, reason, dropped_fingerprints).
    def receive_block(self, block):
        accepted, reason = self.blockchain.add_block(block)
        dropped = []
        if accepted:
            block_fingerprints = {record["fingerprint"] for record in block.records}
            kept = []
            for record in self.blockchain.pending_records:
                if record["fingerprint"] in block_fingerprints:
                    dropped.append(record["fingerprint"])
                else:
                    kept.append(record)
            self.blockchain.pending_records = kept
            self.save()
        return accepted, reason, dropped

    # Returns a short hash of the whole chain. Two banks with the same digest have identical chains.
    def chain_digest(self):
        chain_text = json.dumps([block.to_dict() for block in self.blockchain.chain], sort_keys=True)
        return hashlib.sha256(chain_text.encode("utf-8")).hexdigest()


class BankNetwork:

    # Creates all three bank nodes, each with its own storage file.
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.nodes = {bank_id: BankNode(bank_id, data_dir) for bank_id in BANKS}

    # Returns the node for a bank id, or None if the bank does not exist.
    def get(self, bank_id):
        return self.nodes.get(bank_id)

    # THE DUPLICATE CHECK. Returns None if the invoice is new, otherwise who already has it.
    # Step 1: search the blockchain (invoices already mined into a block).
    # Step 2: search every bank's pending list (approved but not mined yet). Like the "mempool"
    #         in Bitcoin, an approval is visible to all banks straight away, so a second bank
    #         cannot approve the same invoice in the gap before the first bank mines it.
    def check_duplicate(self, bank_id, fingerprint):
        found = self.nodes[bank_id].blockchain.find_fingerprint(fingerprint)
        if found:
            record = found["record"]
            return {
                "bank_name": record["bank_name"],
                "financing_date": record["financing_date"],
                "block_index": found["block_index"],
                "record": record,
                "message": f"Already financed by {record['bank_name']} on {record['financing_date']}",
            }
        for node in self.nodes.values():
            record = node.blockchain.find_pending(fingerprint)
            if record:
                return {
                    "bank_name": record["bank_name"],
                    "financing_date": record["financing_date"],
                    "block_index": None,
                    "record": record,
                    "message": f"Already approved by {record['bank_name']} on {record['financing_date']} "
                               "(waiting to be mined into a block)",
                }
        return None

    # A bank approves a financing record: run the duplicate check, and if the invoice is new,
    # add the record to that bank's pending list. Returns (True, None) or (False, duplicate_info).
    def approve(self, bank_id, record):
        duplicate = self.check_duplicate(bank_id, record["fingerprint"])
        if duplicate:
            return False, duplicate
        node = self.nodes[bank_id]
        node.blockchain.add_record(record)
        node.save()
        return True, None

    # Mines a block at one bank and broadcasts it to the other two.
    # Returns the new block plus a report of how every other bank responded.
    def mine_and_broadcast(self, bank_id):
        miner = self.nodes[bank_id]
        block = miner.mine()
        if block is None:
            return None, []

        broadcast = []
        for other_id, other in self.nodes.items():
            if other_id == bank_id:
                continue
            # Send a COPY through JSON, just like a real network message.
            # (Sharing the same Python object would let one bank's edits change the others.)
            block_copy = Block.from_dict(json.loads(json.dumps(block.to_dict())))
            accepted, reason, dropped = other.receive_block(block_copy)
            broadcast.append({
                "bank_id": other_id,
                "bank_name": other.name,
                "accepted": accepted,
                "reason": reason,
                "dropped_fingerprints": dropped,
            })
        return block, broadcast

    # Consensus rule: find the longest VALID chain in the network and copy it to every bank
    # whose own chain is shorter or broken. Returns a list of the banks that were updated.
    def resolve_conflicts(self):
        best = None
        for node in self.nodes.values():
            if node.blockchain.is_chain_valid():
                if best is None or len(node.blockchain.chain) > len(best.blockchain.chain):
                    best = node
        if best is None:
            return []

        updated = []
        # Turned into JSON text so each bank gets its own independent copy of the chain.
        best_chain_json = json.dumps(best.blockchain.to_dict()["chain"])
        for node in self.nodes.values():
            if node is best:
                continue
            own_is_broken = not node.blockchain.is_chain_valid()
            own_is_shorter = len(node.blockchain.chain) < len(best.blockchain.chain)
            if own_is_broken or own_is_shorter:
                # Replace only the chain; the bank keeps its own pending records
                # (minus any that are now already on the new chain).
                pending = node.blockchain.pending_records
                node.blockchain = Blockchain.from_dict({"chain": json.loads(best_chain_json)})
                node.blockchain.pending_records = [
                    r for r in pending if not node.blockchain.find_fingerprint(r["fingerprint"])
                ]
                node.save()
                updated.append(node.name)
        return updated

    # Validates every bank's chain and compares them. Returns a report for the dashboard/explorer.
    def compare_chains(self):
        banks = []
        for bank_id, node in self.nodes.items():
            report = node.blockchain.validate_chain()
            banks.append({
                "bank_id": bank_id,
                "bank_name": node.name,
                "length": len(node.blockchain.chain),
                "last_hash": node.blockchain.get_last_block().hash,
                "digest": node.chain_digest(),
                "valid": report["valid"],
                "errors": report["errors"],
                "pending": len(node.blockchain.pending_records),
            })

        # Count how many banks share each digest; the most common one is the "majority" chain.
        counts = {}
        for bank in banks:
            counts[bank["digest"]] = counts.get(bank["digest"], 0) + 1
        majority_digest = max(counts, key=counts.get)
        for bank in banks:
            bank["in_sync"] = bank["digest"] == majority_digest and bank["valid"]

        return {
            "all_match": len(counts) == 1,
            "all_valid": all(bank["valid"] for bank in banks),
            "banks": banks,
        }

    # Returns a node whose chain is valid and agrees with the majority - used for public lookups.
    def trusted_node(self):
        report = self.compare_chains()
        for bank in report["banks"]:
            if bank["in_sync"]:
                return self.nodes[bank["bank_id"]]
        return next(iter(self.nodes.values()))

    # Deletes every bank's saved chain and starts all three again from the genesis block.
    def reset(self):
        for bank_id, node in self.nodes.items():
            node.blockchain = Blockchain()
            node.save()
