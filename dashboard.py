#!/usr/bin/env python3
"""
Aerial Leads - Dashboard
Beautiful web interface for lead generation
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import time
from datetime import datetime
import os
import hashlib

# Import our modules - Sellers
from sellers.scrapers.franklin_county_excel import FranklinCountyExcelLoader
from sellers.scrapers.columbus_violations_api import ColumbusViolationsAPI
from sellers.scoring.motivation_scorer import MotivationScorer
from sellers.scrapers.factory import ScraperFactory
from sellers.skip_tracing.skip_tracer import SkipTracer
from sellers.scrapers.probate_scraper import ProbateScraper
from sellers.scrapers.sheriff_sale_scraper import SheriffSaleScraper
from sellers.tracking.call_tracker import CallTracker
from sellers.tracking.va_manager import VAManager
from sellers.lead_generation.dnc_scrubber import DNCChecker

# Import our modules - Shared
from shared.config.settings import RAW_DATA_DIR, PROCESSED_DATA_DIR, BATCHDATA_API_KEY, DATA_DIR
from shared.config.market_loader import load_market
from shared.data_processing.portfolio_detector import PortfolioDetector
from shared.data_processing.equity_calculator import EquityCalculator
from shared.data_processing.comps_estimator import CompsEstimator
from shared.data_processing.freshness_tracker import FreshnessTracker
from shared.data_processing.lead_integrator import LeadIntegrator
from shared.data_processing.probate_matcher import ProbateMatcher
from shared.utils.street_view import StreetViewHelper
from shared.utils.data_archiver import DataArchiver, archive_before_scrape

# Page config
st.set_page_config(
    page_title="Aerial Leads - Lead Generation Dashboard",
    page_icon="🏠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        margin-bottom: 1rem;
    }
    .stButton>button {
        width: 100%;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-weight: bold;
        border: none;
        padding: 0.75rem;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ========================================
# AUTHENTICATION SYSTEM
# ========================================
# Initialize session state for auth
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
if 'user_type' not in st.session_state:
    st.session_state.user_type = None  # 'admin' or 'va'
if 'user_id' not in st.session_state:
    st.session_state.user_id = None
if 'user_name' not in st.session_state:
    st.session_state.user_name = None

# Admin credentials (you can change these)
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"

def check_va_login(username, password):
    """Check if VA credentials are valid"""
    va_mgr = VAManager()
    vas_df = va_mgr.get_all_vas()
    if vas_df.empty:
        return None

    # Hash the entered password
    password_hash = hashlib.sha256(password.encode()).hexdigest()

    # Check if username matches any VA (case-insensitive)
    for _, va in vas_df.iterrows():
        va_username = va.get('username', '').lower()
        stored_hash = va.get('password_hash', '')
        if va_username == username.lower() and stored_hash == password_hash:
            return {'user_id': va['user_id'], 'name': va['name'], 'type': 'va'}
    return None

def show_login_page():
    """Display login page"""
    st.markdown("# 🏠 Aerial Leads")
    st.markdown("### Login to Continue")

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        login_type = st.radio("Login As", ["Admin", "VA (Virtual Assistant)"], horizontal=True)

        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("🔐 Login", type="primary", use_container_width=True):
            if login_type == "Admin":
                if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
                    st.session_state.logged_in = True
                    st.session_state.user_type = 'admin'
                    st.session_state.user_name = 'Admin'
                    st.rerun()
                else:
                    st.error("Invalid admin credentials")
            else:
                va_info = check_va_login(username, password)
                if va_info:
                    st.session_state.logged_in = True
                    st.session_state.user_type = 'va'
                    st.session_state.user_id = va_info['user_id']
                    st.session_state.user_name = va_info['name']
                    st.rerun()
                else:
                    st.error("Invalid VA credentials. Check with your admin.")

        st.markdown("---")
        st.caption("**Admin:** Full access to all features")
        st.caption("**VA:** Access to Dialer and assigned leads only")

# Show login page if not logged in
if not st.session_state.logged_in:
    show_login_page()
    st.stop()

# ========================================
# VA DASHBOARD (Simplified for VAs)
# ========================================
if st.session_state.user_type == 'va':
    # Simplified sidebar for VAs
    with st.sidebar:
        st.markdown(f"# 📞 VA Portal")
        st.markdown(f"**Welcome, {st.session_state.user_name}!**")
        st.markdown("---")

        va_page = st.radio(
            "Navigation",
            ["📋 My Leads", "📱 Dialer", "📞 My Calls", "📊 My Stats"],
            label_visibility="collapsed"
        )

        st.markdown("---")

        # Quick stats in sidebar
        va_mgr = VAManager()
        my_leads = va_mgr.get_va_assignments(st.session_state.user_id)
        pending_leads = len(my_leads[my_leads['status'] == 'pending']) if not my_leads.empty else 0
        st.metric("📋 Pending Leads", pending_leads)

        st.markdown("---")
        if st.button("🚪 Logout"):
            st.session_state.logged_in = False
            st.session_state.user_type = None
            st.session_state.user_id = None
            st.session_state.user_name = None
            st.rerun()

    # ========== MY LEADS PAGE ==========
    if va_page == "📋 My Leads":
        st.markdown(f'<h1 class="main-header">📋 My Assigned Leads</h1>', unsafe_allow_html=True)
        st.info(f"👋 Welcome {st.session_state.user_name}! Here are the leads assigned to you.")

        va_mgr = VAManager()
        my_leads = va_mgr.get_va_assignments(st.session_state.user_id)

        if my_leads.empty:
            st.warning("🚫 No leads assigned to you yet. Ask your admin to assign leads.")
        else:
            # Filter tabs
            tab1, tab2, tab3 = st.tabs(["📋 Pending", "🔄 In Progress", "✅ Completed"])

            with tab1:
                pending = my_leads[my_leads['status'] == 'pending']
                if pending.empty:
                    st.info("No pending leads")
                else:
                    st.success(f"You have **{len(pending)}** leads to call!")
                    for idx, lead in pending.iterrows():
                        with st.expander(f"🏠 {lead['address']} - {lead['owner_name']}", expanded=False):
                            col1, col2, col3 = st.columns([2, 2, 1])
                            with col1:
                                st.markdown(f"**👤 Owner:** {lead['owner_name']}")
                                st.markdown(f"**🏠 Address:** {lead['address']}")
                                st.markdown(f"**⭐ Score:** {lead.get('motivation_score', 'N/A')}")
                            with col2:
                                phone = lead.get('phone', 'No phone')
                                st.markdown(f"**📞 Phone:** `{phone}`")
                                st.markdown(f"**📅 Assigned:** {str(lead.get('assigned_date', ''))[:10]}")
                                st.markdown(f"**🎯 Priority:** {lead.get('priority', 'Normal')}")
                            with col3:
                                if st.button("📱 Call", key=f"call_{lead['assignment_id']}"):
                                    st.session_state.selected_lead = lead.to_dict()
                                    st.session_state.va_page_redirect = "📱 Dialer"
                                    st.rerun()

            with tab2:
                in_progress = my_leads[my_leads['status'] == 'in_progress']
                if in_progress.empty:
                    st.info("No leads in progress")
                else:
                    for idx, lead in in_progress.iterrows():
                        with st.expander(f"🔄 {lead['address']} - {lead['owner_name']}"):
                            st.markdown(f"**📞 Phone:** `{lead.get('phone', 'N/A')}`")
                            st.markdown(f"**📝 Notes:** {lead.get('notes', 'None')}")

            with tab3:
                completed = my_leads[my_leads['status'] == 'completed']
                if completed.empty:
                    st.info("No completed leads yet")
                else:
                    st.dataframe(completed[['address', 'owner_name', 'phone', 'notes']],
                                use_container_width=True, hide_index=True)

    # ========== DIALER PAGE ==========
    elif va_page == "📱 Dialer":
        st.markdown(f'<h1 class="main-header">📱 Cold Calling Dialer</h1>', unsafe_allow_html=True)

        # Initialize Twilio
        twilio_connected = False
        twilio = None
        selected_number = None

        try:
            from sellers.dialer.twilio_client import TwilioClient
            twilio = TwilioClient()
            phone_numbers = twilio.get_phone_numbers()
            valid_numbers = [n for n in phone_numbers if 'error' not in n]
            twilio_connected = len(valid_numbers) > 0
            if valid_numbers:
                selected_number = valid_numbers[0]['phone_number']
        except Exception as e:
            twilio_connected = False

        va_mgr = VAManager()

        # Get assigned leads
        pending_leads = va_mgr.get_va_assignments(st.session_state.user_id, status='pending')
        in_progress_leads = va_mgr.get_va_assignments(st.session_state.user_id, status='in_progress')
        my_leads = pd.concat([in_progress_leads, pending_leads], ignore_index=True) if not pending_leads.empty or not in_progress_leads.empty else pd.DataFrame()

        # Show connection status
        if twilio_connected:
            st.success(f"✅ Twilio Connected | Caller ID: `{selected_number}`")
        else:
            st.warning("⚠️ Twilio not connected - Manual dialing mode")

        st.markdown("---")

        # YOUR PHONE NUMBER (required for Twilio)
        st.markdown("### 📱 Your Phone Number")
        if 'va_phone' not in st.session_state:
            st.session_state.va_phone = ""

        va_phone = st.text_input(
            "Enter your phone number (Twilio will call YOU, then connect you)",
            value=st.session_state.va_phone,
            placeholder="+1234567890"
        )
        st.session_state.va_phone = va_phone

        st.markdown("---")

        # CALL MODE SELECTION
        call_mode = st.radio(
            "Call Mode",
            ["📋 Call Assigned Leads", "📞 Quick Call (Enter Any Number)"],
            horizontal=True
        )

        st.markdown("---")

        if call_mode == "📞 Quick Call (Enter Any Number)":
            # QUICK CALL MODE - Enter any number
            st.markdown("### 📞 Quick Call")

            col1, col2 = st.columns([1, 1])

            with col1:
                target_phone = st.text_input(
                    "Number to Call",
                    placeholder="+16145551234",
                    help="Enter any phone number"
                )

                if twilio_connected and va_phone and target_phone:
                    if st.button("📞 CALL NOW", type="primary", use_container_width=True):
                        try:
                            result = twilio.make_call(
                                to_number=va_phone,
                                from_number=selected_number,
                                twiml=f'''<Response>
                                    <Say>Connecting your call.</Say>
                                    <Dial callerId="{selected_number}" record="record-from-answer">
                                        <Number>{target_phone}</Number>
                                    </Dial>
                                </Response>''',
                                record=True
                            )
                            if result.get('success'):
                                st.success(f"📞 Calling your phone... Answer to connect!")
                            else:
                                st.error(f"Call failed: {result.get('error')}")
                        except Exception as e:
                            st.error(f"Error: {e}")
                elif not twilio_connected:
                    st.info(f"📞 Dial manually: **{target_phone}**")
                elif not va_phone:
                    st.warning("⬆️ Enter your phone number above")

            with col2:
                st.markdown("### 📝 Log Call Result")
                outcome = st.selectbox("What happened?", [
                    "No Answer", "Left Voicemail", "Spoke - Not Interested",
                    "Spoke - Call Back Later", "Spoke - Interested",
                    "Appointment Set!", "Wrong Number", "Disconnected"
                ], key="quick_outcome")

                notes = st.text_area("Notes", placeholder="Quick notes...", key="quick_notes")

                if st.button("💾 Save Call Log", use_container_width=True):
                    tracker = CallTracker()
                    tracker.log_call(
                        address="Quick Call",
                        owner_name="Manual Entry",
                        phone=target_phone,
                        outcome=outcome,
                        notes=notes
                    )
                    st.success("✅ Call logged!")

        else:
            # ASSIGNED LEADS MODE
            if my_leads.empty:
                st.warning("🚫 No leads assigned. Ask your admin to assign leads to you.")
            else:
                st.success(f"📋 You have **{len(my_leads)}** leads to call!")

                col1, col2 = st.columns([1, 1])

                with col1:
                    st.markdown("### 📋 Select Lead")

                    # Lead selection
                    lead_options = {f"{row['address']} - {row['owner_name']}": row.to_dict()
                                  for _, row in my_leads.iterrows()}

                    selected_key = st.selectbox("Choose Lead", list(lead_options.keys()))
                    lead = lead_options[selected_key]

                    phone = str(lead.get('phone', '')).strip()

                    st.markdown("---")
                    st.markdown("### 👤 Lead Info")
                    st.markdown(f"**🏠 Address:** {lead.get('address', 'N/A')}")
                    st.markdown(f"**👤 Owner:** {lead.get('owner_name', 'N/A')}")
                    st.markdown(f"**⭐ Score:** {lead.get('motivation_score', 'N/A')}")

                    st.markdown("---")
                    st.markdown("### 📞 Phone Number")

                    if phone and phone != 'nan':
                        st.code(phone, language=None)

                        if twilio_connected and va_phone:
                            if st.button("📞 CALL NOW", type="primary", use_container_width=True):
                                try:
                                    result = twilio.make_call(
                                        to_number=va_phone,
                                        from_number=selected_number,
                                        twiml=f'''<Response>
                                            <Say>Connecting you to {lead.get('owner_name', 'the owner')}.</Say>
                                            <Dial callerId="{selected_number}" record="record-from-answer">
                                                <Number>{phone}</Number>
                                            </Dial>
                                        </Response>''',
                                        record=True
                                    )
                                    if result.get('success'):
                                        st.success(f"📞 Calling your phone... Answer to connect!")
                                        va_mgr.update_assignment_status(lead['assignment_id'], 'in_progress')
                                    else:
                                        st.error(f"Call failed: {result.get('error')}")
                                except Exception as e:
                                    st.error(f"Error: {e}")
                        elif not twilio_connected:
                            # Manual dial link
                            phone_clean = phone.replace('(', '').replace(')', '').replace('-', '').replace(' ', '')
                            st.markdown(f"[📱 Tap to Call]({f'tel:{phone_clean}'})")
                            st.caption("Or dial manually")
                        else:
                            st.warning("⬆️ Enter your phone number above")
                    else:
                        st.error("❌ No phone number!")
                        if st.button("⏭️ Skip Lead"):
                            va_mgr.update_assignment_status(lead['assignment_id'], 'completed', notes="No phone")
                            st.rerun()

                with col2:
                    st.markdown("### 📝 Log Call Result")

                    outcome = st.selectbox("What happened?", [
                        "No Answer", "Left Voicemail", "Spoke - Not Interested",
                        "Spoke - Call Back Later", "Spoke - Interested",
                        "Appointment Set!", "Wrong Number", "Disconnected"
                    ])

                    notes = st.text_area("Notes", placeholder="What happened on the call?")

                    callback_date = None
                    if "Call Back" in outcome:
                        callback_date = st.date_input("📅 Callback Date")

                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button("✅ Save & Next", type="primary", use_container_width=True):
                            tracker = CallTracker()
                            tracker.log_call(
                                address=lead.get('address', ''),
                                owner_name=lead.get('owner_name', ''),
                                phone=phone,
                                outcome=outcome,
                                notes=notes,
                                follow_up_date=str(callback_date) if callback_date else None
                            )

                            if outcome in ['Spoke - Not Interested', 'Wrong Number', 'Disconnected']:
                                new_status = 'completed'
                            elif outcome == 'Appointment Set!':
                                new_status = 'completed'
                                st.balloons()
                            else:
                                new_status = 'in_progress'

                            va_mgr.update_assignment_status(lead['assignment_id'], new_status, notes=f"{outcome}: {notes}")
                            st.success("✅ Logged!")
                            time.sleep(0.5)
                            st.rerun()

                    with col_b:
                        if st.button("⏭️ Skip", use_container_width=True):
                            st.rerun()

    # ========== MY CALLS PAGE ==========
    elif va_page == "📞 My Calls":
        st.markdown("### 📞 My Recent Calls")
        tracker = CallTracker()
        calls = tracker.get_all_calls(limit=100)

        if calls.empty:
            st.info("No calls logged yet. Start calling from the Dialer!")
        else:
            # Filter to show only relevant columns
            display_cols = ['call_date', 'call_time', 'address', 'owner_name', 'phone', 'outcome', 'notes']
            available_cols = [c for c in display_cols if c in calls.columns]
            st.dataframe(calls[available_cols], use_container_width=True, hide_index=True)

    # ========== MY STATS PAGE ==========
    elif va_page == "📊 My Stats":
        st.markdown("### 📊 My Performance")

        col1, col2 = st.columns([1, 1])

        with col1:
            st.markdown("#### Today's Progress")
            tracker = CallTracker()
            stats = tracker.get_todays_stats()

            c1, c2 = st.columns(2)
            with c1:
                st.metric("📞 Calls Made", stats['total_calls'])
                st.metric("💬 Conversations", stats['conversations'])
            with c2:
                st.metric("⭐ Interested", stats['interested'])
                st.metric("📅 Appointments", stats['appointments'])

        with col2:
            st.markdown("#### My Lead Progress")
            va_mgr = VAManager()
            my_leads = va_mgr.get_va_assignments(st.session_state.user_id)

            if not my_leads.empty:
                pending = len(my_leads[my_leads['status'] == 'pending'])
                in_progress = len(my_leads[my_leads['status'] == 'in_progress'])
                completed = len(my_leads[my_leads['status'] == 'completed'])

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("📋 Pending", pending)
                with c2:
                    st.metric("🔄 In Progress", in_progress)
                with c3:
                    st.metric("✅ Completed", completed)

                # Progress bar
                total = len(my_leads)
                completion_pct = (completed / total * 100) if total > 0 else 0
                st.progress(completion_pct / 100, text=f"Completion: {completion_pct:.0f}%")
            else:
                st.info("No leads assigned yet")

    st.stop()  # Stop here for VA users

# ========================================
# ADMIN DASHBOARD (Full Access)
# ========================================
# Sidebar for Admin
with st.sidebar:
    st.markdown("# 🏠 Aerial Leads")
    st.markdown(f"**Logged in as: {st.session_state.user_name}**")
    st.markdown("---")

    page = st.radio(
        "Navigation",
        ["🏠 Home", "🚀 Generate Leads", "⚖️ Probate & Foreclosure", "📞 Skip Trace", "🛡️ DNC Scrub", "☎️ Call Tracker", "👥 VA Management", "📱 Dialer", "🔍 Search Owner", "📊 View Leads", "🐋 Whale Owners", "💰 Investor Finder", "💵 Deal Analyzer", "📈 Statistics", "📋 Data Quality", "📁 Data History", "⚙️ Data Management"],
        label_visibility="collapsed"
    )

    st.markdown("---")
    if st.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.session_state.user_type = None
        st.rerun()

    st.markdown("---")
    st.markdown("### Quick Stats")

    # Check for existing data - try new format first
    leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
    if not leads_file.exists():
        leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

    if leads_file.exists():
        df_all = pd.read_csv(leads_file)
        st.metric("Total Leads", len(df_all))
        st.metric("Avg Score", f"{df_all['motivation_score'].mean():.1f}/100")

        # Whale owners stat
        if 'is_whale' in df_all.columns:
            whale_count = df_all[df_all['is_whale'] == True]['owner_name'].nunique()
            st.metric("🐋 Whale Owners", whale_count)

        revenue = (
            len(df_all[df_all['tier'] == 1]) * 100 +
            len(df_all[df_all['tier'] == 2]) * 75 +
            len(df_all[df_all['tier'] == 3]) * 50
        )
        st.metric("Potential Revenue", f"${revenue:,}")
    else:
        st.info("No leads generated yet")

    st.markdown("---")
    st.markdown("**Version:** 1.0.0")
    st.markdown("**Data Source:** Franklin County, OH")


# ========================================
# HOME PAGE
# ========================================
if page == "🏠 Home":
    st.markdown('<h1 class="main-header">🏠 Aerial Leads Dashboard</h1>', unsafe_allow_html=True)
    st.markdown("### Premium Real Estate Lead Generation Platform")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
        <div class="metric-card">
            <h3>📥 Real Data Sources</h3>
            <p>Franklin County tax records<br>Columbus code violations<br>Updated monthly</p>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
        <div class="metric-card">
            <h3>🎯 Smart Scoring</h3>
            <p>AI-powered motivation algorithm<br>0-100 distress score<br>Tiered pricing ready</p>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
        <div class="metric-card">
            <h3>💰 Revenue Potential</h3>
            <p>Tier 1: $100/lead<br>Tier 2: $75/lead<br>Tier 3: $50/lead</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("## 🚀 Getting Started")

    st.markdown("""
    1. **Generate Leads**: Use the "Generate Leads" page to create your first batch
    2. **View Results**: Check "View Leads" to see your generated leads
    3. **Export Data**: Download CSV files ready for CRM import
    4. **Track Stats**: Monitor performance on the Statistics page
    """)

    st.markdown("---")
    st.markdown("## 📊 Available Data")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Franklin County Tax Data")
        if (RAW_DATA_DIR / 'TaxDetail.xlsx').exists():
            st.success("✅ Tax data loaded")
            st.info("22,858 total delinquent parcels")
            st.info("7,870 Columbus properties available")
        else:
            st.error("❌ Tax data not found")
            st.warning("Go to Data Management to download")

    with col2:
        st.markdown("### Code Violations API")
        st.success("✅ Columbus API connected")
        st.info("Real-time violation data")
        st.info("No authentication required")


# ========================================
# GENERATE LEADS PAGE
# ========================================
elif page == "🚀 Generate Leads":
    st.markdown('<h1 class="main-header">🚀 Generate Leads</h1>', unsafe_allow_html=True)

    st.markdown("### Configure Your Lead Generation")

    col1, col2 = st.columns(2)

    with col1:
        num_properties = st.slider(
            "Number of Properties",
            min_value=10,
            max_value=1000,
            value=100,
            step=10,
            help="How many leads to generate"
        )

        min_tax_debt = st.slider(
            "Minimum Tax Debt ($)",
            min_value=1000,
            max_value=10000,
            value=2000,
            step=500,
            help="Minimum amount owed in taxes"
        )

    with col2:
        min_years = st.slider(
            "Minimum Years Delinquent",
            min_value=1,
            max_value=10,
            value=2,
            help="Minimum years behind on taxes"
        )

        columbus_only = st.checkbox(
            "Columbus Only",
            value=True,
            help="Filter to Columbus zip codes only"
        )

    st.markdown("---")

    # Probate & Foreclosure Integration Options
    st.markdown("#### Boost with Probate & Pre-Foreclosure Data")
    col3, col4 = st.columns(2)

    with col3:
        include_probate = st.checkbox(
            "Include Probate Data",
            value=True,
            help="Match probate cases to boost motivation scores (+40 pts)"
        )

    with col4:
        include_sheriff = st.checkbox(
            "Include Sheriff Sales",
            value=True,
            help="Match sheriff sale properties to boost scores (+35 pts)"
        )

    st.markdown("---")

    if st.button("🚀 Generate Leads Now", type="primary"):
        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            # Step 0: Archive existing data before generating new
            status_text.text("📁 Archiving existing data...")
            archived = archive_before_scrape('delinquent')
            if archived:
                st.info(f"📁 Archived {len(archived)} existing files")
            progress_bar.progress(5)

            # Step 1: Load tax data (using new GenericExcelLoader with year_built support)
            status_text.text("📊 Loading tax delinquent properties...")
            progress_bar.progress(10)

            # Use market config and factory for year_built support
            market = load_market('columbus_oh')
            loader = ScraperFactory.create_tax_scraper(market)
            df = loader.load_tax_delinquent_properties(
                min_amount_owed=min_tax_debt,
                min_years_delinquent=min_years,
                filter_by_zip=columbus_only,
                max_properties=num_properties
            )

            progress_bar.progress(30)
            st.success(f"✅ Loaded {len(df)} properties")

            # Step 1.5: Integrate Probate & Sheriff Sale Data
            probate_df = None
            sheriff_df = None

            if include_probate or include_sheriff:
                status_text.text("⚖️ Loading probate & foreclosure data...")
                integrator = LeadIntegrator()

                # Load existing probate data if available
                probate_file = PROCESSED_DATA_DIR / 'probate_leads.csv'
                if include_probate and probate_file.exists():
                    probate_df = pd.read_csv(probate_file)
                    st.info(f"📜 Found {len(probate_df)} probate cases")

                # Load existing sheriff sale data if available
                sheriff_file = PROCESSED_DATA_DIR / 'sheriff_sale_leads.csv'
                if include_sheriff and sheriff_file.exists():
                    sheriff_df = pd.read_csv(sheriff_file)
                    st.info(f"🏚️ Found {len(sheriff_df)} sheriff sale properties")

                # Integrate all sources
                if probate_df is not None or sheriff_df is not None:
                    df = integrator.integrate_all_sources(df, probate_df, sheriff_df)

                    # Count matches
                    probate_matches = df['is_probate'].sum() if 'is_probate' in df.columns else 0
                    sheriff_matches = df['is_sheriff_sale'].sum() if 'is_sheriff_sale' in df.columns else 0

                    if probate_matches > 0:
                        st.success(f"✅ Matched {probate_matches} properties to probate cases (+40 pts each)")
                    if sheriff_matches > 0:
                        st.success(f"✅ Matched {sheriff_matches} properties to sheriff sales (+35 pts each)")
                else:
                    st.warning("⚠️ No probate/sheriff data found. Scrape data first on the Probate & Foreclosure page.")

            progress_bar.progress(40)

            # Step 2: Enrich with violations (using ADDRESS matching)
            status_text.text("🏛️ Enriching with code violations...")
            progress_bar.progress(50)

            api = ColumbusViolationsAPI()

            # Use addresses for matching (parcel formats don't match between systems)
            addresses = df['address'].tolist()

            # Limit to first 100 to avoid API overload (each is a separate request)
            sample_addresses = addresses[:min(100, len(addresses))]
            violations_dict = api.get_violations_by_address(sample_addresses)

            if violations_dict:
                # Create violations dataframe keyed by address
                violations_data = []
                for addr, viol_list in violations_dict.items():
                    critical = sum(1 for v in viol_list if v['severity'] == 'critical')
                    major = sum(1 for v in viol_list if v['severity'] == 'major')
                    minor = sum(1 for v in viol_list if v['severity'] == 'minor')
                    violations_data.append({
                        'address_match': addr.upper(),
                        'total_violations': len(viol_list),
                        'critical_violations': critical,
                        'major_violations': major,
                        'minor_violations': minor
                    })

                df_violations = pd.DataFrame(violations_data)

                # Normalize addresses for matching
                df['address_match'] = df['address'].str.upper().str.strip()
                df = df.merge(df_violations, on='address_match', how='left')
                df.drop('address_match', axis=1, inplace=True)

                violation_cols = ['total_violations', 'critical_violations', 'major_violations', 'minor_violations']
                for col in violation_cols:
                    if col in df.columns:
                        df[col] = df[col].fillna(0).astype(int)

                matched = (df['total_violations'] > 0).sum()
                st.info(f"🏛️ Found {matched} properties with code violations")
            else:
                df['total_violations'] = 0
                df['critical_violations'] = 0
                df['major_violations'] = 0
                df['minor_violations'] = 0

            progress_bar.progress(70)

            # Step 3: Calculate scores
            status_text.text("🎯 Calculating motivation scores...")

            scorer = MotivationScorer()
            properties = df.to_dict('records')
            scored_properties = []

            for prop in properties:
                prop_for_scoring = {
                    'address': prop.get('address', ''),
                    'owner_name': prop.get('owner_name', ''),
                    'mailing_address': prop.get('mailing_address', ''),
                    'assessed_value': prop.get('assessed_value', 0),
                    'taxes_owed': prop.get('taxes_owed', 0),
                    'years_delinquent': prop.get('years_delinquent', 0),
                    'code_violations': prop.get('total_violations', 0),
                    'is_absentee': prop.get('is_absentee', False),
                    # Probate fields (adds up to +40 points)
                    'is_probate': prop.get('is_probate', False),
                    'probate_case_number': prop.get('probate_case_number', ''),
                    'decedent_name': prop.get('decedent_name', ''),
                    # Pre-foreclosure fields (adds up to +35 points)
                    'is_pre_foreclosure': prop.get('is_pre_foreclosure', False),
                    'is_sheriff_sale': prop.get('is_sheriff_sale', False),
                    'auction_date': prop.get('auction_date', ''),
                }
                scored = scorer.calculate_score(prop_for_scoring)
                prop['motivation_score'] = scored['score']
                prop['tier'] = scored['tier']
                prop['tier_name'] = scored['tier_name']
                prop['rating'] = scored['rating']
                prop['reasons'] = ', '.join(scored['reasons'])
                scored_properties.append(prop)

            df = pd.DataFrame(scored_properties)
            progress_bar.progress(50)

            # Step 4: Detect whale owners
            status_text.text("🐋 Detecting multi-property owners...")
            detector = PortfolioDetector()
            df = detector.analyze_portfolios(df)
            df = detector.boost_whale_scores(df, boost_per_property=5)
            progress_bar.progress(60)

            # Step 5: Calculate equity
            status_text.text("💰 Calculating equity estimates...")
            equity_calc = EquityCalculator()
            df = equity_calc.add_equity_columns(df)
            progress_bar.progress(70)

            # Step 6: Estimate ARV
            status_text.text("📊 Estimating ARV...")
            comps = CompsEstimator()
            df = comps.add_arv_columns(df)
            progress_bar.progress(80)

            # Step 7: Track freshness
            status_text.text("📅 Tracking data freshness...")
            tracker = FreshnessTracker()
            df = tracker.add_freshness_columns(df)
            df['is_new_lead'] = True
            df['change_alert'] = 'NEW LEAD'
            progress_bar.progress(85)

            # Step 8: Add Street View URLs
            status_text.text("📷 Adding Street View links...")
            street_view = StreetViewHelper()
            df = street_view.add_street_view_columns(df, address_col='address', city='Columbus', state='OH')
            progress_bar.progress(88)

            # Initialize skip trace columns (user can skip trace later on Skip Trace page)
            status_text.text("📞 Preparing contact columns...")
            df['phone'] = None
            df['phone_2'] = None
            df['email'] = None
            df['email_2'] = None
            df['skip_traced'] = False
            df['skip_trace_confidence'] = 0.0
            progress_bar.progress(90)

            # Step 9: Export as numbered batch with month label
            status_text.text("📤 Exporting leads as batch...")

            PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)

            # Create batches directory
            batches_dir = PROCESSED_DATA_DIR / 'batches'
            batches_dir.mkdir(parents=True, exist_ok=True)

            # Determine next batch number and month label
            from datetime import datetime
            current_month = datetime.now().strftime('%b').lower()  # jan, feb, etc.
            current_year = datetime.now().strftime('%Y')  # 2025

            # Find existing batches to determine next number
            existing_batches = list(batches_dir.glob(f'batch_*_{current_month}_{current_year}.csv'))
            if existing_batches:
                # Extract batch numbers and find max
                batch_numbers = []
                for batch_file in existing_batches:
                    try:
                        batch_num = int(batch_file.stem.split('_')[1])
                        batch_numbers.append(batch_num)
                    except:
                        pass
                next_batch_num = max(batch_numbers) + 1 if batch_numbers else 1
            else:
                next_batch_num = 1

            # Create batch filename
            batch_filename = f'batch_{next_batch_num}_{current_month}_{current_year}.csv'
            batch_path = batches_dir / batch_filename

            # Save to batch file
            df.to_csv(batch_path, index=False)
            st.success(f"📁 Saved as **{batch_filename}** ({len(df)} leads)")

            # Also save to main file for compatibility (latest batch)
            all_leads_path = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
            df.to_csv(all_leads_path, index=False)
            df.to_csv(PROCESSED_DATA_DIR / 'all_leads_real.csv', index=False)

            # Save tier files for this batch too
            for tier_num in [1, 2, 3]:
                tier_df = df[df['tier'] == tier_num]
                if len(tier_df) > 0:
                    tier_batch_filename = f'batch_{next_batch_num}_{current_month}_{current_year}_tier_{tier_num}.csv'
                    tier_df.to_csv(batches_dir / tier_batch_filename, index=False)
                    # Also save to main tier files for compatibility
                    tier_df.to_csv(PROCESSED_DATA_DIR / f'columbus_oh_tier_{tier_num}_leads.csv', index=False)
                    tier_df.to_csv(PROCESSED_DATA_DIR / f'tier_{tier_num}_leads_real.csv', index=False)

            progress_bar.progress(100)
            status_text.text("✅ Complete!")

            # Show results
            st.balloons()

            st.markdown("---")
            st.markdown("## 🎉 Generation Complete!")

            col1, col2, col3, col4 = st.columns(4)

            tier_1 = len(df[df['tier'] == 1])
            tier_2 = len(df[df['tier'] == 2])
            tier_3 = len(df[df['tier'] == 3])

            with col1:
                st.metric("Total Leads", len(df))
            with col2:
                st.metric("Tier 1", tier_1, f"${tier_1 * 100:,}")
            with col3:
                st.metric("Tier 2", tier_2, f"${tier_2 * 75:,}")
            with col4:
                st.metric("Tier 3", tier_3, f"${tier_3 * 50:,}")

            revenue = tier_1*100 + tier_2*75 + tier_3*50
            st.success(f"💰 **Potential Revenue: ${revenue:,}**")

            # Show preview
            st.markdown("### Preview (Top 5 Leads)")
            preview_cols = ['address', 'owner_name', 'motivation_score', 'taxes_owed', 'tier_name']
            if 'year_built' in df.columns:
                preview_cols.insert(4, 'year_built')
            top_5 = df.nlargest(5, 'motivation_score')[preview_cols]
            st.dataframe(top_5, width='stretch')

        except Exception as e:
            st.error(f"❌ Error: {e}")
            import traceback
            st.code(traceback.format_exc())


# ========================================
# PROBATE & FORECLOSURE PAGE
# ========================================
elif page == "⚖️ Probate & Foreclosure":
    st.markdown('<h1 class="main-header">⚖️ Probate & Pre-Foreclosure Leads</h1>', unsafe_allow_html=True)
    st.markdown("### High-Motivation Leads from Court Records")

    st.info("""
    **Probate leads** are properties from estate cases where heirs often want to sell quickly.
    **Pre-foreclosure leads** are properties heading to sheriff sale - owners have deadline pressure.
    """)

    st.success("""
    **Pro Tip:** Go back **6 months (180 days)** for probate - heirs are MORE motivated after dealing with the property for a while.
    Cases 3-12 months old are in the sweet spot where heirs are ready to sell but haven't listed yet.
    """)

    # Two columns for the two scraper types
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 📜 Probate Court Records")
        st.markdown("Franklin County Probate Court estate cases")

        probate_days = st.slider("Days to look back (Probate)", 30, 365, 180, key="probate_days")
        probate_max = st.slider("Max results (Probate)", 50, 1000, 300, key="probate_max")

        if st.button("🔍 Scrape Probate Cases", type="primary", key="btn_probate"):
            with st.spinner("Scraping probate court records... (this may take 1-2 minutes)"):
                try:
                    # Archive existing probate data first
                    archived = archive_before_scrape('probate')
                    if archived:
                        st.info(f"📁 Archived {len(archived)} existing probate file(s)")

                    scraper = ProbateScraper(headless=True)
                    probate_df = scraper.scrape(days_back=probate_days, max_results=probate_max)

                    if not probate_df.empty:
                        st.success(f"✅ Found {len(probate_df)} probate cases!")

                        # Save to session state
                        st.session_state['probate_df'] = probate_df

                        # Save to file
                        probate_file = PROCESSED_DATA_DIR / 'probate_leads.csv'
                        probate_df.to_csv(probate_file, index=False)
                        st.info(f"💾 Saved to {probate_file.name}")
                    else:
                        st.warning("No probate cases found")

                except Exception as e:
                    st.error(f"❌ Error: {e}")
                    import traceback
                    st.code(traceback.format_exc())

    with col2:
        st.markdown("#### 🏚️ Sheriff Sales / Pre-Foreclosure")
        st.markdown("Properties scheduled for auction")

        sheriff_max = st.slider("Max results (Sheriff Sales)", 20, 500, 100, key="sheriff_max")
        st.caption("*Sheriff sales are limited by actual foreclosure activity in the county*")

        if st.button("🔍 Scrape Sheriff Sales", type="primary", key="btn_sheriff"):
            with st.spinner("Scraping sheriff sale listings..."):
                try:
                    # Archive existing sheriff data first
                    archived = archive_before_scrape('sheriff')
                    if archived:
                        st.info(f"📁 Archived {len(archived)} existing sheriff file(s)")

                    scraper = SheriffSaleScraper(county="franklin")
                    sheriff_df = scraper.scrape(max_results=sheriff_max, include_details=False)

                    if not sheriff_df.empty:
                        st.success(f"✅ Found {len(sheriff_df)} sheriff sale properties!")

                        # Save to session state
                        st.session_state['sheriff_df'] = sheriff_df

                        # Save to file
                        sheriff_file = PROCESSED_DATA_DIR / 'sheriff_sale_leads.csv'
                        sheriff_df.to_csv(sheriff_file, index=False)
                        st.info(f"💾 Saved to {sheriff_file.name}")
                    else:
                        st.warning("No sheriff sale properties found")

                except Exception as e:
                    st.error(f"❌ Error: {e}")
                    import traceback
                    st.code(traceback.format_exc())

    st.markdown("---")

    # ========================================
    # MATCH PROBATE TO PROPERTIES SECTION
    # ========================================
    st.markdown("## 🔗 Match Probate Cases to Properties")
    st.markdown("Find properties owned by deceased to get addresses for skip tracing")

    probate_file = PROCESSED_DATA_DIR / 'probate_leads.csv'
    parcel_file = RAW_DATA_DIR / 'Parcel.xlsx'

    if not probate_file.exists():
        st.info("Scrape probate cases first to enable matching")
    elif not parcel_file.exists():
        st.warning("⚠️ Parcel.xlsx not found. Download from Franklin County Auditor to enable property matching.")
        st.markdown("[Download Franklin County Data](https://apps.franklincountyauditor.com/Outside_User_Files/)")
    else:
        # Load current probate data
        probate_df_check = pd.read_csv(probate_file)
        total_cases = len(probate_df_check)
        already_matched = probate_df_check['property_address'].notna().sum() if 'property_address' in probate_df_check.columns else 0

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Probate Cases", total_cases)
        with col2:
            st.metric("Already Matched", already_matched)
        with col3:
            st.metric("Need Matching", total_cases - already_matched)

        if st.button("🔗 Match Probate to Properties", type="primary", key="btn_match_probate"):
            with st.spinner("Matching probate cases to property records..."):
                try:
                    matcher = ProbateMatcher()

                    if matcher.load_property_records():
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        def update_progress(current, total):
                            progress_bar.progress(current / total)
                            status_text.text(f"Matching {current}/{total}...")

                        # Match probate to properties
                        enhanced_df = matcher.match_probate_to_properties(
                            probate_df_check,
                            progress_callback=update_progress
                        )

                        # Save enhanced data
                        enhanced_df.to_csv(probate_file, index=False)

                        # Get stats
                        stats = matcher.get_match_stats(enhanced_df)

                        progress_bar.progress(100)
                        status_text.text("✅ Matching complete!")

                        st.success(f"✅ Matched {stats['matched_cases']}/{stats['total_cases']} cases ({stats['match_rate']:.1f}%)")

                        if stats['multi_property_owners'] > 0:
                            st.info(f"📊 {stats['multi_property_owners']} decedents owned multiple properties")

                        st.rerun()
                    else:
                        st.error("Could not load property records")

                except Exception as e:
                    st.error(f"Error: {e}")
                    import traceback
                    st.code(traceback.format_exc())

    st.markdown("---")

    # Display results if we have them
    tab1, tab2 = st.tabs(["📜 Probate Results", "🏚️ Sheriff Sale Results"])

    with tab1:
        # Always load from file to get latest data (including matched properties)
        probate_file = PROCESSED_DATA_DIR / 'probate_leads.csv'
        if probate_file.exists():
            probate_df = pd.read_csv(probate_file)
        else:
            probate_df = pd.DataFrame()

        if not probate_df.empty:
            st.subheader(f"📋 {len(probate_df)} Probate Cases")

            # Display columns - include executor name, property address, and contact info
            display_cols = ['case_number', 'decedent_name', 'executor_name', 'property_address', 'phone', 'email', 'case_type', 'safe_to_call']
            available_cols = [c for c in display_cols if c in probate_df.columns]

            st.dataframe(
                probate_df[available_cols].head(50),
                use_container_width=True,
                hide_index=True,
                column_config={
                    'safe_to_call': st.column_config.CheckboxColumn('Safe to Call'),
                    'property_address': st.column_config.TextColumn('Property Address', width='medium'),
                    'executor_name': st.column_config.TextColumn('Executor', width='medium'),
                }
            )

            # Download button
            csv = probate_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Probate Leads CSV",
                data=csv,
                file_name="probate_leads.csv",
                mime="text/csv"
            )

            # Scrape Executor Names Section
            st.markdown("---")
            st.markdown("#### 👤 Scrape Executor Names")
            st.caption("Scrape executor/administrator names from probate case detail pages (FREE)")

            # Check for existing executor names
            has_executor = probate_df['executor_name'].notna().sum() if 'executor_name' in probate_df.columns else 0
            without_executor = len(probate_df) - has_executor

            col1, col2 = st.columns(2)
            with col1:
                st.metric("With Executor", has_executor)
            with col2:
                st.metric("Need Scraping", without_executor)

            if without_executor == 0:
                st.success("✅ All cases have executor names!")
            else:
                if st.button("🔍 Scrape Executor Names", type="primary", key="btn_scrape_executors"):
                    from scrapers.probate_scraper import ProbateScraper

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    scraper = ProbateScraper()

                    def update_progress(current, total):
                        progress_bar.progress(current / total)
                        status_text.text(f"Scraping case {current}/{total}...")

                    enriched_df = scraper.enrich_with_executor_info(
                        probate_df,
                        progress_callback=update_progress
                    )

                    # Save to file
                    enriched_df.to_csv(probate_file, index=False)

                    found_new = enriched_df['executor_name'].notna().sum() - has_executor
                    status_text.empty()
                    progress_bar.empty()
                    st.success(f"✅ Scraped {found_new} new executor names!")
                    st.rerun()

            # Skip Trace Section for Probate
            st.markdown("---")
            st.markdown("#### 📞 Skip Trace Probate Cases")
            st.caption("Skip trace EXECUTOR names (not deceased) + property address for best results")

            # Check for existing phone numbers
            has_phone = probate_df['phone'].notna().sum() if 'phone' in probate_df.columns else 0
            without_phone = len(probate_df) - has_phone

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Cases", len(probate_df))
            with col2:
                st.metric("With Phone", has_phone)
            with col3:
                st.metric("Need Skip Trace", without_phone)

            if not BATCHDATA_API_KEY:
                st.warning("⚠️ Configure BatchData API key to enable skip tracing")
            elif without_phone == 0:
                st.success("✅ All probate cases have been skip traced!")
            else:
                col1, col2 = st.columns(2)

                with col1:
                    max_trace = min(50, without_phone)
                    # Handle case when only 1 remains (slider needs min < max)
                    if max_trace <= 1:
                        probate_trace_count = 1
                        st.info(f"1 case remaining to skip trace")
                    else:
                        probate_trace_count = st.slider(
                            "Cases to skip trace",
                            min_value=1,
                            max_value=max_trace,
                            value=min(10, max_trace),
                            key="probate_trace_count"
                        )

                with col2:
                    estimated_cost = probate_trace_count * 0.20
                    st.warning(f"💰 Estimated Cost: ${estimated_cost:.2f}")

                # Check for executor names
                executor_count = probate_df['executor_name'].notna().sum() if 'executor_name' in probate_df.columns else 0
                if executor_count > 0:
                    st.success(f"✅ {executor_count} cases have executor names - will skip trace executors!")
                else:
                    st.warning("⚠️ No executor names scraped yet. Click 'Scrape Executor Names' above first!")

                # Check if we have matched properties
                matched_count = probate_df['property_address'].notna().sum() if 'property_address' in probate_df.columns else 0
                if matched_count > 0:
                    st.info(f"📍 {matched_count} cases have property addresses for better lookup accuracy")

                if st.button("📞 Skip Trace Executors", type="primary", key="btn_probate_trace"):
                    # Filter to cases without phone
                    if 'phone' not in probate_df.columns:
                        probate_df['phone'] = None
                        probate_df['email'] = None

                    to_trace = probate_df[probate_df['phone'].isna()].head(probate_trace_count)

                    progress_bar = st.progress(0)
                    status_text = st.empty()

                    try:
                        tracer = SkipTracer(provider='batchdata', api_key=BATCHDATA_API_KEY)
                        dnc_checker = DNCChecker()

                        results = []
                        success_count = 0
                        total = len(to_trace)

                        for i, (idx, row) in enumerate(to_trace.iterrows()):
                            # Use EXECUTOR name (living person) instead of decedent name (deceased)
                            executor_name = str(row.get('executor_name', '')) if pd.notna(row.get('executor_name')) else ''
                            # Handle string 'nan' which is not a valid name
                            if executor_name.lower() == 'nan':
                                executor_name = ''
                            decedent_name = str(row.get('decedent_name', ''))
                            if decedent_name.lower() == 'nan':
                                decedent_name = ''

                            # Prefer executor name, fall back to decedent name if no executor
                            search_name = executor_name if executor_name else decedent_name

                            if not search_name or search_name.lower() == 'nan':
                                continue

                            # Use property_address if matched, otherwise empty
                            property_address = str(row.get('property_address', '')) if pd.notna(row.get('property_address')) else ''
                            property_city = str(row.get('property_city', 'Columbus')) if pd.notna(row.get('property_city')) else 'Columbus'
                            # Clean city name - remove "CITY" suffix (e.g., "COLUMBUS CITY" -> "Columbus")
                            property_city = property_city.replace(' CITY', '').replace(' city', '').title()
                            property_zip = str(row.get('property_zip', '')) if pd.notna(row.get('property_zip')) else ''

                            display_name = f"{search_name[:25]}{'(Exec)' if executor_name else '(Dec)'}"
                            status_text.text(f"Tracing {i+1}/{total}: {display_name}...")
                            progress_bar.progress((i + 1) / total)

                            # Skip trace with executor name + property address
                            result = tracer.lookup(
                                owner_name=search_name,
                                address=property_address,
                                city=property_city,
                                state='OH',
                                zip_code=property_zip
                            )

                            if result.success:
                                success_count += 1
                                probate_df.at[idx, 'phone'] = result.primary_phone
                                probate_df.at[idx, 'email'] = result.primary_email
                                probate_df.at[idx, 'skip_traced'] = True

                                # DNC check
                                if result.primary_phone:
                                    dnc_result = dnc_checker.check_dnc(result.primary_phone)
                                    probate_df.at[idx, 'dnc_status'] = dnc_result['dnc_status']
                                    probate_df.at[idx, 'safe_to_call'] = dnc_result['safe_to_call']

                            results.append({
                                'decedent_name': decedent_name,
                                'phone': result.primary_phone if result.success else None,
                                'email': result.primary_email if result.success else None,
                                'success': result.success
                            })

                        # Save updated data
                        probate_df.to_csv(probate_file, index=False)

                        progress_bar.progress(100)
                        status_text.text("✅ Skip trace complete!")

                        # Show results
                        st.markdown("##### Results")

                        results_df = pd.DataFrame(results)
                        hit_rate = (success_count / total * 100) if total > 0 else 0

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Traced", total)
                        with col2:
                            st.metric("Found", success_count)
                        with col3:
                            st.metric("Hit Rate", f"{hit_rate:.0f}%")

                        # Show successful traces
                        successful = results_df[results_df['success'] == True]
                        if len(successful) > 0:
                            st.dataframe(successful, width='stretch', hide_index=True)

                        st.success("✅ Results saved!")
                        st.rerun()

                    except Exception as e:
                        st.error(f"Error: {e}")
                        import traceback
                        st.code(traceback.format_exc())
        else:
            st.info("No probate data yet. Click 'Scrape Probate Cases' to fetch records.")

    with tab2:
        # Check session state or load from file
        sheriff_file = PROCESSED_DATA_DIR / 'sheriff_sale_leads.csv'
        if 'sheriff_df' in st.session_state:
            sheriff_df = st.session_state['sheriff_df']
        elif sheriff_file.exists():
            sheriff_df = pd.read_csv(sheriff_file)
        else:
            sheriff_df = pd.DataFrame()

        if not sheriff_df.empty:
            st.markdown(f"**{len(sheriff_df)} Sheriff Sale Properties**")

            # Display columns - include contact info
            display_cols = ['address', 'city', 'phone', 'email', 'auction_date', 'starting_bid', 'safe_to_call']
            available_cols = [c for c in display_cols if c in sheriff_df.columns]

            # Format starting_bid as currency if present
            display_df = sheriff_df[available_cols].copy()
            if 'starting_bid' in display_df.columns:
                display_df['starting_bid'] = display_df['starting_bid'].apply(lambda x: f"${x:,.0f}" if pd.notna(x) and x > 0 else "TBD")

            st.dataframe(
                display_df.head(50),
                width='stretch',
                hide_index=True,
                column_config={
                    'safe_to_call': st.column_config.CheckboxColumn('Safe to Call'),
                }
            )

            # Download button
            csv = sheriff_df.to_csv(index=False)
            st.download_button(
                label="📥 Download Sheriff Sale Leads CSV",
                data=csv,
                file_name="sheriff_sale_leads.csv",
                mime="text/csv"
            )
        else:
            st.info("No sheriff sale data yet. Click 'Scrape Sheriff Sales' to fetch listings.")

    st.markdown("---")

    # ========================================
    # SKIP TRACE SECTION FOR SHERIFF SALES
    # ========================================
    st.markdown("## 📞 Skip Trace Sheriff Sale Properties")
    st.markdown("Find owner contact info for properties heading to auction")

    # Load sheriff sale data
    sheriff_file = PROCESSED_DATA_DIR / 'sheriff_sale_leads.csv'
    if sheriff_file.exists():
        sheriff_df = pd.read_csv(sheriff_file)

        # Check for existing phone numbers
        has_phone = sheriff_df['phone'].notna().sum() if 'phone' in sheriff_df.columns else 0
        without_phone = len(sheriff_df) - has_phone

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Properties", len(sheriff_df))
        with col2:
            st.metric("With Phone", has_phone)
        with col3:
            st.metric("Need Skip Trace", without_phone)

        if not BATCHDATA_API_KEY:
            st.warning("⚠️ Configure BatchData API key to enable skip tracing")
        elif without_phone == 0:
            st.success("✅ All sheriff sale properties have been skip traced!")
        else:
            # Skip trace options
            col1, col2 = st.columns(2)

            with col1:
                max_trace = min(50, without_phone)
                sheriff_trace_count = st.slider(
                    "Properties to skip trace",
                    min_value=1,
                    max_value=max(1, max_trace),
                    value=min(10, max_trace),
                    key="sheriff_trace_count"
                )

            with col2:
                estimated_cost = sheriff_trace_count * 0.20
                st.warning(f"💰 Estimated Cost: ${estimated_cost:.2f}")

            if st.button("📞 Skip Trace Sheriff Sales", type="primary", key="btn_sheriff_trace"):
                # Filter to properties without phone
                if 'phone' not in sheriff_df.columns:
                    sheriff_df['phone'] = None
                    sheriff_df['email'] = None
                    sheriff_df['owner_name'] = None

                to_trace = sheriff_df[sheriff_df['phone'].isna()].head(sheriff_trace_count)

                progress_bar = st.progress(0)
                status_text = st.empty()

                try:
                    tracer = SkipTracer(provider='batchdata', api_key=BATCHDATA_API_KEY)
                    dnc_checker = DNCChecker()

                    results = []
                    success_count = 0
                    total = len(to_trace)

                    for i, (idx, row) in enumerate(to_trace.iterrows()):
                        address = str(row.get('address', ''))
                        city = str(row.get('city', 'Columbus'))
                        zip_code = str(row.get('zip_code', '')) if pd.notna(row.get('zip_code')) else ''

                        status_text.text(f"Tracing {i+1}/{total}: {address[:35]}...")
                        progress_bar.progress((i + 1) / total)

                        # Skip trace by address (BatchData can find owner from address)
                        result = tracer.lookup(
                            owner_name='',  # Empty - lookup by address
                            address=address,
                            city=city,
                            state='OH',
                            zip_code=zip_code
                        )

                        if result.success:
                            success_count += 1
                            sheriff_df.at[idx, 'phone'] = result.primary_phone
                            sheriff_df.at[idx, 'email'] = result.primary_email
                            sheriff_df.at[idx, 'owner_name'] = result.owner_name if hasattr(result, 'owner_name') else None
                            sheriff_df.at[idx, 'skip_traced'] = True

                            # DNC check
                            if result.primary_phone:
                                dnc_result = dnc_checker.check_dnc(result.primary_phone)
                                sheriff_df.at[idx, 'dnc_status'] = dnc_result['dnc_status']
                                sheriff_df.at[idx, 'safe_to_call'] = dnc_result['safe_to_call']

                        results.append({
                            'address': address,
                            'phone': result.primary_phone if result.success else None,
                            'email': result.primary_email if result.success else None,
                            'success': result.success
                        })

                    # Save updated data
                    sheriff_df.to_csv(sheriff_file, index=False)

                    progress_bar.progress(100)
                    status_text.text("✅ Skip trace complete!")

                    # Show results
                    st.markdown("### Results")

                    results_df = pd.DataFrame(results)
                    hit_rate = (success_count / total * 100) if total > 0 else 0

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Traced", total)
                    with col2:
                        st.metric("Found", success_count)
                    with col3:
                        st.metric("Hit Rate", f"{hit_rate:.0f}%")

                    # Show successful traces
                    successful = results_df[results_df['success'] == True]
                    if len(successful) > 0:
                        st.dataframe(successful, width='stretch', hide_index=True)

                    st.success("✅ Results saved!")

                except Exception as e:
                    st.error(f"Error: {e}")
                    import traceback
                    st.code(traceback.format_exc())
    else:
        st.info("No sheriff sale data. Scrape sheriff sales first to enable skip tracing.")

    st.markdown("---")
    st.markdown("### 💡 Tips")
    st.markdown("""
    - **Probate leads** have the highest motivation scores (heirs want quick sales)
    - **Sheriff sales** have hard deadlines - contact owners BEFORE auction date
    - Cross-reference with your tax delinquent leads to find overlapping opportunities
    - Run "Generate Leads" with probate/sheriff data enabled to merge into main leads
    """)


# ========================================
# SKIP TRACE PAGE
# ========================================
elif page == "📞 Skip Trace":
    st.markdown('<h1 class="main-header">📞 Skip Trace</h1>', unsafe_allow_html=True)
    st.markdown("### Find Real Phone Numbers & Emails On-Demand")

    # Check API status
    col1, col2, col3 = st.columns(3)

    with col1:
        if BATCHDATA_API_KEY:
            st.success("✅ BatchData API Connected")
        else:
            st.error("❌ No API Key Configured")
            st.info("Add BATCHDATA_API_KEY to your .env file")

    with col2:
        st.info("💰 Cost: ~$0.15-0.25 per lookup")

    with col3:
        if BATCHDATA_API_KEY:
            # Try to get balance (optional)
            try:
                from sellers.skip_tracing.providers.batchdata_provider import BatchDataProvider
                provider = BatchDataProvider(api_key=BATCHDATA_API_KEY)
                balance = provider.get_balance()
                if balance:
                    st.metric("Account Balance", f"${balance:.2f}")
                else:
                    st.metric("Account Balance", "Check BatchData.com")
            except:
                st.metric("Account Balance", "Check BatchData.com")

    st.markdown("---")

    # Load leads
    all_leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
    if not all_leads_file.exists():
        all_leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

    if not all_leads_file.exists():
        st.warning("⚠️ No leads found. Generate leads first!")
    elif not BATCHDATA_API_KEY:
        st.warning("⚠️ Configure your BatchData API key in .env to enable skip tracing")
    else:
        df = pd.read_csv(all_leads_file)

        # ========================================
        # BULK SKIP TRACE SECTION
        # ========================================
        st.markdown("## 🚀 Bulk Skip Trace")
        st.markdown("Skip trace multiple leads with one click")

        # Count leads without phones
        leads_without_phone = df[df['phone'].isna() | (df['phone'] == '')]
        leads_without_phone = leads_without_phone.sort_values('motivation_score', ascending=False)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Leads Without Phone", len(leads_without_phone))

        with col2:
            # Calculate how many we can afford
            avg_cost = 0.20  # Average cost per lookup
            affordable = min(len(leads_without_phone), 100)  # Cap at 100
            st.metric("Available to Trace", affordable)

        with col3:
            tier1_no_phone = len(leads_without_phone[leads_without_phone['tier'] == 1])
            st.metric("Tier 1 Without Phone", tier1_no_phone)

        # Bulk trace options
        st.markdown("### Configure Bulk Trace")

        col1, col2 = st.columns(2)

        with col1:
            max_bulk = max(5, min(100, len(leads_without_phone)))
            default_bulk = max(5, min(25, len(leads_without_phone)))
            bulk_count = st.slider(
                "Number of leads to skip trace",
                min_value=5,
                max_value=max_bulk,
                value=default_bulk,
                step=5,
                help="Higher motivation score leads are traced first"
            ) if len(leads_without_phone) >= 5 else 0

            bulk_min_score = st.slider(
                "Minimum motivation score",
                min_value=0,
                max_value=100,
                value=50,
                help="Only trace leads with score above this"
            )

        with col2:
            bulk_tiers = st.multiselect(
                "Include tiers",
                [1, 2, 3, 4],
                default=[1, 2],
                help="Which tier leads to include"
            )

            # Cost estimate
            estimated_cost = bulk_count * 0.20
            st.warning(f"💰 **Estimated Cost:** ${estimated_cost:.2f} (at ~$0.20/lookup)")

        # Filter leads for bulk trace
        bulk_leads = leads_without_phone[
            (leads_without_phone['motivation_score'] >= bulk_min_score) &
            (leads_without_phone['tier'].isin(bulk_tiers))
        ].head(bulk_count)

        st.info(f"**{len(bulk_leads)}** leads ready to skip trace (sorted by motivation score)")

        # Preview
        with st.expander("Preview leads to be traced"):
            preview_cols = ['address', 'owner_name', 'motivation_score', 'tier', 'taxes_owed']
            st.dataframe(bulk_leads[preview_cols], width='stretch', hide_index=True)

        # Bulk trace button
        col1, col2, col3 = st.columns([1, 2, 1])

        with col2:
            if st.button(f"🚀 Skip Trace {len(bulk_leads)} Leads", type="primary", disabled=len(bulk_leads) == 0):
                if len(bulk_leads) == 0:
                    st.warning("No leads to trace")
                else:
                    # Confirm cost
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    results_container = st.container()

                    try:
                        tracer = SkipTracer(provider='batchdata', api_key=BATCHDATA_API_KEY)
                        dnc_checker = DNCChecker()

                        results = []
                        success_count = 0
                        total = len(bulk_leads)

                        for i, (idx, row) in enumerate(bulk_leads.iterrows()):
                            owner_name = str(row['owner_name'])
                            address = str(row['address'])
                            zip_code = str(row.get('zip_code', '')) if pd.notna(row.get('zip_code')) else ''

                            status_text.text(f"Tracing {i+1}/{total}: {address[:35]}...")
                            progress_bar.progress((i + 1) / total)

                            # Skip trace
                            result = tracer.lookup(
                                owner_name=owner_name,
                                address=address,
                                city='Columbus',
                                state='OH',
                                zip_code=zip_code
                            )

                            # Update main DataFrame
                            if result.success:
                                success_count += 1
                                df.at[idx, 'phone'] = result.primary_phone
                                df.at[idx, 'email'] = result.primary_email
                                if len(result.phones) > 1:
                                    df.at[idx, 'phone_2'] = result.phones[1]
                                if len(result.emails) > 1:
                                    df.at[idx, 'email_2'] = result.emails[1]
                                df.at[idx, 'skip_traced'] = True
                                df.at[idx, 'skip_trace_confidence'] = result.confidence_score

                                # Run DNC check on new phone
                                if result.primary_phone:
                                    dnc_result = dnc_checker.check_dnc(result.primary_phone)
                                    df.at[idx, 'dnc_status'] = dnc_result['dnc_status']
                                    df.at[idx, 'safe_to_call'] = dnc_result['safe_to_call']
                                    df.at[idx, 'line_type'] = dnc_result['line_type']
                                    df.at[idx, 'dnc_checked_date'] = dnc_result['checked_date']
                            else:
                                df.at[idx, 'skip_traced'] = True  # Mark as attempted
                                df.at[idx, 'skip_trace_confidence'] = 0.0

                            results.append({
                                'address': address,
                                'owner_name': owner_name,
                                'phone': result.primary_phone if result.success else None,
                                'email': result.primary_email if result.success else None,
                                'success': result.success
                            })

                        # Save updated DataFrame to both files for compatibility
                        df.to_csv(PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv', index=False)
                        df.to_csv(PROCESSED_DATA_DIR / 'all_leads_real.csv', index=False)

                        progress_bar.progress(100)
                        status_text.text("✅ Bulk skip trace complete!")

                        # Show results
                        with results_container:
                            st.markdown("---")
                            st.markdown("### 🎉 Bulk Skip Trace Results")

                            results_df = pd.DataFrame(results)
                            hit_rate = (success_count / total * 100) if total > 0 else 0

                            col1, col2, col3, col4 = st.columns(4)

                            with col1:
                                st.metric("Total Traced", total)
                            with col2:
                                st.metric("Found", success_count)
                            with col3:
                                st.metric("Hit Rate", f"{hit_rate:.0f}%")
                            with col4:
                                actual_cost = total * 0.20
                                st.metric("Approx Cost", f"${actual_cost:.2f}")

                            # Show successes
                            successful = results_df[results_df['success'] == True]
                            if len(successful) > 0:
                                st.markdown("#### ✅ Found Contact Info")
                                st.dataframe(
                                    successful[['address', 'owner_name', 'phone', 'email']],
                                    width='stretch',
                                    hide_index=True
                                )

                            # Download results
                            csv = results_df.to_csv(index=False).encode('utf-8')
                            st.download_button(
                                "📥 Download Bulk Trace Results",
                                csv,
                                "bulk_skip_trace_results.csv",
                                "text/csv"
                            )

                            st.success("✅ All results saved to leads file!")
                            st.balloons()

                    except Exception as e:
                        st.error(f"❌ Error: {e}")
                        import traceback
                        st.code(traceback.format_exc())

        st.markdown("---")

        # ========================================
        # MANUAL SELECTION SECTION
        # ========================================
        st.markdown("## 📋 Manual Selection")

        # Filter options
        col1, col2, col3 = st.columns(3)

        with col1:
            show_option = st.radio(
                "Show leads",
                ["Without Phone", "All Leads", "Without Email"],
                horizontal=True
            )

        with col2:
            min_score_filter = st.slider("Min Motivation Score", 0, 100, 60)

        with col3:
            tier_filter = st.multiselect("Tiers", [1, 2, 3, 4], default=[1, 2])

        # Filter DataFrame
        filtered_df = df[
            (df['motivation_score'] >= min_score_filter) &
            (df['tier'].isin(tier_filter))
        ]

        if show_option == "Without Phone":
            filtered_df = filtered_df[filtered_df['phone'].isna() | (filtered_df['phone'] == '')]
        elif show_option == "Without Email":
            filtered_df = filtered_df[filtered_df['email'].isna() | (filtered_df['email'] == '')]

        # Sort by motivation score
        filtered_df = filtered_df.sort_values('motivation_score', ascending=False)

        st.info(f"Found **{len(filtered_df)}** leads matching your criteria")

        if len(filtered_df) > 0:
            # Display leads with selection
            st.markdown("### Select Leads")

            # Create selection DataFrame
            display_cols = ['address', 'owner_name', 'motivation_score', 'tier', 'taxes_owed']
            if 'phone' in filtered_df.columns:
                display_cols.append('phone')

            # Use data editor for selection
            selection_df = filtered_df[display_cols].head(50).copy()
            selection_df.insert(0, 'Select', False)

            edited_df = st.data_editor(
                selection_df,
                hide_index=True,
                width='stretch',
                column_config={
                    "Select": st.column_config.CheckboxColumn(
                        "Select",
                        help="Select leads to skip trace",
                        default=False,
                    )
                },
                disabled=display_cols,
                key="skip_trace_selection"
            )

            # Get selected rows
            selected_rows = edited_df[edited_df['Select'] == True]
            num_selected = len(selected_rows)

            st.markdown("---")

            # Cost estimate and action buttons
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Selected Leads", num_selected)

            with col2:
                estimated_cost = num_selected * 0.20
                st.metric("Estimated Cost", f"${estimated_cost:.2f}")

            with col3:
                if num_selected > 0:
                    if st.button(f"📞 Skip Trace {num_selected} Lead(s)", type="primary"):
                        # Perform skip tracing
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                        results_container = st.container()

                        try:
                            tracer = SkipTracer(provider='batchdata', api_key=BATCHDATA_API_KEY)

                            results = []
                            for i, (idx, row) in enumerate(selected_rows.iterrows()):
                                status_text.text(f"Skip tracing {i+1}/{num_selected}: {row['address'][:30]}...")
                                progress_bar.progress((i + 1) / num_selected)

                                # Get the full row from original DataFrame
                                original_idx = filtered_df[filtered_df['address'] == row['address']].index[0]
                                original_row = df.loc[original_idx]

                                # Get zip code from the lead data
                                zip_code = str(original_row.get('zip_code', '')) if pd.notna(original_row.get('zip_code')) else ''

                                result = tracer.lookup(
                                    owner_name=str(row['owner_name']),
                                    address=str(row['address']),
                                    city='Columbus',
                                    state='OH',
                                    zip_code=zip_code
                                )

                                results.append({
                                    'address': row['address'],
                                    'owner_name': row['owner_name'],
                                    'phone': result.primary_phone,
                                    'phone_2': result.phones[1] if len(result.phones) > 1 else None,
                                    'email': result.primary_email,
                                    'email_2': result.emails[1] if len(result.emails) > 1 else None,
                                    'success': result.success,
                                    'confidence': result.confidence_score,
                                    'original_idx': original_idx
                                })

                                # Update the main DataFrame
                                if result.success:
                                    df.at[original_idx, 'phone'] = result.primary_phone
                                    df.at[original_idx, 'email'] = result.primary_email
                                    if len(result.phones) > 1:
                                        df.at[original_idx, 'phone_2'] = result.phones[1]
                                    if len(result.emails) > 1:
                                        df.at[original_idx, 'email_2'] = result.emails[1]
                                    df.at[original_idx, 'skip_traced'] = True
                                    df.at[original_idx, 'skip_trace_confidence'] = result.confidence_score

                            # Save updated DataFrame to both files for compatibility
                            df.to_csv(PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv', index=False)
                            df.to_csv(PROCESSED_DATA_DIR / 'all_leads_real.csv', index=False)

                            progress_bar.progress(100)
                            status_text.text("✅ Skip tracing complete!")

                            # Show results
                            with results_container:
                                st.markdown("### 📊 Skip Trace Results")

                                results_df = pd.DataFrame(results)
                                success_count = results_df['success'].sum()

                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Total Traced", num_selected)
                                with col2:
                                    st.metric("Found Contacts", success_count)
                                with col3:
                                    hit_rate = (success_count / num_selected * 100) if num_selected > 0 else 0
                                    st.metric("Hit Rate", f"{hit_rate:.0f}%")

                                # Show results table
                                st.dataframe(
                                    results_df[['address', 'owner_name', 'phone', 'email', 'success', 'confidence']],
                                    width='stretch',
                                    column_config={
                                        'success': st.column_config.CheckboxColumn('Found'),
                                        'confidence': st.column_config.ProgressColumn('Confidence', min_value=0, max_value=1)
                                    }
                                )

                                st.success("✅ Results saved to CSV file!")

                                # Download results
                                csv = results_df.to_csv(index=False).encode('utf-8')
                                st.download_button(
                                    "📥 Download Skip Trace Results",
                                    csv,
                                    "skip_trace_results.csv",
                                    "text/csv"
                                )

                        except Exception as e:
                            st.error(f"❌ Error: {e}")
                            import traceback
                            st.code(traceback.format_exc())
                else:
                    st.button("📞 Skip Trace Selected", disabled=True, help="Select at least one lead")

        # Quick single lookup section
        st.markdown("---")
        st.markdown("## 🔍 Quick Single Lookup")

        col1, col2 = st.columns(2)

        with col1:
            quick_name = st.text_input("Owner Name", placeholder="e.g., SMITH JOHN")

        with col2:
            quick_address = st.text_input("Address", placeholder="e.g., 123 MAIN ST, Columbus, OH 43215")

        if st.button("🔍 Look Up Contact Info"):
            if quick_name and quick_address:
                with st.spinner("Skip tracing..."):
                    try:
                        tracer = SkipTracer(provider='batchdata', api_key=BATCHDATA_API_KEY)
                        result = tracer.lookup(owner_name=quick_name, address=quick_address)

                        if result.success:
                            st.success("✅ Contact Found!")

                            col1, col2 = st.columns(2)
                            with col1:
                                st.markdown("**📞 Phone Numbers**")
                                for i, phone in enumerate(result.phones, 1):
                                    st.write(f"{i}. {phone}")

                            with col2:
                                st.markdown("**📧 Emails**")
                                if result.emails:
                                    for i, email in enumerate(result.emails, 1):
                                        st.write(f"{i}. {email}")
                                else:
                                    st.write("No emails found")

                            st.metric("Confidence Score", f"{result.confidence_score:.0%}")
                        else:
                            st.warning(f"No contact info found: {result.error_message}")

                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                st.warning("Please enter both owner name and address")


# ========================================
# DNC SCRUB PAGE
# ========================================
elif page == "🛡️ DNC Scrub":
    st.markdown('<h1 class="main-header">🛡️ DNC Compliance Checker</h1>', unsafe_allow_html=True)
    st.markdown("### Protect Yourself from TCPA Lawsuits")

    st.info("""
    **Why DNC Scrubbing Matters:**
    - Calling numbers on the National Do Not Call Registry = **$500 - $46,000 fines PER CALL**
    - Wireless numbers have stricter rules (no autodialers without written consent)
    - Known TCPA litigators actively sue cold callers
    """)

    # Load leads
    all_leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
    if not all_leads_file.exists():
        all_leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

    if not all_leads_file.exists():
        st.warning("⚠️ No leads found. Generate leads first!")
    else:
        df = pd.read_csv(all_leads_file)

        # Check current DNC status
        has_phones = df['phone'].notna().sum() if 'phone' in df.columns else 0
        already_checked = df['dnc_status'].notna().sum() if 'dnc_status' in df.columns else 0

        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Leads", len(df))
        with col2:
            st.metric("With Phone Numbers", has_phones)
        with col3:
            st.metric("DNC Checked", already_checked)
        with col4:
            if 'safe_to_call' in df.columns:
                safe_count = df['safe_to_call'].sum()
                st.metric("Safe to Call", int(safe_count))
            else:
                st.metric("Safe to Call", "Not checked")

        st.markdown("---")

        # DNC Check Options
        st.markdown("## 🔍 Run DNC Check")

        col1, col2 = st.columns(2)

        with col1:
            check_option = st.radio(
                "Check which leads?",
                ["All leads with phone numbers", "Only unchecked leads", "Selected leads"],
                key="dnc_check_option"
            )

        with col2:
            st.markdown("**What gets checked:**")
            st.markdown("- Phone number validation")
            st.markdown("- Line type (landline vs wireless)")
            st.markdown("- Local DNC list matching")
            st.markdown("- Known litigator detection")

        if st.button("🛡️ Run DNC Check", type="primary"):
            with st.spinner("Checking phone numbers..."):
                try:
                    checker = DNCChecker()

                    # Filter based on selection
                    if check_option == "All leads with phone numbers":
                        to_check = df[df['phone'].notna()].copy()
                    elif check_option == "Only unchecked leads":
                        if 'dnc_status' in df.columns:
                            to_check = df[(df['phone'].notna()) & (df['dnc_status'].isna())].copy()
                        else:
                            to_check = df[df['phone'].notna()].copy()
                    else:
                        to_check = df[df['phone'].notna()].copy()

                    if len(to_check) == 0:
                        st.warning("No leads with phone numbers to check")
                    else:
                        # Progress bar
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        total = len(to_check)
                        results = []

                        for i, (idx, row) in enumerate(to_check.iterrows()):
                            phone = str(row['phone'])
                            status_text.text(f"Checking {i+1}/{total}: {phone}")
                            progress_bar.progress((i + 1) / total)

                            result = checker.check_dnc(phone)

                            # Update main DataFrame
                            df.at[idx, 'dnc_status'] = result['dnc_status']
                            df.at[idx, 'safe_to_call'] = result['safe_to_call']
                            df.at[idx, 'dnc_risk_level'] = result['risk_level']
                            df.at[idx, 'line_type'] = result['line_type']
                            df.at[idx, 'dnc_warnings'] = '; '.join(result['warnings'])
                            df.at[idx, 'dnc_checked_date'] = result['checked_date']

                            results.append({
                                'phone': phone,
                                'status': result['dnc_status'],
                                'safe': result['safe_to_call'],
                                'line_type': result['line_type'],
                                'risk': result['risk_level']
                            })

                        # Save updated DataFrame to both files for compatibility
                        df.to_csv(PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv', index=False)
                        df.to_csv(PROCESSED_DATA_DIR / 'all_leads_real.csv', index=False)

                        progress_bar.progress(100)
                        status_text.text("✅ DNC check complete!")

                        # Show results summary
                        results_df = pd.DataFrame(results)

                        st.markdown("### Results Summary")

                        col1, col2, col3, col4, col5 = st.columns(5)

                        safe_count = results_df['safe'].sum()
                        on_dnc = (results_df['status'] == 'ON_DNC').sum()
                        wireless = (results_df['status'] == 'WIRELESS').sum()
                        invalid = (results_df['status'] == 'INVALID').sum()
                        litigator = (results_df['status'] == 'LITIGATOR').sum()

                        with col1:
                            st.metric("Checked", len(results_df))
                        with col2:
                            st.metric("✅ Safe to Call", int(safe_count))
                        with col3:
                            st.metric("🚫 On DNC", int(on_dnc))
                        with col4:
                            st.metric("📱 Wireless", int(wireless))
                        with col5:
                            st.metric("⚠️ Invalid", int(invalid))

                        if litigator > 0:
                            st.error(f"🚨 ALERT: {litigator} known TCPA litigator(s) detected! DO NOT CALL these numbers.")

                        if on_dnc > 0:
                            st.warning(f"⚠️ {on_dnc} numbers are on the Do Not Call registry. Remove from calling list.")

                        # Show detailed results
                        st.markdown("### Detailed Results")
                        st.dataframe(
                            results_df,
                            width='stretch',
                            hide_index=True,
                            column_config={
                                'safe': st.column_config.CheckboxColumn('Safe to Call')
                            }
                        )

                except Exception as e:
                    st.error(f"Error: {e}")
                    import traceback
                    st.code(traceback.format_exc())

        st.markdown("---")

        # Compliance Report
        st.markdown("## 📊 Compliance Report")

        if 'dnc_status' in df.columns and df['dnc_status'].notna().any():
            checker = DNCChecker()
            report = checker.generate_compliance_report(df)

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("### Statistics")
                st.write(f"**Total Leads:** {report['total_leads']}")
                st.write(f"**With Phone:** {report['with_phone']}")
                st.write(f"**Safe to Call:** {report['safe_to_call']}")
                st.write(f"**On DNC Registry:** {report['on_dnc']}")
                st.write(f"**Wireless (Restricted):** {report['wireless']}")
                st.write(f"**Invalid Numbers:** {report['invalid']}")
                st.write(f"**Known Litigators:** {report['litigators']}")

                # Compliance score gauge
                score = report['compliance_score']
                if score >= 80:
                    st.success(f"✅ Compliance Score: {score}%")
                elif score >= 50:
                    st.warning(f"⚠️ Compliance Score: {score}%")
                else:
                    st.error(f"🚨 Compliance Score: {score}%")

            with col2:
                st.markdown("### Recommendations")
                if report['recommendations']:
                    for rec in report['recommendations']:
                        if 'URGENT' in rec or 'litigator' in rec.lower():
                            st.error(f"🚨 {rec}")
                        elif 'DNC' in rec:
                            st.warning(f"⚠️ {rec}")
                        else:
                            st.info(f"💡 {rec}")
                else:
                    st.success("✅ No compliance issues detected!")

            # Download safe calling list
            st.markdown("---")
            st.markdown("### 📥 Download Safe Calling List")

            safe_df = df[df['safe_to_call'] == True] if 'safe_to_call' in df.columns else df

            if len(safe_df) > 0:
                # Select relevant columns
                export_cols = ['address', 'owner_name', 'phone', 'email', 'motivation_score',
                              'tier', 'dnc_status', 'line_type', 'safe_to_call']
                export_cols = [c for c in export_cols if c in safe_df.columns]

                csv = safe_df[export_cols].to_csv(index=False).encode('utf-8')
                st.download_button(
                    f"📥 Download {len(safe_df)} Safe-to-Call Leads",
                    csv,
                    "safe_to_call_leads.csv",
                    "text/csv"
                )
            else:
                st.warning("No safe-to-call leads available")

        else:
            st.info("Run DNC check first to see compliance report")

        # Internal DNC List Management
        st.markdown("---")
        st.markdown("## 📝 Internal DNC List (Opt-Outs)")
        st.markdown("Add numbers that have requested not to be called")

        col1, col2 = st.columns(2)

        with col1:
            opt_out_phone = st.text_input("Phone Number", placeholder="(614) 555-1234")

        with col2:
            opt_out_reason = st.selectbox("Reason", ["Opt-out request", "Wrong number", "Hostile response", "Other"])

        if st.button("➕ Add to Internal DNC"):
            if opt_out_phone:
                checker = DNCChecker()
                checker.add_internal_dnc(opt_out_phone, opt_out_reason)
                st.success(f"✅ Added {opt_out_phone} to internal DNC list")
            else:
                st.warning("Enter a phone number")

        # Show internal DNC list
        internal_dnc_file = DATA_DIR / 'dnc' / 'internal_dnc.csv'
        if internal_dnc_file.exists():
            internal_df = pd.read_csv(internal_dnc_file)
            st.markdown(f"**Internal DNC List:** {len(internal_df)} numbers")
            with st.expander("View Internal DNC List"):
                st.dataframe(internal_df, width='stretch', hide_index=True)


# ========================================
# CALL TRACKER PAGE
# ========================================
elif page == "☎️ Call Tracker":
    st.markdown('<h1 class="main-header">☎️ Cold Calling Tracker</h1>', unsafe_allow_html=True)

    # Initialize tracker
    tracker = CallTracker()

    # Top metrics row
    col1, col2, col3, col4, col5 = st.columns(5)

    today_stats = tracker.get_todays_stats()
    week_stats = tracker.get_weekly_stats()

    with col1:
        st.metric("Today's Calls", today_stats['total_calls'])
    with col2:
        st.metric("Conversations", today_stats['conversations'])
    with col3:
        st.metric("Interested", today_stats['interested'])
    with col4:
        st.metric("Appointments", today_stats['appointments'])
    with col5:
        follow_ups = tracker.get_follow_ups_due(days_ahead=1)
        st.metric("Follow-Ups Due", len(follow_ups))

    st.markdown("---")

    # Tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["📞 Log Call", "📋 Follow-Ups", "🎯 Pipeline", "📊 History"])

    with tab1:
        st.markdown("### Log a New Call")

        col1, col2 = st.columns(2)

        with col1:
            # Option to select from existing leads or enter manually
            input_method = st.radio("Lead Source", ["Select from leads", "Enter manually"], horizontal=True)

            if input_method == "Select from leads":
                # Load leads
                leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
                if not leads_file.exists():
                    leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

                if leads_file.exists():
                    leads_df = pd.read_csv(leads_file)
                    # Create display options
                    lead_options = leads_df.apply(
                        lambda x: f"{x['address']} - {x['owner_name']}", axis=1
                    ).tolist()

                    selected_lead = st.selectbox("Select Lead", [""] + lead_options[:200])

                    if selected_lead:
                        selected_idx = lead_options.index(selected_lead)
                        lead_row = leads_df.iloc[selected_idx]
                        call_address = lead_row['address']
                        call_owner = lead_row['owner_name']
                        call_phone = str(lead_row.get('phone', '')) if pd.notna(lead_row.get('phone')) else ''
                    else:
                        call_address = ""
                        call_owner = ""
                        call_phone = ""
                else:
                    st.warning("No leads file found. Generate leads first.")
                    call_address = st.text_input("Address")
                    call_owner = st.text_input("Owner Name")
                    call_phone = st.text_input("Phone Number")
            else:
                call_address = st.text_input("Address")
                call_owner = st.text_input("Owner Name")
                call_phone = st.text_input("Phone Number")

        with col2:
            call_outcome = st.selectbox("Call Outcome", CallTracker.OUTCOMES)
            call_notes = st.text_area("Notes", height=100, placeholder="What did you discuss?")

            # Follow-up section
            needs_follow_up = st.checkbox("Schedule Follow-Up")
            if needs_follow_up:
                follow_up_col1, follow_up_col2 = st.columns(2)
                with follow_up_col1:
                    follow_up_date = st.date_input("Follow-Up Date")
                with follow_up_col2:
                    follow_up_notes = st.text_input("Follow-Up Note", placeholder="e.g., Call after 5pm")
            else:
                follow_up_date = None
                follow_up_notes = ""

        if st.button("📞 Log Call", type="primary", disabled=not call_address):
            if call_address and call_outcome:
                result = tracker.log_call(
                    address=call_address,
                    owner_name=call_owner,
                    phone=call_phone,
                    outcome=call_outcome,
                    notes=call_notes,
                    follow_up_date=str(follow_up_date) if follow_up_date else None,
                    follow_up_notes=follow_up_notes if needs_follow_up else ''
                )
                st.success(f"✅ Call logged! Status: {result['new_status']}")
                st.balloons()
            else:
                st.error("Please enter address and outcome")

    with tab2:
        st.markdown("### Follow-Ups Due")

        # Get follow-ups
        follow_ups_today = tracker.get_follow_ups_due(days_ahead=0)
        follow_ups_week = tracker.get_follow_ups_due(days_ahead=7)

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Due Today", len(follow_ups_today))
        with col2:
            st.metric("Due This Week", len(follow_ups_week))

        if not follow_ups_week.empty:
            st.markdown("#### Upcoming Follow-Ups")

            display_cols = ['address', 'owner_name', 'phone', 'status', 'next_follow_up', 'follow_up_notes']
            available_cols = [c for c in display_cols if c in follow_ups_week.columns]

            st.dataframe(
                follow_ups_week[available_cols],
                width='stretch',
                hide_index=True
            )
        else:
            st.info("No follow-ups scheduled. Log some calls to get started!")

    with tab3:
        st.markdown("### Lead Pipeline")

        pipeline = tracker.get_pipeline_summary()

        # Pipeline visualization
        pipeline_order = ['New Lead', 'Contacted', 'Follow Up', 'Interested', 'Hot Lead',
                         'Appointment', 'Offer Made', 'Under Contract', 'Closed', 'Dead Lead']

        # Create columns for pipeline stages
        active_stages = [s for s in pipeline_order if pipeline.get(s, 0) > 0 or s in ['New Lead', 'Interested', 'Appointment', 'Closed']]

        if active_stages:
            cols = st.columns(len(active_stages))
            for i, stage in enumerate(active_stages):
                with cols[i]:
                    count = pipeline.get(stage, 0)
                    color = "🟢" if stage in ['Interested', 'Hot Lead', 'Appointment'] else "🔵" if stage in ['Closed', 'Under Contract'] else "⚪"
                    st.metric(f"{color} {stage}", count)

        st.markdown("---")

        # Show leads by status
        status_filter = st.selectbox("View Leads by Status", ['All'] + CallTracker.STATUSES)

        if status_filter == 'All':
            all_leads = tracker.get_all_leads()
        else:
            all_leads = tracker.get_leads_by_status(status_filter)

        if not all_leads.empty:
            display_cols = ['address', 'owner_name', 'phone', 'status', 'total_calls', 'last_outcome', 'priority']
            available_cols = [c for c in display_cols if c in all_leads.columns]

            st.dataframe(
                all_leads[available_cols].sort_values('priority'),
                width='stretch',
                hide_index=True
            )
        else:
            st.info("No leads in tracker yet. Log some calls to get started!")

    with tab4:
        st.markdown("### Call History")

        # Weekly stats
        st.markdown("#### This Week's Performance")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Calls", week_stats['total_calls'])
        with col2:
            st.metric("Conversations", week_stats['conversations'])
        with col3:
            st.metric("Interested Leads", week_stats['interested'])
        with col4:
            st.metric("Conversion Rate", f"{week_stats['conversion_rate']}%")

        st.markdown("---")
        st.markdown("#### Recent Calls")

        calls_df = tracker.get_all_calls(limit=50)

        if not calls_df.empty:
            display_cols = ['call_date', 'call_time', 'address', 'owner_name', 'outcome', 'notes']
            available_cols = [c for c in display_cols if c in calls_df.columns]

            st.dataframe(
                calls_df[available_cols],
                width='stretch',
                hide_index=True
            )
        else:
            st.info("No calls logged yet. Start calling and log your results!")

    # Import leads section
    st.markdown("---")
    st.markdown("### Import Leads to Tracker")

    col1, col2 = st.columns([3, 1])
    with col1:
        import_count = st.slider("Number of leads to import", 10, 100, 50)
    with col2:
        if st.button("📥 Import Top Leads"):
            leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
            if not leads_file.exists():
                leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

            if leads_file.exists():
                main_df = pd.read_csv(leads_file)
                # Sort by motivation score and import top leads
                main_df = main_df.sort_values('motivation_score', ascending=False)
                imported = tracker.import_leads_from_main(main_df, limit=import_count)
                st.success(f"✅ Imported {imported} leads to tracker!")
            else:
                st.error("No leads file found. Generate leads first.")


# ========================================
# VA MANAGEMENT PAGE
# ========================================
elif page == "👥 VA Management":
    st.markdown('<h1 class="main-header">👥 VA Management</h1>', unsafe_allow_html=True)

    # Initialize VA Manager
    va_manager = VAManager()

    # Check if user is admin (simple session state for demo)
    if 'va_authenticated' not in st.session_state:
        st.session_state.va_authenticated = False
        st.session_state.va_user = None

    # Admin login
    if not st.session_state.va_authenticated:
        st.markdown("### 🔐 Admin Login")
        st.info("Default credentials: admin / admin123")

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")

            if st.button("🔑 Login", use_container_width=True):
                user = va_manager.authenticate(username, password)
                if user and user['role'] == 'admin':
                    st.session_state.va_authenticated = True
                    st.session_state.va_user = user
                    st.success(f"✅ Welcome, {user['name']}!")
                    st.rerun()
                elif user:
                    st.error("❌ Access denied. Admin privileges required.")
                else:
                    st.error("❌ Invalid credentials")
    else:
        # Logout button
        col1, col2 = st.columns([6, 1])
        with col2:
            if st.button("🚪 Logout"):
                st.session_state.va_authenticated = False
                st.session_state.va_user = None
                st.rerun()

        # VA Management Tabs
        tab1, tab2, tab3, tab4 = st.tabs(["👤 Manage VAs", "📋 Assign Leads", "📊 Performance", "👁️ Team Overview"])

        # TAB 1: Manage VAs
        with tab1:
            st.markdown("### 👤 Virtual Assistant Management")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### ➕ Add New VA")
                with st.form("add_va_form"):
                    new_username = st.text_input("Username*")
                    new_password = st.text_input("Password*", type="password")
                    new_name = st.text_input("Full Name*")
                    new_email = st.text_input("Email")
                    new_quota = st.number_input("Daily Call Quota", min_value=10, max_value=200, value=50)

                    if st.form_submit_button("➕ Add VA", use_container_width=True):
                        if new_username and new_password and new_name:
                            user_id = va_manager.add_user(
                                username=new_username,
                                password=new_password,
                                name=new_name,
                                email=new_email,
                                role='va',
                                daily_quota=new_quota
                            )
                            if user_id:
                                st.success(f"✅ Added VA: {new_name}")
                                st.rerun()
                            else:
                                st.error("❌ Username already exists")
                        else:
                            st.warning("⚠️ Please fill required fields")

            with col2:
                st.markdown("#### 📋 Current VAs")
                vas_df = va_manager.get_all_vas()

                if not vas_df.empty:
                    for _, va in vas_df.iterrows():
                        with st.container():
                            st.markdown(f"""
                            **{va['name']}** (@{va['username']})
                            📧 {va['email'] if va['email'] else 'No email'}
                            📊 Quota: {va['daily_quota']} calls/day
                            ✅ Active: {'Yes' if va['is_active'] else 'No'}
                            """)

                            col_a, col_b = st.columns(2)
                            with col_a:
                                if st.button(f"{'🔴 Deactivate' if va['is_active'] else '🟢 Activate'}", key=f"toggle_{va['user_id']}"):
                                    va_manager.update_user(va['user_id'], is_active=not va['is_active'])
                                    st.rerun()
                            with col_b:
                                if st.button("🗑️ Remove", key=f"remove_{va['user_id']}"):
                                    va_manager.remove_user(va['user_id'])
                                    st.rerun()
                            st.markdown("---")
                else:
                    st.info("No VAs added yet. Add your first VA!")

        # TAB 2: Assign Leads
        with tab2:
            st.markdown("### 📋 Lead Assignment")

            vas_df = va_manager.get_all_vas()

            if vas_df.empty:
                st.warning("⚠️ No VAs available. Add VAs first!")
            else:
                # Lead Source Selection
                st.markdown("#### 📁 Select Lead Source")
                lead_source = st.radio(
                    "Lead Type",
                    ["🏦 Delinquent Tax", "⚖️ Probate", "🏠 Sheriff Sales", "📊 All Sources"],
                    horizontal=True
                )

                # Load leads based on source
                leads_df = None
                source_name = ""

                if lead_source == "🏦 Delinquent Tax":
                    # Check for batches
                    batches_dir = PROCESSED_DATA_DIR / 'batches'
                    batch_files = []
                    if batches_dir.exists():
                        batch_files = sorted(batches_dir.glob('batch_*_*.csv'), reverse=True)
                        batch_files = [f for f in batch_files if '_tier_' not in f.name]

                    if batch_files:
                        batch_options = ["📋 Latest (Main File)"] + [f.name for f in batch_files]
                        selected_batch = st.selectbox("Select Batch", batch_options, key="assign_batch")

                        if selected_batch == "📋 Latest (Main File)":
                            file_path = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
                        else:
                            file_path = batches_dir / selected_batch
                    else:
                        file_path = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'

                    if file_path.exists():
                        leads_df = pd.read_csv(file_path)
                        source_name = f"Delinquent Tax ({file_path.name})"
                elif lead_source == "⚖️ Probate":
                    file_path = PROCESSED_DATA_DIR / 'probate_leads.csv'
                    if file_path.exists():
                        leads_df = pd.read_csv(file_path)
                        # Normalize column names for probate
                        if 'property_address' in leads_df.columns:
                            leads_df['address'] = leads_df['property_address']
                        if 'decedent_name' in leads_df.columns:
                            leads_df['owner_name'] = leads_df['decedent_name']
                        if 'motivation_score' not in leads_df.columns:
                            leads_df['motivation_score'] = 75  # Default score for probate
                        source_name = "Probate"
                elif lead_source == "🏠 Sheriff Sales":
                    file_path = PROCESSED_DATA_DIR / 'sheriff_sale_leads.csv'
                    if file_path.exists():
                        leads_df = pd.read_csv(file_path)
                        if 'motivation_score' not in leads_df.columns:
                            leads_df['motivation_score'] = 80  # Default score for sheriff sales
                        source_name = "Sheriff Sales"
                else:  # All Sources
                    all_dfs = []
                    # Delinquent
                    f1 = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
                    if f1.exists():
                        df1 = pd.read_csv(f1)
                        df1['lead_source'] = 'Delinquent Tax'
                        all_dfs.append(df1[['address', 'owner_name', 'phone', 'motivation_score', 'lead_source']])
                    # Probate
                    f2 = PROCESSED_DATA_DIR / 'probate_leads.csv'
                    if f2.exists():
                        df2 = pd.read_csv(f2)
                        if 'property_address' in df2.columns:
                            df2['address'] = df2['property_address']
                        if 'decedent_name' in df2.columns:
                            df2['owner_name'] = df2['decedent_name']
                        df2['motivation_score'] = 75
                        df2['lead_source'] = 'Probate'
                        all_dfs.append(df2[['address', 'owner_name', 'phone', 'motivation_score', 'lead_source']])
                    # Sheriff
                    f3 = PROCESSED_DATA_DIR / 'sheriff_sale_leads.csv'
                    if f3.exists():
                        df3 = pd.read_csv(f3)
                        df3['motivation_score'] = 80
                        df3['lead_source'] = 'Sheriff Sale'
                        all_dfs.append(df3[['address', 'owner_name', 'phone', 'motivation_score', 'lead_source']])
                    if all_dfs:
                        leads_df = pd.concat(all_dfs, ignore_index=True)
                    source_name = "All Sources"

                if leads_df is None or leads_df.empty:
                    st.warning(f"⚠️ No {source_name} leads found. Generate leads first!")
                else:
                    # Filter to only leads with phone numbers
                    leads_with_phone = leads_df[leads_df['phone'].notna() & (leads_df['phone'] != '')]
                    st.success(f"📊 **{len(leads_with_phone)}** leads with phone numbers available from {source_name}")

                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("#### 🎯 Assign to VA")

                        # Select VA
                        va_options = {f"{row['name']} (@{row['username']})": row['user_id'] for _, row in vas_df.iterrows()}
                        selected_va_name = st.selectbox("Select VA", list(va_options.keys()))
                        selected_va_id = va_options[selected_va_name]

                        # Number of leads
                        max_leads = min(len(leads_with_phone), 100)
                        num_leads = st.slider("Number of leads to assign", 5, max(5, max_leads), min(25, max_leads))

                        # Priority
                        priority = st.select_slider("Priority", options=[1, 2, 3, 4, 5], value=3,
                                                   format_func=lambda x: {1: "🔴 Urgent", 2: "🟠 High", 3: "🟡 Normal", 4: "🟢 Low", 5: "⚪ Lowest"}[x])

                        if st.button("📋 Assign Leads", type="primary", use_container_width=True):
                            # Get leads with phone numbers
                            to_assign = leads_with_phone.head(num_leads).copy()
                            if len(to_assign) > 0:
                                count = va_manager.assign_leads(
                                    to_assign,
                                    selected_va_id,
                                    assigned_by='admin',
                                    priority=priority
                                )
                                st.success(f"✅ Assigned **{count}** leads to {selected_va_name}!")
                                st.balloons()
                            else:
                                st.warning("No leads to assign")

                    with col2:
                        st.markdown("#### 👀 Preview Leads")
                        preview = leads_with_phone.head(10)[['address', 'owner_name', 'phone']].copy()
                        preview.columns = ['Address', 'Owner', 'Phone']
                        st.dataframe(preview, use_container_width=True, hide_index=True)

                    st.markdown("---")

                    # Auto-Distribution
                    st.markdown("#### 🔄 Auto-Distribution (Split Among All VAs)")
                    col_a, col_b, col_c = st.columns(3)

                    with col_a:
                        distribution_method = st.radio(
                            "Method",
                            ["equal", "by_quota"],
                            format_func=lambda x: {"equal": "📊 Equal Split", "by_quota": "📈 By Quota"}[x]
                        )
                    with col_b:
                        auto_num_leads = st.slider("Total leads", 10, min(200, len(leads_with_phone)), min(50, len(leads_with_phone)), key="auto_leads")
                    with col_c:
                        if st.button("🔄 Auto-Distribute", type="primary", use_container_width=True):
                            to_distribute = leads_with_phone.head(auto_num_leads)
                            if len(to_distribute) > 0:
                                result = va_manager.auto_distribute_leads(to_distribute, distribution=distribution_method)
                                st.success("✅ Leads distributed!")
                                for va_name, count in result.items():
                                    st.write(f"• **{va_name}**: {count} leads")
                            else:
                                st.warning("No leads to distribute")

        # TAB 3: Performance
        with tab3:
            st.markdown("### 📊 VA Performance")

            vas_df = va_manager.get_all_vas()

            if not vas_df.empty:
                # Select VA to view
                va_options = {"All VAs": None}
                va_options.update({f"{row['name']}": row['user_id'] for _, row in vas_df.iterrows()})

                col1, col2 = st.columns([2, 1])
                with col1:
                    selected_va = st.selectbox("Select VA", list(va_options.keys()), key="perf_va")
                with col2:
                    days = st.selectbox("Time Period", [7, 14, 30], format_func=lambda x: f"Last {x} days")

                if selected_va == "All VAs":
                    # Show all VA performance
                    perf_df = va_manager.get_all_va_performance(days=days)

                    if not perf_df.empty:
                        st.markdown("#### 📈 Team Performance")

                        # Ensure columns exist with defaults (using VAManager's column names)
                        if 'total_calls' not in perf_df.columns:
                            perf_df['total_calls'] = 0
                        if 'conversations' not in perf_df.columns:
                            perf_df['conversations'] = 0
                        if 'appointments' not in perf_df.columns:
                            perf_df['appointments'] = 0
                        if 'conversion_rate' not in perf_df.columns:
                            perf_df['conversion_rate'] = 0.0
                        if 'calls_per_day' not in perf_df.columns:
                            perf_df['calls_per_day'] = 0.0

                        # Metrics row
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Total Calls", int(perf_df['total_calls'].sum()))
                        with col2:
                            st.metric("Total Contacts", int(perf_df['conversations'].sum()))
                        with col3:
                            st.metric("Appointments", int(perf_df['appointments'].sum()))
                        with col4:
                            avg_rate = perf_df['conversion_rate'].mean() if len(perf_df) > 0 else 0
                            st.metric("Avg Conversion", f"{avg_rate:.1f}%")

                        # Performance table
                        st.markdown("#### 👥 Individual Performance")
                        display_df = perf_df[['name', 'total_calls', 'conversations', 'appointments', 'conversion_rate', 'calls_per_day']].copy()
                        display_df.columns = ['VA Name', 'Calls', 'Contacts', 'Appointments', 'Conv. Rate %', 'Calls/Day']
                        st.dataframe(display_df, use_container_width=True, hide_index=True)

                        # Chart
                        fig = px.bar(perf_df, x='name', y='total_calls',
                                    color='conversion_rate',
                                    title="Calls Made by VA (colored by conversion rate)",
                                    color_continuous_scale='RdYlGn')
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No performance data yet")
                else:
                    # Individual VA performance
                    va_id = va_options[selected_va]
                    perf = va_manager.get_va_performance(va_id, days=days)
                    progress = va_manager.get_va_today_progress(va_id)

                    st.markdown(f"#### 📊 {selected_va}'s Performance")

                    # Today's progress
                    st.markdown("##### Today's Progress")
                    progress_pct = (progress['calls'] / progress['quota'] * 100) if progress['quota'] > 0 else 0
                    st.progress(min(progress_pct / 100, 1.0))
                    st.write(f"**{progress['calls']}** / {progress['quota']} calls ({progress_pct:.0f}%)")

                    # Period stats
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Calls Made", perf.get('total_calls', 0))
                    with col2:
                        st.metric("Contacts", perf.get('conversations', 0))
                    with col3:
                        st.metric("Appointments", perf.get('appointments', 0))
                    with col4:
                        st.metric("Conversion", f"{perf.get('conversion_rate', 0):.1f}%")
            else:
                st.info("No VAs added yet")

        # TAB 4: Team Overview
        with tab4:
            st.markdown("### 👁️ Team Overview")

            vas_df = va_manager.get_all_vas()

            if not vas_df.empty:
                # Today's snapshot
                st.markdown("#### 📅 Today's Activity")

                cols = st.columns(len(vas_df))
                for idx, (_, va) in enumerate(vas_df.iterrows()):
                    with cols[idx]:
                        progress = va_manager.get_va_today_progress(va['user_id'])
                        progress_pct = (progress['calls'] / progress['quota'] * 100) if progress['quota'] > 0 else 0

                        st.markdown(f"**{va['name']}**")
                        st.progress(min(progress_pct / 100, 1.0))
                        st.caption(f"{progress['calls']}/{progress['quota']} calls")

                        # Status indicator
                        if progress_pct >= 100:
                            st.success("✅ Quota met!")
                        elif progress_pct >= 75:
                            st.info("🔵 On track")
                        elif progress_pct >= 50:
                            st.warning("🟡 Behind")
                        else:
                            st.error("🔴 Needs attention")

                # Assignment overview
                st.markdown("#### 📋 Current Assignments")

                for _, va in vas_df.iterrows():
                    assignments = va_manager.get_va_assignments(va['user_id'], status='pending')
                    in_progress = va_manager.get_va_assignments(va['user_id'], status='in_progress')
                    completed = va_manager.get_va_assignments(va['user_id'], status='completed')

                    with st.expander(f"📂 {va['name']} - {len(assignments)} pending, {len(in_progress)} in progress"):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Pending", len(assignments))
                        with col2:
                            st.metric("In Progress", len(in_progress))
                        with col3:
                            st.metric("Completed", len(completed))
            else:
                st.info("No VAs added yet. Add VAs in the 'Manage VAs' tab.")


# ========================================
# SEARCH OWNER PAGE
# ========================================
elif page == "🔍 Search Owner":
    st.markdown('<h1 class="main-header">🔍 Search by Owner Name</h1>', unsafe_allow_html=True)

    # Check if data exists
    all_leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

    if not all_leads_file.exists():
        st.warning("⚠️ No leads found. Generate leads first!")
        if st.button("Go to Generate Leads"):
            st.experimental_rerun()
    else:
        df = pd.read_csv(all_leads_file)

        st.markdown("### Enter Owner Name")

        col1, col2 = st.columns([4, 1])

        with col1:
            search_name = st.text_input(
                "Owner Name",
                placeholder="e.g., John Smith, Smith, JONES...",
                label_visibility="collapsed",
                key="owner_search_main"
            )

        with col2:
            exact_match = st.checkbox("Exact Match", value=False, key="exact_search")

        if search_name:
            # Perform search
            if exact_match:
                results = df[df['owner_name'].str.lower() == search_name.lower()]
            else:
                results = df[df['owner_name'].str.contains(search_name, case=False, na=False)]

            if len(results) == 0:
                st.warning(f"No results found for \"{search_name}\"")
                st.info("💡 Try a partial name or check spelling")
            else:
                st.success(f"Found {len(results)} result(s)")

                # Show results in a nice format
                for i, (idx, row) in enumerate(results.iterrows()):
                    with st.expander(f"**{row['owner_name']}** - {row['address']}", expanded=(i < 3)):
                        col1, col2, col3 = st.columns(3)

                        with col1:
                            st.markdown("**Property Details**")
                            st.write(f"📍 **Address:** {row['address']}")
                            st.write(f"👤 **Owner:** {row['owner_name']}")
                            if 'mailing_address' in row and pd.notna(row['mailing_address']):
                                st.write(f"📫 **Mailing:** {row['mailing_address']}")

                        with col2:
                            st.markdown("**Financial & Property Info**")
                            st.write(f"💰 **Taxes Owed:** ${row['taxes_owed']:,.0f}")
                            if 'years_delinquent' in row:
                                st.write(f"📅 **Years Delinquent:** {row['years_delinquent']}")
                            if 'assessed_value' in row and pd.notna(row['assessed_value']):
                                st.write(f"🏠 **Assessed Value:** ${row['assessed_value']:,.0f}")
                            if 'year_built' in row and pd.notna(row['year_built']) and row['year_built'] > 0:
                                st.write(f"🏗️ **Year Built:** {int(row['year_built'])}")
                            if 'square_feet' in row and pd.notna(row['square_feet']) and row['square_feet'] > 0:
                                st.write(f"📐 **Square Feet:** {int(row['square_feet']):,}")
                            if 'bedrooms' in row and pd.notna(row['bedrooms']) and row['bedrooms'] > 0:
                                beds = int(row['bedrooms'])
                                baths = row.get('bathrooms', 0)
                                st.write(f"🛏️ **Beds/Baths:** {beds} / {baths}")

                        with col3:
                            st.markdown("**Lead Score**")
                            score = int(row['motivation_score']) if 'motivation_score' in row else 0
                            tier = int(row['tier']) if 'tier' in row else 4

                            # Color-coded score
                            if score >= 80:
                                st.markdown(f"🎯 **Score:** :green[{score}/100]")
                            elif score >= 60:
                                st.markdown(f"🎯 **Score:** :orange[{score}/100]")
                            else:
                                st.markdown(f"🎯 **Score:** :red[{score}/100]")

                            st.write(f"⭐ **Tier:** {tier}")

                            if 'phone' in row and pd.notna(row['phone']):
                                st.write(f"📞 **Phone:** {row['phone']}")

                        if 'reasons' in row and pd.notna(row['reasons']):
                            st.markdown(f"**Motivation Factors:** {row['reasons']}")

                    # Limit display
                    if i >= 19:
                        st.info(f"Showing first 20 of {len(results)} results. Export to CSV for full list.")
                        break

                # Export option
                st.markdown("---")
                csv = results.to_csv(index=False).encode('utf-8')
                st.download_button(
                    f"📥 Download {len(results)} Results as CSV",
                    csv,
                    f"search_{search_name.replace(' ', '_')}.csv",
                    "text/csv"
                )

        else:
            st.info("👆 Enter an owner name above to search")

            # Show some stats
            st.markdown("---")
            st.markdown("### Quick Stats")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Owners", df['owner_name'].nunique())
            with col2:
                st.metric("Total Properties", len(df))
            with col3:
                st.metric("Avg Score", f"{df['motivation_score'].mean():.1f}")


# ========================================
# VIEW LEADS PAGE
# ========================================
elif page == "📊 View Leads":
    st.markdown('<h1 class="main-header">📊 View Leads</h1>', unsafe_allow_html=True)

    # Check for batches
    batches_dir = PROCESSED_DATA_DIR / 'batches'
    batch_files = []
    if batches_dir.exists():
        batch_files = sorted(batches_dir.glob('batch_*_*.csv'), reverse=True)
        # Filter out tier-specific files (only show main batch files)
        batch_files = [f for f in batch_files if '_tier_' not in f.name]

    # Batch selector
    if batch_files:
        st.markdown("### 📁 Select Batch")
        batch_options = ["📋 Latest (All Combined)"] + [f.name for f in batch_files]
        selected_batch = st.selectbox("Choose which batch to view:", batch_options)

        if selected_batch == "📋 Latest (All Combined)":
            all_leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
            if not all_leads_file.exists():
                all_leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'
        else:
            all_leads_file = batches_dir / selected_batch

        # Show batch summary
        st.markdown("#### 📊 Available Batches")
        batch_summary = []
        for bf in batch_files[:10]:  # Show last 10 batches
            try:
                batch_df = pd.read_csv(bf)
                batch_summary.append({
                    'Batch': bf.name,
                    'Leads': len(batch_df),
                    'Tier 1': len(batch_df[batch_df['tier'] == 1]) if 'tier' in batch_df.columns else 0,
                    'Tier 2': len(batch_df[batch_df['tier'] == 2]) if 'tier' in batch_df.columns else 0,
                    'Tier 3': len(batch_df[batch_df['tier'] == 3]) if 'tier' in batch_df.columns else 0,
                })
            except:
                pass
        if batch_summary:
            st.dataframe(pd.DataFrame(batch_summary), use_container_width=True, hide_index=True)
        st.markdown("---")
    else:
        # No batches yet, use legacy file
        all_leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
        if not all_leads_file.exists():
            all_leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

    if not all_leads_file.exists():
        st.warning("⚠️ No leads found. Generate leads first!")
        if st.button("Go to Generate Leads"):
            st.experimental_rerun()
    else:
        df = pd.read_csv(all_leads_file)

        # Filters - Row 1: Basic filters
        st.markdown("### Filters")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            tier_filter = st.multiselect(
                "Tier",
                options=[1, 2, 3, 4],
                default=[1, 2, 3]
            )

        with col2:
            min_score = st.slider("Min Score", 0, 100, 40)

        with col3:
            min_debt = st.number_input("Min Tax Debt ($)", value=0, step=1000)

        with col4:
            search_address = st.text_input("Search Address")

        # Filters - Row 2: Property characteristics
        st.markdown("#### Property Filters")
        col1, col2, col3, col4, col5 = st.columns(5)

        with col1:
            # Year Built filter
            if 'year_built' in df.columns:
                valid_years = df[df['year_built'] > 1800]['year_built']
                if not valid_years.empty:
                    min_year_default = int(valid_years.min())
                    max_year_default = int(valid_years.max())
                else:
                    min_year_default, max_year_default = 1900, 2024
                year_range = st.slider(
                    "Year Built",
                    min_value=1800,
                    max_value=2025,
                    value=(min_year_default, max_year_default),
                    help="Filter by year property was built"
                )
            else:
                year_range = (1800, 2025)

        with col2:
            # Years Delinquent filter
            if 'years_delinquent' in df.columns:
                max_years_del = int(df['years_delinquent'].max()) if df['years_delinquent'].max() > 0 else 10
                years_del_range = st.slider(
                    "Years Delinquent",
                    min_value=0,
                    max_value=max_years_del,
                    value=(0, max_years_del),
                    help="Filter by years behind on taxes"
                )
            else:
                years_del_range = (0, 10)

        with col3:
            # Bedrooms filter
            if 'bedrooms' in df.columns:
                max_beds = int(df['bedrooms'].max()) if df['bedrooms'].max() > 0 else 10
                min_bedrooms = st.number_input(
                    "Min Bedrooms",
                    min_value=0,
                    max_value=max_beds,
                    value=0,
                    help="Minimum number of bedrooms"
                )
            else:
                min_bedrooms = 0

        with col4:
            # Bathrooms filter
            if 'bathrooms' in df.columns:
                max_baths = float(df['bathrooms'].max()) if df['bathrooms'].max() > 0 else 10.0
                min_bathrooms = st.number_input(
                    "Min Bathrooms",
                    min_value=0.0,
                    max_value=float(max_baths),
                    value=0.0,
                    step=0.5,
                    help="Minimum number of bathrooms"
                )
            else:
                min_bathrooms = 0.0

        with col5:
            # Square Feet filter
            if 'square_feet' in df.columns:
                max_sqft = int(df['square_feet'].max()) if df['square_feet'].max() > 0 else 10000
                min_sqft = st.number_input(
                    "Min Sq Ft",
                    min_value=0,
                    max_value=max_sqft,
                    value=0,
                    step=100,
                    help="Minimum square footage"
                )
            else:
                min_sqft = 0

        # Equity and Freshness filters
        st.markdown("#### 💰 Equity & 📅 Freshness Filters")
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            if 'equity_tier' in df.columns:
                equity_filter = st.multiselect(
                    "Equity Tier",
                    options=['high', 'medium', 'low', 'underwater'],
                    default=['high', 'medium', 'low'],
                    help="Filter by estimated equity"
                )
            else:
                equity_filter = ['high', 'medium', 'low', 'underwater']
        with col2:
            if 'estimated_equity' in df.columns:
                min_equity = st.number_input(
                    "Min Equity ($)",
                    min_value=-100000,
                    value=0,
                    step=5000,
                    help="Minimum estimated equity"
                )
            else:
                min_equity = 0
        with col3:
            if 'freshness_tier' in df.columns:
                freshness_filter = st.multiselect(
                    "Freshness",
                    options=['fresh', 'recent', 'aging', 'stale'],
                    default=['fresh', 'recent', 'aging'],
                    help="Filter by data age"
                )
            else:
                freshness_filter = ['fresh', 'recent', 'aging', 'stale']
        with col4:
            if 'distress_increasing' in df.columns:
                increasing_only = st.checkbox("🔥 Increasing Distress", value=False, help="Show only leads with increasing distress")
            else:
                increasing_only = False
        # Owner type & violations filters
        col1, col2, col3 = st.columns(3)
        with col1:
            if 'is_whale' in df.columns:
                whale_only = st.checkbox("🐋 Whale Owners Only", value=False, help="Show only multi-property owners")
            else:
                whale_only = False
        with col2:
            if 'portfolio_size' in df.columns:
                min_portfolio = st.number_input("Min Properties Owned", min_value=1, value=1, help="Filter by portfolio size")
            else:
                min_portfolio = 1
        with col3:
            if 'total_violations' in df.columns:
                violations_only = st.checkbox("🚨 Has Code Violations", value=False, help="Show only properties with code violations")
            else:
                violations_only = False

        # Owner name search (prominent placement)
        st.markdown("### 🔍 Search by Owner Name")
        col_search1, col_search2 = st.columns([3, 1])
        with col_search1:
            search_owner = st.text_input(
                "Owner Name",
                placeholder="Enter owner name to search...",
                label_visibility="collapsed"
            )
        with col_search2:
            exact_match = st.checkbox("Exact match", value=False)

        # Apply filters - Basic
        filtered_df = df[
            (df['tier'].isin(tier_filter)) &
            (df['motivation_score'] >= min_score) &
            (df['taxes_owed'] >= min_debt)
        ]

        # Apply year built filter
        if 'year_built' in filtered_df.columns:
            filtered_df = filtered_df[
                ((filtered_df['year_built'] >= year_range[0]) & (filtered_df['year_built'] <= year_range[1])) |
                (filtered_df['year_built'] == 0)  # Include properties without year data
            ]

        # Apply years delinquent filter
        if 'years_delinquent' in filtered_df.columns:
            filtered_df = filtered_df[
                (filtered_df['years_delinquent'] >= years_del_range[0]) &
                (filtered_df['years_delinquent'] <= years_del_range[1])
            ]

        # Apply bedrooms filter
        if 'bedrooms' in filtered_df.columns and min_bedrooms > 0:
            filtered_df = filtered_df[filtered_df['bedrooms'] >= min_bedrooms]

        # Apply bathrooms filter
        if 'bathrooms' in filtered_df.columns and min_bathrooms > 0:
            filtered_df = filtered_df[filtered_df['bathrooms'] >= min_bathrooms]

        # Apply square feet filter
        if 'square_feet' in filtered_df.columns and min_sqft > 0:
            filtered_df = filtered_df[filtered_df['square_feet'] >= min_sqft]

        # Apply whale filter
        if whale_only and 'is_whale' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['is_whale'] == True]

        # Apply portfolio size filter
        if min_portfolio > 1 and 'portfolio_size' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['portfolio_size'] >= min_portfolio]

        # Apply violations filter
        if violations_only and 'total_violations' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['total_violations'] > 0]

        # Apply equity filters
        if 'equity_tier' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['equity_tier'].isin(equity_filter)]
        if 'estimated_equity' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['estimated_equity'] >= min_equity]

        # Apply freshness filters
        if 'freshness_tier' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['freshness_tier'].isin(freshness_filter)]
        if increasing_only and 'distress_increasing' in filtered_df.columns:
            filtered_df = filtered_df[filtered_df['distress_increasing'] == True]

        if search_address:
            filtered_df = filtered_df[filtered_df['address'].str.contains(search_address, case=False, na=False)]

        # Apply owner name search
        if search_owner:
            if exact_match:
                filtered_df = filtered_df[filtered_df['owner_name'].str.lower() == search_owner.lower()]
            else:
                filtered_df = filtered_df[filtered_df['owner_name'].str.contains(search_owner, case=False, na=False)]

        st.markdown(f"### Results: {len(filtered_df)} leads")

        # Download buttons
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            csv = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download Filtered CSV",
                csv,
                "filtered_leads.csv",
                "text/csv"
            )

        with col2:
            if (PROCESSED_DATA_DIR / 'tier_1_leads_real.csv').exists():
                tier1_csv = pd.read_csv(PROCESSED_DATA_DIR / 'tier_1_leads_real.csv').to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Tier 1 CSV",
                    tier1_csv,
                    "tier_1_leads.csv",
                    "text/csv"
                )

        with col3:
            if (PROCESSED_DATA_DIR / 'tier_2_leads_real.csv').exists():
                tier2_csv = pd.read_csv(PROCESSED_DATA_DIR / 'tier_2_leads_real.csv').to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Tier 2 CSV",
                    tier2_csv,
                    "tier_2_leads.csv",
                    "text/csv"
                )

        with col4:
            if (PROCESSED_DATA_DIR / 'tier_3_leads_real.csv').exists():
                tier3_csv = pd.read_csv(PROCESSED_DATA_DIR / 'tier_3_leads_real.csv').to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Tier 3 CSV",
                    tier3_csv,
                    "tier_3_leads.csv",
                    "text/csv"
                )

        # Show data - include year_built if available
        display_cols = ['address', 'owner_name', 'motivation_score', 'tier',
                       'taxes_owed', 'years_delinquent']

        # Add code violations columns
        if 'total_violations' in filtered_df.columns:
            display_cols.append('total_violations')
        if 'critical_violations' in filtered_df.columns:
            display_cols.append('critical_violations')

        # Add contact info columns
        if 'phone' in filtered_df.columns:
            display_cols.append('phone')
        if 'email' in filtered_df.columns:
            display_cols.append('email')

        # Add equity columns
        if 'estimated_equity' in filtered_df.columns:
            display_cols.append('estimated_equity')
        if 'equity_tier' in filtered_df.columns:
            display_cols.append('equity_tier')

        # Add freshness columns
        if 'freshness_tier' in filtered_df.columns:
            display_cols.append('freshness_tier')
        if 'change_alert' in filtered_df.columns:
            display_cols.append('change_alert')

        # Add ARV/comps columns
        if 'arv_estimate' in filtered_df.columns:
            display_cols.append('arv_estimate')
        if 'potential_profit' in filtered_df.columns:
            display_cols.append('potential_profit')

        # Add portfolio size for whale detection
        if 'portfolio_size' in filtered_df.columns:
            display_cols.append('portfolio_size')

        # Add property details columns if available
        if 'year_built' in filtered_df.columns:
            display_cols.append('year_built')
        if 'square_feet' in filtered_df.columns:
            display_cols.append('square_feet')
        if 'bedrooms' in filtered_df.columns:
            display_cols.append('bedrooms')

        display_cols.append('reasons')

        # Filter to only columns that exist
        display_cols = [col for col in display_cols if col in filtered_df.columns]

        # Add Street View column if available
        if 'street_view_url' in filtered_df.columns:
            # Create a display DataFrame with clickable links
            display_df = filtered_df[display_cols].copy()
            display_df['📷 View'] = filtered_df['street_view_url']

            st.dataframe(
                display_df,
                width='stretch',
                height=600,
                column_config={
                    '📷 View': st.column_config.LinkColumn(
                        '📷 View',
                        display_text='View',
                        help='Click to open Google Street View'
                    )
                }
            )
        else:
            st.dataframe(
                filtered_df[display_cols],
                width='stretch',
                height=600
            )


# ========================================
# WHALE OWNERS PAGE
# ========================================
elif page == "🐋 Whale Owners":
    st.markdown('<h1 class="main-header">🐋 Whale Owners</h1>', unsafe_allow_html=True)
    st.markdown("### Multi-Property Owners - Your Highest Value Leads")

    st.info("""
    **Why Whale Owners Matter:**
    - Own 2+ distressed properties = tired landlords ready to sell
    - Higher motivation to negotiate bulk deals
    - One conversation can lead to multiple property acquisitions
    """)

    all_leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

    if not all_leads_file.exists():
        st.warning("⚠️ No leads found. Generate leads first!")
    else:
        df = pd.read_csv(all_leads_file)

        # Run portfolio detection if not already done
        if 'portfolio_size' not in df.columns:
            detector = PortfolioDetector()
            df = detector.analyze_portfolios(df)

        # Get whale summary
        detector = PortfolioDetector()
        whales = detector.get_whale_summary(df)

        if whales.empty:
            st.warning("No whale owners found in current dataset. Try generating more leads.")
        else:
            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)

            total_whale_owners = len(whales)
            total_whale_properties = whales['property_count'].sum()
            total_whale_debt = whales['total_debt'].sum()
            avg_properties = whales['property_count'].mean()

            with col1:
                st.metric("Whale Owners", total_whale_owners)
            with col2:
                st.metric("Properties Owned", int(total_whale_properties))
            with col3:
                st.metric("Total Debt", f"${total_whale_debt:,.0f}")
            with col4:
                st.metric("Avg Props/Owner", f"{avg_properties:.1f}")

            st.markdown("---")

            # Filter options
            col1, col2 = st.columns(2)
            with col1:
                min_properties = st.slider("Min Properties", 2, 10, 2)
            with col2:
                min_total_debt = st.number_input("Min Total Debt ($)", value=0, step=5000)

            # Filter whales
            filtered_whales = whales[
                (whales['property_count'] >= min_properties) &
                (whales['total_debt'] >= min_total_debt)
            ]

            st.markdown(f"### Showing {len(filtered_whales)} Whale Owners")

            # Display whale cards
            for idx, (_, whale) in enumerate(filtered_whales.iterrows()):
                with st.expander(
                    f"**{whale['owner_name']}** - {whale['property_count']} properties | ${whale['total_debt']:,.0f} total debt",
                    expanded=(idx < 3)
                ):
                    col1, col2 = st.columns([1, 2])

                    with col1:
                        st.markdown("**Portfolio Summary**")
                        st.write(f"🏠 **Properties:** {whale['property_count']}")
                        st.write(f"💰 **Total Debt:** ${whale['total_debt']:,.0f}")
                        st.write(f"🏦 **Total Value:** ${whale['total_value']:,.0f}")
                        if pd.notna(whale['avg_score']):
                            st.write(f"🎯 **Avg Score:** {whale['avg_score']:.0f}/100")

                    with col2:
                        st.markdown("**Properties Owned**")
                        for i, addr in enumerate(whale['properties'], 1):
                            # Get property details
                            prop_data = df[df['address'] == addr]
                            if not prop_data.empty:
                                prop = prop_data.iloc[0]
                                debt = prop.get('taxes_owed', 0)
                                score = prop.get('motivation_score', 0)
                                st.write(f"{i}. **{addr}** - ${debt:,.0f} debt, Score: {score:.0f}")
                            else:
                                st.write(f"{i}. {addr}")

            # Download whale data
            st.markdown("---")

            # Create downloadable whale report
            whale_export = filtered_whales.copy()
            whale_export['properties'] = whale_export['properties'].apply(lambda x: '; '.join(x))

            csv = whale_export.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download Whale Owners Report",
                csv,
                "whale_owners_report.csv",
                "text/csv"
            )

            # Also allow downloading all whale properties
            whale_properties_df = df[df['is_whale'] == True] if 'is_whale' in df.columns else pd.DataFrame()
            if not whale_properties_df.empty:
                csv2 = whale_properties_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    "📥 Download All Whale Properties",
                    csv2,
                    "whale_properties.csv",
                    "text/csv"
                )


# ========================================
# INVESTOR FINDER PAGE
# ========================================
elif page == "💰 Investor Finder":
    st.markdown('<h1 class="main-header">💰 Investor Finder</h1>', unsafe_allow_html=True)
    st.markdown("Find cash buyers for your deals - scored and ranked by investment activity")

    # Investor data directory
    BUYERS_DATA_DIR = DATA_DIR / 'buyers' / 'processed'
    BUYERS_RAW_DIR = DATA_DIR / 'buyers' / 'raw'

    # County configuration
    COUNTY_OPTIONS = {
        'franklin': {'name': 'Franklin County', 'city': 'Columbus'},
        'hamilton': {'name': 'Hamilton County', 'city': 'Cincinnati'}
    }

    # Tabs for different functions
    inv_tab1, inv_tab2, inv_tab3, inv_tab4, inv_tab5 = st.tabs(["📋 View Investors", "🔄 Run Pipeline", "📞 Bulk Skip Trace", "🔍 Lookup Contact", "💾 Saved Contacts"])

    # ---- TAB 1: VIEW INVESTORS ----
    with inv_tab1:
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            county_select = st.selectbox(
                "Select County",
                options=list(COUNTY_OPTIONS.keys()),
                format_func=lambda x: f"{COUNTY_OPTIONS[x]['city']} ({COUNTY_OPTIONS[x]['name']})"
            )
        with col2:
            tier_filter = st.selectbox(
                "Filter by Tier",
                ["All Tiers", "Tier 1 (80-100)", "Tier 2 (60-79)", "Tier 3 (40-59)"]
            )

        # Load investor data for selected county
        @st.cache_data
        def load_investors_by_county(county, tier=None):
            investors = []
            tier_map = {
                'Tier 1 (80-100)': f'investor_prospects_{county}_tier_1.csv',
                'Tier 2 (60-79)': f'investor_prospects_{county}_tier_2.csv',
                'Tier 3 (40-59)': f'investor_prospects_{county}_tier_3.csv',
            }

            if tier and tier != "All Tiers":
                files = {tier: tier_map[tier]}
            else:
                files = tier_map

            for tier_name, filename in files.items():
                filepath = BUYERS_DATA_DIR / filename
                if filepath.exists():
                    df = pd.read_csv(filepath)
                    df['tier'] = tier_name
                    investors.append(df)

            if investors:
                return pd.concat(investors, ignore_index=True)
            return pd.DataFrame()

        df = load_investors_by_county(county_select, tier_filter)

        if len(df) > 0:
            # Stats
            st.markdown("---")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Investors", f"{len(df):,}")
            with col2:
                if 'investor_score' in df.columns:
                    st.metric("Avg Score", f"{df['investor_score'].mean():.1f}")
            with col3:
                if 'portfolio_size' in df.columns:
                    st.metric("Avg Portfolio", f"{df['portfolio_size'].mean():.1f} properties")
            with col4:
                tier1_count = len(df[df['tier'] == 'Tier 1 (80-100)']) if 'tier' in df.columns else 0
                st.metric("Tier 1 (Hot)", tier1_count)

            st.markdown("---")

            # Search
            search = st.text_input("🔍 Search investors by name or address", key="inv_search")

            if search:
                mask = df.astype(str).apply(lambda x: x.str.contains(search, case=False, na=False)).any(axis=1)
                df = df[mask]

            # Display columns
            display_cols = ['owner_name', 'investor_score', 'portfolio_size', 'entity_type', 'mailing_address', 'tier']
            available_cols = [c for c in display_cols if c in df.columns]

            st.dataframe(
                df[available_cols].sort_values('investor_score', ascending=False) if 'investor_score' in df.columns else df[available_cols],
                use_container_width=True,
                height=400
            )

            # Export options
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                csv = df.to_csv(index=False)
                st.download_button(
                    "📥 Export Full CSV",
                    csv,
                    f"investors_{county_select}_{tier_filter.replace(' ', '_').lower()}.csv",
                    "text/csv"
                )
            with col2:
                # Export formatted for skip tracing
                skip_cols = ['owner_name', 'mailing_address', 'entity_type', 'investor_score', 'portfolio_size']
                skip_available = [c for c in skip_cols if c in df.columns]
                skip_csv = df[skip_available].to_csv(index=False)
                st.download_button(
                    "📥 Export for Skip Tracing",
                    skip_csv,
                    f"investors_skip_trace_{county_select}.csv",
                    "text/csv"
                )
        else:
            st.warning(f"⚠️ No investor data found for {COUNTY_OPTIONS[county_select]['city']}.")
            st.info("Go to 'Run Pipeline' tab to scrape and identify investors.")

    # ---- TAB 2: RUN PIPELINE ----
    with inv_tab2:
        st.subheader("🔄 Run Investor Pipeline")
        st.markdown("Scrape property records and identify cash buyers")

        pipeline_county = st.selectbox(
            "Select County to Process",
            options=list(COUNTY_OPTIONS.keys()),
            format_func=lambda x: f"{COUNTY_OPTIONS[x]['city']} ({COUNTY_OPTIONS[x]['name']})",
            key="pipeline_county"
        )

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Run Full Pipeline**")
            st.caption("Loads property data, identifies multi-property owners, scores investors")
            if st.button("🚀 Run Pipeline", use_container_width=True):
                with st.spinner(f"Running pipeline for {COUNTY_OPTIONS[pipeline_county]['city']}..."):
                    try:
                        from buyers.pipeline.investor_pipeline import InvestorPipeline
                        pipeline = InvestorPipeline(county=pipeline_county)
                        df = pipeline.run()
                        pipeline.export_investors(df)

                        st.success(f"✅ Pipeline complete! Found {len(df)} investors")
                        if 'investor_tier' in df.columns:
                            tier_counts = df['investor_tier'].value_counts()
                            st.write("**Results:**")
                            st.write(f"- Tier 1: {tier_counts.get('tier_1', 0)}")
                            st.write(f"- Tier 2: {tier_counts.get('tier_2', 0)}")
                            st.write(f"- Tier 3: {tier_counts.get('tier_3', 0)}")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"❌ Pipeline failed: {str(e)}")

        with col2:
            if pipeline_county == 'hamilton':
                st.markdown("**Scrape Hamilton County**")
                st.caption("Scrape fresh data from Hamilton County Auditor")
                if st.button("🌐 Scrape Hamilton", use_container_width=True):
                    with st.spinner("Scraping Hamilton County (this may take a while)..."):
                        try:
                            from buyers.scrapers.hamilton_county import HamiltonCountyScraper
                            scraper = HamiltonCountyScraper(headless=True)
                            path = scraper.scrape_and_save()
                            st.success(f"✅ Scrape complete! Saved to {path}")
                        except Exception as e:
                            st.error(f"❌ Scrape failed: {str(e)}")

    # ---- TAB 3: BULK SKIP TRACE ----
    with inv_tab3:
        st.subheader("📞 Bulk Skip Trace Investors")
        st.markdown("Skip trace multiple investors at once to get phone numbers and emails")

        # County selector for bulk skip trace
        bulk_county = st.selectbox(
            "Select County",
            options=list(COUNTY_OPTIONS.keys()),
            format_func=lambda x: f"{COUNTY_OPTIONS[x]['city']} ({COUNTY_OPTIONS[x]['name']})",
            key="bulk_skip_county"
        )

        # Load investors for this county
        bulk_tier_map = {
            'Tier 1 (80-100)': f'investor_prospects_{bulk_county}_tier_1.csv',
            'Tier 2 (60-79)': f'investor_prospects_{bulk_county}_tier_2.csv',
            'Tier 3 (40-59)': f'investor_prospects_{bulk_county}_tier_3.csv',
        }

        # Check which tiers have data
        available_tiers = []
        for tier_name, filename in bulk_tier_map.items():
            if (BUYERS_DATA_DIR / filename).exists():
                available_tiers.append(tier_name)

        if not available_tiers:
            st.warning(f"⚠️ No investor data for {COUNTY_OPTIONS[bulk_county]['city']}. Run the pipeline first.")
        else:
            bulk_tier = st.selectbox("Select Tier to Skip Trace", available_tiers, key="bulk_skip_tier")

            # Load the selected tier
            tier_file = BUYERS_DATA_DIR / bulk_tier_map[bulk_tier]
            inv_df = pd.read_csv(tier_file)

            # Count how many need skip tracing
            has_phone = inv_df['phone'].notna() & (inv_df['phone'] != '') if 'phone' in inv_df.columns else pd.Series([False] * len(inv_df))
            needs_trace = ~has_phone

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total in Tier", len(inv_df))
            with col2:
                st.metric("Already Have Phone", has_phone.sum())
            with col3:
                st.metric("Need Skip Trace", needs_trace.sum())

            if needs_trace.sum() == 0:
                st.success("✅ All investors in this tier already have phone numbers!")
            else:
                st.markdown("---")

                # Slider to select how many to trace
                max_trace = min(needs_trace.sum(), 100)  # Cap at 100 per batch
                if max_trace > 1:
                    num_to_trace = st.slider(
                        "How many to skip trace?",
                        min_value=1,
                        max_value=max_trace,
                        value=min(10, max_trace),
                        key="bulk_inv_trace_count"
                    )
                else:
                    num_to_trace = 1
                    st.info("1 investor to skip trace")

                # Cost estimate
                cost_estimate = num_to_trace * 0.20  # Approximate cost per lookup
                st.caption(f"💰 Estimated cost: ${cost_estimate:.2f} ({num_to_trace} x $0.20)")

                if st.button(f"📞 Skip Trace {num_to_trace} Investors", use_container_width=True, type="primary"):
                    # Get investors that need tracing
                    to_trace = inv_df[needs_trace].head(num_to_trace)

                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    results_container = st.empty()

                    success_count = 0
                    failed_count = 0

                    try:
                        from sellers.skip_tracing.skip_tracer import SkipTracer
                        tracer = SkipTracer()

                        for idx, (i, row) in enumerate(to_trace.iterrows()):
                            progress = (idx + 1) / num_to_trace
                            progress_bar.progress(progress)
                            status_text.text(f"Processing {idx + 1}/{num_to_trace}: {row.get('owner_name', 'Unknown')[:30]}...")

                            name = row.get('owner_name', '')
                            address = row.get('mailing_address', '') or row.get('owner_address', '')

                            if not name:
                                failed_count += 1
                                continue

                            try:
                                result = tracer.skip_trace_single(name, address, '', 'OH')

                                if result and (result.get('phone') or result.get('email')):
                                    inv_df.loc[i, 'phone'] = result.get('phone', '')
                                    inv_df.loc[i, 'email'] = result.get('email', '')
                                    success_count += 1
                                else:
                                    failed_count += 1
                            except Exception as e:
                                failed_count += 1

                            # Small delay to avoid rate limiting
                            time.sleep(0.5)

                        # Save updated data
                        inv_df.to_csv(tier_file, index=False)

                        progress_bar.progress(1.0)
                        status_text.empty()

                        st.success(f"✅ Skip trace complete!")
                        col1, col2 = st.columns(2)
                        with col1:
                            st.metric("Found Contact Info", success_count)
                        with col2:
                            st.metric("No Results", failed_count)

                        if success_count > 0:
                            st.info("Data saved! Refresh the View Investors tab to see phone numbers.")
                            st.cache_data.clear()

                    except Exception as e:
                        st.error(f"❌ Skip trace failed: {str(e)}")

    # ---- TAB 4: LOOKUP CONTACT ----
    with inv_tab4:
        st.subheader("🔍 Contact Lookup")
        st.markdown("Find contact info for investors - supports both individuals and LLCs")

        lookup_name = st.text_input("Owner/Business Name", key="lookup_name")
        lookup_address = st.text_input("Address (optional, helps with accuracy)", key="lookup_addr")

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("🔍 Full Lookup", use_container_width=True, help="Smart lookup: detects LLC vs individual"):
                if lookup_name:
                    with st.spinner("Looking up..."):
                        try:
                            # Detect if business
                            business_keywords = ['LLC', 'L.L.C', 'INC', 'CORP', 'TRUST', 'LP', 'LTD', 'COMPANY', 'PARTNERS']
                            is_business = any(kw in lookup_name.upper() for kw in business_keywords)

                            if is_business:
                                st.info("Detected business entity - checking Ohio SOS...")
                                from buyers.scrapers.ohio_sos import OhioSOSScraper
                                scraper = OhioSOSScraper(headless=True)
                                sos_result = scraper.search_business(lookup_name)

                                if sos_result:
                                    st.success("✅ Found on Ohio SOS")
                                    st.write(f"**Agent:** {sos_result.agent_name}")
                                    st.write(f"**Agent Address:** {sos_result.agent_address}")
                                    st.write(f"**Status:** {sos_result.status}")

                                    # Store for saving
                                    st.session_state['last_lookup'] = {
                                        'llc_name': lookup_name,
                                        'agent_name': sos_result.agent_name,
                                        'agent_address': sos_result.agent_address,
                                        'status': sos_result.status
                                    }
                                else:
                                    st.warning("Not found on Ohio SOS")
                            else:
                                st.info("Detected individual - skip tracing...")
                                from sellers.skip_tracing.skip_tracer import SkipTracer
                                tracer = SkipTracer()
                                result = tracer.skip_trace_single(lookup_name, lookup_address, '', 'OH')

                                if result and (result.get('phone') or result.get('email')):
                                    st.success("✅ Found contact info!")
                                    st.write(f"**Phone:** {result.get('phone', 'N/A')}")
                                    st.write(f"**Email:** {result.get('email', 'N/A')}")
                                    st.session_state['last_lookup'] = {
                                        'name': lookup_name,
                                        'phone': result.get('phone', ''),
                                        'email': result.get('email', '')
                                    }
                                else:
                                    st.warning("No contact info found")
                        except Exception as e:
                            st.error(f"Lookup failed: {str(e)}")
                else:
                    st.warning("Enter a name to lookup")

        with col2:
            if st.button("🏢 Ohio SOS Only", use_container_width=True, help="Search Ohio Secretary of State"):
                if lookup_name:
                    with st.spinner("Searching Ohio SOS..."):
                        try:
                            from buyers.scrapers.ohio_sos import OhioSOSScraper
                            scraper = OhioSOSScraper(headless=True)
                            result = scraper.search_business(lookup_name)

                            if result:
                                st.success("✅ Found!")
                                st.json(result.to_dict() if hasattr(result, 'to_dict') else str(result))
                            else:
                                st.warning("Not found on Ohio SOS")
                        except Exception as e:
                            st.error(f"SOS lookup failed: {str(e)}")
                else:
                    st.warning("Enter a business name")

        with col3:
            if st.button("📞 Skip Trace Only", use_container_width=True, help="Get phone/email"):
                if lookup_name:
                    with st.spinner("Skip tracing..."):
                        try:
                            from sellers.skip_tracing.skip_tracer import SkipTracer
                            tracer = SkipTracer()
                            result = tracer.skip_trace_single(lookup_name, lookup_address, '', 'OH')

                            if result:
                                st.success("✅ Results:")
                                st.write(f"**Phone:** {result.get('phone', 'N/A')}")
                                st.write(f"**Email:** {result.get('email', 'N/A')}")
                            else:
                                st.warning("No results found")
                        except Exception as e:
                            st.error(f"Skip trace failed: {str(e)}")
                else:
                    st.warning("Enter a name")

        # Save contact button
        if 'last_lookup' in st.session_state and st.session_state['last_lookup']:
            st.markdown("---")
            if st.button("💾 Save This Contact", use_container_width=True):
                import json
                contacts_file = DATA_DIR / 'buyers' / 'saved_contacts.json'
                contacts_file.parent.mkdir(parents=True, exist_ok=True)

                existing = []
                if contacts_file.exists():
                    with open(contacts_file, 'r') as f:
                        existing = json.load(f)

                contact = st.session_state['last_lookup']
                contact['saved_at'] = datetime.now().isoformat()
                existing.append(contact)

                with open(contacts_file, 'w') as f:
                    json.dump(existing, f, indent=2)

                st.success("✅ Contact saved!")
                st.session_state['last_lookup'] = None

    # ---- TAB 5: SAVED CONTACTS ----
    with inv_tab5:
        st.subheader("💾 Saved Contacts")

        import json
        contacts_file = DATA_DIR / 'buyers' / 'saved_contacts.json'

        if contacts_file.exists():
            with open(contacts_file, 'r') as f:
                contacts = json.load(f)

            if contacts:
                st.metric("Total Saved", len(contacts))

                contacts_df = pd.DataFrame(contacts)
                st.dataframe(contacts_df, use_container_width=True, height=300)

                col1, col2 = st.columns(2)
                with col1:
                    csv = contacts_df.to_csv(index=False)
                    st.download_button(
                        "📥 Export Contacts CSV",
                        csv,
                        "saved_investor_contacts.csv",
                        "text/csv"
                    )
                with col2:
                    if st.button("🗑️ Clear All Contacts"):
                        with open(contacts_file, 'w') as f:
                            json.dump([], f)
                        st.success("Contacts cleared!")
                        st.rerun()
            else:
                st.info("No saved contacts yet. Use the Lookup tab to find and save contacts.")
        else:
            st.info("No saved contacts yet. Use the Lookup tab to find and save contacts.")

# ========================================
# DEAL ANALYZER PAGE
# ========================================
elif page == "💵 Deal Analyzer":
    st.markdown('<h1 class="main-header">💵 Deal Analyzer</h1>', unsafe_allow_html=True)
    st.markdown("Calculate MAO and match leads to buyers")

    deal_tab1, deal_tab2 = st.tabs(["🧮 MAO Calculator", "🤝 Match Lead to Buyer"])

    # ---- TAB 1: MAO CALCULATOR ----
    with deal_tab1:
        # Option to load from leads or enter manually
        data_source = st.radio(
            "Data Source",
            ["📋 Select from Leads", "✏️ Enter Manually"],
            horizontal=True,
            key="mao_data_source"
        )

        # Initialize values
        address = ""
        arv = 150000
        repairs = 25000
        sqft = 0
        zip_code = ""
        condition = "fair"

        if data_source == "📋 Select from Leads":
            # Lead source selector
            lead_sources = {
                "📋 All Leads": PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv',
                "⚖️ Probate Leads": PROCESSED_DATA_DIR / 'probate_leads.csv',
                "🏛️ Sheriff Sales": PROCESSED_DATA_DIR / 'sheriff_sale_leads.csv',
                "⭐ Tier 1 (Hot)": PROCESSED_DATA_DIR / 'columbus_oh_tier_1_leads.csv',
                "📊 Tier 2": PROCESSED_DATA_DIR / 'columbus_oh_tier_2_leads.csv',
                "📉 Tier 3": PROCESSED_DATA_DIR / 'columbus_oh_tier_3_leads.csv',
            }

            # Filter to existing files only
            available_sources = {k: v for k, v in lead_sources.items() if v.exists()}

            if not available_sources:
                st.warning("No lead files found. Generate leads first!")
            else:
                lead_source = st.selectbox(
                    "Lead Source",
                    options=list(available_sources.keys()),
                    key="mao_lead_source"
                )

                leads_df = pd.read_csv(available_sources[lead_source])

                # Create lead options
                lead_options = ["-- Select a property --"]
                for idx, row in leads_df.head(100).iterrows():
                    addr = row.get('property_address', row.get('address', 'Unknown'))
                    score = row.get('motivation_score', 0)
                    lead_type = row.get('lead_type', row.get('source', ''))
                    if lead_type:
                        lead_options.append(f"{addr} ({lead_type}, Score: {score})")
                    else:
                        lead_options.append(f"{addr} (Score: {score})")

                selected = st.selectbox("Select Property", lead_options, key="mao_lead_select")

                if selected != "-- Select a property --":
                    # Get the selected lead
                    selected_idx = lead_options.index(selected) - 1  # -1 for the placeholder
                    lead_row = leads_df.iloc[selected_idx]

                    # Extract data
                    street_address = lead_row.get('property_address', lead_row.get('address', ''))
                    city = lead_row.get('property_city', lead_row.get('city', 'Columbus')).replace(' CITY', '').title()
                    state = lead_row.get('state', 'OH')
                    zip_code = str(lead_row.get('property_zip', lead_row.get('zip_code', lead_row.get('zip', ''))))[:5]

                    # Build full address for lookup
                    address = f"{street_address}, {city}, {state} {zip_code}"

                    sqft = float(lead_row.get('square_feet', lead_row.get('sqft', 0)) or 0)
                    years_del = int(lead_row.get('years_delinquent', 0) or 0)
                    violations = int(lead_row.get('code_violations', lead_row.get('violations', 0)) or 0)

                    # Use CompsEstimator
                    estimator = CompsEstimator()

                    if sqft > 0:
                        # Option to refresh from Zillow for more accurate data
                        refresh_col1, refresh_col2 = st.columns([3, 1])
                        with refresh_col1:
                            st.caption(f"📊 Current data: {sqft:,.0f} sqft from tax records")
                        with refresh_col2:
                            refresh_zillow = st.button("🔄 Get Zillow Data", key="refresh_zillow_btn")

                        if refresh_zillow:
                            from shared.utils.property_lookup import PropertyLookup
                            lookup = PropertyLookup()
                            with st.spinner("🔍 Fetching from Zillow..."):
                                try:
                                    zillow_data = lookup.lookup_by_address(address)
                                finally:
                                    lookup.close()

                            if zillow_data and zillow_data.get('square_feet'):
                                sqft = zillow_data['square_feet']
                                st.success(f"✅ Updated from Zillow: {sqft:,} sqft, {zillow_data.get('bedrooms', 'N/A')} bed, {zillow_data.get('bathrooms', 'N/A')} bath")

                        estimated_arv, details = estimator.estimate_arv(
                            zip_code=zip_code,
                            square_feet=sqft,
                            years_delinquent=years_del,
                            violations=violations
                        )
                        arv = int(estimated_arv)
                        repairs = int(details.get('repair_cost_estimate', 25000))
                        condition = details.get('condition', 'fair')

                        # Show property details
                        st.markdown("---")
                        st.subheader("📍 Property Analysis")

                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Square Feet", f"{sqft:,.0f}")
                        with col2:
                            st.metric("Zip Code", zip_code)
                        with col3:
                            st.metric("Market $/sqft", f"${details.get('market_psf', 100)}")
                        with col4:
                            st.metric("Condition", condition.title())

                        st.info(f"**Estimated based on:** {sqft:,.0f} sqft × ${details.get('market_psf', 100)}/sqft = ${arv:,}")

                        # Quick Links for Real Comps
                        st.markdown("---")
                        st.subheader("🔗 Research Real Comps")
                        st.caption("Click these links to verify ARV with actual market data:")

                        # Format address for URLs
                        import urllib.parse
                        addr_encoded = urllib.parse.quote(address)
                        addr_plus = address.replace(' ', '+')
                        city_state = "Columbus+OH"

                        link_col1, link_col2, link_col3, link_col4 = st.columns(4)

                        with link_col1:
                            zillow_url = f"https://www.zillow.com/homes/{addr_plus},-{city_state}_rb/"
                            st.link_button("🏠 Zillow", zillow_url, use_container_width=True)

                        with link_col2:
                            redfin_url = f"https://www.redfin.com/city/35241/OH/Columbus/filter/include=sold-3mo"
                            st.link_button("🔴 Redfin Sold", redfin_url, use_container_width=True)

                        with link_col3:
                            realtor_url = f"https://www.realtor.com/realestateandhomes-search/Columbus_OH/show-recently-sold"
                            st.link_button("🏡 Realtor.com", realtor_url, use_container_width=True)

                        with link_col4:
                            auditor_url = f"https://property.franklincountyauditor.com/_web/search/commonsearch.aspx?mode=address"
                            st.link_button("📋 County Auditor", auditor_url, use_container_width=True)

                        st.caption("💡 **Tip:** Look for 3-5 similar properties sold in last 90 days within 0.5 miles")
                    else:
                        # No sqft data - try auto-lookup from County Auditor
                        st.markdown("---")
                        st.subheader("📍 Property: " + address)

                        import urllib.parse
                        addr_plus = address.replace(' ', '+')
                        city_state = "Columbus+OH"

                        # Try auto-lookup using Selenium
                        from shared.utils.property_lookup import PropertyLookup
                        lookup = PropertyLookup()

                        with st.spinner("🔍 Looking up property details (this may take a few seconds)..."):
                            try:
                                property_details = lookup.lookup_by_address(address)
                            finally:
                                lookup.close()  # Always close the browser

                        if property_details and property_details.get('square_feet', 0) > 0:
                            # Found sqft automatically!
                            auto_sqft = property_details['square_feet']
                            source = property_details.get('source', 'Online')
                            st.success(f"✅ Found property data from {source}!")

                            # Calculate ARV with auto-found sqft
                            estimated_arv, details = estimator.estimate_arv(
                                zip_code=zip_code,
                                square_feet=auto_sqft,
                                years_delinquent=years_del,
                                violations=violations
                            )
                            arv = int(estimated_arv)
                            repairs = int(details.get('repair_cost_estimate', 25000))
                            condition = details.get('condition', 'fair')
                            sqft = auto_sqft

                            st.info(f"**Estimated ARV:** ${arv:,} based on {auto_sqft:,} sqft × ${details.get('market_psf', 100)}/sqft")

                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("Square Feet", f"{auto_sqft:,.0f}")
                            with col2:
                                st.metric("Zip Code", zip_code)
                            with col3:
                                st.metric("Market $/sqft", f"${details.get('market_psf', 100)}")
                            with col4:
                                st.metric("Condition", condition.title())

                            # Show other details if found
                            if property_details.get('year_built'):
                                st.caption(f"📅 Year Built: {property_details['year_built']}")
                            if property_details.get('bedrooms'):
                                st.caption(f"🛏️ Bedrooms: {property_details['bedrooms']}")

                            # Quick Links for comps
                            st.markdown("---")
                            st.subheader("🔗 Verify with Real Comps")
                            link_col1, link_col2, link_col3 = st.columns(3)
                            with link_col1:
                                zillow_url = f"https://www.zillow.com/homes/{addr_plus},-{city_state}_rb/"
                                st.link_button("🏠 Zillow", zillow_url, use_container_width=True)
                            with link_col2:
                                redfin_url = f"https://www.redfin.com/city/35241/OH/Columbus/filter/include=sold-3mo"
                                st.link_button("🔴 Redfin Sold", redfin_url, use_container_width=True)
                            with link_col3:
                                realtor_url = f"https://www.realtor.com/realestateandhomes-search/Columbus_OH/show-recently-sold"
                                st.link_button("🏡 Realtor.com", realtor_url, use_container_width=True)
                        else:
                            # Auto-lookup failed - manual entry
                            st.warning("⚠️ Couldn't auto-fetch property data. Enter manually:")

                            # Link to County Auditor to look up sqft
                            auditor_url = f"https://property.franklincountyauditor.com/_web/search/commonsearch.aspx?mode=address"
                            st.link_button("🔍 Look Up on County Auditor", auditor_url, use_container_width=False)

                            manual_sqft = st.number_input("Square Footage", min_value=0, value=0, step=100, key="manual_sqft_input")

                            if manual_sqft > 0:
                                # Calculate ARV with manual sqft
                                estimated_arv, details = estimator.estimate_arv(
                                    zip_code=zip_code,
                                    square_feet=manual_sqft,
                                    years_delinquent=years_del,
                                    violations=violations
                                )
                                arv = int(estimated_arv)
                                repairs = int(details.get('repair_cost_estimate', 25000))
                                condition = details.get('condition', 'fair')
                                sqft = manual_sqft

                                st.success(f"✅ ARV calculated: **${arv:,}** based on {manual_sqft:,} sqft × ${details.get('market_psf', 100)}/sqft")

                                col1, col2, col3, col4 = st.columns(4)
                                with col1:
                                    st.metric("Square Feet", f"{manual_sqft:,.0f}")
                                with col2:
                                    st.metric("Zip Code", zip_code)
                                with col3:
                                    st.metric("Market $/sqft", f"${details.get('market_psf', 100)}")
                                with col4:
                                    st.metric("Condition", condition.title())

                                # Quick Links for comps
                                st.markdown("---")
                                st.subheader("🔗 Verify with Real Comps")
                                link_col1, link_col2, link_col3 = st.columns(3)
                                with link_col1:
                                    zillow_url = f"https://www.zillow.com/homes/{addr_plus},-{city_state}_rb/"
                                    st.link_button("🏠 Zillow", zillow_url, use_container_width=True)
                                with link_col2:
                                    redfin_url = f"https://www.redfin.com/city/35241/OH/Columbus/filter/include=sold-3mo"
                                    st.link_button("🔴 Redfin Sold", redfin_url, use_container_width=True)
                                with link_col3:
                                    realtor_url = f"https://www.realtor.com/realestateandhomes-search/Columbus_OH/show-recently-sold"
                                    st.link_button("🏡 Realtor.com", realtor_url, use_container_width=True)

        st.markdown("---")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Property Details")
            address = st.text_input("Property Address", value=address, key="mao_address")
            arv = st.number_input("ARV (After Repair Value)", min_value=0, value=arv, step=5000, key="mao_arv",
                                  help="Estimated value after repairs - adjust based on your comps research")

            st.markdown("**Repair Estimates:**")
            st.caption("Light: $15/sqft | Moderate: $35/sqft | Heavy: $60/sqft | Gut: $100/sqft")
            repairs = st.number_input("Estimated Repairs", min_value=0, value=repairs, step=1000, key="mao_repairs",
                                      help="Estimated repair costs - adjust based on property condition")

        with col2:
            st.subheader("Deal Parameters")
            arv_percentage = st.slider("Investor ARV %", 60, 80, 70, key="mao_arv_pct",
                                       help="Most investors want to pay 65-75% of ARV") / 100
            assignment_fee = st.number_input("Your Assignment Fee", min_value=0, value=10000, step=1000, key="mao_fee",
                                             help="Your profit from the deal - typically $5k-$15k")

        # Calculate
        if st.button("🧮 Calculate MAO", use_container_width=True, key="mao_calc_btn"):
            investor_max = arv * arv_percentage
            investor_offer = investor_max - repairs
            mao = investor_offer - assignment_fee

            # Investor numbers
            total_investor_cost = investor_offer + repairs
            investor_profit = arv - total_investor_cost
            investor_roi = (investor_profit / total_investor_cost) * 100 if total_investor_cost > 0 else 0

            st.markdown("---")

            # Results
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("YOUR MAO", f"${mao:,.0f}", help="Maximum you should offer the seller")
            with col2:
                st.metric("Your Profit", f"${assignment_fee:,.0f}")
            with col3:
                st.metric("Investor ROI", f"{investor_roi:.1f}%")

            st.markdown("---")

            # Breakdown
            st.subheader("Deal Breakdown")

            breakdown = f"""
