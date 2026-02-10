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

# Clear stale cache on each load to prevent showing old data
if 'cache_cleared' not in st.session_state:
    st.cache_data.clear()
    st.session_state.cache_cleared = True

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

# Qualified buyers module for IDS team
QUALIFIED_BUYERS_AVAILABLE = False
try:
    from buyers.qualified_buyers import (
        add_buyer, get_buyers_df, get_buyer_stats,
        PROPERTY_TYPES, CONDITION_PREFS, INTEREST_LEVELS, INTEREST_DISPLAY
    )
    QUALIFIED_BUYERS_AVAILABLE = True
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

# Investor/Buyer data directories
BUYERS_DATA_DIR = BASE_DIR / "data" / "buyers" / "processed"

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
    """Load call history from database (primary) or CSV (fallback)"""
    # Try PostgreSQL first
    if DB_AUTH_AVAILABLE:
        try:
            db_auth = DatabaseAuth()
            conn = db_auth._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, va_identity as va_name, lead_name as owner_name,
                       lead_phone as phone, lead_address as address,
                       call_start, duration_seconds as duration,
                       outcome as result, notes, follow_up_date as callback_date
                FROM call_logs
                ORDER BY call_start DESC NULLS LAST
                LIMIT 500
            """)
            rows = cursor.fetchall()
            conn.close()

            if rows:
                # Rows are dicts from RealDictCursor
                df = pd.DataFrame([dict(row) for row in rows])
                # Extract date and time from call_start
                if 'call_start' in df.columns and not df['call_start'].isna().all():
                    df['date'] = pd.to_datetime(df['call_start']).dt.strftime('%Y-%m-%d')
                    df['time'] = pd.to_datetime(df['call_start']).dt.strftime('%H:%M')
                else:
                    df['date'] = datetime.now().strftime('%Y-%m-%d')
                    df['time'] = datetime.now().strftime('%H:%M')
                # Convert callback_date to string for comparisons
                if 'callback_date' in df.columns:
                    df['callback_date'] = df['callback_date'].apply(
                        lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else (str(x) if x else '')
                    )
                return df
            else:
                # No rows in database, return empty DataFrame with expected columns
                return pd.DataFrame(columns=['id', 'va_name', 'owner_name', 'phone', 'address',
                                            'date', 'time', 'duration', 'result', 'notes', 'callback_date'])
        except Exception as e:
            import traceback
            print(f"Database error in load_calls: {e}")
            traceback.print_exc()
            # Fall through to CSV

    # Fallback to CSV
    if CALLS_FILE.exists():
        try:
            return pd.read_csv(CALLS_FILE)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def save_call(call_data):
    """Save a call log entry to database and CSV"""
    # Save to PostgreSQL first
    if DB_AUTH_AVAILABLE:
        try:
            db_auth = DatabaseAuth()
            conn = db_auth._get_connection()
            cursor = conn.cursor()

            # Map VA dashboard format to database format
            cursor.execute("""
                INSERT INTO call_logs
                (va_identity, lead_name, lead_phone, lead_address, outcome, notes, follow_up_date, call_start)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """, (
                call_data.get('va_name', ''),
                call_data.get('owner_name', ''),
                call_data.get('phone', ''),
                call_data.get('address', ''),
                call_data.get('result', ''),
                call_data.get('notes', ''),
                call_data.get('callback_date') or None
            ))
            conn.commit()
            conn.close()
            print(f"Call saved to database: {call_data.get('va_name')} - {call_data.get('result')}")
        except Exception as e:
            import traceback
            print(f"Database error in save_call: {e}")
            traceback.print_exc()

    # Also save to CSV for backward compatibility
    calls_df = pd.DataFrame()
    if CALLS_FILE.exists():
        try:
            calls_df = pd.read_csv(CALLS_FILE)
        except:
            pass
    new_call = pd.DataFrame([call_data])
    calls_df = pd.concat([calls_df, new_call], ignore_index=True)
    try:
        calls_df.to_csv(CALLS_FILE, index=False)
    except:
        pass  # Ignore CSV errors on Railway

# Appointments file
APPOINTMENTS_FILE = DATA_DIR / "appointments.csv"

def load_appointments():
    """Load scheduled appointments from database (primary) or CSV (fallback)"""
    # Try PostgreSQL first
    if DB_AUTH_AVAILABLE:
        try:
            db_auth = DatabaseAuth()
            conn = db_auth._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, created_by as scheduled_by, lead_name as "with",
                       lead_phone as phone, lead_address as address,
                       appointment_date as date, appointment_time as time,
                       appointment_type as type, status, notes
                FROM appointments
                WHERE status = 'scheduled'
                ORDER BY appointment_date, appointment_time
            """)
            rows = cursor.fetchall()
            conn.close()
            if rows:
                df = pd.DataFrame([dict(row) for row in rows])
                # Convert date/time to strings for comparisons
                if 'date' in df.columns:
                    df['date'] = df['date'].apply(
                        lambda x: x.strftime('%Y-%m-%d') if hasattr(x, 'strftime') else str(x) if x else ''
                    )
                if 'time' in df.columns:
                    df['time'] = df['time'].apply(
                        lambda x: x.strftime('%H:%M') if hasattr(x, 'strftime') else str(x) if x else ''
                    )
                return df
            else:
                return pd.DataFrame(columns=['id', 'scheduled_by', 'with', 'phone', 'address',
                                            'date', 'time', 'type', 'status', 'notes'])
        except Exception as e:
            import traceback
            print(f"Database error in load_appointments: {e}")
            traceback.print_exc()

    # Fallback to CSV
    if APPOINTMENTS_FILE.exists():
        try:
            return pd.read_csv(APPOINTMENTS_FILE)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def load_investors(county: str = 'franklin', tier: str = None):
    """Load investor prospects from CSV files

    Args:
        county: 'franklin' (Columbus) or 'hamilton' (Cincinnati)
        tier: 'tier_1', 'tier_2', 'tier_3', or None for all
    """
    investors = []

    if tier:
        files = {tier: f'investor_prospects_{county}_{tier}.csv'}
    else:
        files = {
            'tier_1': f'investor_prospects_{county}_tier_1.csv',
            'tier_2': f'investor_prospects_{county}_tier_2.csv',
            'tier_3': f'investor_prospects_{county}_tier_3.csv',
        }

    for tier_name, filename in files.items():
        filepath = BUYERS_DATA_DIR / filename
        if filepath.exists():
            try:
                df = pd.read_csv(filepath)
                df['tier'] = tier_name
                investors.append(df)
            except Exception as e:
                print(f"Error loading {filename}: {e}")

    if investors:
        df = pd.concat(investors, ignore_index=True)
        df = df.fillna('')
        return df
    return pd.DataFrame()

