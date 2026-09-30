/*
 * explorer.js - Blockchain Explorer logic: draws one bank's chain as linked cards,
 * shows block details, validates all three chains, runs the tamper demo and consensus.
 */

let selectedBank = "bank-of-brokechain";
let chainData = null;          // the chain currently on screen
let selectedIndex = null;      // the block whose details are shown
let validationReport = null;   // last result of "Validate Chain" (null = not validated yet)

// Draws the three bank tabs and highlights the selected one.
async function renderTabs() {
  const banks = await getBanks();
  const tabs = document.getElementById("bank-tabs");
  tabs.innerHTML = banks.map((b) => `<button data-bank="${b.id}" class="${b.id === selectedBank ? "active" : ""}">${esc(b.name)}</button>`).join("");
  tabs.querySelectorAll("button").forEach((button) => button.addEventListener("click", () => {
    selectedBank = button.dataset.bank;
    selectedIndex = null;
    renderTabs();
    loadChain();
  }));
}

// Returns the validation errors for the selected bank from the last "Validate Chain" click.
function errorsForSelectedBank() {
  if (!validationReport) return [];
  return validationReport.banks.find((b) => b.bank_id === selectedBank)?.errors ?? [];
}

// Loads the selected bank's chain from the API and draws it.
async function loadChain() {
  const { data } = await api("GET", `/api/banks/${selectedBank}/chain`);
  chainData = data;
  document.getElementById("chain-title").textContent = `${data.bank_name}'s copy of the shared chain — ${data.chain.length} blocks`;
  renderChain();
  if (selectedIndex !== null && data.chain[selectedIndex]) showBlock(selectedIndex);
  else document.getElementById("block-details").innerHTML = `<p class="empty" style="margin: 0">No block selected.</p>`;
}

