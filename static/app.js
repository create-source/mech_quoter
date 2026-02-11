(async function () {
  const $ = (id) => document.getElementById(id);

  const zipEl = $("zip");
  const yearEl = $("year");
  const makeEl = $("make");
  const modelEl = $("model");
  const categoryEl = $("category");
  const serviceEl = $("service");
  const partsPriceEl = $("partsPrice");
  const btn = $("estimateBtn");
  const resultEl = $("result");

  function setLoading(msg) {
    resultEl.className = "result";
    resultEl.textContent = msg || "";
  }

  function setError(msg) {
    resultEl.className = "result error";
    resultEl.textContent = msg;
  }

  function setOk(html) {
    resultEl.className = "result ok";
    resultEl.innerHTML = html;
  }

  function clearSelect(selectEl, placeholder) {
    selectEl.innerHTML = "";
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = placeholder;
    selectEl.appendChild(opt);
  }

  function fillSelect(selectEl, items, getValue, getLabel) {
    for (const item of items) {
      const opt = document.createElement("option");
      opt.value = getValue(item);
      opt.textContent = getLabel(item);
      selectEl.appendChild(opt);
    }
  }

  async function fetchJSON(url) {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText}${text ? ` - ${text}` : ""}`);
    }
    return await res.json();
  }

  // ---- Load YEARS ----
  async function loadYears() {
    clearSelect(yearEl, "Select year");
    makeEl.disabled = true;
    modelEl.disabled = true;
    clearSelect(makeEl, "Select make");
    clearSelect(modelEl, "Select a model");

    const years = await fetchJSON("/vehicle/years");
    fillSelect(yearEl, years, (y) => String(y), (y) => String(y));
  }

  // ---- Load MAKES (popular only, API already enforces) ----
  async function loadMakes(year) {
    makeEl.disabled = true;
    modelEl.disabled = true;
    clearSelect(makeEl, "Select make");
    clearSelect(modelEl, "Select a model");

    if (!year) return;

    const makes = await fetchJSON(`/vehicle/makes?year=${encodeURIComponent(year)}`);
    fillSelect(makeEl, makes, (m) => String(m), (m) => String(m));
    makeEl.disabled = false;
  }

  // ---- Load MODELS ----
  async function loadModels(year, make) {
    modelEl.disabled = true;
    clearSelect(modelEl, "Select a model");
    if (!year || !make) return;

    const models = await fetchJSON(
      `/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`
    );
    fillSelect(modelEl, models, (m) => String(m), (m) => String(m));
    modelEl.disabled = false;
  }

  // ---- Catalog for client-side category->service filtering ----
  let catalogTree = null; // { categories: [ {key,name,services:[{code,name,...}]} ] }

  async function loadCatalog() {
    clearSelect(categoryEl, "Select category");
    serviceEl.disabled = true;
    clearSelect(serviceEl, "Select a service");

    catalogTree = await fetchJSON("/catalog");

    // categories are objects; ALWAYS use strings to avoid [object Object]
    fillSelect(
      categoryEl,
      catalogTree.categories || [],
      (c) => String(c.key),
      (c) => String(c.name || c.key)
    );
  }

  function updateServicesForCategory(categoryKey) {
    serviceEl.disabled = true;
    clearSelect(serviceEl, "Select a service");

    if (!catalogTree || !categoryKey) return;

    const cat = (catalogTree.categories || []).find((c) => String(c.key) === String(categoryKey));
    if (!cat) return;

    const services = cat.services || [];
    fillSelect(
      serviceEl,
      services,
      (s) => String(s.code),
      (s) => String(s.name || s.code)
    );

    serviceEl.disabled = false;
  }

  // ---- Estimate ----
  async function runEstimate() {
    const zip = (zipEl.value || "").trim();
    const year = yearEl.value;
    const make = makeEl.value;
    const model = modelEl.value;
    const category = categoryEl.value;
    const service = serviceEl.value;
    const partsPrice = partsPriceEl.value ? Number(partsPriceEl.value) : 0;

    if (!zip || zip.length < 5) return setError("Enter a valid ZIP code.");
    if (!year) return setError("Select a year.");
    if (!make) return setError("Select a make.");
    if (!model) return setError("Select a model.");
    if (!category) return setError("Select a category.");
    if (!service) return setError("Select a service.");

    setLoading("Calculating...");

    const qs = new URLSearchParams({
      zip_code: zip,
      year,
      make,
      model,
      category,
      service,
      parts_price: String(partsPrice || 0),
    });

    const data = await fetchJSON(`/estimate?${qs.toString()}`);

    setOk(`
      <div><strong>${data.service_name}</strong></div>
      <div>Labor: $${data.labor_min} – $${data.labor_max} (rate $${data.labor_rate}/hr)</div>
      <div>Parts: $${data.parts_price}</div>
      <hr/>
      <div><strong>Total Estimate: $${data.total_min} – $${data.total_max}</strong></div>
    `);
  }

  // ---- Wire events ----
  yearEl.addEventListener("change", async () => {
    try {
      setLoading("");
      await loadMakes(yearEl.value);
    } catch (e) {
      setError(`Failed to load makes: ${e.message}`);
    }
  });

  makeEl.addEventListener("change", async () => {
    try {
      setLoading("");
      await loadModels(yearEl.value, makeEl.value);
    } catch (e) {
      setError(`Failed to load models: ${e.message}`);
    }
  });

  categoryEl.addEventListener("change", () => {
    setLoading("");
    updateServicesForCategory(categoryEl.value);
  });

  btn.addEventListener("click", async () => {
    try {
      await runEstimate();
    } catch (e) {
      setError(`Estimate failed: ${e.message}`);
    }
  });

  // ---- Boot ----
  try {
    setLoading("Loading...");
    await Promise.all([loadYears(), loadCatalog()]);
    setLoading("");
  } catch (e) {
    setError(`Startup failed: ${e.message}`);
  }
})();
