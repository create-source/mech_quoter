// ===============================
// SERVICE WORKER REGISTRATION
// ===============================
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/static/sw.js")
      .then(() => console.log("Service Worker registered"))
      .catch((err) => console.error("SW registration failed:", err));
  });
}

// ===============================
// GLOBALS
// ===============================
const makeSelect = document.getElementById("make");
const modelSelect = document.getElementById("model");
const estimateForm = document.getElementById("estimateForm");
const downloadBtn = document.getElementById("downloadPdf");

// ===============================
// LOAD MAKES
// ===============================
async function loadMakes() {
  try {
    const res = await fetch("/api/makes");
    const makes = await res.json();

    makeSelect.innerHTML = `<option value="">Select Make</option>`;

    makes.forEach((make) => {
      const option = document.createElement("option");
      option.value = make;
      option.textContent = make;
      makeSelect.appendChild(option);
    });

  } catch (error) {
    console.error("Error loading makes:", error);
  }
}

// ===============================
// LOAD MODELS
// ===============================
async function loadModels(make) {
  try {
    const res = await fetch(`/api/models/${make}`);
    const models = await res.json();

    modelSelect.innerHTML = `<option value="">Select Model</option>`;

    models.forEach((model) => {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = model;
      modelSelect.appendChild(option);
    });

  } catch (error) {
    console.error("Error loading models:", error);
  }
}

// ===============================
// EVENT: MAKE CHANGE
// ===============================
makeSelect.addEventListener("change", (e) => {
  const selectedMake = e.target.value;

  modelSelect.innerHTML = `<option value="">Loading...</option>`;

  if (selectedMake) {
    loadModels(selectedMake);
  } else {
    modelSelect.innerHTML = `<option value="">Select Model</option>`;
  }
});

// ===============================
// SUBMIT ESTIMATE
// ===============================
estimateForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const formData = new FormData(estimateForm);

  const data = {
    make: formData.get("make"),
    model: formData.get("model"),
    year: formData.get("year"),
    zip: formData.get("zip"),
    service: formData.get("service"),
  };

  try {
    const res = await fetch("/estimate", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });

    const result = await res.json();

    alert(`Estimated Cost: $${result.estimate}`);

  } catch (error) {
    console.error("Estimate error:", error);
    alert("Something went wrong. Please try again.");
  }
});

// ===============================
// DOWNLOAD PDF
// ===============================
downloadBtn.addEventListener("click", async () => {
  const formData = new FormData(estimateForm);

  const data = {
    make: formData.get("make"),
    model: formData.get("model"),
    year: formData.get("year"),
    zip: formData.get("zip"),
    service: formData.get("service"),
  };

  try {
    const res = await fetch("/estimate/pdf", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(data),
    });

    if (!res.ok) throw new Error("PDF failed");

    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);

    const a = document.createElement("a");
    a.href = url;
    a.download = "estimate.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();

    window.URL.revokeObjectURL(url);

  } catch (error) {
    console.error("PDF error:", error);
    alert("Could not generate PDF.");
  }
});

// ===============================
// INIT
// ===============================
document.addEventListener("DOMContentLoaded", () => {
  loadMakes();
});