// Draws every block as a card, with arrows between them. Invalid blocks are drawn in red.
function renderChain() {
  const errors = errorsForSelectedBank();
  const parts = chainData.chain.map((b) => {
    const error = errors.find((e) => e.index === b.index);
    return `
      <button class="block-card ${error ? "invalid" : ""} ${b.index === selectedIndex ? "selected" : ""}" data-index="${b.index}">
        <div class="b-head">
          <span class="b-index">${b.index === 0 ? "Genesis #0" : `Block #${b.index}`}</span>
          <span class="badge ${b.records.length ? "badge-info" : ""}">${b.records.length} record(s)</span>
        </div>
        <div class="b-row"><span>Timestamp</span>${esc(b.timestamp)}</div>
        <div class="b-row"><span>Nonce</span><code>${b.nonce}</code></div>
        <div class="b-row"><span>Merkle root</span><code>${shortHash(b.merkle_root)}</code></div>
        <div class="b-row"><span>Previous hash</span><code class="${b.index > 0 ? "hash-link" : ""}">${shortHash(b.previous_hash)}</code></div>
        <div class="b-row"><span>Hash</span><code class="hash-link">${shortHash(b.hash)}</code></div>
        ${error ? `<div class="b-error">✕ ${esc(error.reason)}</div>` : ""}
      </button>`;
  });
  document.getElementById("chain").innerHTML = parts.join(`<div class="chain-arrow" aria-hidden="true">→</div>`);
  document.querySelectorAll(".block-card").forEach((card) => card.addEventListener("click", () => {
    selectedIndex = Number(card.dataset.index);
    renderChain();
    showBlock(selectedIndex);
  }));
}

// Shows the full details and financing records of one block.
function showBlock(index) {
  const b = chainData.chain[index];
  const records = b.records.length
    ? `<div class="table-wrap"><table>
        <thead><tr><th>Fingerprint</th><th>Bank</th><th>Supplier</th><th class="num">Amount financed</th><th>Date</th></tr></thead>
        <tbody>${b.records.map((r) => `
          <tr>
            <td><code title="${esc(r.fingerprint)}">${shortHash(r.fingerprint, 16, 8)}</code></td>
            <td>${esc(r.bank_name)}</td>
            <td>${esc(r.supplier_name)}</td>
            <td class="num">${inr(r.amount_financed)}</td>
            <td>${esc(r.financing_date)}</td>
          </tr>`).join("")}</tbody></table></div>`
    : `<p class="muted">The genesis block is the fixed starting point of the chain. It has no records.</p>`;

  document.getElementById("block-details").innerHTML = `
    <div class="card-head"><h2>${index === 0 ? "Genesis block" : `Block #${index}`} — ${esc(chainData.bank_name)}</h2></div>
    <dl class="kv" style="margin-bottom: 16px">
      <dt>Timestamp</dt><dd>${esc(b.timestamp)}</dd>
      <dt>Nonce</dt><dd><code>${b.nonce}</code></dd>
      <dt>Merkle root</dt><dd><code>${esc(b.merkle_root)}</code></dd>
      <dt>Previous hash</dt><dd><code>${esc(b.previous_hash)}</code></dd>
      <dt>Hash</dt><dd><code>${esc(b.hash)}</code></dd>
    </dl>
    <h3>Financing records</h3>
    ${records}`;
}

// Draws the valid / in-sync result for each bank after "Validate Chain".
function renderValidation() {
  const r = validationReport;
  const summary = r.all_match && r.all_valid
    ? `<div class="alert alert-ok" style="grid-column: 1 / -1; margin: 0"><strong>All 3 chains are valid and identical</strong>Every hash, link, proof-of-work and Merkle root checks out.</div>`
    : `<div class="alert alert-bad" style="grid-column: 1 / -1; margin: 0"><strong>Problem detected</strong>${r.all_valid ? "The chains are valid but not identical." : "At least one bank's chain failed validation and no longer matches the others."}</div>`;
  const cards = r.banks.map((b) => `
    <div class="card node-card ${b.valid && b.in_sync ? "" : "bad"}" style="box-shadow: none">
      <div class="node-name"><span class="node-dot"></span>${esc(b.bank_name)}</div>
      <div class="row" style="gap: 6px">
        ${b.valid ? `<span class="badge badge-ok">Valid</span>` : `<span class="badge badge-bad">Invalid</span>`}
        ${b.in_sync ? `<span class="badge badge-ok">In sync</span>` : `<span class="badge badge-bad">Out of sync</span>`}
      </div>
      <div class="small muted">${b.length} blocks · digest <code>${shortHash(b.digest, 8, 4)}</code></div>
      ${b.errors.map((e) => `<div class="small" style="color: var(--red)">Block #${e.index}: ${esc(e.reason)}</div>`).join("")}
    </div>`).join("");
  document.getElementById("validation").innerHTML = summary + cards;
}

// "Validate Chain": asks the server to validate and compare all three chains.
async function validate() {
  const done = setLoading(document.getElementById("validate-btn"), "Validating…");
  const { data } = await api("GET", "/api/validate");
  done();
  validationReport = data;
  renderValidation();
  renderChain();
}

// "Tamper Demo": edits an old record in the selected bank's chain without re-mining it.
// Step 1: shows every financed invoice on the selected bank's chain, so the user can pick one.
async function tamper() {
  const invoices = (await api("GET", "/api/invoices")).data;
  const invoiceNumber = (fp) => invoices.find((i) => i.fingerprint === fp)?.invoice_number ?? `${fp.slice(0, 10)}…`;

  const rows = [];
  chainData.chain.forEach((block) => block.records.forEach((r, i) => rows.push(`
    <tr>
      <td>#${block.index}</td>
      <td><strong>${esc(invoiceNumber(r.fingerprint))}</strong><div class="muted small">${esc(r.supplier_name)}</div></td>
      <td>${esc(r.bank_name)}</td>
      <td class="num">${inr(r.amount_financed)}</td>
      <td><button class="btn btn-danger btn-sm" data-block="${block.index}" data-record="${i}">Tamper</button></td>
    </tr>`)));
  if (!rows.length) return toast("No financed invoices on this chain yet. Mine a block first.", "bad");

  openModal(`Tamper with ${chainData.bank_name}'s copy`, `
    <div class="card">
      <p class="muted small">Pick one invoice. Its financed amount will be multiplied by 10 in
        <strong>${esc(chainData.bank_name)}'s</strong> copy only, without re-mining the block.
        The other two banks keep the honest copy.</p>
      <div class="table-wrap"><table>
        <thead><tr><th>Block</th><th>Invoice</th><th>Financed by</th><th class="num">Amount</th><th></th></tr></thead>
        <tbody>${rows.join("")}</tbody>
      </table></div>
    </div>`);
  document.querySelectorAll("#modal [data-block]").forEach((button) => button.addEventListener("click", () => {
    closeModal();
    tamperRecord(Number(button.dataset.block), Number(button.dataset.record));
  }));
}

// Step 2: asks the server to change the chosen record, then shows what was changed.
async function tamperRecord(blockIndex, recordIndex) {
  const { ok, data } = await api("POST", "/api/tamper", { bank: selectedBank, block_index: blockIndex, record_index: recordIndex });
  if (!ok) return toast(data.error, "bad");
  validationReport = null;
  document.getElementById("tamper-note").innerHTML = `
    <div class="alert alert-bad"><strong>Tampered!</strong>${esc(data.message)} Now click <em>Validate Chain</em> to see if anyone notices.</div>`;
  document.getElementById("validation").innerHTML = "";
  selectedIndex = data.block_index;
  loadChain();
}

// "Sync Nodes": runs consensus so every broken or shorter chain is replaced by the longest valid chain.
async function sync() {
  const { data } = await api("POST", "/api/consensus");
  toast(data.updated.length ? `Replaced chain at: ${data.updated.join(", ")}` : "All chains already agree", "ok");
  document.getElementById("tamper-note").innerHTML = "";
  validationReport = data.network;
  renderValidation();
  loadChain();
}

document.getElementById("validate-btn").addEventListener("click", validate);
document.getElementById("tamper-btn").addEventListener("click", tamper);
document.getElementById("sync-btn").addEventListener("click", sync);
renderTabs();
loadChain();
