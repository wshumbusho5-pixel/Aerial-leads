#!/usr/bin/env python3
"""
Aerial Leads - VA Dashboard
Clean, focused interface for Virtual Assistants
Shares data with admin dashboard for seamless communication
"""

import streamlit as st

# Page config - MUST be first Streamlit command
st.set_page_config(
    page_title="Lifeline - VA Portal",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded"
)

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import os
import json

# Try to import auth modules
# Priority: Database auth (PostgreSQL) > CSV-based auth
DB_AUTH_AVAILABLE = False
CSV_AUTH_AVAILABLE = False

try:
    from auth.database import DatabaseAuth
    DB_AUTH_AVAILABLE = True
except ImportError:
    pass

try:
    from auth.lead_assignments import get_leads_for_va, log_call, update_lead_status
    LEAD_ASSIGNMENTS_AVAILABLE = True
except ImportError:
    LEAD_ASSIGNMENTS_AVAILABLE = False

try:
    from auth.twilio_calling import initiate_two_leg_call, TWILIO_AVAILABLE
except ImportError:
    TWILIO_AVAILABLE = False
    def initiate_two_leg_call(*args, **kwargs):
        return False, "Twilio not available", None

# Browser-based calling (WebRTC) - no phone needed, just browser + headset
BROWSER_DIALER_AVAILABLE = False
try:
    from auth.browser_calling import TWILIO_CLIENT_AVAILABLE, generate_access_token, get_dialer_html
    BROWSER_DIALER_AVAILABLE = TWILIO_CLIENT_AVAILABLE
except ImportError:
    BROWSER_DIALER_AVAILABLE = False

try:
    from auth.va_auth import VAAuth, check_login, require_login
    CSV_AUTH_AVAILABLE = True
except ImportError:
    pass

AUTH_AVAILABLE = DB_AUTH_AVAILABLE or CSV_AUTH_AVAILABLE

# Configure paths - works both locally and deployed
BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
PROCESSED_DIR = DATA_DIR / "processed"

# Ensure directories exist
DATA_DIR.mkdir(exist_ok=True)
PROCESSED_DIR.mkdir(exist_ok=True)

# Data files (shared with admin dashboard)
LEADS_FILE = PROCESSED_DIR / "master_leads.csv"
CALLS_FILE = PROCESSED_DIR / "call_log.csv"
INBOUND_FILE = PROCESSED_DIR / "inbound_leads.csv"
VA_ASSIGNMENTS_FILE = PROCESSED_DIR / "va_assignments.csv"

# RVM files (shared with admin dashboard)
RVM_CAMPAIGNS_FILE = DATA_DIR / "rvm_campaigns.json"
RVM_DROPS_FILE = DATA_DIR / "rvm_drops.csv"
CALLBACK_QUEUE_FILE = DATA_DIR / "callback_queue.csv"
VA_RVM_LIMITS_FILE = DATA_DIR / "va_rvm_limits.json"

# RVM Settings
RVM_DAILY_LIMIT_PER_VA = 50  # Max RVM drops per VA per day
RVM_CALLBACK_DELAY_MINUTES = 30  # Wait time after RVM before calling

