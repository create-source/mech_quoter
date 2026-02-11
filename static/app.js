const $ = (id) => document.getElementById(id);

const els = {
  zip: $("zip"),
  zipList: $("zipList"),
  partsPrice: $("partsPrice"),
  pricingMode: $("pricingMode"),
  year: $("year"),
  make: $("make"),
  model: $("model"),
  category: $("category"),
  service: $("service"),
  estimateBtn: $("estimateBtn"),
  result: $("result"),
};

let catalog = null; // { categories: [...] }

function opt(value, text) {
  const o = document.createElement("option");
  o.value = value;
  o.textContent = text ?? value;
  return o;
}

function setLoading(selectEl, label = "Loading...") {
  selectEl.innerHTML = "";
  selectEl.appendChild(opt("", label));
  selectEl.disabled = true;
}

function setEmpty(selectEl, label = "Select...") {
  selectEl.innerHTML = "";
  selectEl.appendChild(opt("", label));
  selectEl.disabled = false;
}

async function api(url) {
  const r = await fetch(url, { headers: { "Accept": "application/json" } });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`${r.status} ${r.statusText}: ${t}`);
  }
  return r.json();
}

function populateSelect(selectEl, values, placeholder) {
  selectEl.innerHTML = "";
  selectEl.appendChild(opt("", placeholder));
  for (const v of values) selectEl.appendChild(opt(v, v));
  selectEl.disabled = false;
}

function populateCategorySelect() {
  setEmpty(els.category, "Select category");
  for (const c of catalog.categories) {
    els.category.appendChild(opt(c.key, c.name));
  }
}

function populateServiceSelectForCategory(categoryKey) {
  els.service.innerHTML = "";
  els.service.appendChild(opt("", "Select a service"));

  if (!categoryKey) {
    els.service.disabled = false;
    return;
  }

  const cat = catalog.categories.find((c) => c.key === categoryKey);
  const services = (cat && Array.isArray(cat.services)) ? cat.services : [];

  for (const s of services) {
    // IMPORTANT: s is an object; we must display s.name and value s.code.
    els.service.appendChild(opt(s.code, s.name));
  }

  els.service.disabled = false;
}

// Popular ZIP suggestions (you can change these anytime)
function loadZipSuggestions() {
  const zips = [
    "92646","92647","92648","92649",
    "92701","92703","92704","92705","92706","92707","92708",
    "92801","92802","92804","92805","92806","92807","92808",
    "92602","92603","92604","92606","92612","92614","92618",
    "92620","92625","92626","92627","92629","92630","92637",
    "92651","92653","92655","92656","92657","92660","92661",
    "92662","92663","92672","92673","92675","92677","92679",
    "92683","92688","92691","92692","92694"
  ];
  els.zipList.innerHTML = "";
  for (const z of zips) {
    const o = document.createElement("option");
    o.value = z;
    els.zipList.appendChild(o);
  }
}

async function init() {
  loadZipSuggestions();

  // Default states
  setLoading(els.year);
  setLoading(els.make);
  setLoading(els.model);
  setLoading(els.category);
  setLoading(els.service);

  // Load catalog once (client-side filtering)
  catalog = await api("/catalog");
  if (!catalog || !Array.isArray(catalog.categories)) {
    throw new Error("Catalog response invalid (expected { categories: [...] })");
  }

  // Load years
  const years = await api("/vehicle/years");
  populateSelect(els.year, years, "Select year");

  // Categories come from catalog
  populateCategorySelect();
  populateServiceSelectForCategory("");

  // Wire events
  els.year.addEventListener("change", async () => {
    const year = els.year.value;
    setLoading(els.make);
    setLoading(els.model, "Select a model");

    if (!year) {
      setEmpty(els.make, "Select make");
      setEmpty(els.model, "Select a model");
      return;
    }

    const makes = await api(`/vehicle/makes?year=${encodeURIComponent(year)}`);
    populateSelect(els.make, makes, "Select make");
    setEmpty(els.model, "Select a model");
  });

  els.make.addEventListener("change", async () => {
    const year = els.year.value;
    const make = els.make.value;

    setLoading(els.model);

    if (!year || !make) {
      setEmpty(els.model, "Select a model");
      return;
    }

    const models = await api(`/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`);
    populateSelect(els.model, models, "Select a model");
  });

  els.category.addEventListener("change", () => {
    populateServiceSelectForCategory(els.category.value);
  });

  els.estimateBtn.addEventListener("click", async () => {
    els.result.textContent = "";

    const zip = (els.zip.value || "").trim();
    const year = els.year.value;
    const make = els.make.value;
    const model = els.model.value;
    const categoryKey = els.category.value;
    const serviceCode = els.service.value;
    const pricingMode = els.pricingMode.value;
    const partsPrice = parseFloat((els.partsPrice.value || "0").toString()) || 0;

    if (!zip) return (els.result.textContent = "Enter a ZIP code.");
    if (!year) return (els.result.textContent = "Select a year.");
    if (!make) return (els.result.textContent = "Select a make.");
    if (!model) return (els.result.textContent = "Select a model.");
    if (!categoryKey) return (els.result.textContent = "Select a category.");
    if (!serviceCode) return (els.result.textContent = "Select a service.");

    const url =
      `/estimate?zip_code=${encodeURIComponent(zip)}` +
      `&year=${encodeURIComponent(year)}` +
      `&make=${encodeURIComponent(make)}` +
      `&model=${encodeURIComponent(model)}` +
      `&category_key=${encodeURIComponent(categoryKey)}` +
      `&service_code=${encodeURIComponent(serviceCode)}` +
      `&pricing_mode=${encodeURIComponent(pricingMode)}` +
      `&parts_price=${encodeURIComponent(partsPrice.toFixed(2))}`;

    try {
      const out = await api(url);
      els.result.textContent =
        `Service: ${out.service.name}\n` +
        `Category: ${out.category.name}\n\n` +
        `Labor: $${out.labor_min} – $${out.labor_max}\n` +
        `Parts: $${out.parts_price}\n` +
        `TOTAL: $${out.total_min} – $${out.total_max}\n`;
    } catch (e) {
      els.result.textContent = `Error: ${e.message}`;
    }
  });

  // Initialize make/model placeholders
  setEmpty(els.make, "Select make");
  setEmpty(els.model, "Select a model");
}

init().catch((e) => {
  console.error(e);
  els.result.textContent = `Startup error: ${e.message}`;
});
