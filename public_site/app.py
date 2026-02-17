"""
Lifeline Home Buyers - Public Facing Website

Property pages that rank on Google, capture inbound leads,
and position you as the go-to cash buyer in your market.
"""

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from pathlib import Path
import pandas as pd
from datetime import datetime
import re
import json
import os
import sys
import logging
import yaml
import markdown

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup paths - works both locally and deployed
BASE_DIR = Path(__file__).parent
logger.info(f"BASE_DIR: {BASE_DIR}")
logger.info(f"Templates dir: {BASE_DIR / 'templates'}")
logger.info(f"Templates exist: {(BASE_DIR / 'templates').exists()}")

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
DATABASE_URL = os.environ.get('DATABASE_URL', '')

# Check if psycopg2 is available
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.warning("psycopg2 not available")

def init_database():
    """Initialize database table (called on first request, not at startup)."""
    global DB_AVAILABLE
    if not PSYCOPG2_AVAILABLE or not DATABASE_URL:
        return False
    try:
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
        DB_AVAILABLE = True
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.warning(f"Database init failed: {e}")
        return False

app = FastAPI(title="Lifeline Home Buyers")


# ============================================
# CACHE HEADERS MIDDLEWARE
# ============================================

class CacheHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/static"):
            response.headers["Cache-Control"] = "public, max-age=31536000"
        elif request.url.path in ("/sitemap.xml", "/robots.txt"):
            response.headers["Cache-Control"] = "public, max-age=3600"
        else:
            response.headers["Cache-Control"] = "public, max-age=300"
        return response

app.add_middleware(CacheHeaderMiddleware)


# ============================================
# NEIGHBORHOOD DATA
# ============================================

