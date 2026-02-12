from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
import httpx
from datetime import datetime
from urllib.parse import quote

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
INDEX_PATH = BASE_DIR / "index.html"
CATALOG_PATH = BASE_DIR / "services_catalog.json"

POPULAR_MAKES = [
    "TOYOTA","HONDA","FORD","CHEVROLET","NISSAN","HYUNDAI","KIA","DODGE","JEEP",
    "GMC","SUBARU","BMW","MERCEDES-BENZ","VOLKSWAGEN","AUDI","LEXUS","MAZDA","TESLA","VOLVO"
]

def load_catalog():
    if not CATALOG_PATH.exists():
        return {"labor_rate": 90, "categories": []}
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

# Static files
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
    # Correct vPIC endpoint
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetMakesForVehicleModelYear/{year}?format=json"
    try:
        r = httpx.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        results = data.get("Results", []) or []
        makes = sorted({(m.get("MakeName") or "").upper().strip() for m in results if m.get("MakeName")})
        makes = [m for m in makes if m in POPULAR_MAKES]
        return {"makes": makes}
    except Exception:
        return {"makes": POPULAR_MAKES}

@app.get("/vehicle/models")
def vehicle_models(year: int, make: str):
    make_clean = (make or "").strip()
    if not make_clean:
        return {"models": []}

    # Correct vPIC endpoint (URL-encode make)
    make_q = quote(make_clean)
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetModelsForMakeYear/make/{make_q}/modelyear/{year}?format=json"
    try:
        r = httpx.get(url, timeout=20)
        r.raise_for_status()
        data = r.json()
        results = data.get("Results", []) or []
        models = sorted({(m.get("Model_Name") or "").strip() for m in results if m.get("Model_Name")})
        return {"models": models}
    except Exception:
        return {"models": []}

# ---------- Catalog endpoints ----------
@app.get("/catalog")
def catalog():
    return load_catalog()

@app.get("/categories")
def categories():
    cat = load_catalog()
    return [{"key": c["key"], "name": c["name"]} for c in cat.get("categories", [])]

from fastapi.responses import FileResponse
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
import uuid

@app.post("/generate-pdf")
async def generate_pdf(data: dict):

    filename = f"estimate_{uuid.uuid4().hex}.pdf"
    filepath = BASE_DIR / filename

    doc = SimpleDocTemplate(str(filepath), pagesize=
