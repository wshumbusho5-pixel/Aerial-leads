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
TWILIO_TWIML_APP_SID = os.environ.get('TWILIO_TWIML_APP_SID', '')
TWILIO_API_KEY = os.environ.get('TWILIO_API_KEY', '')
TWILIO_API_SECRET = os.environ.get('TWILIO_API_SECRET', '')

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
except ImportError:
    logger.warning("Twilio library not installed")


def generate_twilio_token(identity: str):
    """Generate access token for browser calling."""
    if not TWILIO_CLIENT_AVAILABLE or not TWILIO_API_KEY or not TWILIO_API_SECRET:
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
        return token.to_jwt()
    except Exception as e:
        logger.error(f"Token generation failed: {e}")
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
        "api_key_configured": bool(TWILIO_API_KEY and TWILIO_API_SECRET)
    }


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
    if not TWILIO_CLIENT_AVAILABLE:
        return HTMLResponse(content="<Response><Say>Not configured</Say></Response>", media_type="application/xml")

    form = await request.form()
    to_number = clean_phone(form.get('To', ''))

    if not to_number:
        return HTMLResponse(content="<Response><Say>Invalid number</Say></Response>", media_type="application/xml")

    response = VoiceResponse()
    dial = Dial(caller_id=TWILIO_PHONE_NUMBER, timeout=30)
    dial.number(to_number)
    response.append(dial)
    response.say("Call ended. Goodbye.")

    logger.info(f"Browser call to: {to_number}")
    return HTMLResponse(content=str(response), media_type="application/xml")


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

    # Return dialer HTML
    html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Browser Dialer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://sdk.twilio.com/js/client/releases/1.14.0/twilio.min.js"></script>
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
            max-width: 400px;
            width: 100%;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }}
        h1 {{ font-size: 1.5rem; text-align: center; margin-bottom: 20px; }}
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
        .lead-info {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .lead-info h3 {{ font-size: 1rem; margin-bottom: 5px; }}
        .lead-info .phone {{ font-size: 1.3rem; font-weight: 700; color: #4CAF50; margin-top: 10px; }}
        input {{
            width: 100%;
            padding: 15px;
            font-size: 1.2rem;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            margin-bottom: 15px;
            text-align: center;
        }}
        input:focus {{ outline: none; border-color: #4CAF50; }}
        .btn {{
            width: 100%;
            padding: 15px;
            font-size: 1.1rem;
            font-weight: 600;
            border: none;
            border-radius: 10px;
            cursor: pointer;
        }}
        .btn-call {{ background: #4CAF50; color: white; }}
        .btn-call:disabled {{ background: #ccc; }}
        .btn-hangup {{ background: #dc3545; color: white; display: none; }}
        .timer {{
            text-align: center;
            font-size: 2rem;
            font-weight: 700;
            margin: 20px 0;
            display: none;
        }}
    </style>
</head>
<body>
    <div class="dialer">
        <h1>Browser Dialer</h1>
        <div id="status" class="status">Initializing...</div>

        <div id="lead-info" class="lead-info" style="display:{{'block' if phone else 'none'}}">
            <h3>{name or 'Lead'}</h3>
            <p>{address or ''}</p>
            <div class="phone">{phone or ''}</div>
        </div>

        <input type="tel" id="phone" placeholder="Enter phone number" value="{phone or ''}">
        <div id="timer" class="timer">00:00</div>
        <button id="call-btn" class="btn btn-call" disabled>Call</button>
        <button id="hangup-btn" class="btn btn-hangup">Hang Up</button>
    </div>

    <script>
        const token = "{token}";
        let device, activeCall, timerInterval, startTime;

        const statusEl = document.getElementById('status');
        const phoneInput = document.getElementById('phone');
        const callBtn = document.getElementById('call-btn');
        const hangupBtn = document.getElementById('hangup-btn');
        const timerEl = document.getElementById('timer');

        function setStatus(text, cls) {{
            statusEl.textContent = text;
            statusEl.className = 'status ' + cls;
        }}

        function formatTime(sec) {{
            return String(Math.floor(sec/60)).padStart(2,'0') + ':' + String(sec%60).padStart(2,'0');
        }}

        async function init() {{
            try {{
                device = new Twilio.Device(token, {{
                    codecPreferences: ['opus', 'pcmu'],
                    enableRingingState: true
                }});

                device.on('ready', () => {{
                    setStatus('Ready to call', 'ready');
                    callBtn.disabled = false;
                }});

                device.on('error', (err) => setStatus('Error: ' + err.message, 'error'));

                device.on('connect', (conn) => {{
                    activeCall = conn;
                    setStatus('On Call', 'on-call');
                    callBtn.style.display = 'none';
                    hangupBtn.style.display = 'block';
                    timerEl.style.display = 'block';
                    startTime = Date.now();
                    timerInterval = setInterval(() => {{
                        timerEl.textContent = formatTime(Math.floor((Date.now()-startTime)/1000));
                    }}, 1000);
                }});

                device.on('disconnect', () => {{
                    activeCall = null;
                    setStatus('Call ended', 'ready');
                    callBtn.style.display = 'block';
                    hangupBtn.style.display = 'none';
                    clearInterval(timerInterval);
                }});
            }} catch(e) {{
                setStatus('Init failed: ' + e.message, 'error');
            }}
        }}

        callBtn.onclick = () => {{
            const num = phoneInput.value.trim();
            if (!num) return alert('Enter a phone number');
            setStatus('Connecting...', 'connecting');
            device.connect({{ To: num }});
        }};

        hangupBtn.onclick = () => {{
            if (activeCall) activeCall.disconnect();
            device.disconnectAll();
        }};

        phoneInput.onkeypress = (e) => {{
            if (e.key === 'Enter' && !callBtn.disabled) callBtn.click();
        }};

        init();
    </script>
</body>
</html>'''
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