NEIGHBORHOODS = {
    "linden": {
        "name": "Linden",
        "zip": "43211",
        "desc": "Linden is one of Columbus's most established neighborhoods on the near east and northeast side. With a large inventory of single-family homes built in the early-to-mid 20th century, Linden presents significant opportunity for homeowners looking to sell properties that may need updates or have fallen behind on taxes.",
        "long_desc": "Linden is a neighborhood in northeast Columbus known for its tree-lined streets and historic housing stock. Many properties in the 43211 zip code are single-family homes built between 1920 and 1960. The area has seen increased investor activity as Columbus continues to grow, and property values have been steadily rising. However, many long-time homeowners face challenges with deferred maintenance, rising property taxes, and inherited properties. Lifeline Home Buyers is actively acquiring in Linden and provides fair cash offers for properties in any condition.",
        "property_types": [
            {"title": "Tax Delinquent Properties", "desc": "Many Linden homeowners face accumulated tax debt. We resolve all back taxes at closing so you walk away clean."},
            {"title": "Inherited Homes", "desc": "Probate properties from long-time Linden families. We coordinate with estate attorneys and handle title issues."},
            {"title": "Deferred Maintenance", "desc": "Older homes needing roof, foundation, plumbing, or electrical work. We buy as-is, no repairs required."},
            {"title": "Vacant Properties", "desc": "Vacant homes accumulating code violations and carrying costs. Sell before the costs outweigh the equity."},
        ],
    },
    "franklinton": {
        "name": "Franklinton",
        "zip": "43222",
        "desc": "Franklinton is one of Columbus's oldest neighborhoods, located just west of downtown across the Scioto River. The area is undergoing significant redevelopment, creating opportunity for homeowners to capture rising values — especially for properties that need work.",
        "long_desc": "Franklinton sits directly west of downtown Columbus and is one of the city's most rapidly changing neighborhoods. New development along West Broad Street and the Scioto Peninsula has driven property values upward, but many long-time residents own older homes that need significant work. The 43222 zip code contains a mix of single-family homes, duplexes, and small multi-family properties. For homeowners who can't afford renovations to capitalize on rising values, selling for cash allows them to capture equity now rather than watching it erode through carrying costs.",
        "property_types": [
            {"title": "Properties Near Redevelopment", "desc": "Franklinton's growth means your property may be worth more than you think. Get a current valuation."},
            {"title": "Older Single-Family Homes", "desc": "Turn-of-century homes needing complete renovation. We purchase regardless of condition."},
            {"title": "Duplexes & Small Multi-Family", "desc": "Rental properties with tenant issues or deferred maintenance. We buy with tenants in place."},
            {"title": "Flood Zone Properties", "desc": "Properties in flood-prone areas that are difficult to insure or finance traditionally."},
        ],
    },
    "near-east-side": {
        "name": "Near East Side",
        "zip": "43203",
        "desc": "The Near East Side is centrally located just east of downtown Columbus. With proximity to major employers and institutions, the area has strong fundamentals — but many properties have deferred maintenance or complicated title situations.",
        "long_desc": "The Near East Side neighborhood in the 43203 zip code is one of Columbus's most centrally located residential areas. Its proximity to downtown, Columbus State Community College, and major medical facilities makes it attractive for redevelopment. Property values have been appreciating as the neighborhood continues to evolve. Many properties in the area are older single-family homes and small multi-family buildings that have been in the same families for decades. Lifeline works with homeowners who need to sell inherited properties, resolve tax issues, or simply move on from a property they can no longer maintain.",
        "property_types": [
            {"title": "Probate & Inherited Properties", "desc": "Multi-generational homes where heirs need a clean resolution. We handle all title coordination."},
            {"title": "Tax Delinquent Properties", "desc": "Properties with accumulated tax debt. We clear all liens and back taxes at closing."},
            {"title": "Code Violation Properties", "desc": "Homes with outstanding city code violations. Sell before fines accumulate further."},
            {"title": "Occupied Properties", "desc": "Need to sell but still living there? We offer flexible closing dates and leaseback options."},
        ],
    },
    "south-side": {
        "name": "South Side",
        "zip": "43207",
        "desc": "Columbus's South Side is a working-class neighborhood with affordable housing stock and a strong sense of community. Many homeowners here face challenges with aging properties and rising costs.",
        "long_desc": "The South Side of Columbus, primarily in the 43207 zip code, is a large residential area south of downtown. The neighborhood features predominantly single-family homes built from the 1940s through the 1970s. It's a working-class community where many families have owned homes for generations. Rising property taxes, aging infrastructure, and deferred maintenance are common challenges. Lifeline Home Buyers provides South Side homeowners with a straightforward path to sell their property for cash without the burden of repairs or the uncertainty of a traditional listing.",
        "property_types": [
            {"title": "Aging Housing Stock", "desc": "Homes from the 1940s-1970s that need updates. We buy regardless of condition — roof, plumbing, electrical, all of it."},
            {"title": "Tax Delinquent Properties", "desc": "South Side properties with accumulated tax debt. Resolve the balance and keep your equity."},
            {"title": "Estate Sales", "desc": "Family homes being sold after a parent or grandparent passes. We make the process simple."},
            {"title": "Rental Properties", "desc": "Tired of being a landlord? Sell your rental property as-is, tenants and all."},
        ],
    },
    "hilltop": {
        "name": "Hilltop",
        "zip": "43228",
        "desc": "The Hilltop is a large neighborhood on Columbus's west side with one of the highest concentrations of distressed properties in the city. Lifeline is actively acquiring here and providing homeowners with fair cash offers.",
        "long_desc": "The Hilltop neighborhood in west Columbus (43228) is one of the largest residential areas in the city. Known for its affordable housing stock, the area has a high proportion of properties needing renovation. Many homes were built in the 1950s-1970s and have significant deferred maintenance. The neighborhood also has one of the higher rates of tax delinquency in Franklin County. For Hilltop homeowners, selling for cash is often the most practical option — especially when repair costs would exceed the potential increase in sale price. Lifeline Home Buyers is one of the most active cash buyers in the Hilltop area.",
        "property_types": [
            {"title": "Major Renovation Properties", "desc": "Homes needing $30,000+ in work. Foundation, roof, HVAC — we take it all as-is."},
            {"title": "Tax Delinquent Properties", "desc": "The Hilltop has high tax delinquency rates. We resolve back taxes and get you cash at closing."},
            {"title": "Fire & Water Damaged", "desc": "Properties damaged by fire, flooding, or other events. We purchase regardless of damage extent."},
            {"title": "Vacant & Abandoned", "desc": "Properties sitting empty and accumulating violations. Convert a liability into cash."},
        ],
    },
    "german-village": {
        "name": "German Village",
        "zip": "43206",
        "desc": "German Village is one of Columbus's most desirable historic neighborhoods. Properties here command premium prices, but even in German Village, homeowners face situations where a quick cash sale makes sense.",
        "long_desc": "German Village, located just south of downtown Columbus in the 43206 zip code, is one of the city's premier historic neighborhoods. Listed on the National Register of Historic Places, the area features beautifully preserved brick homes, tree-lined streets, and a vibrant commercial district. While property values are among the highest in Columbus, homeowners here still face situations that require a fast, certain sale: divorce, relocation, inherited properties, or homes that need historic-compliant renovations that can be extremely expensive. Lifeline Home Buyers works with German Village homeowners to provide competitive cash offers that reflect the area's premium values.",
        "property_types": [
            {"title": "Historic Properties", "desc": "Homes requiring expensive historic-compliant renovations. We understand the value and buy accordingly."},
            {"title": "Inherited Properties", "desc": "Premium real estate inherited by out-of-state heirs. We provide a simple path to liquidity."},
            {"title": "Divorce Sales", "desc": "When both parties need a clean, fast resolution on a high-value property."},
            {"title": "Relocation Sales", "desc": "Need to move for work? Close on your German Village home in days, not months."},
        ],
    },
}


