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

        conn.commit()
        conn.close()
        logger.info("Database initialized with call_logs and appointments tables")
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
        "db_error": DB_ERROR
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
        .lead-info .phone {{ font-size: 1.3rem; font-weight: 700; color: #4CAF50; margin-top: 10px; }}
        input, select, textarea {{
            width: 100%;
            padding: 12px 15px;
            font-size: 1rem;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            margin-bottom: 12px;
        }}
        input[type="tel"] {{ text-align: center; font-size: 1.2rem; }}
        input:focus, select:focus, textarea:focus {{ outline: none; border-color: #4CAF50; }}
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
        .btn-call {{ background: #4CAF50; color: white; }}
        .btn-call:hover {{ background: #43a047; }}
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
