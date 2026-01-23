"""
Aerial Leads - Public Facing Website

Property pages that rank on Google, capture inbound leads,
and position you as the go-to cash buyer in your market.
"""

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import pandas as pd
from datetime import datetime
import re
import json
import os
import sys
import logging

logger = logging.getLogger(__name__)

# Setup paths - works both locally and deployed
BASE_DIR = Path(__file__).parent

# Try to import from parent config (local development)
# Fall back to local paths (deployed)
try:
    sys.path.insert(0, str(BASE_DIR.parent))
    from config.settings import PROCESSED_DATA_DIR, DATA_DIR
except ImportError:
    # Deployed standalone - use local data directories
    DATA_DIR = BASE_DIR / "data"
    PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"
    DATA_DIR.mkdir(exist_ok=True)
    PROCESSED_DATA_DIR.mkdir(exist_ok=True)

# Database connection for storing inbound leads
DB_AVAILABLE = False
db_connection = None

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL:
        DB_AVAILABLE = True
        # Initialize inbound_leads table
        conn = psycopg2.connect(DATABASE_URL)
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
        logger.info("Database connected - inbound leads will be saved to PostgreSQL")
except Exception as e:
    logger.warning(f"Database not available, using CSV fallback: {e}")

app = FastAPI(title="Lifeline Home Buyers")

# Setup templates and static files
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Mount static files only if directory exists
static_dir = BASE_DIR / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Lead capture storage
CAPTURED_LEADS_FILE = DATA_DIR / "inbound_leads.csv"


def slugify(text: str) -> str:
    """Convert address to URL-friendly slug."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text


def load_all_leads() -> pd.DataFrame:
    """Load all leads from processed data."""
    leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
    if not leads_file.exists():
        leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

    if leads_file.exists():
        df = pd.read_csv(leads_file)
        # Add slug column
        if 'address' in df.columns:
            df['slug'] = df['address'].apply(slugify)
        return df
    return pd.DataFrame()


def get_property_by_slug(slug: str) -> dict:
    """Find property by URL slug."""
    df = load_all_leads()
    if df.empty:
        return None

    match = df[df['slug'] == slug]
    if match.empty:
        return None

    return match.iloc[0].to_dict()


def save_inbound_lead(data: dict):
    """Save captured lead to database (preferred) or CSV (fallback)."""
    data['captured_at'] = datetime.now().isoformat()

    # Try to save to PostgreSQL database first
    if DB_AVAILABLE:
        try:
            DATABASE_URL = os.environ.get('DATABASE_URL')
            conn = psycopg2.connect(DATABASE_URL)
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
                data.get('lead_type', 'inbound_web'),
                data.get('ip_address', '')
            ))
            conn.commit()
            conn.close()
            logger.info(f"Lead saved to database: {data.get('name')} - {data.get('phone')}")
            return  # Success, no need for CSV fallback
        except Exception as e:
            logger.error(f"Database save failed, falling back to CSV: {e}")

    # Fallback to CSV
    df_columns = [
        'captured_at', 'source_page', 'name', 'phone', 'email',
        'property_address', 'message', 'lead_type', 'ip_address'
    ]

    if CAPTURED_LEADS_FILE.exists():
        df = pd.read_csv(CAPTURED_LEADS_FILE)
    else:
        df = pd.DataFrame(columns=df_columns)

    df = pd.concat([df, pd.DataFrame([data])], ignore_index=True)
    df.to_csv(CAPTURED_LEADS_FILE, index=False)


# ============================================
# PUBLIC ROUTES
# ============================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Homepage - main landing page."""
    df = load_all_leads()

    stats = {
        'total_properties': len(df),
        'probate': len(df[df.get('lead_type', '') == 'probate']) if 'lead_type' in df.columns else 0,
        'tax_delinquent': len(df[df.get('lead_type', '') == 'tax_delinquent']) if 'lead_type' in df.columns else 0,
    }

    return templates.TemplateResponse("home.html", {
        "request": request,
        "stats": stats,
        "page_title": "Lifeline Home Buyers | We Buy Houses Ohio - Cash Offers in 24 Hours",
        "meta_description": "Lifeline Home Buyers - the help that wasn't there for my family is here for yours. We buy houses in any condition - probate, tax liens, foreclosure. Fair cash offers."
    })