# ============================================
# BLOG POST LOADING
# ============================================

BLOG_POSTS_DIR = BASE_DIR / "blog_posts"


def load_blog_posts():
    """Load all blog posts from markdown files with YAML frontmatter."""
    posts = []
    if not BLOG_POSTS_DIR.exists():
        return posts

    for md_file in BLOG_POSTS_DIR.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            # Split frontmatter from content
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    body = parts[2].strip()
                    frontmatter["body"] = body
                    frontmatter["file"] = md_file.name
                    if isinstance(frontmatter.get("date"), str):
                        frontmatter["date"] = frontmatter["date"]
                    else:
                        frontmatter["date"] = str(frontmatter.get("date", ""))
                    posts.append(frontmatter)
        except Exception as e:
            logger.warning(f"Error loading blog post {md_file}: {e}")

    # Sort by date descending
    posts.sort(key=lambda p: p.get("date", ""), reverse=True)
    return posts


def get_blog_post(slug: str):
    """Get a single blog post by slug."""
    posts = load_blog_posts()
    for post in posts:
        if post.get("slug") == slug:
            return post
    return None


# Health check endpoint (no templates needed)
@app.get("/health")
async def health_check():
    """Health check endpoint for debugging."""
    templates_dir = BASE_DIR / "templates"
    return JSONResponse({
        "status": "ok",
        "base_dir": str(BASE_DIR),
        "templates_dir": str(templates_dir),
        "templates_exist": templates_dir.exists(),
        "template_files": [f.name for f in templates_dir.glob("*.html")] if templates_dir.exists() else [],
        "db_available": DB_AVAILABLE,
        "cwd": os.getcwd()
    })

# Setup templates and static files
templates_dir = BASE_DIR / "templates"
if not templates_dir.exists():
    logger.error(f"Templates directory not found: {templates_dir}")
    # Try alternate location
    alt_templates = Path(os.getcwd()) / "public_site" / "templates"
    if alt_templates.exists():
        templates_dir = alt_templates
        logger.info(f"Using alternate templates dir: {templates_dir}")

