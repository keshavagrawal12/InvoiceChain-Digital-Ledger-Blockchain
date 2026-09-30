/*
 * bank.js - Bank Portal logic: choose a bank, list its requests, approve/reject them,
 * view the invoice, and mine pending records into a block.
 */

const bankSelect = document.getElementById("bank-select");

// Returns the id of the bank we are currently acting as.
function currentBank() {
  return bankSelect.value;
}

// Shows a big green (success) or red (fraud) message at the top of the page.
// An optional rubber stamp (HTML) is pressed onto the right-hand side of the message.
function showResult(html, type, stamp = "") {
  document.getElementById("result").innerHTML = `<div class="alert alert-${type} ${stamp ? "has-stamp" : ""}">${html}${stamp}</div>`;
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// Loads this bank's financing requests into the table. Pending ones get Approve/Reject buttons.
async function loadRequests() {
  const { data } = await api("GET", `/api/banks/${currentBank()}/requests`);
  const body = document.getElementById("requests");
  if (!data.length) {
    body.innerHTML = `<tr><td colspan="7" class="empty">No requests for this bank yet. Send one from the Supplier Portal.</td></tr>`;
    return;
  }
  body.innerHTML = data.map((r) => `
    <tr>
      <td><strong>${esc(r.id)}</strong><div class="muted small">${esc(r.created_at)}</div></td>
      <td>${esc(r.invoice_number)}</td>
      <td>${esc(r.supplier_name)}</td>
      <td class="num">${inr(r.invoice_total)}</td>
      <td class="num">${inr(r.amount_requested)}</td>
      <td>${statusBadge(r.status)}${r.status === "fraud" ? `<div class="small" style="color: var(--red)">${esc(r.message.replace("FRAUD ALERT: ", ""))}</div>` : ""}</td>
      <td>
        <div class="row" style="gap: 6px; flex-wrap: nowrap">
          <button class="btn btn-outline btn-sm" data-view="${esc(r.invoice_id)}">View Invoice</button>
          ${r.status === "pending" ? `
            <button class="btn btn-ok btn-sm" data-approve="${esc(r.id)}">Approve</button>
            <button class="btn btn-outline btn-sm" data-reject="${esc(r.id)}">Reject</button>` : ""}
        </div>
      </td>
    </tr>`).join("");

  body.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => viewInvoice(b.dataset.view)));
  body.querySelectorAll("[data-approve]").forEach((b) => b.addEventListener("click", () => approve(b.dataset.approve, b)));
  body.querySelectorAll("[data-reject]").forEach((b) => b.addEventListener("click", () => reject(b.dataset.reject)));
}

// Loads the records this bank has approved but not yet mined.
async function loadPending() {
  const { data } = await api("GET", `/api/banks/${currentBank()}/chain`);
  const records = data.pending_records;
  document.getElementById("mine-btn").disabled = records.length === 0;
  document.getElementById("pending").innerHTML = records.length
    ? records.map((r) => `
        <tr>
          <td><code title="${esc(r.fingerprint)}">${shortHash(r.fingerprint, 16, 8)}</code></td>
          <td>${esc(r.supplier_name)}</td>
          <td class="num">${inr(r.amount_financed)}</td>
          <td>${esc(r.financing_date)}</td>
        </tr>`).join("")
    : `<tr><td colspan="4" class="empty">No pending records. Approve a request first.</td></tr>`;
}

// Opens the full invoice in a pop-up so the bank can inspect it.
async function viewInvoice(invoiceId) {
  const { ok, data } = await api("GET", `/api/invoices/${invoiceId}`);
  if (!ok) return toast(data.error, "bad");
  openModal(`Invoice ${data.invoice_number}`, renderInvoice(data));
}

// Approves a request. The server runs the duplicate check on the blockchain.
async function approve(requestId, button) {
  const done = setLoading(button, "Checking chain…");
  const { ok, data } = await api("POST", `/api/banks/${currentBank()}/approve/${requestId}`);
  done();
  if (ok) {
    showResult(`<strong>No duplicate found. Request ${esc(requestId)} approved</strong>
      This invoice is not on the blockchain or pending at any bank. It is now in the pending list below, and other banks can see it. Click <em>Mine Block</em> to write it permanently onto the chain.`, "ok");
  } else if (data.fraud) {
    const d = data.duplicate;
    showResult(`<strong>FRAUD ALERT: Duplicate invoice</strong>
      ${esc(d.message)}${d.block_index !== null ? ` (block #${d.block_index})` : ""}.
      Request ${esc(requestId)} (invoice ${esc(data.request.invoice_number)}) has been rejected automatically.`, "bad",
      `<span class="stamp stamp-red stamp-thump">Duplicate<small>Rejected</small></span>`);
  } else {
    toast(data.error, "bad");
  }
  refresh();
}

// Rejects a request for normal business reasons.
async function reject(requestId) {
  const { ok, data } = await api("POST", `/api/banks/${currentBank()}/reject/${requestId}`);
  toast(ok ? `${requestId} rejected` : data.error, ok ? "" : "bad");
  refresh();
}

// Mines all pending records into a new block and shows how the other banks responded.
async function mine() {
  const done = setLoading(document.getElementById("mine-btn"), "Running proof-of-work…");
  const started = performance.now();
  const { ok, data } = await api("POST", `/api/banks/${currentBank()}/mine`);
  const seconds = ((performance.now() - started) / 1000).toFixed(2);
  done();
  if (!ok) {
    toast(data.error, "bad");
    return refresh();
  }
  document.getElementById("result").innerHTML = "";
  const b = data.block;
  const broadcast = data.broadcast.map((n) =>
    `<li>${esc(n.bank_name)}: ${n.accepted ? `<span class="badge badge-ok">validated &amp; added</span>` : `<span class="badge badge-bad">rejected</span> ${esc(n.reason)}`}</li>`).join("");
  document.getElementById("mine-result").innerHTML = `
    <div class="alert alert-info has-stamp" style="margin: 16px 0 0">
      <span class="stamp stamp-violet stamp-thump">Financed<small>Block #${b.index}</small></span>
      <strong>Block #${b.index} mined in ${seconds}s</strong>
      Nonce <code>${b.nonce}</code> · Hash <code>${shortHash(b.hash, 20, 8)}</code> · ${b.records.length} record(s)
      <div style="margin-top: 6px">Broadcast to the other banks:</div>
      <ul style="margin: 4px 0 0; padding-left: 20px">${broadcast}</ul>
    </div>`;
  refresh();
}

// Reloads both tables.
function refresh() {
  loadRequests();
  loadPending();
}

// Switching bank remembers the choice (so a page reload keeps the same bank) and reloads the tables.
bankSelect.addEventListener("change", () => {
  try { localStorage.setItem("invoicechain-bank", currentBank()); } catch (e) { /* storage may be blocked */ }
  document.getElementById("result").innerHTML = "";
  document.getElementById("mine-result").innerHTML = "";
  refresh();
});
document.getElementById("refresh-btn").addEventListener("click", refresh);
document.getElementById("mine-btn").addEventListener("click", mine);

// Start: pick the remembered bank (or the first one) and load its data.
(async () => {
  let saved = null;
  try { saved = localStorage.getItem("invoicechain-bank"); } catch (e) { /* ignore */ }
  await fillBankSelect(bankSelect, saved);
  refresh();
})();
