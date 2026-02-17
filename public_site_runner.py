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

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
import pandas as pd
import logging

try:
    import yaml
    import markdown
    BLOG_AVAILABLE = True
except ImportError:
    BLOG_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup - lazy connection
DATABASE_URL = os.environ.get('DATABASE_URL', '')
DB_AVAILABLE = False
DB_ERROR = None

def get_db_connection():
    """Get database connection (lazy initialization)."""
    global DB_AVAILABLE, DB_ERROR
    if not DATABASE_URL:
        DB_ERROR = "DATABASE_URL not set"
        return None
    try:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        DB_AVAILABLE = True
        DB_ERROR = None
        return conn
    except Exception as e:
        DB_ERROR = str(e)
        logger.error(f"Database connection failed: {e}")
        return None

import hashlib

def hash_password(password: str) -> str:
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def init_database():
    """Create tables if they don't exist."""
    conn = get_db_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()

        # Users table for VA authentication
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                full_name VARCHAR(255),
                email VARCHAR(255),
                role VARCHAR(50) DEFAULT 'va',
                status VARCHAR(50) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                phone VARCHAR(50),
                notes TEXT
            )
        """)

        # Sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(255) UNIQUE NOT NULL,
                username VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                ip_address VARCHAR(50),
                user_agent TEXT
            )
        """)

        # Activity log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100),
                action VARCHAR(100),
                details TEXT,
                ip_address VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Check if users table is empty and seed default users
        cursor.execute("SELECT COUNT(*) FROM users")
        user_count = cursor.fetchone()[0]
        if user_count == 0:
            logger.info("Seeding default users...")
            default_password = hash_password('Lifeline2026')
            admin_password = hash_password('admin123')

            # Admin user
            cursor.execute("""
                INSERT INTO users (username, password_hash, full_name, role, status)
                VALUES (%s, %s, %s, %s, %s)
            """, ('admin', admin_password, 'System Admin', 'admin', 'active'))

            # VA users
            va_users = [
                ('naomi', 'Naomi Keza', 'naomikezau@gmail.com'),
                ('keomi', 'Naomi Keza Uwase', 'naomikezau@gmail.com'),
                ('monalisa', 'Naomi Keza', 'naomikezau@gmail.com'),
                ('brent', 'Willy Miles', 'wshumbusho5@gmail.com'),
            ]
            for username, full_name, email in va_users:
                cursor.execute("""
                    INSERT INTO users (username, password_hash, full_name, email, role, status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (username, default_password, full_name, email, 'va', 'active'))

            logger.info("Seeded admin and 4 VA users")

        # Inbound leads table
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

        # Call logs table - tracks all VA calls
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS call_logs (
                id SERIAL PRIMARY KEY,
                call_sid VARCHAR(100),
                va_identity VARCHAR(100),
                lead_name VARCHAR(255),
                lead_phone VARCHAR(50),
                lead_address TEXT,
                call_start TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                call_end TIMESTAMP,
                duration_seconds INTEGER DEFAULT 0,
                twilio_status VARCHAR(50),
                outcome VARCHAR(50),
                notes TEXT,
                follow_up_date DATE,
                appointment_id INTEGER
            )
        """)

        # Appointments table - scheduled callbacks and meetings
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by VARCHAR(100),
                lead_name VARCHAR(255),
                lead_phone VARCHAR(50),
                lead_address TEXT,
                appointment_date DATE NOT NULL,
                appointment_time TIME NOT NULL,
                appointment_type VARCHAR(50) DEFAULT 'callback',
                status VARCHAR(50) DEFAULT 'scheduled',
                notes TEXT,
                reminder_sent BOOLEAN DEFAULT FALSE,
                call_log_id INTEGER
            )
        """)

        # Public properties table — powers SEO property pages
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS public_properties (
                id SERIAL PRIMARY KEY,
                slug VARCHAR(500) UNIQUE NOT NULL,
                address VARCHAR(500) NOT NULL,
                city VARCHAR(100) DEFAULT 'Columbus',
                zip VARCHAR(10),
                state VARCHAR(5) DEFAULT 'OH',
                neighborhood VARCHAR(100),
                lead_type VARCHAR(50) DEFAULT 'motivated_seller',
                assessed_value INTEGER,
                val_low INTEGER,
                val_high INTEGER,
                taxes_owed INTEGER,
                years_delinquent INTEGER,
                imported_at DATE DEFAULT CURRENT_DATE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
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


def load_properties():
    """Load public properties — database first, CSV fallback."""
    conn = get_db_connection()
    if conn:
        try:
            df = pd.read_sql("SELECT * FROM public_properties ORDER BY imported_at DESC", conn)
            conn.close()
            if not df.empty:
                return df
        except Exception as e:
            logger.error(f"Failed to load properties from DB: {e}")

    # Fallback to CSV
    props_file = PROCESSED_DATA_DIR / "public_properties.csv"
    if props_file.exists():
        try:
            return pd.read_csv(props_file)
        except Exception as e:
            logger.error(f"Failed to load properties CSV: {e}")
    return pd.DataFrame()

app = FastAPI(title="Lifeline Home Buyers")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "public_site" / "static")), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals['now'] = datetime.now


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
        "name": "Linden", "zip": "43211",
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
        "name": "Franklinton", "zip": "43222",
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
        "name": "Near East Side", "zip": "43203",
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
        "name": "South Side", "zip": "43207",
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
        "name": "Hilltop", "zip": "43228",
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
        "name": "German Village", "zip": "43206",
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

BLOG_POSTS_DIR = BASE_DIR / "public_site" / "blog_posts"


def load_blog_posts():
    """Load all blog posts from markdown files with YAML frontmatter."""
    posts = []
    if not BLOG_AVAILABLE or not BLOG_POSTS_DIR.exists():
        return posts
    for md_file in BLOG_POSTS_DIR.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    frontmatter["body"] = parts[2].strip()
                    frontmatter["date"] = str(frontmatter.get("date", ""))
                    posts.append(frontmatter)
        except Exception as e:
            logger.warning(f"Error loading blog post {md_file}: {e}")
    posts.sort(key=lambda p: p.get("date", ""), reverse=True)
    return posts


def get_blog_post(slug: str):
    """Get a single blog post by slug."""
    for post in load_blog_posts():
        if post.get("slug") == slug:
            return post
    return None


@app.on_event("startup")
async def startup():
    """Initialize database on startup."""
    init_database()

@app.get("/health")
async def health():
    # Try connecting now to get fresh status
    test_conn = get_db_connection()
    if test_conn:
        test_conn.close()

    return {
        "status": "ok",
        "templates": str(TEMPLATES_DIR),
        "exists": TEMPLATES_DIR.exists(),
        "db_available": DB_AVAILABLE,
        "db_url_set": bool(DATABASE_URL),
        "db_error": DB_ERROR,
        "blog_available": BLOG_AVAILABLE,
        "blog_dir": str(BLOG_POSTS_DIR),
        "blog_dir_exists": BLOG_POSTS_DIR.exists(),
        "blog_posts_count": len(load_blog_posts()),
        "blog_files": [f.name for f in BLOG_POSTS_DIR.glob("*.md")] if BLOG_POSTS_DIR.exists() else [],
    }

@app.get("/robots.txt")
async def robots_txt():
    """robots.txt for Google crawling."""
    content = """User-agent: *