templates = Jinja2Templates(directory=str(templates_dir))

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
    global DB_AVAILABLE
    data['captured_at'] = datetime.now().isoformat()

    # Initialize database on first use
    if not DB_AVAILABLE and PSYCOPG2_AVAILABLE and DATABASE_URL:
        init_database()

    # Try to save to PostgreSQL database first
    if DB_AVAILABLE and PSYCOPG2_AVAILABLE:
        try:
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
        "meta_description": "Lifeline Home Buyers - the help that wasn't there for my family is here for yours. We buy houses in any condition - probate, tax liens, foreclosure. Fair cash offers.",
        "breadcrumbs": [
            {"name": "Home", "url": "https://life-line-homebuyers.com/"},
        ],
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
        "meta_description": "I watched my father lose our home to tax delinquency. No one helped. That's why I started Lifeline Home Buyers - to be there when no one else is.",
        "breadcrumbs": [
            {"name": "Home", "url": "https://life-line-homebuyers.com/"},
            {"name": "About", "url": "https://life-line-homebuyers.com/about"},
        ],
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
async def sitemap(request: Request):
    """Generate dynamic sitemap for SEO."""
    df = load_all_leads()

    # Use actual host from request, fallback to custom domain
    host = request.headers.get('host', 'lifelinehome-buyers.com')
    scheme = 'https'
    base_url = f"{scheme}://{host}"

    urls = [
        {"loc": f"{base_url}/", "priority": "1.0", "changefreq": "daily"},
        {"loc": f"{base_url}/get-offer", "priority": "0.9", "changefreq": "weekly"},
        {"loc": f"{base_url}/database", "priority": "0.9", "changefreq": "daily"},
        {"loc": f"{base_url}/calculator", "priority": "0.8", "changefreq": "monthly"},
        {"loc": f"{base_url}/probate", "priority": "0.8", "changefreq": "weekly"},
        {"loc": f"{base_url}/tax-delinquent", "priority": "0.8", "changefreq": "weekly"},
        {"loc": f"{base_url}/sell-my-house-fast-columbus-ohio", "priority": "0.9", "changefreq": "weekly"},
        {"loc": f"{base_url}/we-buy-houses-columbus", "priority": "0.9", "changefreq": "weekly"},
        {"loc": f"{base_url}/about", "priority": "0.6", "changefreq": "monthly"},
        {"loc": f"{base_url}/blog", "priority": "0.7", "changefreq": "weekly"},
    ]

    # Add neighborhood pages
    for slug in NEIGHBORHOODS:
        urls.append({
            "loc": f"{base_url}/we-buy-houses-{slug}",
            "priority": "0.85",
            "changefreq": "weekly"
        })

    # Add blog posts
    blog_posts = load_blog_posts()
    for post in blog_posts:
        urls.append({
            "loc": f"{base_url}/blog/{post['slug']}",
            "priority": "0.6",
            "changefreq": "monthly"
        })

    # Add all property pages
    for _, row in df.iterrows():
        if 'slug' in row:
            urls.append({
                "loc": f"{base_url}/property/{row['slug']}",
                "priority": "0.7",
                "changefreq": "weekly"
            })

    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'

    for url in urls:
        xml_content += f'  <url>\n'
        xml_content += f'    <loc>{url["loc"]}</loc>\n'
        xml_content += f'    <changefreq>{url["changefreq"]}</changefreq>\n'
        xml_content += f'    <priority>{url["priority"]}</priority>\n'
        xml_content += f'  </url>\n'

    xml_content += '</urlset>'

    return HTMLResponse(content=xml_content, media_type="application/xml")


@app.get("/robots.txt")
async def robots(request: Request):
    """Robots.txt for search engines."""
    host = request.headers.get('host', 'lifelinehome-buyers.com')
    content = f"""User-agent: *
Allow: /
Disallow: /api/

Sitemap: https://{host}/sitemap.xml
"""
    return HTMLResponse(content=content, media_type="text/plain")


# ============================================
# NEIGHBORHOOD PAGES
# ============================================

@app.get("/we-buy-houses-{slug}", response_class=HTMLResponse)
async def neighborhood_page(request: Request, slug: str):
    """Neighborhood-specific landing pages for hyper-local SEO."""
    if slug == "columbus":
        # This is the existing we-buy-houses-columbus route
        return templates.TemplateResponse("we_buy_houses.html", {
            "request": request,
            "page_title": "We Buy Houses Columbus OH | Cash Home Buyers | Lifeline Home Buyers",
            "meta_description": "We buy houses in Columbus, Ohio - any condition, any situation. Facing foreclosure? Inherited a property? Behind on taxes? Get a cash offer today. No obligation.",
            "breadcrumbs": [
                {"name": "Home", "url": "https://life-line-homebuyers.com/"},
                {"name": "We Buy Houses Columbus", "url": "https://life-line-homebuyers.com/we-buy-houses-columbus"},
            ],
        })

    neighborhood = NEIGHBORHOODS.get(slug)
    if not neighborhood:
        raise HTTPException(status_code=404, detail="Neighborhood not found")

    return templates.TemplateResponse("neighborhood.html", {
        "request": request,
        "neighborhood": neighborhood,
        "slug": slug,
        "page_title": f"We Buy Houses {neighborhood['name']} Columbus OH | Cash Offer | Lifeline Home Buyers",
        "meta_description": f"We buy houses in {neighborhood['name']}, Columbus OH ({neighborhood['zip']}). Cash offers in 24 hours, close in 7 days. Any condition. No fees. Call (614) 825-3368.",
        "breadcrumbs": [
            {"name": "Home", "url": "https://life-line-homebuyers.com/"},
            {"name": f"We Buy Houses {neighborhood['name']}", "url": f"https://life-line-homebuyers.com/we-buy-houses-{slug}"},
        ],
    })


