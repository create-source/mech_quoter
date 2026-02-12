function $(id) { return document.getElementById(id); }

function setOptions(select, items, placeholder) {
  select.innerHTML = "";
  const ph = document.createElement("option");
  ph.value = "";
  ph.textContent = placeholder;
  select.appendChild(ph);

  for (const item of items) {
    const opt = document.createElement("option");
    if (typeof item === "string") {
      opt.value = item;
      opt.textContent = item;
    } else {
      opt.value = item.value;
      opt.textContent = item.label;
    }
    select.appendChild(opt);
  }
}

async function apiGet(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

let CATALOG = null;

function money(n) {
  const v = Number(n || 0);
  return v.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

function showStatus(html) {
  $("statusBox").innerHTML = html;
}

async function init() {
  // Grab elements safely
  const yearEl = $("year");
  const makeEl = $("make");
  const modelEl = $("model");
  const catEl = $("category");
  const svcEl = $("service");
  const laborHoursEl = $("laborHours");
  const partsPriceEl = $("partsPrice");
  const laborRateEl = $("laborRate");
  const btn = $("estimateBtn");

  if (!yearEl || !makeEl || !modelEl || !catEl || !svcEl || !btn) {
    showStatus("UI init failed: missing required fields in index.html");
    return;
  }

  // Load years
  const years = await apiGet("/vehicle/years");
  setOptions(yearEl, years.map(String), "Select year");

  // Load catalog + categories
  CATALOG = await apiGet("/catalog");
  laborRateEl.value = Number(CATALOG?.labor_rate || 90);

  const categories = (CATALOG?.categories || []).map(c => ({ value: c.key, label: c.name }));
  setOptions(catEl, categories, "Select category");
  setOptions(svcEl, [], "Select service");

  // Year -> makes
  yearEl.addEventListener("change", async () => {
    const year = yearEl.value;
    setOptions(makeEl, [], "Loading makes...");
    setOptions(modelEl, [], "Select model");
    if (!year) {
      setOptions(makeEl, [], "Select make");
      return;
    }
    const data = await apiGet(`/vehicle/makes?year=${encodeURIComponent(year)}`);
    setOptions(makeEl, data.makes || [], "Select make");
  });

  // Make -> models
  makeEl.addEventListener("change", async () => {
    const year = yearEl.value;
    const make = makeEl.value;
    setOptions(modelEl, [], "Loading models...");
    if (!year || !make) {
      setOptions(modelEl, [], "Select model");
      return;
    }
    const data = await apiGet(`/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`);
    setOptions(modelEl, data.models || [], "Select model");
  });

  // Category -> services
  catEl.addEventListener("change", () => {
    const key = catEl.value;
    const cat = (CATALOG?.categories || []).find(c => c.key === key);
    const services = (cat?.services || []).map(s => ({ value: s.code, label: s.name }));
    setOptions(svcEl, services, "Select service");
    laborHoursEl.value = 0;
  });

  // Service -> auto-fill labor hours (avg of min/max)
  svcEl.addEventListener("change", () => {
    const catKey = catEl.value;
    const svcCode = svcEl.value;
    const cat = (CATALOG?.categories || []).find(c => c.key === catKey);
    const svc = (cat?.services || []).find(s => s.code === svcCode);
    if (svc) {
      const min = Number(svc.labor_hours_min ?? 0);
      const max = Number(svc.labor_hours_max ?? min);
      const avg = (min + max) / 2;
      laborHoursEl.value = avg.toFixed(1);
    }
  });

  // Button
  btn.addEventListener("click", () => {
    const laborHours = Number(laborHoursEl.value || 0);
    const parts = Number(partsPriceEl.value || 0);
    const rate = Number(laborRateEl.value || 0);

    const labor = laborHours * rate;
    const total = labor + parts;

    showStatus(`
      <div class="result">
        <div><strong>Labor:</strong> ${money(labor)} (${laborHours.toFixed(1)} hrs @ ${money(rate)}/hr)</div>
        <div><strong>Parts:</strong> ${money(parts)}</div>
        <div class="total"><strong>Total:</strong> ${money(total)}</div>
      </div>
    `);
  });

  // Nice defaults
  setOptions(makeEl, [], "Select make");
  setOptions(modelEl, [], "Select model");
  showStatus("");
}

window.addEventListener("DOMContentLoaded", () => {
  init().catch(err => {
    console.error(err);
    showStatus(`UI init failed: ${err.message}`);
  });
});
