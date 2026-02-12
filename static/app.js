// app.js — populates Year/Make/Model from GET /catalog

document.addEventListener("DOMContentLoaded", async () => {
  console.log("app.js loaded ✅");

  // ---- Grab elements (these IDs must exist in your HTML) ----
  const yearEl = document.getElementById("year");
  const makeEl = document.getElementById("make");
  const modelEl = document.getElementById("model");

  if (!yearEl || !makeEl || !modelEl) {
    console.error("Missing required select IDs. Need #year, #make, #model", {
      yearEl,
      makeEl,
      modelEl,
    });
    return;
  }

  // ---- Helpers ----
  const setOptions = (select, items, placeholder) => {
    select.innerHTML = "";

    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = placeholder;
    select.appendChild(ph);

    (items || []).forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      select.appendChild(opt);
    });
  };

  const normalizeModels = (modelsRaw) => {
    // modelsRaw can be:
    // - ["Camry","Corolla"]
    // - {"Camry": {...}, "Corolla": {...}}
    // - {"models": ["Camry","Corolla"]}
    if (!modelsRaw) return [];

    if (Array.isArray(modelsRaw)) return modelsRaw;

    if (typeof modelsRaw === "object") {
      if (Array.isArray(modelsRaw.models)) return modelsRaw.models;
      return Object.keys(modelsRaw);
    }

    return [];
  };

  const sortYearsDesc = (years) =>
    years.sort((a, b) => Number(b) - Number(a));

  // ---- Load catalog ----
  let catalog = {};
  try {
    const res = await fetch("/catalog", { cache: "no-store" });
    if (!res.ok) throw new Error(`GET /catalog failed: ${res.status}`);
    catalog = await res.json();

    console.log("Catalog loaded ✅", catalog);
  } catch (err) {
    console.error("Failed to load catalog ❌", err);
    setOptions(yearEl, [], "Year unavailable");
    setOptions(makeEl, [], "Make unavailable");
    setOptions(modelEl, [], "Model unavailable");
    return;
  }

  // ---- Populate Years from catalog keys ----
  const years = sortYearsDesc(Object.keys(catalog || {}));
  setOptions(yearEl, years, "Select year");
  setOptions(makeEl, [], "Select make");
  setOptions(modelEl, [], "Select model");

  // ---- Year -> Makes ----
  yearEl.addEventListener("change", () => {
    const year = yearEl.value;

    setOptions(makeEl, [], "Select make");
    setOptions(modelEl, [], "Select model");

    if (!year) return;

    const yearData = catalog[year];
    if (!yearData || typeof yearData !== "object") {
      console.warn("No catalog data for year:", year);
      return;
    }

    const makes = Object.keys(yearData).sort();
    console.log("Makes for year", year, "=>", makes);

    setOptions(makeEl, makes, "Select make");
  });

  // ---- Make -> Models ----
  makeEl.addEventListener("change", () => {
    const year = yearEl.value;
    const make = makeEl.value;

    setOptions(modelEl, [], "Select model");

    if (!year || !make) return;

    const yearData = catalog[year];
    if (!yearData || typeof yearData !== "object") return;

    const modelsRaw = yearData[make];
    const models = normalizeModels(modelsRaw).sort();

    console.log("Models for", { year, make }, "=>", models);

    setOptions(modelEl, models, "Select model");
  });
});
