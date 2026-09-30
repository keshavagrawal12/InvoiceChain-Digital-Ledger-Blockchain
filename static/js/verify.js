/*
 * verify.js - Verify Invoice logic: sends an invoice number (or a fingerprint) to /api/verify
 * and shows whether that invoice is already financed on the blockchain.
 */

// Switches between the "details" form and the "fingerprint" form.
document.querySelectorAll("[data-mode]").forEach((tab) => tab.addEventListener("click", () => {
  document.querySelectorAll("[data-mode]").forEach((t) => t.classList.toggle("active", t === tab));
  document.getElementById("details-form").classList.toggle("hidden", tab.dataset.mode !== "details");
  document.getElementById("fingerprint-form").classList.toggle("hidden", tab.dataset.mode !== "fingerprint");
}));

// Builds the result card for one invoice: financed (red), pending (red) or not financed (green).
function renderResult(r) {
  const inv = r.invoice;
  const details = inv ? `
      <dt>Invoice</dt><dd>${esc(inv.invoice_number)}</dd>
      <dt>Supplier</dt><dd>${esc(inv.supplier_name)}</dd>
      <dt>Buyer</dt><dd>${esc(inv.buyer_name)}</dd>
      <dt>Invoice total</dt><dd>${inr(inv.total)}</dd>` : "";
  const fingerprint = `<dt>Fingerprint</dt><dd><code>${esc(r.fingerprint)}</code></dd>`;

  if (r.status === "not_financed") {
    return `
      <div class="alert alert-ok"><strong>Not financed yet</strong>
        This invoice's fingerprint is not on the blockchain or pending at any bank.</div>
      <div class="card" style="margin-bottom: 16px"><dl class="kv">${details}${fingerprint}
        <dt>Checked on</dt><dd>${esc(r.checked_on)}'s copy of the chain</dd></dl></div>`;
  }
  const headline = r.status === "financed"
    ? `Financed by ${esc(r.bank_name)} on ${esc(r.financing_date)}, recorded in block #${r.block_index}.`
    : `Approved by ${esc(r.bank_name)} on ${esc(r.financing_date)}, waiting to be mined into a block.`;
  return `
    <div class="alert alert-bad has-stamp"><strong>Already financed. Do not finance again</strong>${headline}
      <span class="stamp ${r.status === "financed" ? "stamp-violet" : "stamp-red"} stamp-thump">${r.status === "financed" ? `Financed<small>Block #${r.block_index}</small>` : `Pending<small>Not mined</small>`}</span></div>
    <div class="card" style="margin-bottom: 16px"><dl class="kv">${details}
      <dt>Financed by</dt><dd>${esc(r.bank_name)}</dd>
      <dt>Amount financed</dt><dd>${inr(r.record.amount_financed)}</dd>
      <dt>Financing date</dt><dd>${esc(r.financing_date)}</dd>
      <dt>Block</dt><dd>${r.block_index !== null ? `#${r.block_index}` : "Pending (not mined yet)"}</dd>
      ${fingerprint}</dl></div>`;
}

// Sends the check to the server and shows one result card per matching invoice.
async function verify(body) {
  const { ok, data } = await api("POST", "/api/verify", body);
  const box = document.getElementById("verify-result");
  if (!ok) {
    box.innerHTML = `<div class="alert alert-bad"><strong>Cannot check</strong>${esc(data.error)}</div>`;
    return;
  }
  const note = data.results.length > 1
    ? `<p class="muted small">${data.results.length} invoices have this number (e.g. from different suppliers). Each one is checked separately.</p>` : "";
  box.innerHTML = note + data.results.map(renderResult).join("");
}

// Checks by invoice number only.
document.getElementById("details-form").addEventListener("submit", (e) => {
  e.preventDefault();
  verify({ invoice_number: document.getElementById("v-number").value });
});

// Checks by a pasted fingerprint.
document.getElementById("fingerprint-form").addEventListener("submit", (e) => {
  e.preventDefault();
  verify({ fingerprint: document.getElementById("v-fingerprint").value });
});
