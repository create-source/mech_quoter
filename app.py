from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="Repair Estimator")

# ---------- Paths / static ----------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
else:
    # fallback: if you put index.html/style.css/app.js next to app.py
    app.mount("/static", StaticFiles(directory=str(BASE_DIR)), name="static")


@app.get("/", include_in_schema=False)
def home():
    # Prefer static/index.html; fallback to ./index.html
    if (STATIC_DIR / "index.html").exists():
        return FileResponse(STATIC_DIR / "index.html")
    if (BASE_DIR / "index.html").exists():
        return FileResponse(BASE_DIR / "index.html")
    raise HTTPException(
        status_code=404,
        detail="index.html not found (expected in ./static or next to app.py)",
    )


@app.get("/manifest.json", include_in_schema=False)
def manifest():
    if (STATIC_DIR / "manifest.json").exists():
        return FileResponse(STATIC_DIR / "manifest.json")
    if (BASE_DIR / "manifest.json").exists():
        return FileResponse(BASE_DIR / "manifest.json")
    raise HTTPException(status_code=404, detail="manifest.json not found")


# ---------- Config ----------
DEFAULT_LABOR_RATE = 90.0  # you asked for $90/hr

# Optional: override by ZIP if you want (leave empty if not using)
LABOR_RATE_BY_ZIP: Dict[str, float] = {
    # "92646": 90.0,
}

PARTS_TAX_RATE = 0.0775  # edit anytime


# ---------- Vehicle (NHTSA vPIC) ----------
VPIC_BASE = "https://vpic.nhtsa.dot.gov/api/vehicles"


@app.get("/vehicle/years")
def vehicle_years():
    # Simple range for UX
    return list(range(1981, 2026))[::-1]


@app.get("/vehicle/makes")
async def vehicle_makes(year: int):
    """
    Returns *filtered* popular makes for the selected year.
    If you want the full list, remove the POPULAR_MAKES filter.
    """
    url = f"{VPIC_BASE}/GetMakesForModelYear/modelyear/{year}?format=json"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()

    makes = sorted(
        {
            (i.get("MakeName") or "").strip().upper()
            for i in data.get("Results", [])
            if i.get("MakeName")
        }
    )

    POPULAR_MAKES = {
        "ACURA",
        "AUDI",
        "BMW",
        "BUICK",
        "CADILLAC",
        "CHEVROLET",
        "CHRYSLER",
        "DODGE",
        "FIAT",
        "FORD",
        "GMC",
        "HONDA",
        "HYUNDAI",
        "INFINITI",
        "JEEP",
        "KIA",
        "LEXUS",
        "LINCOLN",
        "MAZDA",
        "MERCEDES-BENZ",
        "MINI",
        "MITSUBISHI",
        "NISSAN",
        "RAM",
        "SUBARU",
        "TESLA",
        "TOYOTA",
        "VOLKSWAGEN",
        "VOLVO",
        "PORSCHE",
        "LAND ROVER",
        "JAGUAR",
    }

    filtered = [m for m in makes if m in POPULAR_MAKES]
    return filtered or makes  # fallback if filter returns nothing


@app.get("/vehicle/models")
async def vehicle_models(year: int, make: str):
    make_clean = make.strip()
    url = f"{VPIC_BASE}/GetModelsForMakeYear/make/{make_clean}/modelyear/{year}?format=json"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()

    models = sorted(
        {(i.get("Model_Name") or "").strip() for i in data.get("Results", []) if i.get("Model_Name")}
    )
    return models


# ---------- Catalog (categories + services) ----------
CATALOG_PATH = BASE_DIR / "services_catalog.json"


def load_catalog() -> Dict[str, Any]:
    if not CATALOG_PATH.exists():
        raise RuntimeError(f"Missing {CATALOG_PATH.name} next to app.py")
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def get_catalog() -> Dict[str, Any]:
    # lightweight cache
    if not hasattr(get_catalog, "_cache"):
        setattr(get_catalog, "_cache", load_catalog())
    return getattr(get_catalog, "_cache")


def find_category(category_key: str) -> Optional[Dict[str, Any]]:
    cat_key = (category_key or "").strip()
    for c in get_catalog().get("categories", []):
        if c.get("key") == cat_key:
            return c
    return None


def find_service(category_key: str, service_code: str) -> Optional[Dict[str, Any]]:
    cat = find_category(category_key)
    if not cat:
        return None
    code = (service_code or "").strip()
    for s in cat.get("services", []):
        if s.get("code") == code:
            return s
    return None


