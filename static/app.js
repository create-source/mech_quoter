/* global Choices */

async function apiGet(url) {
  const r = await fetch(url, { headers: { "Accept": "application/json" } });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`${url} failed: ${r.status} ${r.statusText} ${text}`);
  }
  return r.json();
}

async function apiPost(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`${url} failed: ${r.status} ${r.statusText} ${text}`);
  }
  return r.json();
}

function onlyDigits(s) {
  return (s || "").replace(/\D+/g, "");
}

function setStatus(el, msg, isError = false) {
  el.textContent = msg;
  el.classList.toggle("error", !!isError);
}

document.addEventListener("DOMContentLoaded", async () => {
  const zip = document.getElementById("zip");
  const yearEl = document.getElementById("year");
  const makeEl = document.getElementById("make");
  const modelEl = document.getElementById("model");
  const categoryEl = document.getElementById("category");
  const serviceEl = document.getElementById("service");
  const btn = document.getElementById("estimateBtn");
  const result = document.getElementById("result");

  // Fix zip typing
  zip.addEventListener("input", () => {
    zip.value = onlyDigits(zip.value).slice(0, 5);
  });

  // Choices (searchable selects)
  const yearChoices = new Choices(yearEl, { searchEnabled: true, shouldSort: false });
  const makeChoices = new Choices(makeEl, { searchEnabled: true, shouldSort: false });
  const modelChoices = new Choices(modelEl, { searchEnabled: true, shouldSort: false });
  const categoryChoices = new Choices(categoryEl, { searchEnabled: true, shouldSort: false });
  const serviceChoices = new Choices(serviceEl, { searchEnabled: true, shouldSort: false });

  function resetChoices(ch, placeholder) {
    ch.clearStore();
    ch.setChoices([{ value: "", label: placeholder, disabled: true, selected: true }], "value", "label", true);
  }

  resetChoices(yearChoices, "Select year");
  resetChoices(makeChoices, "Select make");
  resetChoices(modelChoices, "Select a model");
  resetChoices(categoryChoices, "Select category");
  resetChoices(serviceChoices, "Select a service");

  async function loadYears() {
    const years = await apiGet("/vehicle/years");
    const choices = [
      { value: "", label: "Select year", disabled: true, selected: true },
      ...years.map(y => ({ value: String(y), label: String(y) })),
    ];
    yearChoices.setChoices(choices, "value", "label", true);
  }

  async function loadMakes() {
    resetChoices(makeChoices, "Select make");
    resetChoices(modelChoices, "Select a model");
    resetChoices(categoryChoices, "Select category");
    resetChoices(serviceChoices, "Select a service");

    const y = yearEl.value;
    if (!y) return;

    const makes = await apiGet(`/vehicle/makes?year=${encodeURIComponent(y)}`);
    const choices = [
      { value: "", label: "Select make", disabled: true, selected: true },
      ...makes.map(m => ({ value: m, label: m })),
    ];
    makeChoices.setChoices(choices, "value", "label", true);
  }

  async function loadModels() {
    resetChoices(modelChoices, "Select a model");
    resetChoices(categoryChoices, "Select category");
    resetChoices(serviceChoices, "Select a service");

    const y = yearEl.value;
    const m = makeEl.value;
    if (!y || !m) return;

    const models = await apiGet(`/vehicle/models?year=${encodeURIComponent(y)}&make=${encodeURIComponent(m)}`);
    const choices = [
      { value: "", label: "Select a model", disabled: true, selected: true },
      ...models.map(mm => ({ value: mm, label: mm })),
    ];
    modelChoices.setChoices(choices, "value", "label", true);
  }

  async function loadCategories() {
    resetChoices(categoryChoices, "Select category");
    resetChoices(serviceChoices, "Select a service");

    // You can require year/make/model before categories if you want; for now just load
    const cats = await apiGet("/categories");
    // IMPORTANT: label must be the category name string, not the object -> avoids [object Object]
    const choices = [
      { value: "", label: "Select category", disabled: true, selected: true },
      ...cats.map(c => ({ value: c.key, label: c.name })),
    ];
    categoryChoices.setChoices(choices, "value", "label", true);
  }

  async function loadServices() {
    resetChoices(serviceChoices, "Select a service");

    const catKey = categoryEl.value;
    if (!catKey) return;

    const svcs = await apiGet(`/services/${encodeURIComponent(catKey)}`);
    const choices = [
      { value: "", label: "Select a service", disabled: true, selected: true },
      ...svcs.map(s => ({ value: String(s.code), label: String(s.name) })),
    ];
    serviceChoices.setChoices(choices, "value", "label", true);
  }

  // Wire up events
  yearEl.addEventListener("change", () => loadMakes().catch(e => setStatus(result, e.message, true)));
  makeEl.addEventListener("change", () => loadModels().catch(e => setStatus(result, e.message, true)));
  modelEl.addEventListener("change", () => loadCategories().catch(e => setStatus(result, e.message, true)));
  categoryEl.addEventListener("change", () => loadServices().catch(e => setStatus(result, e.message, true)));

  btn.addEventListener("click", async () => {
    try {
      setStatus(result, "Working...");
      const payload = {
        zip_code: zip.value || null,
        year: yearEl.value ? Number(yearEl.value) : null,
        make: makeEl.value || null,
        model: modelEl.value || null,
        category: categoryEl.value,
        service: serviceEl.value,
      };

      if (!payload.year || !payload.make || !payload.model || !payload.category || !payload.service) {
        setStatus(result, "Please select Year, Make, Model, Category, and Service.", true);
        return;
      }

      const data = await apiPost("/estimate", payload);
      setStatus(
        result,
        `${data.service_name}\nEstimated labor: $${data.estimate_low} – $${data.estimate_high} (rate $${data.labor_rate}/hr)`
      );
    } catch (e) {
      setStatus(result, e.message, true);
    }
  });

  // Initial load
  try {
    await loadYears();
    // Optional: pre-load categories (or wait until model selected)
    // await loadCategories();
    setStatus(result, "");
  } catch (e) {
    setStatus(result, e.message, true);
  }
});
