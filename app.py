from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


# ===============================
# PATHS
# ===============================
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_HTML = STATIC_DIR / "index.html"
CATALOG_PATH = BASE_DIR / "services_catalog.json"


# ===============================
# CONFIG
# ===============================
POPULAR_MAKES: List[str] = [
    "TOYOTA", "HONDA", "FORD", "CHEVROLET", "NISSAN", "HYUNDAI", "KIA", "DODGE", "JEEP",
    "GMC", "SUBARU", "BMW", "MERCEDES-BENZ", "VOLKSWAGEN", "AUDI", "LEXUS", "MAZDA",
    "TESLA", "VOLVO"
]

# Example service base prices (you can move this into services_catalog.json later)
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


# ===============================
# APP
# ===============================
app = FastAPI(title="Repair Estimator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static assets (app.js, style.css, icons, manifest file, etc.)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ===============================
# HELPERS
# ===============================
_catalog_cache: Optional[Dict[str, List[str]]] = None


def load_catalog() -> Dict[str, List[str]]:
    """
    Load make->models from services_catalog.json.
    Cached in-memory for speed.
    """
    global _catalog_cache

    if _catalog_cache is not None:
        return _catalog_cache

    if not CATALOG_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail="Missing services_catalog.json at project root.",
        )

    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invalid services_catalog.json: {e}")

    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="services_catalog.json must be a JSON object.")

    # Normalize keys to uppercase so it matches POPULAR_MAKES
    normalized: Dict[str, List[str]] = {}
    for k, v in data.items():
        key = str(k).strip().upper()
        if isinstance(v, list):
            normalized[key] = [str(m).strip() for m in v if str(m).strip()]
        else:
            normalized[key] = []

    _catalog_cache = normalized
    return normalized


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


def base_service_price(service: str) -> float:
    # If unknown, treat as 0 -> validation error
    return float(SERVICE_BASE_PRICE.get(service, 0))


# ===============================
# MODELS
# ===============================
class EstimateRequest(BaseModel):
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

    zip: Optional[str] = Field(default="00000", min_length=5, max_length=10)
    signatureDataUrl: Optional[str] = None


class EstimateResponse(BaseModel):
    estimate: int
    currency: str = "USD"
    breakdown: Dict[str, float]


# ===============================
# ROUTES
# ===============================
@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=500, detail="Missing static/index.html")
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


# Best-practice PWA: serve manifest at root URL (file stays in /static)
@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    p = STATIC_DIR / "manifest.webmanifest"
    if not p.exists():
        raise HTTPException(status_code=500, detail="Missing static/manifest.webmanifest")
    return FileResponse(str(p), media_type="application/manifest+json")


# Best-practice PWA: serve SW at root URL (file stays in /static)
@app.get("/sw.js")
def service_worker() -> FileResponse:
    p = STATIC_DIR / "sw.js"
    if not p.exists():
        raise HTTPException(status_code=500, detail="Missing static/sw.js")
    return FileResponse(
        str(p),
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/api/makes")
def get_makes() -> List[str]:
    # Keep the UI exactly "popular makes" (your list)
    return POPULAR_MAKES


@app.get("/api/models/{make}")
def get_models(make: str) -> List[str]:
    catalog = load_catalog()
    key = make.strip().upper()
    if key not in catalog:
        raise HTTPException(status_code=404, detail=f"Make '{make}' not found")
    return sorted(catalog[key])


@app.post("/estimate", response_model=EstimateResponse)
def estimate(req: EstimateRequest) -> EstimateResponse:
    catalog = load_catalog()

    make_key = req.make.strip().upper()
    if make_key not in catalog:
        raise HTTPException(status_code=400, detail="Invalid make")

    # Validate model exists for make (case-insensitive)
    models_upper = {m.upper(): m for m in catalog[make_key]}
    if req.model.strip().upper() not in models_upper:
        raise HTTPException(status_code=400, detail="Invalid model for selected make")

    base = base_service_price(req.service)
    if base <= 0:
        raise HTTPException(status_code=400, detail="Invalid service selection")

    labor = float(req.laborHours) * float(req.laborRate)
    parts = float(req.partsPrice)

    z = zip_multiplier(req.zip or "00000")
    y = year_multiplier(req.year)

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
    c.drawString(72, y, "Estimated Total")
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