| Item | Amount |
|------|--------|
| ARV (After Repair Value) | ${arv:,.0f} |
| Investor Max ({arv_percentage*100:.0f}% of ARV) | ${investor_max:,.0f} |
| Minus Repairs | -${repairs:,.0f} |
| **Max Investor Pays** | **${investor_offer:,.0f}** |
| Minus Your Fee | -${assignment_fee:,.0f} |
| **YOUR MAO** | **${mao:,.0f}** |
"""
            st.markdown(breakdown)

            # Deal Rating
            st.markdown("---")
            if investor_roi >= 20 and assignment_fee >= 5000:
                st.success("✅ **STRONG DEAL** - Good margins for both you and investor")
            elif investor_roi >= 15 and assignment_fee >= 3000:
                st.warning("⚠️ **DECENT DEAL** - Acceptable margins, may need negotiation")
            elif investor_roi >= 10:
                st.warning("⚠️ **THIN DEAL** - Margins are tight, experienced investors only")
            else:
                st.error("❌ **PASS** - Not enough margin, renegotiate or walk away")

            # Negotiation tips
            st.markdown("---")
            st.subheader("Negotiation Strategy")
            low_offer = mao * 0.85
            st.markdown(f"""
- **Start at:** ${low_offer:,.0f}
- **Walk-away point:** ${mao:,.0f}
- Never exceed your MAO!
""")

    # ---- TAB 2: MATCH LEAD TO BUYER ----
    with deal_tab2:
        st.subheader("🤝 Match Seller Lead to Cash Buyer")
        st.markdown("Select a motivated seller lead and find matching investors")

        # Lead source selector
        match_lead_sources = {
            "📋 All Leads": PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv',
            "⚖️ Probate Leads": PROCESSED_DATA_DIR / 'probate_leads.csv',
            "🏛️ Sheriff Sales": PROCESSED_DATA_DIR / 'sheriff_sale_leads.csv',
            "⭐ Tier 1 (Hot)": PROCESSED_DATA_DIR / 'columbus_oh_tier_1_leads.csv',
        }

        # Filter to existing files only
        match_available_sources = {k: v for k, v in match_lead_sources.items() if v.exists()}

        # Load investor data
        BUYERS_DATA_DIR = DATA_DIR / 'buyers' / 'processed'

        if not match_available_sources:
            st.warning("⚠️ No seller leads found. Generate leads first!")
        else:
            match_lead_source = st.selectbox(
                "Lead Source",
                options=list(match_available_sources.keys()),
                key="match_lead_source"
            )

            leads_df = pd.read_csv(match_available_sources[match_lead_source])

            # Filter to leads with phone numbers (ready to contact)
            if 'phone' in leads_df.columns:
                callable_leads = leads_df[leads_df['phone'].notna() & (leads_df['phone'] != '')]
            else:
                callable_leads = leads_df

            if len(callable_leads) == 0:
                st.warning("No callable leads found. Skip trace your leads first!")
            else:
                st.info(f"📋 {len(callable_leads)} callable leads available from {match_lead_source}")

                # Select a lead
                lead_options = []
                for idx, row in callable_leads.head(100).iterrows():
                    addr = row.get('property_address', row.get('address', 'Unknown'))
                    score = row.get('motivation_score', 0)
                    lead_options.append(f"{addr} (Score: {score})")

                selected_lead = st.selectbox("Select a Lead", lead_options, key="match_lead_select")

                if selected_lead:
                    # Get the selected lead data
                    selected_idx = lead_options.index(selected_lead)
                    lead_row = callable_leads.iloc[selected_idx]

                    # Display lead info
                    st.markdown("---")
                    st.subheader("📍 Selected Property")

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.write(f"**Address:** {lead_row.get('property_address', lead_row.get('address', 'N/A'))}")
                        st.write(f"**Owner:** {lead_row.get('owner_name', 'N/A')}")
                    with col2:
                        st.write(f"**Motivation Score:** {lead_row.get('motivation_score', 'N/A')}")
                        st.write(f"**Lead Type:** {lead_row.get('lead_type', lead_row.get('source', 'N/A'))}")
                    with col3:
                        st.write(f"**Phone:** {lead_row.get('phone', 'N/A')}")
                        st.write(f"**Email:** {lead_row.get('email', 'N/A')}")

                    # Find matching buyers button
                    st.markdown("---")

                    if st.button("🔍 Find Matching Buyers", use_container_width=True, type="primary"):
                        # Load investor data (Tier 1 and 2 - active buyers)
                        investors = []

                        for tier in ['tier_1', 'tier_2']:
                            tier_file = BUYERS_DATA_DIR / f'investor_prospects_franklin_{tier}.csv'
                            if tier_file.exists():
                                df = pd.read_csv(tier_file)
                                df['tier'] = tier
                                investors.append(df)

                        if not investors:
                            st.warning("⚠️ No investor data found. Run the Investor Finder pipeline first!")
                        else:
                            inv_df = pd.concat(investors, ignore_index=True)

                            # Filter to investors with contact info
                            if 'phone' in inv_df.columns:
                                has_contact = inv_df['phone'].notna() & (inv_df['phone'] != '')
                                contactable = inv_df[has_contact]
                            else:
                                contactable = inv_df

                            # Sort by investor score
                            if 'investor_score' in contactable.columns:
                                contactable = contactable.sort_values('investor_score', ascending=False)

                            st.success(f"✅ Found {len(contactable)} potential buyers!")

                            # Display top matches
                            st.subheader("🏆 Top Matching Buyers")

                            display_cols = ['owner_name', 'investor_score', 'portfolio_size', 'entity_type', 'phone', 'email', 'tier']
                            available_cols = [c for c in display_cols if c in contactable.columns]

                            st.dataframe(
                                contactable[available_cols].head(20),
                                use_container_width=True,
                                height=400
                            )

                            # Export matches
                            st.markdown("---")
                            col1, col2 = st.columns(2)

                            with col1:
                                # Export top 20 matches
                                top_matches = contactable.head(20)
                                csv = top_matches.to_csv(index=False)
                                property_addr = str(lead_row.get('property_address', 'property'))[:20].replace(' ', '_')
                                st.download_button(
                                    "📥 Export Top 20 Matches",
                                    csv,
                                    f"buyers_for_{property_addr}.csv",
                                    "text/csv"
                                )

                            with col2:
                                # Quick stats
                                st.write(f"**Tier 1 Buyers:** {len(contactable[contactable['tier'] == 'tier_1'])}")
                                st.write(f"**Tier 2 Buyers:** {len(contactable[contactable['tier'] == 'tier_2'])}")
                                if 'portfolio_size' in contactable.columns:
                                    st.write(f"**Avg Portfolio:** {contactable['portfolio_size'].mean():.1f} properties")

# ========================================
# STATISTICS PAGE
# ========================================
elif page == "📈 Statistics":
    st.markdown('<h1 class="main-header">📈 Statistics</h1>', unsafe_allow_html=True)

    all_leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

    if not all_leads_file.exists():
        st.warning("⚠️ No leads found. Generate leads first!")
    else:
        df = pd.read_csv(all_leads_file)

        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Leads", len(df))
        with col2:
            st.metric("Avg Score", f"{df['motivation_score'].mean():.1f}/100")
        with col3:
            st.metric("Total Tax Debt", f"${df['taxes_owed'].sum():,.0f}")
        with col4:
            revenue = (
                len(df[df['tier'] == 1]) * 100 +
                len(df[df['tier'] == 2]) * 75 +
                len(df[df['tier'] == 3]) * 50
            )
            st.metric("Revenue Potential", f"${revenue:,}")

        st.markdown("---")

        # Charts
        col1, col2 = st.columns(2)

        with col1:
            # Tier distribution
            tier_counts = df['tier'].value_counts().sort_index()
            fig1 = px.pie(
                values=tier_counts.values,
                names=[f"Tier {t}" for t in tier_counts.index],
                title="Lead Distribution by Tier"
            )
            st.plotly_chart(fig1, use_container_width=True)

        with col2:
            # Score distribution
            fig2 = px.histogram(
                df,
                x='motivation_score',
                nbins=20,
                title="Motivation Score Distribution"
            )
            st.plotly_chart(fig2, use_container_width=True)

        col1, col2 = st.columns(2)

        with col1:
            # Tax debt distribution
            fig3 = px.box(
                df,
                x='tier',
                y='taxes_owed',
                title="Tax Debt by Tier"
            )
            st.plotly_chart(fig3, use_container_width=True)

        with col2:
            # Years delinquent
            fig4 = px.histogram(
                df,
                x='years_delinquent',
                title="Years Delinquent Distribution"
            )
            st.plotly_chart(fig4, use_container_width=True)


# ========================================
# DATA QUALITY PAGE
# ========================================
elif page == "📋 Data Quality":
    st.markdown('<h1 class="main-header">📋 Data Quality</h1>', unsafe_allow_html=True)
    st.markdown("### Data Completeness & Freshness Analysis")

    all_leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'

    if not all_leads_file.exists():
        st.warning("⚠️ No leads data found. Generate leads first!")
    else:
        df = pd.read_csv(all_leads_file)

        # Data Freshness Section
        st.markdown("---")
        st.markdown("## 📅 Data Freshness")

        col1, col2, col3, col4 = st.columns(4)

        # Calculate freshness metrics
        if 'scraped_date' in df.columns:
            from datetime import datetime
            try:
                df['_age_days'] = pd.to_datetime(df['scraped_date']).apply(
                    lambda x: (datetime.now() - x).days if pd.notna(x) else 999
                )
                avg_age = df['_age_days'].mean()
                max_age = df['_age_days'].max()
                fresh_count = (df['_age_days'] < 7).sum()
                stale_count = (df['_age_days'] > 90).sum()
            except:
                avg_age, max_age, fresh_count, stale_count = 0, 0, 0, 0
        else:
            avg_age, max_age, fresh_count, stale_count = 0, 0, 0, 0

        with col1:
            st.metric("Avg Data Age", f"{avg_age:.0f} days")
        with col2:
            st.metric("Fresh (<7 days)", f"{fresh_count}")
        with col3:
            st.metric("Stale (>90 days)", f"{stale_count}", delta=None if stale_count == 0 else f"-{stale_count}", delta_color="inverse")
        with col4:
            freshness_score = max(0, 100 - avg_age)
            st.metric("Freshness Score", f"{freshness_score:.0f}/100")

        if avg_age > 30:
            st.warning(f"⚠️ Data is {avg_age:.0f} days old on average. Consider refreshing for best results.")

        # Data Completeness Section
        st.markdown("---")
        st.markdown("## 📊 Data Completeness")

        # Define key fields to check
        key_fields = {
            'owner_name': 'Owner Name',
            'address': 'Address',
            'zip_code': 'ZIP Code',
            'taxes_owed': 'Taxes Owed',
            'market_value': 'Market Value',
            'square_feet': 'Square Footage',
            'year_built': 'Year Built',
            'bedrooms': 'Bedrooms',
            'phone': 'Phone (Skip Trace)',
            'email': 'Email (Skip Trace)',
            'estimated_equity': 'Equity Estimate',
            'arv_estimate': 'ARV Estimate',
        }

        completeness_data = []
        for field, label in key_fields.items():
            if field in df.columns:
                filled = df[field].notna() & (df[field] != '') & (df[field] != 0)
                pct = filled.sum() / len(df) * 100
                completeness_data.append({
                    'Field': label,
                    'Filled': filled.sum(),
                    'Missing': len(df) - filled.sum(),
                    'Completeness': f"{pct:.1f}%",
                    '_pct': pct
                })

        if completeness_data:
            completeness_df = pd.DataFrame(completeness_data)

            # Show as bar chart
            fig = px.bar(
                completeness_df,
                x='Field',
                y='_pct',
                title='Field Completeness (%)',
                color='_pct',
                color_continuous_scale=['red', 'yellow', 'green'],
                range_color=[0, 100]
            )
            fig.update_layout(showlegend=False, yaxis_title='Completeness %')
            st.plotly_chart(fig, use_container_width=True)

            # Show table
            st.dataframe(
                completeness_df[['Field', 'Filled', 'Missing', 'Completeness']],
                width='stretch',
                hide_index=True
            )

        # Quality Alerts Section
        st.markdown("---")
        st.markdown("## 🚨 Quality Alerts")

        alerts = []

        # Check for missing critical data
        if 'phone' in df.columns:
            no_phone = df['phone'].isna().sum()
            if no_phone > len(df) * 0.5:
                alerts.append(f"⚠️ {no_phone} leads ({no_phone/len(df)*100:.0f}%) missing phone numbers")

        if 'square_feet' in df.columns:
            no_sqft = (df['square_feet'].isna() | (df['square_feet'] == 0)).sum()
            if no_sqft > len(df) * 0.3:
                alerts.append(f"📐 {no_sqft} leads ({no_sqft/len(df)*100:.0f}%) missing square footage - affects ARV estimates")

        if 'market_value' in df.columns:
            no_value = (df['market_value'].isna() | (df['market_value'] == 0)).sum()
            if no_value > len(df) * 0.2:
                alerts.append(f"💰 {no_value} leads ({no_value/len(df)*100:.0f}%) missing market value - affects equity estimates")

        if stale_count > 0:
            alerts.append(f"📅 {stale_count} leads have data over 90 days old")

        if alerts:
            for alert in alerts:
                st.warning(alert)
        else:
            st.success("✅ No major data quality issues detected!")

        # Recommendations Section
        st.markdown("---")
        st.markdown("## 💡 Recommendations")

        recommendations = []

        if avg_age > 30:
            recommendations.append("**Refresh Data**: Re-run the lead generation pipeline to get updated tax records")

        if 'phone' in df.columns and df['phone'].isna().sum() > len(df) * 0.3:
            recommendations.append("**Improve Skip Tracing**: Consider using a premium skip trace provider for better hit rates")

        if 'arv_estimate' in df.columns and (df['arv_estimate'] == 0).sum() > len(df) * 0.3:
            recommendations.append("**Square Footage Data**: Many properties missing sq ft data needed for accurate ARV estimates")

        if not recommendations:
            recommendations.append("**All Good!** Your data quality is excellent. Keep up the regular refresh schedule.")

        for rec in recommendations:
            st.info(rec)


# ========================================
# DATA HISTORY PAGE
# ========================================
elif page == "📁 Data History":
    st.markdown('<h1 class="main-header">📁 Data History & Archives</h1>', unsafe_allow_html=True)
    st.markdown("### View, restore, or manage archived lead data")

    archiver = DataArchiver()

    # Get all archives
    archives = archiver.get_archives()

    if not archives:
        st.info("📭 No archived data yet. Archives are created automatically when you generate new leads.")
        st.markdown("""
        **How archiving works:**
        - When you scrape new leads, the old data is automatically saved
        - Archives are organized by type: Delinquent, Probate, Sheriff Sales
        - You can restore old data anytime
        """)
    else:
        # Summary stats
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("📁 Total Archives", len(archives))
        with col2:
            delinquent_count = len([a for a in archives if a['category'] == 'delinquent'])
            st.metric("🏦 Delinquent", delinquent_count)
        with col3:
            probate_count = len([a for a in archives if a['category'] == 'probate'])
            st.metric("⚖️ Probate", probate_count)
        with col4:
            sheriff_count = len([a for a in archives if a['category'] == 'sheriff'])
            st.metric("🏠 Sheriff", sheriff_count)

        st.markdown("---")

        # Filter by category
        categories = ['All'] + list(set([a['category'] for a in archives]))
        selected_category = st.selectbox("Filter by Type", categories)

        if selected_category != 'All':
            filtered_archives = [a for a in archives if a['category'] == selected_category]
        else:
            filtered_archives = archives

        st.markdown(f"### 📋 Archives ({len(filtered_archives)} files)")

        for archive in filtered_archives:
            with st.expander(f"📄 {archive['original_name']} - {archive['timestamp']}", expanded=False):
                col1, col2, col3 = st.columns([2, 1, 1])

                with col1:
                    st.markdown(f"**Category:** {archive['category'].title()}")
                    st.markdown(f"**Rows:** {archive['rows']:,}")
                    st.markdown(f"**Size:** {archive['size_kb']} KB")
                    st.markdown(f"**Archived:** {archive['archived_date'].strftime('%Y-%m-%d %H:%M')}")

                with col2:
                    if st.button("🔄 Restore", key=f"restore_{archive['filename']}", use_container_width=True):
                        if archiver.restore_archive(archive['filepath']):
                            st.success(f"✅ Restored {archive['original_name']}!")
                            st.rerun()
                        else:
                            st.error("Failed to restore")

                with col3:
                    if st.button("🗑️ Delete", key=f"delete_{archive['filename']}", use_container_width=True):
                        if archiver.delete_archive(archive['filepath']):
                            st.success("Deleted!")
                            st.rerun()

        st.markdown("---")

        # Cleanup section
        st.markdown("### 🧹 Cleanup Old Archives")
        col1, col2 = st.columns([2, 1])
        with col1:
            days_to_keep = st.slider("Delete archives older than (days)", 7, 90, 30)
        with col2:
            if st.button("🗑️ Cleanup Old Archives", use_container_width=True):
                deleted = archiver.cleanup_old_archives(days=days_to_keep)
                if deleted > 0:
                    st.success(f"Deleted {deleted} old archives")
                    st.rerun()
                else:
                    st.info("No archives to clean up")

# ========================================
# DATA MANAGEMENT PAGE
# ========================================
elif page == "⚙️ Data Management":
    st.markdown('<h1 class="main-header">⚙️ Data Management</h1>', unsafe_allow_html=True)

    st.markdown("### Franklin County Data Files")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Current Data Status")

        files = {
            'TaxDetail.xlsx': RAW_DATA_DIR / 'TaxDetail.xlsx',
            'Parcel.xlsx': RAW_DATA_DIR / 'Parcel.xlsx',
            'Value.xlsx': RAW_DATA_DIR / 'Value.xlsx'
        }

        for filename, filepath in files.items():
            if filepath.exists():
                size_mb = filepath.stat().st_size / (1024 * 1024)
                st.success(f"✅ {filename} ({size_mb:.1f} MB)")
            else:
                st.error(f"❌ {filename} (Not found)")

    with col2:
        st.markdown("#### Download Fresh Data")
        st.info("""
        Franklin County publishes new data on the **15th of each month**.

        Click the button below to automatically download the latest files.
        """)

        if st.button("📥 Auto-Download Latest Data", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()

            try:
                import requests
                from bs4 import BeautifulSoup
                import urllib.request

                # Step 1: Find latest Tax Accounting folder
                status_text.text("🔍 Finding latest data files...")
                progress_bar.progress(10)

                base_domain = "https://apps.franklincountyauditor.com"
                base_url = "https://apps.franklincountyauditor.com/Outside_User_Files/"

                # Get current year
                current_year = datetime.now().year

                # Try current year first, then previous year
                for year in [current_year, current_year - 1]:
                    try:
                        year_url = f"{base_url}{year}/"
                        response = requests.get(year_url, timeout=30)

                        if response.status_code == 200:
                            soup = BeautifulSoup(response.content, 'html.parser')

                            # Find all Tax Accounting folders
                            folders = []
                            for link in soup.find_all('a'):
                                href = link.get('href', '')
                                if 'Tax%20Accounting' in href or 'Tax Accounting' in href:
                                    folders.append(href)

                            if folders:
                                # Get the most recent folder
                                latest_folder = sorted(folders)[-1]
                                # The href is already a full path from root, just need base domain
                                data_url = f"{base_domain}{latest_folder}"
                                st.info(f"Found: {latest_folder.replace('%20', ' ')}")
                                break
                    except:
                        continue
                else:
                    st.error("Could not find Tax Accounting folder")
                    st.stop()

                progress_bar.progress(20)

                # Step 2: Download files directly (we know the file names)
                # Since we have the folder URL, just append the file names
                files_to_download = ['TaxDetail.xlsx', 'Parcel.xlsx', 'Value.xlsx']

                st.info(f"Downloading from: {latest_folder.replace('%20', ' ')}")
                progress_bar.progress(25)

                # Download each file
                for i, filename in enumerate(files_to_download):
                    status_text.text(f"⬇️ Downloading {filename}...")
                    progress = 25 + (i * 25)
                    progress_bar.progress(progress)

                    # Construct full URL
                    # The data_url already has the folder path, just add the filename
                    file_url = f"{data_url}{filename}"

                    local_path = RAW_DATA_DIR / filename

                    try:
                        # Download with progress
                        urllib.request.urlretrieve(file_url, local_path)

                        size_mb = local_path.stat().st_size / (1024 * 1024)
                        st.success(f"✅ Downloaded {filename} ({size_mb:.1f} MB)")
                    except Exception as e:
                        st.error(f"Failed to download {filename}: {e}")
                        st.info(f"Tried URL: {file_url}")
                        raise

                progress_bar.progress(100)
                status_text.text("✅ Download complete!")

                st.balloons()
                st.success("🎉 All files downloaded successfully! You can now generate fresh leads.")

                # Show download date
                st.info(f"📅 Data downloaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

            except Exception as e:
                st.error(f"❌ Download failed: {e}")
                st.warning("Please try manual download or check your internet connection.")

        st.markdown("---")

        if st.button("🌐 Manual Download Page"):
            import webbrowser
            webbrowser.open("https://apps.franklincountyauditor.com/Outside_User_Files/")

    st.markdown("---")
    st.markdown("### Generated Leads Files")

    lead_files = list(PROCESSED_DATA_DIR.glob('*.csv'))

    if lead_files:
        for file in lead_files:
            size_kb = file.stat().st_size / 1024
            modified = datetime.fromtimestamp(file.stat().st_mtime)
            st.info(f"📄 {file.name} - {size_kb:.1f} KB - Modified: {modified.strftime('%Y-%m-%d %H:%M')}")
    else:
        st.warning("No lead files found")

# ========================================
# DIALER PAGE
# ========================================
elif page == "📱 Dialer":
    st.markdown('<h1 class="main-header">📱 Cold Calling Dialer</h1>', unsafe_allow_html=True)

    # Import dialer modules
    try:
        from sellers.dialer.twilio_client import TwilioClient
        from sellers.dialer.call_manager import CallManager, CallDisposition, LeadStatus
        twilio_available = True
    except ImportError as e:
        twilio_available = False
        st.error(f"Dialer modules not available: {e}")

    if twilio_available:
        # Initialize clients
        try:
            twilio = TwilioClient()
            call_mgr = CallManager()
            twilio_connected = True
        except Exception as e:
            twilio_connected = False
            st.error(f"Twilio connection failed: {e}")

        if twilio_connected:
            # Top metrics
            col1, col2, col3, col4 = st.columns(4)

            # Get Twilio info
            balance = twilio.get_balance()
            phone_numbers = twilio.get_phone_numbers()
            queue_stats = call_mgr.get_queue_stats()

            with col1:
                st.metric("💰 Twilio Balance", f"${balance.get('balance', '0.00')}")
            with col2:
                st.metric("📱 Phone Numbers", len([n for n in phone_numbers if 'error' not in n]))
            with col3:
                st.metric("📋 Leads in Queue", queue_stats['total_in_queue'])
            with col4:
                st.metric("🔥 Hot Leads", queue_stats['hot_leads'])

            st.markdown("---")

            # Tabs for different functions
            tab1, tab2, tab3, tab4 = st.tabs(["📋 Call Queue", "📞 Make Calls", "🔥 Hot Leads", "📈 Stats"])

            # ========== TAB 1: Call Queue ==========
            with tab1:
                st.markdown("### 📋 Manage Call Queue")

                col1, col2 = st.columns([2, 1])

                with col1:
                    st.markdown("#### Load Leads into Queue")

                    # Find leads file
                    leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
                    if not leads_file.exists():
                        leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

                    if leads_file.exists():
                        df_leads = pd.read_csv(leads_file)

                        # Filter options
                        min_score = st.slider("Minimum Motivation Score", 0, 100, 60)

                        # Count leads with phone
                        phone_cols = [c for c in df_leads.columns if 'phone' in c.lower()]
                        if phone_cols:
                            has_phone = df_leads[phone_cols[0]].notna().sum()
                        else:
                            has_phone = 0

                        st.info(f"📊 {len(df_leads)} total leads | {has_phone} with phone numbers")

                        if st.button("📥 Load Leads to Queue", type="primary"):
                            count = call_mgr.load_leads_to_queue(
                                str(leads_file),
                                filter_criteria={'min_score': min_score, 'has_phone': True}
                            )
                            st.success(f"✅ Added {count} leads to queue!")
                            st.rerun()
                    else:
                        st.warning("No leads file found. Generate leads first!")

                with col2:
                    st.markdown("#### Queue Status")
                    for status, count in queue_stats['by_status'].items():
                        st.write(f"**{status}:** {count}")

                    if queue_stats['callbacks_due'] > 0:
                        st.warning(f"⏰ {queue_stats['callbacks_due']} callbacks due!")

                st.markdown("---")
                st.markdown("#### Current Queue")

                if call_mgr.call_queue:
                    queue_df = pd.DataFrame(call_mgr.call_queue)
                    display_cols = ['address', 'owner_name', 'phone', 'motivation_score', 'status', 'call_attempts', 'disposition']
                    display_cols = [c for c in display_cols if c in queue_df.columns]
                    st.dataframe(queue_df[display_cols], use_container_width=True)

                    if st.button("🗑️ Clear Queue"):
                        count = call_mgr.clear_queue()
                        st.success(f"Cleared {count} leads from queue")
                        st.rerun()
                else:
                    st.info("Queue is empty. Load leads above!")

            # ========== TAB 2: Make Calls ==========
            with tab2:
                st.markdown("### 📞 Browser Dialer")
                st.caption("Make calls directly from your browser - VAs can use this from anywhere!")

                # Phone number selection
                st.markdown("#### Select Caller ID")

                valid_numbers = [n for n in phone_numbers if 'error' not in n]

                if valid_numbers:
                    caller_options = {
                        f"{n['phone_number']} - {n.get('friendly_name', 'Unknown')}": n['phone_number']
                        for n in valid_numbers
                    }

                    selected_caller = st.selectbox(
                        "Outbound Caller ID",
                        options=list(caller_options.keys()),
                        help="This number will show on the lead's phone"
                    )
                    selected_number = caller_options[selected_caller]
                else:
                    st.warning("No phone numbers. Buy one in Twilio Console!")
                    selected_number = None

                st.markdown("---")

                col1, col2 = st.columns([3, 2])

                with col1:
                    # Click-to-Call Dialer
                    st.markdown("#### Click-to-Call Dialer")

                    # VA's phone number (the person making calls)
                    if 'va_phone' not in st.session_state:
                        st.session_state.va_phone = ""

                    va_phone = st.text_input(
                        "Your Phone Number",
                        value=st.session_state.va_phone,
                        placeholder="+1234567890",
                        help="Twilio will call YOU first, then connect you to the target"
                    )
                    st.session_state.va_phone = va_phone

                    st.markdown("---")

                    # Two options: Quick Call or Lead Call
                    call_mode = st.radio(
                        "Call Mode",
                        ["📞 Quick Call (any number)", "📋 Call from Queue"],
                        horizontal=True,
                        label_visibility="collapsed"
                    )

                    if call_mode == "📞 Quick Call (any number)":
                        # Quick call to any number
                        target_phone = st.text_input(
                            "Number to Call",
                            placeholder="+16145551234",
                            help="Enter any phone number to call"
                        )

                        if va_phone and target_phone:
                            if st.button("📞 CALL NOW", type="primary", key="quick_call_btn"):
                                try:
                                    result = twilio.make_call(
                                        to_number=va_phone,
                                        from_number=selected_number,
                                        twiml=f'''<Response>
                                            <Say>Connecting your call.</Say>
                                            <Dial callerId="{selected_number}" record="record-from-answer">
                                                <Number>{target_phone}</Number>
                                            </Dial>
                                        </Response>''',
                                        record=True
                                    )
                                    if result.get('success'):
                                        st.success(f"📞 Calling your phone... Answer to connect!")
                                    else:
                                        st.error(f"Call failed: {result.get('error')}")
                                except Exception as e:
                                    st.error(f"Error: {e}")
                        else:
                            if not va_phone:
                                st.warning("⬆️ Enter your phone number above")
                            elif not target_phone:
                                st.info("Enter the number you want to call")

                    else:
                        # Call from queue
                        lead = st.session_state.get('current_lead')

                        if lead:
                            st.markdown(f"**Calling:** {lead.get('owner_name', 'Unknown')}")
                            st.markdown(f"**Lead Phone:** `{lead.get('phone', 'N/A')}`")
                            st.markdown(f"**Address:** {lead.get('address', 'N/A')}")

                            if va_phone and lead.get('phone'):
                                if st.button("📞 CALL LEAD", type="primary", key="call_lead_btn"):
                                    try:
                                        result = twilio.make_call(
                                            to_number=va_phone,
                                            from_number=selected_number,
                                            twiml=f'''<Response>
                                                <Say>Connecting you to {lead.get('owner_name', 'the property owner')}.</Say>
                                                <Dial callerId="{selected_number}" record="record-from-answer">
                                                    <Number>{lead.get('phone')}</Number>
                                                </Dial>
                                            </Response>''',
                                            record=True
                                        )
                                        if result.get('success'):
                                            st.success(f"📞 Calling your phone... Answer to connect!")
                                            st.session_state.active_call_sid = result.get('call_sid')
                                        else:
                                            st.error(f"Call failed: {result.get('error')}")
                                    except Exception as e:
                                        st.error(f"Error: {e}")
                            else:
                                if not va_phone:
                                    st.warning("⬆️ Enter your phone number above")
                                if not lead.get('phone'):
                                    st.warning("Lead has no phone number")
                        else:
                            st.info("👉 Click 'Get Next Lead' to load a lead from queue")

                with col2:
                    st.markdown("#### Lead Queue")

                    # Get next lead
                    if 'current_lead' not in st.session_state:
                        st.session_state.current_lead = None

                    if st.button("📋 Get Next Lead", key="get_lead_btn"):
                        st.session_state.current_lead = call_mgr.get_next_lead(va_id="dashboard_user")
                        st.rerun()

                    lead = st.session_state.current_lead

                    if lead:
                        st.markdown(f"""
                        **Address:** {lead.get('address', 'N/A')}

                        **Owner:** {lead.get('owner_name', 'N/A')}

                        **Phone:** `{lead.get('phone', 'N/A')}`

                        **Score:** {lead.get('motivation_score', 0)}/100

                        **Attempts:** {lead.get('call_attempts', 0)}
                        """)

                        st.markdown("---")
                        st.markdown("#### Record Disposition")

                        disposition = st.selectbox(
                            "Call Result",
                            options=[d.value for d in CallDisposition],
                            format_func=lambda x: x.replace('_', ' ').title()
                        )

                        notes = st.text_area("Notes", placeholder="Enter call notes...", key="call_notes")

                        callback_date = None
                        if disposition == CallDisposition.CALLBACK_REQUESTED.value:
                            callback_date = st.date_input("Callback Date")
                            callback_time = st.time_input("Callback Time")
                            if callback_date and callback_time:
                                callback_date = f"{callback_date}T{callback_time}"

                        if st.button("💾 Save & Next Lead"):
                            # Save to CallManager
                            call_mgr.record_call(
                                lead_id=lead['id'],
                                disposition=disposition,
                                notes=notes,
                                va_id="dashboard_user",
                                callback_date=callback_date
                            )

                            # Also log to CallTracker for unified tracking
                            try:
                                # Map disposition to CallTracker outcome
                                disposition_to_outcome = {
                                    'no_answer': 'No Answer',
                                    'voicemail': 'Left Voicemail',
                                    'wrong_number': 'Wrong Number',
                                    'not_interested': 'Not Interested',
                                    'callback_requested': 'Callback Requested',
                                    'interested': 'Interested',
                                    'appointment_set': 'Appointment Set',
                                    'do_not_call': 'Do Not Call',
                                    'disconnected': 'Disconnected'
                                }
                                outcome = disposition_to_outcome.get(disposition, 'No Answer')

                                tracker = CallTracker()
                                tracker.log_call(
                                    address=lead.get('address', 'Unknown'),
                                    owner_name=lead.get('owner_name', 'Unknown'),
                                    phone=lead.get('phone', ''),
                                    outcome=outcome,
                                    notes=notes,
                                    follow_up_date=str(callback_date).split('T')[0] if callback_date else None,
                                    follow_up_notes=f"Callback from Dialer" if callback_date else ''
                                )
                            except Exception as e:
                                pass  # Don't fail if tracker has issues

                            st.success("✅ Saved to Dialer & Call Tracker!")
                            st.session_state.current_lead = None
                            st.rerun()
                    else:
                        st.info("Click 'Get Next Lead' to start calling")

                    st.markdown("---")
                    st.markdown("#### Recent Calls")
                    recent = twilio.get_recent_calls(limit=5)
                    for call in recent[:5]:
                        if 'error' not in call:
                            st.write(f"📞 {call['to']} - {call['status']} ({call.get('duration', 0)}s)")

            # ========== TAB 3: Hot Leads ==========
            with tab3:
                st.markdown("### 🔥 Hot Leads")

                hot_leads = call_mgr.get_hot_leads()

                if hot_leads:
                    st.success(f"🔥 {len(hot_leads)} hot leads ready for follow-up!")

                    hot_df = pd.DataFrame(hot_leads)
                    display_cols = ['address', 'owner_name', 'phone', 'motivation_score', 'notes', 'last_called']
                    display_cols = [c for c in display_cols if c in hot_df.columns]
                    st.dataframe(hot_df[display_cols], use_container_width=True)

                    # Export button
                    if st.button("📤 Export Hot Leads"):
                        export_path = PROCESSED_DATA_DIR / 'hot_leads_export.csv'
                        count = call_mgr.export_hot_leads(str(export_path))
                        st.success(f"Exported {count} hot leads to {export_path.name}")
                else:
                    st.info("No hot leads yet. Start calling!")

                st.markdown("---")
                st.markdown("### ⏰ Scheduled Callbacks")

                callbacks = call_mgr.get_callbacks()
                if callbacks:
                    for cb in callbacks:
                        st.write(f"📅 {cb.get('next_callback', 'N/A')} - {cb.get('owner_name', 'N/A')} - {cb.get('phone', 'N/A')}")
                else:
                    st.info("No callbacks scheduled")

            # ========== TAB 4: Stats ==========
            with tab4:
                st.markdown("### 📈 Calling Statistics")

                va_stats = call_mgr.get_va_stats()

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Calls", va_stats['total_calls'])
                with col2:
                    st.metric("Hot Leads", va_stats['hot_leads'])
                with col3:
                    st.metric("Conversion Rate", f"{va_stats['conversion_rate']:.1f}%")

                st.markdown("---")
                st.markdown("#### Dispositions Breakdown")

                if va_stats['by_disposition']:
                    disp_df = pd.DataFrame([
                        {'Disposition': k.replace('_', ' ').title(), 'Count': v}
                        for k, v in va_stats['by_disposition'].items()
                    ])

                    fig = px.pie(disp_df, values='Count', names='Disposition', title='Call Outcomes')
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No call data yet")

                st.markdown("---")
                st.markdown("#### Call History")

                if call_mgr.call_history:
                    history_df = pd.DataFrame(call_mgr.call_history[-20:])  # Last 20 calls
                    st.dataframe(history_df, use_container_width=True)
                else:
                    st.info("No calls recorded yet")
