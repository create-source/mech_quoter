let catalog = null;
let estimateId = null;
let catByKey = new Map();
let svcByCodeByCat = new Map();

let yearChoices, makeChoices, modelChoices, catChoices, svcChoices;

const $ = (id) => document.getElementById(id);

function fmtMoney(x) {
  const n = Number(x || 0);
  return n.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

async function apiGet(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`GET ${url} failed: ${r.status}`);
  return r.json();
}

async function apiPost(url, body, headers = {}) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new Error(`POST ${url} failed: ${r.status} ${t}`);
  }
  return r.json();
}

// ---------- SIMPLE SIGNATURE PAD ----------
function makeSignaturePad(canvasId) {
  const canvas = $(canvasId);
  const ctx = canvas.getContext("2d");
  let drawing = false;
  let last = null;

  function resizeToDevice() {
    const rect = canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.floor(rect.width * ratio);
    canvas.height = Math.floor(rect.height * ratio);
    ctx.scale(ratio, ratio);
    ctx.lineWidth = 2;
    ctx.lineCap = "round";
    ctx.strokeStyle = "white";
  }

  function pos(e) {
    const rect = canvas.getBoundingClientRect();
    const x = (e.touches ? e.touches[0].clientX : e.clientX) - rect.left;
    const y = (e.touches ? e.touches[0].clientY : e.clientY) - rect.top;
    return { x, y };
  }

  function down(e) { e.preventDefault(); drawing = true; last = pos(e); }
  function up(e) { e.preventDefault(); drawing = false; last = null; }
  function move(e) {
    if (!drawing) return;
    e.preventDefault();
    const p = pos(e);
    ctx.beginPath();
    ctx.moveTo(last.x, last.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    last = p;
  }

  canvas.addEventListener("mousedown", down);
  canvas.addEventListener("mouseup", up);
  canvas.addEventListener("mouseleave", up);
  canvas.addEventListener("mousemove", move);

  canvas.addEventListener("touchstart", down, { passive: false });
  canvas.addEventListener("touchend", up, { passive: false });
  canvas.addEventListener("touchcancel", up, { passive: false });
  canvas.addEventListener("touchmove", move, { passive: false });

  window.addEventListener("resize", () => {
    // Reset the canvas on resize for simplicity
    const data = canvas.toDataURL("image/png");
    resizeToDevice();
    // don’t restore strokes perfectly; keep it simple
  });

  // Initialize
  setTimeout(() => resizeToDevice(), 0);

  return {
    clear() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
    },
    toDataURL() {
      // Need a stable export size; use current device pixels
      return canvas.toDataURL("image/png");
    }
  };
}

const approvePad = makeSignaturePad("sigCanvas");
const payPad = makeSignaturePad("payCanvas");

// ---------- UI ----------
function setTab(isOwner) {
  $("customerPanel").style.display = isOwner ? "none" : "block";
  $("ownerPanel").style.display = isOwner ? "block" : "none";
  $("tabCustomer").classList.toggle("active", !isOwner);
  $("tabOwner").classList.toggle("active", isOwner);
}

$("tabCustomer").addEventListener("click", () => setTab(false));
$("tabOwner").addEventListener("click", () => setTab(true));

function initChoices() {
  yearChoices = new Choices("#yearSelect", { shouldSort: false, searchEnabled: true });
  makeChoices = new Choices("#makeSelect", { shouldSort: false, searchEnabled: true });
  modelChoices = new Choices("#modelSelect", { shouldSort: false, searchEnabled: true });

  catChoices = new Choices("#categorySelect", { shouldSort: false, searchEnabled: true });
  svcChoices = new Choices("#serviceSelect", { shouldSort: false, searchEnabled: true });
}

function setChoices(choices, items, placeholder = "Select...") {
  choices.clearChoices();
  choices.setChoices(
    [{ value: "", label: placeholder, selected: true, disabled: true }].concat(
      items.map((x) => ({ value: x.value, label: x.label }))
    ),
    "value",
    "label",
    true
  );
}

function buildCatalogMaps() {
  catByKey = new Map();
  svcByCodeByCat = new Map();

  for (const c of (catalog.categories || [])) {
    catByKey.set(c.key, c);
    const m = new Map();
    for (const s of (c.services || [])) m.set(s.code, s);
    svcByCodeByCat.set(c.key, m);
  }
}

