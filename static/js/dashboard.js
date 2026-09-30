/*
 * dashboard.js - Loads the stats cards and node status on the home page,
 * and handles the "Load Demo Data" and "Reset Everything" buttons.
 */

// Fetches /api/stats and fills in the stats cards and the three bank node cards.
async function loadDashboard() {
  const { data } = await api("GET", "/api/stats");
  if (!data || data.error) return;

  document.getElementById("s-invoices").textContent = data.total_invoices;
  document.getElementById("s-financed").textContent = inr(data.total_financed);
  document.getElementById("s-financed-count").textContent = `${data.invoices_financed} invoice(s) on-chain`;
  document.getElementById("s-fraud").textContent = data.fraud_blocked;
  document.getElementById("s-length").textContent = data.chain_length;

  const net = data.network;
  const inSync = net.all_match && net.all_valid;
  document.getElementById("sync-badge").innerHTML = inSync
    ? `<span class="badge badge-ok">All 3 nodes in sync</span>`
    : `<span class="badge badge-bad">Nodes out of sync</span>`;

  document.getElementById("nodes").innerHTML = net.banks.map((b) => `
    <div class="card node-card ${b.in_sync ? "" : "bad"}">
      <div class="node-name"><span class="node-dot"></span>${esc(b.bank_name)}</div>
      <div>${b.in_sync ? `<span class="badge badge-ok">In sync</span>` : `<span class="badge badge-bad">${b.valid ? "Out of sync" : "Invalid chain"}</span>`}</div>
      <dl class="kv">
        <dt>Blocks</dt><dd>${b.length}</dd>
        <dt>Pending</dt><dd>${b.pending} record(s)</dd>
        <dt>Last hash</dt><dd><code>${shortHash(b.last_hash)}</code></dd>
      </dl>
    </div>`).join("");
}

// "Load Demo Data": resets and fills the system with sample invoices, blocks and one fraud attempt.
document.getElementById("demo-btn").addEventListener("click", async (e) => {
  const done = setLoading(e.currentTarget, "Mining demo blocks…");
  const { ok, data } = await api("POST", "/api/demo-data");
  done();
  toast(ok ? data.message : data.error, ok ? "ok" : "bad");
  loadDashboard();
});

// "Reset Everything": clears all invoices, requests and blocks after asking for confirmation.
document.getElementById("reset-btn").addEventListener("click", async () => {
  if (!confirm("Delete all invoices, requests and blocks, and start again from the genesis block?")) return;
  const { ok, data } = await api("POST", "/api/reset");
  toast(ok ? data.message : data.error, ok ? "ok" : "bad");
  loadDashboard();
});

loadDashboard();
