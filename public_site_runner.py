#!/usr/bin/env python3
"""
Lifeline Home Buyers - Public Site
Clean standalone version for Railway deployment.
"""
import os
import sys
from pathlib import Path
from datetime import datetime

# Setup
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "public_site" / "templates"
DATA_DIR = BASE_DIR / "public_site" / "data"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import pandas as pd
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup - lazy connection
DATABASE_URL = os.environ.get('DATABASE_URL', '')
DB_AVAILABLE = False

def get_db_connection():
    """Get database connection (lazy initialization)."""
    global DB_AVAILABLE
    if not DATABASE_URL:
        return None
    try:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        DB_AVAILABLE = True
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None

def init_database():
    """Create tables if they don't exist."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inbound_leads (
                id SERIAL PRIMARY KEY,
                captured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source_page VARCHAR(255),
                name VARCHAR(255),
                phone VARCHAR(50),
                email VARCHAR(255),
                property_address TEXT,
                message TEXT,
                lead_type VARCHAR(50) DEFAULT 'inbound_web',
                ip_address VARCHAR(50),
                status VARCHAR(50) DEFAULT 'new',
                assigned_to VARCHAR(100),
                notes TEXT
            )
        """)
        conn.commit()
        conn.close()
        logger.info("Database initialized")
        return True
    except Exception as e:
        logger.error(f"Database init failed: {e}")
        return False

