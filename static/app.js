// Front-end logic for Repair Estimator
// - Vehicle selects (Year -> Make -> Model) load from API
// - Category -> Service filtering is 100% client-side (catalog loaded once)
// - Estimate call posts selections + optional parts price

async function getJSON(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`);
  }
  return await res.json();
}

async function postJSON(url, payload) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text.slice(0, 200)}`);
  }
  return await res.json();
}

function clearOptions(selectEl, placeholder) {
  selectEl.innerHTML = "";
  const opt = document.createElement("option");
  opt.value = "";
  opt.textContent = placeholder;
  opt.disabled = true;
  opt.selected = true;
  selectEl.appendChild(opt);
}

function addOption(selectEl, value, label) {
  const opt = document.createElement("option");
  opt.value = String(value);
  opt.textContent = label;
  selectEl.appendChild(opt);
}

function money(n) {
  const num = Number(n);
  if (!Number.isFinite(num)) return "$0";
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(num);
}

document.addEventListener("DOMContentLoaded", async () => {
  // IDs come from index.html
  const yearSelect = document.getElementById("year");
  const makeSelect = document.getElementById("make");
  const modelSelect = document.getElementById("model");
  const categorySelect = document.getElementById("category");
  const serviceSelect = document.getElementById("service");

  const zipInput = document.getElementById("zip");
  const partsPriceInput = document.getElementById("partsPrice");
  const pricingModeSelect = document.getElementById("pricingMode");
  const getEstimateBtn = document.getElementById("estimateBtn");
  const resultEl = document.getElementById("result");

  // Optional status element
  let statusEl = document.getElementById("status");
  if (!statusEl) {
    statusEl = document.createElement("div");
    statusEl.id = "status";
    statusEl.style.margin = "8px 0";
    statusEl.style.fontSize = "14px";
    const h1 = document.querySelector("h1");
    if (h1 && h1.parentNode) h1.parentNode.insertBefore(statusEl, h1.nextSibling);
  }

  function setStatus(msg) {
    statusEl.textContent = msg || "";
  }

  // Local catalog cache (category->services)
  let categoriesByKey = new Map();

  function resetVehicleDownstream() {
    clearOptions(makeSelect, "Select make");
    clearOptions(modelSelect, "Select a model");
    makeSelect.disabled = true;
    modelSelect.disabled = true;
  }

  function resetCatalogDownstream() {
    clearOptions(categorySelect, "Select category");
    clearOptions(serviceSelect, "Select a service");
    categorySelect.disabled = true;
    serviceSelect.disabled = true;
  }

  function resetAll() {
    clearOptions(yearSelect, "Select year");
    yearSelect.disabled = true;
    resetVehicleDownstream();
    resetCatalogDownstream();
  }

  resetAll();

  async function loadYears() {
    setStatus("Loading years...");
    const years = await getJSON("/vehicle/years");
    clearOptions(yearSelect, "Select year");
    for (const y of years) addOption(yearSelect, y, y);
    yearSelect.disabled = false;
    setStatus("");
  }

  async function loadMakes(year) {
    setStatus("Loading makes...");
    const makes = await getJSON(`/vehicle/makes?year=${encodeURIComponent(year)}`);
    clearOptions(makeSelect, "Select make");
    for (const m of makes) addOption(makeSelect, m, m);
    makeSelect.disabled = false;
    setStatus("");
  }

  async function loadModels(year, make) {
    setStatus("Loading models...");
    const models = await getJSON(`/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`);
    clearOptions(modelSelect, "Select a model");
    for (const m of models) addOption(modelSelect, m, m);
    modelSelect.disabled = false;
    setStatus("");
  }

  async function loadCatalog() {
    setStatus("Loading service catalog...");
    const catalog = await getJSON("/catalog");
    const cats = catalog.categories || [];
    categoriesByKey = new Map(cats.map((c) => [c.key, c]));

    clearOptions(categorySelect, "Select category");
    for (const c of cats) addOption(categorySelect, c.key, c.name);
    categorySelect.disabled = false;

    clearOptions(serviceSelect, "Select a service");
    serviceSelect.disabled = true;
    setStatus("");
  }

  function populateServicesForCategory(categoryKey) {
    clearOptions(serviceSelect, "Select a service");
    const cat = categoriesByKey.get(categoryKey);
    const services = cat?.services || [];
    for (const s of services) addOption(serviceSelect, s.code, s.name);
    serviceSelect.disabled = services.length === 0;
  }

  // Wire up events
  yearSelect.addEventListener("change", async () => {
    resetVehicleDownstream();
    const year = yearSelect.value;
    if (!year) return;
    try {
      await loadMakes(year);
    } catch (err) {
      console.error(err);
      setStatus("Failed to load makes.");
      alert("Failed to load makes. Check server logs.");
    }
  });

  makeSelect.addEventListener("change", async () => {
    clearOptions(modelSelect, "Select a model");
    modelSelect.disabled = true;
    const year = yearSelect.value;
    const make = makeSelect.value;
    if (!year || !make) return;
    try {
      await loadModels(year, make);
    } catch (err) {
      console.error(err);
      setStatus("Failed to load models.");
      alert("Failed to load models. Check server logs.");
    }
  });

  categorySelect.addEventListener("change", () => {
    populateServicesForCategory(categorySelect.value);
  });

  getEstimateBtn.addEventListener("click", async () => {
    resultEl.innerHTML = "";

    const payload = {
      zip_code: (zipInput.value || "").trim(),
      year: parseInt(yearSelect.value, 10),
      make: makeSelect.value,
      model: modelSelect.value,
      category_key: categorySelect.value,
      service_code: serviceSelect.value,
      pricing_mode: pricingModeSelect ? pricingModeSelect.value : "flat",
      parts_price: partsPriceInput.value === "" ? null : Number(partsPriceInput.value),
    };

    if (!payload.year || !payload.make || !payload.model || !payload.category_key || !payload.service_code) {
      alert("Please select Year, Make, Model, Category, and Service.");
      return;
    }

    if (payload.zip_code && !/^\d{5}(-\d{4})?$/.test(payload.zip_code)) {
      alert("Please enter a valid ZIP code (5 digits).");
      return;
    }

    if (payload.parts_price != null && (!Number.isFinite(payload.parts_price) || payload.parts_price < 0)) {
      alert("Parts price must be a positive number.");
      return;
    }

    try {
      setStatus("Calculating estimate...");
      const data = await postJSON("/estimate", payload);
      setStatus("");

      const [h1, h2] = data.labor_hours_range;
      const [l1, l2] = data.labor_cost_range;
      const [t1, t2] = data.total_cost_range;

      resultEl.innerHTML = `
        <div class="card">
          <div class="card-title">Estimate</div>
          <div class="card-row"><span>Labor hours</span><span>${h1.toFixed(1)}–${h2.toFixed(1)}</span></div>
          <div class="card-row"><span>Labor</span><span>${money(l1)} – ${money(l2)}</span></div>
          <div class="card-row"><span>Parts</span><span>${money(data.parts_price || 0)}</span></div>
          <div class="card-row total"><span>Total</span><span>${money(t1)} – ${money(t2)}</span></div>
          <div class="card-note">ZIP labor multiplier: ${(data.labor_rate_multiplier || 1).toFixed(2)}</div>
        </div>
      `;
    } catch (err) {
      console.error(err);
      setStatus("Estimate failed.");
      alert("Estimate failed. Check server logs.");
    }
  });

  // Initial loads
  try {
    await Promise.all([loadYears(), loadCatalog()]);
  } catch (err) {
    console.error(err);
    setStatus("Failed to initialize.");
    alert("Failed to initialize UI. Check server logs.");
  }
});
