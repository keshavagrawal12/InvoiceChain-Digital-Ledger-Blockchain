/*
 * supplier.js - Supplier Portal logic: line items with live totals, generating the invoice,
 * printing it as a PDF, sending it to a bank, and listing past invoices with their status.
 */

const GST_RATE = 0.18;
let currentInvoice = null;   // the invoice shown in the preview

// Returns a date as YYYY-MM-DD, moved forward by `addDays` days.
function isoDate(addDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + addDays);
  return d.toLocaleDateString("en-CA"); // en-CA formats as YYYY-MM-DD
}

// Adds one empty (or pre-filled) line item row to the items table.
function addItemRow(description = "", quantity = 1, rate = "") {
  const row = document.createElement("tr");
  row.innerHTML = `
    <td><input class="i-desc" placeholder="Item description" value="${esc(description)}" required></td>
    <td><input class="i-qty" type="number" min="0.01" step="any" value="${quantity}" required></td>
    <td><input class="i-rate" type="number" min="0" step="0.01" value="${rate}" required></td>
    <td class="num i-amount">₹0.00</td>
    <td><button type="button" class="btn btn-link i-remove" title="Remove">✕</button></td>`;
  row.querySelector(".i-remove").addEventListener("click", () => {
    if (document.querySelectorAll("#items tr").length > 1) row.remove();
    updateTotals();
  });
  document.getElementById("items").appendChild(row);
  updateTotals();
}

// Reads all line items from the table.
function readItems() {
  return [...document.querySelectorAll("#items tr")].map((row) => ({
    description: row.querySelector(".i-desc").value,
    quantity: parseFloat(row.querySelector(".i-qty").value) || 0,
    rate: parseFloat(row.querySelector(".i-rate").value) || 0,
  }));
}

// Recalculates each row's amount plus the subtotal, 18% GST and grand total.
function updateTotals() {
  let subtotal = 0;
  document.querySelectorAll("#items tr").forEach((row) => {
    const amount = (parseFloat(row.querySelector(".i-qty").value) || 0) * (parseFloat(row.querySelector(".i-rate").value) || 0);
    row.querySelector(".i-amount").textContent = inr(amount);
    subtotal += amount;
  });
  const gst = Math.round(subtotal * GST_RATE * 100) / 100;
  document.getElementById("t-subtotal").textContent = inr(subtotal);
  document.getElementById("t-gst").textContent = inr(gst);
  document.getElementById("t-total").textContent = inr(subtotal + gst);
}

// Asks the server for the next invoice number and puts it in the form.
async function suggestInvoiceNumber() {
  const { data } = await api("GET", "/api/next-invoice-number");
  document.getElementById("invoice_number").value = data.invoice_number;
}

// Clears the form back to defaults: today's date, due in 30 days, one empty line item.
function resetForm() {
  document.getElementById("invoice-form").reset();
  document.getElementById("invoice_date").value = isoDate();
  document.getElementById("due_date").value = isoDate(30);
  document.getElementById("items").innerHTML = "";
  addItemRow();
  suggestInvoiceNumber();
}

// Fills the form with realistic sample data so the demo is quick.
function fillSample() {
  const values = {
    supplier_name: "Shakti Auto Components", supplier_gstin: "GST-SHAKTI-001",
    buyer_name: "Ganga Motors Ltd", buyer_gstin: "GST-GANGA-002",
  };
  Object.entries(values).forEach(([id, value]) => { document.getElementById(id).value = value; });
  document.getElementById("items").innerHTML = "";
  addItemRow("Brake pads (set of 4)", 120, 1450);
  addItemRow("Clutch plate assembly", 35, 3200);
}

// Shows an invoice in the preview panel with the PDF and Send to Bank controls.
function showPreview(invoice) {
  currentInvoice = invoice;
  document.getElementById("preview-empty").classList.add("hidden");
  document.getElementById("invoice-print-area").innerHTML = renderInvoice(invoice);
  document.getElementById("pdf-btn").classList.remove("hidden");
  document.getElementById("send-box").classList.remove("hidden");
}

