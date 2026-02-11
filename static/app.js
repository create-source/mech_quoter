const $ = (id) => document.getElementById(id);

async function apiGet(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path} failed: ${r.status}`);
  return await r.json();
}

async function apiPost(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path} failed: ${r.status}`);
  return await r.json();
}

let CATALOG = null;

function setStatus(msg) { $("status").textContent = msg || ""; }

function fillSelect(sel, items, placeholder) {
  sel.innerHTML = "";
  const ph = document.createElement("option");
  ph.value = "";
  ph.textContent = placeholder;
  sel.appendChild(ph);

  for (const it of items) {
    const opt = document.createElement("option");
    if (typeof it === "string") {
      opt.value = it;
      opt.textContent = it;
    } else {
      opt.value = it.value;
      opt.textContent = it.label;
    }
    sel.appendChild(opt);
  }
}

function money(n){ return `$${Number(n).toFixed(2)}`; }

function currentServiceObj() {
  const catKey = $("category").value;
  const svcCode = $("service").value;
  const cat = (CATALOG?.categories || []).find(c => c.key === catKey);
  if (!cat) return null;
  return (cat.services || []).find(s => s.code === svcCode) || null;
}

async function init() {
  setStatus("Loading…");

  // Load years
  const years = await apiGet("/vehicle/years");
  fillSelect($("year"), years.map(String), "Choose year");

  // Load catalog
  CATALOG = await apiGet("/catalog");
  $("laborRate").value = CATALOG.labor_rate ?? 90;

  // Categories
  const cats = (CATALOG.categories || []).map(c => ({ value: c.key, label: c.name }));
  fillSelect($("category"), cats, "Choose category");

  setStatus("");

  // Hooks
  $("year").addEventListener("change", onYear);
  $("make").addEventListener("change", onMake);
  $("category").addEventListener("change", onCategory);
  $("service").addEventListener("change", onService);
  $("btnEstimate").addEventListener("click", onEstimate);
}

async function onYear() {
  $("make").disabled = true;
  $("model").disabled = true;
  fillSelect($("make"), [], "Choose make");
  fillSelect($("model"), [], "Choose model");

  const year = $("year").value;
  if (!year) return;

  setStatus("Loading makes…");
  const makes = await apiGet(`/vehicle/makes?year=${encodeURIComponent(year)}`);
  fillSelect($("make"), makes, "Choose make");
  $("make").disabled = false;
  setStatus("");
}

async function onMake() {
  $("model").disabled = true;
  fillSelect($("model"), [], "Choose model");

  const year = $("year").value;
  const make = $("make").value;
  if (!year || !make) return;

  setStatus("Loading models…");
  const models = await apiGet(`/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`);
  fillSelect($("model"), models, "Choose model");
  $("model").disabled = false;
  setStatus("");
}

function onCategory() {
  $("service").disabled = true;
  fillSelect($("service"), [], "Choose service");

  const catKey = $("category").value;
  if (!catKey) return;

  const cat = (CATALOG.categories || []).find(c => c.key === catKey);
  const svcs = (cat?.services || []).map(s => ({ value: s.code, label: s.name }));
  fillSelect($("service"), svcs, "Choose service");
  $("service").disabled = false;

  $("laborHours").value = 0;
}

function onService() {
  const svc = currentServiceObj();
  if (!svc) return;

  // default labor hours to the midpoint
  const min = Number(svc.labor_hours_min ?? 0);
  const max = Number(svc.labor_hours_max ?? min);
  const mid = (min + max) / 2;
  $("laborHours").value = (Math.round(mid * 10) / 10).toFixed(1);
}

async function onEstimate() {
  try {
    setStatus("");

    const year = $("year").value;
    const make = $("make").value;
    const model = $("model").value;
    const catKey = $("category").value;
    const svcCode = $("service").value;

    if (!year || !make || !model) throw new Error("Select Year, Make, and Model.");
    if (!catKey || !svcCode) throw new Error("Select Category and Service.");

    const svc = currentServiceObj();
    if (!svc) throw new Error("Service not found in catalog.");

    const laborRate = Number($("laborRate").value || 0);
    const laborHours = Number($("laborHours").value || 0);
    const partsPrice = Number($("partsPrice").value || 0);

    const laborCost = laborRate * laborHours;
    const subtotal = laborCost + partsPrice;

    const payload = {
      vehicle: { year, make, model },
      category_key: catKey,
      service_code: svcCode,
      service_name: svc.name,
      labor_rate: laborRate,
      labor_hours: laborHours,
      parts_price: partsPrice,
      totals: { labor_cost: laborCost, subtotal },
      notes: $("notes").value || ""
    };

    // Save (optional) – if you don’t want saving, comment these 2 lines out
    const saved = await apiPost("/estimate", payload);
    payload.id = saved.id;

    const out = `
      <div><b>Estimate #${payload.id}</b></div>
      <div><b>Vehicle:</b> ${year} ${make} ${model}</div>
      <div><b>Service:</b> ${svc.name}</div>
      <div><b>Labor:</b> ${laborHours.toFixed(1)} hr × ${money(laborRate)} = ${money(laborCost)}</div>
      <div><b>Parts:</b> ${money(partsPrice)}</div>
      <div style="margin-top:8px"><b>Total:</b> ${money(subtotal)}</div>
    `.trim();

    $("result").style.display = "block";
    $("result").innerHTML = out;
    setStatus("Saved.");
  } catch (e) {
    $("result").style.display = "none";
    setStatus(e.message || String(e));
  }
}

init().catch(err => {
  console.error(err);
  setStatus("Failed to initialize UI. Check server logs.");
});
