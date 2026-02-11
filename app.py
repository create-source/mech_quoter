from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CATALOG_PATH = BASE_DIR / "services_catalog.json"
ESTIMATES_PATH = DATA_DIR / "estimates.json"

POPULAR_MAKES = [
    "TOYOTA","HONDA","FORD","CHEVROLET","NISSAN","HYUNDAI","KIA","DODGE","JEEP",
    "GMC","SUBARU","BMW","MERCEDES-BENZ","VOLKSWAGEN","AUDI","LEXUS","MAZDA","TESLA"
]

def load_catalog():
    if not CATALOG_PATH.exists():
        return {"labor_rate": 90, "categories": []}
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

def load_estimates():
    if not ESTIMATES_PATH.exists():
        return []
    return json.loads(ESTIMATES_PATH.read_text(encoding="utf-8"))

def save_estimates(rows):
    ESTIMATES_PATH.write_text(json.dumps(rows, indent=2), encoding="utf-8")

# Serve the UI from / (mobile friendly)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/", response_class=HTMLResponse)
def index():
    p = STATIC_DIR / "index.html"
    if not p.exists():
        return HTMLResponse("<h1>Missing static/index.html</h1>", status_code=500)
    return HTMLResponse(p.read_text(encoding="utf-8"))

# -------- Vehicle endpoints --------
@app.get("/vehicle/years")
def years():
    from datetime import datetime
    y = datetime.utcnow().year + 1
    return list(range(y, 1980, -1))

@app.get("/vehicle/makes")
def makes(year: int):
    return POPULAR_MAKES

@app.get("/vehicle/models")
def models(year: int, make: str):
    # Keep simple/stable for now
    return ["CAMRY","COROLLA","RAV4","TACOMA","PRIUS","CIVIC","ACCORD","CR-V","F-150","SILVERADO","ALTIMA"]

# -------- Catalog endpoints --------
@app.get("/catalog")
def catalog():
    return load_catalog()

# -------- Estimate save (optional) --------
@app.post("/estimate")
async def create_estimate(req: Request):
    payload = await req.json()
    rows = load_estimates()
    payload["id"] = len(rows) + 1
    rows.append(payload)
    save_estimates(rows)
    return {"ok": True, "id": payload["id"]}