Allow: /
Disallow: /dialer
Disallow: /api/

Sitemap: https://life-line-homebuyers.com/sitemap.xml
"""
    return HTMLResponse(content=content, media_type="text/plain")


@app.get("/sitemap.xml")
async def sitemap():
    """XML sitemap for Google indexing — includes all property pages."""
    base_url = "https://life-line-homebuyers.com"

    static_pages = [
        (f"{base_url}/", "weekly", "1.0"),
        (f"{base_url}/about", "monthly", "0.8"),
        (f"{base_url}/get-offer", "monthly", "0.9"),
        (f"{base_url}/probate", "weekly", "0.8"),
        (f"{base_url}/tax-delinquent", "weekly", "0.8"),
        (f"{base_url}/properties", "weekly", "0.7"),
        (f"{base_url}/calculator", "monthly", "0.7"),
        (f"{base_url}/we-buy-houses", "monthly", "0.8"),
        (f"{base_url}/sell-house-fast", "monthly", "0.8"),
        (f"{base_url}/blog", "weekly", "0.7"),
    ]

    urls = []
    for loc, freq, priority in static_pages:
        urls.append(f"    <url><loc>{loc}</loc><changefreq>{freq}</changefreq><priority>{priority}</priority></url>")

    # Add neighborhood pages
    for slug in NEIGHBORHOODS:
        urls.append(f"    <url><loc>{base_url}/we-buy-houses-{slug}</loc><changefreq>weekly</changefreq><priority>0.85</priority></url>")

    # Add blog posts
    for post in load_blog_posts():
        urls.append(f"    <url><loc>{base_url}/blog/{post['slug']}</loc><changefreq>monthly</changefreq><priority>0.6</priority></url>")

    # Add individual property pages
    df = load_properties()
    if not df.empty and "slug" in df.columns:
        for slug in df["slug"].dropna().unique()[:50000]:  # sitemap spec allows up to 50,000 URLs
            urls.append(f"    <url><loc>{base_url}/property/{slug}</loc><changefreq>monthly</changefreq><priority>0.6</priority></url>")

    content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    content += "\n".join(urls)
    content += "\n</urlset>"

    return HTMLResponse(content=content, media_type="application/xml")


@app.get("/")
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
        "page_title": "We Buy Houses Columbus Ohio | Cash Offers in 24 Hours | Lifeline Home Buyers",
        "meta_description": "We buy houses in Columbus, Ohio for cash. Any condition - tax delinquent, probate, foreclosure, repairs needed. Get a fair cash offer in 24 hours. Call (614) 825-3368."
    })

@app.get("/about", response_class=HTMLResponse)
async def about(request: Request):
    return templates.TemplateResponse("about.html", {
        "request": request,
        "page_title": "About Us | Lifeline Home Buyers Columbus Ohio",
        "meta_description": "We are local Columbus Ohio cash home buyers. Founded by Willy Shumbusho to help homeowners facing foreclosure, tax problems, and difficult situations. Call (614) 825-3368."
    })

@app.get("/get-offer", response_class=HTMLResponse)
async def get_offer(request: Request):
    return templates.TemplateResponse("get_offer.html", {
        "request": request,
        "page_title": "Get a Free Cash Offer | Sell Your House Fast Columbus Ohio | Lifeline Home Buyers",
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

@app.get("/property/{slug}", response_class=HTMLResponse)
async def property_detail(request: Request, slug: str):
    """Individual property page — ranks for address searches."""
    df = load_properties()
    if df.empty or "slug" not in df.columns:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    match = df[df["slug"] == slug]
    if match.empty:
        return templates.TemplateResponse("404.html", {"request": request}, status_code=404)

    prop = match.iloc[0].where(match.iloc[0].notna(), other=None).to_dict()

    # Build value display string
    val_low = prop.get("val_low")
    val_high = prop.get("val_high")
    if val_low and val_high:
        value_range = f"${val_low:,} – ${val_high:,}"
    else:
        value_range = None

    # Build taxes display
    taxes_owed = prop.get("taxes_owed")
    taxes_display = f"${int(taxes_owed):,}" if taxes_owed else None

    address = prop.get("address", "")
    city = prop.get("city", "Columbus")
    neighborhood = prop.get("neighborhood", "Columbus")
    lead_type = prop.get("lead_type", "motivated_seller")

    # SEO title and description per property
    if lead_type == "probate":
        page_title = f"{address}, {city} OH | Inherited Property Cash Offer | Lifeline Home Buyers"
        meta_desc = f"We buy inherited properties in {neighborhood}, Columbus OH. {address} — get a cash offer with no repairs, no fees, no hassle."
    elif lead_type == "tax_delinquent":
        page_title = f"{address}, {city} OH | Behind on Taxes? Sell Fast | Lifeline Home Buyers"
        meta_desc = f"Property at {address} in {neighborhood}, Columbus OH has outstanding taxes. We buy as-is, pay off back taxes, close in 7 days."
    elif lead_type == "sheriff_sale":
        page_title = f"{address}, {city} OH | Stop Foreclosure | Lifeline Home Buyers"
        meta_desc = f"Facing foreclosure on {address} in {neighborhood}? We buy before the sheriff sale. Cash offer within 24 hours."
    else:
        page_title = f"{address}, {city} OH | Cash Home Buyer | Lifeline Home Buyers"
        meta_desc = f"We're looking to buy {address} in {neighborhood}, Columbus OH. Get a cash offer with no repairs or agent fees."

    return templates.TemplateResponse("property_detail.html", {
        "request": request,
        "property": prop,
        "slug": slug,
        "value_range": value_range,
        "taxes_display": taxes_display,
        "neighborhood": neighborhood,
        "page_title": page_title,
        "meta_description": meta_desc,
    })


@app.get("/properties", response_class=HTMLResponse)
async def property_list(request: Request, type: str = None, page: int = 1):
    """Browseable list of all properties by type."""
    df = load_properties()

    if not df.empty and type:
        df = df[df["lead_type"] == type]

    per_page = 24
    total = len(df)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    end = start + per_page
    properties = df.iloc[start:end].to_dict("records") if total > 0 else []

    type_labels = {
        "probate": "Inherited / Probate Properties",
        "tax_delinquent": "Tax Delinquent Properties",
        "sheriff_sale": "Foreclosure / Sheriff Sale Properties",
        "code_violation": "Code Violation Properties",
    }

    return templates.TemplateResponse("property_list.html", {
        "request": request,
        "properties": properties,
        "total": total,
        "page": page,
        "total_pages": total_pages,
        "filter_type": type or "",
        "type_label": type_labels.get(type, "All Properties"),
        "page_title": f"{type_labels.get(type, 'Distressed Properties')} in Columbus OH | Lifeline Home Buyers",
        "meta_description": f"We buy {type_labels.get(type, 'distressed properties').lower()} in Columbus, Ohio for cash. Browse our active list.",
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


# ============================================
# NEIGHBORHOOD PAGES
# ============================================

@app.get("/we-buy-houses-{slug}", response_class=HTMLResponse)
async def neighborhood_page(request: Request, slug: str):
    """Neighborhood-specific landing pages for hyper-local SEO."""
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
    page_posts = posts[start:start + per_page]

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

    html_content = markdown.markdown(
        post["body"],
        extensions=["tables", "fenced_code", "nl2br"]
    ) if BLOG_AVAILABLE else "<p>Blog not available</p>"

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
# ADMIN — Property Data Upload
# ============================================

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Lifeline2026!')

import re as _re
import io

def _make_slug(address: str, city: str = "columbus") -> str:
    text = f"{address} {city} oh".lower()
    text = _re.sub(r"[^a-z0-9\s-]", "", text)
    text = _re.sub(r"\s+", "-", text.strip())
    return _re.sub(r"-+", "-", text)

ZIP_NEIGHBORHOODS = {
    "43201": "Short North", "43202": "Clintonville", "43203": "Near East Side",
    "43204": "Franklinton", "43205": "South Side", "43206": "German Village Area",
    "43207": "South Columbus", "43209": "Bexley", "43210": "University District",
    "43211": "Linden", "43212": "Grandview Heights", "43213": "East Columbus",
    "43214": "Beechwold", "43215": "Downtown Columbus", "43219": "Northland",
    "43220": "Upper Arlington", "43221": "Upper Arlington West", "43222": "Hilltop",
    "43223": "Southwest Columbus", "43224": "Northeast Columbus", "43227": "Whitehall",
    "43229": "Northland East", "43230": "Gahanna", "43231": "Northeast Columbus",
    "43232": "Reynoldsburg", "43235": "Worthington", "43240": "New Albany Area",
}

def _detect_lead_type(row: dict, filename: str) -> str:
    fname = filename.lower()
    if "probate" in fname: return "probate"
    if "tax" in fname or "delinquent" in fname: return "tax_delinquent"
    if "sheriff" in fname or "foreclosure" in fname: return "sheriff_sale"
    if "violation" in fname: return "code_violation"
    taxes = float(row.get("taxes_owed") or row.get("tax_owed") or 0)
    if taxes > 0: return "tax_delinquent"
    return "motivated_seller"

def _estimate_value_range(assessed):
    if not assessed or assessed <= 0:
        return None, None
    market = assessed / 0.35
    return int(market * 0.85 / 1000) * 1000, int(market * 1.15 / 1000) * 1000

def _process_upload_df(df: pd.DataFrame, filename: str) -> list:
    """Parse uploaded dataframe into property records."""
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    address_col = next((c for c in df.columns if "address" in c), None)
    if not address_col:
        return []

    records = []
    for _, row in df.iterrows():
        row = row.where(row.notna(), other=None).to_dict()
        address = str(row.get(address_col) or "").strip()
        if not address or address.lower() == "nan":
            continue

        zip_code = str(row.get("zip_code") or row.get("zip") or "").strip()
        if not zip_code or zip_code == "nan":
            m = _re.search(r"\b(4[0-9]{4})\b", address)
            zip_code = m.group(1) if m else ""

        city = str(row.get("city") or "Columbus").strip()
        if not city or city == "nan":
            city = "Columbus"

        neighborhood = ZIP_NEIGHBORHOODS.get(zip_code, "Columbus")
        assessed = float(row.get("assessed_value") or row.get("taxable_value") or 0)
        market = float(row.get("market_value") or 0)
        taxes_owed = float(row.get("taxes_owed") or row.get("tax_owed") or 0)
        years_delinquent = int(float(row.get("years_delinquent") or 0))

        if market > 0:
            val_low = int(market * 0.85 / 1000) * 1000
            val_high = int(market * 1.15 / 1000) * 1000
        else:
            val_low, val_high = _estimate_value_range(assessed)

        records.append({
            "slug": _make_slug(address, city),
            "address": address.title(),
            "city": city,
            "zip": zip_code or None,
            "neighborhood": neighborhood,
            "lead_type": _detect_lead_type(row, filename),
            "assessed_value": int(assessed) if assessed > 0 else None,
            "val_low": val_low,
            "val_high": val_high,
            "taxes_owed": int(taxes_owed) if taxes_owed > 0 else None,
            "years_delinquent": years_delinquent if years_delinquent > 0 else None,
        })
    return records

def _upsert_properties(records: list) -> int:
    """Insert or update properties in the database. Returns count saved."""
    conn = get_db_connection()
    if not conn:
        return 0
    try:
        cursor = conn.cursor()
        count = 0
        for r in records:
            cursor.execute("""
                INSERT INTO public_properties
                    (slug, address, city, zip, neighborhood, lead_type,
                     assessed_value, val_low, val_high, taxes_owed, years_delinquent, imported_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, CURRENT_DATE)
                ON CONFLICT (slug) DO UPDATE SET
                    address = EXCLUDED.address,
                    city = EXCLUDED.city,
                    zip = EXCLUDED.zip,
                    neighborhood = EXCLUDED.neighborhood,
                    lead_type = EXCLUDED.lead_type,
                    assessed_value = EXCLUDED.assessed_value,
                    val_low = EXCLUDED.val_low,
                    val_high = EXCLUDED.val_high,
                    taxes_owed = EXCLUDED.taxes_owed,
                    years_delinquent = EXCLUDED.years_delinquent,
                    imported_at = CURRENT_DATE,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                r["slug"], r["address"], r["city"], r["zip"], r["neighborhood"],
                r["lead_type"], r["assessed_value"], r["val_low"], r["val_high"],
                r["taxes_owed"], r["years_delinquent"]
            ))
            count += 1
        conn.commit()
        conn.close()
        return count
    except Exception as e:
        logger.error(f"Upsert error: {e}")
        return 0

