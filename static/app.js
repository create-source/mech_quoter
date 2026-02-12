/* static/app.js */

function $(id) {
  return document.getElementById(id);
}

function money(n) {
  const x = Number(n || 0);
  return `$${x.toFixed(2)}`;
}

function setOptions(selectEl, items, { placeholder = "Select...", valueKey = null, textKey = null } = {}) {
  selectEl.innerHTML = "";

  const ph = document.createElement("option");
  ph.value = "";
  ph.textContent = placeholder;
  selectEl.appendChild(ph);

  for (const item of items) {
    const opt = document.createElement("option");
    if (valueKey) opt.value = item[valueKey];
    else opt.value = String(item);

    if (textKey) opt.textContent = item[textKey];
    else opt.textContent = String(item);

    selectEl.appendChild(opt);
  }

  selectEl.value = "";
}

async function apiGet(path) {
  const r = await fetch(path, { method: "GET" });
  if (!r.ok) throw new Error(`GET ${path} failed: ${r.status}`);
  return await r.json();
}

async function apiPost(path, payload) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`POST ${path} failed: ${r.status}`);
  return r;
}

let catalogData = null;

function findCategoryByKey(key) {
  return (catalogData?.categories || []).find((c) => c.key === key) || null;
}

function findServiceByCode(categoryKey, serviceCode) {
  const cat = findCategoryByKey(categoryKey);
  if (!cat) return null;
  return (cat.services || []).find((s) => s.code === serviceCode) || null;
}

function renderEstimate(statusBox, payload) {
  const laborTotal = Number(payload.laborHours || 0) * Number(payload.laborRate || 0);
  const parts = Number(payload.partsPrice || 0);
  const total = laborTotal + parts;

  statusBox.innerHTML = `
    <div style="font-weight:700; margin-bottom:6px;">Estimate</div>
    <div><strong>Labor:</strong> ${money(laborTotal)} (${Number(payload.laborHours || 0).toFixed(1)} hrs @ ${money(payload.laborRate).replace("$", "$")}/hr)</div>
    <div><strong>Parts:</strong> ${money(parts)}</div>
    <div style="margin-top:6px; font-size:1.05em;"><strong>Total:</strong> ${money(total)}</div>
  `;
}