@app.get("/categories")
def categories():
    cats = get_catalog().get("categories", [])
    return [
        {"key": c.get("key"), "name": c.get("name"), "count": len(c.get("services", []) or [])}
        for c in cats
        if c.get("key") and c.get("name")
    ]


@app.get("/services/{category_key}")
def services_for_category(category_key: str):
    cat = find_category(category_key)
    if not cat:
        raise HTTPException(status_code=404, detail=f"Unknown category: {category_key}")
    return cat.get("services", []) or []


# ---------- Estimating ----------
class EstimateRequest(BaseModel):
    zip_code: str = Field(default="92646")
    category: str
    service: str
    parts_price: float = Field(default=0, ge=0)
    pricing_mode: str = Field(default="hourly")  # "hourly" or "flat"

    # optional vehicle context (used for multipliers later)
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None


def infer_vehicle_multiplier(year: Optional[int], make: Optional[str], model: Optional[str]) -> float:
    """
    Simple heuristics:
      sedan/hatch/coupe: 1.00
      suv/crossover:     1.10
      truck:             1.20
      van:               1.10
    """
    m = (model or "").upper()

    truck_hits = ["F-150", "F150", "SILVERADO", "SIERRA", "1500", "2500", "3500", "RANGER", "TACOMA", "TUNDRA"]
    suv_hits = ["SUV", "CROSSOVER", "HIGHLANDER", "4RUNNER", "SEQUOIA", "PILOT", "CR-V", "RAV4", "TAHOE", "SUBURBAN", "EXPLORER"]
    van_hits = ["VAN", "ODYSSEY", "SIENNA", "PACIFICA", "CARAVAN", "TRANSIT"]

    if any(h in m for h in truck_hits):
        return 1.20
    if any(h in m for h in suv_hits):
        return 1.10
    if any(h in m for h in van_hits):
        return 1.10
    return 1.00


@app.post("/estimate")
def estimate(req: EstimateRequest):
    svc = find_service(req.category, req.service)
    if not svc:
        raise HTTPException(status_code=400, detail=f"Unknown service '{req.service}' for category '{req.category}'")

    labor_rate = float(LABOR_RATE_BY_ZIP.get(req.zip_code, DEFAULT_LABOR_RATE))
    mult = infer_vehicle_multiplier(req.year, req.make, req.model)

    hrs_min = float(svc.get("labor_hours_min", 0) or 0) * mult
    hrs_max = float(svc.get("labor_hours_max", 0) or 0) * mult

    # If the catalog has no hours, give a sane fallback (prevents "undefined")
    if hrs_min <= 0 and hrs_max <= 0:
        hrs_min, hrs_max = 1.0 * mult, 2.0 * mult

    parts = float(req.parts_price or 0)
    parts_tax = parts * PARTS_TAX_RATE

    pricing_mode = (req.pricing_mode or "hourly").lower().strip()

    if pricing_mode == "flat":
        flat_min = float(svc.get("flat_rate_min", 0) or 0)
        flat_max = float(svc.get("flat_rate_max", 0) or 0)

        # fallback if flat isn't in catalog
        if flat_min <= 0 and flat_max <= 0:
            flat_min = labor_rate * hrs_min
            flat_max = labor_rate * hrs_max

        total_low = flat_min + parts + parts_tax
        total_high = flat_max + parts + parts_tax

        return {
            "service_name": svc.get("name"),
            "pricing_mode": "flat",
            "estimate_low": round(total_low),
            "estimate_high": round(total_high),
            "labor_rate": labor_rate,
            "labor_hours_min": round(hrs_min, 2),
            "labor_hours_max": round(hrs_max, 2),
            "vehicle_multiplier": mult,
            "parts_price": parts,
            "parts_tax": round(parts_tax, 2),
        }

    # hourly mode (default)
    labor_low = labor_rate * hrs_min
    labor_high = labor_rate * hrs_max

    total_low = labor_low + parts + parts_tax
    total_high = labor_high + parts + parts_tax

    return {
        "service_name": svc.get("name"),
        "pricing_mode": "hourly",
        "estimate_low": round(total_low),
        "estimate_high": round(total_high),
        "labor_rate": labor_rate,
        "labor_hours_min": round(hrs_min, 2),
        "labor_hours_max": round(hrs_max, 2),
        "vehicle_multiplier": mult,
        "parts_price": parts,
        "parts_tax": round(parts_tax, 2),
    }
