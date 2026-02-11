import json
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Mech Quoter")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = (BASE_DIR / "static") if (BASE_DIR / "static").exists() else BASE_DIR

# Only show a short, popular make list in the UI
POPULAR_MAKES = [
    "Toyota",
    "Honda",
    "Ford",
    "Chevrolet",
    "Nissan",
    "GMC",
    "Dodge",
    "Jeep",
    "Hyundai",
    "Kia",
    "Subaru",
    "Volkswagen",
    "BMW",
    "Mercedes-Benz",
    "Audi",
    "Mazda",
]

# Serve frontend
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def home():
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="index.html not found")
    return FileResponse(str(index_path))


CATALOG_PATH = BASE_DIR / "services_catalog.json"


def load_catalog_raw() -> Dict:
    if not CATALOG_PATH.exists():
        raise HTTPException(status_code=500, detail="services_catalog.json not found")
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_catalog_map() -> Dict[str, Dict]:
    raw = load_catalog_raw()
    cats = raw.get("categories", [])
    out = {}
    for c in cats:
        if isinstance(c, dict) and c.get("key"):
            out[c["key"]] = c
    return out


def find_service(category_key: str, service_code: str) -> Optional[Dict]:
    cat = get_catalog_map().get(category_key)
    if not cat:
        return None
    for s in cat.get("services", []):
        if isinstance(s, dict) and s.get("code") == service_code:
            return s
    return None


def labor_rate_multiplier(zip_code: str) -> float:
    # Simple placeholder multiplier (you can replace with real zip-based logic later)
    z = (zip_code or "").strip()
    if not z or len(z) < 3 or not z[:3].isdigit():
        return 1.00
    prefix = int(z[:3])
    if 900 <= prefix <= 961:  # CA-ish rough
        return 1.15
    if 100 <= prefix <= 299:  # NE-ish rough
        return 1.20
    if 300 <= prefix <= 599:  # mid-ish rough
        return 1.05
    return 1.00


def base_labor_rate() -> float:
    return 140.0  # baseline hourly labor rate


@app.get("/categories")
def categories():
    raw = load_catalog_raw()
    cats = raw.get("categories", [])
    return [{"key": c.get("key"), "name": c.get("name")} for c in cats if isinstance(c, dict)]


@app.get("/services/{category}")
def services(category: str):
    cat = get_catalog_map().get(category)
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    return [{"code": s.get("code"), "name": s.get("name")} for s in cat.get("services", []) if isinstance(s, dict)]


@app.get("/catalog")
def catalog():
    """Full catalog for client-side filtering (one fetch, no round-trips)."""
    raw = load_catalog_raw()
    cats = raw.get("categories", [])
    cleaned = []
    for c in cats:
        if not isinstance(c, dict):
            continue
        cleaned.append(
            {
                "key": c.get("key"),
                "name": c.get("name"),
                "services": [
                    {"code": s.get("code"), "name": s.get("name")}
                    for s in (c.get("services") or [])
                    if isinstance(s, dict) and s.get("code") and s.get("name")
                ],
            }
        )
    return {"categories": cleaned}


VPIC_BASE = "https://vpic.nhtsa.dot.gov/api/vehicles"


@app.get("/vehicle/years")
def vehicle_years():
    # Simple year list for UI
    return list(range(1990, 2027))


@app.get("/vehicle/makes")
async def vehicle_makes(year: int):
    # Hard-limit to popular makes (fast + predictable)
    return sorted(POPULAR_MAKES)


@app.get("/vehicle/models")
async def vehicle_models(year: int, make: str):
    # Use vPIC models-by-make+year
    url = f"{VPIC_BASE}/GetModelsForMakeYear/make/{make}/modelyear/{year}?format=json"
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
    models = []
    for item in data.get("Results", []):
        name = item.get("Model_Name")
        if name:
            models.append(name)
    models = sorted(set(models))
    if not models:
        # fallback: allow UI to still proceed
        return []
    return models


class EstimateRequest(BaseModel):
    zip_code: str
    year: int | None = None
    make: str | None = None
    model: str | None = None
    category_key: str
    service_code: str
    pricing_mode: str = "flat"  # "flat" or "hourly"
    parts_price: float | None = None


@app.post("/estimate")
def estimate(req: EstimateRequest):
    svc = find_service(req.category_key, req.service_code)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found")

    hours_min = float(svc.get("labor_hours_min", 1.0))
    hours_max = float(svc.get("labor_hours_max", hours_min))

    mult = labor_rate_multiplier(req.zip_code)
    rate = base_labor_rate() * mult

    hourly_low = hours_min * rate
    hourly_high = hours_max * rate

    flat_min = svc.get("flat_rate_min")
    flat_max = svc.get("flat_rate_max")

    pricing_mode = (req.pricing_mode or "flat").lower().strip()
    if pricing_mode == "hourly" or flat_min is None or flat_max is None:
        labor_low = hourly_low
        labor_high = hourly_high
    else:
        labor_low = float(flat_min)
        labor_high = float(flat_max)

    parts = float(req.parts_price) if req.parts_price is not None else 0.0

    return {
        "labor_hours_range": [hours_min, hours_max],
        "labor_cost_range": [round(labor_low, 2), round(labor_high, 2)],
        "parts_price": round(parts, 2),
        "total_cost_range": [round(labor_low + parts, 2), round(labor_high + parts, 2)],
        "labor_rate_multiplier": mult,
        "pricing_mode": pricing_mode,
    }