// Submits the form to the server, which calculates totals and the fingerprint, then shows the preview.
async function generateInvoice(event) {
  event.preventDefault();
  const body = {
    supplier_name: document.getElementById("supplier_name").value,
    supplier_gstin: document.getElementById("supplier_gstin").value,
    buyer_name: document.getElementById("buyer_name").value,
    buyer_gstin: document.getElementById("buyer_gstin").value,
    invoice_number: document.getElementById("invoice_number").value,
    invoice_date: document.getElementById("invoice_date").value,
    due_date: document.getElementById("due_date").value,
    items: readItems(),
  };
  const done = setLoading(document.getElementById("generate-btn"), "Generating…");
  const { ok, data } = await api("POST", "/api/invoices", body);
  done();
  if (!ok) return toast(data.error, "bad");

  showPreview(data.invoice);
  toast(`Invoice ${data.invoice.invoice_number} created`, "ok");
  suggestInvoiceNumber();
  loadPastInvoices();
  if (window.innerWidth < 960) document.getElementById("preview-card").scrollIntoView({ behavior: "smooth" });
}

// Opens the browser print dialog; the print stylesheet prints only the invoice (choose "Save as PDF").
function downloadPdf() {
  const originalTitle = document.title;
  document.title = currentInvoice ? currentInvoice.invoice_number : "invoice";
  window.print();
  document.title = originalTitle;
}

// Sends the invoice in the preview to the selected bank.
async function sendToBank() {
  if (!currentInvoice) return;
  const bank = document.getElementById("send-bank").value;
  const { ok, data } = await api("POST", "/api/finance-request", { invoice_id: currentInvoice.id, bank });
  if (!ok) return toast(data.error, "bad");
  toast(`${data.request.id} sent to ${data.request.bank_name}`, "ok");
  loadPastInvoices();
}

// Loads all invoices and shows each with its financing requests and their status.
async function loadPastInvoices() {
  const { data } = await api("GET", "/api/invoices");
  const body = document.getElementById("past-invoices");
  if (!data.length) {
    body.innerHTML = `<tr><td colspan="6" class="empty">No invoices yet.</td></tr>`;
    return;
  }
  body.innerHTML = data.map((inv) => {
    const requests = inv.requests.length
      ? inv.requests.map((r) => `<div title="${esc(r.message)}">${esc(r.bank_name)} ${statusBadge(r.status)}</div>`).join("")
      : `<span class="muted small">Not sent yet</span>`;
    return `
      <tr>
        <td><strong>${esc(inv.invoice_number)}</strong><div class="muted small">${esc(inv.supplier_name)}</div></td>
        <td>${esc(inv.buyer_name)}</td>
        <td>${esc(inv.invoice_date)}</td>
        <td class="num">${inr(inv.total)}</td>
        <td class="small">${requests}</td>
        <td><button class="btn btn-outline btn-sm" data-open="${esc(inv.id)}">Open</button></td>
      </tr>`;
  }).join("");

  body.querySelectorAll("[data-open]").forEach((button) => {
    button.addEventListener("click", () => {
      showPreview(data.find((inv) => inv.id === button.dataset.open));
      document.getElementById("preview-card").scrollIntoView({ behavior: "smooth" });
    });
  });
}

// Wire up the page.
document.getElementById("add-item").addEventListener("click", () => addItemRow());
document.getElementById("items").addEventListener("input", updateTotals);
document.getElementById("sample-btn").addEventListener("click", fillSample);
document.getElementById("invoice-form").addEventListener("submit", generateInvoice);
document.getElementById("pdf-btn").addEventListener("click", downloadPdf);
document.getElementById("send-btn").addEventListener("click", sendToBank);
fillBankSelect(document.getElementById("send-bank"));
resetForm();
loadPastInvoices();