async function init() {
  // Grab elements
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

  // Guard against missing IDs (prevents addEventListener null crash)
  const required = [
    yearSel, makeSel, modelSel, categorySel, serviceSel,
    laborHoursEl, partsPriceEl, laborRateEl, notesEl,
    estimateBtn, pdfBtn, statusBox
  ];
  if (required.some((el) => !el)) {
    throw new Error("Missing one or more required elements. Check your index.html IDs.");
  }

  // ---------- Load catalog ----------
  statusBox.textContent = "Loading catalog...";
  catalogData = await apiGet("/catalog");

  // Set labor rate default from catalog if present
  if (catalogData?.labor_rate && !laborRateEl.value) {
    laborRateEl.value = String(catalogData.labor_rate);
  } else if (catalogData?.labor_rate && Number(laborRateEl.value || 0) === 0) {
    laborRateEl.value = String(catalogData.labor_rate);
  }

  // Categories
  const cats = (catalogData.categories || []).map((c) => ({ key: c.key, name: c.name }));
  setOptions(categorySel, cats, { placeholder: "Select category", valueKey: "key", textKey: "name" });

  // Services starts empty until category selected
  setOptions(serviceSel, [], { placeholder: "Select service" });

  // ---------- Load years ----------
  statusBox.textContent = "Loading years...";
  const years = await apiGet("/vehicle/years");
  setOptions(yearSel, years, { placeholder: "Select year" });

  // Makes + Models start empty
  setOptions(makeSel, [], { placeholder: "Select make" });
  setOptions(modelSel, [], { placeholder: "Select model" });

  statusBox.textContent = "";

  // ---------- Events: Vehicle ----------
  yearSel.addEventListener("change", async () => {
    const year = yearSel.value;
    setOptions(makeSel, [], { placeholder: "Loading makes..." });
    setOptions(modelSel, [], { placeholder: "Select model" });

    if (!year) {
      setOptions(makeSel, [], { placeholder: "Select make" });
      return;
    }

    try {
      const data = await apiGet(`/vehicle/makes?year=${encodeURIComponent(year)}`);
      const makes = Array.isArray(data) ? data : (data.makes || []);
      setOptions(makeSel, makes, { placeholder: "Select make" });
    } catch (e) {
      console.error(e);
      setOptions(makeSel, [], { placeholder: "Makes unavailable" });
      statusBox.textContent = "Could not load makes. Try again.";
    }
  });

  makeSel.addEventListener("change", async () => {
    const year = yearSel.value;
    const make = makeSel.value;

    setOptions(modelSel, [], { placeholder: "Loading models..." });

    if (!year || !make) {
      setOptions(modelSel, [], { placeholder: "Select model" });
      return;
    }

    try {
      const data = await apiGet(`/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`);
      const models = Array.isArray(data) ? data : (data.models || []);
      setOptions(modelSel, models, { placeholder: "Select model" });
    } catch (e) {
      console.error(e);
      setOptions(modelSel, [], { placeholder: "Models unavailable" });
      statusBox.textContent = "Could not load models. Try again.";
    }
  });

  // ---------- Events: Service ----------
  categorySel.addEventListener("change", () => {
    const key = categorySel.value;
    const cat = findCategoryByKey(key);

    const services = (cat?.services || []).map((s) => ({
      code: s.code,
      name: s.name,
    }));

    setOptions(serviceSel, services, { placeholder: "Select service", valueKey: "code", textKey: "name" });

    // Reset labor hours on category change
    laborHoursEl.value = "0";
  });

  serviceSel.addEventListener("change", () => {
    const catKey = categorySel.value;
    const svcCode = serviceSel.value;
    const svc = findServiceByCode(catKey, svcCode);

    // Default labor hours from catalog
    if (svc && typeof svc.labor_hours_min === "number") {
      laborHoursEl.value = String(svc.labor_hours_min);
    }
  });

  // ---------- Buttons ----------
  estimateBtn.addEventListener("click", () => {
    try {
      const payload = {
        year: yearSel.value,
        make: makeSel.value,
        model: modelSel.value,
        categoryKey: categorySel.value,
        category: categorySel.options[categorySel.selectedIndex]?.textContent || "",
        serviceCode: serviceSel.value,
        service: serviceSel.options[serviceSel.selectedIndex]?.textContent || "",
        laborHours: Number(laborHoursEl.value || 0),
        partsPrice: Number(partsPriceEl.value || 0),
        laborRate: Number(laborRateEl.value || 90),
        notes: notesEl.value || "",
      };

      if (!payload.year || !payload.make || !payload.model) {
        statusBox.textContent = "Select Year, Make, and Model.";
        return;
      }
      if (!payload.categoryKey || !payload.serviceCode) {
        statusBox.textContent = "Select Category and Service.";
        return;
      }

      renderEstimate(statusBox, payload);
    } catch (e) {
      console.error(e);
      statusBox.textContent = `Estimate error: ${e.message}`;
    }
  });

  pdfBtn.addEventListener("click", async () => {
    try {
      const payload = {
        year: yearSel.value,
        make: makeSel.value,
        model: modelSel.value,
        category: categorySel.options[categorySel.selectedIndex]?.textContent || "",
        service: serviceSel.options[serviceSel.selectedIndex]?.textContent || "",
        laborHours: Number(laborHoursEl.value || 0),
        partsPrice: Number(partsPriceEl.value || 0),
        laborRate: Number(laborRateEl.value || 90),
        notes: notesEl.value || "",
      };

      if (!payload.year || !payload.make || !payload.model) {
        statusBox.textContent = "Select Year, Make, and Model before PDF.";
        return;
      }
      if (!categorySel.value || !serviceSel.value) {
        statusBox.textContent = "Select Category and Service before PDF.";
        return;
      }

      statusBox.textContent = "Generating PDF...";

      const r = await apiPost("/estimate/pdf", payload);
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);

      window.open(url, "_blank");
      setTimeout(() => URL.revokeObjectURL(url), 60_000);

      statusBox.textContent = "";
    } catch (e) {
      console.error(e);
      statusBox.textContent = `PDF error: ${e.message}`;
    }
  });
}

// Boot
window.addEventListener("DOMContentLoaded", () => {
  // PWA service worker (safe if file exists)
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/static/sw.js").catch(() => {});
  }

  init().catch((e) => {
    console.error(e);
    const box = $("statusBox");
    if (box) box.textContent = `UI init failed: ${e.message}`;
  });
});
