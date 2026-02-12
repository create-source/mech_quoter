document.addEventListener("DOMContentLoaded", () => {
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

    items.forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      select.appendChild(opt);
    });
  };

  const unwrapList = (data, key) => {
    if (Array.isArray(data)) return data;
    if (data && Array.isArray(data[key])) return data[key];
    return [];
  };

  async function loadMakes() {
    const year = yearEl.value || "";
    console.log("Loading makes for year:", year);

    setOptions(makeEl, [], "Select make");
    setOptions(modelEl, [], "Select model");

    try {
      const res = await fetch(`/api/makes?year=${encodeURIComponent(year)}`);
      if (!res.ok) throw new Error(`GET /api/makes failed: ${res.status}`);
      const data = await res.json();
      const makes = unwrapList(data, "makes");

      console.log("Makes returned:", makes);
      setOptions(makeEl, makes, "Select make");
    } catch (err) {
      console.error("Error loading makes:", err);
    }
  }

  async function loadModels() {
    const year = yearEl.value || "";
    const make = makeEl.value || "";
    console.log("Loading models for:", { year, make });

    setOptions(modelEl, [], "Select model");
    if (!make) return;

    try {
      const res = await fetch(`/api/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`);
      if (!res.ok) throw new Error(`GET /api/models failed: ${res.status}`);
      const data = await res.json();
      const models = unwrapList(data, "models");

      console.log("Models returned:", models);
      setOptions(modelEl, models, "Select model");
    } catch (err) {
      console.error("Error loading models:", err);
    }
  }

  // Hook changes
  yearEl.addEventListener("change", loadMakes);
  makeEl.addEventListener("change", loadModels);

  // Initial load
  loadMakes();
});
