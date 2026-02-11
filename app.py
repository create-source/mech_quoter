from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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

# --- “Popular makes” hard-limit (edit this list anytime) ---
POPULAR_MAKES_ORDERED: List[str] = [
    "TOYOTA",
    "HONDA",
    "FORD",
    "CHEVROLET",
    "NISSAN",
    "HYUNDAI",
    "KIA",
    "JEEP",
    "DODGE",
    "GMC",
    "SUBARU",
    "MAZDA",
    "VOLKSWAGEN",
    "BMW",
    "MERCEDES-BENZ",
    "LEXUS",
    "AUDI",
    "TESLA",
]

POPULAR_MAKES_SET = {m.upper() for m in POPULAR_MAKES_ORDERED}

# --- Catalog loader (cached) ---
_catalog_cache: Optional[Dict[str, Any]] = None


def _load_catalog() -> Dict[str, Any]:
    """
    Loads services_catalog.json from the same folder as app.py.
    Supports two common shapes:
      A) { "items": [ { ...row... }, ... ] }
      B) [ { ...row... }, ... ]
      C) { "rows": [ ... ] } or { "services": [ ... ] } etc.
    """
    global _catalog_cache
    if _catalog_cache is not None:
        return _catalog_cache

    if not CATALOG_PATH.exists():
        raise HTTPException(status_code=500, detail="Missing services_catalog.json next to app.py")

    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

    # normalize to dict with "items"
    if isinstance(raw, list):
        _catalog_cache = {"items": raw}
        return _catalog_cache

    if isinstance(raw, dict):
        # find first list-of-dicts in common keys
        for key in ("items", "rows", "services", "catalog", "data"):
            v = raw.get(key)
            if isinstance(v, list):
                _catalog_cache = {"items": v}
                return _catalog_cache

        # If it's already a dict but not in expected shape, still store it
        _catalog_cache = raw
        return _catalog_cache

    raise HTTPException(status_code=500, detail="services_catalog.json must be a JSON object or array")