@app.get("/properties", response_class=HTMLResponse)
async def property_list(request: Request, page: int = 1, type: str = None):
    """List all properties or filter by type."""
    df = load_all_leads()

    # Filter by type if specified
    if type and 'lead_type' in df.columns:
        df = df[df['lead_type'] == type]

    # Pagination
    per_page = 50
    total = len(df)
    total_pages = (total + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page

    properties = df.iloc[start:end].to_dict('records')

    return templates.TemplateResponse("property_list.html", {
        "request": request,
        "properties": properties,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "filter_type": type,
        "page_title": f"Distressed Properties in Columbus, Ohio | Page {page}",
        "meta_description": f"Browse {total} distressed properties in Columbus, Ohio. Tax delinquent, probate, and code violation properties available."
    })


@app.get("/property/{slug}", response_class=HTMLResponse)
async def property_detail(request: Request, slug: str):
    """Individual property page - THE KEY FOR SEO."""
    property_data = get_property_by_slug(slug)

    if not property_data:
        raise HTTPException(status_code=404, detail="Property not found")

    address = property_data.get('address', 'Unknown Address')
    city = property_data.get('city', 'Columbus')
    lead_type = property_data.get('lead_type', 'distressed')

    # Build SEO-optimized title and description
    page_title = f"Sell {address} Fast for Cash | We Buy Houses {city}"
    meta_description = f"Get a cash offer for {address} in {city}, Ohio. We buy {lead_type} properties in any condition. No repairs, no fees, close fast."

    return templates.TemplateResponse("property_detail.html", {
        "request": request,
        "property": property_data,
        "page_title": page_title,
        "meta_description": meta_description,
        "slug": slug
    })


@app.get("/get-offer", response_class=HTMLResponse)
async def get_offer_page(request: Request):
    """Cash offer form page."""
    return templates.TemplateResponse("get_offer.html", {
        "request": request,
        "page_title": "Get Your Free Cash Offer | Lifeline Home Buyers",
        "meta_description": "Get a no-obligation cash offer for your Ohio property in 24 hours. Any condition, any situation. Lifeline Home Buyers is here to help."
    })


@app.get("/calculator", response_class=HTMLResponse)
async def offer_calculator(request: Request):
    """Interactive cash offer calculator - lead magnet."""
    return templates.TemplateResponse("offer_calculator.html", {
        "request": request,
        "page_title": "Free Cash Offer Calculator | Lifeline Home Buyers",
        "meta_description": "Find out what your property is worth in 60 seconds. Free cash offer calculator - no obligation, instant estimate."
    })


@app.get("/probate", response_class=HTMLResponse)
async def probate_page(request: Request):
    """Probate-specific landing page."""
    df = load_all_leads()

    if 'lead_type' in df.columns:
        probate_properties = df[df['lead_type'] == 'probate'].head(20).to_dict('records')
    else:
        probate_properties = []

    return templates.TemplateResponse("probate.html", {
        "request": request,
        "properties": probate_properties,
        "page_title": "Sell Inherited Property Ohio | Lifeline Home Buyers",
        "meta_description": "Inherited a property? Lifeline Home Buyers purchases probate and inherited houses for cash. No repairs, no cleaning, no stress. Get an offer today."
    })


@app.get("/tax-delinquent", response_class=HTMLResponse)
async def tax_delinquent_page(request: Request):
    """Tax delinquent landing page."""
    df = load_all_leads()

    if 'lead_type' in df.columns:
        tax_properties = df[df['lead_type'] == 'tax_delinquent'].head(20).to_dict('records')
    else:
        tax_properties = []

    return templates.TemplateResponse("tax_delinquent.html", {
        "request": request,
        "properties": tax_properties,
        "page_title": "Behind on Property Taxes? | Lifeline Home Buyers",
        "meta_description": "Behind on property taxes? I know that pain - my family lost our home. Lifeline Home Buyers helps homeowners get cash before it's too late."
    })


@app.get("/about", response_class=HTMLResponse)
async def about_page(request: Request):
    """About us page."""
    return templates.TemplateResponse("about.html", {
        "request": request,
        "page_title": "My Story | Lifeline Home Buyers - Willy Shumbusho",
        "meta_description": "I watched my father lose our home to tax delinquency. No one helped. That's why I started Lifeline Home Buyers - to be there when no one else is."
    })


# ============================================
# FORM SUBMISSIONS (Lead Capture)
# ============================================

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
    """Handle lead form submissions."""

    # Get client IP
    ip_address = request.client.host if request.client else "unknown"

    lead_data = {
        'name': name,
        'phone': phone,
        'email': email or '',
        'property_address': property_address,
        'message': message or '',
        'source_page': source_page or 'unknown',
        'lead_type': 'inbound_web',
        'ip_address': ip_address
    }

    save_inbound_lead(lead_data)

    # Redirect to thank you page
    return RedirectResponse(url="/thank-you", status_code=303)


@app.get("/thank-you", response_class=HTMLResponse)
async def thank_you(request: Request):
    """Thank you page after form submission."""
    return templates.TemplateResponse("thank_you.html", {
        "request": request,
        "page_title": "Thank You | We'll Contact You Soon",
        "meta_description": "Thank you for your submission. Our team will contact you within 24 hours with a cash offer."
    })


# ============================================
# PUBLIC DATABASE / MAP
# ============================================

@app.get("/database", response_class=HTMLResponse)
async def property_database(
    request: Request,
    page: int = 1,
    type: str = None,
    zip: str = None,
    sort: str = "recent",
    search: str = None
):
    """
    Public searchable database of distressed properties with interactive map.
    Great for SEO - people searching for distressed properties in Columbus.
    """
    df = load_all_leads()

    if df.empty:
        return templates.TemplateResponse("property_map.html", {
            "request": request,
            "properties": [],
            "map_properties": [],
            "total": 0,
            "showing": 0,
            "probate_count": 0,
            "tax_count": 0,
            "violation_count": 0,
            "zip_codes": [],
            "page": 1,
            "total_pages": 1,
            "filter_type": type,
            "filter_zip": zip,
            "sort_by": sort,
            "search_query": search or "",
            "page_title": "Columbus Distressed Property Database | Lifeline Home Buyers",
            "meta_description": "Free searchable database of distressed properties in Columbus, Ohio. Find probate, tax delinquent, and code violation properties."
        })

    # Get stats before filtering
    total_all = len(df)
    probate_count = len(df[df['lead_type'] == 'probate']) if 'lead_type' in df.columns else 0
    tax_count = len(df[df['lead_type'] == 'tax_delinquent']) if 'lead_type' in df.columns else 0
    violation_count = len(df[df['lead_type'] == 'code_violation']) if 'lead_type' in df.columns else 0

    # Get unique ZIP codes for filter
    zip_codes = []
    if 'zip' in df.columns:
        zip_codes = sorted(df['zip'].dropna().unique().tolist())

    # Apply filters
    filtered_df = df.copy()

    if type and 'lead_type' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['lead_type'] == type]

    if zip and 'zip' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['zip'] == zip]

    if search:
        search_lower = search.lower()
        mask = filtered_df['address'].str.lower().str.contains(search_lower, na=False)
        if 'zip' in filtered_df.columns:
            mask = mask | filtered_df['zip'].astype(str).str.contains(search, na=False)
        filtered_df = filtered_df[mask]

    # Apply sorting
    if sort == "score" and 'motivation_score' in filtered_df.columns:
        filtered_df = filtered_df.sort_values('motivation_score', ascending=False)
    elif sort == "address" and 'address' in filtered_df.columns:
        filtered_df = filtered_df.sort_values('address')
    # Default: recent (by scraped_at if available)

    # Pagination
    per_page = 24
    total = len(filtered_df)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page

    page_df = filtered_df.iloc[start:end]
    properties = page_df.to_dict('records')

    # Prepare map data (first 200 with coordinates)
    map_df = filtered_df.head(200)
    map_properties = []
    for _, row in map_df.iterrows():
        prop = {
            'address': row.get('address', ''),
            'city': row.get('city', 'Columbus'),
            'state': row.get('state', 'OH'),
            'zip': row.get('zip', ''),
            'lead_type': row.get('lead_type', ''),
            'motivation_score': row.get('motivation_score', 0),
            'slug': row.get('slug', ''),
            'lat': row.get('latitude') or row.get('lat'),
            'lng': row.get('longitude') or row.get('lng') or row.get('lon')
        }
        map_properties.append(prop)

    return templates.TemplateResponse("property_map.html", {
        "request": request,
        "properties": properties,
        "map_properties": map_properties,
        "total": total_all,
        "showing": len(properties),
        "probate_count": probate_count,
        "tax_count": tax_count,
        "violation_count": violation_count,
        "zip_codes": zip_codes,
        "page": page,
        "total_pages": total_pages,
        "filter_type": type or "",
        "filter_zip": zip or "",
        "sort_by": sort,
        "search_query": search or "",
        "page_title": f"Columbus Distressed Property Database | {total_all} Properties | Lifeline Home Buyers",
        "meta_description": f"Free searchable database of {total_all} distressed properties in Columbus, Ohio. Find probate, tax delinquent, and code violation properties."
    })


