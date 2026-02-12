from __future__ import annotations
import time
import httpx

import io
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

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

MAKE_MODELS_PATH = BASE_DIR / "make_models.json"
SERVICES_CATALOG_PATH = BASE_DIR / "services_catalog.json"


# ===============================
# CONFIG
# ===============================
POPULAR_MAKES: List[str] = [
    "TOYOTA", "HONDA", "FORD", "CHEVROLET", "NISSAN", "HYUNDAI", "KIA", "DODGE", "JEEP",
    "GMC", "SUBARU", "BMW", "MERCEDES-BENZ", "VOLKSWAGEN", "AUDI", "LEXUS", "MAZDA",
    "TESLA", "VOLVO",
]


# ===============================
# APP
# ===============================
app = FastAPI(title="Repair Estimator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ===============================
# FILE CACHES (auto reload on mtime change)
# ===============================
_make_models_cache: Optional[Dict[str, List[str]]] = None
_make_models_mtime: Optional[float] = None

_services_cache: Optional[Dict[str, Any]] = None
_services_mtime: Optional[float] = None


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON in {path.name}: {e}")


def load_make_models() -> Dict[str, List[str]]:
    global _make_models_cache, _make_models_mtime

    if not MAKE_MODELS_PATH.exists():
        raise HTTPException(status_code=500, detail="Missing make_models.json at project root.")

    mtime = MAKE_MODELS_PATH.stat().st_mtime
    if _make_models_cache is not None and _make_models_mtime == mtime:
        return _make_models_cache

    data = _read_json(MAKE_MODELS_PATH)
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="make_models.json must be an object: { MAKE: [models...] }")

    normalized: Dict[str, List[str]] = {}
    for k, v in data.items():
        make = str(k).strip().upper()
        if isinstance(v, list):
            normalized[make] = [str(m).strip() for m in v if str(m).strip()]
        else:
            normalized[make] = []

    _make_models_cache = normalized
    _make_models_mtime = mtime
    return normalized


def load_services_catalog() -> Dict[str, Any]:
    global _services_cache, _services_mtime

    if not SERVICES_CATALOG_PATH.exists():
        raise HTTPException(status_code=500, detail="Missing services_catalog.json at project root.")

    mtime = SERVICES_CATALOG_PATH.stat().st_mtime
    if _services_cache is not None and _services_mtime == mtime:
        return _services_cache

    data = _read_json(SERVICES_CATALOG_PATH)
    if not isinstance(data, dict):
        raise HTTPException(status_code=500, detail="services_catalog.json must be a JSON object.")

    if "categories" not in data or not isinstance(data["categories"], list):
        raise HTTPException(status_code=500, detail="services_catalog.json must include: { categories: [...] }")

    _services_cache = data
    _services_mtime = mtime
    return data


def find_service_by_code(service_code: str) -> Optional[Dict[str, Any]]:
    cat = load_services_catalog()
    code = (service_code or "").strip()
    if not code:
        return None

    for c in cat["categories"]:
        for s in c.get("services", []):
            if s.get("code") == code:
                return s
    return None


def default_labor_rate() -> float:
    cat = load_services_catalog()
    return float(cat.get("default_labor_rate") or cat.get("labor_rate") or 90)


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


# ===============================
# REQUEST/RESPONSE MODELS
# ===============================
class EstimateRequest(BaseModel):
    year: int = Field(..., ge=1970, le=2035)
    make: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)

    category: Optional[str] = None

    # You can send serviceCode (recommended) OR service (name fallback)
    serviceCode: Optional[str] = None
    service: Optional[str] = None

    laborHours: float = Field(0, ge=0)
    partsPrice: float = Field(0, ge=0)
    laborRate: Optional[float] = Field(None, ge=0)

    notes: Optional[str] = None
    customerName: Optional[str] = None
    customerPhone: Optional[str] = None

    zip: Optional[str] = Field(default="00000", min_length=5, max_length=10)
    signatureDataUrl: Optional[str] = None


class EstimateResponse(BaseModel):
    estimate: int
    currency: str = "USD"
    breakdown: Dict[str, float]
    service_name: str


# ===============================
# STARTUP CHECKS
# ===============================
@app.on_event("startup")
def _startup_checks() -> None:
    if not STATIC_DIR.exists():
        raise RuntimeError(f"Missing folder: {STATIC_DIR}")
    if not INDEX_HTML.exists():
        raise RuntimeError("Missing static/index.html")

    # Validate both catalogs load
    _ = load_make_models()
    _ = load_services_catalog()


# ===============================
# ROOT + PWA
# ===============================
@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
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


