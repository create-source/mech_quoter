(() => {
  // ---------- helpers ----------
  const $ = (id) => document.getElementById(id);

  function setStatus(msg, isError = false) {
    const box = $("statusBox");
    if (!box) return;
    box.textContent = msg || "";
    box.style.display = msg ? "block" : "none";
    box.style.borderColor = isError ? "rgba(255,80,80,.45)" : "rgba(255,255,255,.12)";
  }

  function clearSelect(sel, placeholderText) {
    if (!sel) return;
    sel.innerHTML = "";
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = placeholderText;
    sel.appendChild(opt);
    sel.value = "";
  }

  function fillSelect(sel, items, placeholderText) {
    clearSelect(sel, placeholderText);
    if (!sel) return;
    (items || []).forEach((v) => {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      sel.appendChild(opt);
    });
  }

  // Accept either:
  //  - ["TOYOTA","HONDA"]
  //  - { makes: [...] }
  //  - { models: [...] }
  function unwrapArray(json, keyGuess) {
    if (Array.isArray(json)) return json;
    if (json && Array.isArray(json[keyGuess])) return json[keyGuess];
    return [];
  }

  async function fetchJSON(url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText} for ${url}`);
    return await r.json();
  }

  // ---------- main ----------
  async function init() {
    const yearSel = $("year");
    const makeSel = $("make");
    const modelSel = $("model");
    const catSel = $("category");
    const svcSel = $("service");

    if (!yearSel || !makeSel || !modelSel || !catSel || !svcSel) {
      setStatus("UI init failed: Missing form elements in index.html", true);
      return;
    }

    // Start clean
    setStatus("");
    clearSelect(yearSel, "Select year");
    clearSelect(makeSel, "Select make");
    clearSelect(modelSel, "Select model");
    clearSelect(catSel, "Select category");
    clearSelect(svcSel, "Select service");

    // ---- load years
    let years = [];
    try {
      const y = await fetchJSON("/vehicle/years");
      years = unwrapArray(y, "years"); // supports array or {years:[]}
      fillSelect(yearSel, years, "Select year");
    } catch (e) {
      setStatus(`Failed loading years: ${e.message}`, true);
    }

    // ---- load catalog (categories + services)
    let catalog = null;
    try {
      catalog = await fetchJSON("/catalog");
      const categories = (catalog.categories || []).map((c) => ({ key: c.key, name: c.name }));
      // categories dropdown uses key as value
      catSel.innerHTML = "";
      const opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = "Select category";
      catSel.appendChild(opt0);

      categories.forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c.key;
        opt.textContent = c.name;
        catSel.appendChild(opt);
      });

      // default labor rate if your UI uses it
      const laborRate = $("laborRate");
      if (laborRate && catalog.labor_rate) laborRate.value = String(catalog.labor_rate);
    } catch (e) {
      setStatus(`Failed loading catalog: ${e.message}`, true);
    }

    // ---- handlers
    async function loadMakes() {
      clearSelect(makeSel, "Loading makes...");
      clearSelect(modelSel, "Select model");
      const year = yearSel.value;
      if (!year) {
        clearSelect(makeSel, "Select make");
        return;
      }
      try {
        const json = await fetchJSON(`/vehicle/makes?year=${encodeURIComponent(year)}`);
        const makes = unwrapArray(json, "makes");
        fillSelect(makeSel, makes, "Select make");
      } catch (e) {
        clearSelect(makeSel, "Select make");
        setStatus(`Failed loading makes: ${e.message}`, true);
      }
    }

    async function loadModels() {
      clearSelect(modelSel, "Loading models...");
      const year = yearSel.value;
      const make = makeSel.value;
      if (!year || !make) {
        clearSelect(modelSel, "Select model");
        return;
      }
      try {
        const json = await fetchJSON(
          `/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`
        );
        const models = unwrapArray(json, "models");
        fillSelect(modelSel, models, "Select model");
      } catch (e) {
        clearSelect(modelSel, "Select model");
        setStatus(`Failed loading models: ${e.message}`, true);
      }
    }

    function loadServicesForCategory() {
      clearSelect(svcSel, "Select service");
      const key = catSel.value;
      if (!key || !catalog) return;

      const cat = (catalog.categories || []).find((c) => c.key === key);
      const services = (cat?.services || []).map((s) => ({
        code: s.code,
        name: s.name,
        min: s.labor_hours_min,
        max: s.labor_hours_max,
      }));

      // service dropdown uses service.code as value
      svcSel.innerHTML = "";
      const opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = "Select service";
      svcSel.appendChild(opt0);

      services.forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s.code;
        opt.textContent = s.name;
        // stash labor hours range on the option
        opt.dataset.min = String(s.min ?? "");
        opt.dataset.max = String(s.max ?? "");
        svcSel.appendChild(opt);
      });
    }

    function applyLaborHoursFromService() {
      const laborHours = $("laborHours");
      if (!laborHours) return;

      const opt = svcSel.options[svcSel.selectedIndex];
      if (!opt || !opt.dataset) return;

      const min = parseFloat(opt.dataset.min || "");
      const max = parseFloat(opt.dataset.max || "");
      if (Number.isFinite(min) && Number.isFinite(max)) {
        // default to midpoint
        const mid = Math.round(((min + max) / 2) * 10) / 10;
        laborHours.value = String(mid);
      }
    }

    yearSel.addEventListener("change", async () => {
      await loadMakes();
      await loadModels();
    });

    makeSel.addEventListener("change", async () => {
      await loadModels();
    });

    catSel.addEventListener("change", () => {
      loadServicesForCategory();
    });

    svcSel.addEventListener("change", () => {
      applyLaborHoursFromService();
    });

    // Initial: if a year is preselected, load makes
    if (yearSel.value) {
      await loadMakes();
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    init().catch((e) => {
      console.error(e);
      const box = document.getElementById("statusBox");
      if (box) box.textContent = `UI init failed: ${e.message}`;
    });
  });
})();
