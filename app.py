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


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML = STATIC_DIR / "index.html"


app = FastAPI(title="Repair Estimator", version="1.0.0")

# If you serve everything from the same domain, you can tighten this later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static assets live at /static/*
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# -----------------------------
# Demo Data (replace with DB later)
# -----------------------------
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


def zip_multiplier(zip_code: str) -> float:
    z = (zip_code or "").strip()[:5]
    if len(z) == 5 and z.isdigit():
        if z.startswith("9"):
            return 1.10
        if z.startswith(("0", "1")):
            return 1.08
    return 1.00


def year_multiplier(year: int) -> float:
    if year <= 2005:
        return 1.08
    if year >= 2020:
        return 1.05
    return 1.00


# -----------------------------
# Request/Response Models
# -----------------------------
class EstimateRequest(BaseModel):
    # Keep these aligned with your app.js payload
    year: int = Field(..., ge=1970, le=2035)
    make: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    category: Optional[str] = None
    service: str = Field(..., min_length=1)

    laborHours: float = Field(0, ge=0)
    partsPrice: float = Field(0, ge=0)
    laborRate: float = Field(90, ge=0)

    notes: Optional[str] = None
    customerName: Optional[str] = None
    customerPhone: Optional[str] = None

    # Optional ZIP (if you later add it to UI)
    zip: Optional[str] = Field(default="00000", min_length=5, max_length=10)

    # Optional base64 signature (if your app.js sends it)
    signatureDataUrl: Optional[str] = None


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
        raise HTTPException(500, "Missing static/index.html")
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


# Serve manifest at ROOT for best PWA behavior (file remains in /static)
@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    p = STATIC_DIR / "manifest.webmanifest"
    if not p.exists():
        raise HTTPException(500, "Missing static/manifest.webmanifest")
    return FileResponse(str(p), media_type="application/manifest+json")


# Serve service worker at ROOT for best scope (file remains in /static)
@app.get("/sw.js")
def service_worker() -> FileResponse:
    p = STATIC_DIR / "sw.js"
    if not p.exists():
        raise HTTPException(500, "Missing static/sw.js")
    # Avoid aggressive caching of SW itself so updates apply reliably
    return FileResponse(
        str(p),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


# Make/Model endpoints (your app.js should call these)
@app.get("/api/makes")
def get_makes() -> List[str]:
    return sorted(MAKE_MODEL.keys())


@app.get("/api/models/{make}")
def get_models(make: str) -> List[str]:
    if make not in MAKE_MODEL:
        raise HTTPException(status_code=404, detail=f"Make '{make}' not found")
    return sorted(MAKE_MODEL[make])


@app.post("/estimate", response_model=EstimateResponse)
def estimate(req: EstimateRequest) -> EstimateResponse:
    if req.make not in MAKE_MODEL:
        raise HTTPException(status_code=400, detail="Invalid make")
    if req.model not in MAKE_MODEL[req.make]:
        raise HTTPException(status_code=400, detail="Invalid model for selected make")

    base_service = SERVICE_BASE_PRICE.get(req.service, 0)
    if base_service <= 0:
        # If you have categories/services from services_catalog.json, validate here later
        raise HTTPException(status_code=400, detail="Invalid service selection")

    # Simple total:
    # service base + (laborHours * laborRate) + partsPrice, modified by year/zip multipliers
    z = zip_multiplier(req.zip or "00000")
    y = year_multiplier(req.year)

    labor = float(req.laborHours or 0) * float(req.laborRate or 0)
    parts = float(req.partsPrice or 0)
    base = float(base_service)

    subtotal = (base + labor + parts) * z * y
    final_price = int(round(subtotal))

    return EstimateResponse(
        estimate=final_price,
        breakdown={
            "base_service": base,
            "labor": labor,
            "parts": parts,
            "zip_multiplier": z,
            "year_multiplier": y,
            "subtotal": subtotal,
        },
    )


@app.post("/estimate/pdf")
def estimate_pdf(req: EstimateRequest) -> Response:
    est = estimate(req)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    _, height = letter

    y = height - 72
    c.setTitle("Repair Estimate")

    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, "Repair Estimate")
    y -= 24

    c.setFont("Helvetica", 11)
    c.drawString(72, y, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    y -= 24

    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Vehicle")
    y -= 16
    c.setFont("Helvetica", 11)
    c.drawString(72, y, f"{req.year} {req.make} {req.model}")
    y -= 18

    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Service")
    y -= 16
    c.setFont("Helvetica", 11)
    c.drawString(72, y, req.service)
    y -= 18

    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Estimate")
    y -= 16
    c.setFont("Helvetica", 12)
    c.drawString(72, y, f"${est.estimate:,} {est.currency}")
    y -= 18

    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Breakdown")
    y -= 16
    c.setFont("Helvetica", 10)
    for k, v in est.breakdown.items():
        c.drawString(72, y, f"{k}: {v:.2f}")
        y -= 14

    y -= 8
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(72, y, "Note: This is an estimate. Final pricing may vary after inspection.")

    c.showPage()
    c.save()

    buf.seek(0)
    return Response(
        content=buf.read(),
        media_type="application/pdf",
        headers={"Content-Disposition": "inline; filename=estimate.pdf"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