# ===============================
# MAKES / MODELS API
# ===============================
@app.get("/api/makes")
def get_makes() -> List[str]:
    # exactly your "popular list"
    return POPULAR_MAKES


@app.get("/api/models/{make}")
async def get_models(make: str) -> List[str]:
    make_upper = (make or "").strip().upper()

    # Keep UI restricted to your POPULAR_MAKES list
    if make_upper not in POPULAR_MAKES:
        raise HTTPException(status_code=404, detail=f"Make '{make}' not supported")

    return await fetch_models_from_vpic(make_upper)

# ===============================
# SERVICES API
# ===============================
@app.get("/api/categories")
def get_categories() -> List[Dict[str, str]]:
    cat = load_services_catalog()
    out: List[Dict[str, str]] = []
    for c in cat["categories"]:
        out.append({"key": c.get("key", ""), "name": c.get("name", "")})
    return out


@app.get("/api/services/{category_key}")
def get_services(category_key: str) -> List[Dict[str, Any]]:
    cat = load_services_catalog()
    ck = (category_key or "").strip()
    for c in cat["categories"]:
        if c.get("key") == ck:
            return c.get("services", [])
    raise HTTPException(status_code=404, detail=f"Category '{category_key}' not found")


@app.get("/api/service/{service_code}")
def get_service(service_code: str) -> Dict[str, Any]:
    s = find_service_by_code(service_code)
    if not s:
        raise HTTPException(status_code=404, detail="Service not found")
    return s


