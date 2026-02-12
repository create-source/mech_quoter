/* static/app.js
   Production-stable app.js that uses services_catalog.json via API:
   - GET /api/categories
   - GET /api/services/{category_key}
   - (optional) GET /api/service/{service_code}  [not required here]
   - Estimate/PDF send serviceCode (recommended) + service name as fallback
*/

// ===============================
// SERVICE WORKER REGISTRATION (root scope) + updates
// ===============================
window.addEventListener("load", () => {
  registerServiceWorkerWithUpdates();
});

}
// ===============================
// PWA UPDATE NOTIFICATION
// ===============================
let swRegistration = null;
let hasPromptedUpdate = false;

const updateBanner = document.getElementById("updateBanner");
const updateReloadBtn = document.getElementById("updateReloadBtn");
const updateDismissBtn = document.getElementById("updateDismissBtn");

function showUpdateBanner() {
  if (!updateBanner || hasPromptedUpdate) return;
  hasPromptedUpdate = true;
  updateBanner.hidden = false;
}

function hideUpdateBanner() {
  if (!updateBanner) return;
  updateBanner.hidden = true;
}

async function activateUpdateAndReload() {
  try {
    if (!swRegistration) return window.location.reload();
    if (swRegistration.waiting) {
      swRegistration.waiting.postMessage({ type: "SKIP_WAITING" });
    }
  } finally {
    // New SW takes control after controllerchange
  }
}

function setupUpdateUI() {
  if (updateReloadBtn) updateReloadBtn.addEventListener("click", activateUpdateAndReload);
  if (updateDismissBtn) updateDismissBtn.addEventListener("click", hideUpdateBanner);

  // When the new SW activates and takes control, reload once.
  let reloaded = false;
  navigator.serviceWorker?.addEventListener("controllerchange", () => {
    if (reloaded) return;
    reloaded = true;
    window.location.reload();
  });
}

async function registerServiceWorkerWithUpdates() {
  if (!("serviceWorker" in navigator)) return;

  setupUpdateUI();

  try {
    swRegistration = await navigator.serviceWorker.register("/sw.js");

    // If there's already a waiting SW (user visited before), prompt immediately
    if (swRegistration.waiting) showUpdateBanner();

    // Listen for new SW installing
    swRegistration.addEventListener("updatefound", () => {
      const newWorker = swRegistration.installing;
      if (!newWorker) return;

      newWorker.addEventListener("statechange", () => {
        // "installed" + there's an existing controller means update is ready
        if (newWorker.state === "installed" && navigator.serviceWorker.controller) {
          showUpdateBanner();
        }
      });
    });

    // Optional: periodically check for updates (mobile-friendly)
    // Checks every 30 minutes while app is open
    setInterval(() => {
      swRegistration?.update().catch(() => {});
    }, 30 * 60 * 1000);

  } catch (err) {
    console.error("SW registration failed:", err);
  }
}


// ===============================
// DOM HELPERS
// ===============================
const $ = (id) => document.getElementById(id);

const yearEl = $("year");
const makeEl = $("make");
const modelEl = $("model");

const categoryEl = $("category");
const serviceEl = $("service");

const laborHoursEl = $("laborHours");
const partsPriceEl = $("partsPrice");
const laborRateEl = $("laborRate");
const notesEl = $("notes");

const estimateBtn = $("estimateBtn");
const pdfBtn = $("pdfBtn");
const clearBtn = $("clearBtn");
const statusBox = $("statusBox");

const sigCanvas = $("sigCanvas");
const sigClearBtn = $("sigClearBtn");
const customerNameEl = $("customerName");
const customerPhoneEl = $("customerPhone");

// ===============================
// STATUS UI
// ===============================
function setStatus(msg = "", kind = "info") {
  if (!statusBox) return;
  statusBox.textContent = msg;
  statusBox.dataset.kind = kind;
}

function setDisabled(el, disabled) {
  if (!el) return;
  el.disabled = !!disabled;
  el.style.opacity = disabled ? "0.7" : "1";
}

