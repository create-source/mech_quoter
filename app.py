from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI()

# --- Paths (everything expected to live next to this app.py) ---
BASE_DIR = Path(__file__).resolve().parent
INDEX_HTML = BASE_DIR / "index.html"
CATALOG_PATH = BASE_DIR / "services_catalog.json"
STATIC_DIR = BASE_DIR / "static"

# Serve /static/style.css and /static/app.js
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- Catalog loader (cached) ---
_catalog_cache: Optional[Dict[str, Any]] = None

def get_catalog() -> Dict[str, Any]:
    """
    Loads services_catalog.json from the same folder as app.py.
    Expected shape:
      {
        "brakes": {"name": "Brakes", "services": [{"code":"pad_replace","name":"Pad replacement", ...}, ...]},
        ...
      }
    """
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache

    if not CATALOG_PATH.exists():
        raise HTTPException(status_code=500, detail="Missing services_catalog.json next to app.py")

    try:
        _catalog_cache = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        if not isinstance(_catalog_cache, dict):
            raise ValueError("Root JSON must be an object/dict.")
        return _catalog_cache
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load catalog: {type(e).__name__}: {e}")


def find_service(catalog: Dict[str, Any], category_key: str, service_code: str) -> Optional[Dict[str, Any]]:
    cat = catalog.get(category_key)
    if not cat:
        return None
    for s in cat.get("services", []):
        if s.get("code") == service_code:
            return s
    return None


# --- simple zip -> labor rate (placeholder) ---
def labor_rate(zip_code: str) -> float:
    # Replace with your real logic later.
    # For now, returns a safe default.
    return 150.0

PARTS_TAX_RATE = 0.0825

def money(x: float) -> str:
    return f"${x:,.2f}"


# --- Routes ---
@app.get("/")
def home():
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=500, detail="Missing index.html next to app.py")
    return FileResponse(str(INDEX_HTML))


@app.get("/categories")
def categories():
    catalog = get_catalog()
    out = []
    for key, c in catalog.items():
        out.append({
            "key": key,
            "name": c.get("name", key),
            "count": len(c.get("services", [])),
        })
    out.sort(key=lambda x: x["name"].lower())
    return out


@app.get("/services/{category_key}")
def services(category_key: str):
    catalog = get_catalog()
    cat = catalog.get(category_key)
    if not cat:
        raise HTTPException(status_code=404, detail=f"Unknown category '{category_key}'")

    svcs = cat.get("services", [])
    return [
        {"code": s.get("code"), "name": s.get("name")}
        for s in svcs
        if s.get("code") and s.get("name")
    ]


class EstimateRequest(BaseModel):
    zip_code: str
    category: str   # category key
    service: str    # service code


@app.post("/estimate")
def estimate(req: EstimateRequest):
    catalog = get_catalog()
    svc = find_service(catalog, req.category, req.service)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found for selected category")

    rate = labor_rate(req.zip_code)

    # labor_low/high OR labor_hours supported
    if "labor_low" in svc and "labor_high" in svc:
        labor_low = float(svc["labor_low"]) * rate
        labor_high = float(svc["labor_high"]) * rate
    else:
        labor_hours = float(svc.get("labor_hours", 1.0))
        labor_low = labor_hours * rate
        labor_high = labor_low

    parts_low = float(svc.get("parts_low", 0))
    parts_high = float(svc.get("parts_high", 0))

    total_low = labor_low + parts_low * (1 + PARTS_TAX_RATE)
    total_high = labor_high + parts_high * (1 + PARTS_TAX_RATE)
    total_mid = (total_low + total_high) / 2

    return {
        "service_name": svc.get("name"),
        "labor_rate": money(rate),
        "estimate_low": money(total_low),
        "estimate_mid": money(total_mid),
        "estimate_high": money(total_high),
    }


# --- Vehicle Year/Make/Model (vPIC) ---
VPIC_BASE = "https://vpic.nhtsa.dot.gov/api/vehicles"

@app.get("/vehicle/years")
def vehicle_years():
    from datetime import datetime
    current = datetime.now().year
    return list(range(current, current - 30, -1))


@app.get("/vehicle/makes")
async def vehicle_makes(year: int):
    urls = [
        f"{VPIC_BASE}/GetMakesForVehicleType/car?format=json",
        f"{VPIC_BASE}/GetMakesForVehicleType/truck?format=json",
        f"{VPIC_BASE}/GetMakesForVehicleType/multipurposepassengervehicle?format=json",
    ]
    makes_set = set()

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            for url in urls:
                r = await client.get(url)
                r.raise_for_status()
                data = r.json()
                for item in data.get("Results", []):
                    name = item.get("MakeName")
                    if name:
                        makes_set.add(name.strip())
        return sorted(makes_set)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/vehicle/makes failed: {type(e).__name__}: {e}")


@app.get("/vehicle/models")
async def vehicle_models(year: int, make: str):
    make_clean = make.strip()
    url = f"{VPIC_BASE}/GetModelsForMakeYear/make/{make_clean}/modelyear/{year}?format=json"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
        models = sorted({item.get("Model_Name") for item in data.get("Results", []) if item.get("Model_Name")})
        return models
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"/vehicle/models failed: {type(e).__name__}: {e}")
