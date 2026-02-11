from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
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


def load_catalog() -> Dict[str, Any]:
    """Loads services_catalog.json from the same folder as app.py. Caches JSON in memory."""
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
        raise HTTPException(status_code=500, detail=f"Failed to load catalog: {e}")


def _iter_rows(catalog: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Finds list of "rows/items" regardless of key naming.
    Supports shapes like:
      {"items":[...]} or {"services":[...]} or {"catalog":[...]} or {"data":{"items":[...]}}
    """
    if not isinstance(catalog, dict):
        return []

    # Common direct keys
    for key in ("items", "services", "rows", "catalog"):
        val = catalog.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]

    # Nested "data" container
    data = catalog.get("data")
    if isinstance(data, dict):
        for key in ("items", "services", "rows", "catalog"):
            val = data.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]

    # Fallback: first list-of-dicts found anywhere at top level
    for v in catalog.values():
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            return v

    return []


def _norm(s: Optional[str]) -> str:
    return (s or "").strip()


def _get_vehicle_fields(row: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Try extract vehicle_type/year/make/model using multiple possible key names."""
    vehicle_type = row.get("vehicle_type") or row.get("vehicleType") or row.get("type")
    year = row.get("year") or row.get("vehicle_year") or row.get("vehicleYear")
    make = row.get("make") or row.get("vehicle_make") or row.get("vehicleMake")
    model = row.get("model") or row.get("vehicle_model") or row.get("vehicleModel")

    return (
        _norm(str(vehicle_type)) if vehicle_type is not None else None,
        _norm(str(year)) if year is not None else None,
        _norm(str(make)) if make is not None else None,
        _norm(str(model)) if model is not None else None,
    )


def _get_service_fields(row: Dict[str, Any]) -> Tuple[str, str, str, float]:
    """
    Extract category + service + optional identifiers/hours.
    We return: (category_key, category_name, service_name, hours)
    """
    category_key = (
        row.get("category_key")
        or row.get("categoryKey")
        or row.get("category_id")
        or row.get("categoryId")
        or row.get("category")
        or row.get("service_category")
        or row.get("serviceCategory")
        or "general"
    )

    category_name = (
        row.get("category_name")
        or row.get("categoryName")
        or row.get("category")
        or row.get("service_category")
        or row.get("serviceCategory")
        or "General"
    )

    service_name = row.get("service_name") or row.get("serviceName") or row.get("service") or row.get("name") or ""
    hours = row.get("hours") or row.get("labor_hours") or row.get("laborHours") or row.get("hrs") or 0

    try:
        hours_f = float(hours)
    except Exception:
        hours_f = 0.0

    return _norm(str(category_key)), _norm(str(category_name)), _norm(str(service_name)), hours_f


def _matches_vehicle_filter(
    row: Dict[str, Any],
    vehicle_type: Optional[str],
    year: Optional[str],
    make: Optional[str],
    model: Optional[str],
) -> bool:
    r_type, r_year, r_make, r_model = _get_vehicle_fields(row)

    # If row doesn't specify a field, treat it as "generic" and allow it
    if vehicle_type and r_type and r_type.lower() != vehicle_type.lower():
        return False
    if year and r_year and r_year != year:
        return False
    if make and r_make and r_make.lower() != make.lower():
        return False
    if model and r_model and r_model.lower() != model.lower():
        return False

    return True


# ---------- Pages ----------
@app.get("/")
def home() -> FileResponse:
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=500, detail="Missing index.html next to app.py")
    return FileResponse(str(INDEX_HTML))


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


# ---------- Vehicle lookups ----------
@app.get("/vehicle/years")
def vehicle_years(vehicle_type: Optional[str] = Query(default=None)) -> JSONResponse:
    catalog = load_catalog()
    rows = _iter_rows(catalog)

    years: Set[str] = set()
    for row in rows:
        if not _matches_vehicle_filter(row, vehicle_type=vehicle_type, year=None, make=None, model=None):
            continue
        _, r_year, _, _ = _get_vehicle_fields(row)
        if r_year:
            years.add(r_year)

    if not years:
        # fallback range
        years = {str(y) for y in range(1980, datetime.now().year + 2)}

    return JSONResponse(sorted(years, key=lambda x: int(x) if x.isdigit() else 999999))


@app.get("/vehicle/makes")
def vehicle_makes(
    year: Optional[str] = Query(default=None),
    vehicle_type: Optional[str] = Query(default=None),
) -> JSONResponse:
    catalog = load_catalog()
    rows = _iter_rows(catalog)

    makes: Set[str] = set()
    for row in rows:
        if not _matches_vehicle_filter(row, vehicle_type=vehicle_type, year=year, make=None, model=None):
            continue
        _, _, r_make, _ = _get_vehicle_fields(row)
        if r_make:
            makes.add(r_make)

    return JSONResponse(sorted(makes))


