/* global Choices */

const $ = (id) => document.getElementById(id);

const els = {
  vehicleType: $("vehicleType"),
  year: $("year"),
  make: $("make"),
  model: $("model"),
  category: $("category"),
  service: $("service"),
  result: $("result"),
};

let choices = {};

function setDisabled(el, disabled) {
  el.disabled = !!disabled;
}

function clearSelect(el, placeholder) {
  el.innerHTML = "";
  const opt = document.createElement("option");
  opt.value = "";
  opt.textContent = placeholder;
  opt.selected = true;
  el.appendChild(opt);
}

function setOptions(el, items, placeholder) {
  clearSelect(el, placeholder);
  for (const v of items) {
    const opt = document.createElement("option");
    opt.value = v;
    opt.textContent = v;
    el.appendChild(opt);
  }
}

function rebuildChoices(id) {
  if (choices[id]) choices[id].destroy();
  choices[id] = new Choices("#" + id, {
    searchEnabled: true,
    shouldSort: true,
    itemSelectText: "",
    allowHTML: false,
  });
}

async function api(path) {
  const res = await fetch(path, { headers: { "Accept": "application/json" } });
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j && j.detail) msg = j.detail;
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

function qs(params) {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && String(v).trim() !== "") sp.set(k, v);
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

async function loadYears() {
  const vehicle_type = els.vehicleType.value;
  const years = await api("/vehicle/years" + qs({ vehicle_type }));
  setOptions(els.year, years, "Select year");
  rebuildChoices("year");
}

async function loadMakes() {
  const vehicle_type = els.vehicleType.value;
  const year = els.year.value;
  const makes = await api("/vehicle/makes" + qs({ vehicle_type, year }));
  setOptions(els.make, makes, "Select make");
  setDisabled(els.make, false);
  rebuildChoices("make");
}

async function loadModels() {
  const vehicle_type = els.vehicleType.value;
  const year = els.year.value;
  const make = els.make.value;
  const models = await api("/vehicle/models" + qs({ vehicle_type, year, make }));
  setOptions(els.model, models, "Select model");
  setDisabled(els.model, false);
  rebuildChoices("model");
}

async function loadCategories() {
  const vehicle_type = els.vehicleType.value;
  const year = els.year.value;
  const make = els.make.value;
  const model = els.model.value;

  const categories = await api("/categories" + qs({ vehicle_type, year, make, model }));
  setOptions(els.category, categories, "Select category");
  setDisabled(els.category, false);
  rebuildChoices("category");
}

async function loadServices() {
  const vehicle_type = els.vehicleType.value;
  const year = els.year.value;
  const make = els.make.value;
  const model = els.model.value;
  const category = els.category.value;

  const services = await api("/services" + qs({ vehicle_type, year, make, model, category }));
  setOptions(els.service, services, "Select service");
  setDisabled(els.service, false);
  rebuildChoices("service");
}

function resetDownstream(from) {
  if (from === "vehicleType") {
    clearSelect(els.year, "Select year");
    setDisabled(els.year, false);
    clearSelect(els.make, "Select make"); setDisabled(els.make, true);
    clearSelect(els.model, "Select model"); setDisabled(els.model, true);
    clearSelect(els.category, "Select category"); setDisabled(els.category, true);
    clearSelect(els.service, "Select service"); setDisabled(els.service, true);
  }
  if (from === "year") {
    clearSelect(els.make, "Select make"); setDisabled(els.make, true);
    clearSelect(els.model, "Select model"); setDisabled(els.model, true);
    clearSelect(els.category, "Select category"); setDisabled(els.category, true);
    clearSelect(els.service, "Select service"); setDisabled(els.service, true);
  }
  if (from === "make") {
    clearSelect(els.model, "Select model"); setDisabled(els.model, true);
    clearSelect(els.category, "Select category"); setDisabled(els.category, true);
    clearSelect(els.service, "Select service"); setDisabled(els.service, true);
  }
  if (from === "model") {
    clearSelect(els.category, "Select category"); setDisabled(els.category, true);
    clearSelect(els.service, "Select service"); setDisabled(els.service, true);
  }
  if (from === "category") {
    clearSelect(els.service, "Select service"); setDisabled(els.service, true);
  }
}

async function init() {
  // Initialize Choices on selects that already exist
  ["laborPricing", "vehicleType", "year", "make", "model", "category", "service"].forEach((id) => {
    if ($(id)) rebuildChoices(id);
  });

  // Start state
  setDisabled(els.make, true);
  setDisabled(els.model, true);
  setDisabled(els.category, true);
  setDisabled(els.service, true);

  try {
    await loadYears();
  } catch (e) {
    els.result.textContent = `Error loading years: ${e.message}`;
  }

  els.vehicleType.addEventListener("change", async () => {
    resetDownstream("vehicleType");
    try { await loadYears(); } catch (e) { els.result.textContent = e.message; }
  });

  els.year.addEventListener("change", async () => {
    resetDownstream("year");
    if (!els.year.value) return;
    try { await loadMakes(); } catch (e) { els.result.textContent = e.message; }
  });

  els.make.addEventListener("change", async () => {
    resetDownstream("make");
    if (!els.make.value) return;
    try { await loadModels(); } catch (e) { els.result.textContent = e.message; }
  });

  els.model.addEventListener("change", async () => {
    resetDownstream("model");
    if (!els.model.value) return;
    try { await loadCategories(); } catch (e) { els.result.textContent = e.message; }
  });

  els.category.addEventListener("change", async () => {
    resetDownstream("category");
    if (!els.category.value) return;
    try { await loadServices(); } catch (e) { els.result.textContent = e.message; }
  });
}

document.addEventListener("DOMContentLoaded", init);
