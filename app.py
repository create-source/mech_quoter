import os
import io
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader


APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
STATIC_DIR = os.path.join(APP_DIR, "static")

CATALOG_PATH = os.path.join(APP_DIR, "services_catalog.json")

SHOP_PIN = os.environ.get("SHOP_PIN", "1234")
POPULAR_MAKES = {
    "FORD", "CHEVROLET", "TOYOTA", "HONDA", "NISSAN", "DODGE", "JEEP",
    "GMC", "HYUNDAI", "KIA", "SUBARU", "VOLKSWAGEN", "BMW", "MERCEDES-BENZ",
    "LEXUS", "MAZDA", "AUDI", "CHRYSLER", "RAM", "ACURA", "INFINITI"
}


def ensure_dirs():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(STATIC_DIR, exist_ok=True)


def load_catalog() -> Dict[str, Any]:
    if not os.path.exists(CATALOG_PATH):
        raise HTTPException(status_code=500, detail="services_catalog.json not found")
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"services_catalog.json invalid JSON: {e}")


def save_json(path: str, obj: Any):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)


def read_json(path: str, default: Any):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_owner(request: Request):
    pin = request.headers.get("x-shop-pin") or request.query_params.get("pin") or ""
    if pin != SHOP_PIN:
        raise HTTPException(status_code=401, detail="Unauthorized (bad PIN)")


app = FastAPI()
ensure_dirs()

# Serve /static/*
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def home():
    index_path = os.path.join(APP_DIR, "index.html")
    if not os.path.exists(index_path):
        return HTMLResponse("<h1>Missing index.html</h1>", status_code=500)
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# -----------------------------
# Vehicle endpoints (NHTSA)
# -----------------------------
@app.get("/vehicle/years")
def vehicle_years():
    current_year = datetime.now().year
    years = list(range(current_year, 1980, -1))
    return {"years": years}


@app.get("/vehicle/makes")
def vehicle_makes(year: int):
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetMakesForVehicleModelYear/modelyear/{year}?format=json"
    r = httpx.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    results = data.get("Results", [])
    makes = sorted({(m.get("MakeName") or "").upper().strip() for m in results if m.get("MakeName")})
    # Hard-limit to popular makes (your requirement)
    makes = [m for m in makes if m in POPULAR_MAKES]
    return {"makes": makes}


@app.get("/vehicle/models")
def vehicle_models(year: int, make: str):
    make = make.upper().strip()
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetModelsForMakeYear/make/{make}/modelyear/{year}?format=json"
    r = httpx.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
    results = data.get("Results", [])
    models = sorted({(m.get("Model_Name") or "").strip() for m in results if m.get("Model_Name")})
    return {"models": models}


# -----------------------------
# Catalog + estimate
# -----------------------------
@app.get("/api/catalog")
def api_catalog():
    return load_catalog()


@app.post("/api/estimate")
async def api_estimate(payload: Dict[str, Any]):
    """
    payload:
      year, make, model, zip, category_key, service_code, parts_price(optional)
    """
    catalog = load_catalog()
    labor_rate = float(catalog.get("labor_rate", 90))

    category_key = payload.get("category_key")
    service_code = payload.get("service_code")

    categories = catalog.get("categories", [])
    cat = next((c for c in categories if c.get("key") == category_key), None)
    if not cat:
        raise HTTPException(status_code=400, detail="Invalid category_key")
    svc = next((s for s in cat.get("services", []) if s.get("code") == service_code), None)
    if not svc:
        raise HTTPException(status_code=400, detail="Invalid service_code")

    hours_min = float(svc.get("labor_hours_min", 0))
    hours_max = float(svc.get("labor_hours_max", hours_min))
    parts_price = payload.get("parts_price")
    parts_price = float(parts_price) if parts_price not in (None, "") else 0.0

    labor_min = round(hours_min * labor_rate, 2)
    labor_max = round(hours_max * labor_rate, 2)
    total_min = round(labor_min + parts_price, 2)
    total_max = round(labor_max + parts_price, 2)

    return {
        "labor_rate": labor_rate,
        "category": {"key": cat.get("key"), "name": cat.get("name")},
        "service": {"code": svc.get("code"), "name": svc.get("name")},
        "labor_hours_min": hours_min,
        "labor_hours_max": hours_max,
        "labor_cost_min": labor_min,
        "labor_cost_max": labor_max,
        "parts_price": parts_price,
        "total_min": total_min,
        "total_max": total_max,
        "vehicle": {
            "year": payload.get("year"),
            "make": payload.get("make"),
            "model": payload.get("model"),
        },
        "zip": payload.get("zip"),
    }


