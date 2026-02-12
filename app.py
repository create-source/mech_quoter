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


# -----------------------------
# App
# -----------------------------
app = FastAPI(title="Auto Mechanic Estimate", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve /static/*
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# -----------------------------
# Data (replace with DB later)
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


# -----------------------------
# Helpers
# -----------------------------
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
# Models
# -----------------------------
class EstimateRequest(BaseModel):
    make: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    year: int = Field(..., ge=1970, le=2035)
    # Make ZIP optional so your UI doesn't 422 if zip isn't present yet
    zip: Optional[str] = Field(default="00000", min_length=5, max_length=10)
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
        raise HTTPException(500, "Missing static/index.html")
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


# Serve manifest at a clean root URL (so your HTML can use /manifest.webmanifest)
@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    p = STATIC_DIR / "manifest.webmanifest"
    if not p.exists():
        raise HTTPException(500, "Missing static/manifest.webmanifest")
    return FileResponse(str(p), media_type="application/manifest+json")


# OPTIONAL: serve service worker at root too, if your index.html registers "/sw.js"
# If your index.html registers "/static/sw.js", you can delete this route.
@app.get("/sw.js")
def service_worker() -> FileResponse:
    p = STATIC_DIR / "sw.js"
    if not p.exists():
        raise HTTPException(500, "Missing static/sw.js")
    return FileResponse(str(p), media_type="application/javascript")


@app.get("/health")
def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


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

    if req.service not in SERVICE_BASE_PRICE:
        raise HTTPException(status_code=400, detail="Invalid service selection")

    zip5 = (req.zip or "00000").strip()[:5]
    base = float(SERVICE_BASE_PRICE[req.service])
    z = zip_multiplier(zip5)
    y = year_multiplier(req.year)

    subtotal = base * z * y
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


@app.post("/estimate/pdf")
def estimate_pdf(req: EstimateRequest)_
