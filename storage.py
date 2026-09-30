"""
storage.py - Tiny helpers to read and write the OFF-CHAIN JSON files.

Off-chain data is information that does NOT go on the blockchain:
    data/invoices.json  - full invoices created in the Supplier Portal
    data/requests.json  - financing requests sent from suppliers to banks

(Each bank's blockchain is saved separately by bank_node.py in data/nodes/.)
"""

import json
import os


# Reads a JSON list from a file. Returns an empty list if the file does not exist yet.
def load_list(file_path):
    if not os.path.exists(file_path):
        return []
    with open(file_path) as f:
        return json.load(f)


# Writes a list to a JSON file, creating the folder if needed.
def save_list(file_path, items):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w") as f:
        json.dump(items, f, indent=2)
