#!/usr/bin/env python3
"""
Aerial Leads - VA Dashboard
Clean, focused interface for Virtual Assistants
Shares data with admin dashboard for seamless communication
"""

import streamlit as st
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

# Page config
st.set_page_config(
    page_title="Lifeline - VA Portal",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded"
)

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

def load_leads():
    """Load leads from master file"""
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
    st.markdown("<h1 class='main-header'>📞 Lifeline VA Portal</h1>", unsafe_allow_html=True)
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

        page = st.radio(
            "Navigation",
            ["📊 My Stats", "📋 My Leads", "📱 Dialer", f"🔔 Callback Queue{callback_badge}", "📞 Call Tracker", "📥 Inbound Leads"],
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

    # Load data
    leads_df = load_leads()
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
            st.markdown(f"**{address}**")
            st.caption(f"{city} | Owner: {owner}")

        with col2:
            score = lead.get('motivation_score', lead.get('score', 0))
            if score >= 70:
                st.markdown("🔥 **Hot**")
            elif score >= 50:
                st.markdown("🌡️ Warm")
            else:
                st.markdown("❄️ Cold")

        with col3:
            if st.button("📞 Call", key=f"call_{idx}"):
                st.session_state.selected_lead = lead.to_dict()
                st.session_state.page = "Call Tracker"
                st.rerun()

        st.markdown("---")

def show_call_tracker(leads_df, va_name):
    st.markdown("## 📞 Call Tracker")
    st.markdown("Log your calls and track results.")

    # Quick log form
    st.markdown("### Log a Call")

    col1, col2 = st.columns(2)

    with col1:
        # Address input - either from leads or manual
        if not leads_df.empty and 'address' in leads_df.columns:
            addresses = leads_df['address'].dropna().tolist()[:100]
            address = st.selectbox("Property Address", [""] + addresses)
            if not address:
                address = st.text_input("Or enter manually", placeholder="123 Main St")
        else:
            address = st.text_input("Property Address", placeholder="123 Main St")

        phone = st.text_input("Phone Number Called", placeholder="(614) 555-1234")

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

        callback = st.date_input("Callback Date (if needed)", value=None)

    notes = st.text_area("Notes", placeholder="Any important details from the call...")

    if st.button("💾 Save Call", type="primary", use_container_width=True):
        if address:
            call_data = {
                "date": datetime.now().strftime('%Y-%m-%d'),
                "time": datetime.now().strftime('%H:%M'),
                "va_name": va_name,
                "address": address,
                "phone": phone,
                "result": result,
                "callback_date": str(callback) if callback else "",
                "notes": notes
            }
            save_call(call_data)
            st.markdown("<div class='success-msg'>✅ Call logged successfully!</div>", unsafe_allow_html=True)
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
