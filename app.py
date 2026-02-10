from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
INDEX_HTML = BASE_DIR / "index.html"
CATALOG_PATH = BASE_DIR / "services_catalog.json"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Repair Estimator", version="1.0")


# Serve /static/*
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ---------- Catalog loading (cached) ----------
_catalog_cache: Optional[Dict[str, Any]] = None


def _load_catalog() -> Dict[str, Any]:
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
    Tries to find a list of rows/items inside the catalog regardless of key naming.
    Supports common shapes like:
      {"items":[...]} or {"services":[...]} or {"catalog":[...]} or {"rows":[...]} or {"data":[...]}
    If the whole file is already a list, you can adjust here, but we expect dict root.
    """
    for key in ("items", "services", "catalog", "rows", "data"):
        v = catalog.get(key)
        if isinstance(v, list) and all(isinstance(x, dict) for x in v):
            return v

    # fallback: first list-of-dicts value
    for v in catalog.values():
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            return v

    return []


def _norm(s: Optional[str]) -> str:
    return (s or "").strip()


def _get_vehicle_fields(row: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
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


def _get_service_fields(row: Dict[str, Any]) -> Tuple[str, str]:
    category = (
        row.get("category")
        or row.get("service_category")
        or row.get("serviceCategory")
        or row.get("group")
        or ""
    )
    service = row.get("service") or row.get("name") or row.get("service_name") or row.get("serviceName") or ""
    return _norm(str(category)), _norm(str(service))


def _matches_vehicle_filter(
    row: Dict[str, Any],
    vehicle_type: Optional[str],
    year: Optional[str],
    make: Optional[str],
    model: Optional[str],
) -> bool:
    r_type, r_year, r_make, r_model = _get_vehicle_fields(row)

    # If a field isn't present in the row, treat it as "generic" and allow it.
    if vehicle_type and r_type and r_type.lower() != vehicle_type.lower():
        return False
    if year and r_year and r_year != year:
        return False
    if make and r_make and r_make.lower() != make.lower():
        return False
    if model and r_model and r_model.lower() != model.lower():
        return False
    return True


# ---------- Routes ----------
@app.get("/")
def home():
    if INDEX_HTML.exists():
        return FileResponse(str(INDEX_HTML))
    raise HTTPException(status_code=500, detail="Missing index.html next to app.py")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/vehicle/years")
def vehicle_years(
    vehicle_type: Optional[str] = Query(default=None),
):
    catalog = _load_catalog()
    rows = _iter_rows(catalog)

    years: Set[str] = set()
    for row in rows:
        if _matches_vehicle_filter(row, vehicle_type=vehicle_type, year=None, make=None, model=None):
            _, r_year, _, _ = _get_vehicle_fields(row)
            if r_year:
                years.add(r_year)

    if not years:
        # reasonable fallback
        years = {str(y) for y in range(1980, 2027)}

    return JSONResponse(sorted(years, key=lambda x: int(x) if x.isdigit() else 999999))


@app.get("/vehicle/makes")
def vehicle_makes(
    year: Optional[str] = Query(default=None),
    vehicle_type: Optional[str] = Query(default=None),
):
    catalog = _load_catalog()
    rows = _iter_rows(catalog)

    makes: Set[str] = set()
    for row in rows:
        if _matches_vehicle_filter(row, vehicle_type=vehicle_type, year=year, make=None, model=None):
            _, _, r_make, _ = _get_vehicle_fields(row)
            if r_make:
                makes.add(r_make)

    return JSONResponse(sorted(makes))


@app.get("/vehicle/models")
def vehicle_models(
    year: Optional[str] = Query(default=None),
    make: Optional[str] = Query(default=None),
    vehicle_type: Optional[str] = Query(default=None),
):
    catalog = _load_catalog()
    rows = _iter_rows(catalog)

    models: Set[str] = set()
    for row in rows:
        if _matches_vehicle_filter(row, vehicle_type=vehicle_type, year=year, make=make, model=None):
            _, _, _, r_model = _get_vehicle_fields(row)
            if r_model:
                models.add(r_model)

    return JSONResponse(sorted(models))


@app.get("/categories")
def categories(
    year: Optional[str] = Query(default=None),
    make: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    vehicle_type: Optional[str] = Query(default=None),
):
    catalog = _load_catalog()
    rows = _iter_rows(catalog)

    cats: Set[str] = set()
    for row in rows:
        if _matches_vehicle_filter(row, vehicle_type=vehicle_type, year=year, make=make, model=model):
            category, _ = _get_service_fields(row)
            if category:
                cats.add(category)

    return JSONResponse(sorted(cats))


@app.get("/services")
def services(
    category: str = Query(...),
    year: Optional[str] = Query(default=None),
    make: Optional[str] = Query(default=None),
    model: Optional[str] = Query(default=None),
    vehicle_type: Optional[str] = Query(default=None),
):
    catalog = _load_catalog()
    rows = _iter_rows(catalog)

    svcs: Set[str] = set()
    for row in rows:
        if _matches_vehicle_filter(row, vehicle_type=vehicle_type, year=year, make=make, model=model):
            r_cat, r_svc = _get_service_fields(row)
            if r_cat and r_cat.lower() == category.lower() and r_svc:
                svcs.add(r_svc)

    return JSONResponse(sorted(svcs))
