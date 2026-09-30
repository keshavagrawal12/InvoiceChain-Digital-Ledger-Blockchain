/*
 * common.js - Helper functions shared by every page:
 * calling the API, showing messages, formatting money/hashes and drawing an invoice.
 */

// Calls our Flask API and returns { ok, status, data }. Never throws, so pages can show errors nicely.
async function api(method, url, body) {
  try {
    const options = { method, headers: { "Content-Type": "application/json" } };
    if (body !== undefined) options.body = JSON.stringify(body);
    const response = await fetch(url, options);
    const data = await response.json();
    return { ok: response.ok, status: response.status, data };
  } catch (err) {
    return { ok: false, status: 0, data: { error: "Could not reach the server. Is app.py running?" } };
  }
}

// Shows a small pop-up message in the bottom-right corner for a few seconds.
function toast(message, type = "") {
  const box = document.createElement("div");
  box.className = `toast ${type}`;
  box.textContent = message;
  document.getElementById("toasts").appendChild(box);
  setTimeout(() => box.remove(), 4500);
}

// Makes text safe to put inside HTML (stops user input from being treated as HTML code).
function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// Formats a number as Indian Rupees, e.g. 59000 -> "₹59,000.00".
function inr(amount) {
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" }).format(amount || 0);
}

// Shortens a long hash for display, e.g. "0000a1b2c3…9f8e".
function shortHash(hash, start = 12, end = 6) {
  if (!hash) return "";
  return hash.length > start + end ? `${hash.slice(0, start)}…${hash.slice(-end)}` : hash;
}

// Returns the HTML for a coloured status badge (pending, approved, financed, rejected, fraud).
function statusBadge(status) {
  const styles = { pending: "badge-warn", approved: "badge-info", financed: "badge-ok", rejected: "", fraud: "badge-bad" };
  const labels = { pending: "Pending", approved: "Approved · awaiting mining", financed: "Financed", rejected: "Rejected", fraud: "Fraud blocked" };
  return `<span class="badge ${styles[status] ?? ""}">${labels[status] ?? esc(status)}</span>`;
}

// Loads the list of banks once and remembers it.
let cachedBanks = null;
async function getBanks() {
  if (!cachedBanks) cachedBanks = (await api("GET", "/api/banks")).data;
  return cachedBanks;
}

// Fills a <select> element with the three banks.
async function fillBankSelect(select, selected) {
  const banks = await getBanks();
  select.innerHTML = banks.map((b) => `<option value="${b.id}" ${b.id === selected ? "selected" : ""}>${esc(b.name)}</option>`).join("");
}

// Puts a button into a "loading" state (spinner + text) and returns a function that restores it.
function setLoading(button, text) {
  const original = button.innerHTML;
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span>${esc(text)}`;
  return () => { button.disabled = false; button.innerHTML = original; };
}

// Builds the HTML of a full invoice (header, parties, items, totals, fingerprint, demo watermark).
function renderInvoice(inv) {
  const rows = inv.items.map((item, i) => `
    <tr>
      <td>${i + 1}</td>
      <td>${esc(item.description)}</td>
      <td class="num">${item.quantity}</td>
      <td class="num">${inr(item.rate)}</td>
      <td class="num">${inr(item.amount)}</td>
    </tr>`).join("");

  return `
  <div class="invoice">
    <div class="watermark">Demo invoice<br>for project use only</div>
    <div class="demo-banner">Demo invoice — for project use only · not a real tax document</div>
    <div class="inv-top">
      <div>
        <div class="inv-title">TAX INVOICE</div>
        <div class="muted small">${esc(inv.supplier_name)}</div>
      </div>
      <div class="inv-meta">
        <div><strong>Invoice No:</strong> ${esc(inv.invoice_number)}</div>
        <div><strong>Invoice Date:</strong> ${esc(inv.invoice_date)}</div>
        <div><strong>Due Date:</strong> ${esc(inv.due_date)}</div>
      </div>
    </div>
    <div class="inv-parties">
      <div class="inv-party">
        <div class="tag">Supplier (billed from)</div>
        <div class="name">${esc(inv.supplier_name)}</div>
        <div>GST No: <span class="mono">${esc(inv.supplier_gstin)}</span></div>
      </div>
      <div class="inv-party">
        <div class="tag">Buyer (billed to)</div>
        <div class="name">${esc(inv.buyer_name)}</div>
        <div>GST No: <span class="mono">${esc(inv.buyer_gstin)}</span></div>
      </div>
    </div>
    <div class="table-wrap">
      <table class="inv-items">
        <thead><tr><th>#</th><th>Description</th><th class="num">Qty</th><th class="num">Rate</th><th class="num">Amount</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="inv-totals">
      <div><span>Subtotal</span><span>${inr(inv.subtotal)}</span></div>
      <div><span>GST @ ${Math.round(inv.gst_rate * 100)}%</span><span>${inr(inv.gst_amount)}</span></div>
      <div class="grand"><span>Grand Total</span><span>${inr(inv.total)}</span></div>
    </div>
    <div class="inv-fingerprint">
      <strong>Invoice fingerprint (SHA-256)</strong> — the only thing stored on the blockchain
      <code>${esc(inv.fingerprint)}</code>
    </div>
  </div>`;
}

// Opens a pop-up window (modal) with a title and some HTML inside.
function openModal(title, html) {
  closeModal();
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.id = "modal";
  backdrop.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true">
      <div class="modal-head"><h3>${esc(title)}</h3><button class="btn btn-outline btn-sm" onclick="closeModal()">Close</button></div>
      ${html}
    </div>`;
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) closeModal(); });
  document.body.appendChild(backdrop);
}

// Closes the pop-up window if one is open.
function closeModal() {
  document.getElementById("modal")?.remove();
}

// Lets the Escape key close any open pop-up.
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
