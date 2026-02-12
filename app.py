from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# PDF
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io
from datetime import datetime


# -----------------------------
# Paths
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

INDEX_HTML = STATIC_DIR / "index.html"
MANIFEST_JSON = STATIC_DIR / "manifest.json"


# -----------------------------
# App
# -----------------------------
app = FastAPI(title="Auto Mechanic Estimate", version="1.0.0")

# If you’ll host frontend + backend together, this is fine.
# If your UI is hosted on another domain, add it to allow_origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static assets: /static/app.js, /static/styles.css, /static/sw.js, /static/icons/*
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# -----------------------------
# Data (replace with DB later)
# -----------------------------
# Keep make/model values normalized (simple strings)
MAKE_MODEL: Dict[str, List[str]] = {
    "Toyota": ["Camry", "Corolla", "Tacoma", "Tundra", "Sequoia", "RAV4", "Highlander"],
    "Honda": ["Civic", "Accord", "CR-V", "Pilot", "Odyssey"],
    "Ford": ["F-150", "Escape", "Explorer", "Mustang", "Ranger"],
    "Chevrolet": ["Silverado 1500", "Tahoe", "Suburban", "Malibu", "Equinox"],
    "Nissan": ["Altima", "Sentra", "Rogue", "Frontier", "Pathfinder"],
}

SERVICE_BASE_PRICE: Dict[str, int] = {
    "Oil Change": 79,
    "Brake Pads (Front)": 249,
    "Brake Pads (Rear)": 239,
    "Spark Plugs": 299,
    "Battery Replacement": 219,
    "Alternator Replacement": 699,
    "Starter Replacement": 649,
    "Diagnostic": 149,
}


# Example ZIP modifier (simple demo; swap to real logic later)
def zip_multiplier(zip_code: str) -> float:
    # Basic validation is done elsewhere; this is just a placeholder
    # You can customize by region (OC/LA/SD etc.)
    if zip_code.startswith("9"):  # much of CA/West
        return 1.10
    if zip_code.startswith("1") or zip_code.startswith("0"):  # Northeast-ish
        return 1.08
    return 1.00


def year_multiplier(year: int) -> float:
    # Older vehicles sometimes take longer / more surprises
    if year <= 2005:
        return 1.08
    if year >= 2020:
        return 1.05
    return 1.00


# -----------------------------
# Models
# -----------------------------
class EstimateRequest(BaseModel):
    make: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    year: int = Field(..., ge=1970, le=2035)
    zip: str = Field(..., min_length=5, max_length=10)
    service: str = Field(..., min_length=1)


class EstimateResponse(BaseModel):
    estimate: int
    currency: str = "USD"
    breakdown: Dict[str, float]


# -----------------------------
# Routes
# -----------------------------
@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    if not INDEX_HTML.exists():
        raise HTTPException(
            status_code=500,
            detail="Missing static/index.html. Create it in the static folder.",
        )
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(
        "static/manifest.webmanifest",
        media_type="application/manifest+json"
    )

@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


# ---------- Make/Model API ----------
@app.get("/api/makes")
def get_makes() -> List[str]:
    return sorted(MAKE_MODEL.keys())


@app.get("/api/models/{make}")
def get_models(make: str) -> List[str]:
    # Make matching should be exact to avoid surprises.
    if make not in MAKE_MODEL:
        raise HTTPException(status_code=404, detail=f"Make '{make}' not found")
    return sorted(MAKE_MODEL[make])


# ---------- Estimate ----------
@app.post("/estimate", response_model=EstimateResponse)
def estimate(req: EstimateRequest) -> EstimateResponse:
    # Validate make/model pair
    if req.make not in MAKE_MODEL:
        raise HTTPException(status_code=400, detail="Invalid make")

    if req.model not in MAKE_MODEL[req.make]:
        raise HTTPException(status_code=400, detail="Invalid model for selected make")

    if req.service not in SERVICE_BASE_PRICE:
        raise HTTPException(status_code=400, detail="Invalid service selection")

    # Normalize zip: allow '92647' or '92647-1234'
    zip5 = req.zip.strip()[:5]
    if not zip5.isdigit():
        raise HTTPException(status_code=400, detail="ZIP must start with 5 digits")

    base = float(SERVICE_BASE_PRICE[req.service])
    z = zip_multiplier(zip5)
    y = year_multiplier(req.year)

    subtotal = base * z * y

    # Round to nearest dollar
    final_price = int(round(subtotal))

    return EstimateResponse(
        estimate=final_price,
        breakdown={
            "base": base,
            "zip_multiplier": z,
            "year_multiplier": y,
            "subtotal": subtotal,
        },
    )


# ---------- PDF ----------
@app.post("/estimate/pdf")
def estimate_pdf(req: EstimateRequest) -> Response:
    # Reuse estimate logic
    est = estimate(req)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    # Simple clean PDF layout
    c.setTitle("Auto Mechanic Estimate")

    y = height - 72
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, "Auto Mechanic Estimate")
    y -= 24

    c.setFont("Helvetica", 11)
    c.drawString(72, y, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    y -= 24

    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Vehicle")
    y -= 16
    c.setFont("Helvetica", 11)
    c.drawString(72, y, f"{req.year} {req.make} {req.model}")
    y -= 24

    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Service")
    y -= 16
    c.setFont("Helvetica", 11)
    c.drawString(72, y, f"{req.service}")
    y -= 24

    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Location")
    y -= 16
    c.setFont("Helvetica", 11)
    c.drawString(72, y, f"ZIP: {req.zip}")
    y -= 24

    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Estimate")
    y -= 16
    c.setFont("Helvetica", 12)
    c.drawString(72, y, f"${est.estimate:,} {est.currency}")
    y -= 24

    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Breakdown")
    y -= 16
    c.setFont("Helvetica", 10)
    for k, v in est.breakdown.items():
        c.drawString(72, y, f"{k}: {v:.2f}" if isinstance(v, float) else f"{k}: {v}")
        y -= 14

    y -= 10
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(72, y, "Note: This is an estimate. Final pricing may vary after inspection.")

    c.showPage()
    c.save()

    buf.seek(0)
    pdf_bytes = buf.read()

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=estimate.pdf"},
    )


# -----------------------------
# Local run
# -----------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