from fastapi import UploadFile, File

@app.get("/admin/upload", response_class=HTMLResponse)
async def admin_upload_page(request: Request, success: int = None, error: str = None):
    return templates.TemplateResponse("admin_upload.html", {
        "request": request,
        "success": success,
        "error": error,
        "page_title": "Admin — Upload Property Data",
        "meta_description": "",
    })

@app.post("/admin/upload", response_class=HTMLResponse)
async def admin_upload_post(
    request: Request,
    password: str = Form(...),
    file: UploadFile = File(...)
):
    # Password check
    if password != ADMIN_PASSWORD:
        return RedirectResponse(url="/admin/upload?error=Wrong+password", status_code=303)

    # Read file
    contents = await file.read()
    filename = file.filename or ""

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        elif filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(contents), engine="openpyxl")
        else:
            return RedirectResponse(url="/admin/upload?error=Only+CSV+or+Excel+files+accepted", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/admin/upload?error=Could+not+read+file", status_code=303)

    records = _process_upload_df(df, filename)
    if not records:
        return RedirectResponse(url="/admin/upload?error=No+valid+addresses+found+in+file", status_code=303)

    saved = _upsert_properties(records)
    return RedirectResponse(url=f"/admin/upload?success={saved}", status_code=303)


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

# ============================================
# BROWSER DIALER API (Twilio WebRTC)
# ============================================

TWILIO_CLIENT_AVAILABLE = False
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
TWILIO_PHONE_NUMBER_2 = os.environ.get('TWILIO_PHONE_NUMBER_2', '')  # Second number for buyers
TWILIO_TWIML_APP_SID = os.environ.get('TWILIO_TWIML_APP_SID', '')
TWILIO_API_KEY = os.environ.get('TWILIO_API_KEY', '')
TWILIO_API_SECRET = os.environ.get('TWILIO_API_SECRET', '')

# Call forwarding - real phone numbers to forward inbound calls to
FORWARD_TO_SELLERS = os.environ.get('FORWARD_TO_SELLERS', '')  # Your real number for sellers line
FORWARD_TO_BUYERS = os.environ.get('FORWARD_TO_BUYERS', '')    # Your real number for buyers line

# Phone number labels for VA selection
PHONE_NUMBERS = {
    'sellers': {'number': TWILIO_PHONE_NUMBER, 'label': 'Sellers Line'},
    'buyers': {'number': TWILIO_PHONE_NUMBER_2, 'label': 'Buyers Line'}
}

try:
    from twilio.rest import Client
    from twilio.jwt.access_token import AccessToken
    from twilio.jwt.access_token.grants import VoiceGrant
    from twilio.twiml.voice_response import VoiceResponse, Dial

    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER:
        TWILIO_CLIENT_AVAILABLE = True
        logger.info("Twilio browser calling initialized")
    else:
        logger.warning("Twilio credentials not fully configured")
except ImportError as e:
    logger.warning(f"Twilio library not installed: {e}")


def generate_twilio_token(identity: str):
    """Generate Access Token for Voice SDK 2.x."""
    if not TWILIO_CLIENT_AVAILABLE:
        logger.error("Twilio client not available")
        return None

    if not TWILIO_API_KEY or not TWILIO_API_SECRET:
        logger.error("TWILIO_API_KEY or TWILIO_API_SECRET not set")
        return None

    try:
        token = AccessToken(
            TWILIO_ACCOUNT_SID,
            TWILIO_API_KEY,
            TWILIO_API_SECRET,
            identity=identity,
            ttl=3600
        )
        voice_grant = VoiceGrant(
            outgoing_application_sid=TWILIO_TWIML_APP_SID,
            incoming_allow=False
        )
        token.add_grant(voice_grant)
        jwt_token = token.to_jwt()
        # Ensure string
        if isinstance(jwt_token, bytes):
            jwt_token = jwt_token.decode('utf-8')
        logger.info(f"Generated access token for: {identity}")
        return jwt_token
    except Exception as e:
        logger.error(f"Token generation failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def clean_phone(phone: str):
    """Clean phone to E.164 format."""
    if not phone:
        return None
    digits = ''.join(filter(str.isdigit, str(phone)))
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
    elif len(digits) > 10:
        return f"+{digits}"
    return None


@app.get("/api/dialer/status")
async def dialer_status():
    """Check if browser dialer is available."""
    return {
        "available": TWILIO_CLIENT_AVAILABLE,
        "twiml_configured": bool(TWILIO_TWIML_APP_SID),
        "phone_number": TWILIO_PHONE_NUMBER or "",
        "api_key_configured": bool(TWILIO_API_KEY and TWILIO_API_SECRET),
        "account_sid": TWILIO_ACCOUNT_SID[:10] + "..." if TWILIO_ACCOUNT_SID else None,
        "twiml_app_sid": TWILIO_TWIML_APP_SID[:10] + "..." if TWILIO_TWIML_APP_SID else None
    }


@app.get("/api/dialer/test-twiml")
async def test_twiml(phone: str = "+15551234567"):
    """Test TwiML generation."""
    try:
        to_number = clean_phone(phone)
        if not to_number:
            return {"error": "Invalid phone", "raw": phone}

        response = VoiceResponse()
        dial = Dial(caller_id=TWILIO_PHONE_NUMBER, timeout=30)
        dial.number(to_number)
        response.append(dial)
        response.say("Call ended.")

        return {
            "success": True,
            "to_number": to_number,
            "caller_id": TWILIO_PHONE_NUMBER,
            "twiml": str(response)
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/dialer/token")
async def get_dialer_token(identity: str = "va-user"):
    """Generate Twilio token for browser calling."""
    if not TWILIO_CLIENT_AVAILABLE:
        return JSONResponse(status_code=503, content={"error": "Twilio not configured"})

    token = generate_twilio_token(identity)
    if token:
        return {"token": token, "identity": identity}
    return JSONResponse(status_code=500, content={"error": "Token generation failed"})


@app.post("/api/dialer/twiml")
async def handle_twiml(request: Request):
    """TwiML webhook for outbound browser calls."""
    try:
        form = await request.form()
        raw_to = form.get('To', '')
        selected_caller_id = form.get('CallerId', '') or TWILIO_PHONE_NUMBER
        logger.info(f"TwiML request - Raw To: {raw_to}")

        to_number = clean_phone(raw_to)

        # Validate the selected caller ID is one of our numbers
        valid_caller_ids = [TWILIO_PHONE_NUMBER, TWILIO_PHONE_NUMBER_2]
        if selected_caller_id not in valid_caller_ids:
            selected_caller_id = TWILIO_PHONE_NUMBER

        logger.info(f"TwiML request - Cleaned To: {to_number}, Caller ID: {selected_caller_id}")

        if not to_number:
            logger.error("Invalid phone number")
            return HTMLResponse(content="<Response><Say>Invalid phone number provided</Say></Response>", media_type="application/xml")

        if not selected_caller_id:
            logger.error("No caller ID configured")
            return HTMLResponse(content="<Response><Say>Caller ID not configured</Say></Response>", media_type="application/xml")

        response = VoiceResponse()
        dial = Dial(caller_id=selected_caller_id, timeout=30)
        dial.number(to_number)
        response.append(dial)
        response.say("Call ended. Goodbye.")

        twiml_str = str(response)
        logger.info(f"Generated TwiML: {twiml_str}")
        return HTMLResponse(content=twiml_str, media_type="application/xml")

    except Exception as e:
        logger.error(f"TwiML error: {e}")
        import traceback
        traceback.print_exc()
        return HTMLResponse(content=f"<Response><Say>Error: {str(e)}</Say></Response>", media_type="application/xml")


@app.post("/incoming-sms")
async def incoming_sms_sellers(request: Request):
    """Forward incoming SMS from sellers line to real phone via Twilio."""
    from twilio.twiml.messaging_response import MessagingResponse
    try:
        form = await request.form()
        from_number = form.get('From', '')
        body = form.get('Body', '')
        logger.info(f"Incoming SMS from {from_number}: {body}")

        # Forward via Twilio client
        if TWILIO_CLIENT_AVAILABLE and FORWARD_TO_SELLERS:
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            client.messages.create(
                body=f"SMS from {from_number}: {body}",
                from_=TWILIO_PHONE_NUMBER,
                to=FORWARD_TO_SELLERS
            )
            logger.info(f"Forwarded SMS to {FORWARD_TO_SELLERS}")

        # Send auto-reply to sender
        response = MessagingResponse()
        response.message("Thank you for reaching out to Lifeline Home Buyers! We'll get back to you shortly. Call us at (614) 825-3368 for a faster response.")
        return HTMLResponse(content=str(response), media_type="application/xml")
    except Exception as e:
        logger.error(f"SMS error: {e}")
        return HTMLResponse(content="<Response></Response>", media_type="application/xml")


@app.post("/incoming-sms-buyers")
async def incoming_sms_buyers(request: Request):
    """Forward incoming SMS from buyers line to real phone via Twilio."""
    from twilio.twiml.messaging_response import MessagingResponse
    try:
        form = await request.form()
        from_number = form.get('From', '')
        body = form.get('Body', '')
        forward_to = FORWARD_TO_BUYERS or FORWARD_TO_SELLERS
        logger.info(f"Incoming SMS (buyers) from {from_number}: {body}")

        if TWILIO_CLIENT_AVAILABLE and forward_to:
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            client.messages.create(
                body=f"BUYER SMS from {from_number}: {body}",
                from_=TWILIO_PHONE_NUMBER_2 or TWILIO_PHONE_NUMBER,
                to=forward_to
            )

        response = MessagingResponse()
        response.message("Thank you for reaching out to Lifeline Home Buyers! We'll get back to you shortly.")
        return HTMLResponse(content=str(response), media_type="application/xml")
    except Exception as e:
        logger.error(f"SMS buyers error: {e}")
        return HTMLResponse(content="<Response></Response>", media_type="application/xml")


@app.post("/incoming-call")
async def incoming_call_sellers(request: Request):
    """Handle inbound calls to the sellers Twilio number - forward to real phone."""
    forward_to = FORWARD_TO_SELLERS
    caller_id = TWILIO_PHONE_NUMBER

    response = VoiceResponse()
    if forward_to:
        dial = Dial(caller_id=caller_id, timeout=30)
        dial.number(forward_to)
        response.append(dial)
        logger.info(f"Forwarding sellers line call to {forward_to}")
    else:
        response.say("Thank you for calling Lifeline Home Buyers. Please leave a message or call back later.")
        logger.warning("FORWARD_TO_SELLERS not configured")

    return HTMLResponse(content=str(response), media_type="application/xml")


@app.post("/incoming-call-buyers")
async def incoming_call_buyers(request: Request):
    """Handle inbound calls to the buyers Twilio number - forward to real phone."""
    forward_to = FORWARD_TO_BUYERS or FORWARD_TO_SELLERS  # Fallback to sellers number
    caller_id = TWILIO_PHONE_NUMBER_2 or TWILIO_PHONE_NUMBER

    response = VoiceResponse()
    if forward_to:
        dial = Dial(caller_id=caller_id, timeout=30)
        dial.number(forward_to)
        response.append(dial)
        logger.info(f"Forwarding buyers line call to {forward_to}")
    else:
        response.say("Thank you for calling Lifeline Home Buyers. Please leave a message or call back later.")
        logger.warning("FORWARD_TO_BUYERS not configured")

    return HTMLResponse(content=str(response), media_type="application/xml")


@app.post("/api/dialer/log-call")
async def log_call(request: Request):
    """Save call log after VA completes a call."""
    try:
        data = await request.json()
        conn = get_db_connection()
        if not conn:
            return JSONResponse(status_code=500, content={"error": "Database not available"})

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO call_logs
            (call_sid, va_identity, lead_name, lead_phone, lead_address,
             duration_seconds, twilio_status, outcome, notes, follow_up_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data.get('call_sid', ''),
            data.get('va_identity', ''),
            data.get('lead_name', ''),
            data.get('lead_phone', ''),
            data.get('lead_address', ''),
            int(data.get('duration_seconds', 0)),
            data.get('twilio_status', ''),
            data.get('outcome', ''),
            data.get('notes', ''),
            data.get('follow_up_date') or None
        ))
        call_log_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()

        logger.info(f"Call logged: {call_log_id} - {data.get('outcome')} by {data.get('va_identity')}")
        return {"success": True, "call_log_id": call_log_id}
    except Exception as e:
        logger.error(f"Failed to log call: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/dialer/set-appointment")
async def set_appointment(request: Request):
    """Create an appointment from the dialer."""
    try:
        data = await request.json()
        conn = get_db_connection()
        if not conn:
            return JSONResponse(status_code=500, content={"error": "Database not available"})

        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO appointments
            (created_by, lead_name, lead_phone, lead_address,
             appointment_date, appointment_time, appointment_type, notes, call_log_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            data.get('created_by', ''),
            data.get('lead_name', ''),
            data.get('lead_phone', ''),
            data.get('lead_address', ''),
            data.get('appointment_date'),
            data.get('appointment_time'),
            data.get('appointment_type', 'callback'),
            data.get('notes', ''),
            data.get('call_log_id')
        ))
        appointment_id = cursor.fetchone()[0]

        # Update call log with appointment ID if provided
        if data.get('call_log_id'):
            cursor.execute("""
                UPDATE call_logs SET appointment_id = %s WHERE id = %s
            """, (appointment_id, data.get('call_log_id')))

        conn.commit()
        conn.close()

        logger.info(f"Appointment created: {appointment_id} for {data.get('lead_name')}")
        return {"success": True, "appointment_id": appointment_id}
    except Exception as e:
        logger.error(f"Failed to create appointment: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/dialer/appointments")
async def get_appointments(va_identity: str = None, date: str = None):
    """Get appointments, optionally filtered by VA or date."""
    try:
        conn = get_db_connection()
        if not conn:
            return JSONResponse(status_code=500, content={"error": "Database not available"})

        cursor = conn.cursor()
        query = "SELECT * FROM appointments WHERE status = 'scheduled'"
        params = []

        if va_identity:
            query += " AND created_by = %s"
            params.append(va_identity)
        if date:
            query += " AND appointment_date = %s"
            params.append(date)

        query += " ORDER BY appointment_date, appointment_time"
        cursor.execute(query, params)

        columns = [desc[0] for desc in cursor.description]
        appointments = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()

        # Convert dates/times to strings for JSON
        for apt in appointments:
            for key in apt:
                if hasattr(apt[key], 'isoformat'):
                    apt[key] = apt[key].isoformat()

        return {"appointments": appointments}
    except Exception as e:
        logger.error(f"Failed to get appointments: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/dialer/call-history")
async def get_call_history(va_identity: str = None, limit: int = 50):
    """Get recent call logs."""
    try:
        conn = get_db_connection()
        if not conn:
            return JSONResponse(status_code=500, content={"error": "Database not available"})

        cursor = conn.cursor()
        query = "SELECT * FROM call_logs"
        params = []

        if va_identity:
            query += " WHERE va_identity = %s"
            params.append(va_identity)

        query += " ORDER BY call_start DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        columns = [desc[0] for desc in cursor.description]
        calls = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()

        # Convert dates to strings for JSON
        for call in calls:
            for key in call:
                if hasattr(call[key], 'isoformat'):
                    call[key] = call[key].isoformat()

        return {"calls": calls}
    except Exception as e:
        logger.error(f"Failed to get call history: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/dialer", response_class=HTMLResponse)
async def browser_dialer(phone: str = "", name: str = "", address: str = "", identity: str = "va-user"):
    """Browser dialer page."""
    if not TWILIO_CLIENT_AVAILABLE:
        return HTMLResponse(content="""
            <html><body style='font-family:sans-serif;padding:50px;text-align:center;'>
            <h1>Browser Dialer Not Available</h1>
            <p>Twilio credentials not configured.</p>
            </body></html>
        """, status_code=503)

    token = generate_twilio_token(identity)
    if not token:
        return HTMLResponse(content="""
            <html><body style='font-family:sans-serif;padding:50px;text-align:center;'>
            <h1>Token Generation Failed</h1>
            <p>Check TWILIO_API_KEY and TWILIO_API_SECRET.</p>
            </body></html>
        """, status_code=500)

    # Return dialer HTML - Using Twilio Voice SDK 2.x with call logging
    html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Browser Dialer - Lifeline Home Buyers</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script type="text/javascript" src="https://cdn.jsdelivr.net/npm/@twilio/voice-sdk@2.10.0/dist/twilio.min.js"></script>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        .dialer {{
            background: white;
            border-radius: 20px;
            padding: 30px;
            max-width: 450px;
            width: 100%;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }}
        h1 {{ font-size: 1.5rem; text-align: center; margin-bottom: 20px; color: #1a1a2e; }}
        h2 {{ font-size: 1.2rem; margin-bottom: 15px; color: #333; }}
        .status {{
            text-align: center;
            padding: 8px 16px;
            border-radius: 20px;
            margin-bottom: 20px;
            font-size: 0.9rem;
        }}
        .status.ready {{ background: #d4edda; color: #155724; }}
        .status.connecting {{ background: #fff3cd; color: #856404; }}
        .status.on-call {{ background: #cce5ff; color: #004085; }}
        .status.error {{ background: #f8d7da; color: #721c24; }}
        .status.logging {{ background: #e2e3e5; color: #383d41; }}
        .lead-info {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .lead-info h3 {{ font-size: 1rem; margin-bottom: 5px; color: #333; }}
        .lead-info p {{ color: #666; font-size: 0.9rem; }}
        .lead-info .phone {{ font-size: 1.3rem; font-weight: 700; color: #0b6b30; margin-top: 10px; }}
        input, select, textarea {{
            width: 100%;
            padding: 12px 15px;
            font-size: 1rem;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            margin-bottom: 12px;
        }}
        input[type="tel"] {{ text-align: center; font-size: 1.2rem; }}
        input:focus, select:focus, textarea:focus {{ outline: none; border-color: #0b6b30; }}
        textarea {{ resize: vertical; min-height: 80px; }}
        .btn {{
            width: 100%;
            padding: 15px;
            font-size: 1.1rem;
            font-weight: 600;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            margin-bottom: 10px;
        }}
        .btn-call {{ background: #0b6b30; color: white; }}
        .btn-call:hover {{ background: #095a28; }}
        .btn-call:disabled {{ background: #ccc; cursor: not-allowed; }}
        .btn-hangup {{ background: #dc3545; color: white; display: none; }}
        .btn-hangup:hover {{ background: #c82333; }}
        .btn-submit {{ background: #007bff; color: white; }}
        .btn-submit:hover {{ background: #0056b3; }}
        .btn-secondary {{ background: #6c757d; color: white; }}
        .btn-secondary:hover {{ background: #545b62; }}
        .timer {{
            text-align: center;
            font-size: 2.5rem;
            font-weight: 700;
            margin: 20px 0;
            display: none;
            color: #1a1a2e;
        }}
        .call-form {{ display: none; }}
        .form-row {{
            display: flex;
            gap: 10px;
        }}
        .form-row > * {{ flex: 1; }}
        .appointment-fields {{ display: none; margin-top: 10px; }}
        label {{
            display: block;
            margin-bottom: 5px;
            font-weight: 600;
            color: #333;
            font-size: 0.9rem;
        }}
        .divider {{
            border-top: 1px solid #e0e0e0;
            margin: 20px 0;
        }}
        .success-msg {{
            background: #d4edda;
            color: #155724;
            padding: 15px;
            border-radius: 10px;
            text-align: center;
            margin-bottom: 15px;
        }}
        .va-identity {{
            font-size: 0.85rem;
            color: #666;
            text-align: center;
            margin-bottom: 15px;
        }}
    </style>
</head>
<body>
    <div class="dialer">
        <h1>Lifeline Home Buyers</h1>
        <div class="va-identity">Logged in as: <strong>{identity}</strong></div>
        <div id="status" class="status">Initializing...</div>

        <!-- DIALER SECTION -->
        <div id="dialer-section">
            <div id="lead-info" class="lead-info" style="display:{{'block' if phone else 'none'}}">
                <h3 id="lead-name-display">{name or 'Lead'}</h3>
                <p id="lead-address-display">{address or ''}</p>
                <div class="phone" id="lead-phone-display">{phone or ''}</div>
            </div>

            <label for="caller-line">Call From</label>
            <select id="caller-line">
                <option value="{TWILIO_PHONE_NUMBER}">Sellers Line ({TWILIO_PHONE_NUMBER})</option>
                {"<option value='" + TWILIO_PHONE_NUMBER_2 + "'>Buyers Line (" + TWILIO_PHONE_NUMBER_2 + ")</option>" if TWILIO_PHONE_NUMBER_2 else ""}
            </select>

            <input type="tel" id="phone" placeholder="Enter phone number" value="{phone or ''}">
            <div id="timer" class="timer">00:00</div>
            <button id="call-btn" class="btn btn-call" disabled>Call</button>
            <button id="hangup-btn" class="btn btn-hangup">Hang Up</button>
        </div>

        <!-- CALL LOG FORM (shown after call ends) -->
        <div id="call-form" class="call-form">
            <div class="divider"></div>
            <h2>Log This Call</h2>

            <label for="outcome">Call Outcome *</label>
            <select id="outcome" required>
                <option value="">-- Select Outcome --</option>
                <option value="No Answer">No Answer</option>
                <option value="Voicemail Left">Left Voicemail</option>
                <option value="Wrong Number">Wrong Number</option>
                <option value="Contact - Not Interested">Not Interested</option>
                <option value="Contact - Maybe Later">Maybe Later / Call Back</option>
                <option value="Contact - Interested">Interested</option>
                <option value="Appointment Set">Appointment Set</option>
                <option value="Do Not Call">Do Not Call</option>
            </select>

            <!-- Appointment fields (shown when outcome is Appointment Set) -->
            <div id="appointment-fields" class="appointment-fields">
                <label>Appointment Date & Time *</label>
                <div class="form-row">
                    <input type="date" id="apt-date" required>
                    <input type="time" id="apt-time" value="10:00" required>
                </div>
                <label for="apt-type">Appointment Type</label>
                <select id="apt-type">
                    <option value="callback">Scheduled Callback</option>
                    <option value="property_visit">Property Visit</option>
                    <option value="offer_presentation">Offer Presentation</option>
                </select>
            </div>

            <label for="notes">Notes</label>
            <textarea id="notes" placeholder="Enter any notes about this call..."></textarea>

            <button id="submit-log" class="btn btn-submit">Save Call Log</button>
            <button id="skip-log" class="btn btn-secondary">Skip & Make Another Call</button>
        </div>

        <!-- SUCCESS MESSAGE -->
        <div id="success-section" style="display: none;">
            <div class="success-msg" id="success-msg">Call logged successfully!</div>
            <button id="new-call-btn" class="btn btn-call">Make Another Call</button>
            <button id="back-to-dashboard" class="btn btn-secondary" style="margin-top: 10px;">Back to VA Dashboard</button>
        </div>

        <!-- ERROR MESSAGE -->
        <div id="error-section" style="display: none;">
            <div style="background: #f8d7da; color: #721c24; padding: 15px; border-radius: 10px; margin-bottom: 15px;">
                <strong>Error saving call:</strong>
                <p id="error-msg"></p>
            </div>
            <button id="retry-save" class="btn btn-call">Try Again</button>
            <button id="back-to-dashboard-error" class="btn btn-secondary" style="margin-top: 10px;">Back to VA Dashboard</button>
        </div>
    </div>

    <script>
        const token = "{token}";
        const vaIdentity = "{identity}";
        const leadName = "{name or ''}";
        const leadAddress = "{address or ''}";
        const leadPhone = "{phone or ''}";

        let device = null;
        let activeCall = null;
        let timerInterval = null;
        let startTime = null;
        let callDuration = 0;
        let lastCallSid = '';

        const statusEl = document.getElementById('status');
        const phoneInput = document.getElementById('phone');
        const callBtn = document.getElementById('call-btn');
        const hangupBtn = document.getElementById('hangup-btn');
        const timerEl = document.getElementById('timer');
        const dialerSection = document.getElementById('dialer-section');
        const callForm = document.getElementById('call-form');
        const successSection = document.getElementById('success-section');
        const outcomeSelect = document.getElementById('outcome');
        const appointmentFields = document.getElementById('appointment-fields');

        function setStatus(text, cls) {{
            statusEl.textContent = text;
            statusEl.className = 'status ' + cls;
        }}

        function formatTime(sec) {{
            return String(Math.floor(sec/60)).padStart(2,'0') + ':' + String(sec%60).padStart(2,'0');
        }}

        // Show/hide appointment fields based on outcome
        outcomeSelect.addEventListener('change', function() {{
            if (this.value === 'Appointment Set') {{
                appointmentFields.style.display = 'block';
                // Set default date to tomorrow
                const tomorrow = new Date();
                tomorrow.setDate(tomorrow.getDate() + 1);
                document.getElementById('apt-date').value = tomorrow.toISOString().split('T')[0];
            }} else {{
                appointmentFields.style.display = 'none';
            }}
        }});

        async function initDevice() {{
            console.log('Initializing Twilio Device...');

            try {{
                device = new Twilio.Device(token, {{
                    logLevel: 1,
                    codecPreferences: ['opus', 'pcmu']
                }});

                device.on('registered', function() {{
                    console.log('Device registered!');
                    setStatus('Ready to call', 'ready');
                    callBtn.disabled = false;
                }});

                device.on('error', function(twilioError) {{
                    console.error('Twilio error:', twilioError);
                    setStatus('Error: ' + twilioError.message, 'error');
                }});

                await device.register();
                console.log('Device registration complete');

            }} catch(e) {{
                console.error('Init error:', e);
                setStatus('Init failed: ' + e.message, 'error');
            }}
        }}

        async function makeCall() {{
            var num = phoneInput.value.trim();
            if (!num) {{
                alert('Enter a phone number');
                return;
            }}

            const callerLine = document.getElementById('caller-line').value;
            console.log('Calling:', num, 'from:', callerLine);
            setStatus('Connecting...', 'connecting');
            callDuration = 0;

            try {{
                const params = {{ To: num, CallerId: callerLine }};
                activeCall = await device.connect({{ params: params }});

                activeCall.on('accept', function() {{
                    console.log('Call accepted');
                    lastCallSid = activeCall.parameters.CallSid || '';
                    setStatus('On Call', 'on-call');
                    callBtn.style.display = 'none';
                    hangupBtn.style.display = 'block';
                    timerEl.style.display = 'block';
                    startTime = Date.now();
                    timerInterval = setInterval(function() {{
                        callDuration = Math.floor((Date.now()-startTime)/1000);
                        timerEl.textContent = formatTime(callDuration);
                    }}, 1000);
                }});

                activeCall.on('disconnect', function() {{
                    console.log('Call disconnected');
                    if (timerInterval) clearInterval(timerInterval);
                    activeCall = null;

                    // Show call log form
                    showCallLogForm();
                }});

                activeCall.on('error', function(err) {{
                    console.error('Call error:', err);
                    setStatus('Call error', 'error');
                }});

            }} catch(e) {{
                console.error('Call failed:', e);
                setStatus('Call failed: ' + e.message, 'error');
            }}
        }}

        function showCallLogForm() {{
            setStatus('Log your call', 'logging');
            dialerSection.style.display = 'none';
            callForm.style.display = 'block';
            timerEl.style.display = 'none';

            // Reset form
            outcomeSelect.value = '';
            document.getElementById('notes').value = '';
            appointmentFields.style.display = 'none';
        }}

        function hangUp() {{
            if (activeCall) {{
                activeCall.disconnect();
            }}
        }}

        async function submitCallLog() {{
            const outcome = outcomeSelect.value;
            if (!outcome) {{
                alert('Please select a call outcome');
                return;
            }}

            const callData = {{
                call_sid: lastCallSid,
                va_identity: vaIdentity,
                lead_name: leadName || document.getElementById('lead-name-display').textContent,
                lead_phone: phoneInput.value,
                lead_address: leadAddress || document.getElementById('lead-address-display').textContent,
                duration_seconds: callDuration,
                twilio_status: 'completed',
                outcome: outcome,
                notes: document.getElementById('notes').value
            }};

            try {{
                setStatus('Saving...', 'logging');
                console.log('Saving call data:', callData);

                // Save call log
                const logResponse = await fetch('/api/dialer/log-call', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify(callData)
                }});
                const logResult = await logResponse.json();
                console.log('Log response:', logResult);

                // Check for errors
                if (!logResponse.ok || logResult.error) {{
                    throw new Error(logResult.error || 'Failed to save call log');
                }}

                // If appointment set, create appointment
                if (outcome === 'Appointment Set') {{
                    const aptDate = document.getElementById('apt-date').value;
                    const aptTime = document.getElementById('apt-time').value;
                    const aptType = document.getElementById('apt-type').value;

                    if (!aptDate || !aptTime) {{
                        alert('Please enter appointment date and time');
                        return;
                    }}

                    const aptData = {{
                        created_by: vaIdentity,
                        lead_name: callData.lead_name,
                        lead_phone: callData.lead_phone,
                        lead_address: callData.lead_address,
                        appointment_date: aptDate,
                        appointment_time: aptTime,
                        appointment_type: aptType,
                        notes: callData.notes,
                        call_log_id: logResult.call_log_id
                    }};

                    const aptResponse = await fetch('/api/dialer/set-appointment', {{
                        method: 'POST',
                        headers: {{ 'Content-Type': 'application/json' }},
                        body: JSON.stringify(aptData)
                    }});
                    console.log('Appointment response:', await aptResponse.json());

                    document.getElementById('success-msg').textContent = 'Call logged & appointment scheduled!';
                }} else {{
                    document.getElementById('success-msg').textContent = 'Call logged successfully!';
                }}

                // Show success
                callForm.style.display = 'none';
                successSection.style.display = 'block';
                setStatus('Saved!', 'ready');

            }} catch(e) {{
                console.error('Failed to save:', e);
                // Show error section
                callForm.style.display = 'none';
                document.getElementById('error-section').style.display = 'block';
                document.getElementById('error-msg').textContent = e.message || 'Unknown error. Check console for details.';
                setStatus('Save failed', 'error');
            }}
        }}

        function resetForNewCall() {{
            successSection.style.display = 'none';
            dialerSection.style.display = 'block';
            callBtn.style.display = 'block';
            hangupBtn.style.display = 'none';
            phoneInput.value = '';

            // Clear lead info if it was prefilled
            if (!leadPhone) {{
                document.getElementById('lead-info').style.display = 'none';
            }}
        }}

        function skipLog() {{
            callForm.style.display = 'none';
            dialerSection.style.display = 'block';
            callBtn.style.display = 'block';
            hangupBtn.style.display = 'none';
            setStatus('Ready to call', 'ready');
        }}

        function goToDashboard() {{
            // Redirect to VA Portal (different service)
            const vaPortalUrl = 'https://va-portal-production.up.railway.app';
            if (window.opener) {{
                window.opener.location.reload();  // Refresh the dashboard
                window.close();
            }} else {{
                window.location.href = vaPortalUrl;
            }}
        }}

        function retryFromError() {{
            document.getElementById('error-section').style.display = 'none';
            callForm.style.display = 'block';
            setStatus('Ready to save', 'logging');
        }}

        // Event listeners
        callBtn.onclick = makeCall;
        hangupBtn.onclick = hangUp;
        document.getElementById('submit-log').onclick = submitCallLog;
        document.getElementById('skip-log').onclick = skipLog;
        document.getElementById('new-call-btn').onclick = resetForNewCall;
        document.getElementById('back-to-dashboard').onclick = goToDashboard;
        document.getElementById('back-to-dashboard-error').onclick = goToDashboard;
        document.getElementById('retry-save').onclick = retryFromError;

        phoneInput.onkeypress = function(e) {{
            if (e.key === 'Enter' && !callBtn.disabled) makeCall();
        }};

        window.addEventListener('load', initDevice);
    </script>
</body>
</html>'''
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
