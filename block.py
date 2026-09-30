"""
block.py - Defines a single Block of the blockchain.

Each block stores:
    index         - position of the block in the chain (genesis block = 0)
    timestamp     - when the block was created
    records       - list of financing records (one per financed invoice)
    merkle_root   - Merkle root of all invoice fingerprints in this block
    previous_hash - hash of the block before this one (this is the "chain")
    nonce         - number changed during mining until the hash is valid
    hash          - SHA-256 hash of everything above

Proof-of-work: mining means trying nonce = 0, 1, 2, ... until the block hash
starts with DIFFICULTY zeros. This takes effort to find but is instant to check.
"""

import hashlib
import json
from datetime import datetime

from merkle import compute_merkle_root

# Number of leading zeros a valid block hash must have. Change this to make mining harder/easier.
DIFFICULTY = 4


class Block:

    # Creates a block. When loading a saved block, the existing nonce, hash and merkle_root are passed in.
    def __init__(self, index, records, previous_hash, timestamp=None, nonce=0, merkle_root=None, hash=None):
        self.index = index
        self.timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.records = records
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.merkle_root = merkle_root or self.calculate_merkle_root()
        self.hash = hash or self.calculate_hash()

    # Builds the Merkle root from the fingerprints of all records in this block.
    def calculate_merkle_root(self):
        fingerprints = [record["fingerprint"] for record in self.records]
        return compute_merkle_root(fingerprints)

    # Calculates the SHA-256 hash of the block's contents.
    # The records are included too, so changing ANY field of a record changes the hash.
    def calculate_hash(self):
        block_content = {
            "index": self.index,
            "timestamp": self.timestamp,
            "records": self.records,
            "merkle_root": self.merkle_root,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
        }
        # sort_keys=True makes sure the same data always produces the same text (and hash).
        block_text = json.dumps(block_content, sort_keys=True)
        return hashlib.sha256(block_text.encode("utf-8")).hexdigest()

    # Proof-of-work: keep increasing the nonce until the hash starts with DIFFICULTY zeros.
    def mine_block(self, difficulty=DIFFICULTY):
        target = "0" * difficulty
        self.nonce = 0
        self.hash = self.calculate_hash()
        while not self.hash.startswith(target):
            self.nonce += 1
            self.hash = self.calculate_hash()
        return self.hash

    # Converts the block into a plain dictionary so it can be saved as JSON or sent over the API.
    def to_dict(self):
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "records": self.records,
            "merkle_root": self.merkle_root,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
        }

    # Rebuilds a Block object from a dictionary (the opposite of to_dict).
    @staticmethod
    def from_dict(data):
        return Block(
            index=data["index"],
            records=data["records"],
            previous_hash=data["previous_hash"],
            timestamp=data["timestamp"],
            nonce=data["nonce"],
            merkle_root=data["merkle_root"],
            hash=data["hash"],
        )
