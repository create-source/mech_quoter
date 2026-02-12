const $ = (id) => document.getElementById(id);

let catalog = null;
let categories = [];
let servicesByCategory = new Map();

function money(n){
  const v = Number(n || 0);
  return v.toLocaleString(undefined, { style:"currency", currency:"USD" });
}

async function apiGet(url){
  const r = await fetch(url);
  if(!r.ok) throw new Error(`GET ${url} failed: ${r.status}`);
  return r.json();
}

function setOptions(selectEl, items, placeholder){
  selectEl.innerHTML = "";
  const ph = document.createElement("option");
  ph.value = "";
  ph.textContent = placeholder;
  selectEl.appendChild(ph);

  for(const it of items){
    const opt = document.createElement("option");
    opt.value = it.value;
    opt.textContent = it.label;
    selectEl.appendChild(opt);
  }
}

async function init(){
  try{
    // Years
    const years = await apiGet("/vehicle/years");
    setOptions($("year"), years.map(y => ({value:String(y), label:String(y)})), "Select year");

    // Catalog
    catalog = await apiGet("/catalog");
    $("laborRate").value = Number(catalog.labor_rate || 90);

    categories = (catalog.categories || []);
    for(const c of categories){
      servicesByCategory.set(c.key, c.services || []);
    }

    setOptions(
      $("category"),
      categories.map(c => ({value:c.key, label:c.name})),
      "Select category"
    );

    setOptions($("service"), [], "Select service");

    // Events
    $("year").addEventListener("change", onYear);
    $("make").addEventListener("change", onMake);
    $("category").addEventListener("change", onCategory);
    $("service").addEventListener("change", onService);
    $("estimateBtn").addEventListener("click", onEstimate);

  }catch(e){
    $("out").textContent = `UI init failed: ${e.message}`;
    console.error(e);
  }
}

async function onYear(){
  const year = $("year").value;
  setOptions($("make"), [], "Loading makes...");
  setOptions($("model"), [], "Select model");
  if(!year) return;

  const makes = await apiGet(`/vehicle/makes?year=${year}`);
  setOptions(
    $("make"),
    makes.map(m => ({value:m, label:m})),
    "Select make"
  );
}

async function onMake(){
  const year = $("year").value;
  const make = $("make").value;
  setOptions($("model"), [], "Loading models...");
  if(!year || !make) return;

  const models = await apiGet(`/vehicle/models?year=${year}&make=${make}`);
  setOptions(
    $("model"),
    models.map(m => ({value:m, label:m})),
    "Select model"
  );
}

function onCategory(){
  const key = $("category").value;
  const list = servicesByCategory.get(key) || [];

  setOptions(
    $("service"),
    list.map(s => ({value:s.code, label:s.name})),
    "Select service"
  );

  $("laborHours").value = "0";
}

function onService(){
  const catKey = $("category").value;
  const code = $("service").value;
  const list = servicesByCategory.get(catKey) || [];
  const svc = list.find(s => s.code === code);
  if(!svc) return;

  const min = Number(svc.labor_hours_min ?? 0);
  const max = Number(svc.labor_hours_max ?? min);
  const mid = (min + max) / 2;

  $("laborHours").value = mid.toFixed(1);
}

function onEstimate(){
  const hours = Number($("laborHours").value || 0);
  const rate = Number($("laborRate").value || 90);
  const parts = Number($("partsPrice").value || 0);

  const labor = hours * rate;
  const total = labor + parts;

  $("out").innerHTML = `
    <div><b>Labor:</b> ${money(labor)} (${hours.toFixed(1)} hrs @ $${rate}/hr)</div>
    <div><b>Parts:</b> ${money(parts)}</div>
    <div style="margin-top:6px;"><b>Total:</b> ${money(total)}</div>
  `;
}

window.addEventListener("DOMContentLoaded", init);
