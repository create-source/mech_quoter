from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
import httpx
from datetime import datetime
from urllib.parse import quote
from fastapi import Body
from fastapi.responses import Response
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
import base64
import re
from reportlab.lib.utils import ImageReader

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

from fastapi.responses import FileResponse

@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(BASE_DIR / "manifest.webmanifest", media_type="application/manifest+json")

@app.get("/sw.js")
def service_worker():
    return FileResponse(BASE_DIR / "sw.js", media_type="application/javascript")


@app.get("/categories")
def categories():
    cat = load_catalog()
    return [{"key": c["key"], "name": c["name"]} for c in cat.get("categories", [])]

@app.post("/estimate/pdf")
def estimate_pdf(payload: dict = Body(...)):
    """
    Expects JSON payload from app.js buildEstimatePayload().
    Returns a generated PDF.
    """
    vehicle = payload.get("vehicle", {})
    selection = payload.get("selection", {})
    pricing = payload.get("pricing", {})
    notes = payload.get("notes", "")

    customer = payload.get("customer", {}) or {}
    customer_name = customer.get("name", "")
    customer_phone = customer.get("phone", "")
    
    sig_data_url = payload.get("signature_data_url", "") or ""

    year = vehicle.get("year", "")
    make = vehicle.get("make", "")
    model = vehicle.get("model", "")

    category_name = selection.get("category_name", "")
    service_name = selection.get("service_name", "")

    labor_hours = float(pricing.get("labor_hours", 0) or 0)
    labor_rate = float(pricing.get("labor_rate", 0) or 0)
    parts = float(pricing.get("parts", 0) or 0)
    labor = float(pricing.get("labor", labor_hours * labor_rate) or 0)
    total = float(pricing.get("total", labor + parts) or 0)

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    width, height = letter

    y = height - 60
    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, y, "Repair Estimate")
    y -= 25

    c.setFont("Helvetica", 11)
    c.drawString(50, y, f"Date: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    y -= 18
    c.drawString(50, y, f"Vehicle: {year} {make} {model}".strip())
    y -= 18
    c.drawString(50, y, f"Category: {category_name}")
    y -= 18
    c.drawString(50, y, f"Service: {service_name}")
    y -= 22

    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Pricing")
    y -= 16

    c.setFont("Helvetica", 11)
    c.drawString(50, y, f"Labor: {labor_hours:.1f} hrs @ ${labor_rate:.2f}/hr = ${labor:.2f}")
    y -= 16
    c.drawString(50, y, f"Parts: ${parts:.2f}")
    y -= 16
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, f"Total: ${total:.2f}")
    y -= 22

    # Customer
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Customer")
    y -= 16

    c.setFont("Helvetica", 11)
    if customer_name:
        c.drawString(50, y, f"Name: {customer_name}")
        y -= 16
    if customer_phone:
        c.drawString(50, y, f"Phone: {customer_phone}")
        y -= 16

    # Signature
    if sig_data_url.startswith("data:image/png;base64,"):
        try:
            b64 = re.sub(r"^data:image\/png;base64,", "", sig_data_url)
            img_bytes = base64.b64decode(b64)
            img = ImageReader(BytesIO(img_bytes))
    
            y -= 10
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y, "Signature")
            y -= 10
    
            sig_w = 260
            sig_h = 90
    
            # Draw box
            c.rect(50, y - sig_h, sig_w, sig_h)
    
            # Draw image inside box
            c.drawImage(
                img,
                52,
                y - sig_h + 2,
                width=sig_w - 4,
                height=sig_h - 4,
                preserveAspectRatio=True,
                mask='auto'
            )
    
            y -= (sig_h + 18)
    
        except Exception:
            c.setFont("Helvetica", 10)
            c.drawString(50, y, "Signature could not be rendered.")
            y -= 16

    if notes:
      c.setFont("Helvetica-Bold", 12)
      c.drawString(50, y, "Notes")
      y -= 16
      c.setFont("Helvetica", 11)
      # simple wrap
      max_chars = 95
      for i in range(0, len(notes), max_chars):
          c.drawString(50, y, notes[i:i+max_chars])
          y -= 14
          if y < 60:
              c.showPage()
              y = height - 60

    c.showPage()
    c.save()

    pdf_bytes = buf.getvalue()
    buf.close()

    filename = "estimate.pdf"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"'
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)

