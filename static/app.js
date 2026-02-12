const $ = (id) => document.getElementById(id);

function money(n) {
  const v = Number(n || 0);
  return v.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function setStatus(msg = "", isError = false) {
  const box = $("statusBox");
  if (!box) return;
  box.textContent = msg;
  box.classList.toggle("error", !!isError);
}

async function apiGet(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText} for ${url}`);
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
    setStatus(`UI init failed: ${e.message}`, true);
  });
});

async function init() {
  // Ensure all required elements exist (prevents null addEventListener)
  const requiredIds = [
    "year","make","model","category","service",
    "laborHours","partsPrice","laborRate","notes",
    "estimateBtn","statusBox"
  ];
  for (const id of requiredIds) {
    if (!$(id)) throw new Error(`Missing element #${id} in index.html`);
  }

  // Load years
  const years = await apiGet("/vehicle/years");
  setOptions($("year"), years.map(y => ({ value: String(y), label: String(y) })), "Select year");

  // Load catalog
  catalog = await apiGet("/catalog");
  $("laborRate").value = String(catalog.labor_rate ?? 90);

  categories = (catalog.categories || []).map(c => ({
    key: c.key,
    name: c.name,
    services: c.services || []
  }));
  servicesByCategory = new Map(categories.map(c => [c.key, c.services]));

  setOptions(
    $("category"),
    categories.map(c => ({ value: c.key, label: c.name })),
    "Select category"
  );

  // Init dropdowns disabled until selections happen
  $("make").disabled = true;
  $("model").disabled = true;
  $("service").disabled = true;

  setOptions($("make"), [], "Select make");
  setOptions($("model"), [], "Select model");
  setOptions($("service"), [], "Select service");

  // Events
  $("year").addEventListener("change", onYearChange);
  $("make").addEventListener("change", onMakeChange);
  $("category").addEventListener("change", onCategoryChange);
  $("estimateBtn").addEventListener("click", onEstimate);

  setStatus(""); // clear
}

async function onYearChange() {
  const year = $("year").value;

  // Reset dependent fields
  setOptions($("make"), [], year ? "Loading makes..." : "Select make");
  setOptions($("model"), [], "Select model");
  $("make").disabled = !year;
  $("model").disabled = true;

  if (!year) return;

  try {
    setStatus("");
    const res = await apiGet(`/vehicle/makes?year=${encodeURIComponent(year)}`);
    const makes = (res.makes || []).map(m => ({ value: m, label: m }));

    setOptions($("make"), makes, "Select make");
    $("make").disabled = false;
  } catch (e) {
    console.error(e);
    setOptions($("make"), [], "Select make");
    $("make").disabled = false;
    setStatus("Could not load makes. Try a different year.", true);
  }
}

async function onMakeChange() {
  const year = $("year").value;
  const make = $("make").value;

  setOptions($("model"), [], make ? "Loading models..." : "Select model");
  $("model").disabled = !(year && make);

  if (!year || !make) return;

  try {
    setStatus("");
    const res = await apiGet(`/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`);
    const models = (res.models || []).map(m => ({ value: m, label: m }));

    setOptions($("model"), models, "Select model");
    $("model").disabled = false;
  } catch (e) {
    console.error(e);
    setOptions($("model"), [], "Select model");
    $("model").disabled = false;
    setStatus("Could not load models. Try another make/year.", true);
  }
}

function onCategoryChange() {
  const catKey = $("category").value;
  const list = servicesByCategory.get(catKey) || [];

  const items = list.map(s => ({ value: s.code, label: s.name }));
  setOptions($("service"), items, "Select service");
  $("service").disabled = !catKey;

  setStatus("");
}

function onEstimate() {
  const catKey = $("category").value;
  const svcCode = $("service").value;

  if (!catKey) return setStatus("Pick a category.", true);
  if (!svcCode) return setStatus("Pick a service.", true);

  const laborHours = Number($("laborHours").value || 0);
  const parts = Number($("partsPrice").value || 0);
  const rate = Number($("laborRate").value || (catalog?.labor_rate ?? 90));
  const notes = ($("notes").value || "").trim();

  const list = servicesByCategory.get(catKey) || [];
  const svc = list.find(s => s.code === svcCode);
  if (!svc) return setStatus("Service not found in catalog.", true);

  if (laborHours <= 0) {
    // If user didn't enter hours, default to midpoint of service range
    const minH = Number(svc.labor_hours_min ?? 0);
    const maxH = Number(svc.labor_hours_max ?? minH);
    const midH = (minH + maxH) / 2;
    $("laborHours").value = midH.toFixed(1);
  }

  const finalHours = Number($("laborHours").value || 0);
  const labor = finalHours * rate;
  const total = labor + parts;

  setStatus(
    `${svc.name} — Labor ${money(labor)} (${finalHours.toFixed(1)} hrs @ ${money(rate)}/hr) | Parts ${money(parts)} | Total ${money(total)}`
    + (notes ? ` | Notes: ${notes}` : ""),
    false
  );
}