def save_lead_to_db(data: dict):
    """Save lead to database."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO inbound_leads
            (captured_at, source_page, name, phone, email, property_address, message, lead_type, ip_address)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            data.get('captured_at'),
            data.get('source_page', ''),
            data.get('name', ''),
            data.get('phone', ''),
            data.get('email', ''),
            data.get('property_address', ''),
            data.get('message', ''),
            'inbound_web',
            data.get('ip_address', '')
        ))
        conn.commit()
        conn.close()
        logger.info(f"Lead saved: {data.get('name')}")
        return True
    except Exception as e:
        logger.error(f"Failed to save lead: {e}")
        return False

def load_leads():
    """Load leads from CSV file."""
    leads_file = PROCESSED_DATA_DIR / "columbus_oh_all_leads.csv"
    if leads_file.exists():
        try:
            return pd.read_csv(leads_file)
        except Exception as e:
            logger.error(f"Failed to load leads: {e}")
    return pd.DataFrame()

app = FastAPI(title="Lifeline Home Buyers")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    init_database()

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "templates": str(TEMPLATES_DIR),
        "exists": TEMPLATES_DIR.exists(),
        "db_available": DB_AVAILABLE,
        "db_url_set": bool(DATABASE_URL)
    }

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    df = load_leads()
    stats = {
        'total_properties': len(df),
        'probate': len(df[df['lead_type'] == 'probate']) if 'lead_type' in df.columns and len(df) > 0 else 0,
        'tax_delinquent': len(df[df['lead_type'] == 'tax_delinquent']) if 'lead_type' in df.columns and len(df) > 0 else 0,
    }
    return templates.TemplateResponse("home.html", {
        "request": request,
        "stats": stats,
        "page_title": "Lifeline Home Buyers | We Buy Houses Ohio",
        "meta_description": "We buy houses in any condition - cash offers in 24 hours."
    })

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse("about.html", {
        "request": request,
        "page_title": "About | Lifeline Home Buyers",
        "meta_description": "Our story - why we started Lifeline Home Buyers."
    })

@app.get("/get-offer", response_class=HTMLResponse)
async def get_offer(request: Request):
    return templates.TemplateResponse("get_offer.html", {
        "request": request,
        "page_title": "Get Cash Offer | Lifeline Home Buyers",
        "meta_description": "Get a free cash offer for your property."
    })

@app.get("/probate", response_class=HTMLResponse)
async def probate(request: Request):
    df = load_leads()
    properties = []
    if 'lead_type' in df.columns and len(df) > 0:
        properties = df[df['lead_type'] == 'probate'].head(20).to_dict('records')
    return templates.TemplateResponse("probate.html", {
        "request": request,
        "properties": properties,
        "page_title": "Probate Properties | Lifeline Home Buyers",
        "meta_description": "We help with inherited and probate properties."
    })

@app.get("/tax-delinquent", response_class=HTMLResponse)
async def tax_delinquent(request: Request):
    df = load_leads()
    properties = []
    if 'lead_type' in df.columns and len(df) > 0:
        properties = df[df['lead_type'] == 'tax_delinquent'].head(20).to_dict('records')
    return templates.TemplateResponse("tax_delinquent.html", {
        "request": request,
        "properties": properties,
        "page_title": "Tax Delinquent Help | Lifeline Home Buyers",
        "meta_description": "Behind on taxes? We can help."
    })

@app.get("/calculator", response_class=HTMLResponse)
async def calculator(request: Request):
    return templates.TemplateResponse("offer_calculator.html", {
        "request": request,
        "page_title": "Cash Offer Calculator | Lifeline Home Buyers",
        "meta_description": "Calculate your cash offer."
    })

@app.get("/database", response_class=HTMLResponse)
async def property_database(request: Request, page: int = 1, type: str = None):
    """Property database with map."""
    df = load_leads()

    # Get stats
    total_all = len(df)
    probate_count = len(df[df['lead_type'] == 'probate']) if 'lead_type' in df.columns and len(df) > 0 else 0
    tax_count = len(df[df['lead_type'] == 'tax_delinquent']) if 'lead_type' in df.columns and len(df) > 0 else 0
    violation_count = len(df[df['lead_type'] == 'code_violation']) if 'lead_type' in df.columns and len(df) > 0 else 0

    # Filter
    filtered_df = df.copy()
    if type and 'lead_type' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['lead_type'] == type]

    # Pagination
    per_page = 24
    total = len(filtered_df)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page

    properties = filtered_df.iloc[start:end].to_dict('records') if len(filtered_df) > 0 else []

    # Map data
    map_properties = []
    if len(filtered_df) > 0:
        for _, row in filtered_df.head(200).iterrows():
            map_properties.append({
                'address': row.get('address', ''),
                'city': row.get('city', 'Columbus'),
                'lead_type': row.get('lead_type', ''),
                'lat': row.get('latitude') or row.get('lat'),
                'lng': row.get('longitude') or row.get('lng') or row.get('lon')
            })

    return templates.TemplateResponse("property_map.html", {
        "request": request,
        "properties": properties,
        "map_properties": map_properties,
        "total": total_all,
        "showing": len(properties),
        "probate_count": probate_count,
        "tax_count": tax_count,
        "violation_count": violation_count,
        "zip_codes": [],
        "page": page,
        "total_pages": total_pages,
        "filter_type": type or "",
        "filter_zip": "",
        "sort_by": "recent",
        "search_query": "",
        "page_title": "Property Database | Lifeline Home Buyers",
        "meta_description": "Search distressed properties in Columbus, Ohio."
    })

@app.get("/thank-you", response_class=HTMLResponse)
async def thank_you(request: Request):
    return templates.TemplateResponse("thank_you.html", {
        "request": request,
        "page_title": "Thank You | Lifeline Home Buyers",
        "meta_description": "We'll contact you soon."
    })

@app.post("/submit-lead")
async def submit_lead(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(None),
    property_address: str = Form(...),
    message: str = Form(None),
    source_page: str = Form(None)
):
    ip_address = request.client.host if request.client else "unknown"

    lead_data = {
        'captured_at': datetime.now().isoformat(),
        'name': name,
        'phone': phone,
        'email': email or '',
        'property_address': property_address,
        'message': message or '',
        'source_page': source_page or 'unknown',
        'ip_address': ip_address
    }

    saved = save_lead_to_db(lead_data)
    logger.info(f"Lead received: {name} - {phone} (saved to db: {saved})")

    return RedirectResponse(url="/thank-you", status_code=303)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