async function loadCatalog() {
  catalog = await apiGet("/catalog");
  buildCatalogMaps();

  const cats = (catalog.categories || []).map(c => ({ value: c.key, label: c.name }));
  setChoices(catChoices, cats, "Choose category");
  setChoices(svcChoices, [], "Choose service");
}

async function loadYears() {
  const years = await apiGet("/vehicle/years");
  setChoices(yearChoices, years.map(y => ({ value: String(y), label: String(y) })), "Choose year");
}

async function loadMakes(year) {
  const makes = await apiGet(`/vehicle/makes?year=${encodeURIComponent(year)}`);
  setChoices(makeChoices, makes.map(m => ({ value: m, label: m })), "Choose make");
  setChoices(modelChoices, [], "Choose model");
}

async function loadModels(year, make) {
  const models = await apiGet(`/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`);
  setChoices(modelChoices, models.map(m => ({ value: m, label: m })), "Choose model");
}

function onCategoryChange(catKey) {
  const c = catByKey.get(catKey);
  const svcs = (c?.services || []).map(s => ({ value: s.code, label: s.name }));
  setChoices(svcChoices, svcs, "Choose service");

  // Helpful: auto-fill labor hours if the service has range
  $("laborHours").value = "";
}

function onServiceChange(catKey, svcCode) {
  const svcMap = svcByCodeByCat.get(catKey);
  const svc = svcMap?.get(svcCode);
  if (!svc) return;

  // Pick a midpoint default
  const min = Number(svc.labor_hours_min || 0);
  const max = Number(svc.labor_hours_max || min);
  const mid = (min + max) / 2;
  if (!Number.isFinite(mid)) return;
  $("laborHours").value = mid.toFixed(1);
}

// ---------- EVENTS ----------
$("yearSelect").addEventListener("change", async (e) => {
  const year = e.target.value;
  if (!year) return;
  await loadMakes(year);
});

$("makeSelect").addEventListener("change", async (e) => {
  const year = $("yearSelect").value;
  const make = e.target.value;
  if (!year || !make) return;
  await loadModels(year, make);
});

$("categorySelect").addEventListener("change", (e) => {
  const catKey = e.target.value;
  if (!catKey) return;
  onCategoryChange(catKey);
});

$("serviceSelect").addEventListener("change", (e) => {
  const catKey = $("categorySelect").value;
  const svcCode = e.target.value;
  if (!catKey || !svcCode) return;
  onServiceChange(catKey, svcCode);
});

$("btnClearSig").addEventListener("click", () => approvePad.clear());
$("btnClearPaySig").addEventListener("click", () => payPad.clear());

$("btnCreateEstimate").addEventListener("click", async () => {
  try {
    const year = $("yearSelect").value;
    const make = $("makeSelect").value;
    const model = $("modelSelect").value;
    const category_key = $("categorySelect").value;
    const service_code = $("serviceSelect").value;

    const c = catByKey.get(category_key);
    const s = (svcByCodeByCat.get(category_key) || new Map()).get(service_code);

    if (!year || !make || !model) throw new Error("Pick Year, Make, Model.");
    if (!c || !s) throw new Error("Pick Category and Service.");

    const payload = {
      customer_name: $("customerName").value.trim(),
      customer_phone: $("customerPhone").value.trim(),
      customer_email: $("customerEmail").value.trim(),
      zip_code: $("zipCode").value.trim(),
      year,
      make,
      model,
      category_key,
      category_name: c.name,
      service_code,
      service_name: s.name,
      labor_rate: Number(catalog.labor_rate || 90),
      labor_hours: Number($("laborHours").value || 0),
      parts_price: Number($("partsPrice").value || 0),
      tax_rate: Number($("taxRate").value || 0),
      notes: $("notes").value.trim()
    };

    const res = await apiPost("/estimate", payload);
    estimateId = res.id;

    $("estimateResult").textContent =
      `Estimate Created: ${estimateId}\n` +
      `Subtotal: ${fmtMoney(res.totals.subtotal)}\n` +
      `Tax: ${fmtMoney(res.totals.tax)}\n` +
      `Total: ${fmtMoney(res.totals.total)}`;

    $("approvalCard").style.display = "block";
    $("paymentCard").style.display = "block";

    $("btnDownloadEstimatePdf").href = `/estimate/${encodeURIComponent(estimateId)}/pdf`;
    $("btnDownloadInvoicePdf").href = `/invoice/${encodeURIComponent(estimateId)}/pdf`;
  } catch (err) {
    $("estimateResult").textContent = String(err.message || err);
  }
});

