document.addEventListener("DOMContentLoaded", async () => {
  console.log("app.js loaded ✅");

  const yearEl = document.getElementById("year");
  const makeEl = document.getElementById("make");
  const modelEl = document.getElementById("model");

  if (!yearEl || !makeEl || !modelEl) {
    console.error("Missing select IDs. Need #year, #make, #model", { yearEl, makeEl, modelEl });
    return;
  }

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

  const isYearKey = (k) => /^\d{4}$/.test(String(k)); // "2019"

  const normalizeModels = (modelsRaw) => {
    if (!modelsRaw) return [];
    if (Array.isArray(modelsRaw)) return modelsRaw;
    if (typeof modelsRaw === "object") {
      if (Array.isArray(modelsRaw.models)) return modelsRaw.models;
      return Object.keys(modelsRaw);
    }
    return [];
  };

  // ---- Load catalog ----
  let catalog;
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

  // ---- Find vehicle tree inside catalog ----
  // If catalog has a "vehicles" key, use that. Otherwise assume catalog itself is the vehicle tree.
  const vehicleTree = (catalog && typeof catalog === "object" && catalog.vehicles && typeof catalog.vehicles === "object")
    ? catalog.vehicles
    : catalog;

  // ---- Years (only 4-digit keys) ----
  const years = Object.keys(vehicleTree || {})
    .filter(isYearKey)
    .sort((a, b) => Number(b) - Number(a));

  console.log("Years detected:", years);

  setOptions(yearEl, years, "Select year");
  setOptions(makeEl, [], "Select make");
  setOptions(modelEl, [], "Select model");

  // ---- Year -> Makes ----
  yearEl.addEventListener("change", () => {
    const year = yearEl.value;
    setOptions(makeEl, [], "Select make");
    setOptions(modelEl, [], "Select model");

    if (!year) return;

    const yearData = vehicleTree[year];
    if (!yearData || typeof yearData !== "object") return;

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

    const yearData = vehicleTree[year];
    if (!yearData || typeof yearData !== "object") return;

    const modelsRaw = yearData[make];
    const models = normalizeModels(modelsRaw).sort();

    console.log("Models for", { year, make }, "=>", models);
    setOptions(modelEl, models, "Select model");
  });
});
