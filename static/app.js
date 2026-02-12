function $(id) {
  return document.getElementById(id);
}

function money(n) {
  const v = Number(n || 0);
  return v.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

async function apiGet(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`GET ${url} failed: ${r.status}`);
  return r.json();
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

window.addEventListener("DOMContentLoaded", () => {
  init().catch((e) => {
    console.error(e);
    const box = $("statusBox");
    if (box) box.textContent = `UI init failed: ${e.message}`;
  });
});

let catalog = null;
let servicesByCategory = new Map();

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
  const statusBox = $("statusBox");

  // Guard (helps you instantly if IDs ever change)
  const required = [yearSel, makeSel, modelSel, categorySel, serviceSel, laborHoursEl, partsPriceEl, laborRateEl, notesEl, estimateBtn, statusBox];
  if (required.some((x) => !x)) {
    throw new Error("One or more required elements are missing in index.html (check IDs).");
  }

  // Load years
  const years = await apiGet("/vehicle/years"); // expects: [2027, 2026, ...]
  setOptions(yearSel, years.map((y) => ({ value: String(y), label: String(y) })), "Select year");

  // Load catalog
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

  // Vehicle events
  yearSel.addEventListener("change", onYearChange);
  makeSel.addEventListener("change", onMakeChange);

  // Service events
  categorySel.addEventListener("change", onCategoryChange);
  serviceSel.addEventListener("change", onServiceChange);

  // Button
  estimateBtn.addEventListener("click", () => {
    const hours = Number(laborHoursEl.value || 0);
    const rate = Number(laborRateEl.value || 90);
    const parts = Number(partsPriceEl.value || 0);

    const labor = hours * rate;
    const total = labor + parts;

    statusBox.innerHTML = `
      <div><b>Labor:</b> ${money(labor)} (${hours.toFixed(1)} hrs @ ${money(rate)}/hr)</div>
      <div><b>Parts:</b> ${money(parts)}</div>
      <div style="margin-top:6px;"><b>Total:</b> ${money(total)}</div>
    `;
  });

  // Prime initial state
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
    const res = await apiGet(`/vehicle/makes?year=${encodeURIComponent(year)}`); // expects: { makes: [...] }
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
    const res = await apiGet(`/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`); // expects: { models: [...] }
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

// Add this INSIDE your existing DOMContentLoaded handler, before init():
window.addEventListener("DOMContentLoaded", () => {
  // PWA service worker
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js").catch(console.error);
  }

  init().catch((e) => {
    console.error(e);
    const box = $("statusBox");
    if (box) box.textContent = `UI init failed: ${e.message}`;
  });
});