$("btnApprove").addEventListener("click", async () => {
  try {
    if (!estimateId) throw new Error("Create an estimate first.");
    const signature_png = approvePad.toDataURL();
    const res = await apiPost(`/estimate/${encodeURIComponent(estimateId)}/approve`, { signature_png });
    $("approvalResult").textContent = `Approved ✅\nPDF ready.`;
    $("btnDownloadEstimatePdf").href = `/estimate/${encodeURIComponent(estimateId)}/pdf`;
  } catch (err) {
    $("approvalResult").textContent = String(err.message || err);
  }
});

$("btnAckPayment").addEventListener("click", async () => {
  try {
    if (!estimateId) throw new Error("Create an estimate first.");
    const signature_png = payPad.toDataURL();
    const res = await apiPost(`/invoice/${encodeURIComponent(estimateId)}/ack_payment`, { signature_png });
    $("paymentResult").textContent = `Payment acknowledged ✅\nInvoice PDF ready.`;
    $("btnDownloadInvoicePdf").href = `/invoice/${encodeURIComponent(estimateId)}/pdf`;
  } catch (err) {
    $("paymentResult").textContent = String(err.message || err);
  }
});

// ----- ADMIN -----
function basicAuthHeader(user, pass) {
  const token = btoa(`${user}:${pass}`);
  return { Authorization: `Basic ${token}` };
}

$("btnLoadAdmin").addEventListener("click", async () => {
  try {
    const user = $("adminUser").value.trim();
    const pass = $("adminPass").value.trim();
    if (!user || !pass) throw new Error("Enter admin credentials.");

    const list = await apiPost("/admin/estimates", {}, basicAuthHeader(user, pass));
    // ^ workaround: many hosts block GET+auth in some embedded fetch contexts; using POST avoids weirdness
    // server doesn’t have POST /admin/estimates, so fallback to GET properly:
  } catch (e) {
    // Actually do GET:
    try {
      const user = $("adminUser").value.trim();
      const pass = $("adminPass").value.trim();
      const headers = basicAuthHeader(user, pass);

      const r = await fetch("/admin/estimates", { headers });
      if (!r.ok) throw new Error(`Admin load failed: ${r.status}`);
      const rows = await r.json();

      const wrap = $("adminList");
      wrap.innerHTML = "";

      for (const row of rows) {
        const div = document.createElement("div");
        div.className = "adminItem";

        div.innerHTML = `
          <div class="adminRow">
            <div><b>${row.id}</b><div class="muted">${row.created_at}</div></div>
            <div class="muted">${row.year || ""} ${row.make || ""} ${row.model || ""}</div>
            <div><b>${fmtMoney(row.total || 0)}</b><div class="muted">${row.status} / ${row.invoice_status}</div></div>
          </div>
          <div class="actions">
            <a class="btn" href="/estimate/${encodeURIComponent(row.id)}/pdf" target="_blank" rel="noopener">Estimate PDF</a>
            <a class="btn" href="/invoice/${encodeURIComponent(row.id)}/pdf" target="_blank" rel="noopener">Invoice PDF</a>
            <button class="btn primary" data-invoice="${row.id}">Mark Invoiced</button>
          </div>
        `;

        div.querySelector("[data-invoice]").addEventListener("click", async (ev) => {
          const id = ev.currentTarget.getAttribute("data-invoice");
          const user2 = $("adminUser").value.trim();
          const pass2 = $("adminPass").value.trim();
          const headers2 = basicAuthHeader(user2, pass2);

          const rr = await fetch(`/admin/estimate/${encodeURIComponent(id)}/mark_invoiced`, {
            method: "POST",
            headers: { ...headers2, "Content-Type": "application/json" },
            body: JSON.stringify({})
          });
          if (!rr.ok) alert(`Failed: ${rr.status}`);
          else alert("Invoice marked as issued ✅");
        });

        wrap.appendChild(div);
      }
    } catch (err2) {
      $("adminList").textContent = String(err2.message || err2);
    }
  }
});

// ---------- STARTUP ----------
window.addEventListener("DOMContentLoaded", async () => {
  initChoices();
  await loadCatalog();
  await loadYears();
  setTab(false);
});
