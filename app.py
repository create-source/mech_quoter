from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# --- Paths (everything expected to live next to this app.py) ---
BASE_DIR = Path(__file__).resolve().parent
INDEX_HTML = BASE_DIR / "index.html"
CATALOG_PATH = BASE_DIR / "services_catalog.json"
STATIC_DIR = BASE_DIR / "static"

# Serve /static/style.css and /static/app.js
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# -----------------------------
# Catalog loading + validation
# -----------------------------
_catalog_cache: Optional[Dict[str, Any]] = None


def _load_catalog() -> Dict[str, Any]:
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache

    if not CATALOG_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail="Missing services_catalog.json next to app.py",
        )

    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Catalog JSON parse error: {e}")

    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="Catalog root must be an object.")

    cats = data.get("categories")
    if not isinstance(cats, list):
        raise HTTPException(status_code=500, detail='Catalog must contain "categories": []')

    # Validate shape to prevent the exact crash you saw (list has no .get)
    cleaned: List[Dict[str, Any]] = []
    for i, c in enumerate(cats):
        if not isinstance(c, dict):
            raise HTTPException(
                status_code=500,
                detail=f'Invalid catalog: categories[{i}] must be an object (got {type(c).__name__}).',
            )
        if "key" not in c or "name" not in c:
            raise HTTPException(status_code=500, detail=f'Invalid category at index {i}: needs "key" and "name".')
        services = c.get("services", [])
        if not isinstance(services, list):
            raise HTTPException(status_code=500, detail=f'Invalid category "{c.get("key")}": "services" must be a list.')
        for j, s in enumerate(services):
            if not isinstance(s, dict):
                raise HTTPException(
                    status_code=500,
                    detail=f'Invalid service in category "{c.get("key")}" at services[{j}]: must be an object.',
                )
            if "code" not in s or "name" not in s:
                raise HTTPException(
                    status_code=500,
                    detail=f'Invalid service in category "{c.get("key")}": needs "code" and "name".',
                )

        cleaned.append(
            {
                "key": str(c["key"]).strip(),
                "name": str(c["name"]).strip(),
                "services": services,
            }
        )

    _catalog_cache = {"categories": cleaned}
    return _catalog_cache


# -----------------------------
# Vehicle data (popular makes)
# -----------------------------
POPULAR_MAKES = [
    "FORD", "CHEVROLET", "TOYOTA", "HONDA", "NISSAN", "JEEP", "DODGE", "GMC",
    "HYUNDAI", "KIA", "SUBARU", "RAM", "VOLKSWAGEN", "BMW", "MERCEDES-BENZ",
    "AUDI", "LEXUS", "MAZDA", "VOLVO", "TESLA",
]

FALLBACK_MODELS: Dict[str, List[str]] = {
    "FORD": ["F-150", "F-250", "F-350", "RANGER", "MUSTANG", "EXPLORER", "ESCAPE", "EDGE", "FOCUS", "FUSION"],
    "CHEVROLET": ["SILVERADO 1500", "SILVERADO 2500", "TAHOE", "SUBURBAN", "EQUINOX", "MALIBU", "CAMARO"],
    "TOYOTA": ["CAMRY", "COROLLA", "RAV4", "HIGHLANDER", "TACOMA", "TUNDRA", "SEQUOIA", "4RUNNER"],
    "HONDA": ["CIVIC", "ACCORD", "CR-V", "PILOT", "ODYSSEY", "FIT", "HR-V"],
    "NISSAN": ["ALTIMA", "SENTRA", "MAXIMA", "ROGUE", "MURANO", "FRONTIER", "TITAN", "PATHFINDER"],
    "GMC": ["SIERRA 1500", "SIERRA 2500", "YUKON", "ACADIA", "TERRAIN"],
    "JEEP": ["WRANGLER", "GRAND CHEROKEE", "CHEROKEE", "COMPASS", "RENEGADE", "GLADIATOR"],
    "RAM": ["1500", "2500", "3500", "PROMASTER"],
    "DODGE": ["CHARGER", "CHALLENGER", "DURANGO", "GRAND CARAVAN"],
    "SUBARU": ["OUTBACK", "FORESTER", "CROSSTREK", "IMPREZA", "LEGACY", "ASCENT"],
    "HYUNDAI": ["ELANTRA", "SONATA", "TUCSON", "SANTA FE", "KONA", "PALISADE"],
    "KIA": ["FORTE", "OPTIMA", "K5", "SORENTO", "SPORTAGE", "TELLURIDE"],
    "MAZDA": ["MAZDA3", "MAZDA6", "CX-5", "CX-30", "CX-9"],
    "VOLKSWAGEN": ["JETTA", "PASSAT", "TIGUAN", "ATLAS", "GOLF"],
    "BMW": ["3 SERIES", "5 SERIES", "X3", "X5", "X1"],
    "MERCEDES-BENZ": ["C-CLASS", "E-CLASS", "GLC", "GLE", "A-CLASS"],
    "AUDI": ["A3", "A4", "A6", "Q5", "Q7"],
    "LEXUS": ["ES", "IS", "RX", "GX", "NX"],
}