@app.get("/vehicle/models")
def vehicle_models(
    year: Optional[str] = Query(default=None),
    make: Optional[str] = Query(default=None),
    vehicle_type: Optional[str] = Query(default=None),
) -> JSONResponse:
    catalog = load_catalog()
    rows = _iter_rows(catalog)

    models: Set[str] = set()
    for row in rows:
        if not _matches_vehicle_filter(row, vehicle_type=vehicle_type, year=year, make=make, model=None):
            continue
        _, _, _, r_model = _get_vehicle_fields(row)
        if r_model:
            models.add(r_model)

    return JSONResponse(sorted(models))


# ---------- Category / Service ----------
@app.get("/categories")
def categories(
    year: Optional[str] = Query(default=None),
    make: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    vehicle_type: Optional[str] = Query(default=None),
) -> JSONResponse:
    catalog = load_catalog()
    rows = _iter_rows(catalog)

    # key -> {name, count}
    bucket: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        if not _matches_vehicle_filter(row, vehicle_type=vehicle_type, year=year, make=make, model=model):
            continue
        cat_key, cat_name, _, _ = _get_service_fields(row)
        if not cat_key:
            continue
        if cat_key not in bucket:
            bucket[cat_key] = {"key": cat_key, "name": cat_name or cat_key, "count": 0}
        bucket[cat_key]["count"] += 1

    # Always return list of dicts
    out = sorted(bucket.values(), key=lambda x: x["name"].lower())
    return JSONResponse(out)


@app.get("/services/{category_key}")
def services(
    category_key: str,
    year: Optional[str] = Query(default=None),
    make: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    vehicle_type: Optional[str] = Query(default=None),
) -> JSONResponse:
    catalog = load_catalog()
    rows = _iter_rows(catalog)

    out: List[Dict[str, Any]] = []
    for row in rows:
        if not _matches_vehicle_filter(row, vehicle_type=vehicle_type, year=year, make=make, model=model):
            continue
        cat_key, _, svc_name, hours = _get_service_fields(row)
        if cat_key != category_key:
            continue
        if not svc_name:
            continue

        out.append(
            {
                "id": svc_name,   # stable enough for dropdown
                "name": svc_name,
                "hrs": hours,
            }
        )

    out_sorted = sorted(out, key=lambda x: x["name"].lower())
    return JSONResponse(out_sorted)


# ---------- Labor rate ----------
@app.get("/labor_rate")
def get_labor_rate(zip: str = Query(..., min_length=3, max_length=10)) -> JSONResponse:
    """
    Simple labor-rate estimator. Replace with your real logic if you want.
    """
    z = "".join([c for c in zip if c.isdigit()])
    if len(z) < 5:
        raise HTTPException(status_code=400, detail="Enter a valid 5-digit ZIP")

    # Example: a tiny fake curve just so the UI works
    base = 140.0
    bump = (int(z[:2]) % 10) * 3.5
    rate = base + bump
    return JSONResponse({"zip": z[:5], "rate": round(rate, 2)})


# ---------- Estimate ----------
class EstimateRequest(BaseModel):
    zip: str
    parts_price: float = 0.0
    labor_pricing: str = "hourly"  # "hourly" or "flat"
    labor_hours: float = 0.0
    labor_rate: float = 0.0
    flat_labor: float = 0.0

    vehicle_type: Optional[str] = None
    year: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None

    category_key: Optional[str] = None
    service_id: Optional[str] = None


@app.post("/estimate")
def estimate(req: EstimateRequest) -> JSONResponse:
    # labor rate auto-fill if not provided
    labor_rate = req.labor_rate
    if (labor_rate is None) or labor_rate <= 0:
        labor_rate = get_labor_rate(req.zip).body
        # get_labor_rate returns JSONResponse; .body is bytes
        try:
            labor_rate = json.loads(labor_rate.decode("utf-8")).get("rate", 0.0)
        except Exception:
            labor_rate = 0.0

    labor_total = 0.0
    if req.labor_pricing == "flat":
        labor_total = float(req.flat_labor or 0.0)
    else:
        labor_total = float(labor_rate or 0.0) * float(req.labor_hours or 0.0)

    parts = float(req.parts_price or 0.0)
    subtotal = parts + labor_total

    # optional: shop supplies + tax example
    shop_supplies = round(subtotal * 0.02, 2)
    taxable = subtotal + shop_supplies
    tax = round(taxable * 0.0825, 2)
    total = round(taxable + tax, 2)

    return JSONResponse(
        {
            "parts": round(parts, 2),
            "labor_rate": round(float(labor_rate or 0.0), 2),
            "labor_hours": round(float(req.labor_hours or 0.0), 2),
            "labor_total": round(labor_total, 2),
            "shop_supplies": shop_supplies,
            "tax": tax,
            "total": total,
        }
    )