# -----------------------------
# Approvals + invoices storage
# -----------------------------
APPROVALS_PATH = os.path.join(DATA_DIR, "approvals.json")
INVOICES_PATH = os.path.join(DATA_DIR, "invoices.json")


@app.post("/api/approval")
async def api_approval(payload: Dict[str, Any]):
    """
    Customer signs estimate => approval

    payload:
      customer_name, customer_email(optional), customer_phone(optional)
      estimate (object from /api/estimate)
      signature_data_url (data:image/png;base64,...)
    """
    if not payload.get("signature_data_url"):
        raise HTTPException(status_code=400, detail="Missing signature_data_url")

    approvals = read_json(APPROVALS_PATH, default=[])
    approval_id = str(uuid.uuid4())

    record = {
        "id": approval_id,
        "created_at": now_iso(),
        "customer": {
            "name": payload.get("customer_name", "").strip(),
            "email": payload.get("customer_email", "").strip(),
            "phone": payload.get("customer_phone", "").strip(),
        },
        "estimate": payload.get("estimate"),
        "signature_data_url": payload.get("signature_data_url"),
        "status": "approved",
    }
    approvals.insert(0, record)
    save_json(APPROVALS_PATH, approvals)
    return {"id": approval_id}


@app.get("/api/approval/{approval_id}")
def api_get_approval(approval_id: str):
    approvals = read_json(APPROVALS_PATH, default=[])
    rec = next((a for a in approvals if a.get("id") == approval_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Approval not found")
    return rec


@app.post("/api/invoice")
async def api_create_invoice(payload: Dict[str, Any]):
    """
    Invoice signature => payment acknowledgement

    payload:
      approval_id
      payment_signature_data_url (data:image/png;base64,...)
    """
    approval_id = payload.get("approval_id")
    pay_sig = payload.get("payment_signature_data_url")
    if not approval_id:
        raise HTTPException(status_code=400, detail="Missing approval_id")
    if not pay_sig:
        raise HTTPException(status_code=400, detail="Missing payment_signature_data_url")

    approvals = read_json(APPROVALS_PATH, default=[])
    appr = next((a for a in approvals if a.get("id") == approval_id), None)
    if not appr:
        raise HTTPException(status_code=404, detail="Approval not found")

    invoices = read_json(INVOICES_PATH, default=[])
    invoice_id = str(uuid.uuid4())
    rec = {
        "id": invoice_id,
        "created_at": now_iso(),
        "approval_id": approval_id,
        "customer": appr.get("customer"),
        "estimate": appr.get("estimate"),
        "payment_signature_data_url": pay_sig,
        "status": "payment_acknowledged",
    }
    invoices.insert(0, rec)
    save_json(INVOICES_PATH, invoices)
    return {"id": invoice_id}


@app.get("/api/invoice/{invoice_id}")
def api_get_invoice(invoice_id: str):
    invoices = read_json(INVOICES_PATH, default=[])
    rec = next((i for i in invoices if i.get("id") == invoice_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return rec


# Owner backend list endpoints
@app.get("/api/admin/approvals")
def admin_list_approvals(request: Request):
    require_owner(request)
    return {"approvals": read_json(APPROVALS_PATH, default=[])}


@app.get("/api/admin/invoices")
def admin_list_invoices(request: Request):
    require_owner(request)
    return {"invoices": read_json(INVOICES_PATH, default=[])}


# -----------------------------
# PDF helpers
# -----------------------------
def _data_url_to_imagereader(data_url: str) -> ImageReader:
    # data:image/png;base64,....
    if "," not in data_url:
        raise ValueError("Bad data URL")
    header, b64 = data_url.split(",", 1)
    raw = io.BytesIO(__import__("base64").b64decode(b64))
    return ImageReader(raw)


def build_estimate_pdf(approval: Dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter

    est = approval.get("estimate", {}) or {}
    cust = approval.get("customer", {}) or {}

    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, h - 60, "APPROVED ESTIMATE")

    c.setFont("Helvetica", 11)
    c.drawString(50, h - 90, f"Estimate ID: {approval.get('id')}")
    c.drawString(50, h - 110, f"Date: {approval.get('created_at')}")
    c.drawString(50, h - 130, f"Customer: {cust.get('name','')}")
    c.drawString(50, h - 150, f"Email: {cust.get('email','')}")
    c.drawString(50, h - 170, f"Phone: {cust.get('phone','')}")

    veh = est.get("vehicle", {}) or {}
    c.drawString(50, h - 200, f"Vehicle: {veh.get('year')} {veh.get('make')} {veh.get('model')}")
    c.drawString(50, h - 220, f"ZIP: {est.get('zip','')}")

    cat = est.get("category", {}) or {}
    svc = est.get("service", {}) or {}
    c.drawString(50, h - 250, f"Category: {cat.get('name','')}")
    c.drawString(50, h - 270, f"Service: {svc.get('name','')}")

    c.drawString(50, h - 310, f"Labor rate: ${est.get('labor_rate', 0):.2f}/hr")
    c.drawString(50, h - 330, f"Labor hours: {est.get('labor_hours_min','')} – {est.get('labor_hours_max','')}")
    c.drawString(50, h - 350, f"Labor: ${est.get('labor_cost_min',0):.2f} – ${est.get('labor_cost_max',0):.2f}")
    c.drawString(50, h - 370, f"Parts: ${est.get('parts_price',0):.2f}")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, h - 395, f"Total: ${est.get('total_min',0):.2f} – ${est.get('total_max',0):.2f}")

    c.setFont("Helvetica", 10)
    c.drawString(50, 140, "Customer Signature (Approval):")
    sig = _data_url_to_imagereader(approval["signature_data_url"])
    c.drawImage(sig, 50, 60, width=240, height=70, preserveAspectRatio=True, mask="auto")
    c.drawString(50, 45, "By signing, customer approves this estimate.")

    c.showPage()
    c.save()
    return buf.getvalue()


def build_invoice_pdf(invoice: Dict[str, Any]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter

    est = invoice.get("estimate", {}) or {}
    cust = invoice.get("customer", {}) or {}

    c.setFont("Helvetica-Bold", 18)
    c.drawString(50, h - 60, "INVOICE")

    c.setFont("Helvetica", 11)
    c.drawString(50, h - 90, f"Invoice ID: {invoice.get('id')}")
    c.drawString(50, h - 110, f"Related Approval ID: {invoice.get('approval_id')}")
    c.drawString(50, h - 130, f"Date: {invoice.get('created_at')}")

    c.drawString(50, h - 160, f"Customer: {cust.get('name','')}")
    c.drawString(50, h - 180, f"Email: {cust.get('email','')}")
    c.drawString(50, h - 200, f"Phone: {cust.get('phone','')}")

    veh = est.get("vehicle", {}) or {}
    c.drawString(50, h - 230, f"Vehicle: {veh.get('year')} {veh.get('make')} {veh.get('model')}")
    c.drawString(50, h - 250, f"ZIP: {est.get('zip','')}")

    cat = est.get("category", {}) or {}
    svc = est.get("service", {}) or {}
    c.drawString(50, h - 280, f"Service: {cat.get('name','')} — {svc.get('name','')}")

    c.drawString(50, h - 320, f"Labor: ${est.get('labor_cost_min',0):.2f} – ${est.get('labor_cost_max',0):.2f}")
    c.drawString(50, h - 340, f"Parts: ${est.get('parts_price',0):.2f}")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, h - 365, f"Amount Due: ${est.get('total_min',0):.2f} – ${est.get('total_max',0):.2f}")

    c.setFont("Helvetica", 10)
    c.drawString(50, 140, "Customer Signature (Payment Acknowledgement):")
    sig = _data_url_to_imagereader(invoice["payment_signature_data_url"])
    c.drawImage(sig, 50, 60, width=240, height=70, preserveAspectRatio=True, mask="auto")
    c.drawString(50, 45, "By signing, customer acknowledges payment obligation/receipt per shop policy.")

    c.showPage()
    c.save()
    return buf.getvalue()


@app.get("/api/approval/{approval_id}/pdf")
def approval_pdf(approval_id: str):
    approvals = read_json(APPROVALS_PATH, default=[])
    rec = next((a for a in approvals if a.get("id") == approval_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Approval not found")
    pdf_bytes = build_estimate_pdf(rec)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="estimate_{approval_id}.pdf"'},
    )


@app.get("/api/invoice/{invoice_id}/pdf")
def invoice_pdf(invoice_id: str):
    invoices = read_json(INVOICES_PATH, default=[])
    rec = next((i for i in invoices if i.get("id") == invoice_id), None)
    if not rec:
        raise HTTPException(status_code=404, detail="Invoice not found")
    pdf_bytes = build_invoice_pdf(rec)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="invoice_{invoice_id}.pdf"'},
    )
