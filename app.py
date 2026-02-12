from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
import httpx
from datetime import datetime

# PDF (ReportLab)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
CATALOG_PATH = BASE_DIR / "services_catalog.json"
INDEX_PATH = BASE_DIR / "index.html"

STATIC_DIR.mkdir(exist_ok=True)

POPULAR_MAKES = [
    "TOYOTA","HONDA","FORD","CHEVROLET","NISSAN","HYUNDAI","KIA","DODGE","JEEP",
    "GMC","SUBARU","BMW","MERCEDES-BENZ","VOLKSWAGEN","AUDI","LEXUS","MAZDA","TESLA","VOLVO"
]

def load_catalog():
    if not CATALOG_PATH.exists():
        return {"labor_rate": 90, "categories": []}
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))

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
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetMakesForVehicleModelYear/{year}?format=json"
    try:
        r = httpx.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = data.get("Results", []) or []
        makes = sorted({(m.get("MakeName") or "").upper().strip() for m in results if m.get("MakeName")})
        makes = [m for m in makes if m in POPULAR_MAKES]
        return {"makes": makes}
    except Exception:
        return {"makes": []}

@app.get("/vehicle/models")
def vehicle_models(year: int, make: str):
    make_clean = (make or "").strip()
    if not make_clean:
        return {"models": []}

    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetModelsForMakeYear/make/{make_clean}/modelyear/{year}?format=json"
    try:
        r = httpx.get(url, timeout=15)
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

# ---------- PDF endpoint ----------
@app.post("/estimate/pdf")
async def estimate_pdf(req: Request):
    payload = await req.json()

    # Pull + sanitize
    year = str(payload.get("year") or "")
    make = str(payload.get("make") or "")
    model = str(payload.get("model") or "")
    category = str(payload.get("category") or "")
    service = str(payload.get("service") or "")
    notes = str(payload.get("notes") or "")

    labor_hours = float(payload.get("laborHours") or 0)
    parts_price = float(payload.get("partsPrice") or 0)
    labor_rate = float(payload.get("laborRate") or 90)

    labor_total = labor_hours * labor_rate
    total = labor_total + parts_price

    # Build PDF bytes
    from io import BytesIO
    buf = BytesIO()

    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    x = 0.75 * inch
    y = height - 0.85 * inch

    c.setFont("Helvetica-Bold", 18)
    c.drawString(x, y, "Repair Estimate")
    y -= 0.35 * inch

    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"Generated: {datetime.now().strftime('%Y-%m-%d %I:%M %p')}")
    y -= 0.35 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Vehicle")
    y -= 0.2 * inch
    c.setFont("Helvetica", 11)
    c.drawString(x, y, f"{year}  {make}  {model}".strip())
    y -= 0.35 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Service")
    y -= 0.2 * inch
    c.setFont("Helvetica", 11)
    c.drawString(x, y, f"{category} — {service}".strip(" —"))
    y -= 0.35 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, "Totals")
    y -= 0.25 * inch
    c.setFont("Helvetica", 11)
    c.drawString(x, y, f"Labor:  {labor_hours:.1f} hrs @ ${labor_rate:.2f}/hr = ${labor_total:.2f}")
    y -= 0.22 * inch
    c.drawString(x, y, f"Parts:  ${parts_price:.2f}")
    y -= 0.22 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, f"Total:  ${total:.2f}")
    y -= 0.40 * inch

    if notes.strip():
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x, y, "Notes")
        y -= 0.20 * inch
        c.setFont("Helvetica", 10)

        # simple wrap
        max_width = width - 2 * x
        words = notes.replace("\r", "").split()
        line = ""
        for w in words:
            test = (line + " " + w).strip()
            if c.stringWidth(test, "Helvetica", 10) <= max_width:
                line = test
            else:
                c.drawString(x, y, line)
                y -= 0.18 * inch
                line = w
                if y < 1.0 * inch:
                    c.showPage()
                    y = height - 1.0 * inch
                    c.setFont("Helvetica", 10)
        if line:
            c.drawString(x, y, line)
            y -= 0.18 * inch

    c.showPage()
    c.save()

    pdf_bytes = buf.getvalue()
    buf.close()

    filename = f"estimate_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )
