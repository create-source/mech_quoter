/* global Choices */
(() => {
  const $ = (id) => document.getElementById(id);

  const els = {
    zip: $("zip"),
    partsPrice: $("partsPrice"),
    laborPricing: $("laborPricing"),
    laborHours: $("laborHours"),
    flatLabor: $("flatLabor"),
    vehicleType: $("vehicleType"),
    year: $("year"),
    make: $("make"),
    model: $("model"),
    category: $("category"),
    service: $("service"),
    btnEstimate: $("btnEstimate"),
    result: $("result"),
  };

  function setResult(obj) {
    els.result.textContent = typeof obj === "string" ? obj : JSON.stringify(obj, null, 2);
  }

  async function apiGet(path) {
    const res = await fetch(path, { headers: { "Accept": "application/json" } });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText} — ${text}`);
    }
    return res.json();
  }

  async function apiPost(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      throw new Error(`${res.status} ${res.statusText} — ${text}`);
    }
    return res.json();
  }

  function clearSelect(sel, placeholderText) {
    sel.innerHTML = "";
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = placeholderText;
    opt.selected = true;
    sel.appendChild(opt);
  }

  function addOptions(sel, items, getValue, getLabel) {
    for (const item of items) {
      const opt = document.createElement("option");
      opt.value = String(getValue(item) ?? "");
      opt.textContent = String(getLabel(item) ?? "");
      sel.appendChild(opt);
    }
  }

  // Choices.js: make selects searchable / pretty
  function initChoices(selectEl, placeholder) {
    if (!window.Choices) return null;
    return new Choices(selectEl, {
      searchEnabled: true,
      shouldSort: false,
      itemSelectText: "",
      placeholderValue: placeholder,
      allowHTML: false,
    });
  }

  const choices = {
    year: null,
    make: null,
    model: null,
    category: null,
    service: null,
  };

  function refreshChoices(instance) {
    // Choices needs setChoices when we rebuild <option>s
    if (!instance) return;
    instance.destroy();
  }

  function rebuildChoices() {
    // Re-init after options change
    choices.year = initChoices(els.year, "Select year");
    choices.make = initChoices(els.make, "Select make");
    choices.model = initChoices(els.model, "Select a model");
    choices.category = initChoices(els.category, "Select category");
    choices.service = initChoices(els.service, "Select a service");
  }

  function getVehicleQuery() {
    const params = new URLSearchParams();
    if (els.vehicleType.value) params.set("vehicle_type", els.vehicleType.value);
    if (els.year.value) params.set("year", els.year.value);
    if (els.make.value) params.set("make", els.make.value);
    if (els.model.value) params.set("model", els.model.value);
    return params.toString() ? `?${params.toString()}` : "";
  }

  async function loadYears() {
    clearSelect(els.year, "Select year");
    clearSelect(els.make, "Select make");
    clearSelect(els.model, "Select a model");

    const q = new URLSearchParams();
    if (els.vehicleType.value) q.set("vehicle_type", els.vehicleType.value);
    const years = await apiGet(`/vehicle/years${q.toString() ? `?${q.toString()}` : ""}`);
    addOptions(els.year, years, (x) => x, (x) => x);

    rebuildChoices();
  }

  async function loadMakes() {
    clearSelect(els.make, "Select make");
    clearSelect(els.model, "Select a model");

    const q = new URLSearchParams();
    if (els.vehicleType.value) q.set("vehicle_type", els.vehicleType.value);
    if (els.year.value) q.set("year", els.year.value);

    const makes = await apiGet(`/vehicle/makes${q.toString() ? `?${q.toString()}` : ""}`);
    addOptions(els.make, makes, (x) => x, (x) => x);

    rebuildChoices();
  }

  async function loadModels() {
    clearSelect(els.model, "Select a model");

    const q = new URLSearchParams();
    if (els.vehicleType.value) q.set("vehicle_type", els.vehicleType.value);
    if (els.year.value) q.set("year", els.year.value);
    if (els.make.value) q.set("make", els.make.value);

    const models = await apiGet(`/vehicle/models${q.toString() ? `?${q.toString()}` : ""}`);
    addOptions(els.model, models, (x) => x, (x) => x);

    rebuildChoices();
  }

  async function loadCategories() {
    clearSelect(els.category, "Select category");
    clearSelect(els.service, "Select a service");

    const cats = await apiGet(`/categories${getVehicleQuery()}`);

    // cats is a LIST of objects like: {key,name,count}
    addOptions(
      els.category,
      cats,
      (c) => c.key,
      (c) => c.name
    );

    rebuildChoices();
  }

  async function loadServices() {
    clearSelect(els.service, "Select a service");
    const catKey = els.category.value;
    if (!catKey) {
      rebuildChoices();
      return;
    }

    const svcs = await apiGet(`/services/${encodeURIComponent(catKey)}${getVehicleQuery()}`);

    // svcs is a LIST of objects like: {id,name,hrs}
    addOptions(
      els.service,
      svcs,
      (s) => s.id,
      (s) => (s.hrs ? `${s.name} (${s.hrs}h)` : s.name)
    );

    rebuildChoices();
  }

  function syncLaborInputs() {
    const pricing = els.laborPricing.value;
    const hourly = pricing === "hourly";

    els.laborHours.disabled = !hourly;
    els.flatLabor.disabled = hourly;

    if (hourly) els.flatLabor.value = "";
    else els.laborHours.value = "";
  }

  async function doEstimate() {
    const zip = (els.zip.value || "").trim();
    if (!zip) return setResult("Enter a ZIP code.");

    const laborPricing = els.laborPricing.value;
    const partsPrice = Number(els.partsPrice.value || 0);

    // If a service is chosen and label contains "(Xh)" we can auto-use those hours
    let laborHours = Number(els.laborHours.value || 0);
    const serviceText = els.service.options[els.service.selectedIndex]?.textContent || "";
    const match = serviceText.match(/\(([\d.]+)\s*h\)/i);
    if (match && laborPricing === "hourly") {
      laborHours = Number(match[1]);
      if (!Number.isNaN(laborHours)) els.laborHours.value = String(laborHours);
    }

    const flatLabor = Number(els.flatLabor.value || 0);

    // ask server for labor rate (optional)
    let laborRate = 0;
    try {
      const r = await apiGet(`/labor_rate?zip=${encodeURIComponent(zip)}`);
      laborRate = Number(r.rate || 0);
    } catch (_) {
      // ok if rate endpoint fails; estimate will still run
    }

    const payload = {
      zip,
      parts_price: partsPrice,
      labor_pricing: laborPricing,
      labor_hours: laborPricing === "hourly" ? laborHours : 0,
      labor_rate: laborRate,
      flat_labor: laborPricing === "flat" ? flatLabor : 0,

      vehicle_type: els.vehicleType.value || null,
      year: els.year.value || null,
      make: els.make.value || null,
      model: els.model.value || null,

      category_key: els.category.value || null,
      service_id: els.service.value || null,
    };

    const result = await apiPost("/estimate", payload);
    setResult(result);
  }

  async function init() {
    syncLaborInputs();

    // Initialize dropdown styling once (Choices will be rebuilt after loads)
    rebuildChoices();

    // Load initial vehicle list + categories
    await loadYears();
    await loadCategories();
  }

  // --- Events ---
  els.laborPricing.addEventListener("change", syncLaborInputs);

  els.vehicleType.addEventListener("change", async () => {
    await loadYears();
    await loadCategories();
  });

  els.year.addEventListener("change", async () => {
    await loadMakes();
    await loadCategories();
  });

  els.make.addEventListener("change", async () => {
    await loadModels();
    await loadCategories();
  });

  els.model.addEventListener("change", async () => {
    await loadCategories();
  });

  els.category.addEventListener("change", async () => {
    await loadServices();
  });

  els.btnEstimate.addEventListener("click", async () => {
    try {
      await doEstimate();
    } catch (e) {
      setResult(String(e));
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    init().catch((e) => setResult(String(e)));
  });
})();
