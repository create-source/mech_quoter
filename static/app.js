const fmt = (n) =>
  (typeof n === "number" && isFinite(n))
    ? n.toLocaleString("en-US")
    : n;

const money = (n) =>
  (typeof n === "number" && isFinite(n))
    ? `$${Math.round(n).toLocaleString("en-US")}`
    : "—";

const hours = (a, b) =>
  (typeof a === "number" && typeof b === "number")
    ? `${a}–${b} hr`
    : "—";

const modeLabel = (m) => (m === "flat" ? "Flat-rate" : "Hourly");

resultEl.innerHTML = `
  <div class="estimate-card">
    <div class="estimate-top">
      <div class="svc-name">${data.service_name ?? "Estimate"}</div>
      <div class="svc-range">${money(data.estimate_low)} <span class="muted">–</span> ${money(data.estimate_high)}</div>
    </div>

    <div class="estimate-grid">
      <div class="kpi">
        <div class="k">Mode</div>
        <div class="v">${modeLabel(data.pricing_mode)}</div>
      </div>
      <div class="kpi">
        <div class="k">Labor rate</div>
        <div class="v">$${fmt(data.labor_rate)}/hr</div>
      </div>
      <div class="kpi">
        <div class="k">Labor hours</div>
        <div class="v">${hours(data.labor_hours_min, data.labor_hours_max)}</div>
      </div>
      <div class="kpi">
        <div class="k">Multiplier</div>
        <div class="v">${fmt(data.vehicle_multiplier)}×</div>
      </div>
      <div class="kpi">
        <div class="k">Parts</div>
        <div class="v">${money(data.parts_price)}</div>
      </div>
      <div class="kpi">
        <div class="k">Parts tax</div>
        <div class="v">${money(data.parts_tax)}</div>
      </div>
    </div>
  </div>
`;