async def _vp_ic_models(make: str, year: Optional[str]) -> List[str]:
    # vPIC endpoint (free)
    # https://vpic.nhtsa.dot.gov/api/vehicles/getmodelsformakeyear/make/{make}/modelyear/{year}?format=json
    if not year or not year.isdigit():
        return []
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/getmodelsformakeyear/make/{make}/modelyear/{year}?format=json"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
        r.raise_for_status()
        payload = r.json()
        results = payload.get("Results", [])
        models = []
        for item in results:
            m = (item.get("Model_Name") or "").strip()
            if m:
                models.append(m.upper())
        # unique, sorted
        return sorted(set(models))
    except Exception:
        return []


# -----------------------------
# Routes
# -----------------------------
@app.get("/")
def home() -> FileResponse:
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=500, detail="Missing index.html next to app.py")
    return FileResponse(str(INDEX_HTML))


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


# ---- Catalog API ----
@app.get("/catalog")
def catalog() -> JSONResponse:
    # Full catalog so UI can filter client-side
    return JSONResponse(_load_catalog())


@app.get("/categories")
def categories() -> JSONResponse:
    cats = _load_catalog()["categories"]
    return JSONResponse([{"key": c["key"], "name": c["name"]} for c in cats])


@app.get("/services")
def services(category_key: str = Query(...)) -> JSONResponse:
    # Optional helper endpoint (frontend does not need it if filtering client-side)
    cats = _load_catalog()["categories"]
    for c in cats:
        if c["key"] == category_key:
            return JSONResponse(c.get("services", []))
    return JSONResponse([])


# ---- Vehicle API ----
@app.get("/vehicle/years")
def vehicle_years() -> JSONResponse:
    # Simple range; UI will use it.
    years = [str(y) for y in range(1980, 2028)]
    return JSONResponse(years)


@app.get("/vehicle/makes")
async def vehicle_makes(year: int):
    # ... however you fetch makes from vPIC ...
    # Suppose the result is: makes = sorted({...})
    makes = sorted({m.upper() for m in makes})

    popular = [m for m in POPULAR_MAKES if m in makes]
    return popular if popular else makes[:20]


@app.get("/vehicle/models")
async def vehicle_models(
    year: Optional[str] = Query(default=None),
    make: Optional[str] = Query(default=None),
) -> JSONResponse:
    if not make:
        return JSONResponse([])

    make_u = make.strip().upper()

    models = await _vp_ic_models(make_u, year)
    if models:
        return JSONResponse(models)

    # fallback if vPIC fails / rate-limits
    return JSONResponse(FALLBACK_MODELS.get(make_u, []))


# ---- Estimate ----
@app.get("/estimate")
def estimate(
    zip_code: str = Query(..., min_length=5, max_length=10),
    year: Optional[str] = Query(default=None),
    make: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    category_key: str = Query(...),
    service_code: str = Query(...),
    labor_rate: float = Query(160.0, ge=0),
    pricing_mode: str = Query("hourly"),  # "hourly" or "flat"
    parts_price: float = Query(0.0, ge=0),
) -> JSONResponse:
    cat = None
    svc = None
    for c in _load_catalog()["categories"]:
        if c["key"] == category_key:
            cat = c
            for s in c.get("services", []):
                if s.get("code") == service_code:
                    svc = s
                    break
            break

    if not cat or not svc:
        raise HTTPException(status_code=400, detail="Invalid category/service selection")

    # Labor calc
    lh_min = float(svc.get("labor_hours_min") or 0)
    lh_max = float(svc.get("labor_hours_max") or lh_min)

    if pricing_mode == "flat":
        labor_min = float(svc.get("flat_rate_min") or 0)
        labor_max = float(svc.get("flat_rate_max") or labor_min)
    else:
        labor_min = lh_min * labor_rate
        labor_max = lh_max * labor_rate

    total_min = labor_min + parts_price
    total_max = labor_max + parts_price

    return JSONResponse(
        {
            "zip_code": zip_code,
            "vehicle": {"year": year, "make": make, "model": model},
            "category": {"key": cat["key"], "name": cat["name"]},
            "service": {"code": svc.get("code"), "name": svc.get("name")},
            "pricing_mode": pricing_mode,
            "labor_rate": labor_rate,
            "parts_price": parts_price,
            "labor_hours_min": lh_min,
            "labor_hours_max": lh_max,
            "labor_min": round(labor_min, 2),
            "labor_max": round(labor_max, 2),
            "total_min": round(total_min, 2),
            "total_max": round(total_max, 2),
        }
    )
