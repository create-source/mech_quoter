from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
import httpx
from datetime import datetime

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CATALOG_PATH = BASE_DIR / "services_catalog.json"
INDEX_PATH = BASE_DIR / "index.html"

STATIC_DIR.mkdir(exist_ok=True)

POPULAR_MAKES = [
    "TOYOTA","HONDA","FORD","CHEVROLET","NISSAN","HYUNDAI","KIA","DODGE","JEEP",
    "GMC","SUBARU","BMW","MERCEDES-BENZ","VOLKSWAGEN","AUDI","LEXUS","MAZDA","TESLA",
    "VOLVO"
]

def load_catalog():
    if not CATALOG_PATH.exists():
        return {"labor_rate": 90, "categories": []}
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

# Serve static assets from /static
app.mount("/static", StaticFiles(directory=str(STATIC_DIR), html=False), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    if not INDEX_PATH.exists():
        return HTMLResponse("<h1>Missing index.html</h1>", status_code=500)
    return HTMLResponse(INDEX_PATH.read_text(encoding="utf-8"))


# ---------- Vehicle endpoints ----------
@app.get("/vehicle/years")
def vehicle_years():
    y = datetime.utcnow().year + 1
    return list(range(y, 1980, -1))


@app.get("/vehicle/makes")
def vehicle_makes(year: int):
    # Correct VPIC endpoint
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetMakesForVehicleModelYear/{year}?format=json"
    r = httpx.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    results = data.get("Results", [])
    makes = sorted({(m.get("MakeName") or "").upper().strip() for m in results if m.get("MakeName")})
    makes = [m for m in makes if m in POPULAR_MAKES]
    return makes


@app.get("/vehicle/models")
def vehicle_models(year: int, make: str):
    make = make.upper().strip()
    # Correct VPIC endpoint
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetModelsForMakeYear/make/{make}/modelyear/{year}?format=json"
    r = httpx.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    results = data.get("Results", [])
    models = sorted({(m.get("Model_Name") or "").strip() for m in results if m.get("Model_Name")})
    return models


# ---------- Catalog ----------
@app.get("/catalog")
def catalog():
    return load_catalog()


@app.get("/categories")
def categories():
    cat = load_catalog()
    return [{"key": c["key"], "name": c["name"]} for c in cat.get("categories", [])]