# Custom CSS - Clean, professional look
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1e3a5f;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        color: #666;
        margin-bottom: 2rem;
    }
    .va-logo-header {
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .va-logo-header svg {
        width: 60px;
        height: auto;
    }
    .stat-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 12px;
        color: white;
        text-align: center;
        margin-bottom: 1rem;
    }
    .stat-number {
        font-size: 2.5rem;
        font-weight: bold;
    }
    .stat-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    .lead-card {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
        border-left: 4px solid #667eea;
        margin-bottom: 0.5rem;
    }
    .priority-high { border-left-color: #e74c3c; }
    .priority-medium { border-left-color: #f39c12; }
    .priority-low { border-left-color: #27ae60; }
    .success-msg {
        background: #d4edda;
        color: #155724;
        padding: 1rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Session state for VA login
if 'va_logged_in' not in st.session_state:
    st.session_state.va_logged_in = False
if 'va_name' not in st.session_state:
    st.session_state.va_name = ""
if 'session_id' not in st.session_state:
    st.session_state.session_id = None
if 'user_role' not in st.session_state:
    st.session_state.user_role = None

def load_leads(va_username: str = None):
    """Load leads assigned to this VA from database, fallback to CSV"""
    # Try database first (for leads assigned via dashboard)
    if LEAD_ASSIGNMENTS_AVAILABLE and va_username:
        try:
            db_leads = get_leads_for_va(va_username)
            if not db_leads.empty:
                return db_leads
        except Exception as e:
            pass  # Fall through to CSV

    # Fallback to CSV file
    if LEADS_FILE.exists():
        try:
            return pd.read_csv(LEADS_FILE)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def load_calls():
    """Load call history"""
    if CALLS_FILE.exists():
        try:
            return pd.read_csv(CALLS_FILE)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def save_call(call_data):
    """Save a call log entry - syncs with admin dashboard"""
    calls_df = load_calls()
    new_call = pd.DataFrame([call_data])
    calls_df = pd.concat([calls_df, new_call], ignore_index=True)
    calls_df.to_csv(CALLS_FILE, index=False)

# Appointments file
APPOINTMENTS_FILE = DATA_DIR / "appointments.csv"

def load_appointments():
    """Load scheduled appointments"""
    if APPOINTMENTS_FILE.exists():
        try:
            return pd.read_csv(APPOINTMENTS_FILE)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def save_appointment(appt_data, va_name):
    """Save a scheduled appointment"""
    appts_df = load_appointments()
    appt_data['scheduled_by'] = va_name
    appt_data['scheduled_at'] = datetime.now().isoformat()
    appt_data['status'] = 'scheduled'
    new_appt = pd.DataFrame([appt_data])
    appts_df = pd.concat([appts_df, new_appt], ignore_index=True)
    appts_df.to_csv(APPOINTMENTS_FILE, index=False)

def load_inbound_leads():
    """Load inbound leads from form submissions"""
    if INBOUND_FILE.exists():
        try:
            return pd.read_csv(INBOUND_FILE)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def get_va_stats(va_name, calls_df):
    """Calculate VA's personal stats"""
    if calls_df.empty:
        return {"today": 0, "week": 0, "contacts": 0, "appointments": 0}

    va_calls = calls_df[calls_df.get('va_name', '') == va_name] if 'va_name' in calls_df.columns else calls_df

    today = datetime.now().strftime('%Y-%m-%d')
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    stats = {
        "today": len(va_calls[va_calls.get('date', '') == today]) if 'date' in va_calls.columns else 0,
        "week": len(va_calls[va_calls.get('date', '') >= week_ago]) if 'date' in va_calls.columns else len(va_calls),
        "contacts": len(va_calls[va_calls.get('result', '') == 'Contact']) if 'result' in va_calls.columns else 0,
        "appointments": len(va_calls[va_calls.get('result', '') == 'Appointment']) if 'result' in va_calls.columns else 0
    }
    return stats

# ========================================
# RVM FUNCTIONS
# ========================================

def load_rvm_scripts():
    """Load available RVM scripts from admin settings"""
    if RVM_CAMPAIGNS_FILE.exists():
        try:
            with open(RVM_CAMPAIGNS_FILE, 'r') as f:
                data = json.load(f)
            return data.get('voicemail_scripts', {})
        except:
            return {}
    return {}

def get_va_rvm_usage(va_name):
    """Get VA's RVM usage for today"""
    today = datetime.now().strftime('%Y-%m-%d')

    if VA_RVM_LIMITS_FILE.exists():
        try:
            with open(VA_RVM_LIMITS_FILE, 'r') as f:
                data = json.load(f)
            va_data = data.get(va_name, {})
            if va_data.get('date') == today:
                return va_data.get('drops_today', 0)
        except:
            pass
    return 0

def increment_va_rvm_usage(va_name):
    """Increment VA's RVM usage count"""
    today = datetime.now().strftime('%Y-%m-%d')

    data = {}
    if VA_RVM_LIMITS_FILE.exists():
        try:
            with open(VA_RVM_LIMITS_FILE, 'r') as f:
                data = json.load(f)
        except:
            data = {}

    if va_name not in data or data[va_name].get('date') != today:
        data[va_name] = {'date': today, 'drops_today': 0}

    data[va_name]['drops_today'] += 1

    with open(VA_RVM_LIMITS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

    return data[va_name]['drops_today']

def drop_rvm(va_name, phone, address, owner, script_id, script_name):
    """Drop an RVM and log it - returns True if successful"""
    # Check daily limit
    current_usage = get_va_rvm_usage(va_name)
    if current_usage >= RVM_DAILY_LIMIT_PER_VA:
        return False, "Daily RVM limit reached"

    # Log the RVM drop
    drop_data = {
        'drop_id': f"DROP-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        'va_name': va_name,
        'target_number': phone,
        'address': address,
        'owner': owner,
        'script_id': script_id,
        'script_name': script_name,
        'dropped_at': datetime.now().isoformat(),
        'status': 'sent',
        'callback': False
    }

    # Save to RVM drops file
    if RVM_DROPS_FILE.exists():
        drops_df = pd.read_csv(RVM_DROPS_FILE)
    else:
        drops_df = pd.DataFrame()

    drops_df = pd.concat([drops_df, pd.DataFrame([drop_data])], ignore_index=True)
    drops_df.to_csv(RVM_DROPS_FILE, index=False)

    # Increment usage
    increment_va_rvm_usage(va_name)

    return True, drop_data['drop_id']

def add_to_callback_queue(va_name, phone, address, owner, rvm_drop_id):
    """Add lead to callback queue after RVM drop"""
    callback_time = datetime.now() + timedelta(minutes=RVM_CALLBACK_DELAY_MINUTES)

    callback_data = {
        'va_name': va_name,
        'phone': phone,
        'address': address,
        'owner': owner,
        'rvm_drop_id': rvm_drop_id,
        'added_at': datetime.now().isoformat(),
        'callback_at': callback_time.isoformat(),
        'status': 'pending'
    }

    if CALLBACK_QUEUE_FILE.exists():
        queue_df = pd.read_csv(CALLBACK_QUEUE_FILE)
    else:
        queue_df = pd.DataFrame()

    queue_df = pd.concat([queue_df, pd.DataFrame([callback_data])], ignore_index=True)
    queue_df.to_csv(CALLBACK_QUEUE_FILE, index=False)

def load_callback_queue(va_name):
    """Load callback queue for a VA"""
    if CALLBACK_QUEUE_FILE.exists():
        try:
            df = pd.read_csv(CALLBACK_QUEUE_FILE)
            # Filter for this VA and pending status
            df = df[(df['va_name'] == va_name) & (df['status'] == 'pending')]
            return df
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def get_ready_callbacks(va_name):
    """Get callbacks that are ready (past the delay time)"""
    df = load_callback_queue(va_name)
    if df.empty:
        return pd.DataFrame()

    now = datetime.now()
    ready = []
    for _, row in df.iterrows():
        callback_at = datetime.fromisoformat(row['callback_at'])
        if now >= callback_at:
            ready.append(row)

    return pd.DataFrame(ready) if ready else pd.DataFrame()

def mark_callback_complete(phone):
    """Mark a callback as complete"""
    if CALLBACK_QUEUE_FILE.exists():
        df = pd.read_csv(CALLBACK_QUEUE_FILE)
        df.loc[df['phone'] == phone, 'status'] = 'completed'
        df.to_csv(CALLBACK_QUEUE_FILE, index=False)

# Login Screen
def show_login():
    st.markdown("""<div class="va-logo-header"><svg viewBox="40 40 160 80" xmlns="http://www.w3.org/2000/svg"><path d="M 50 80 L 80 50 L 110 80 L 110 110 L 50 110 Z" fill="none" stroke="#1e3a5f" stroke-width="2.5" stroke-linejoin="miter"/><path d="M 110 80 L 135 80 L 145 65 L 155 95 L 165 80 L 190 80" fill="none" stroke="#1e3a5f" stroke-width="2.5" stroke-linecap="butt"/></svg></div>""", unsafe_allow_html=True)
    st.markdown("<h1 class='main-header'>Lifeline VA Portal</h1>", unsafe_allow_html=True)
    st.markdown("<p class='sub-header'>Virtual Assistant Dashboard</p>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### Sign In")

        if AUTH_AVAILABLE:
            # Use proper authentication
            username = st.text_input("Username", placeholder="Enter your username")
            password = st.text_input("Password", type="password", placeholder="Enter your password")

            if st.button("Sign In", type="primary", use_container_width=True):
                if username and password:
                    success = False
                    session_id = None
                    message = "Authentication failed"
                    user = None

                    # Try database auth first (shared across all apps)
                    if DB_AUTH_AVAILABLE:
                        try:
                            db_auth = DatabaseAuth()
                            success, session_id, message = db_auth.authenticate(username, password)
                            if success:
                                user = db_auth.get_user(username)
                        except Exception as e:
                            st.warning(f"Database auth unavailable: {e}")

                    # Fall back to CSV auth if database fails
                    if not success and CSV_AUTH_AVAILABLE:
                        try:
                            csv_auth = VAAuth()
                            success, session_id, message = csv_auth.authenticate(username, password)
                            if success:
                                user = csv_auth.get_user(username)
                        except Exception as e:
                            st.error(f"Authentication error: {e}")

                    if success and user:
                        st.session_state.va_logged_in = True
                        st.session_state.va_name = user.get('full_name', username)
                        st.session_state.va_username = username  # Store username for database lookups
                        st.session_state.va_phone = user.get('va_phone', '') or ''  # Store VA's phone for calling
                        st.session_state.session_id = session_id
                        st.session_state.user_role = user.get('role', 'va')
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
                else:
                    st.error("Please enter username and password")

            st.markdown("---")
            st.caption("Contact your admin if you forgot your credentials.")
        else:
            # Fallback to simple login (for deployment without auth module)
            va_name = st.text_input("Your Name", placeholder="Enter your name")
            va_pin = st.text_input("PIN", type="password", placeholder="Enter your PIN")

            if st.button("Sign In", type="primary", use_container_width=True):
                if va_name:
                    st.session_state.va_logged_in = True
                    st.session_state.va_name = va_name
                    st.rerun()
                else:
                    st.error("Please enter your name")

# Main Dashboard
def show_dashboard():
    va_name = st.session_state.va_name

    # Sidebar
    with st.sidebar:
        st.markdown(f"### 👤 {va_name}")
        st.markdown("---")

        # Check for ready callbacks to show badge
        ready_callbacks = get_ready_callbacks(va_name)
        callback_badge = f" ({len(ready_callbacks)})" if len(ready_callbacks) > 0 else ""

        # Check for upcoming appointments badge
        appts_df = load_appointments()
        upcoming_appts = 0
        if not appts_df.empty and 'date' in appts_df.columns:
            today = datetime.now().strftime('%Y-%m-%d')
            upcoming_appts = len(appts_df[(appts_df['date'] >= today) & (appts_df.get('scheduled_by', '') == va_name)])
        appt_badge = f" ({upcoming_appts})" if upcoming_appts > 0 else ""

        page = st.radio(
            "Navigation",
            ["📊 My Stats", "📋 My Leads", "📱 Dialer", f"🔔 Callback Queue{callback_badge}", "📞 Call Tracker", f"📅 Appointments{appt_badge}", "📥 Inbound Leads"],
            label_visibility="collapsed"
        )

        # RVM usage indicator
        rvm_usage = get_va_rvm_usage(va_name)
        st.markdown("---")
        st.caption(f"🎤 RVM Today: {rvm_usage}/{RVM_DAILY_LIMIT_PER_VA}")

        st.markdown("---")
        if st.button("Sign Out", use_container_width=True):
            # Properly logout from auth system
            if AUTH_AVAILABLE and st.session_state.session_id:
                auth = VAAuth()
                auth.logout(st.session_state.session_id)
            st.session_state.va_logged_in = False
            st.session_state.va_name = ""
            st.session_state.session_id = None
            st.session_state.user_role = None
            st.rerun()

    # Load data - use username for database lookup
    va_username = st.session_state.get('va_username', va_name)
    leads_df = load_leads(va_username)
    calls_df = load_calls()
    inbound_df = load_inbound_leads()
    stats = get_va_stats(va_name, calls_df)

    # Pages
    if "My Stats" in page:
        show_stats_page(stats, calls_df, va_name)
    elif "My Leads" in page:
        show_leads_page(leads_df, va_name)
    elif "Dialer" in page:
        show_dialer_page(leads_df, va_name)
    elif "Callback Queue" in page:
        show_callback_queue_page(va_name)
    elif "Call Tracker" in page:
        show_call_tracker(leads_df, va_name)
    elif "Appointments" in page:
        show_appointments_page(va_name)
    elif "Inbound" in page:
        show_inbound_page(inbound_df, va_name)

def show_stats_page(stats, calls_df, va_name):
    st.markdown("## 📊 My Stats")
    st.markdown(f"Welcome back, **{va_name}**! Here's your performance overview.")

    # Stats cards
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(f"""
        <div class='stat-card'>
            <div class='stat-number'>{stats['today']}</div>
            <div class='stat-label'>Calls Today</div>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class='stat-card'>
            <div class='stat-number'>{stats['week']}</div>
            <div class='stat-label'>Calls This Week</div>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
        <div class='stat-card'>
            <div class='stat-number'>{stats['contacts']}</div>
            <div class='stat-label'>Contacts Made</div>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
        <div class='stat-card'>
            <div class='stat-number'>{stats['appointments']}</div>
            <div class='stat-label'>Appointments</div>
        </div>
        """, unsafe_allow_html=True)

    # Recent activity
    st.markdown("### Recent Activity")
    if not calls_df.empty:
        recent = calls_df.tail(10).iloc[::-1]
        for _, call in recent.iterrows():
            result_color = "🟢" if call.get('result') == 'Contact' else "🟡" if call.get('result') == 'Voicemail' else "🔴"
            st.markdown(f"{result_color} **{call.get('address', 'Unknown')}** - {call.get('result', 'N/A')} - {call.get('date', '')}")
    else:
        st.info("No calls logged yet. Start making calls to see your activity!")

def show_leads_page(leads_df, va_name):
    st.markdown("## 📋 My Leads")
    st.markdown("Properties assigned to you for outreach.")

    # Get VA's phone number for calling
    va_username = st.session_state.get('va_username', '')
    va_phone = st.session_state.get('va_phone', '')

    # Phone setup section - Browser Dialer is now the primary option
    with st.expander("📱 Call Settings", expanded=True):
        # Initialize calling mode in session state
        if 'calling_mode' not in st.session_state:
            st.session_state.calling_mode = 'browser' if BROWSER_DIALER_AVAILABLE else 'phone'

        st.markdown("### Calling Method")

        # Check if user is admin
        user_role = st.session_state.get('user_role', 'va')
        is_admin = user_role == 'admin'

        # Browser Dialer is the only option for VAs (cost control)
        if BROWSER_DIALER_AVAILABLE:
            st.session_state.calling_mode = 'browser'  # Force browser mode
            st.success("🖥️ **Browser Dialer Active**")
            st.caption("Make calls directly from your browser using your headset.")
        else:
            st.error("Browser Dialer not configured - contact admin")

        # Only show phone dialer option to admins
        if is_admin:
            st.markdown("---")
            st.caption("🔒 Admin-only options:")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🖥️ Use Browser", use_container_width=True,
                           type="primary" if st.session_state.calling_mode == 'browser' else "secondary"):
                    st.session_state.calling_mode = 'browser'
                    st.rerun()
            with col2:
                if TWILIO_AVAILABLE:
                    if st.button("📱 Use Phone", use_container_width=True,
                               type="primary" if st.session_state.calling_mode == 'phone' else "secondary"):
                        st.session_state.calling_mode = 'phone'
                        st.rerun()
                else:
                    st.button("📱 Phone N/A", use_container_width=True, disabled=True)

        st.markdown("---")

        # Show settings based on selected mode
        if st.session_state.calling_mode == 'browser':
            st.markdown("""
            **How to use:**
            1. Use a headset with microphone (or laptop mic + speakers)
            2. Click 'Call' on any lead below
            3. A dialer opens in new tab - allow microphone access
            4. Talk through your headset!
            """)

            # Test browser dialer link
            public_site_url = os.environ.get('PUBLIC_SITE_URL', 'https://aerialleads-public-production.up.railway.app')
            test_url = f"{public_site_url}/dialer?identity={va_username or 'test-va'}&phone=&name=Test&address=Test"
            st.link_button("🧪 Test Browser Dialer", test_url, use_container_width=True)
            st.caption("Test your microphone before making real calls.")

        elif st.session_state.calling_mode == 'phone' and is_admin:
            st.info("📱 **Phone Dialer Mode** (Admin)")
            st.caption("Calls your phone first, then connects to lead.")

            new_phone = st.text_input(
                "Your Phone Number",
                value=va_phone,
                placeholder="+1 614 555 1234",
                key="va_phone_input"
            )

            if st.button("💾 Save Phone Number"):
                if new_phone:
                    st.session_state.va_phone = new_phone
                    if DB_AUTH_AVAILABLE and va_username:
                        try:
                            db_auth = DatabaseAuth()
                            conn = db_auth._get_connection()
                            cursor = conn.cursor()
                            cursor.execute("UPDATE users SET va_phone = %s WHERE username = %s", (new_phone, va_username))
                            conn.commit()
                            conn.close()
                            st.success(f"Phone saved: {new_phone}")
                        except Exception as e:
                            st.error(f"Could not save: {e}")
                    else:
                        st.success(f"Phone set: {new_phone}")

            if not va_phone:
                st.warning("⚠️ Enter your phone number to enable calling")

    if leads_df.empty:
        st.warning("No leads available. Check back later for new assignments.")
        return

    # Filter and search
    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input("🔍 Search by address", placeholder="Type to search...")
    with col2:
        sort_by = st.selectbox("Sort by", ["Priority", "Address", "Score"])

    # Filter leads
    filtered = leads_df.copy()
    if search:
        filtered = filtered[filtered['address'].str.contains(search, case=False, na=False)]

    # Display leads
    st.markdown(f"**{len(filtered)}** leads to work")
    st.markdown("---")

    for idx, lead in filtered.head(50).iterrows():
        col1, col2, col3 = st.columns([3, 1, 1])

        with col1:
            address = lead.get('address', lead.get('property_address', 'Unknown Address'))
            city = lead.get('city', '')
            owner = lead.get('owner_name', lead.get('owner', 'Unknown Owner'))
            phone = lead.get('phone', lead.get('phone_1', ''))
            phone_2 = lead.get('phone_2', '')

            st.markdown(f"**{address}**")
            st.caption(f"Owner: {owner}")

            # Display phone numbers prominently
            if phone:
                st.markdown(f"📞 **{phone}**" + (f" | {phone_2}" if phone_2 else ""))
            else:
                st.caption("No phone number")

        with col2:
            score = lead.get('motivation_score', lead.get('score', 0))
            if score and score >= 70:
                st.markdown("🔥 **Hot**")
            elif score and score >= 50:
                st.markdown("🌡️ Warm")
            else:
                st.markdown("❄️ Cold")

        with col3:
            # Make calls based on selected mode
            if phone:
                calling_mode = st.session_state.get('calling_mode', 'phone')
                va_phone = st.session_state.get('va_phone', '')
                va_identity = st.session_state.get('va_username', 'va-user')

                if calling_mode == 'browser' and BROWSER_DIALER_AVAILABLE:
                    # Browser dialer mode - open dialer in new tab
                    import urllib.parse
                    params = urllib.parse.urlencode({
                        'identity': va_identity,
                        'phone': phone,
                        'name': owner or '',
                        'address': address or ''
                    })
                    public_site_url = os.environ.get('PUBLIC_SITE_URL', 'https://aerialleads-public-production.up.railway.app')
                    dialer_url = f"{public_site_url}/dialer?{params}"

                    # Two buttons: Call and Log
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        st.link_button("📞", dialer_url, use_container_width=True)
                    with btn_col2:
                        if st.button("📝", key=f"log_{idx}", use_container_width=True):
                            # Save lead info and switch to Call Tracker
                            st.session_state.last_called_lead = {
                                'address': address,
                                'phone': phone,
                                'owner_name': owner,
                                'called_at': datetime.now().isoformat()
                            }
                            st.session_state.va_page = "📞 Call Tracker"
                            st.rerun()

                elif calling_mode == 'phone' and va_phone and TWILIO_AVAILABLE:
                    # Phone dialer mode - two-leg call
                    if st.button("📱 Call", key=f"call_{idx}", use_container_width=True):
                        with st.spinner("Calling your phone..."):
                            success, message, call_sid = initiate_two_leg_call(
                                va_phone=va_phone,
                                lead_phone=phone,
                                lead_name=owner,
                                lead_address=address
                            )
                            if success:
                                st.success(f"📞 {message}")
                                st.info("Answer your phone to connect to the lead!")
                            else:
                                st.error(f"❌ {message}")

                elif calling_mode == 'phone' and not va_phone:
                    st.button("📱 Call", key=f"call_{idx}", use_container_width=True, disabled=True)
                    st.caption("Set phone ↑")

                else:
                    # Fallback to tel: link
                    st.link_button("📞 Call", f"tel:{phone}", use_container_width=True)
            else:
                st.button("📞 No Phone", key=f"call_{idx}", disabled=True)

        st.markdown("---")

def show_call_tracker(leads_df, va_name):
    st.markdown("## 📞 Call Tracker")
    st.markdown("Log your calls and track results.")

    # Check for pre-filled lead info from "Log" button
    last_lead = st.session_state.get('last_called_lead', {})
    prefill_address = last_lead.get('address', '')
    prefill_phone = last_lead.get('phone', '')
    prefill_owner = last_lead.get('owner_name', '')

    # Show pre-filled info banner
    if prefill_address:
        st.success(f"📋 **Logging call for:** {prefill_address} | {prefill_owner} | {prefill_phone}")
        if st.button("✖️ Clear & Start Fresh", key="clear_prefill"):
            st.session_state.last_called_lead = {}
            st.rerun()

    # Quick log form
    st.markdown("### Log a Call")

    col1, col2 = st.columns(2)

    with col1:
        # Address - pre-filled if available
        if prefill_address:
            address = st.text_input("Property Address", value=prefill_address)
        elif not leads_df.empty and 'address' in leads_df.columns:
            addresses = leads_df['address'].dropna().tolist()[:100]
            address = st.selectbox("Property Address", [""] + addresses)
            if not address:
                address = st.text_input("Or enter manually", placeholder="123 Main St")
        else:
            address = st.text_input("Property Address", placeholder="123 Main St")

        # Phone - pre-filled if available
        phone = st.text_input("Phone Number Called", value=prefill_phone, placeholder="(614) 555-1234")

        # Owner name (for reference)
        if prefill_owner:
            st.caption(f"👤 Owner: {prefill_owner}")

    with col2:
        result = st.selectbox("Call Result", [
            "No Answer",
            "Voicemail Left",
            "Contact - Not Interested",
            "Contact - Maybe Later",
            "Contact - Interested",
            "Appointment Set",
            "Wrong Number",
            "Disconnected"
        ])

        # Show callback date for follow-ups
        if result in ["Contact - Maybe Later", "Contact - Interested", "No Answer"]:
            callback = st.date_input("📅 Callback Date", value=None)
        else:
            callback = None

    # Appointment scheduling section - appears when "Appointment Set"
    appointment_data = {}
    if result == "Appointment Set":
        st.markdown("---")
        st.markdown("### 📅 Schedule Appointment")

        appt_col1, appt_col2 = st.columns(2)

        with appt_col1:
            appt_date = st.date_input("Appointment Date", value=datetime.now().date() + timedelta(days=1))
            appt_time = st.time_input("Appointment Time", value=datetime.strptime("10:00", "%H:%M").time())

        with appt_col2:
            appt_type = st.selectbox("Appointment Type", [
                "Phone Call",
                "Property Visit",
                "Video Call",
                "Office Meeting"
            ])
            appt_with = st.text_input("Meeting With", value=prefill_owner, placeholder="Owner name")

        appointment_data = {
            'date': str(appt_date),
            'time': str(appt_time),
            'type': appt_type,
            'with': appt_with,
            'address': address,
            'phone': phone
        }

        st.info(f"📅 Appointment: {appt_type} on {appt_date} at {appt_time} with {appt_with}")

    notes = st.text_area("Notes", placeholder="Any important details from the call...")

    if st.button("💾 Save Call", type="primary", use_container_width=True):
        if address:
            call_data = {
                "date": datetime.now().strftime('%Y-%m-%d'),
                "time": datetime.now().strftime('%H:%M'),
                "va_name": va_name,
                "address": address,
                "phone": phone,
                "owner_name": prefill_owner,
                "result": result,
                "callback_date": str(callback) if callback else "",
                "notes": notes
            }

            # Add appointment info if set
            if appointment_data:
                call_data['appointment_date'] = appointment_data.get('date', '')
                call_data['appointment_time'] = appointment_data.get('time', '')
                call_data['appointment_type'] = appointment_data.get('type', '')

                # Also save to appointments file
                save_appointment(appointment_data, va_name)

            save_call(call_data)

            # Clear pre-filled data
            st.session_state.last_called_lead = {}

            st.markdown("<div class='success-msg'>✅ Call logged successfully!</div>", unsafe_allow_html=True)
            if appointment_data:
                st.success(f"📅 Appointment scheduled for {appointment_data['date']} at {appointment_data['time']}")
            st.balloons()
        else:
            st.error("Please enter the property address")

    # Recent calls
    st.markdown("### Your Recent Calls")
    calls_df = load_calls()
    if not calls_df.empty:
        va_calls = calls_df[calls_df.get('va_name', '') == va_name] if 'va_name' in calls_df.columns else calls_df
        if not va_calls.empty:
            st.dataframe(
                va_calls.tail(20).iloc[::-1][['date', 'address', 'result', 'notes']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("No calls logged yet today.")
    else:
        st.info("No calls logged yet. Make your first call!")

def show_appointments_page(va_name):
    """Display scheduled appointments for the VA"""
    st.markdown("## 📅 My Appointments")
    st.markdown("View and manage your scheduled appointments.")

    appts_df = load_appointments()

    if appts_df.empty:
        st.info("No appointments scheduled yet. Set appointments from the Call Tracker!")
        return

    # Filter to this VA's appointments
    if 'scheduled_by' in appts_df.columns:
        va_appts = appts_df[appts_df['scheduled_by'] == va_name].copy()
    else:
        va_appts = appts_df.copy()

    if va_appts.empty:
        st.info("No appointments scheduled yet. Set appointments from the Call Tracker!")
        return

    # Sort by date
    if 'date' in va_appts.columns:
        va_appts = va_appts.sort_values('date')

    today = datetime.now().strftime('%Y-%m-%d')

    # Upcoming appointments
    st.markdown("### 📅 Upcoming")
    if 'date' in va_appts.columns:
        upcoming = va_appts[va_appts['date'] >= today]
    else:
        upcoming = va_appts

    if not upcoming.empty:
        for idx, appt in upcoming.iterrows():
            appt_date = appt.get('date', 'No date')
            appt_time = appt.get('time', '')
            appt_type = appt.get('type', 'Appointment')
            appt_with = appt.get('with', 'Unknown')
            appt_address = appt.get('address', '')
            appt_phone = appt.get('phone', '')
            status = appt.get('status', 'scheduled')

            # Color code based on date
            is_today = appt_date == today
            color = "#28a745" if is_today else "#17a2b8"

            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    if is_today:
                        st.markdown(f"### 🔴 TODAY - {appt_time}")
                    else:
                        st.markdown(f"### {appt_date} at {appt_time}")

                    st.markdown(f"**{appt_type}** with **{appt_with}**")
                    if appt_address:
                        st.caption(f"📍 {appt_address}")
                    if appt_phone:
                        st.caption(f"📞 {appt_phone}")

                with col2:
                    st.markdown(f"**Status:** {status.title()}")

                with col3:
                    if st.button("✅ Complete", key=f"complete_{idx}"):
                        # Update status
                        appts_df.loc[idx, 'status'] = 'completed'
                        appts_df.to_csv(APPOINTMENTS_FILE, index=False)
                        st.success("Marked complete!")
                        st.rerun()

                    if st.button("❌ Cancel", key=f"cancel_{idx}"):
                        appts_df.loc[idx, 'status'] = 'cancelled'
                        appts_df.to_csv(APPOINTMENTS_FILE, index=False)
                        st.warning("Appointment cancelled")
                        st.rerun()

                st.markdown("---")
    else:
        st.info("No upcoming appointments.")

    # Past appointments
    st.markdown("### 📜 Past Appointments")
    if 'date' in va_appts.columns:
        past = va_appts[va_appts['date'] < today]
        if not past.empty:
            display_cols = ['date', 'time', 'type', 'with', 'address', 'status']
            display_cols = [c for c in display_cols if c in past.columns]
            st.dataframe(past[display_cols].tail(20).iloc[::-1], use_container_width=True, hide_index=True)
        else:
            st.caption("No past appointments.")

def show_dialer_page(leads_df, va_name):
    st.markdown("## 📱 Dialer")
    st.markdown("Power through your call list efficiently.")

    if leads_df.empty:
        st.warning("No leads loaded. Check back when leads are assigned.")
        return

    # Session state for current lead index
    if 'dialer_index' not in st.session_state:
        st.session_state.dialer_index = 0

    # Get current lead
    total_leads = len(leads_df)
    current_index = st.session_state.dialer_index % total_leads
    current_lead = leads_df.iloc[current_index]

    # Progress bar
    st.progress(current_index / total_leads, text=f"Lead {current_index + 1} of {total_leads}")

    # Current lead card
    st.markdown("### Current Lead")
    col1, col2 = st.columns([2, 1])

    with col1:
        address = current_lead.get('address', current_lead.get('property_address', 'Unknown'))
        owner = current_lead.get('owner_name', current_lead.get('owner', 'Unknown'))
        phone = current_lead.get('phone', current_lead.get('phone_1', 'No phone'))
        phone2 = current_lead.get('phone_2', '')
        city = current_lead.get('city', '')

        st.markdown(f"## 🏠 {address}")
        st.markdown(f"**{city}**" if city else "")
        st.markdown(f"### 👤 {owner}")
        st.markdown("---")

        # Phone numbers - clickable
        st.markdown("### 📞 Phone Numbers")
        if phone and phone != 'No phone':
            st.markdown(f"**Primary:** [{phone}](tel:{phone})")
            st.code(phone, language=None)
        if phone2:
            st.markdown(f"**Secondary:** [{phone2}](tel:{phone2})")
            st.code(phone2, language=None)

    with col2:
        # Lead info
        score = current_lead.get('motivation_score', current_lead.get('score', 0))
        equity = current_lead.get('equity_percent', 'N/A')

        st.markdown("### Lead Score")
        if score >= 70:
            st.markdown(f"# 🔥 {score}")
            st.caption("HOT LEAD")
        elif score >= 50:
            st.markdown(f"# 🌡️ {score}")
            st.caption("WARM LEAD")
        else:
            st.markdown(f"# ❄️ {score}")
            st.caption("COLD LEAD")

        if equity != 'N/A':
            st.markdown(f"**Equity:** {equity}%")

    # RVM Section - Warm before calling
    st.markdown("---")
    st.markdown("### 🎤 Warm This Lead First")

    rvm_scripts = load_rvm_scripts()
    rvm_usage = get_va_rvm_usage(va_name)
    rvm_remaining = RVM_DAILY_LIMIT_PER_VA - rvm_usage

    if rvm_remaining > 0 and rvm_scripts and phone and phone != 'No phone':
        col_rvm1, col_rvm2 = st.columns([2, 1])

        with col_rvm1:
            script_options = {sid: s.get('name', sid) for sid, s in rvm_scripts.items()}
            selected_script = st.selectbox(
                "Select voicemail script",
                options=list(script_options.keys()),
                format_func=lambda x: script_options.get(x, x),
                key="rvm_script_select"
            )

        with col_rvm2:
            st.caption(f"RVM remaining today: {rvm_remaining}")
            if st.button("🎤 Drop RVM & Queue", use_container_width=True, type="secondary"):
                success, result = drop_rvm(
                    va_name=va_name,
                    phone=phone,
                    address=address,
                    owner=owner,
                    script_id=selected_script,
                    script_name=script_options.get(selected_script, selected_script)
                )
                if success:
                    add_to_callback_queue(va_name, phone, address, owner, result)
                    st.success(f"✅ RVM dropped! Lead added to callback queue (call in {RVM_CALLBACK_DELAY_MINUTES} min)")
                    st.session_state.dialer_index += 1
                    st.rerun()
                else:
                    st.error(f"❌ {result}")
    elif rvm_remaining <= 0:
        st.warning(f"⚠️ Daily RVM limit reached ({RVM_DAILY_LIMIT_PER_VA}). Continue with direct calls.")
    elif not rvm_scripts:
        st.info("💡 No RVM scripts available. Ask admin to set up scripts.")
    elif not phone or phone == 'No phone':
        st.info("📵 No phone number for RVM.")

    st.markdown("---")

    # Quick disposition buttons
    st.markdown("### Quick Disposition (Direct Call)")
    col1, col2, col3, col4 = st.columns(4)

    def log_and_next(result):
        call_data = {
            "date": datetime.now().strftime('%Y-%m-%d'),
            "time": datetime.now().strftime('%H:%M'),
            "va_name": va_name,
            "address": address,
            "phone": phone,
            "result": result,
            "callback_date": "",
            "notes": f"Quick dial - {result}"
        }
        save_call(call_data)
        st.session_state.dialer_index += 1

    with col1:
        if st.button("❌ No Answer", use_container_width=True):
            log_and_next("No Answer")
            # Offer RVM after no answer
            st.session_state.show_rvm_after_no_answer = True
            st.rerun()

    with col2:
        if st.button("📧 Voicemail", use_container_width=True):
            log_and_next("Voicemail Left")
            st.rerun()

    # Show RVM option after No Answer (if triggered)
    if st.session_state.get('show_rvm_after_no_answer') and rvm_remaining > 0 and rvm_scripts:
        st.info("💡 **No answer?** Drop an RVM so they know who called!")
        if st.button("🎤 Drop RVM for Last Lead", use_container_width=True):
            # Get previous lead (we already moved to next)
            prev_index = (st.session_state.dialer_index - 1) % total_leads
            prev_lead = leads_df.iloc[prev_index]
            prev_phone = prev_lead.get('phone', prev_lead.get('phone_1', ''))
            prev_address = prev_lead.get('address', prev_lead.get('property_address', ''))
            prev_owner = prev_lead.get('owner_name', prev_lead.get('owner', ''))

            if prev_phone:
                success, result = drop_rvm(va_name, prev_phone, prev_address, prev_owner,
                                          list(rvm_scripts.keys())[0],
                                          list(rvm_scripts.values())[0].get('name', 'Default'))
                if success:
                    add_to_callback_queue(va_name, prev_phone, prev_address, prev_owner, result)
                    st.success("✅ RVM dropped! Added to callback queue.")
            st.session_state.show_rvm_after_no_answer = False
            st.rerun()

    with col3:
        if st.button("🚫 Not Interested", use_container_width=True):
            log_and_next("Contact - Not Interested")
            st.rerun()

    with col4:
        if st.button("🔥 Interested!", use_container_width=True, type="primary"):
            log_and_next("Contact - Interested")
            st.rerun()

    # Navigation
    st.markdown("---")
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        if st.button("⬅️ Previous", use_container_width=True):
            st.session_state.dialer_index = max(0, st.session_state.dialer_index - 1)
            st.rerun()

    with col2:
        skip_to = st.number_input("Jump to lead #", min_value=1, max_value=total_leads, value=current_index + 1)
        if skip_to != current_index + 1:
            st.session_state.dialer_index = skip_to - 1
            st.rerun()

    with col3:
        if st.button("Skip ➡️", use_container_width=True):
            st.session_state.dialer_index += 1
            st.rerun()

def show_callback_queue_page(va_name):
    st.markdown("## 🔔 Callback Queue")
    st.markdown("Leads you've warmed with RVM - ready for follow-up calls!")

    # Get all callbacks and ready callbacks
    all_callbacks = load_callback_queue(va_name)
    ready_callbacks = get_ready_callbacks(va_name)

    # Stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total in Queue", len(all_callbacks))
    with col2:
        st.metric("Ready to Call", len(ready_callbacks), delta="🔥" if len(ready_callbacks) > 0 else None)
    with col3:
        rvm_usage = get_va_rvm_usage(va_name)
        st.metric("RVM Drops Today", f"{rvm_usage}/{RVM_DAILY_LIMIT_PER_VA}")

    st.markdown("---")

    # Ready callbacks section
    if not ready_callbacks.empty:
        st.success(f"🔥 **{len(ready_callbacks)} leads ready for callback!** They've heard your voicemail.")

        for idx, callback in ready_callbacks.iterrows():
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    st.markdown(f"### 🏠 {callback.get('address', 'Unknown')}")
                    st.markdown(f"**Owner:** {callback.get('owner', 'N/A')}")
                    phone = callback.get('phone', '')
                    st.markdown(f"**Phone:** [{phone}](tel:{phone})")
                    st.code(phone, language=None)

                with col2:
                    added = callback.get('added_at', '')
                    if added:
                        try:
                            added_time = datetime.fromisoformat(added)
                            st.caption(f"RVM sent: {added_time.strftime('%H:%M')}")
                        except:
                            pass
                    st.markdown("✅ **READY**")

                with col3:
                    if st.button("📞 Called", key=f"called_{idx}", use_container_width=True, type="primary"):
                        mark_callback_complete(phone)
                        st.success("Marked as called!")
                        st.rerun()

                    if st.button("⏭️ Skip", key=f"skip_cb_{idx}", use_container_width=True):
                        mark_callback_complete(phone)
                        st.rerun()

                st.markdown("---")

    # Pending callbacks (not yet ready)
    if not all_callbacks.empty:
        pending = all_callbacks[~all_callbacks.index.isin(ready_callbacks.index)] if not ready_callbacks.empty else all_callbacks

        if not pending.empty:
            st.markdown("### ⏳ Warming Up...")
            st.caption("These leads have received RVM but aren't ready for callback yet.")

            for idx, callback in pending.iterrows():
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.markdown(f"**{callback.get('address', 'Unknown')}** - {callback.get('owner', '')}")

                with col2:
                    callback_at = callback.get('callback_at', '')
                    if callback_at:
                        try:
                            cb_time = datetime.fromisoformat(callback_at)
                            mins_left = max(0, int((cb_time - datetime.now()).total_seconds() / 60))
                            st.caption(f"⏰ Ready in {mins_left} min")
                        except:
                            st.caption("⏰ Pending")

    if all_callbacks.empty:
        st.info("No leads in callback queue. Use the Dialer to drop RVM and warm leads!")
        st.markdown("""
        **How it works:**
        1. Go to **Dialer**
        2. Click **"🎤 Drop RVM & Queue"** on a lead
        3. Lead gets voicemail dropped
        4. After 30 minutes, they appear here **READY** for callback
        5. Higher answer rate because they just heard your message!
        """)

def show_inbound_page(inbound_df, va_name):
    st.markdown("## 📥 Inbound Leads")
    st.markdown("People who submitted their information through our website.")

    if inbound_df.empty:
        st.info("No inbound leads yet. These will appear when homeowners submit forms on the website.")
        return

    # Priority badge
    st.warning("⚡ **These are HOT leads!** They came to us. Call them first!")

    for idx, lead in inbound_df.iterrows():
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                st.markdown(f"### {lead.get('address', 'Unknown Address')}")
                st.markdown(f"**Name:** {lead.get('name', 'N/A')}")
                st.markdown(f"**Phone:** {lead.get('phone', 'N/A')}")
                st.markdown(f"**Email:** {lead.get('email', 'N/A')}")
                if lead.get('message'):
                    st.markdown(f"**Message:** {lead.get('message')}")

            with col2:
                submitted = lead.get('submitted_at', lead.get('date', 'N/A'))
                st.markdown(f"📅 {submitted}")

            with col3:
                status = lead.get('status', 'New')
                if status == 'New':
                    st.markdown("🆕 **NEW**")
                elif status == 'Contacted':
                    st.markdown("✅ Contacted")
                elif status == 'Scheduled':
                    st.markdown("📅 Scheduled")

                if st.button("📞 Log Call", key=f"inbound_{idx}"):
                    st.session_state.selected_inbound = lead.to_dict()

            st.markdown("---")

# Main app
def main():
    if not st.session_state.va_logged_in:
        show_login()
    else:
        show_dashboard()

if __name__ == "__main__":
    main()
