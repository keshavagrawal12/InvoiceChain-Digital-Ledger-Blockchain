# InvoiceChain: Invoice Double-Financing Checker

A blockchain-based system that stops a business from financing the **same invoice with more than one bank**.
Built from scratch in Python (no blockchain libraries) with a Flask REST API and a plain HTML/CSS/JavaScript frontend.
B.Sc. Blockchain course project.

---

## 1. Project summary

**The problem.** In *invoice financing*, a small business borrows money from a bank against an unpaid invoice.
A dishonest business can take the same invoice to several banks and borrow against it several times.
Each bank only sees its own records, so nobody notices until the buyer pays once and the loans go bad.

**The solution.** All banks share one blockchain. Every financed invoice is recorded on it as a
**fingerprint** (a SHA-256 hash of the invoice's key fields). Before a bank finances an invoice it searches
the chain for that fingerprint. If the fingerprint is already there, the request is rejected with a
**FRAUD ALERT** saying which bank financed it and when.

**Blockchain features implemented from scratch:**

| Feature | Where |
|---|---|
| SHA-256 invoice fingerprint with input cleaning | `fingerprint.py` |
| Merkle tree / Merkle root per block | `merkle.py` |
| Blocks with index, timestamp, records, Merkle root, previous hash, nonce, hash | `block.py` |
| Proof-of-work (hash must start with `0000`, difficulty is a constant) | `block.py` |
| Genesis block, pending records, mining, full chain validation, fingerprint search | `blockchain.py` |
| 3 bank nodes, each with its own chain copy, broadcasting and validating blocks | `bank_node.py` |
| Consensus (longest valid chain wins) and chain comparison | `bank_node.py` |
| JSON persistence (data survives a restart) | `bank_node.py`, `storage.py` |

---

## 2. Folder structure

```
<project folder>/
├── app.py               Flask server: REST API + page routes
├── block.py             Block class + proof-of-work (DIFFICULTY constant)
├── blockchain.py        Blockchain class: genesis, pending, mining, validation, search
├── merkle.py            Merkle root calculation
├── fingerprint.py       Cleans invoice fields and builds the SHA-256 fingerprint
├── bank_node.py         BankNode (one bank) + BankNetwork (3 banks, broadcast, consensus)
├── storage.py           Read/write helpers for the off-chain JSON files
├── requirements.txt
├── data/                Created automatically at runtime
│   ├── invoices.json    Full invoices (off-chain)
│   ├── requests.json    Financing requests (off-chain)
│   └── nodes/           One JSON file per bank: its chain + pending records
├── templates/           HTML pages (Jinja templates)
│   ├── base.html        Shared layout + top navigation bar
│   ├── dashboard.html   Home / Dashboard
│   ├── supplier.html    Supplier Portal (invoice generator)
│   ├── bank.html        Bank Portal
│   ├── explorer.html    Blockchain Explorer
│   └── verify.html      Verify Invoice
├── static/
│   ├── css/style.css    All styles (navy/white + teal accent, responsive, print stylesheet)
│   └── js/              common.js (shared helpers) + one script per page
└── tests/
    ├── test_blockchain.py   Stage 1: blockchain core
    ├── test_bank_nodes.py   Stage 2: 3 banks, broadcast, fraud check, tamper, consensus
    └── test_api.py          Stage 3: full demo flow through the REST API
```

---

## 3. How to run

Requires **Python 3.9+**.

```bash
cd "path/to/project"
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 app.py
```

Open **http://127.0.0.1:5050** in your browser.
(Port 5050 is used because macOS often reserves port 5000 for AirPlay. To change it: `PORT=8000 python3 app.py`.)

**Run the tests** (each uses a temporary folder, so your demo data is not touched):

```bash
python3 tests/test_blockchain.py
python3 tests/test_bank_nodes.py
python3 tests/test_api.py
```

---

## 4. How each file works

### `fingerprint.py`
Builds the invoice fingerprint from five fields: **supplier GSTIN, buyer GSTIN, invoice number, invoice date, invoice amount**.
GST numbers are not checked against the real GSTIN format, so any demo value (e.g. `GST-SUP-001`) works.
Each field is cleaned first (uppercase, all spaces removed, date converted to `YYYY-MM-DD`, amount rounded to 2 decimals),
joined with `|`, then hashed with SHA-256. Cleaning means `"inv-001 "` and `"INV-001"`, or `12/09/2026` and `2026-09-12`,
give the **same** fingerprint, so a fraudster cannot get past the check by retyping the invoice slightly differently.
Only the fingerprint goes on the chain, never the full invoice, which keeps business details private.

### `merkle.py`
`compute_merkle_root(leaves)` takes the list of fingerprints in a block and repeatedly hashes neighbouring pairs
(`sha256(left + right)`) until one hash remains: the Merkle root. With an odd number of hashes, the last one is paired with itself.
If any fingerprint in the block changes, the root changes.

### `block.py`
The `Block` class holds `index, timestamp, records, merkle_root, previous_hash, nonce, hash`.
- `calculate_hash()` takes the SHA-256 of all fields (including the records), serialised as JSON with sorted keys.
- `mine_block()` is **proof-of-work**: it tries `nonce = 0, 1, 2, …` until the hash starts with `DIFFICULTY` zeros (`"0000"`).
  Finding the nonce takes tens of thousands of attempts; checking it takes one hash.
- `to_dict()` / `from_dict()` convert to and from plain dictionaries for JSON storage and broadcasting.

### `blockchain.py`
The `Blockchain` class holds `chain` (list of blocks) and `pending_records`.
- **Genesis block**: a fixed first block (fixed timestamp, `previous_hash = 000…0`) so all three banks start identical.
- `add_record()` puts an approved financing record in the pending list.
- `mine_pending_records()` creates a block from all pending records, mines it and appends it.
- `validate_chain()` / `is_chain_valid()`: for every block, checks that
  1. the index follows on from the previous block,
  2. `previous_hash` equals the previous block's hash (the "chain" link),
  3. the Merkle root matches the fingerprints in the block,
  4. the stored hash equals a freshly recomputed hash (detects edited data),
  5. the hash meets the proof-of-work difficulty,
  6. no invoice fingerprint appears twice on the chain.

  It returns which blocks failed and why, which is how the Explorer turns invalid blocks red.
- `find_fingerprint(fp)` searches every block and returns the matching record and block number. **This is the double-financing check.**
- `add_block(block)` accepts a block from another bank only if it passes the checks above and contains no already-financed invoice.

### `bank_node.py`
- `BankNode` is one bank: its own `Blockchain` copy, saved to `data/nodes/<bank>.json`.
  `receive_block()` validates a block broadcast by another bank before adding it.
- `BankNetwork` holds the three banks: **Bank of BrokeChain, No Coincidence Bank, Trust Me Bro Bank**.
  - `check_duplicate()` / `approve()`: **the fraud check**. It searches (1) the blockchain and (2) *every* bank's pending records.
    Like Bitcoin's "mempool", an approval is visible to all banks straight away, so a second bank cannot approve the same
    invoice in the gap before the first bank clicks *Mine Block*.
  - `mine_and_broadcast()`: one bank mines, then a **copy** of the block (sent through JSON, like a real network message) goes to the other two, and each validates it.
  - `resolve_conflicts()`: **consensus**. The longest *valid* chain wins. Any bank whose chain is shorter or broken (e.g. tampered) gets it replaced.
  - `compare_chains()`: validates all three chains and compares a digest (hash of the whole chain) to report whether they match.

### `app.py`
The Flask server. Invoices and requests are **off-chain** data (`invoices.json`, `requests.json`); only financing records go on-chain.
Totals, 18% GST and the fingerprint are calculated on the server so they cannot be faked from the browser.
A bank lends 80% of the invoice value (`ADVANCE_RATE`). A thread lock makes sure two clicks can never write the files at the same time.

### Frontend (`templates/` + `static/`)
Plain HTML/CSS/JS. Every page extends `base.html` (top nav). `common.js` has the shared helpers (`api()`, `toast()`, `renderInvoice()`, …),
and each page has its own small script that calls the REST API. "Download as PDF" uses the browser's print dialog with a print
stylesheet that prints only the invoice (choose **Save as PDF**).

---

## 5. REST API

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/invoices` | Create invoice (off-chain), returns it with its fingerprint |
| GET | `/api/invoices` | List all invoices with their financing requests |
| GET | `/api/invoices/<id>` | One invoice (used by "View Invoice") |
| POST | `/api/finance-request` | `{invoice_id, bank}` sends an invoice to a bank |
| GET | `/api/banks/<bank>/requests` | Requests received by a bank |
| POST | `/api/banks/<bank>/approve/<request_id>` | Duplicate check → pending, or **409 FRAUD ALERT** |
| POST | `/api/banks/<bank>/reject/<request_id>` | Reject a request |
| POST | `/api/banks/<bank>/mine` | Mine pending records and broadcast the block |
| GET | `/api/banks/<bank>/chain` | That bank's chain, pending records and validation |
| GET | `/api/validate` | Validate all 3 chains and report if they match |
| POST | `/api/consensus` | Longest valid chain replaces broken/shorter chains |
| POST | `/api/verify` | `{invoice_number}` or `{fingerprint}` → financed, pending, or not financed |
| POST | `/api/tamper` | **Demo only**: `{bank, block_index, record_index}` edits the chosen record without re-mining |
| POST | `/api/reset` | Wipe everything back to genesis |
| POST | `/api/demo-data` | Load sample invoices, blocks and one blocked fraud attempt |
| GET | `/api/stats` | Dashboard numbers + node status |

Bank ids: `bank-of-brokechain`, `no-coincidence-bank`, `trust-me-bro-bank`.

---

## 6. Demo steps (for the viva)

Start with **Dashboard → Reset Everything** (or **Load Demo Data** to start with a populated chain).

1. **Supplier Portal**: click *Fill sample data* → *Generate Invoice*. Point out the invoice preview, the watermark and the fingerprint at the bottom. Choose **Bank of BrokeChain** → *Send to Bank*.
2. **Bank Portal**: act as **Bank of BrokeChain** → *Approve* (green: no duplicate found) → *Mine Block*. The result shows the nonce, the hash starting with `0000`, and that both other banks validated and added the block. The **Dashboard** now shows all 3 nodes in sync.
3. **Supplier Portal**: in *My invoices*, click *Open* on the same invoice → choose **No Coincidence Bank** → *Send to Bank*.
4. **Bank Portal**: act as **No Coincidence Bank** → *Approve* → red **FRAUD ALERT: Duplicate invoice. Already financed by Bank of BrokeChain on …**. The fraud counter on the Dashboard goes up.
5. **Blockchain Explorer**: select **Trust Me Bro Bank** → *Tamper Demo* → pick any invoice from the list (its financed amount is multiplied by 10 without re-mining) → *Validate Chain*. The block holding that invoice turns red ("Stored hash does not match the block contents") and Trust Me Bro Bank is shown **Invalid / Out of sync** while the other two remain valid.
   Then click *Sync Nodes (consensus)*: the longest valid chain replaces Trust Me Bro's broken copy and all three match again.
6. **Verify Invoice**: type just the invoice number (lowercase or extra spaces are fine) → "Already financed by Bank of BrokeChain".
   The chain stores only fingerprints, so the app first finds the invoice by its number in `invoices.json`, then searches the chain for that invoice's fingerprint.

---

## 7. Key points to explain

- **Why a fingerprint and not the invoice?** Privacy: banks can detect duplicates without seeing each other's customers' invoices. A hash is one-way, so the invoice cannot be rebuilt from it.
- **Why does tampering get caught?** A block's hash covers its records. Changing a record changes the recomputed hash, which no longer matches the stored hash. Re-mining that block would change its hash, which breaks the next block's `previous_hash` link, so an attacker would have to re-mine every later block on every bank.
- **What does proof-of-work add?** It makes creating (or re-creating) blocks expensive, so rewriting history is costly. Increase `DIFFICULTY` in `block.py` to see mining slow down (each extra zero is about 16× more work).
- **What does the Merkle root add?** One short hash that commits to every fingerprint in the block. It lets you prove an invoice is inside a block without sending the whole block.
- **What if a bank approves but hasn't mined yet?** The duplicate check also searches every bank's pending list, so a second bank still gets *"Already approved by … (waiting to be mined into a block)"*.
- **Two banks approving at the exact same instant?** Safety net: the first bank to mine wins. When the other bank receives that block, it drops its now-duplicate pending record and the request is marked as fraud.
- **Limitations (simulation):** the three banks run inside one Python process instead of on separate servers, and there is no login or digital signatures. A real deployment would be a permissioned network (e.g. Hyperledger Fabric) with signed transactions.

> All invoices generated by this app carry a "Demo invoice — for project use only" watermark and are not real tax documents.
