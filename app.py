from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import os, json
from pathlib import Path

app = FastAPI()
security = HTTPBasic()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CATALOG_PATH = BASE_DIR / "services_catalog.json"
ESTIMATES_PATH = DATA_DIR / "estimates.json"

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "change_me")

POPULAR_MAKES = [
    "TOYOTA","HONDA","FORD","CHEVROLET","NISSAN","HYUNDAI","KIA","DODGE","JEEP",
    "GMC","SUBARU","BMW","MERCEDES-BENZ","VOLKSWAGEN","AUDI","LEXUS","MAZDA","TESLA", "VOLVO"
]

def require_admin(creds: HTTPBasicCredentials = Depends(security)):
    if creds.username != ADMIN_USER or creds.password != ADMIN_PASS:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True

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

# Serve static assets + index.html at /
app.mount("/static", StaticFiles(directory=BASE_DIR, html=False), name="static")

@app.get("/", response_class=HTMLResponse)
def index():
    # index.html is in project root
    p = BASE_DIR / "index.html"
    if not p.exists():
        return HTMLResponse("<h1>Missing index.html</h1>", status_code=500)
    return HTMLResponse(p.read_text(encoding="utf-8"))

# ---------- Vehicle endpoints ----------
@app.get("/vehicle/years")
def years():
    # Example: 1981 -> current+1
    from datetime import datetime
    y = datetime.utcnow().year + 1
    return list(range(y, 1980, -1))

@app.get("/vehicle/makes")
def makes(year: int):
    return POPULAR_MAKES

@app.get("/vehicle/models")
def models(year: int, make: str):
    # You can replace with real model lookup later
    # For now, keep UI functional
    return ["(Select model)", "CAMRY", "COROLLA", "CIVIC", "ACCORD", "F-150", "SILVERADO", "ALTIMA", "RAV4", "CR-V"]

# ---------- Catalog endpoints ----------
@app.get("/catalog")
def catalog():
    return load_catalog()

@app.get("/categories")
def categories():
    cat = load_catalog()
    return [{"key": c["key"], "name": c["name"]} for c in cat.get("categories", [])]

# ---------- Estimates ----------
@app.post("/estimate")
async def create_estimate(req: Request):
    payload = await req.json()
    rows = load_estimates()
    payload["id"] = len(rows) + 1
    rows.append(payload)
    save_estimates(rows)
    return {"ok": True, "id": payload["id"]}

# ---------- Admin / Shop Owner ----------
@app.get("/admin/estimates")
def admin_estimates(_: bool = Depends(require_admin)):
    return load_estimates()