# ============================================
# SEO ROUTES
# ============================================

@app.get("/sitemap.xml")
async def sitemap():
    """Generate dynamic sitemap for SEO."""
    df = load_all_leads()

    base_url = "https://lifelinehomebuyers.com"  # Update with actual domain when live

    urls = [
        {"loc": f"{base_url}/", "priority": "1.0"},
        {"loc": f"{base_url}/database", "priority": "0.9"},
        {"loc": f"{base_url}/get-offer", "priority": "0.9"},
        {"loc": f"{base_url}/calculator", "priority": "0.8"},
        {"loc": f"{base_url}/probate", "priority": "0.8"},
        {"loc": f"{base_url}/tax-delinquent", "priority": "0.8"},
        {"loc": f"{base_url}/about", "priority": "0.5"},
    ]

    # Add all property pages
    for _, row in df.iterrows():
        if 'slug' in row:
            urls.append({
                "loc": f"{base_url}/property/{row['slug']}",
                "priority": "0.7"
            })

    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    for url in urls:
        xml_content += f'  <url>\n'
        xml_content += f'    <loc>{url["loc"]}</loc>\n'
        xml_content += f'    <priority>{url["priority"]}</priority>\n'
        xml_content += f'  </url>\n'

    xml_content += '</urlset>'

    return HTMLResponse(content=xml_content, media_type="application/xml")


@app.get("/robots.txt")
async def robots():
    """Robots.txt for search engines."""
    content = """User-agent: *
Allow: /

Sitemap: https://lifelinehomebuyers.com/sitemap.xml
"""
    return HTMLResponse(content=content, media_type="text/plain")


# ============================================
# API ENDPOINTS (for internal use)
# ============================================

@app.get("/api/properties")
async def api_properties(limit: int = 100, offset: int = 0):
    """API endpoint to get properties as JSON."""
    df = load_all_leads()

    properties = df.iloc[offset:offset+limit].to_dict('records')

    return {
        "total": len(df),
        "limit": limit,
        "offset": offset,
        "properties": properties
    }


@app.get("/api/inbound-leads")
async def api_inbound_leads():
    """API endpoint to get captured inbound leads."""
    if CAPTURED_LEADS_FILE.exists():
        df = pd.read_csv(CAPTURED_LEADS_FILE)
        return {"leads": df.to_dict('records')}
    return {"leads": []}


# ============================================
# RUN SERVER
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
