from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
import httpx
from datetime import datetime

# PDF
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

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

def safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default

# Serve static assets from /static/*
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
    """
    Returns: { "makes": ["TOYOTA","HONDA", ...] }
    VPIC endpoint:
      https://vpic.nhtsa.dot.gov/api/vehicles/GetMakesForVehicleModelYear/{year}?format=json
    """
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetMakesForVehicleModelYear/{year}?format=json"
    try:
        r = httpx.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        results = data.get("Results", []) or []
        makes = sorted({(m.get("MakeName") or "").upper().strip() for m in results if m.get("MakeName")})
        makes = [m for m in makes if m in POPULAR_MAKES]  # hard-limit popular only
        return {"makes": makes}
    except Exception:
        return {"makes": []}

@app.get("/vehicle/models")
def vehicle_models(year: int, make: str):
    """
    Returns: { "models": ["Camry","Corolla", ...] }
    VPIC endpoint:
      https://vpic.nhtsa.dot.gov/api/vehicles/GetModelsForMakeYear/make/{make}/modelyear/{year}?format=json
    """
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

@app.get("/services")
def services(category: str):
    cat = load_catalog()
    for c in cat.get("categories", []):
        if c.get("key") == category:
            return c.get("services", [])
    return []

# ---------- Estimate calc (server-side sanity) ----------
@app.post("/estimate/calc")
async def estimate_calc(req: Request):
    p = await req.json()
    labor_hours = safe_float(p.get("laborHours"), 0.0)
    parts_price = safe_float(p.get("partsPrice"), 0.0)
    labor_rate = safe_float(p.get("laborRate"), 90.0)

    labor_total = round(labor_hours * labor_rate, 2)
    total = round(labor_total + parts_price, 2)
    return {
        "labor_hours": labor_hours,
        "labor_rate": labor_rate,
        "labor_total": labor_total,
        "parts_price": round(parts_price, 2),
        "total": total
    }

# ---------- PDF generation ----------
def build_estimate_pdf_bytes(payload: dict) -> bytes:
    # Create PDF in-memory
    from io import BytesIO
    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    story = []

    title = payload.get("title") or "Repair Estimate"
    story.append(Paragraph(f"<b>{title}</b>", styles["Title"]))
    story.append(Spacer(1, 10))

    # Header info
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    year = payload.get("year", "")
    make = payload.get("make", "")
    model = payload.get("model", "")
    category_name = payload.get("categoryName", payload.get("category", ""))
    service_name = payload.get("serviceName", payload.get("service", ""))

    header_tbl = Table(
        [
            ["Date", now_str],
            ["Vehicle", f"{year} {make} {model}".strip()],
            ["Category", str(category_name)],
            ["Service", str(service_name)],
        ],
        colWidths=[90, 420],
    )
    header_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(header_tbl)
    story.append(Spacer(1, 14))

    # Totals
    labor_hours = safe_float(payload.get("laborHours"), 0.0)
    parts_price = safe_float(payload.get("partsPrice"), 0.0)
    labor_rate = safe_float(payload.get("laborRate"), 90.0)
    labor_total = round(labor_hours * labor_rate, 2)
    total = round(labor_total + parts_price, 2)

    money_tbl = Table(
        [
            ["Labor Hours", f"{labor_hours:.2f}"],
            ["Labor Rate", f"${labor_rate:.2f}/hr"],
            ["Labor", f"${labor_total:.2f}"],
            ["Parts", f"${parts_price:.2f}"],
            ["Total", f"${total:.2f}"],
        ],
        colWidths=[180, 330],
    )
    money_tbl.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("BACKGROUND", (0, 4), (-1, 4), colors.HexColor("#e8f0ff")),
                ("FONTNAME", (0, 4), (-1, 4), "Helvetica-Bold"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(money_tbl)
    story.append(Spacer(1, 14))

    notes = (payload.get("notes") or "").strip()
    if notes:
        story.append(Paragraph("<b>Notes</b>", styles["Heading3"]))
        story.append(Paragraph(notes.replace("\n", "<br/>"), styles["BodyText"]))
        story.append(Spacer(1, 10))

    story.append(Spacer(1, 10))
    story.append(Paragraph("This is an estimate only. Final cost may vary after inspection.", styles["Italic"]))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes

@app.post("/estimate/pdf")
async def estimate_pdf(req: Request):
    payload = await req.json()
    pdf_bytes = build_estimate_pdf_bytes(payload)

    filename = "estimate.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'}
    )
