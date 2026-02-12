const $ = (id) => document.getElementById(id);

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
    opt.value = it.value;
    opt.textContent = it.label;
    selectEl.appendChild(opt);
  }
}

let catalog = null;
let categories = [];
let servicesByCategory = new Map();

window.addEventListener("DOMContentLoaded", () => {
  init().catch((e) => {
    console.error(e);
    const result = $("result");
    if (result) result.textContent = `UI init failed: ${e.message}`;
  });
});

async function init() {
  // Required elements (must exist in index.html)
  const yearSel = $("year");
  const makeSel = $("make");
  const modelSel = $("model");
  const categorySel = $("category");
  const serviceSel = $("service");
  const partsPrice = $("partsPrice");
  const btn = $("estimateBtn");
  const result = $("result");

  if (!yearSel || !makeSel || !modelSel || !categorySel || !serviceSel || !partsPrice || !btn || !result) {
    throw new Error("index.html is missing one or more required elements.");
  }

  // Years
  const years = await apiGet("/vehicle/years");
  setOptions(yearSel, years.map((y) => ({ value: String(y), label: String(y) })), "Select year");

  // Catalog
  catalog = await apiGet("/catalog");
  categories = (catalog.categories || []).map((c) => ({ key: c.key, name: c.name, services: c.services || [] }));
  servicesByCategory = new Map(categories.map((c) => [c.key, c.services]));

  setOptions(categorySel, categories.map((c) => ({ value: c.key, label: c.name })), "Select category");

  // Disable until needed
  makeSel.disabled = true;
  modelSel.disabled = true;
  serviceSel.disabled = true;

  // Events
  yearSel.addEventListener("change", onYearChange);
  makeSel.addEventListener("change", onMakeChange);
  categorySel.addEventListener("change", onCategoryChange);
  btn.addEventListener("click", onEstimate);

  // Initial blank options
  setOptions(makeSel, [], "Select make");
  setOptions(modelSel, [], "Select model");
  setOptions(serviceSel, [], "Select service");
}

async function onYearChange() {
  const year = $("year").value;
  const makeSel = $("make");
  const modelSel = $("model");

  // reset
  setOptions(makeSel, [], year ? "Loading makes..." : "Select make");
  setOptions(modelSel, [], "Select model");
  makeSel.disabled = !year;
  modelSel.disabled = true;

  if (!year) return;

  const res = await apiGet(`/vehicle/makes?year=${encodeURIComponent(year)}`);
  const makes = (res.makes || []).map((m) => ({ value: m, label: m }));
  setOptions(makeSel, makes, "Select make");
  makeSel.disabled = false;
}

async function onMakeChange() {
  const year = $("year").value;
  const make = $("make").value;
  const modelSel = $("model");

  setOptions(modelSel, [], make ? "Loading models..." : "Select model");
  modelSel.disabled = !(year && make);

  if (!year || !make) return;

  const res = await apiGet(`/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`);
  const models = (res.models || []).map((m) => ({ value: m, label: m }));
  setOptions(modelSel, models, "Select model");
  modelSel.disabled = false;
}

function onCategoryChange() {
  const catKey = $("category").value;
  const serviceSel = $("service");

  const list = servicesByCategory.get(catKey) || [];
  const items = list.map((s) => ({ value: s.code, label: s.name }));

  setOptions(serviceSel, items, "Select service");
  serviceSel.disabled = !catKey;
}

function onEstimate() {
  const catKey = $("category").value;
  const svcCode = $("service").value;

  if (!catKey) {
    $("result").textContent = "Pick a category.";
    return;
  }
  if (!svcCode) {
    $("result").textContent = "Pick a service.";
    return;
  }

  const parts = Number($("partsPrice").value || 0);
  const rate = Number((catalog && catalog.labor_rate) || 90);

  const list = servicesByCategory.get(catKey) || [];
  const svc = list.find((s) => s.code === svcCode);

  if (!svc) {
    $("result").textContent = "Service not found in catalog.";
    return;
  }

  const minH = Number(svc.labor_hours_min ?? 0);
  const maxH = Number(svc.labor_hours_max ?? minH);
  const midH = (minH + maxH) / 2;

  const labor = midH * rate;
  const total = labor + parts;

  $("result").innerHTML =
    `<div><b>${svc.name}</b></div>` +
    `<div style="margin-top:8px;"><b>Labor:</b> ${money(labor)} (${midH.toFixed(1)} hrs @ ${money(rate)}/hr)</div>` +
    `<div><b>Parts:</b> ${money(parts)}</div>` +
    `<div style="margin-top:8px;"><b>Total:</b> ${money(total)}</div>`;
}
