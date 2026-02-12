function $(id) {
  return document.getElementById(id);
}

// Only attach listeners after DOM exists
window.addEventListener("DOMContentLoaded", () => {
  try {
    initUI();
  } catch (e) {
    console.error(e);
    const box = $("statusBox");
    if (box) box.textContent = `UI init failed: ${e.message}`;
  }
});

function must(id) {
  const el = $(id);
  if (!el) throw new Error(`Missing element #${id} in index.html`);
  return el;
}

async function initUI() {
  // ✅ ONLY reference elements that exist in the simplified UI
  const yearSel     = must("year");
  const makeSel     = must("make");
  const modelSel    = must("model");
  const categorySel = must("category");
  const serviceSel  = must("service");
  const laborHours  = must("laborHours");
  const partsPrice  = must("partsPrice");
  const laborRate   = must("laborRate");
  const notes       = must("notes");
  const estimateBtn = must("estimateBtn");

  estimateBtn.addEventListener("click", async () => {
    // your estimate logic here...
  });

  // load years, makes, models, categories, services...
}

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
    if(typeof it === "string"){
      opt.value = it;
      opt.textContent = it;
    }else{
      opt.value = it.value;
      opt.textContent = it.label;
    }
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

    categories = (catalog.categories || []).map(c => ({ key:c.key, name:c.name, services:c.services || [] }));
    for(const c of categories){
      servicesByCategory.set(c.key, c.services);
    }

    setOptions($("category"), categories.map(c => ({value:c.key, label:c.name})), "Select category");
    setOptions($("service"), [], "Select service");

    // Events
    $("year").addEventListener("change", onYear);
    $("make").addEventListener("change", onMake);
    $("category").addEventListener("change", onCategory);
    $("service").addEventListener("change", onService);
    $("calcBtn").addEventListener("click", onCalc);

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

  const res = await apiGet(`/vehicle/makes?year=${encodeURIComponent(year)}`);
  const makes = res.makes || [];
  setOptions($("make"), makes.map(m => ({value:m, label:m})), "Select make");
}

async function onMake(){
  const year = $("year").value;
  const make = $("make").value;
  setOptions($("model"), [], "Loading models...");
  if(!year || !make) return;

  const res = await apiGet(`/vehicle/models?year=${encodeURIComponent(year)}&make=${encodeURIComponent(make)}`);
  const models = res.models || [];
  setOptions($("model"), models.map(m => ({value:m, label:m})), "Select model");
}

function onCategory(){
  const key = $("category").value;
  const list = servicesByCategory.get(key) || [];
  setOptions($("service"), list.map(s => ({value:s.code, label:s.name})), "Select service");
  $("laborHours").value = "0";
}

function onService(){
  const catKey = $("category").value;
  const code = $("service").value;
  const list = servicesByCategory.get(catKey) || [];
  const svc = list.find(s => s.code === code);
  if(!svc) return;

  // auto-fill a midpoint labor hour
  const min = Number(svc.labor_hours_min ?? 0);
  const max = Number(svc.labor_hours_max ?? min);
  const mid = (min + max) / 2;
  $("laborHours").value = mid.toFixed(1);
}

function onCalc(){
  const hours = Number($("laborHours").value || 0);
  const rate = Number($("laborRate").value || 90);
  const parts = Number($("partsPrice").value || 0);

  const labor = hours * rate;
  const total = labor + parts;

  $("out").innerHTML = `
    <div><b>Labor:</b> ${money(labor)} (${hours.toFixed(1)} hrs @ ${money(rate)}/hr)</div>
    <div><b>Parts:</b> ${money(parts)}</div>
    <div style="margin-top:6px;"><b>Total:</b> ${money(total)}</div>
  `;
}

init();
