function $(id) {
  return document.getElementById(id);
}

function money(n) {
  const v = Number(n || 0);
  return v.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

async function apiGet(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`GET ${url} failed: ${r.status}`);
  return r.json();
}

async function apiPostJson(url, payload) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const txt = await r.text().catch(() => "");
    throw new Error(`POST ${url} failed: ${r.status} ${txt}`);
  }
  return r;
}

function setOptions(selectEl, items, placeholder) {
  selectEl.innerHTML = "";
  const ph = document.createElement("option");
  ph.value = "";
  ph.textContent = placeholder;
  selectEl.appendChild(ph);

  for (const it of items) {
    const opt = document.createElement("option");
    if (typeof it === "string") {
      opt.value = it;
      opt.textContent = it;
    } else {
      opt.value = it.value;
      opt.textContent = it.label;
    }
    selectEl.appendChild(opt);
  }
}

function buildEstimatePayload() {
  const year = $("year").value || "";
  const make = $("make").value || "";
  const model = $("model").value || "";

  const categoryKey = $("category").value || "";
  const categoryLabel = $("category").selectedOptions?.[0]?.textContent || "";

  const serviceCode = $("service").value || "";
  const serviceLabel = $("service").selectedOptions?.[0]?.textContent || "";

  const hours = Number($("laborHours").value || 0);
  const rate = Number($("laborRate").value || 90);
  const parts = Number($("partsPrice").value || 0);
  const notes = ($("notes").value || "").trim();

  const labor = hours * rate;
  const total = labor + parts;

  const customerName = ($("customerName")?.value || "").trim();
  const customerPhone = ($("customerPhone")?.value || "").trim();
  const signatureDataUrl = window.__sigPad ? window.__sigPad.getDataUrl() : "";

  return {
  vehicle: { year, make, model },
  selection: {
    category_key: categoryKey,
    category_name: categoryLabel,
    service_code: serviceCode,
    service_name: serviceLabel,
  },
  pricing: {
    labor_hours: hours,
    labor_rate: rate,
    parts: parts,
    labor: labor,
    total: total,
  },
  notes,

  customer: {
    name: customerName,
    phone: customerPhone
  },

  signature_data_url: signatureDataUrl
};

window.addEventListener("DOMContentLoaded", () => {
  init().catch((e) => {
    console.error(e);
    const box = $("statusBox");
    if (box) box.textContent = `UI init failed: ${e.message}`;
  });
});

let catalog = null;
let servicesByCategory = new Map();

function setupSignaturePad(canvas, clearBtn) {
  const ctx = canvas.getContext("2d");
  let drawing = false;
  let lastX = 0, lastY = 0;

  const resizeCanvasToDisplaySize = () => {
    // Make canvas crisp on high-DPI screens (phones)
    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.round(rect.width * ratio);
    canvas.height = Math.round(rect.height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);

    // Nice pen settings
    ctx.lineWidth = 2.5;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
  };

  const getPos = (e) => {
    const rect = canvas.getBoundingClientRect();
    const isTouch = e.touches && e.touches.length;
    const clientX = isTouch ? e.touches[0].clientX : e.clientX;
    const clientY = isTouch ? e.touches[0].clientY : e.clientY;
    return { x: clientX - rect.left, y: clientY - rect.top };
  };

  const start = (e) => {
    e.preventDefault();
    drawing = true;
    const p = getPos(e);
    lastX = p.x; lastY = p.y;
  };

  const move = (e) => {
    if (!drawing) return;
    e.preventDefault();
    const p = getPos(e);
    ctx.beginPath();
    ctx.moveTo(lastX, lastY);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    lastX = p.x; lastY = p.y;
  };

  const end = (e) => {
    if (!drawing) return;
    e.preventDefault();
    drawing = false;
  };

  const clear = () => {
    const rect = canvas.getBoundingClientRect();
    ctx.clearRect(0, 0, rect.width, rect.height);
  };

  // Events: mouse + touch
  canvas.addEventListener("mousedown", start);
  canvas.addEventListener("mousemove", move);
  window.addEventListener("mouseup", end);

  canvas.addEventListener("touchstart", start, { passive: false });
  canvas.addEventListener("touchmove", move, { passive: false });
  window.addEventListener("touchend", end, { passive: false });

  // Resize on load + when screen changes
  resizeCanvasToDisplaySize();
  window.addEventListener("resize", () => resizeCanvasToDisplaySize());

  if (clearBtn) clearBtn.addEventListener("click", clear);

  return {
    clear,
    getDataUrl: () => {
      // If blank, return empty string (so PDF doesn’t show garbage)
      // Quick blank check: compare to an empty canvas
      const tmp = document.createElement("canvas");
      tmp.width = canvas.width;
      tmp.height = canvas.height;
      if (canvas.toDataURL() === tmp.toDataURL()) return "";
      return canvas.toDataURL("image/png");
    }
  };
}

async function init() {
  const yearSel = $("year");
  const makeSel = $("make");
  const modelSel = $("model");
  const categorySel = $("category");
  const serviceSel = $("service");
  const laborHoursEl = $("laborHours");
  const partsPriceEl = $("partsPrice");
  const laborRateEl = $("laborRate");
  const notesEl = $("notes");
  const estimateBtn = $("estimateBtn");
  const pdfBtn = $("pdfBtn");
  const statusBox = $("statusBox");
  const clearBtn = $("clearBtn");
  const sigCanvas = $("sigCanvas");
  const sigClearBtn = $("sigClearBtn");
  const customerNameEl = $("customerName");
  const customerPhoneEl = $("customerPhone");


  const required = [
    yearSel, makeSel, modelSel, categorySel, serviceSel,
    laborHoursEl, partsPriceEl, laborRateEl, notesEl,
    estimateBtn, pdfBtn, statusBox, clearBtn,
    sigCanvas, sigClearBtn
  ];
  if (required.some((x) => !x)) {
    throw new Error("Missing required elements (check IDs in index.html).");
  }

  // Initialize signature pad
  window.__sigPad = setupSignaturePad(sigCanvas, sigClearBtn);
  
  // Years
  const years = await apiGet("/vehicle/years");
  setOptions(yearSel, years.map((y) => ({ value: String(y), label: String(y) })), "Select year");

  // Catalog
  catalog = await apiGet("/catalog");
  laborRateEl.value = Number(catalog.labor_rate || 90);

  const categories = (catalog.categories || []).map((c) => ({
    key: c.key,
    name: c.name,
    services: c.services || [],
  }));

  servicesByCategory = new Map();
  for (const c of categories) servicesByCategory.set(c.key, c.services);

  setOptions(categorySel, categories.map((c) => ({ value: c.key, label: c.name })), "Select category");
  setOptions(serviceSel, [], "Select service");

  // Events
  yearSel.addEventListener("change", onYearChange);
  makeSel.addEventListener("change", onMakeChange);
  categorySel.addEventListener("change", onCategoryChange);
  serviceSel.addEventListener("change", onServiceChange);

  // Create estimate (on screen)
  estimateBtn.addEventListener("click", () => {
    const payload = buildEstimatePayload();
    statusBox.innerHTML = `
      <div><b>Labor:</b> ${money(payload.pricing.labor)} (${payload.pricing.labor_hours.toFixed(1)} hrs @ ${money(payload.pricing.labor_rate)}/hr)</div>
      <div><b>Parts:</b> ${money(payload.pricing.parts)}</div>
      <div style="margin-top:6px;"><b>Total:</b> ${money(payload.pricing.total)}</div>
    `;
  });

  // Download PDF
  pdfBtn.addEventListener("click", async () => {
    try {
      const payload = buildEstimatePayload();

      // Basic guard
      if (!payload.selection.service_name) {
        statusBox.textContent = "Pick a Category + Service before downloading PDF.";
        return;
      }

      statusBox.textContent = "Generating PDF...";
      const res = await apiPostJson("/estimate/pdf", payload);
      const blob = await res.blob();

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const safeMake = (payload.vehicle.make || "Vehicle").replace(/\s+/g, "_");
      const safeModel = (payload.vehicle.model || "").replace(/\s+/g, "_");
      a.href = url;
      a.download = `estimate_${safeMake}_${safeModel || "service"}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);

      statusBox.textContent = "PDF downloaded ✅";
    } catch (e) {
      console.error(e);
      statusBox.textContent = `PDF failed: ${e.message}`;
    }
  });

  // Clear button
  clearBtn.addEventListener("click", () => {
  
      // Reset vehicle dropdowns
      yearSel.value = "";
      setOptions(makeSel, [], "Select make");
      setOptions(modelSel, [], "Select model");
    
      // Reset category + service
      categorySel.value = "";
      setOptions(serviceSel, [], "Select service");
    
      // Reset inputs
      laborHoursEl.value = "0";
      partsPriceEl.value = "0";
      notesEl.value = "";
    
      // Reset labor rate to default
      if (catalog && typeof catalog.labor_rate !== "undefined") {
        laborRateEl.value = Number(catalog.labor_rate || 90);

      // Reset customer fields
      if ($("customerName")) $("customerName").value = "";
      if ($("customerPhone")) $("customerPhone").value = "";
      
      // Clear signature canvas
      if (window.__sigPad) window.__sigPad.clear();
      
      // Clear status box
      statusBox.textContent = "";

      });
    
      // Clear output box
      statusBox.textContent = "";
    
      // Optional smooth scroll (nice on mobile)
      window.scrollTo({ top: 0, behavior: "smooth" });
  });


  // Prime state
  setOptions(makeSel, [], "Select make");
  setOptions(modelSel, [], "Select model");
  statusBox.textContent = "";
}

async function onYearChange() {
  const year = $("year").value;
  const makeSel = $("make");
  const modelSel = $("model");
  const statusBox = $("statusBox");

  setOptions(makeSel, [], "Loading makes...");
  setOptions(modelSel, [], "Select model");

  if (!year) return;

  try {
    const res = await apiGet(`/vehicle/makes?year=${encodeURIComponent(year)}`);
    const makes = res.makes || [];
    setOptions(makeSel, makes.map((m) => ({ value: m, label: m })), "Select make");
    statusBox.textContent = makes.length ? "" : "No makes returned (server or VPIC issue).";
  } catch (e) {
    console.error(e);
    setOptions(makeSel, [], "Select make");
    statusBox.textContent = `Make load failed: ${e.message}`;
  }
}

async function onMakeChange() {
  const year = $("year").value;
  const make = $("make").value;
  const modelSel = $("model");
  const statusBox = $("statusBox");

  setOptions(modelSel, [], "Loading models...");
  if (!year || !make) {
    setOptions(modelSel, [], "Select model");
    return;
  }

  try {
    const res = await apiGet(`/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`);
    const models = res.models || [];
    setOptions(modelSel, models.map((m) => ({ value: m, label: m })), "Select model");
    statusBox.textContent = models.length ? "" : "No models returned (server or VPIC issue).";
  } catch (e) {
    console.error(e);
    setOptions(modelSel, [], "Select model");
    statusBox.textContent = `Model load failed: ${e.message}`;
  }
}

function onCategoryChange() {
  const categoryKey = $("category").value;
  const list = servicesByCategory.get(categoryKey) || [];
  setOptions($("service"), list.map((s) => ({ value: s.code, label: s.name })), "Select service");
  $("laborHours").value = "0";
}

function onServiceChange() {
  const catKey = $("category").value;
  const code = $("service").value;
  const list = servicesByCategory.get(catKey) || [];
  const svc = list.find((s) => s.code === code);
  if (!svc) return;

  const min = Number(svc.labor_hours_min ?? 0);
  const max = Number(svc.labor_hours_max ?? min);
  const mid = (min + max) / 2;
  $("laborHours").value = mid.toFixed(1);
}
