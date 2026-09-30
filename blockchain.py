"""
blockchain.py - The Blockchain class: a list of linked blocks plus pending records.

Main ideas:
    * The chain starts with a fixed "genesis" block, identical for every bank.
    * New financing records wait in `pending_records` until a bank mines them.
    * Mining puts all pending records into a new block and runs proof-of-work.
    * is_chain_valid() re-checks every block, so any tampering is detected.
    * find_fingerprint() searches the whole chain for an invoice fingerprint -
      this is the check that stops double financing.
"""

from block import Block, DIFFICULTY

# The genesis block uses fixed values so all three banks start with the exact same first block.
GENESIS_TIMESTAMP = "2026-01-01 00:00:00"
GENESIS_PREVIOUS_HASH = "0" * 64


class Blockchain:

    # Creates a new chain containing only the genesis block.
    def __init__(self, difficulty=DIFFICULTY):
        self.difficulty = difficulty
        self.chain = [self.create_genesis_block()]
        # Remember the correct genesis hash so we can later detect if the genesis block was edited.
        self.genesis_hash = self.chain[0].hash
        self.pending_records = []

    # Builds and mines the first block of the chain. It has no records and no real previous block.
    def create_genesis_block(self):
        genesis = Block(index=0, records=[], previous_hash=GENESIS_PREVIOUS_HASH, timestamp=GENESIS_TIMESTAMP)
        genesis.mine_block(self.difficulty)
        return genesis

    # Returns the newest block in the chain.
    def get_last_block(self):
        return self.chain[-1]

    # Adds a financing record to the waiting list. It goes on the chain the next time we mine.
    def add_record(self, record):
        self.pending_records.append(record)

    # Puts all pending records into a new block, mines it, adds it to the chain and returns it.
    # Returns None if there is nothing to mine.
    def mine_pending_records(self):
        if len(self.pending_records) == 0:
            return None

        new_block = Block(
            index=len(self.chain),
            records=list(self.pending_records),
            previous_hash=self.get_last_block().hash,
        )
        new_block.mine_block(self.difficulty)
        self.chain.append(new_block)
        self.pending_records = []
        return new_block

    # Checks one block against the block before it. Returns None if valid, or a text reason if not.
    def check_block(self, block, previous_block):
        if block.index != previous_block.index + 1:
            return "Index is not one more than the previous block"
        if block.previous_hash != previous_block.hash:
            return "previous_hash does not match the hash of the previous block"
        if block.merkle_root != block.calculate_merkle_root():
            return "Merkle root does not match the fingerprints in this block"
        if block.hash != block.calculate_hash():
            return "Stored hash does not match the block contents (data was changed)"
        if not block.hash.startswith("0" * self.difficulty):
            return "Hash does not meet the proof-of-work difficulty"
        return None

    # Checks the genesis block has not been changed. Returns None if valid, or a text reason if not.
    def check_genesis(self):
        genesis = self.chain[0]
        if genesis.hash != self.genesis_hash or genesis.hash != genesis.calculate_hash():
            return "Genesis block has been changed"
        return None

    # Goes through the whole chain and returns a report: whether it is valid and which blocks are broken.
    def validate_chain(self):
        errors = []
        genesis_error = self.check_genesis()
        if genesis_error:
            errors.append({"index": 0, "reason": genesis_error})

        seen_fingerprints = set()
        for i in range(1, len(self.chain)):
            block = self.chain[i]
            reason = self.check_block(block, self.chain[i - 1])
            if reason:
                errors.append({"index": block.index, "reason": reason})

            # The same invoice must never appear twice on the chain.
            for record in block.records:
                if record["fingerprint"] in seen_fingerprints:
                    errors.append({"index": block.index, "reason": "Duplicate invoice fingerprint on chain"})
                seen_fingerprints.add(record["fingerprint"])

        return {"valid": len(errors) == 0, "errors": errors}

    # Returns True if every block in the chain is valid, otherwise False.
    def is_chain_valid(self):
        return self.validate_chain()["valid"]

    # Searches every block for a fingerprint. Returns the record and its block index, or None if not found.
    def find_fingerprint(self, fingerprint):
        for block in self.chain:
            for record in block.records:
                if record["fingerprint"] == fingerprint:
                    return {"record": record, "block_index": block.index}
        return None

    # Returns the pending record with this fingerprint, or None if it is not waiting to be mined.
    def find_pending(self, fingerprint):
        for record in self.pending_records:
            if record["fingerprint"] == fingerprint:
                return record
        return None

    # Adds a block received from another bank, but only after checking it is valid
    # and that none of its invoices are already on our chain. Returns (accepted, reason).
    def add_block(self, block):
        reason = self.check_block(block, self.get_last_block())
        if reason:
            return False, reason
        for record in block.records:
            if self.find_fingerprint(record["fingerprint"]):
                return False, "Block contains an invoice that is already financed"
        self.chain.append(block)
        return True, "Block accepted"

    # Converts the whole blockchain (chain + pending records) into a dictionary for saving as JSON.
    def to_dict(self):
        return {
            "chain": [block.to_dict() for block in self.chain],
            "pending_records": self.pending_records,
        }

    # Rebuilds a Blockchain object from a saved dictionary.
    @staticmethod
    def from_dict(data, difficulty=DIFFICULTY):
        blockchain = Blockchain(difficulty)
        blockchain.chain = [Block.from_dict(block) for block in data["chain"]]
        blockchain.pending_records = data.get("pending_records", [])
        return blockchain
