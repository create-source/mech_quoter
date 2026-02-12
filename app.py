from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
    "TESLA", "VOLVO",
]

# Base services (stable fallback; move into JSON later if you want)
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

# If serving UI + API from same domain, you can remove CORS entirely.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production domain later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static assets: /static/*
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ===============================
# CATALOG LOADER (auto-reload on file change)
# ===============================
_catalog_cache: Optional[Dict[str, List[str]]] = None
_catalog_mtime: Optional[float] = None


def _normalize_catalog(data: dict) -> Dict[str, List[str]]:
    normalized: Dict[str, List[str]] = {}
    for k, v in data.items():
        key = str(k).strip().upper()
        if isinstance(v, list):
            normalized[key] = [str(m).strip() for m in v if str(m).strip()]
        else:
            normalized[key] = []
    return normalized


def load_catalog() -> Dict[str, List[str]]:
    """
    Load make->models from services_catalog.json.
    Caches in memory, and reloads automatically if the file changes.
    """
    global _catalog_cache, _catalog_mtime

    if not CATALOG_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail="Missing services_catalog.json at project root (same folder as app.py).",
        )

    mtime = CATALOG_PATH.stat().st_mtime
    if _catalog_cache is not None and _catalog_mtime == mtime:
        return _catalog_cache

    try:
        raw = CATALOG_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invalid services_catalog.json: {e}")

    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="services_catalog.json must be a JSON object mapping make->models[]")

    _catalog_cache = _normalize_catalog(data)
    _catalog_mtime = mtime
    return _catalog_cache


# ===============================
# PRICING HELPERS
# ===============================
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
    return float(SERVICE_BASE_PRICE.get(service, 0))


def validate_make_model(make: str, model: str, catalog: Dict[str, List[str]]) -> Tuple[str, str]:
    make_key = (make or "").strip().upper()
    if not make_key:
        raise HTTPException(status_code=400, detail="Make is required")

    if make_key not in catalog:
        raise HTTPException(status_code=400, detail=f"Invalid make: {make}")

    model_in = (model or "").strip()
    if not model_in:
        raise HTTPException(status_code=400, detail="Model is required")

    # Case-insensitive model check
    allowed = catalog[make_key]
    allowed_upper = {m.upper(): m for m in allowed}
    if model_in.upper() not in allowed_upper:
        raise HTTPException(status_code=400, detail=f"Invalid model '{model}' for make '{make}'")

    # Return normalized make/model
    return make_key, allowed_upper[model_in.upper()]


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
# STARTUP CHECKS (fail fast)
# ===============================
@app.on_event("startup")
def _startup_checks() -> None:
    if not STATIC_DIR.exists():
        raise RuntimeError(f"Missing folder: {STATIC_DIR}")

    if not INDEX_HTML.exists():
        raise RuntimeError("Missing static/index.html")

    # Optional but recommended
    mw = STATIC_DIR / "manifest.webmanifest"
    sw = STATIC_DIR / "sw.js"
    if not mw.exists():
        print("WARNING: static/manifest.webmanifest is missing (PWA install will not work).")
    if not sw.exists():
        print("WARNING: static/sw.js is missing (offline/install will not work).")

    # Validate catalog loads
    _ = load_catalog()


# ===============================
# ROUTES
# ===============================
@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    """
    Serve manifest at root for best PWA behavior.
    File lives in /static/manifest.webmanifest.
    """
    p = STATIC_DIR / "manifest.webmanifest"
    if not p.exists():
        raise HTTPException(status_code=500, detail="Missing static/manifest.webmanifest")
    return FileResponse(
        str(p),
        media_type="application/manifest+json",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/sw.js")
def service_worker() -> FileResponse:
    """
    Serve SW at root so scope covers the whole site.
    File lives in /static/sw.js.
    """
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
    return POPULAR_MAKES


@app.get("/api/models/{make}")
def get_models(make: str) -> List[str]:
    catalog = load_catalog()
    key = (make or "").strip().upper()
    if key not in catalog:
        raise HTTPException(status_code=404, detail=f"Make '{make}' not found")
    return sorted(catalog[key])


@app.post("/estimate", response_model=EstimateResponse)
def estimate(req: EstimateRequest) -> EstimateResponse:
    catalog = load_catalog()

    make_key, model_norm = validate_make_model(req.make, req.model, catalog)

    base = base_service_price(req.service)
    if base <= 0:
        raise HTTPException(status_code=400, detail=f"Invalid service selection: {req.service}")

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
    c.drawString(72, y, f"{req.year} {make_key} {model_norm}")
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
