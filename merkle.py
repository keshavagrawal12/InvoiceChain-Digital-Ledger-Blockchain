r"""
merkle.py - Builds a Merkle tree and returns its root hash.

A Merkle tree is a "tree of hashes". We start with a list of leaves (here, the
invoice fingerprints inside a block), then repeatedly hash neighbouring pairs
together until only ONE hash is left. That final hash is the Merkle root.

Why it matters: if even one fingerprint in the block changes, the Merkle root
changes too, so the block can prove exactly which invoices it contains.

Example with 3 leaves (A, B, C):

            ROOT = H( H(A+B) + H(C+C) )
             /                    \
        H(A + B)                H(C + C)     <- odd count, so C is paired with itself
        /      \                /      \
       A        B              C        C
"""

import hashlib


# Returns the SHA-256 hash of a piece of text as a 64-character hex string.
def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# Takes a list of leaf hashes and returns the Merkle root.
# An empty block (like the genesis block) gets the hash of an empty string.
def compute_merkle_root(leaves):
    if len(leaves) == 0:
        return sha256("")

    # Start at the bottom level of the tree.
    level = list(leaves)

    # Keep combining pairs until only the root is left.
    while len(level) > 1:
        # If there is an odd number of hashes, copy the last one so every hash has a partner.
        if len(level) % 2 == 1:
            level.append(level[-1])

        next_level = []
        for i in range(0, len(level), 2):
            next_level.append(sha256(level[i] + level[i + 1]))
        level = next_level

    return level[0]