def save_appointment(appt_data, va_name):
    """Save a scheduled appointment to database and CSV"""
    appt_data['scheduled_by'] = va_name
    appt_data['scheduled_at'] = datetime.now().isoformat()
    appt_data['status'] = 'scheduled'

    # Save to PostgreSQL first
    if DB_AUTH_AVAILABLE:
        try:
            db_auth = DatabaseAuth()
            conn = db_auth._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO appointments
                (created_by, lead_name, lead_phone, lead_address,
                 appointment_date, appointment_time, appointment_type, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                va_name,
                appt_data.get('with', ''),
                appt_data.get('phone', ''),
                appt_data.get('address', ''),
                appt_data.get('date', ''),
                appt_data.get('time', ''),
                appt_data.get('type', 'callback'),
                appt_data.get('notes', '')
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            pass  # Continue to CSV

    # Also save to CSV for backward compatibility
    appts_df = pd.DataFrame()
    if APPOINTMENTS_FILE.exists():
        try:
            appts_df = pd.read_csv(APPOINTMENTS_FILE)
        except:
            pass
    new_appt = pd.DataFrame([appt_data])
    appts_df = pd.concat([appts_df, new_appt], ignore_index=True)
    try:
        appts_df.to_csv(APPOINTMENTS_FILE, index=False)
    except:
        pass

# Daily Reports file
REPORTS_FILE = DATA_DIR / "va_daily_reports.csv"

def load_reports():
    """Load daily reports"""
    if REPORTS_FILE.exists():
        try:
            return pd.read_csv(REPORTS_FILE)
        except:
            return pd.DataFrame()
    return pd.DataFrame()

def save_daily_report(report_data):
    """Save a daily report"""
    reports_df = load_reports()
    new_report = pd.DataFrame([report_data])
    reports_df = pd.concat([reports_df, new_report], ignore_index=True)
    reports_df.to_csv(REPORTS_FILE, index=False)

def get_today_stats(va_name, calls_df):
    """Get detailed stats for today"""
    today = datetime.now().strftime('%Y-%m-%d')

    if calls_df.empty or 'va_name' not in calls_df.columns:
        return {
            'total_calls': 0,
            'contacts': 0,
            'appointments': 0,
            'interested': 0,
            'not_interested': 0,
            'no_answer': 0,
            'voicemails': 0
        }

    va_today = calls_df[(calls_df['va_name'] == va_name) & (calls_df['date'] == today)]

    if va_today.empty:
        return {
            'total_calls': 0,
            'contacts': 0,
            'appointments': 0,
            'interested': 0,
            'not_interested': 0,
            'no_answer': 0,
            'voicemails': 0
        }

    results = va_today['result'].value_counts().to_dict() if 'result' in va_today.columns else {}

    return {
        'total_calls': len(va_today),
        'contacts': results.get('Contact - Interested', 0) + results.get('Contact - Maybe Later', 0) + results.get('Contact - Not Interested', 0),
        'appointments': results.get('Appointment Set', 0),
        'interested': results.get('Contact - Interested', 0),
        'not_interested': results.get('Contact - Not Interested', 0),
        'no_answer': results.get('No Answer', 0),
        'voicemails': results.get('Voicemail Left', 0)
    }

def load_inbound_leads():
    """Load inbound leads from database (primary) or CSV (fallback)"""
    # Try database first (shared with public site)
    if DB_AUTH_AVAILABLE:
        try:
            db_auth = DatabaseAuth()
            conn = db_auth._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM inbound_leads
                ORDER BY captured_at DESC
                LIMIT 100
            """)
            rows = cursor.fetchall()
            conn.close()
            if rows:
                # Convert to DataFrame
                columns = ['id', 'captured_at', 'source_page', 'name', 'phone', 'email',
                          'property_address', 'message', 'lead_type', 'ip_address',
                          'status', 'assigned_to', 'notes']
                df = pd.DataFrame(rows, columns=columns[:len(rows[0])] if rows else columns)
                # Rename for consistency
                if 'property_address' in df.columns:
                    df['address'] = df['property_address']
                return df
        except Exception as e:
            pass  # Fall through to CSV

    # Fallback to CSV
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

    # Count contacts (any result starting with "Contact")
    contacts_count = 0
    appointments_count = 0
    if 'result' in va_calls.columns:
        contacts_count = len(va_calls[va_calls['result'].astype(str).str.startswith('Contact')])
        appointments_count = len(va_calls[va_calls['result'].astype(str).str.contains('Appointment', case=False, na=False)])

    stats = {
        "today": len(va_calls[va_calls.get('date', '') == today]) if 'date' in va_calls.columns else 0,
        "week": len(va_calls[va_calls.get('date', '') >= week_ago]) if 'date' in va_calls.columns else len(va_calls),
        "contacts": contacts_count,
        "appointments": appointments_count
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
        # Check if admin is logged in and needs to select a VA
        if st.session_state.get('admin_logged_in', False):
            st.markdown("### Admin Mode - Select VA to View")
            st.info(f"Logged in as admin: {st.session_state.get('admin_username', 'admin')}")

            # Get list of VAs from database
            va_list = []
            if DB_AUTH_AVAILABLE:
                try:
                    import psycopg2
                    DATABASE_URL = os.environ.get('DATABASE_URL', '')
                    if DATABASE_URL:
                        conn = psycopg2.connect(DATABASE_URL)
                        cursor = conn.cursor()
                        cursor.execute("SELECT username, full_name, role FROM users WHERE role IN ('va', 'va_ids', 'va_pas') AND status = 'active'")
                        va_list = cursor.fetchall()
                        conn.close()
                except Exception as e:
                    st.error(f"Error loading VAs: {e}")

            if va_list:
                va_options = {f"{row[1]} (@{row[0]}) - {row[2]}": row for row in va_list}
                selected = st.selectbox("Select VA to view as:", list(va_options.keys()))

                if st.button("View as this VA", type="primary", use_container_width=True):
                    va_data = va_options[selected]
                    st.session_state.va_logged_in = True
                    st.session_state.va_name = va_data[1]  # full_name
                    st.session_state.va_username = va_data[0]  # username
                    st.session_state.user_role = va_data[2]  # role
                    st.session_state.va_phone = ''
                    st.session_state.is_admin_viewing = True  # Flag to show admin is viewing
                    st.rerun()
            else:
                st.warning("No VAs found in the system.")

            st.markdown("---")
            if st.button("Logout", use_container_width=True):
                st.session_state.admin_logged_in = False
                st.session_state.admin_username = None
                st.rerun()

            return  # Don't show regular login form

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
                        user_role = user.get('role', 'va')

                        # If admin, allow impersonation
                        if user_role == 'admin':
                            st.session_state.admin_logged_in = True
                            st.session_state.admin_username = user.get('username', username)
                            st.success("Admin login successful. Select a VA to view as.")
                            st.rerun()
                        else:
                            st.session_state.va_logged_in = True
                            st.session_state.va_name = user.get('full_name', username)
                            st.session_state.va_username = user.get('username', username)  # Use DB username for correct case
                            st.session_state.va_phone = user.get('va_phone', '') or ''  # Store VA's phone for calling
                            st.session_state.session_id = session_id
                            st.session_state.user_role = user_role
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
        # Admin viewing banner
        if st.session_state.get('is_admin_viewing', False):
            st.markdown("""
                <div style="background: #1e3a5f; padding: 10px; border-radius: 5px; margin-bottom: 10px;">
                    <span style="color: #fbbf24;">👑 ADMIN VIEW</span>
                </div>
            """, unsafe_allow_html=True)
            if st.button("🔄 Switch VA", use_container_width=True):
                st.session_state.va_logged_in = False
                st.session_state.is_admin_viewing = False
                st.rerun()
            if st.button("🚪 Exit Admin Mode", use_container_width=True):
                st.session_state.va_logged_in = False
                st.session_state.admin_logged_in = False
                st.session_state.is_admin_viewing = False
                st.rerun()
            st.markdown("---")

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

        # Get user role to determine which pages to show
        user_role = st.session_state.get('user_role', 'va')

        # Define pages based on role
        if user_role == 'va_ids':
            # IDS (Investor Development Specialist) - Investor/Buyer focused + assigned leads
            nav_pages = ["📊 My Stats", "📋 My Leads", "📱 Dialer", "📞 Call Tracker", "🏢 Investor Leads", "📝 End of Day"]
            st.caption("🏷️ Role: Investor Development (IDS)")
        elif user_role == 'va_pas':
            # PAS (Property Acquisition Specialist) - Seller focused
            nav_pages = ["📊 My Stats", "📋 My Leads", "📱 Dialer", f"🔔 Callback Queue{callback_badge}", "📞 Call Tracker", f"📅 Appointments{appt_badge}", "📥 Inbound Leads", "📝 End of Day"]
            st.caption("🏷️ Role: Property Acquisition (PAS)")
        else:
            # Default 'va' role - show all pages (backwards compatible)
            nav_pages = ["📊 My Stats", "📋 My Leads", "📱 Dialer", f"🔔 Callback Queue{callback_badge}", "📞 Call Tracker", f"📅 Appointments{appt_badge}", "📥 Inbound Leads", "🏢 Investor Leads", "📝 End of Day"]

        page = st.radio(
            "Navigation",
            nav_pages,
            label_visibility="collapsed"
        )

        # RVM usage indicator
        rvm_usage = get_va_rvm_usage(va_name)
        st.markdown("---")
        st.caption(f"🎤 RVM Today: {rvm_usage}/{RVM_DAILY_LIMIT_PER_VA}")

        st.markdown("---")

        # Change Password section
        with st.expander("🔐 Change Password"):
            current_pwd = st.text_input("Current Password", type="password", key="current_pwd")
            new_pwd = st.text_input("New Password", type="password", key="new_pwd")
            confirm_pwd = st.text_input("Confirm New Password", type="password", key="confirm_pwd")

            if st.button("Update Password", use_container_width=True):
                if not current_pwd or not new_pwd or not confirm_pwd:
                    st.error("Please fill in all fields")
                elif new_pwd != confirm_pwd:
                    st.error("New passwords do not match")
                elif len(new_pwd) < 8:
                    st.error("Password must be at least 8 characters")
                else:
                    try:
                        if DB_AUTH_AVAILABLE:
                            db_auth = DatabaseAuth()
                            va_username = st.session_state.get('va_username', va_name)
                            success, msg = db_auth.change_password(va_username, current_pwd, new_pwd)
                            if success:
                                st.success("Password changed successfully!")
                            else:
                                st.error(msg)
                        else:
                            st.error("Database not available")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

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
    elif "Investor Leads" in page:
        show_investor_leads_page(va_name)
    elif "End of Day" in page:
        show_end_of_day_report(va_name, calls_df, stats)

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
            public_site_url = os.environ.get('PUBLIC_SITE_URL', 'https://va-public-production.up.railway.app')
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

    # Separate leads into New (never worked) vs Worked (has call_count > 0)
    if 'call_count' not in filtered.columns:
        filtered['call_count'] = 0
    filtered['call_count'] = pd.to_numeric(filtered['call_count'], errors='coerce').fillna(0).astype(int)
    new_leads = filtered[filtered['call_count'] == 0]
    worked_leads = filtered[filtered['call_count'] > 0]

    # Display counts
    st.markdown(f"**{len(filtered)}** total leads | 🆕 **{len(new_leads)}** new | 📋 **{len(worked_leads)}** worked")
    st.markdown("---")

    # Helper function to display a single lead
    def display_lead(lead, lead_idx, section):
        """Display a single lead card"""
        address = lead.get('address', lead.get('property_address', 'Unknown Address'))
        city = lead.get('city', '')
        owner = lead.get('owner_name', lead.get('owner', 'Unknown Owner'))
        call_count = int(lead.get('call_count', 0) or 0)

        # Get ALL phone numbers with their types
        all_phones = []
        seen_phones = set()

        phone_columns = [
            ('phone', 'phone_type'),
            ('phone_1', 'phone_1_type'),
            ('phone_2', 'phone_2_type'),
            ('phone_3', 'phone_3_type'),
            ('phone_4', 'phone_4_type'),
            ('phone_5', 'phone_5_type'),
            ('phone_6', 'phone_6_type'),
        ]

        def get_phone_priority(phone_type):
            if not phone_type:
                return 4
            phone_type_lower = str(phone_type).lower()
            if 'mobile' in phone_type_lower or 'wireless' in phone_type_lower or 'cell' in phone_type_lower:
                return 1
            elif 'land' in phone_type_lower:
                return 2
            elif 'voip' in phone_type_lower:
                return 3
            return 4

        for phone_col, type_col in phone_columns:
            phone_val = lead.get(phone_col, '')
            if phone_val and str(phone_val).strip() and str(phone_val).lower() not in ['nan', 'none', '']:
                clean_phone = str(phone_val).strip()
                if clean_phone and clean_phone not in seen_phones:
                    seen_phones.add(clean_phone)
                    phone_type = lead.get(type_col, '')
                    if not phone_type or str(phone_type).lower() in ['nan', 'none', '']:
                        phone_type = 'Unknown'
                    priority = get_phone_priority(phone_type)
                    all_phones.append((clean_phone, str(phone_type), priority))

        all_phones.sort(key=lambda x: x[2])

        # Show call count badge for worked leads
        call_badge = f" | 📞 {call_count} calls" if call_count > 0 else ""
        with st.expander(f"**{address}** - {owner} ({len(all_phones)} phones{call_badge})", expanded=False):
            col_info, col_score = st.columns([3, 1])
            with col_info:
                st.caption(f"Owner: {owner}")
                if city:
                    st.caption(f"City: {city}")
            with col_score:
                score = lead.get('motivation_score', lead.get('score', 0))
                if score and score >= 70:
                    st.markdown("🔥 **Hot Lead**")
                elif score and score >= 50:
                    st.markdown("🌡️ Warm Lead")
                else:
                    st.markdown("❄️ Cold Lead")

            if all_phones:
                st.markdown("**📞 Phone Numbers** *(sorted by quality)*:")
                calling_mode = st.session_state.get('calling_mode', 'phone')
                va_phone = st.session_state.get('va_phone', '')
                va_identity = st.session_state.get('va_username', 'va-user')
                public_site_url = os.environ.get('PUBLIC_SITE_URL', 'https://va-public-production.up.railway.app')

                for phone_idx, phone_data in enumerate(all_phones):
                    phone_num, phone_type, priority = phone_data

                    if priority == 1:
                        type_badge = "📱 Mobile"
                    elif priority == 2:
                        type_badge = "🏠 Landline"
                    elif priority == 3:
                        type_badge = "🌐 VOIP"
                    else:
                        type_badge = f"❓ {phone_type}"

                    phone_col1, phone_col2, phone_col3 = st.columns([3, 1, 1])

                    with phone_col1:
                        st.markdown(f"**{phone_idx + 1}.** {phone_num} *({type_badge})*")

                    with phone_col2:
                        if calling_mode == 'browser' and BROWSER_DIALER_AVAILABLE:
                            import urllib.parse
                            params = urllib.parse.urlencode({
                                'identity': va_identity,
                                'phone': phone_num,
                                'name': owner or '',
                                'address': address or ''
                            })
                            dialer_url = f"{public_site_url}/dialer?{params}"
                            st.link_button("📞 Call", dialer_url, use_container_width=True)
                        elif calling_mode == 'phone' and va_phone and TWILIO_AVAILABLE:
                            if st.button("📱 Call", key=f"phone_call_{section}_{lead_idx}_{phone_idx}", use_container_width=True):
                                with st.spinner("Calling..."):
                                    success, message, call_sid = initiate_two_leg_call(
                                        va_phone=va_phone,
                                        lead_phone=phone_num,
                                        lead_name=owner,
                                        lead_address=address
                                    )
                                    if success:
                                        st.success(f"📞 {message}")
                                    else:
                                        st.error(message)
                        else:
                            st.button("📞 Call", key=f"no_call_{section}_{lead_idx}_{phone_idx}", disabled=True, use_container_width=True)

                    with phone_col3:
                        if st.button("📝 Log", key=f"log_{section}_{lead_idx}_{phone_idx}", use_container_width=True):
                            st.session_state.last_called_lead = {
                                'address': address,
                                'phone': phone_num,
                                'owner_name': owner,
                                'lead_id': lead.get('id', None),
                                'called_at': datetime.now().isoformat()
                            }
                            st.session_state.va_page = "📞 Call Tracker"
                            st.rerun()
            else:
                st.warning("No phone numbers available for this lead")

    # Display NEW LEADS section (never worked on)
    if not new_leads.empty:
        st.markdown("""
            <div style="background: #10b981; padding: 10px 15px; border-radius: 5px; margin: 10px 0;">
                <strong style="color: white;">🆕 NEW LEADS</strong>
                <span style="color: white; opacity: 0.9;"> - Never contacted yet</span>
            </div>
        """, unsafe_allow_html=True)
        for idx, lead in new_leads.head(50).iterrows():
            display_lead(lead, idx, 'new')
    else:
        st.info("No new leads - all leads have been worked on!")

    # Display WORKED LEADS section (already contacted)
    if not worked_leads.empty:
        st.markdown("""
            <div style="background: #6b7280; padding: 10px 15px; border-radius: 5px; margin: 20px 0 10px 0;">
                <strong style="color: white;">📋 WORKED LEADS</strong>
                <span style="color: white; opacity: 0.9;"> - Already contacted</span>
            </div>
        """, unsafe_allow_html=True)
        for idx, lead in worked_leads.head(50).iterrows():
            display_lead(lead, idx, 'worked')

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

            # Also update call_count in lead_assignments table
            lead_id = st.session_state.get('last_called_lead', {}).get('lead_id')
            if lead_id and LEAD_ASSIGNMENTS_AVAILABLE:
                try:
                    log_call(lead_id, result, notes, callback)
                except Exception as e:
                    pass  # Don't fail if this update fails

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

def show_end_of_day_report(va_name, calls_df, stats):
    """End of Day Report - auto-fills stats, VA adds insights"""
    st.markdown("## 📝 End of Day Report")
    st.markdown("Submit your daily summary before signing off.")

    today = datetime.now().strftime('%Y-%m-%d')
    today_display = datetime.now().strftime('%A, %B %d, %Y')

    # Check if report already submitted today
    reports_df = load_reports()
    already_submitted = False
    if not reports_df.empty and 'date' in reports_df.columns and 'va_name' in reports_df.columns:
        today_report = reports_df[(reports_df['date'] == today) & (reports_df['va_name'] == va_name)]
        if not today_report.empty:
            already_submitted = True

    if already_submitted:
        st.success("✅ You've already submitted your report for today!")
        st.markdown("---")
        st.markdown("### Your Submitted Report")
        report = today_report.iloc[-1]
        st.markdown(f"**Date:** {report.get('date', '')}")
        st.markdown(f"**Calls Made:** {report.get('total_calls', 0)}")
        st.markdown(f"**Appointments Set:** {report.get('appointments', 0)}")
        st.markdown(f"**Hot Leads:** {report.get('hot_leads', 'None')}")
        st.markdown(f"**Challenges:** {report.get('challenges', 'None')}")
        st.markdown(f"**Tomorrow's Plan:** {report.get('tomorrow_plan', 'None')}")
        return

    st.markdown(f"### 📅 {today_display}")

    # Auto-calculated stats section
    st.markdown("---")
    st.markdown("### 📊 Today's Stats (Auto-calculated)")

    today_stats = get_today_stats(va_name, calls_df)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Calls", today_stats['total_calls'])
    with col2:
        st.metric("Contacts", today_stats['contacts'])
    with col3:
        st.metric("Appointments", today_stats['appointments'])
    with col4:
        st.metric("Interested", today_stats['interested'])

    # Breakdown
    with st.expander("📈 Detailed Breakdown"):
        st.markdown(f"""
        | Result | Count |
        |--------|-------|
        | No Answer | {today_stats['no_answer']} |
        | Voicemail Left | {today_stats['voicemails']} |
        | Not Interested | {today_stats['not_interested']} |
        | Interested | {today_stats['interested']} |
        | Appointments Set | {today_stats['appointments']} |
        """)

    # VA Input section - simple but informative
    st.markdown("---")
    st.markdown("### 📋 Your Input")

    # Hot leads - most important info
    hot_leads = st.text_area(
        "🔥 Hot Leads Today",
        placeholder="List any promising leads (address, owner name, why they're hot)\n\nExample:\n- 123 Main St - John Smith - ready to sell, inherited property\n- 456 Oak Ave - Mary Johnson - behind on taxes, motivated",
        height=100
    )

    # Challenges faced
    challenges = st.text_area(
        "⚠️ Challenges or Issues",
        placeholder="Any problems encountered? (wrong numbers, difficult conversations, system issues)\n\nExample:\n- Many disconnected numbers in the 43215 zip\n- Dialer was slow around 2pm",
        height=80
    )

    # Quick wins
    wins = st.text_area(
        "🎉 Wins & Highlights",
        placeholder="Any victories worth mentioning?\n\nExample:\n- Set appointment with motivated seller\n- Got referral from homeowner",
        height=80
    )

    # Tomorrow's plan
    tomorrow_plan = st.text_area(
        "📅 Plan for Tomorrow",
        placeholder="What will you focus on tomorrow?\n\nExample:\n- Follow up with interested leads from today\n- Work through callback queue\n- Focus on high-score leads",
        height=80
    )

    # Overall rating
    st.markdown("---")
    st.markdown("### How was your day?")
    day_rating = st.select_slider(
        "Rate your productivity",
        options=["😫 Tough", "😐 Okay", "🙂 Good", "😊 Great", "🔥 Excellent"],
        value="🙂 Good"
    )

    # Submit button
    st.markdown("---")
    if st.button("📤 Submit End of Day Report", type="primary", use_container_width=True):
        if today_stats['total_calls'] == 0 and not hot_leads:
            st.warning("Please log at least one call or add some notes before submitting.")
        else:
            report_data = {
                'date': today,
                'va_name': va_name,
                'submitted_at': datetime.now().isoformat(),
                'total_calls': today_stats['total_calls'],
                'contacts': today_stats['contacts'],
                'appointments': today_stats['appointments'],
                'interested': today_stats['interested'],
                'not_interested': today_stats['not_interested'],
                'no_answer': today_stats['no_answer'],
                'voicemails': today_stats['voicemails'],
                'hot_leads': hot_leads,
                'challenges': challenges,
                'wins': wins,
                'tomorrow_plan': tomorrow_plan,
                'day_rating': day_rating
            }

            save_daily_report(report_data)
            st.success("✅ End of Day Report submitted successfully!")
            st.balloons()
            st.info("Great work today! See you tomorrow. 👋")
            st.rerun()

    # Previous reports
    st.markdown("---")
    with st.expander("📜 Your Previous Reports"):
        if not reports_df.empty and 'va_name' in reports_df.columns:
            va_reports = reports_df[reports_df['va_name'] == va_name].tail(7).iloc[::-1]
            if not va_reports.empty:
                for _, report in va_reports.iterrows():
                    st.markdown(f"**{report.get('date', 'Unknown')}** - {report.get('day_rating', '')} - {report.get('total_calls', 0)} calls, {report.get('appointments', 0)} appts")
            else:
                st.caption("No previous reports yet.")
        else:
            st.caption("No previous reports yet.")

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
    st.markdown("Scheduled follow-ups and RVM callbacks.")

    # Get RVM callbacks
    all_callbacks = load_callback_queue(va_name)
    ready_callbacks = get_ready_callbacks(va_name)

    # Get scheduled callbacks from call logs
    calls_df = load_calls()
    scheduled_callbacks = pd.DataFrame()
    today = datetime.now().strftime('%Y-%m-%d')

    if not calls_df.empty and 'callback_date' in calls_df.columns and 'va_name' in calls_df.columns:
        # Filter to this VA's callbacks that are due today or earlier
        va_calls = calls_df[calls_df['va_name'] == va_name]
        if not va_calls.empty:
            scheduled_callbacks = va_calls[
                (va_calls['callback_date'].notna()) &
                (va_calls['callback_date'] != '') &
                (va_calls['callback_date'] <= today)
            ].copy()

    # Stats
    total_ready = len(ready_callbacks) + len(scheduled_callbacks)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Scheduled Callbacks", len(scheduled_callbacks))
    with col2:
        st.metric("RVM Ready", len(ready_callbacks), delta="🔥" if len(ready_callbacks) > 0 else None)
    with col3:
        st.metric("Total to Call", total_ready, delta="⚡" if total_ready > 0 else None)

    st.markdown("---")

    # Scheduled callbacks from Call Tracker (callback dates)
    if not scheduled_callbacks.empty:
        st.success(f"📅 **{len(scheduled_callbacks)} scheduled callbacks due!**")

        for idx, cb in scheduled_callbacks.iterrows():
            with st.container():
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    address = cb.get('address', 'Unknown Address')
                    phone = cb.get('phone', 'No phone')
                    owner = cb.get('owner_name', '')
                    last_result = cb.get('result', '')
                    notes = cb.get('notes', '')

                    st.markdown(f"### 🏠 {address}")
                    if owner:
                        st.markdown(f"**Owner:** {owner}")
                    st.markdown(f"**Phone:** `{phone}`")
                    if last_result:
                        st.caption(f"Last result: {last_result}")
                    if notes:
                        st.caption(f"Notes: {notes[:100]}...")

                with col2:
                    cb_date = cb.get('callback_date', '')
                    if cb_date == today:
                        st.markdown("📅 **TODAY**")
                    else:
                        st.markdown(f"📅 {cb_date}")

                with col3:
                    # Open browser dialer
                    va_identity = st.session_state.get('va_username', 'va-user')
                    public_site_url = os.environ.get('PUBLIC_SITE_URL', 'https://va-public-production.up.railway.app')
                    import urllib.parse
                    params = urllib.parse.urlencode({
                        'identity': va_identity,
                        'phone': phone,
                        'name': owner or '',
                        'address': address or ''
                    })
                    dialer_url = f"{public_site_url}/dialer?{params}"
                    st.link_button("📞 Call", dialer_url, use_container_width=True)

                    if st.button("📝 Log", key=f"log_cb_{idx}", use_container_width=True):
                        st.session_state.last_called_lead = {
                            'address': address,
                            'phone': phone,
                            'owner_name': owner,
                            'called_at': datetime.now().isoformat()
                        }
                        st.session_state.va_page = "📞 Call Tracker"
                        st.rerun()

                st.markdown("---")

        st.markdown("")

    # RVM Ready callbacks section
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

    if all_callbacks.empty and scheduled_callbacks.empty:
        st.info("No callbacks scheduled. Set callback dates in Call Tracker or use RVM in Dialer!")
        st.markdown("""
        **Two ways to add callbacks:**

        **1. From Call Tracker:**
        - Log a call and set a callback date
        - Lead appears here on that date

        **2. From Dialer (RVM):**
        - Click **"🎤 Drop RVM & Queue"** on a lead
        - Lead gets voicemail dropped
        - After 30 minutes, they appear here ready for callback
        """)

def show_inbound_page(inbound_df, va_name):
    st.markdown("## 📥 Inbound Leads")
    st.markdown("People who submitted their information through our website.")

    if inbound_df.empty:
        st.info("No inbound leads yet. These will appear when homeowners submit forms on the website.")
        st.markdown("""
        **Inbound leads come from:**
        - Get Offer form on the website
        - Property pages
        - Landing pages (sell-my-house-fast, etc.)
        """)
        return

    # Priority badge
    st.warning("⚡ **These are HOT leads!** They came to us. Call them FIRST!")

    # Stats
    total = len(inbound_df)
    new_count = len(inbound_df[inbound_df.get('status', 'new') == 'new']) if 'status' in inbound_df.columns else total
    st.markdown(f"**{new_count} new** out of {total} total inbound leads")

    st.markdown("---")

    for idx, lead in inbound_df.head(50).iterrows():
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])

            address = lead.get('address', lead.get('property_address', 'Unknown Address'))
            name = lead.get('name', 'N/A')
            phone = lead.get('phone', '')
            email = lead.get('email', '')
            message = lead.get('message', '')

            with col1:
                st.markdown(f"### 🏠 {address}")
                st.markdown(f"**Name:** {name}")
                if phone:
                    st.markdown(f"**Phone:** `{phone}`")
                if email:
                    st.caption(f"📧 {email}")
                if message:
                    st.info(f"💬 \"{message}\"")

            with col2:
                submitted = lead.get('captured_at', lead.get('submitted_at', lead.get('date', '')))
                if submitted:
                    st.caption(f"📅 {str(submitted)[:16]}")

                status = lead.get('status', 'new')
                if status == 'new':
                    st.markdown("🆕 **NEW**")
                elif status == 'contacted':
                    st.markdown("✅ Contacted")
                elif status == 'scheduled':
                    st.markdown("📅 Scheduled")
                else:
                    st.caption(status)

            with col3:
                if phone:
                    # Browser dialer
                    va_identity = st.session_state.get('va_username', 'va-user')
                    public_site_url = os.environ.get('PUBLIC_SITE_URL', 'https://va-public-production.up.railway.app')
                    import urllib.parse
                    params = urllib.parse.urlencode({
                        'identity': va_identity,
                        'phone': phone,
                        'name': name or '',
                        'address': address or ''
                    })
                    dialer_url = f"{public_site_url}/dialer?{params}"
                    st.link_button("📞 Call", dialer_url, use_container_width=True)

                    if st.button("📝 Log", key=f"inbound_log_{idx}", use_container_width=True):
                        st.session_state.last_called_lead = {
                            'address': address,
                            'phone': phone,
                            'owner_name': name,
                            'called_at': datetime.now().isoformat()
                        }
                        st.session_state.va_page = "📞 Call Tracker"
                        st.rerun()
                else:
                    st.caption("No phone")

            st.markdown("---")


def show_add_buyer_form(va_name, prefill: dict = None):
    """Form for VAs to add qualified buyers"""
    st.markdown("### ➕ Add Qualified Buyer")
    st.info("When an investor says they're interested, capture their buying criteria here.")

    if not QUALIFIED_BUYERS_AVAILABLE:
        st.error("Qualified buyers module not available. Please contact admin.")
        return

    with st.form("add_buyer_form", clear_on_submit=True):
        st.markdown("**Contact Information**")
        col1, col2 = st.columns(2)

        with col1:
            buyer_name = st.text_input("Name *", value=prefill.get('name', '') if prefill else '')
            buyer_phone = st.text_input("Phone *", value=prefill.get('phone', '') if prefill else '')
            buyer_email = st.text_input("Email", value=prefill.get('email', '') if prefill else '')

        with col2:
            buyer_company = st.text_input("Company/LLC", value=prefill.get('company', '') if prefill else '')
            buyer_phone_2 = st.text_input("Phone 2")
            buyer_address = st.text_input("Address", value=prefill.get('address', '') if prefill else '')

        st.markdown("---")
        st.markdown("**Buying Criteria**")

        col1, col2, col3 = st.columns(3)

        with col1:
            price_min = st.number_input("Min Budget ($)", min_value=0, value=0, step=10000)
            price_max = st.number_input("Max Budget ($)", min_value=0, value=150000, step=10000)

        with col2:
            prop_types = st.multiselect(
                "Property Types",
                options=PROPERTY_TYPES,
                default=['SFR']
            )
            condition = st.selectbox("Condition Preference", options=CONDITION_PREFS)

        with col3:
            areas = st.text_input("Areas/Zip Codes", placeholder="43215, 43201, Franklinton")
            interest = st.selectbox(
                "Interest Level",
                options=INTEREST_LEVELS,
                format_func=lambda x: INTEREST_DISPLAY.get(x, x)
            )

        st.markdown("---")
        col1, col2 = st.columns(2)

        with col1:
            cash_buyer = st.checkbox("Cash Buyer", value=True)

        with col2:
            financing = st.text_input("Financing Type (if not cash)", placeholder="Hard money, Conventional")

        notes = st.text_area("Notes", placeholder="Any additional info about this buyer...")

        submitted = st.form_submit_button("✅ Add Buyer", type="primary", use_container_width=True)

        if submitted:
            if not buyer_name or not buyer_phone:
                st.error("Name and Phone are required!")
            else:
                success, message, buyer_id = add_buyer(
                    name=buyer_name,
                    phone=buyer_phone,
                    created_by=va_name,
                    company=buyer_company,
                    phone_2=buyer_phone_2,
                    email=buyer_email,
                    address=buyer_address,
                    price_min=price_min,
                    price_max=price_max,
                    property_types=prop_types,
                    areas=areas,
                    condition_pref=condition,
                    cash_buyer=cash_buyer,
                    financing_type=financing if not cash_buyer else '',
                    interest_level=interest,
                    notes=notes
                )

                if success:
                    st.success(f"✅ {message}")
                    st.balloons()
                else:
                    st.error(f"❌ {message}")


def show_my_added_buyers(va_name):
    """Show buyers added by this VA"""
    st.markdown("### 👥 Buyers I've Added")

    if not QUALIFIED_BUYERS_AVAILABLE:
        st.error("Qualified buyers module not available.")
        return

    buyers_df = get_buyers_df()

    if len(buyers_df) == 0:
        st.info("No buyers added yet. When you find an interested investor, add them using the form!")
        return

    # Filter to this VA's buyers
    my_buyers = buyers_df[buyers_df['created_by'] == va_name] if 'created_by' in buyers_df.columns else buyers_df

    if len(my_buyers) == 0:
        st.info("You haven't added any buyers yet. Start adding interested investors!")
        return

    # Stats
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("My Total Buyers", len(my_buyers))
    with col2:
        hot_count = len(my_buyers[my_buyers['interest_level'] == 'hot']) if 'interest_level' in my_buyers.columns else 0
        st.metric("🔥 Hot Buyers", hot_count)
    with col3:
        today = datetime.now().strftime('%Y-%m-%d')
        today_count = len(my_buyers[my_buyers['created_at'].str.startswith(today)]) if 'created_at' in my_buyers.columns else 0
        st.metric("Added Today", today_count)

    st.markdown("---")

    # Display buyers
    for _, buyer in my_buyers.iterrows():
        interest_icon = {'hot': '🔥', 'warm': '👍', 'cold': '❄️'}.get(buyer.get('interest_level', ''), '❓')

        with st.expander(f"{interest_icon} **{buyer['name']}** — ${buyer.get('price_min', 0):,.0f} - ${buyer.get('price_max', 0):,.0f}"):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"**Phone:** {buyer.get('phone', 'N/A')}")
                st.markdown(f"**Email:** {buyer.get('email', 'N/A')}")
                st.markdown(f"**Company:** {buyer.get('company', 'N/A')}")

            with col2:
                st.markdown(f"**Property Types:** {buyer.get('property_types', 'Any')}")
                st.markdown(f"**Areas:** {buyer.get('areas', 'Any')}")
                st.markdown(f"**Condition:** {buyer.get('condition_pref', 'Any')}")
                st.markdown(f"**Cash Buyer:** {'Yes' if buyer.get('cash_buyer') else 'No'}")

            if buyer.get('notes'):
                st.markdown(f"**Notes:** {buyer['notes']}")

            st.caption(f"Added: {buyer.get('created_at', 'Unknown')[:10]}")


def show_investor_leads_page(va_name):
    """Show investor/buyer leads for IDS team"""
    st.markdown("## 🏢 Investor Leads")

    # Tabs for browsing vs adding buyers
    inv_tab1, inv_tab2, inv_tab3 = st.tabs(["📋 Browse Investors", "➕ Add Qualified Buyer", "👥 My Added Buyers"])

    with inv_tab2:
        show_add_buyer_form(va_name)

    with inv_tab3:
        show_my_added_buyers(va_name)

    with inv_tab1:
        st.markdown("Find and contact active real estate investors in your market.")

    # County and tier selection
    col1, col2, col3 = st.columns([2, 2, 2])

    with col1:
        county = st.selectbox(
            "Market",
            ["franklin", "hamilton"],
            format_func=lambda x: "Columbus (Franklin Co.)" if x == "franklin" else "Cincinnati (Hamilton Co.)"
        )

    with col2:
        tier = st.selectbox(
            "Investor Tier",
            ["all", "tier_1", "tier_2", "tier_3"],
            format_func=lambda x: {
                "all": "All Tiers",
                "tier_1": "Tier 1 - High Confidence",
                "tier_2": "Tier 2 - Medium Confidence",
                "tier_3": "Tier 3 - Lower Confidence"
            }.get(x, x)
        )

    with col3:
        search = st.text_input("Search by name", placeholder="Enter investor name...")

    # Load investors
    tier_filter = None if tier == "all" else tier
    investors_df = load_investors(county=county, tier=tier_filter)

    if investors_df.empty:
        st.warning(f"No investor data found for {county}. Check that investor CSV files exist.")
        return

    # Apply search filter
    if search:
        investors_df = investors_df[investors_df['owner_name'].str.contains(search, case=False, na=False)]

    # Stats
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Investors", len(investors_df))
    with col2:
        tier1_count = len(investors_df[investors_df['tier'] == 'tier_1']) if 'tier' in investors_df.columns else 0
        st.metric("Tier 1 (Best)", tier1_count)
    with col3:
        avg_portfolio = investors_df['portfolio_size'].mean() if 'portfolio_size' in investors_df.columns else 0
        st.metric("Avg Portfolio Size", f"{avg_portfolio:.0f}")
    with col4:
        total_properties = investors_df['portfolio_size'].sum() if 'portfolio_size' in investors_df.columns else 0
        st.metric("Total Properties", f"{total_properties:,.0f}")

    st.markdown("---")

    # Display investors
    st.markdown(f"### Showing {len(investors_df)} investors")

    # Pagination
    page_size = 20
    if 'investor_page' not in st.session_state:
        st.session_state.investor_page = 0

    total_pages = (len(investors_df) - 1) // page_size + 1
    start_idx = st.session_state.investor_page * page_size
    end_idx = start_idx + page_size

    # Page navigation
    nav_col1, nav_col2, nav_col3 = st.columns([1, 3, 1])
    with nav_col1:
        if st.button("← Previous", disabled=st.session_state.investor_page == 0):
            st.session_state.investor_page -= 1
            st.rerun()
    with nav_col2:
        st.markdown(f"<center>Page {st.session_state.investor_page + 1} of {total_pages}</center>", unsafe_allow_html=True)
    with nav_col3:
        if st.button("Next →", disabled=st.session_state.investor_page >= total_pages - 1):
            st.session_state.investor_page += 1
            st.rerun()

    # Display investor cards
    for idx, investor in investors_df.iloc[start_idx:end_idx].iterrows():
        tier_color = {"tier_1": "🟢", "tier_2": "🟡", "tier_3": "🟠"}.get(investor.get('tier', ''), "⚪")
        portfolio_size = investor.get('portfolio_size', 0)
        investor_score = investor.get('investor_score', 0)

        with st.expander(f"{tier_color} **{investor['owner_name']}** — {portfolio_size} properties (Score: {investor_score})"):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"**Entity Type:** {investor.get('entity_type', 'Unknown').upper()}")
                st.markdown(f"**Portfolio Size:** {portfolio_size} properties")
                st.markdown(f"**Investor Score:** {investor_score}/100")
                st.markdown(f"**Tier:** {investor.get('tier', 'Unknown').replace('_', ' ').title()}")

            with col2:
                st.markdown(f"**Address:** {investor.get('owner_address', 'N/A')}")
                st.markdown(f"**Mailing:** {investor.get('mailing_address', 'N/A')}")
                if investor.get('total_market_value'):
                    st.markdown(f"**Total Value:** ${investor.get('total_market_value', 0):,.0f}")

            # Sample properties
            if investor.get('sample_properties'):
                st.markdown("**Sample Properties:**")
                try:
                    props = eval(investor['sample_properties']) if isinstance(investor['sample_properties'], str) else investor['sample_properties']
                    for prop in props[:3]:
                        st.caption(f"  • {prop}")
                except:
                    st.caption(str(investor['sample_properties'])[:100])

            # Score reasons
            if investor.get('score_reasons'):
                st.markdown("**Why High Score:**")
                st.caption(investor['score_reasons'][:200])

            # Action buttons
            btn_col1, btn_col2, btn_col3 = st.columns(3)
            with btn_col1:
                st.button("📋 Copy Info", key=f"copy_{idx}", help="Copy investor details")
            with btn_col2:
                st.button("✅ Mark Contacted", key=f"contacted_{idx}")
            with btn_col3:
                st.button("⭐ Add to Buyers", key=f"add_buyer_{idx}")

# Main app
def main():
    if not st.session_state.va_logged_in:
        show_login()
    else:
        show_dashboard()

if __name__ == "__main__":
    main()
# VA Portal trigger rebuild