// ===============================
// FETCH HELPERS
// ===============================
async function fetchJson(url, options = {}) {
  const res = await fetch(url, { cache: "no-store", ...options });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} ${txt}`.trim());
  }
  return res.json();
}

// ===============================
// YEAR DROPDOWN
// ===============================
function loadYears() {
  if (!yearEl) return;
  const now = new Date().getFullYear();
  const start = now + 1;
  const end = 1970;

  yearEl.innerHTML = "";
  for (let y = start; y >= end; y--) {
    const opt = document.createElement("option");
    opt.value = String(y);
    opt.textContent = String(y);
    yearEl.appendChild(opt);
  }
  yearEl.value = String(now);
}

// ===============================
// MAKES / MODELS
// ===============================
async function loadMakes() {
  if (!makeEl) return;

  try {
    setStatus("Loading makes...");
    setDisabled(makeEl, true);
    setDisabled(modelEl, true);

    const makes = await fetchJson("/api/makes");

    makeEl.innerHTML = `<option value="">Select Make</option>`;
    for (const m of makes) {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      makeEl.appendChild(opt);
    }

    modelEl.innerHTML = `<option value="">Select Model</option>`;
    setStatus("");
  } catch (err) {
    console.error(err);
    setStatus("Could not load makes. Is the server running?", "error");
  } finally {
    setDisabled(makeEl, false);
    setDisabled(modelEl, false);
  }
}

async function loadModels(make) {
  if (!modelEl) return;

  try {
    if (!make) {
      modelEl.innerHTML = `<option value="">Select Model</option>`;
      return;
    }

    setStatus("Loading models...");
    setDisabled(modelEl, true);

    const models = await fetchJson(`/api/models/${encodeURIComponent(make)}`);

    modelEl.innerHTML = `<option value="">Select Model</option>`;
    for (const m of models) {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      modelEl.appendChild(opt);
    }

    setStatus("");
  } catch (err) {
    console.error(err);
    setStatus("Could not load models for that make.", "error");
    modelEl.innerHTML = `<option value="">Select Model</option>`;
  } finally {
    setDisabled(modelEl, false);
  }
}

if (makeEl) {
  makeEl.addEventListener("change", (e) => {
    loadModels(e.target.value);
  });
}

// ===============================
// SERVICES CATALOG (Category -> Service)
// ===============================
let categoriesCache = [];          // [{key,name}]
let servicesByCategory = new Map(); // key -> services[]
let selectedService = null;         // {code,name,labor_hours_min,labor_hours_max}

function midpoint(min, max) {
  const mn = Number(min);
  const mx = Number(max);
  if (!Number.isFinite(mn) || !Number.isFinite(mx)) return 0;
  if (mx <= 0) return 0;
  if (mn < 0) return 0;
  if (mx < mn) return mn;
  return (mn + mx) / 2;
}

function setLaborHoursFromService(svc) {
  if (!laborHoursEl) return;
  if (!svc) return;

  const mid = midpoint(svc.labor_hours_min, svc.labor_hours_max);
  // Only auto-fill if user hasn't typed a custom number (or it's 0)
  const current = parseFloat(laborHoursEl.value || "0") || 0;
  if (current <= 0 && mid > 0) {
    laborHoursEl.value = String(Math.round(mid * 10) / 10);
  }
}

function renderCategories(categories) {
  if (!categoryEl) return;
  categoryEl.innerHTML = `<option value="">Select Category</option>`;

  for (const c of categories) {
    const opt = document.createElement("option");
    opt.value = c.key;
    opt.textContent = c.name || c.key;
    categoryEl.appendChild(opt);
  }
}

function renderServices(services) {
  if (!serviceEl) return;

  serviceEl.innerHTML = `<option value="">Select Service</option>`;
  selectedService = null;

  for (const s of services) {
    const opt = document.createElement("option");
    opt.value = s.code;                 // IMPORTANT: use service code
    opt.textContent = s.name || s.code;  // show name
    opt.dataset.name = s.name || s.code;
    serviceEl.appendChild(opt);
  }
}

async function loadCategories() {
  if (!categoryEl || !serviceEl) return;

  try {
    setStatus("Loading service catalog...");
    setDisabled(categoryEl, true);
    setDisabled(serviceEl, true);

    const cats = await fetchJson("/api/categories");
    categoriesCache = Array.isArray(cats) ? cats : [];

    renderCategories(categoriesCache);
    renderServices([]);

    setStatus("");
  } catch (err) {
    console.error(err);
    setStatus("Could not load service categories. Check services_catalog.json + app.py.", "error");

    // fallback: empty but not broken
    if (categoryEl) categoryEl.innerHTML = `<option value="">General</option>`;
    if (serviceEl) serviceEl.innerHTML = `<option value="">Select Service</option>`;
  } finally {
    setDisabled(categoryEl, false);
    setDisabled(serviceEl, false);
  }
}

async function loadServicesForCategory(categoryKey) {
  if (!serviceEl) return;

  try {
    if (!categoryKey) {
      renderServices([]);
      return;
    }

    setStatus("Loading services...");
    setDisabled(serviceEl, true);

    if (servicesByCategory.has(categoryKey)) {
      renderServices(servicesByCategory.get(categoryKey));
      setStatus("");
      return;
    }

    const services = await fetchJson(`/api/services/${encodeURIComponent(categoryKey)}`);
    const list = Array.isArray(services) ? services : [];
    servicesByCategory.set(categoryKey, list);

    renderServices(list);
    setStatus("");
  } catch (err) {
    console.error(err);
    setStatus("Could not load services for that category.", "error");
    renderServices([]);
  } finally {
    setDisabled(serviceEl, false);
  }
}

if (categoryEl) {
  categoryEl.addEventListener("change", (e) => {
    const key = e.target.value;
    // Reset any previous manual labor hours if you want:
    // if (laborHoursEl) laborHoursEl.value = "0";
    loadServicesForCategory(key);
  });
}

if (serviceEl) {
  serviceEl.addEventListener("change", () => {
    const catKey = categoryEl?.value || "";
    const list = servicesByCategory.get(catKey) || [];
    const code = serviceEl.value;

    selectedService = list.find((s) => s.code === code) || null;

    // Auto-fill labor hours midpoint when selecting a service
    if (selectedService) setLaborHoursFromService(selectedService);
  });
}

// ===============================
// SIGNATURE CANVAS (mobile-friendly)
// ===============================
let sigCtx = null;
let sigDrawing = false;
let sigHasInk = false;

function setupCanvasScale() {
  if (!sigCanvas) return;

  const rect = sigCanvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;

  // Save existing drawing before resize (best effort)
  const prev = sigHasInk ? sigCanvas.toDataURL("image/png") : null;

  sigCanvas.width = Math.floor(rect.width * dpr);
  sigCanvas.height = Math.floor(rect.height * dpr);

  sigCtx = sigCanvas.getContext("2d");
  sigCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  sigCtx.lineWidth = 2;
  sigCtx.lineCap = "round";

  if (prev) {
    const img = new Image();
    img.onload = () => sigCtx.drawImage(img, 0, 0, rect.width, rect.height);
    img.src = prev;
  }
}

function pointFromEvent(evt) {
  const rect = sigCanvas.getBoundingClientRect();
  const touch = evt.touches && evt.touches[0];
  const clientX = touch ? touch.clientX : evt.clientX;
  const clientY = touch ? touch.clientY : evt.clientY;
  return { x: clientX - rect.left, y: clientY - rect.top };
}

function sigStart(evt) {
  if (!sigCtx) return;
  sigDrawing = true;
  const p = pointFromEvent(evt);
  sigCtx.beginPath();
  sigCtx.moveTo(p.x, p.y);
  evt.preventDefault?.();
}

function sigMove(evt) {
  if (!sigDrawing || !sigCtx) return;
  const p = pointFromEvent(evt);
  sigCtx.lineTo(p.x, p.y);
  sigCtx.stroke();
  sigHasInk = true;
  evt.preventDefault?.();
}

function sigEnd() {
  sigDrawing = false;
}

function clearSignature() {
  if (!sigCanvas || !sigCtx) return;
  const rect = sigCanvas.getBoundingClientRect();
  sigCtx.clearRect(0, 0, rect.width, rect.height);
  sigHasInk = false;
}

function getSignatureDataUrl() {
  if (!sigCanvas || !sigHasInk) return null;
  return sigCanvas.toDataURL("image/png");
}

function initSignature() {
  if (!sigCanvas) return;
  setupCanvasScale();
  window.addEventListener("resize", setupCanvasScale);

  // Mouse
  sigCanvas.addEventListener("mousedown", sigStart);
  sigCanvas.addEventListener("mousemove", sigMove);
  window.addEventListener("mouseup", sigEnd);

  // Touch
  sigCanvas.addEventListener("touchstart", sigStart, { passive: false });
  sigCanvas.addEventListener("touchmove", sigMove, { passive: false });
  sigCanvas.addEventListener("touchend", sigEnd);

  if (sigClearBtn) sigClearBtn.addEventListener("click", clearSignature);
}

// ===============================
// CLEAR FIELDS
// ===============================
function clearFields() {
  if (yearEl) yearEl.value = String(new Date().getFullYear());

  if (makeEl) makeEl.value = "";
  if (modelEl) modelEl.innerHTML = `<option value="">Select Model</option>`;

  if (categoryEl) categoryEl.value = "";
  if (serviceEl) serviceEl.innerHTML = `<option value="">Select Service</option>`;

  selectedService = null;

  if (laborHoursEl) laborHoursEl.value = "0";
  if (partsPriceEl) partsPriceEl.value = "0";
  if (laborRateEl) laborRateEl.value = ""; // let backend default if blank
  if (notesEl) notesEl.value = "";

  if (customerNameEl) customerNameEl.value = "";
  if (customerPhoneEl) customerPhoneEl.value = "";

  clearSignature();
  setStatus("");
}

if (clearBtn) clearBtn.addEventListener("click", clearFields);

// ===============================
// BUILD REQUEST PAYLOAD
// ===============================
function num(el, fallback = 0) {
  const v = parseFloat(el?.value ?? "");
  return Number.isFinite(v) ? v : fallback;
}

function buildPayload() {
  const catKey = categoryEl?.value || "";
  const svcCode = serviceEl?.value || "";
  const svcName = selectedService?.name || (serviceEl?.selectedOptions?.[0]?.textContent || "").trim();

  // If user typed a custom labor rate, send it; else let backend use default_labor_rate
  const lrRaw = (laborRateEl?.value ?? "").trim();
  const laborRate = lrRaw === "" ? null : num(laborRateEl, 0);

  return {
    year: parseInt(yearEl?.value || "", 10),
    make: (makeEl?.value || "").trim(),
    model: (modelEl?.value || "").trim(),

    category: catKey || null,

    // recommended
    serviceCode: svcCode || null,

    // fallback for display / compatibility
    service: svcName || null,

    laborHours: num(laborHoursEl, 0),
    partsPrice: num(partsPriceEl, 0),
    laborRate, // null means backend default

    notes: (notesEl?.value || "").trim() || null,
    customerName: (customerNameEl?.value || "").trim() || null,
    customerPhone: (customerPhoneEl?.value || "").trim() || null,

    signatureDataUrl: getSignatureDataUrl()
  };
}

function validatePayload(p) {
  if (!p.year || Number.isNaN(p.year)) return "Select a year.";
  if (!p.make) return "Select a make.";
  if (!p.model) return "Select a model.";
  if (!p.serviceCode && !p.service) return "Select a service.";
  if (p.laborHours < 0) return "Labor hours must be 0 or greater.";
  if (p.partsPrice < 0) return "Parts price must be 0 or greater.";
  if (p.laborRate !== null && p.laborRate < 0) return "Labor rate must be 0 or greater.";
  return null;
}

// ===============================
// CREATE ESTIMATE
// ===============================
async function createEstimate() {
  const payload = buildPayload();
  const err = validatePayload(payload);
  if (err) return setStatus(err, "error");

  try {
    setDisabled(estimateBtn, true);
    setDisabled(pdfBtn, true);
    setStatus("Creating estimate...");

    const res = await fetch("/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`Estimate failed: ${res.status} ${txt}`.trim());
    }

    const result = await res.json();
    setStatus(`Estimated Total: $${result.estimate}`, "ok");
  } catch (e) {
    console.error(e);
    setStatus("Estimate failed. Check server and try again.", "error");
  } finally {
    setDisabled(estimateBtn, false);
    setDisabled(pdfBtn, false);
  }
}

if (estimateBtn) estimateBtn.addEventListener("click", createEstimate);

// ===============================
// DOWNLOAD PDF
// ===============================
async function downloadPdf() {
  const payload = buildPayload();
  const err = validatePayload(payload);
  if (err) return setStatus(err, "error");

  try {
    setDisabled(estimateBtn, true);
    setDisabled(pdfBtn, true);
    setStatus("Generating PDF...");

    const res = await fetch("/estimate/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`PDF failed: ${res.status} ${txt}`.trim());
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = "estimate.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();

    URL.revokeObjectURL(url);
    setStatus("PDF downloaded.", "ok");
  } catch (e) {
    console.error(e);
    setStatus("Could not generate PDF.", "error");
  } finally {
    setDisabled(estimateBtn, false);
    setDisabled(pdfBtn, false);
  }
}

if (pdfBtn) pdfBtn.addEventListener("click", downloadPdf);

// ===============================
// INIT
// ===============================
document.addEventListener("DOMContentLoaded", async () => {
  loadYears();
  initSignature();

  await loadMakes();
  await loadCategories();

  setStatus("");
});
