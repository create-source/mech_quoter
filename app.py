from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CATALOG_PATH = BASE_DIR / "services_catalog.json"

app = FastAPI(title="Mech Quoter", version="1.0")

# Serve /static/*
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def home():
    # Prefer /static/index.html if you put it there, otherwise root index.html
    static_index = STATIC_DIR / "index.html"
    root_index = BASE_DIR / "index.html"
    if static_index.exists():
        return FileResponse(str(static_index))
    if root_index.exists():
        return FileResponse(str(root_index))
    raise HTTPException(status_code=404, detail="index.html not found")


# ---------------- Catalog loading (robust) ----------------

_catalog_cache: Optional[Dict[str, Any]] = None


def _read_catalog_raw() -> Any:
    if not CATALOG_PATH.exists():
        raise RuntimeError(f"Missing {CATALOG_PATH.name} next to app.py")
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _normalize_catalog(raw: Any) -> Dict[str, Dict[str, Any]]:
    """
    Returns a normalized dict:
      {
        "category_key": {
          "name": "Category Name",
          "services": [ { "code": "...", "name": "...", ... }, ... ]
        },
        ...
      }

    Supports common shapes:
    - { "categories": [ {key/name/services}, ... ] }
    - { "catalog": [ ... ] } or { "services": [ ... ] } or { "items": [ ... ] }
    - already-normalized dict keyed by category
    """
    # Case 1: already normalized dict keyed by category
    if isinstance(raw, dict):
        # If it has "categories" list, use it
        if isinstance(raw.get("categories"), list):
            cats = raw["categories"]
            out: Dict[str, Dict[str, Any]] = {}
            for c in cats:
                if not isinstance(c, dict):
                    continue
                key = c.get("key") or c.get("id") or c.get("category_key") or c.get("category")
                name = c.get("name") or c.get("label") or key
                services = c.get("services") or c.get("items") or []
                if not key or not isinstance(services, list):
                    continue
                norm_services = []
                for s in services:
                    if not isinstance(s, dict):
                        continue
                    code = s.get("code") or s.get("id") or s.get("service_code") or s.get("service")
                    sname = s.get("name") or s.get("label") or code
                    if not code or not sname:
                        continue
                    s2 = dict(s)
                    s2["code"] = str(code)
                    s2["name"] = str(sname)
                    norm_services.append(s2)
                out[str(key)] = {"name": str(name), "services": norm_services}
            return out

        # If it looks like dict-of-categories already (values are dicts with services)
        out2: Dict[str, Dict[str, Any]] = {}
        looks_like = False
        for k, v in raw.items():
            if isinstance(v, dict) and ("services" in v or "items" in v):
                looks_like = True
        if looks_like:
            for k, v in raw.items():
                if not isinstance(v, dict):
                    continue
                services = v.get("services") or v.get("items") or []
                if not isinstance(services, list):
                    continue
                name = v.get("name") or k
                norm_services = []
                for s in services:
                    if not isinstance(s, dict):
                        continue
                    code = s.get("code") or s.get("id") or s.get("service_code") or s.get("service")
                    sname = s.get("name") or s.get("label") or code
                    if not code or not sname:
                        continue
                    s2 = dict(s)
                    s2["code"] = str(code)
                    s2["name"] = str(sname)
                    norm_services.append(s2)
                out2[str(k)] = {"name": str(name), "services": norm_services}
            return out2

        # Otherwise try to find first list inside dict that contains dict items with category/service info
        for key in ("items", "services", "catalog", "rows", "data"):
            if isinstance(raw.get(key), list):
                raw = raw[key]
                break

    # Case 2: list of rows (service rows) -> build categories from rows
    # Each row should have category + service-ish fields
    out3: Dict[str, Dict[str, Any]] = {}
    if isinstance(raw, list):
        for row in raw:
            if not isinstance(row, dict):
                continue
            cat = row.get("category") or row.get("service_category") or row.get("serviceCategory") or row.get("category_name")
            svc = row.get("service") or row.get("name") or row.get("service_name") or row.get("serviceName")
            code = row.get("code") or row.get("service_code") or svc
            if not cat or not svc:
                continue
            cat_key = str(cat).strip()
            if cat_key not in out3:
                out3[cat_key] = {"name": cat_key, "services": []}
            s2 = dict(row)
            s2["code"] = str(code).strip()
            s2["name"] = str(svc).strip()
            out3[cat_key]["services"].append(s2)
        return out3

    return {}