# ============================================
# BLOG ROUTES
# ============================================

@app.get("/blog", response_class=HTMLResponse)
async def blog_list(request: Request, page: int = 1):
    """Blog listing page."""
    posts = load_blog_posts()
    per_page = 10
    total_pages = max(1, (len(posts) + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page
    page_posts = posts[start:end]

    return templates.TemplateResponse("blog_list.html", {
        "request": request,
        "posts": page_posts,
        "page": page,
        "total_pages": total_pages,
        "page_title": "Homeowner Resources & Guides | Lifeline Home Buyers Blog",
        "meta_description": "Guides and resources for Ohio homeowners — selling inherited property, dealing with tax delinquency, cash home sales, and the Columbus real estate market.",
        "breadcrumbs": [
            {"name": "Home", "url": "https://life-line-homebuyers.com/"},
            {"name": "Blog", "url": "https://life-line-homebuyers.com/blog"},
        ],
    })


@app.get("/blog/{slug}", response_class=HTMLResponse)
async def blog_post_page(request: Request, slug: str):
    """Individual blog post page."""
    post = get_blog_post(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found")

    # Convert markdown to HTML
    html_content = markdown.markdown(
        post["body"],
        extensions=["tables", "fenced_code", "nl2br"]
    )

    # Get related posts (other posts, excluding current)
    all_posts = load_blog_posts()
    related_posts = [p for p in all_posts if p.get("slug") != slug][:3]

    return templates.TemplateResponse("blog_post.html", {
        "request": request,
        "post": post,
        "content": html_content,
        "related_posts": related_posts,
        "page_title": f"{post['title']} | Lifeline Home Buyers",
        "meta_description": post.get("description", ""),
        "breadcrumbs": [
            {"name": "Home", "url": "https://life-line-homebuyers.com/"},
            {"name": "Blog", "url": "https://life-line-homebuyers.com/blog"},
            {"name": post["title"], "url": f"https://life-line-homebuyers.com/blog/{slug}"},
        ],
    })


# ============================================
# SEO LANDING PAGES (High-Value Keywords)
# ============================================

@app.get("/sell-my-house-fast-columbus-ohio", response_class=HTMLResponse)
async def sell_house_fast_columbus(request: Request):
    """Primary SEO landing page - highest search volume keyword."""
    return templates.TemplateResponse("sell_house_fast.html", {
        "request": request,
        "page_title": "Sell My House Fast Columbus Ohio | Cash Offer in 24 Hours | Lifeline Home Buyers",
        "meta_description": "Need to sell your house fast in Columbus, Ohio? Get a fair cash offer in 24 hours. No repairs, no fees, no hassle. We buy houses in ANY condition. Call today!"
    })


# /we-buy-houses-columbus is now handled by the neighborhood_page route above


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
# BROWSER DIALER API (Twilio WebRTC)
# ============================================

# Import browser calling module (try local first, then parent directory)
BROWSER_CALLING_AVAILABLE = False
TWILIO_CLIENT_AVAILABLE = False
try:
    # Try local auth folder first (for Railway deployment)
    from auth.browser_calling import (
        generate_access_token,
        generate_capability_token,
        create_outbound_twiml,
        get_dialer_html,
        clean_phone_for_browser,
        get_twiml_app_info,
        TWILIO_CLIENT_AVAILABLE
    )
    BROWSER_CALLING_AVAILABLE = True
    logger.info("Loaded browser calling from local auth folder")
except ImportError:
    try:
        # Fall back to parent directory (for local development)
        sys.path.insert(0, str(BASE_DIR.parent))
        from auth.browser_calling import (
            generate_access_token,
            generate_capability_token,
            create_outbound_twiml,
            get_dialer_html,
            clean_phone_for_browser,
            get_twiml_app_info,
            TWILIO_CLIENT_AVAILABLE
        )
        BROWSER_CALLING_AVAILABLE = True
        logger.info("Loaded browser calling from parent directory")
    except ImportError as e:
        logger.warning(f"Browser calling not available: {e}")


@app.get("/api/dialer/status")
async def dialer_status():
    """Check if browser dialer is available."""
    if not BROWSER_CALLING_AVAILABLE:
        return {"available": False, "error": "Browser calling module not loaded"}

    info = get_twiml_app_info() if BROWSER_CALLING_AVAILABLE else {}
    return {
        "available": TWILIO_CLIENT_AVAILABLE,
        "twiml_configured": info.get('configured', False),
        "phone_number": info.get('phone_number', ''),
        "api_key_configured": info.get('api_key_configured', False)
    }


@app.get("/api/dialer/token")
async def get_dialer_token(identity: str = "va-user"):
    """Generate a Twilio capability token for browser calling."""
    if not BROWSER_CALLING_AVAILABLE or not TWILIO_CLIENT_AVAILABLE:
        return JSONResponse(
            status_code=503,
            content={"error": "Browser calling not configured", "available": False}
        )

    success, token_or_error, _ = generate_access_token(identity)

    if success:
        return {"token": token_or_error, "identity": identity}
    else:
        return JSONResponse(
            status_code=500,
            content={"error": token_or_error}
        )


@app.post("/api/dialer/twiml")
async def handle_twiml(request: Request):
    """
    TwiML App webhook - handles outbound calls from browser.
    This endpoint is called by Twilio when a browser call is initiated.
    """
    if not BROWSER_CALLING_AVAILABLE:
        return HTMLResponse(
            content="<Response><Say>Dialer not configured</Say></Response>",
            media_type="application/xml"
        )

    # Parse form data from Twilio
    form = await request.form()
    to_number = form.get('To', '')
    lead_name = form.get('LeadName', '')
    lead_address = form.get('LeadAddress', '')

    # Clean the phone number
    clean_number = clean_phone_for_browser(to_number)

    if not clean_number:
        return HTMLResponse(
            content="<Response><Say>Invalid phone number</Say></Response>",
            media_type="application/xml"
        )

    # Get caller ID from environment
    caller_id = os.environ.get('TWILIO_PHONE_NUMBER', '')

    # Generate TwiML for outbound call
    twiml = create_outbound_twiml(
        to_number=clean_number,
        caller_id=caller_id,
        lead_name=lead_name,
        lead_address=lead_address
    )

    logger.info(f"Browser call: {clean_number} (Lead: {lead_name})")

    return HTMLResponse(content=twiml, media_type="application/xml")


@app.post("/api/call-status")
async def call_status_webhook(request: Request):
    """Webhook called when a call ends - for logging/analytics."""
    form = await request.form()
    call_sid = form.get('CallSid', '')
    call_status = form.get('CallStatus', '')
    call_duration = form.get('CallDuration', '0')

    logger.info(f"Call completed: {call_sid} - Status: {call_status} - Duration: {call_duration}s")

    # Could save call stats to database here

    return HTMLResponse(content="<Response></Response>", media_type="application/xml")


@app.get("/dialer", response_class=HTMLResponse)
async def browser_dialer_page(
    request: Request,
    identity: str = "va-user",
    phone: str = "",
    name: str = "",
    address: str = ""
):
    """
    Standalone browser dialer page.
    VAs can open this in a new tab/window to make calls.

    Query params:
    - identity: VA username for token generation
    - phone: Pre-filled phone number to call
    - name: Lead name (for reference)
    - address: Property address (for reference)
    """
    if not BROWSER_CALLING_AVAILABLE or not TWILIO_CLIENT_AVAILABLE:
        return HTMLResponse(
            content="""
            <html><body style='font-family: sans-serif; padding: 50px; text-align: center;'>
                <h1>Browser Dialer Not Available</h1>
                <p>The browser dialer requires Twilio configuration.</p>
                <p>Please contact your administrator to set up:</p>
                <ul style='text-align: left; max-width: 400px; margin: 20px auto;'>
                    <li>TWILIO_ACCOUNT_SID</li>
                    <li>TWILIO_AUTH_TOKEN</li>
                    <li>TWILIO_PHONE_NUMBER</li>
                    <li>TWILIO_TWIML_APP_SID</li>
                </ul>
            </body></html>
            """,
            status_code=503
        )

    # Generate token
    success, token, _ = generate_access_token(identity)

    if not success:
        return HTMLResponse(
            content=f"""
            <html><body style='font-family: sans-serif; padding: 50px; text-align: center;'>
                <h1>Token Generation Failed</h1>
                <p>{token}</p>
            </body></html>
            """,
            status_code=500
        )

    # Return dialer HTML with token embedded
    html = get_dialer_html(
        token=token,
        lead_name=name,
        lead_address=address,
        lead_phone=phone
    )

    return HTMLResponse(content=html)


# ============================================
# RUN SERVER
# ============================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
