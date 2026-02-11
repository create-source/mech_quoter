// Repair Estimator client logic
// - Cascading Year -> Make -> Model fetches
// - Categories + Services loaded once, filtered client-side

const $ = (id) => document.getElementById(id);

const zipEl = $("zip");
const yearEl = $("year");
const makeEl = $("make");
const modelEl = $("model");
const categoryEl = $("category");
const serviceEl = $("service");
const partsPriceEl = $("partsPrice");
const formEl = $("estimateForm");
const resultEl = $("result");
const detailsEl = $("details");

// --- Helpers ---
function setStatus(message, isError = false) {
  if (!resultEl) return;
  resultEl.textContent = message || "";
  resultEl.classList.toggle("error", !!isError);
}

function clearSelect(selectEl, placeholder) {
  selectEl.innerHTML = "";
  const opt = document.createElement("option");
  opt.value = "";
  opt.textContent = placeholder;
  selectEl.appendChild(opt);
  selectEl.value = "";
}

function fillSelect(selectEl, items, { valueKey, labelKey } = {}) {
  // items can be strings OR objects
  for (const item of items) {
    const opt = document.createElement("option");
    if (typeof item === "string" || typeof item === "number") {
      opt.value = String(item);
      opt.textContent = String(item);
    } else {
      const v = valueKey ? item[valueKey] : item.value ?? item.key ?? item.code ?? "";
      const l = labelKey ? item[labelKey] : item.label ?? item.name ?? v;
      opt.value = String(v);
      opt.textContent = String(l);
    }
    selectEl.appendChild(opt);
  }
}

async function apiGet(url) {
  const r = await fetch(url, { headers: { "Accept": "application/json" } });
  if (!r.ok) {
    const txt = await r.text().catch(() => "");
    throw new Error(`${r.status} ${r.statusText} - ${txt}`);
  }
  return r.json();
}

// --- Catalog (Category/Service) ---
let catalog = null; // array of categories from /categories

function populateCategories() {
  clearSelect(categoryEl, "Select category");
  if (!catalog) return;
  fillSelect(categoryEl, catalog, { valueKey: "key", labelKey: "name" });
}

function populateServicesForCategory(categoryKey) {
  clearSelect(serviceEl, "Select a service");
  if (!catalog || !categoryKey) return;
  const cat = catalog.find((c) => c.key === categoryKey);
  if (!cat || !Array.isArray(cat.services)) return;
  fillSelect(serviceEl, cat.services, { valueKey: "code", labelKey: "name" });
}

// --- Vehicle cascade ---
async function loadYears() {
  clearSelect(yearEl, "Select year");
  clearSelect(makeEl, "Select make");
  clearSelect(modelEl, "Select a model");

  const years = await apiGet("/vehicle/years"); // array (numbers or strings)
  fillSelect(yearEl, years);
}

async function loadMakes(year) {
  clearSelect(makeEl, "Select make");
  clearSelect(modelEl, "Select a model");
  if (!year) return;
  const makes = await apiGet(`/vehicle/makes?year=${encodeURIComponent(year)}`);
  fillSelect(makeEl, makes);
}

async function loadModels(year, make) {
  clearSelect(modelEl, "Select a model");
  if (!year || !make) return;
  const models = await apiGet(
    `/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`
  );
  fillSelect(modelEl, models);
}

// --- Init ---
async function init() {
  setStatus("");

  // baseline placeholders
  clearSelect(yearEl, "Select year");
  clearSelect(makeEl, "Select make");
  clearSelect(modelEl, "Select a model");
  clearSelect(categoryEl, "Select category");
  clearSelect(serviceEl, "Select a service");

  try {
    // Load catalog once (client-side filtering after)
    catalog = await apiGet("/categories"); // expected: [{key,name,services:[{code,name,...}]}]
    populateCategories();

    // Load years
    await loadYears();
  } catch (e) {
    console.error(e);
    setStatus(`Load error: ${e.message}`, true);
  }
}

// --- Event wiring ---
yearEl.addEventListener("change", async () => {
  setStatus("");
  const year = yearEl.value;
  try {
    await loadMakes(year);
  } catch (e) {
    console.error(e);
    setStatus(`Could not load makes: ${e.message}`, true);
  }
});

makeEl.addEventListener("change", async () => {
  setStatus("");
  const year = yearEl.value;
  const make = makeEl.value;
  try {
    await loadModels(year, make);
  } catch (e) {
    console.error(e);
    setStatus(`Could not load models: ${e.message}`, true);
  }
});

categoryEl.addEventListener("change", () => {
  setStatus("");
  populateServicesForCategory(categoryEl.value);
});

formEl.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  setStatus("");

  const payload = {
    zip: (zipEl.value || "").trim(),
    year: yearEl.value ? Number(yearEl.value) : null,
    make: makeEl.value || null,
    model: modelEl.value || null,
    category: categoryEl.value || null,
    service: serviceEl.value || null,
    parts_price: partsPriceEl && partsPriceEl.value ? Number(partsPriceEl.value) : 0,
  };

  // basic guardrails
  if (!payload.zip || payload.zip.length < 5) return setStatus("Enter a valid ZIP code.", true);
  if (!payload.year) return setStatus("Select a year.", true);
  if (!payload.make) return setStatus("Select a make.", true);
  if (!payload.model) return setStatus("Select a model.", true);
  if (!payload.category) return setStatus("Select a category.", true);
  if (!payload.service) return setStatus("Select a service.", true);

  try {
    const resp = await fetch("/estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!resp.ok) {
      const txt = await resp.text().catch(() => "");
      throw new Error(`${resp.status} ${resp.statusText} - ${txt}`);
    }

    const data = await resp.json();
    // expected fields: total_min, total_max, breakdown...
    const min = data?.total_min ?? data?.totalMin;
    const max = data?.total_max ?? data?.totalMax;

    setStatus(
      (min != null && max != null)
        ? `Estimated total: $${Number(min).toFixed(0)} – $${Number(max).toFixed(0)}`
        : "Estimate created.",
      false
    );

    if (detailsEl) {
      detailsEl.textContent = JSON.stringify(data, null, 2);
    }
  } catch (e) {
    console.error(e);
    setStatus(`Estimate failed: ${e.message}`, true);
  }
});

document.addEventListener("DOMContentLoaded", init);
