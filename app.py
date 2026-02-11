import os
import json
import base64
import sqlite3
from datetime import datetime
from typing import Optional, Dict, Any

import httpx
from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_DIR, "static")
CATALOG_PATH = os.path.join(APP_DIR, "services_catalog.json")
INDEX_PATH = os.path.join(APP_DIR, "index.html")
DB_PATH = os.path.join(APP_DIR, "data.db")
PDF_DIR = os.path.join(APP_DIR, "pdf")
os.makedirs(PDF_DIR, exist_ok=True)

security = HTTPBasic()

def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)

ADMIN_USER = env("ADMIN_USER", "admin")
ADMIN_PASS = env("ADMIN_PASS", "change_me")

POPULAR_MAKES = [
    "TOYOTA", "HONDA", "FORD", "CHEVROLET", "NISSAN", "HYUNDAI", "KIA",
    "JEEP", "DODGE", "RAM", "SUBARU", "GMC", "BMW", "MERCEDES-BENZ",
    "VOLKSWAGEN", "AUDI", "MAZDA", "LEXUS", "ACURA", "INFINITI"
]

app = FastAPI()

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS estimates (
      id TEXT PRIMARY KEY,
      created_at TEXT NOT NULL,
      status TEXT NOT NULL,
      customer_name TEXT,
      customer_phone TEXT,
      customer_email TEXT,
      zip_code TEXT,
      year TEXT,
      make TEXT,
      model TEXT,
      category_key TEXT,
      category_name TEXT,
      service_code TEXT,
      service_name TEXT,
      labor_rate REAL,
      labor_hours REAL,
      parts_price REAL,
      notes TEXT,
      subtotal REAL,
      tax_rate REAL,
      tax_amount REAL,
      total REAL,
      approval_signature_path TEXT,
      approval_signed_at TEXT,
      invoice_status TEXT,
      payment_signature_path TEXT,
      payment_signed_at TEXT
    )
    """)
    conn.commit()
    conn.close()

init_db()

def require_admin(creds: HTTPBasicCredentials = Depends(security)):
    if creds.username != ADMIN_USER or creds.password != ADMIN_PASS:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

def load_catalog() -> Dict[str, Any]:
    if not os.path.exists(CATALOG_PATH):
        raise HTTPException(500, f"Missing {os.path.basename(CATALOG_PATH)}")
    try:
        with open(CATALOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"Invalid JSON in services_catalog.json: {e}")

def now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"

def make_id(prefix: str) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}_{ts}"

def save_base64_png(data_url: str, filename: str) -> str:
    # expects: data:image/png;base64,XXXX
    if not data_url.startswith("data:image/png;base64,"):
        raise HTTPException(400, "Signature must be a PNG data URL")
    b64 = data_url.split(",", 1)[1]
    raw = base64.b64decode(b64)
    path = os.path.join(PDF_DIR, filename)
    with open(path, "wb") as f:
        f.write(raw)
    return path

def money(x: float) -> str:
    return f"${x:,.2f}"

def gen_estimate_pdf(row: sqlite3.Row) -> str:
    pdf_path = os.path.join(PDF_DIR, f"{row['id']}_estimate.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)
    w, h = letter

    c.setFont("Helvetica-Bold", 16)
    c.drawString(1*inch, h-1*inch, "Estimate")

    c.setFont("Helvetica", 10)
    c.drawString(1*inch, h-1.3*inch, f"Estimate ID: {row['id']}")
    c.drawString(1*inch, h-1.5*inch, f"Created: {row['created_at']}")

    y = h - 2.0*inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1*inch, y, "Customer")
    c.setFont("Helvetica", 10)
    y -= 0.2*inch
    c.drawString(1*inch, y, f"Name: {row['customer_name'] or ''}")
    y -= 0.2*inch
    c.drawString(1*inch, y, f"Phone: {row['customer_phone'] or ''}")
    y -= 0.2*inch
    c.drawString(1*inch, y, f"Email: {row['customer_email'] or ''}")
    y -= 0.2*inch
    c.drawString(1*inch, y, f"ZIP: {row['zip_code'] or ''}")

    y -= 0.4*inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1*inch, y, "Vehicle")
    c.setFont("Helvetica", 10)
    y -= 0.2*inch
    c.drawString(1*inch, y, f"{row['year'] or ''} {row['make'] or ''} {row['model'] or ''}")

    y -= 0.4*inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1*inch, y, "Service")
    c.setFont("Helvetica", 10)
    y -= 0.2*inch
    c.drawString(1*inch, y, f"Category: {row['category_name'] or ''}")
    y -= 0.2*inch
    c.drawString(1*inch, y, f"Service: {row['service_name'] or ''}")

    y -= 0.4*inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1*inch, y, "Pricing")
    c.setFont("Helvetica", 10)
    y -= 0.2*inch
    c.drawString(1*inch, y, f"Labor Rate: {money(row['labor_rate'] or 0)} / hr")
    y -= 0.2*inch
    c.drawString(1*inch, y, f"Labor Hours: {row['labor_hours'] or 0}")
    y -= 0.2*inch
    c.drawString(1*inch, y, f"Parts Price: {money(row['parts_price'] or 0)}")
    y -= 0.2*inch
    c.drawString(1*inch, y, f"Subtotal: {money(row['subtotal'] or 0)}")
    y -= 0.2*inch
    c.drawString(1*inch, y, f"Tax: {money(row['tax_amount'] or 0)} (rate {int((row['tax_rate'] or 0)*100)}%)")
    y -= 0.2*inch
    c.setFont("Helvetica-Bold", 12)
    c.drawString(1*inch, y, f"Total: {money(row['total'] or 0)}")

    y -= 0.4*inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1*inch, y, "Notes")
    c.setFont("Helvetica", 10)
    y -= 0.2*inch
    c.drawString(1*inch, y, (row["notes"] or "")[:120])

    if row["approval_signature_path"] and os.path.exists(row["approval_signature_path"]):
        y -= 0.6*inch
        c.setFont("Helvetica-Bold", 11)
        c.drawString(1*inch, y, "Customer Approval Signature")
        y -= 0.2*inch
        c.drawImage(row["approval_signature_path"], 1*inch, y-1.0*inch, width=2.5*inch, height=1.0*inch, mask='auto')
        c.setFont("Helvetica", 9)
        c.drawString(3.7*inch, y-0.2*inch, f"Signed: {row['approval_signed_at'] or ''}")

    c.showPage()
    c.save()
    return pdf_path

def gen_invoice_pdf(row: sqlite3.Row) -> str:
    pdf_path = os.path.join(PDF_DIR, f"{row['id']}_invoice.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)
    w, h = letter

    c.setFont("Helvetica-Bold", 16)
    c.drawString(1*inch, h-1*inch, "Invoice")

    c.setFont("Helvetica", 10)
    c.drawString(1*inch, h-1.3*inch, f"Estimate ID: {row['id']}")
    c.drawString(1*inch, h-1.5*inch, f"Created: {row['created_at']}")
    c.drawString(1*inch, h-1.7*inch, f"Invoice Status: {row['invoice_status'] or 'not set'}")

    y = h - 2.2*inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1*inch, y, "Customer")
    c.setFont("Helvetica", 10)
    y -= 0.2*inch
    c.drawString(1*inch, y, f"Name: {row['customer_name'] or ''}")
    y -= 0.2*inch
    c.drawString(1*inch, y, f"Phone: {row['customer_phone'] or ''}")
    y -= 0.2*inch
    c.drawString(1*inch, y, f"Email: {row['customer_email'] or ''}")

    y -= 0.4*inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1*inch, y, "Vehicle / Service")
    c.setFont("Helvetica", 10)
    y -= 0.2*inch
    c.drawString(1*inch, y, f"{row['year'] or ''} {row['make'] or ''} {row['model'] or ''}")
    y -= 0.2*inch
    c.drawString(1*inch, y, f"{row['category_name'] or ''} — {row['service_name'] or ''}")

    y -= 0.4*inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1*inch, y, "Amount Due")
    c.setFont("Helvetica-Bold", 12)
    y -= 0.25*inch
    c.drawString(1*inch, y, f"Total: {money(row['total'] or 0)}")

    if row["payment_signature_path"] and os.path.exists(row["payment_signature_path"]):
        y -= 0.6*inch
        c.setFont("Helvetica-Bold", 11)
        c.drawString(1*inch, y, "Payment Acknowledgement Signature")
        y -= 0.2*inch
        c.drawImage(row["payment_signature_path"], 1*inch, y-1.0*inch, width=2.5*inch, height=1.0*inch, mask='auto')
        c.setFont("Helvetica", 9)
        c.drawString(3.7*inch, y-0.2*inch, f"Signed: {row['payment_signed_at'] or ''}")

    c.showPage()
    c.save()
    return pdf_path

@app.get("/", response_class=HTMLResponse)
def home():
    if not os.path.exists(INDEX_PATH):
        raise HTTPException(500, "index.html missing in root")
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.get("/catalog")
def catalog():
    return JSONResponse(load_catalog())

@app.get("/vehicle/years")
def vehicle_years():
    # keep it simple & fast
    return list(range(datetime.now().year, 1980, -1))

@app.get("/vehicle/makes")
async def vehicle_makes(year: int):
    # Hard-limit to “popular makes”
    return POPULAR_MAKES

@app.get("/vehicle/models")
async def vehicle_models(year: int, make: str):
    # NHTSA endpoint (public) – returns common models
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/GetModelsForMakeYear/make/{make}/modelyear/{year}?format=json"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.json()
    except Exception:
        return []

    results = data.get("Results") or []
    models = sorted({(x.get("Model_Name") or "").strip() for x in results if x.get("Model_Name")})
    return models

@app.post("/estimate")
async def create_estimate(payload: Dict[str, Any]):
    cat = load_catalog()
    labor_rate = float(payload.get("labor_rate") or cat.get("labor_rate") or 90)
    tax_rate = float(payload.get("tax_rate") or 0.0)

    labor_hours = float(payload.get("labor_hours") or 0.0)
    parts_price = float(payload.get("parts_price") or 0.0)
    subtotal = labor_rate * labor_hours + parts_price
    tax_amount = subtotal * tax_rate
    total = subtotal + tax_amount

    est_id = make_id("EST")
    row = {
        "id": est_id,
        "created_at": now_iso(),
        "status": "draft",
        "invoice_status": "none",
        "customer_name": payload.get("customer_name"),
        "customer_phone": payload.get("customer_phone"),
        "customer_email": payload.get("customer_email"),
        "zip_code": payload.get("zip_code"),
        "year": payload.get("year"),
        "make": payload.get("make"),
        "model": payload.get("model"),
        "category_key": payload.get("category_key"),
        "category_name": payload.get("category_name"),
        "service_code": payload.get("service_code"),
        "service_name": payload.get("service_name"),
        "labor_rate": labor_rate,
        "labor_hours": labor_hours,
        "parts_price": parts_price,
        "notes": payload.get("notes"),
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "total": total,
        "approval_signature_path": None,
        "approval_signed_at": None,
        "payment_signature_path": None,
        "payment_signed_at": None
    }

    conn = db()
    cur = conn.cursor()
    cur.execute("""
      INSERT INTO estimates (
        id, created_at, status, customer_name, customer_phone, customer_email, zip_code,
        year, make, model, category_key, category_name, service_code, service_name,
        labor_rate, labor_hours, parts_price, notes, subtotal, tax_rate, tax_amount, total,
        approval_signature_path, approval_signed_at, invoice_status, payment_signature_path, payment_signed_at
      ) VALUES (
        :id, :created_at, :status, :customer_name, :customer_phone, :customer_email, :zip_code,
        :year, :make, :model, :category_key, :category_name, :service_code, :service_name,
        :labor_rate, :labor_hours, :parts_price, :notes, :subtotal, :tax_rate, :tax_amount, :total,
        :approval_signature_path, :approval_signed_at, :invoice_status, :payment_signature_path, :payment_signed_at
      )
    """, row)
    conn.commit()
    conn.close()

    return {"ok": True, "id": est_id, "totals": {"subtotal": subtotal, "tax": tax_amount, "total": total}}

@app.get("/estimate/{est_id}")
def get_estimate(est_id: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM estimates WHERE id=?", (est_id,))
    r = cur.fetchone()
    conn.close()
    if not r:
        raise HTTPException(404, "Estimate not found")
    return dict(r)

@app.post("/estimate/{est_id}/approve")
def approve_estimate(est_id: str, payload: Dict[str, Any]):
    signature = payload.get("signature_png")
    if not signature:
        raise HTTPException(400, "Missing signature_png")

    sig_path = save_base64_png(signature, f"{est_id}_approval.png")
    signed_at = now_iso()

    conn = db()
    cur = conn.cursor()
    cur.execute("""
      UPDATE estimates
      SET status='approved', approval_signature_path=?, approval_signed_at=?
      WHERE id=?
    """, (sig_path, signed_at, est_id))
    conn.commit()

    cur.execute("SELECT * FROM estimates WHERE id=?", (est_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Estimate not found")

    gen_estimate_pdf(row)
    return {"ok": True, "status": "approved"}

@app.get("/estimate/{est_id}/pdf")
def estimate_pdf(est_id: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM estimates WHERE id=?", (est_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Estimate not found")
    pdf_path = os.path.join(PDF_DIR, f"{est_id}_estimate.pdf")
    if not os.path.exists(pdf_path):
        pdf_path = gen_estimate_pdf(row)
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"{est_id}_estimate.pdf")

# -------------------- OWNER / BACKEND MODE --------------------

@app.get("/admin/estimates")
def admin_list_estimates(_: bool = Depends(require_admin)):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id, created_at, status, invoice_status, customer_name, year, make, model, total FROM estimates ORDER BY created_at DESC LIMIT 200")
    rows = [dict(x) for x in cur.fetchall()]
    conn.close()
    return rows

@app.post("/admin/estimate/{est_id}/mark_invoiced")
def admin_mark_invoiced(est_id: str, _: bool = Depends(require_admin)):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE estimates SET invoice_status='issued' WHERE id=?", (est_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "invoice_status": "issued"}

@app.post("/invoice/{est_id}/ack_payment")
def invoice_ack_payment(est_id: str, payload: Dict[str, Any]):
    # Customer payment acknowledgement signature
    signature = payload.get("signature_png")
    if not signature:
        raise HTTPException(400, "Missing signature_png")

    sig_path = save_base64_png(signature, f"{est_id}_payment.png")
    signed_at = now_iso()

    conn = db()
    cur = conn.cursor()
    cur.execute("""
      UPDATE estimates
      SET invoice_status='paid_acknowledged', payment_signature_path=?, payment_signed_at=?
      WHERE id=?
    """, (sig_path, signed_at, est_id))
    conn.commit()

    cur.execute("SELECT * FROM estimates WHERE id=?", (est_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Estimate not found")

    gen_invoice_pdf(row)
    return {"ok": True, "invoice_status": "paid_acknowledged"}

@app.get("/invoice/{est_id}/pdf")
def invoice_pdf(est_id: str):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM estimates WHERE id=?", (est_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Estimate not found")
    pdf_path = os.path.join(PDF_DIR, f"{est_id}_invoice.pdf")
    if not os.path.exists(pdf_path):
        pdf_path = gen_invoice_pdf(row)
    return FileResponse(pdf_path, media_type="application/pdf", filename=f"{est_id}_invoice.pdf")
