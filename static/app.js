// Repair Estimator UI (Customer + Owner)
// Owner mode: https://YOUR_URL/?mode=owner&pin=1234

const $ = (id) => document.getElementById(id);

const state = {
  catalog: null,
  estimate: null,
  approvalId: null,
  invoiceId: null,
  ownerMode: false,
  pin: null
};

function qp(name) {
  const u = new URL(window.location.href);
  return u.searchParams.get(name);
}

async function jget(url, opts={}) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`${r.status} ${r.statusText}: ${t}`);
  }
  return r.json();
}

async function jpost(url, body, opts={}) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    body: JSON.stringify(body)
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(`${r.status} ${r.statusText}: ${t}`);
  }
  return r.json();
}

function fmtMoney(n) {
  return `$${Number(n || 0).toFixed(2)}`;
}

function setOptions(sel, items, placeholder) {
  sel.innerHTML = "";
  const o0 = document.createElement("option");
  o0.value = "";
  o0.textContent = placeholder;
  sel.appendChild(o0);

  for (const it of items) {
    const o = document.createElement("option");
    if (typeof it === "string") {
      o.value = it;
      o.textContent = it;
    } else {
      o.value = it.value;
      o.textContent = it.label;
    }
    sel.appendChild(o);
  }
}

function wireSignature(canvasId, clearBtnId) {
  const canvas = $(canvasId);
  const clearBtn = $(clearBtnId);
  const ctx = canvas.getContext("2d");

  // High-DPI
  function resize() {
    const ratio = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    canvas.width = Math.round(rect.width * ratio);
    canvas.height = Math.round(rect.height * ratio);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.lineWidth = 2.5;
    ctx.lineCap = "round";
    ctx.strokeStyle = "rgba(234,240,255,0.95)";
  }
  resize();
  window.addEventListener("resize", resize);

  let drawing = false;
  let last = null;

  function pos(e) {
    const rect = canvas.getBoundingClientRect();
    const p = e.touches ? e.touches[0] : e;
    return { x: p.clientX - rect.left, y: p.clientY - rect.top };
  }

  function start(e) {
    drawing = true;
    last = pos(e);
    e.preventDefault();
  }
  function move(e) {
    if (!drawing) return;
    const p = pos(e);
    ctx.beginPath();
    ctx.moveTo(last.x, last.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    last = p;
    e.preventDefault();
  }
  function end(e) {
    drawing = false;
    last = null;
    e.preventDefault();
  }

  canvas.addEventListener("mousedown", start);
  canvas.addEventListener("mousemove", move);
  window.addEventListener("mouseup", end);

  canvas.addEventListener("touchstart", start, { passive: false });
  canvas.addEventListener("touchmove", move, { passive: false });
  window.addEventListener("touchend", end, { passive: false });

  clearBtn.addEventListener("click", () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  });

  function isEmpty() {
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    for (let i = 3; i < img.length; i += 4) {
      if (img[i] !== 0) return false;
    }
    return true;
  }

  function toDataURL() {
    // export at native resolution
    return canvas.toDataURL("image/png");
  }

  return { isEmpty, toDataURL };
}

async function init() {
  try {
    state.ownerMode = (qp("mode") === "owner");
    state.pin = qp("pin") || null;

    $("modeBadge").textContent = state.ownerMode ? "Owner Mode" : "Customer Mode";

    // Load years
    const years = await jget("/vehicle/years");
    setOptions($("year"), years.years.map(String), "Select year");

    // Load catalog once (Category->Service is client-side)
    state.catalog = await jget("/api/catalog");
    const cats = (state.catalog.categories || []).map(c => ({ value: c.key, label: c.name }));
    setOptions($("category"), cats, "Select category");

    // Owner mode panel
    if (state.ownerMode) {
      $("ownerCard").classList.remove("hidden");
      await refreshOwner();
    }

    // Wiring dependent selects
    $("year").addEventListener("change", onYear);
    $("make").addEventListener("change", onMake);
    $("category").addEventListener("change", onCategory);
    $("service").addEventListener("change", () => {});

    $("btnEstimate").addEventListener("click", onEstimate);

    // Signature pads
    const sig = wireSignature("sig", "sigClear");
    const paySig = wireSignature("paySig", "payClear");

    $("sigApprove").addEventListener("click", async () => {
      if (!state.estimate) return alert("Get an estimate first.");
      if (!$("custName").value.trim()) return alert("Customer name required.");
      if (sig.isEmpty()) return alert("Please sign in the box.");

      const res = await jpost("/api/approval", {
        customer_name: $("custName").value.trim(),
        customer_email: $("custEmail").value.trim(),
        customer_phone: $("custPhone").value.trim(),
        estimate: state.estimate,
        signature_data_url: sig.toDataURL()
      });

      state.approvalId = res.id;
      $("approvalOut").textContent =
        `APPROVED ✅\nApproval ID: ${state.approvalId}\n\n` +
        `Download PDF: /api/approval/${state.approvalId}/pdf\n\n` +
        `Next: Sign invoice for payment acknowledgement below.`;

      $("invoiceCard").classList.remove("hidden");
      $("invoiceOut").textContent = `Approval ID: ${state.approvalId}\nReady to sign invoice.`;

      if (state.ownerMode) await refreshOwner();
    });

    $("paySign").addEventListener("click", async () => {
      if (!state.approvalId) return alert("Approve the estimate first.");
      if (paySig.isEmpty()) return alert("Please sign in the invoice box.");

      const res = await jpost("/api/invoice", {
        approval_id: state.approvalId,
        payment_signature_data_url: paySig.toDataURL()
      });

      state.invoiceId = res.id;
      $("invoiceOut").textContent =
        `PAYMENT ACKNOWLEDGEMENT ✅\nInvoice ID: ${state.invoiceId}\n\n` +
        `Download PDF: /api/invoice/${state.invoiceId}/pdf`;

      if (state.ownerMode) await refreshOwner();
    });

  } catch (err) {
    console.error(err);
    alert("Failed to initialize UI. Check server logs / browser console.\n\n" + err.message);
  }
}