# ===============================
# ESTIMATE
# ===============================
@app.post("/estimate", response_model=EstimateResponse)
def estimate(req: EstimateRequest) -> EstimateResponse:
    mm = load_make_models()

    make_key = req.make.strip().upper()
    if make_key not in mm:
        raise HTTPException(status_code=400, detail="Invalid make")

    model = (req.model or "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="Model is required")

    allowed_upper = {m.upper(): m for m in mm[make_key]}
    if model.upper() not in allowed_upper:
        raise HTTPException(status_code=400, detail="Invalid model for selected make")

    # Determine service
    service_name = ""
    hours_default = 0.0

    if req.serviceCode:
        s = find_service_by_code(req.serviceCode)
        if not s:
            raise HTTPException(status_code=400, detail="Invalid serviceCode")
        service_name = str(s.get("name", "")).strip()
        # Default labor hours = midpoint of min/max
        mn = float(s.get("labor_hours_min", 0))
        mx = float(s.get("labor_hours_max", 0))
        if mx > 0 and mx >= mn:
            hours_default = (mn + mx) / 2.0
    else:
        service_name = (req.service or "").strip()
        if not service_name:
            raise HTTPException(status_code=400, detail="Select a service")

    labor_rate = float(req.laborRate) if req.laborRate is not None else default_labor_rate()
    labor_hours = float(req.laborHours) if req.laborHours and req.laborHours > 0 else hours_default

    labor = labor_hours * labor_rate
    parts = float(req.partsPrice)

    z = zip_multiplier(req.zip or "00000")
    y = year_multiplier(req.year)

    subtotal = (labor + parts) * z * y
    final_price = int(round(subtotal))

    return EstimateResponse(
        estimate=final_price,
        service_name=service_name,
        breakdown={
          "labor_hours": labor_hours,
          "labor_rate": labor_rate,
          "labor": labor,
          "parts": parts,
          "zip_multiplier": z,
          "year_multiplier": y,
          "subtotal": subtotal
        }
    )

@app.post("/estimate/pdf")
def estimate_pdf(req: EstimateRequest) -> Response:
    est = estimate(req)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    y = height - 72
    c.setTitle("Repair Estimate")

    # Header
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, "Repair Estimate")
    y -= 24

    c.setFont("Helvetica", 11)
    c.drawString(72, y, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    y -= 24

    # Vehicle
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Vehicle")
    y -= 16
    c.setFont("Helvetica", 11)
    c.drawString(72, y, f"{req.year} {req.make} {req.model}")
    y -= 18

    # Service
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Service")
    y -= 16
    c.setFont("Helvetica", 11)
    c.drawString(72, y, est.service_name)
    y -= 18

    # Total
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Estimated Total")
    y -= 16
    c.setFont("Helvetica", 12)
    c.drawString(72, y, f"${est.estimate:,} {est.currency}")
    y -= 18

    # Breakdown
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Breakdown")
    y -= 16
    c.setFont("Helvetica", 10)
    for k, v in est.breakdown.items():
        c.drawString(72, y, f"{k}: {v:.2f}")
        y -= 14

    y -= 10

    # Customer info
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Customer")
    y -= 16
    c.setFont("Helvetica", 11)
    if req.customerName:
        c.drawString(72, y, f"Name: {req.customerName}")
        y -= 14
    if req.customerPhone:
        c.drawString(72, y, f"Phone: {req.customerPhone}")
        y -= 14
    if req.notes:
        c.drawString(72, y, "Notes:")
        y -= 14
        # simple wrap
        note = req.notes.strip()
        for line in wrap_text(note, max_chars=95):
            c.drawString(72, y, line)
            y -= 12
        y -= 4

    # Signature block
    c.setFont("Helvetica-Bold", 12)
    c.drawString(72, y, "Signature")
    y -= 12

    sig_box_w = 240
    sig_box_h = 90
    sig_x = 72
    sig_y = y - sig_box_h

    # Draw signature box
    c.setLineWidth(1)
    c.rect(sig_x, sig_y, sig_box_w, sig_box_h)

    # If signature image exists, decode and draw it
    if req.signatureDataUrl:
        try:
            import base64
            from reportlab.lib.utils import ImageReader

            data_url = req.signatureDataUrl
            if "," in data_url:
                _, b64 = data_url.split(",", 1)
            else:
                b64 = data_url

            img_bytes = base64.b64decode(b64)
            img = ImageReader(io.BytesIO(img_bytes))

            # Fit image into box with padding
            pad = 6
            c.drawImage(
                img,
                sig_x + pad,
                sig_y + pad,
                width=sig_box_w - pad * 2,
                height=sig_box_h - pad * 2,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto",
            )
        except Exception as e:
            # If decode fails, still produce PDF
            c.setFont("Helvetica-Oblique", 9)
            c.drawString(sig_x + 8, sig_y + sig_box_h - 14, "Signature could not be rendered")

    y = sig_y - 24

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


def wrap_text(text: str, max_chars: int = 95) -> List[str]:
    # simple wrapping without extra deps
    words = text.split()
    lines: List[str] = []
    cur: List[str] = []
    cur_len = 0
    for w in words:
        add_len = len(w) + (1 if cur else 0)
        if cur_len + add_len > max_chars:
            lines.append(" ".join(cur))
            cur = [w]
            cur_len = len(w)
        else:
            cur.append(w)
            cur_len += add_len
    if cur:
        lines.append(" ".join(cur))
    return lines

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

# ===============================
# NHTSA vPIC (Models API)
# ===============================
VPIC_BASE = "https://vpic.nhtsa.dot.gov/api/vehicles"
VPIC_TIMEOUT_S = 10.0

# Cache models per make to avoid hammering NHTSA
# make_upper -> (expires_epoch, models_list)
_models_cache: Dict[str, tuple[float, List[str]]] = {}
MODELS_TTL_SECONDS = 60 * 60 * 24  # 24h cache

def _cache_get(make_upper: str) -> Optional[List[str]]:
    item = _models_cache.get(make_upper)
    if not item:
        return None
    expires, models = item
    if time.time() > expires:
        _models_cache.pop(make_upper, None)
        return None
    return models

def _cache_set(make_upper: str, models: List[str]) -> None:
    _models_cache[make_upper] = (time.time() + MODELS_TTL_SECONDS, models)

async def fetch_models_from_vpic(make: str) -> List[str]:
    """
    Fetch all models for a make from NHTSA vPIC.
    Endpoint: /GetModelsForMake/{make}?format=json
    """
    make_clean = (make or "").strip()
    if not make_clean:
        return []

    make_upper = make_clean.upper()
    cached = _cache_get(make_upper)
    if cached is not None:
        return cached

    url = f"{VPIC_BASE}/GetModelsForMake/{httpx.utils.quote(make_clean, safe='')}"
    params = {"format": "json"}

    # retry 2x (quick + safe)
    last_err: Optional[Exception] = None
    for _ in range(2):
        try:
            async with httpx.AsyncClient(timeout=VPIC_TIMEOUT_S, follow_redirects=True) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                data = r.json()

            results = data.get("Results", []) if isinstance(data, dict) else []
            models = []
            seen = set()

            for item in results:
                name = (item.get("Model_Name") or "").strip()
                if not name:
                    continue
                key = name.upper()
                if key in seen:
                    continue
                seen.add(key)
                models.append(name)

            models.sort(key=lambda s: s.upper())
            _cache_set(make_upper, models)
            return models

        except Exception as e:
            last_err = e

    # If NHTSA is down, fail gracefully with any stale cache (if present)
    stale = _models_cache.get(make_upper)
    if stale:
        return stale[1]

    raise HTTPException(status_code=502, detail=f"NHTSA vPIC unavailable: {last_err}")

