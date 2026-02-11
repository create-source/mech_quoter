/* global Choices */

const state = {
  choices: new Map(), // elementId -> Choices instance
};

function $(id) {
  return document.getElementById(id);
}

function setSelectOptions(selectEl, items, { valueFn, labelFn, placeholder }) {
  const prev = selectEl.value;

  selectEl.innerHTML = "";
  const ph = document.createElement("option");
  ph.value = "";
  ph.textContent = placeholder || "Select...";
  selectEl.appendChild(ph);

  for (const item of items) {
    const opt = document.createElement("option");
    opt.value = valueFn(item);
    opt.textContent = labelFn(item);
    selectEl.appendChild(opt);
  }

  // try to keep previous selection if still exists
  if ([...selectEl.options].some(o => o.value === prev)) {
    selectEl.value = prev;
  }

  refreshChoices(selectEl);
}

function refreshChoices(selectEl) {
  // If Choices exists, destroy and re-create (simple + reliable)
  const id = selectEl.id;
  if (state.choices.has(id)) {
    state.choices.get(id).destroy();
    state.choices.delete(id);
  }

  // Only apply if Choices is loaded
  if (window.Choices) {
    const inst = new Choices(selectEl, {
      searchEnabled: true,
      shouldSort: false,
      itemSelectText: "",
      allowHTML: false,
    });
    state.choices.set(id, inst);
  }
}

async function fetchJSON(url) {
  const res = await fetch(url, { headers: { "Accept": "application/json" } });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${url} -> ${res.status} ${res.statusText}: ${txt}`);
  }
  return res.json();
}

async function loadYears() {
  const years = await fetchJSON("/vehicle/years");
  setSelectOptions($("year"), years, {
    valueFn: y => String(y),
    labelFn: y => String(y),
    placeholder: "Select year",
  });
}

async function loadMakes() {
  const year = $("year").value;
  if (!year) {
    $("make").disabled = true;
    $("model").disabled = true;
    return;
  }
  $("make").disabled = false;

  const makes = await fetchJSON(`/vehicle/makes?year=${encodeURIComponent(year)}`);
  setSelectOptions($("make"), makes, {
    valueFn: m => m,
    labelFn: m => m,
    placeholder: "Select make",
  });

  // reset model whenever makes reload
  $("model").disabled = true;
  setSelectOptions($("model"), [], {
    valueFn: x => x,
    labelFn: x => x,
    placeholder: "Select a model",
  });
}

async function loadModels() {
  const year = $("year").value;
  const make = $("make").value;

  if (!year || !make) {
    $("model").disabled = true;
    return;
  }

  const models = await fetchJSON(
    `/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`
  );

  $("model").disabled = false;
  setSelectOptions($("model"), models, {
    valueFn: m => m,
    labelFn: m => m,
    placeholder: "Select a model",
  });
}

async function loadCategories() {
  // returns [{key,name,count}, ...]
  const cats = await fetchJSON("/categories");
  setSelectOptions($("category"), cats, {
    valueFn: c => c.key,
    labelFn: c => c.name,        // ✅ fixes [object Object]
    placeholder: "Select category",
  });

  // service depends on category
  $("service").disabled = true;
  setSelectOptions($("service"), [], {
    valueFn: x => x,
    labelFn: x => x,
    placeholder: "Select a service",
  });
}

async function loadServices() {
  const categoryKey = $("category").value;
  if (!categoryKey) {
    $("service").disabled = true;
    return;
  }

  const services = await fetchJSON(`/services/${encodeURIComponent(categoryKey)}`);
  $("service").disabled = false;

  setSelectOptions($("service"), services, {
    valueFn: s => s.code,
    labelFn: s => s.name,        // ✅ fixes [object Object]
    placeholder: "Select a service",
  });
}

async function runEstimate() {
  const zip = $("zip").value.trim();
  const category = $("category").value;
  const service = $("service").value;

  const resultEl = $("result");
  resultEl.textContent = "";

  if (!zip) return (resultEl.textContent = "Enter a ZIP code.");
  if (!category) return (resultEl.textContent = "Select a category.");
  if (!service) return (resultEl.textContent = "Select a service.");

  const res = await fetch("/estimate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ zip_code: zip, category, service }),
  });

  const data = await res.json();
  if (!res.ok) {
    resultEl.textContent = `Error: ${data.detail || JSON.stringify(data)}`;
    return;
  }

  resultEl.textContent =
    `Service: ${data.service_name}\n` +
    `Labor rate: ${data.labor_rate}\n` +
    `Low: ${data.estimate_low}\n` +
    `Mid: ${data.estimate_mid}\n` +
    `High: ${data.estimate_high}\n`;
}

function wireEvents() {
  $("year").addEventListener("change", async () => {
    try {
      await loadMakes();
    } catch (e) {
      console.error(e);
      $("result").textContent = String(e);
    }
  });

  $("make").addEventListener("change", async () => {
    try {
      await loadModels();
    } catch (e) {
      console.error(e);
      $("result").textContent = String(e);
    }
  });

  $("category").addEventListener("change", async () => {
    try {
      await loadServices();
    } catch (e) {
      console.error(e);
      $("result").textContent = String(e);
    }
  });

  $("btnEstimate").addEventListener("click", async () => {
    try {
      await runEstimate();
    } catch (e) {
      console.error(e);
      $("result").textContent = String(e);
    }
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    // init Choices on empty selects (optional)
    ["year", "make", "model", "category", "service"].forEach(id => refreshChoices($(id)));

    wireEvents();

    await loadYears();
    await loadCategories();

    // makes/models depend on year/make choices; keep disabled until selection
    $("make").disabled = true;
    $("model").disabled = true;
    $("service").disabled = true;
  } catch (e) {
    console.error(e);
    $("result").textContent = String(e);
  }
});