async function onYear() {
  $("make").disabled = true;
  $("model").disabled = true;
  setOptions($("make"), [], "Loading makes...");
  setOptions($("model"), [], "Select a model");

  const y = $("year").value;
  if (!y) {
    setOptions($("make"), [], "Select make");
    $("make").disabled = true;
    return;
  }

  const data = await jget(`/vehicle/makes?year=${encodeURIComponent(y)}`);
  setOptions($("make"), data.makes || [], "Select make");
  $("make").disabled = false;
}

async function onMake() {
  $("model").disabled = true;
  setOptions($("model"), [], "Loading models...");

  const y = $("year").value;
  const m = $("make").value;
  if (!y || !m) {
    setOptions($("model"), [], "Select a model");
    $("model").disabled = true;
    return;
  }

  const data = await jget(`/vehicle/models?year=${encodeURIComponent(y)}&make=${encodeURIComponent(m)}`);
  setOptions($("model"), data.models || [], "Select a model");
  $("model").disabled = false;
}

function onCategory() {
  const key = $("category").value;
  const cat = (state.catalog.categories || []).find(c => c.key === key);
  const services = (cat?.services || []).map(s => ({ value: s.code, label: s.name }));
  setOptions($("service"), services, "Select a service");
  $("service").disabled = !services.length;
}

async function onEstimate() {
  try {
    const zip = $("zip").value.trim();
    const year = $("year").value;
    const make = $("make").value;
    const model = $("model").value;
    const category_key = $("category").value;
    const service_code = $("service").value;
    const parts_price = $("parts").value;

    if (!zip || zip.length < 5) return alert("Enter a valid ZIP.");
    if (!year) return alert("Select a year.");
    if (!make) return alert("Select a make.");
    if (!model) return alert("Select a model.");
    if (!category_key) return alert("Select a category.");
    if (!service_code) return alert("Select a service.");

    state.estimate = await jpost("/api/estimate", {
      zip, year, make, model, category_key, service_code, parts_price
    });

    $("estimateCard").classList.remove("hidden");
    $("invoiceCard").classList.add("hidden");
    $("approvalOut").textContent = "";
    state.approvalId = null;
    state.invoiceId = null;

    const e = state.estimate;
    $("estimateOut").textContent =
      `Vehicle: ${e.vehicle.year} ${e.vehicle.make} ${e.vehicle.model}\n` +
      `ZIP: ${e.zip}\n` +
      `Service: ${e.category.name} — ${e.service.name}\n\n` +
      `Labor rate: ${fmtMoney(e.labor_rate)}/hr\n` +
      `Labor hours: ${e.labor_hours_min} – ${e.labor_hours_max}\n` +
      `Labor: ${fmtMoney(e.labor_cost_min)} – ${fmtMoney(e.labor_cost_max)}\n` +
      `Parts: ${fmtMoney(e.parts_price)}\n` +
      `TOTAL: ${fmtMoney(e.total_min)} – ${fmtMoney(e.total_max)}\n`;
  } catch (err) {
    console.error(err);
    alert("Estimate failed: " + err.message);
  }
}

async function refreshOwner() {
  if (!state.ownerMode) return;
  if (!state.pin) {
    $("ownerApprovals").textContent = "Owner mode requires ?pin=XXXX";
    $("ownerInvoices").textContent = "Owner mode requires ?pin=XXXX";
    return;
  }

  const hdrs = { "x-shop-pin": state.pin };

  try {
    const a = await jget(`/api/admin/approvals?pin=${encodeURIComponent(state.pin)}`, { headers: hdrs });
    const i = await jget(`/api/admin/invoices?pin=${encodeURIComponent(state.pin)}`, { headers: hdrs });

    $("ownerApprovals").textContent = (a.approvals || []).slice(0, 20).map(x =>
      `• ${x.id} | ${x.customer?.name || ""} | ${x.estimate?.vehicle?.year || ""} ${x.estimate?.vehicle?.make || ""} ${x.estimate?.vehicle?.model || ""}\n  PDF: /api/approval/${x.id}/pdf`
    ).join("\n\n") || "No approvals yet.";

    $("ownerInvoices").textContent = (i.invoices || []).slice(0, 20).map(x =>
      `• ${x.id} | approval ${x.approval_id}\n  PDF: /api/invoice/${x.id}/pdf`
    ).join("\n\n") || "No invoices yet.";

  } catch (err) {
    $("ownerApprovals").textContent = "Owner backend error: " + err.message;
    $("ownerInvoices").textContent = "Owner backend error: " + err.message;
  }
}

init();