def get_catalog() -> Dict[str, Dict[str, Any]]:
    global _catalog_cache
    # Cache in memory so Render doesn’t re-read file every request
    if _catalog_cache is not None:
        return _catalog_cache
    try:
        raw = _read_catalog_raw()
        norm = _normalize_catalog(raw)
        if not norm:
            raise RuntimeError("Catalog loaded but could not be normalized. Check JSON shape.")
        _catalog_cache = norm
        return norm
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def find_service(catalog: Dict[str, Dict[str, Any]], category_key: str, service_code: str) -> Optional[Dict[str, Any]]:
    cat = catalog.get(category_key)
    if not cat:
        return None
    for s in cat.get("services", []):
        if str(s.get("code")) == str(service_code):
            return s
    return None


# ---------------- API: vehicle makes/models (popular only) ----------------

VPIC_BASE = "https://vpic.nhtsa.dot.gov/api/vehicles"

POPULAR_MAKES = {
    "ACURA","AUDI","BMW","BUICK","CADILLAC","CHEVROLET","CHRYSLER","DODGE","FORD","GMC",
    "HONDA","HYUNDAI","INFINITI","JEEP","KIA","LEXUS","LINCOLN","MAZDA","MERCEDES-BENZ",
    "MINI","MITSUBISHI","NISSAN","RAM","SUBARU","TESLA","TOYOTA","VOLKSWAGEN","VOLVO",
    "PORSCHE","LAND ROVER","JAGUAR"
}

@app.get("/vehicle/years")
def vehicle_years():
    current = datetime.now().year
    return list(range(current, current - 30, -1))


@app.get("/vehicle/makes")
async def vehicle_makes(year: int):
    # year is used by your UI flow; vPIC doesn't strictly require it here
    urls = [
        f"{VPIC_BASE}/GetMakesForVehicleType/car?format=json",
        f"{VPIC_BASE}/GetMakesForVehicleType/truck?format=json",
        f"{VPIC_BASE}/GetMakesForVehicleType/multipurposepassengervehicle?format=json",
    ]
    makes_set = set()

    async with httpx.AsyncClient(timeout=20) as client:
        for url in urls:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
            for item in data.get("Results", []):
                name = item.get("MakeName")
                if not name:
                    continue
                n = name.strip().upper()
                if n in POPULAR_MAKES:
                    makes_set.add(n)

    return sorted(makes_set)


@app.get("/vehicle/models")
async def vehicle_models(year: int, make: str):
    url = f"{VPIC_BASE}/GetModelsForMakeYear/make/{make}/modelyear/{year}?format=json"
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()

    models = []
    seen = set()
    for item in data.get("Results", []):
        mn = item.get("Model_Name")
        if not mn:
            continue
        mn = mn.strip().upper()
        if mn in seen:
            continue
        seen.add(mn)
        models.append(mn)

    return sorted(models)


# ---------------- API: categories + services ----------------

@app.get("/categories")
def categories():
    catalog = get_catalog()
    out = [{"key": k, "name": v.get("name", k), "count": len(v.get("services", []))} for k, v in catalog.items()]
    out.sort(key=lambda x: (x["name"] or "").lower())
    return out


@app.get("/services/{category_key}")
def services_for_category(category_key: str):
    catalog = get_catalog()
    cat = catalog.get(category_key)
    if not cat:
        raise HTTPException(status_code=404, detail=f"Unknown category '{category_key}'")
    svcs = cat.get("services", [])
    svcs_sorted = sorted(svcs, key=lambda s: (str(s.get("name", ""))).lower())
    return svcs_sorted


# ---------------- Estimate ----------------

class EstimateIn(BaseModel):
    zip_code: Optional[str] = None
    labor_pricing: Optional[str] = "hourly"   # keep for future
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    category: str
    service: str


@app.post("/estimate")
def estimate(payload: EstimateIn):
    catalog = get_catalog()
    svc = find_service(catalog, payload.category, payload.service)
    if not svc:
        raise HTTPException(status_code=404, detail="Service not found for that category")

    # You said you want part price gone; estimate uses service data only.
    # If your JSON includes flat_rate / labor_hours, use it; else simple fallback.
    lh_min = float(svc.get("labor_hours_min") or 0.0)
    lh_max = float(svc.get("labor_hours_max") or lh_min or 0.0)

    if lh_min <= 0 and lh_max <= 0:
        lh_min = lh_max = 1.0
    elif lh_min <= 0:
        lh_min = lh_max
    elif lh_max <= 0:
        lh_max = lh_min

    # Simple labor rate placeholder (you can adjust later or zip-map it)
    labor_rate = float(svc.get("labor_rate") or 90.0)

    low = labor_rate * lh_min
    high = labor_rate * lh_max

    return {
        "service_name": svc.get("name", payload.service),
        "category": payload.category,
        "service": payload.service,
        "labor_rate": round(labor_rate, 2),
        "labor_hours_min": round(lh_min, 2),
        "labor_hours_max": round(lh_max, 2),
        "estimate_low": round(low, 2),
        "estimate_high": round(high, 2),
    }