def _iter_rows(catalog: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Return list of row dicts from catalog.
    """
    items = catalog.get("items")
    if isinstance(items, list):
        return [x for x in items if isinstance(x, dict)]

    # fallback: find any list-of-dicts value
    for v in catalog.values():
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            return v

    return []


def _norm(s: Optional[str]) -> str:
    return (s or "").strip()


def _get_vehicle_fields(row: Dict[str, Any]) -> tuple[str, str, str, str]:
    """
    Extract vehicle_type, year, make, model using multiple possible key names.
    """
    vehicle_type = row.get("vehicle_type") or row.get("vehicleType") or row.get("type") or ""
    year = row.get("year") or row.get("vehicle_year") or row.get("vehicleYear") or ""
    make = row.get("make") or row.get("vehicle_make") or row.get("vehicleMake") or ""
    model = row.get("model") or row.get("vehicle_model") or row.get("vehicleModel") or ""

    return _norm(str(vehicle_type)), _norm(str(year)), _norm(str(make)), _norm(str(model))


def _get_service_fields(row: Dict[str, Any]) -> tuple[str, str, str, str]:
    """
    Extract category_key, category_name, service_code, service_name.
    """
    # category
    category_key = row.get("category_key") or row.get("categoryKey") or row.get("service_category_key") or row.get("serviceCategoryKey") or row.get("category") or row.get("service_category") or ""
    category_name = row.get("category_name") or row.get("categoryName") or row.get("service_category_name") or row.get("serviceCategory") or row.get("serviceCategoryName") or ""

    # service
    service_code = row.get("service_code") or row.get("serviceCode") or row.get("code") or ""
    service_name = row.get("service_name") or row.get("serviceName") or row.get("service") or row.get("name") or ""

    return _norm(str(category_key)), _norm(str(category_name)), _norm(str(service_code)), _norm(str(service_name))


def _matches_vehicle(row: Dict[str, Any], year: Optional[str], make: Optional[str], model: Optional[str], vehicle_type: Optional[str]) -> bool:
    r_type, r_year, r_make, r_model = _get_vehicle_fields(row)

    if vehicle_type and r_type and r_type.lower() != vehicle_type.lower():
        return False
    if year and r_year and r_year != str(year):
        return False
    if make and r_make and r_make.lower() != str(make).lower():
        return False
    if model and r_model and r_model.lower() != str(model).lower():
        return False

    return True


def _build_catalog_tree(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build category->services tree from row data.
    This is returned once to the client, and then the UI filters category->service client-side.
    """
    categories: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        cat_key, cat_name, svc_code, svc_name = _get_service_fields(row)
        if not cat_key:
            continue

        if cat_key not in categories:
            categories[cat_key] = {
                "key": cat_key,
                "name": cat_name or cat_key,
                "services": {},  # temp dict
            }

        if svc_code or svc_name:
            code = svc_code or svc_name  # always ensure a stable value
            sdict = categories[cat_key]["services"].setdefault(code, {
                "code": code,
                "name": svc_name or svc_code or code,
                # pricing fields (if present)
                "labor_hours_min": row.get("labor_hours_min"),
                "labor_hours_max": row.get("labor_hours_max"),
                "flat_rate_min": row.get("flat_rate_min"),
                "flat_rate_max": row.get("flat_rate_max"),
            })

            # If later rows have better names or pricing, prefer them
            if not sdict.get("name") and (svc_name or svc_code):
                sdict["name"] = svc_name or svc_code
            for k in ("labor_hours_min", "labor_hours_max", "flat_rate_min", "flat_rate_max"):
                if sdict.get(k) is None and row.get(k) is not None:
                    sdict[k] = row.get(k)

    # convert services dict->list
    out = {"categories": []}
    for cat_key, c in categories.items():
        services_list = list(c["services"].values())
        # sort services by name
        services_list.sort(key=lambda x: (str(x.get("name") or "").lower()))
        c["services"] = services_list
        out["categories"].append(c)

    # sort categories by name
    out["categories"].sort(key=lambda x: (str(x.get("name") or "").lower()))
    return out


# ---------- Routes ----------
@app.get("/")
def home() -> FileResponse:
    if not INDEX_HTML.exists():
        raise HTTPException(status_code=500, detail="Missing index.html next to app.py")
    return FileResponse(str(INDEX_HTML))


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/vehicle/years")
def vehicle_years(vehicle_type: Optional[str] = Query(default=None)) -> JSONResponse:
    catalog = _load_catalog()
    rows = _iter_rows(catalog)

    years: Set[str] = set()
    for row in rows:
        if not _matches_vehicle(row, year=None, make=None, model=None, vehicle_type=vehicle_type):
            continue
        _, y, _, _ = _get_vehicle_fields(row)
        if y:
            years.add(y)

    # fallback if none in file
    if not years:
        years = {str(y) for y in range(1980, 2028)}

    return JSONResponse(sorted(years, key=lambda x: int(x) if x.isdigit() else 999999))


@app.get("/vehicle/makes")
def vehicle_makes(
    year: Optional[str] = Query(default=None),
    vehicle_type: Optional[str] = Query(default=None),
) -> JSONResponse:
    catalog = _load_catalog()
    rows = _iter_rows(catalog)

    makes: Set[str] = set()
    for row in rows:
        if not _matches_vehicle(row, year=year, make=None, model=None, vehicle_type=vehicle_type):
            continue
        _, _, mk, _ = _get_vehicle_fields(row)
        if mk:
            makes.add(mk.upper())

    # Hard-limit to only popular makes (in your preferred order)
    popular_available = [m for m in POPULAR_MAKES_ORDERED if m in makes]
    if popular_available:
        return JSONResponse(popular_available)

    # If the dataset doesn’t include makes (or no match), still return popular list
    return JSONResponse(POPULAR_MAKES_ORDERED)


@app.get("/vehicle/models")
def vehicle_models(
    year: Optional[str] = Query(default=None),
    make: Optional[str] = Query(default=None),
    vehicle_type: Optional[str] = Query(default=None),
) -> JSONResponse:
    catalog = _load_catalog()
    rows = _iter_rows(catalog)

    models: Set[str] = set()
    for row in rows:
        if not _matches_vehicle(row, year=year, make=make, model=None, vehicle_type=vehicle_type):
            continue
        _, _, _, mdl = _get_vehicle_fields(row)
        if mdl:
            models.add(mdl)

    return JSONResponse(sorted(models, key=lambda x: x.lower()))


@app.get("/catalog")
def catalog() -> JSONResponse:
    """
    One call for the whole category->services tree.
    UI filters category->service entirely client-side.
    """
    catalog = _load_catalog()
    rows = _iter_rows(catalog)
    return JSONResponse(_build_catalog_tree(rows))


def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


@app.get("/estimate")
def estimate(
    zip_code: str = Query(..., min_length=5, max_length=10),
    year: Optional[str] = Query(default=None),
    make: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    vehicle_type: Optional[str] = Query(default=None),
    category: str = Query(...),
    service: str = Query(...),
    parts_price: Optional[float] = Query(default=0.0),
) -> JSONResponse:
    """
    Estimate calculation:
    - Uses service catalog’s flat_rate_min/max if present; otherwise labor_hours_min/max * labor_rate.
    - Adds parts_price to both min/max totals.
    """
    labor_rate = 90.0  # as you requested

    catalog = _load_catalog()
    rows = _iter_rows(catalog)

    # find the service entry in the built catalog tree
    tree = _build_catalog_tree(rows)
    cat_obj = next((c for c in tree["categories"] if c["key"] == category), None)
    if not cat_obj:
        raise HTTPException(status_code=400, detail="Unknown category")

    svc_obj = next((s for s in cat_obj["services"] if s["code"] == service), None)
    if not svc_obj:
        raise HTTPException(status_code=400, detail="Unknown service")

    lh_min = _to_float(svc_obj.get("labor_hours_min"))
    lh_max = _to_float(svc_obj.get("labor_hours_max"))
    fr_min = _to_float(svc_obj.get("flat_rate_min"))
    fr_max = _to_float(svc_obj.get("flat_rate_max"))

    # compute labor
    if fr_min is not None and fr_max is not None:
        labor_min = fr_min
        labor_max = fr_max
    else:
        # fallback to hours * rate
        if lh_min is None:
            lh_min = 1.0
        if lh_max is None:
            lh_max = max(lh_min, 1.5)
        labor_min = lh_min * labor_rate
        labor_max = lh_max * labor_rate

    p = float(parts_price or 0.0)
    total_min = labor_min + p
    total_max = labor_max + p

    return JSONResponse(
        {
            "zip_code": zip_code,
            "vehicle": {"year": year, "make": make, "model": model, "vehicle_type": vehicle_type},
            "selection": {"category": category, "service": service},
            "service_name": svc_obj.get("name") or service,
            "labor_rate": labor_rate,
            "parts_price": round(p, 2),
            "labor_min": round(labor_min, 2),
            "labor_max": round(labor_max, 2),
            "total_min": round(total_min, 2),
            "total_max": round(total_max, 2),
        }
    )
