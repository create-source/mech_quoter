document.addEventListener("DOMContentLoaded", async () => {
  const yearEl = document.getElementById("year");
  const makeEl = document.getElementById("make");
  const modelEl = document.getElementById("model");

  const setOptions = (select, items, placeholder) => {
    select.innerHTML = "";
    const ph = document.createElement("option");
    ph.value = "";
    ph.textContent = placeholder;
    select.appendChild(ph);

    items.forEach(v => {
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      select.appendChild(opt);
    });
  };

  let catalog = {};

  try {
    // Load all vehicle data once
    const res = await fetch("/catalog");
    catalog = await res.json();
    console.log("Catalog loaded:", catalog);
  } catch (err) {
    console.error("Failed to load catalog:", err);
    return;
  }

  // Populate Years
  try {
    const res = await fetch("/years");
    const years = await res.json();
    setOptions(yearEl, years, "Select year");
  } catch (err) {
    console.error("Failed to load years:", err);
  }

  // When Year changes → load Makes
  yearEl.addEventListener("change", () => {
    const year = yearEl.value;
    setOptions(makeEl, [], "Select make");
    setOptions(modelEl, [], "Select model");

    if (!year || !catalog[year]) return;

    const makes = Object.keys(catalog[year]);
    setOptions(makeEl, makes, "Select make");
  });

  // When Make changes → load Models
  makeEl.addEventListener("change", () => {
    const year = yearEl.value;
    const make = makeEl.value;
    setOptions(modelEl, [], "Select model");

    if (!year || !make || !catalog[year][make]) return;

    const models = catalog[year][make];
    setOptions(modelEl, models, "Select model");
  });
});
