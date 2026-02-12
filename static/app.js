// ===============================
// SERVICE WORKER REGISTRATION (root scope)
// ===============================
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js")
      .then(() => console.log("Service Worker registered"))
      .catch((err) => console.error("SW registration failed:", err));
  });
}

// ===============================
// DOM
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
function setStatus(msg, kind = "info") {
  if (!statusBox) return;
  statusBox.textContent = msg || "";
  statusBox.dataset.kind = kind; // optional hook for CSS
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
// MAKE/MODEL
// ===============================
async function loadMakes() {
  try {
    setStatus("Loading makes...");
    const res = await fetch("/api/makes", { cache: "no-store" });
    if (!res.ok) throw new Error(`Makes failed: ${res.status}`);
    const makes = await res.json();

    makeEl.innerHTML = `<option value="">Select Make</option>`;
    makes.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      makeEl.appendChild(opt);
    });

    modelEl.innerHTML = `<option value="">Select Model</option>`;
    setStatus("");
  } catch (err) {
    console.error(err);
    setStatus("Could not load makes. Check server is running.", "error");
  }
}

async function loadModels(make) {
  try {
    if (!make) {
      modelEl.innerHTML = `<option value="">Select Model</option>`;
      return;
    }

    setStatus("Loading models...");
    modelEl.innerHTML = `<option value="">Loading...</option>`;

    const res = await fetch(`/api/models/${encodeURIComponent(make)}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`Models failed: ${res.status}`);
    const models = await res.json();

    modelEl.innerHTML = `<option value="">Select Model</option>`;
    models.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      modelEl.appendChild(opt);
    });

    setStatus("");
  } catch (err) {
    console.error(err);
    setStatus("Could not load models for that make.", "error");
    modelEl.innerHTML = `<option value="">Select Model</option>`;
  }
}

if (makeEl) {
  makeEl.addEventListener("change", (e) => {
    loadModels(e.target.value);
  });
}

// ===============================
// SERVICES
// ===============================
// Simple fallback services (so app always works even if you later change catalogs)
const FALLBACK_SERVICES = [
  "Oil Change",
  "Brake Pads (Front)",
  "Brake Pads (Rear)",
  "Spark Plugs",
  "Battery Replacement",
  "Alternator Replacement",
  "Starter Replacement",
  "Diagnostic",
];

function loadServicesFallback() {
  if (categoryEl) {
    categoryEl.innerHTML = `<option value="">General</option>`;
  }
  if (serviceEl) {
    serviceEl.innerHTML = `<option value="">Select Service</option>`;
    FALLBACK_SERVICES.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      serviceEl.appendChild(opt);
    });
  }
}

// ===============================
// SIGNATURE (simple draw capture)
// ===============================
let sigDrawing = false;
let sigHasInk = false;
let sigCtx = null;

function resizeSignatureCanvas() {
  if (!sigCanvas) return;
  const rect = sigCanvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;

  sigCanvas.width = Math.floor(rect.width * dpr);
  sigCanvas.height = Math.floor(rect.height * dpr);

  sigCtx = sigCanvas.getContext("2d");
  sigCtx.scale(dpr, dpr);
  sigCtx.lineWidth = 2;
  sigCtx.lineCap = "round";
}

function getPoint(evt) {
  const rect = sigCanvas.getBoundingClientRect();
  const touch = evt.touches && evt.touches[0];
  const clientX = touch ? touch.clientX : evt.clientX;
  const clientY = touch ? touch.clientY : evt.clientY;
  return { x: clientX - rect.left, y: clientY - rect.top };
}

function sigStart(evt) {
  if (!sigCtx) return;
  sigDrawing = true;
  const p = getPoint(evt);
  sigCtx.beginPath();
  sigCtx.moveTo(p.x, p.y);
  evt.preventDefault?.();
}

function sigMove(evt) {
  if (!sigDrawing || !sigCtx) return;
  const p = getPoint(evt);
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
  sigCtx.clearRect(0, 0, sigCanvas.width, sigCanvas.height);
  sigHasInk = false;
}

function getSignatureDataUrl() {
  if (!sigCanvas || !sigHasInk) return null;
  // Use PNG data URL
  return sigCanvas.toDataURL("image/png");
}

// Setup signature events
function initSignature() {
  if (!sigCanvas) return;

  // Ensure canvas has size based on CSS
  resizeSignatureCanvas();
  window.addEventListener("resize", resizeSignatureCanvas);

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
  if (makeEl) makeEl.value = "";
  if (modelEl) modelEl.innerHTML = `<option value="">Select Model</option>`;
  if (yearEl) yearEl.value = String(new Date().getFullYear());

  if (categoryEl) categoryEl.value = "";
  if (serviceEl) serviceEl.value = "";

  if (laborHoursEl) laborHoursEl.value = "0";
  if (partsPriceEl) partsPriceEl.value = "0";
  if (laborRateEl) laborRateEl.value = "90";
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
function buildPayload() {
  const year = parseInt(yearEl?.value || "", 10);
  const make = makeEl?.value || "";
  const model = modelEl?.value || "";
  const category = categoryEl?.value || "";
  const service = serviceEl?.value || "";

  const laborHours = parseFloat(laborHoursEl?.value || "0") || 0;
  const partsPrice = parseFloat(partsPriceEl?.value || "0") || 0;
  const laborRate = parseFloat(laborRateEl?.value || "0") || 0;

  const notes = notesEl?.value || "";
  const customerName = customerNameEl?.value || "";
  const customerPhone = customerPhoneEl?.value || "";

  const signatureDataUrl = getSignatureDataUrl();

  return {
    year,
    make,
    model,
    category,
    service,
    laborHours,
    partsPrice,
    laborRate,
    notes,
    customerName,
    customerPhone,
    signatureDataUrl,
    // zip is optional; add later if you put it in UI
  };
}

function validatePayload(p) {
  if (!p.year || Number.isNaN(p.year)) return "Select a year.";
  if (!p.make) return "Select a make.";
  if (!p.model) return "Select a model.";
  if (!p.service) return "Select a service.";
  if (p.laborHours < 0) return "Labor hours must be 0 or greater.";
  if (p.partsPrice < 0) return "Parts price must be 0 or greater.";
  if (p.laborRate < 0) return "Labor rate must be 0 or greater.";
  return null;
}

// ===============================
// CREATE ESTIMATE
// ===============================
async function createEstimate() {
  const payload = buildPayload();
  const err = validatePayload(payload);
  if (err) {
    setStatus(err, "error");
    return;
  }

  try {
    setStatus("Creating estimate...");
    const res = await fetch("/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`Estimate failed: ${res.status} ${text}`);
    }

    const result = await res.json();
    setStatus(`Estimated Total: $${result.estimate}`, "ok");
  } catch (e) {
    console.error(e);
    setStatus("Estimate failed. Check server and try again.", "error");
  }
}

if (estimateBtn) estimateBtn.addEventListener("click", createEstimate);

// ===============================
// DOWNLOAD PDF
// ===============================
async function downloadPdf() {
  const payload = buildPayload();
  const err = validatePayload(payload);
  if (err) {
    setStatus(err, "error");
    return;
  }

  try {
    setStatus("Generating PDF...");
    const res = await fetch("/estimate/pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`PDF failed: ${res.status} ${text}`);
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
  }
}

if (pdfBtn) pdfBtn.addEventListener("click", downloadPdf);

// ===============================
// INIT
// ===============================
document.addEventListener("DOMContentLoaded", () => {
  loadYears();
  loadMakes();
  loadServicesFallback();
  initSignature();
  setStatus("");
});
