console.log("app.js loaded");

const yearSelect = document.getElementById("year");
const makeSelect = document.getElementById("make");
const modelSelect = document.getElementById("model");
const categorySelect = document.getElementById("category");
const serviceSelect = document.getElementById("service");

/* -----------------------------
   Helpers
-------------------------------- */
function resetSelect(select, placeholder, disabled = true) {
  select.innerHTML = "";
  const opt = document.createElement("option");
  opt.value = "";
  opt.textContent = placeholder;
  select.appendChild(opt);
  select.disabled = disabled;
}

function populateSelect(select, items) {
  items.forEach(item => {
    const opt = document.createElement("option");
    opt.value = item;
    opt.textContent = item;
    select.appendChild(opt);
  });
}

/* -----------------------------
   Load Years
-------------------------------- */
fetch("/vehicle/years")
  .then(res => res.json())
  .then(years => {
    populateSelect(yearSelect, years);
  })
  .catch(err => {
    console.error("Failed to load years:", err);
  });

/* -----------------------------
   Year → Makes
-------------------------------- */
yearSelect.addEventListener("change", () => {
  const year = yearSelect.value;

  resetSelect(makeSelect, "Select make");
  resetSelect(modelSelect, "Select model");
  resetSelect(categorySelect, "Select category");
  resetSelect(serviceSelect, "Select service");

  if (!year) return;

  fetch(`/vehicle/makes?year=${year}`)
    .then(res => res.json())
    .then(makes => {
      populateSelect(makeSelect, makes);
      makeSelect.disabled = false;
    })
    .catch(err => {
      console.error("Failed to load makes:", err);
    });
});

/* -----------------------------
   Make → Models
-------------------------------- */
makeSelect.addEventListener("change", () => {
  const year = yearSelect.value;
  const make = makeSelect.value;

  resetSelect(modelSelect, "Select model");
  resetSelect(categorySelect, "Select category");
  resetSelect(serviceSelect, "Select service");

  if (!year || !make) return;

  fetch(`/vehicle/models?year=${year}&make=${encodeURIComponent(make)}`)
    .then(res => res.json())
    .then(models => {
      populateSelect(modelSelect, models);
      modelSelect.disabled = false;
    })
    .catch(err => {
      console.error("Failed to load models:", err);
    });
});

/* -----------------------------
   Model → Categories
-------------------------------- */
modelSelect.addEventListener("change", () => {
  resetSelect(categorySelect, "Select category");
  resetSelect(serviceSelect, "Select service");

  if (!modelSelect.value) return;

  fetch("/categories")
    .then(res => res.json())
    .then(categories => {
      populateSelect(categorySelect, categories);
      categorySelect.disabled = false;
    })
    .catch(err => {
      console.error("Failed to load categories:", err);
    });
});

/* -----------------------------
   Category → Services
-------------------------------- */
categorySelect.addEventListener("change", () => {
  const category = categorySelect.value;

  resetSelect(serviceSelect, "Select service");

  if (!category) return;

  fetch(`/services?category=${encodeURIComponent(category)}`)
    .then(res => res.json())
    .then(services => {
      populateSelect(serviceSelect, services);
      serviceSelect.disabled = false;
    })
    .catch(err => {
      console.error("Failed to load services:", err);
    });
});

/* -----------------------------
   Estimate Button (placeholder)
-------------------------------- */
document.getElementById("estimateBtn").addEventListener("click", () => {
  if (
    !yearSelect.value ||
    !makeSelect.value ||
    !modelSelect.value ||
    !categorySelect.value ||
    !serviceSelect.value
  ) {
    alert("Please complete all fields.");
    return;
  }

  alert(
    `Estimate requested for:\n\n` +
    `${yearSelect.value} ${makeSelect.value} ${modelSelect.value}\n` +
    `Category: ${categorySelect.value}\n` +
    `Service: ${serviceSelect.value}`
  );
});
