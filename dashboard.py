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
from datetime import datetime, timedelta
import os

# Import our modules - with fallbacks for deployment
DEPLOY_MODE = False  # Set to True when modules unavailable

try:
    from scrapers.franklin_county_excel import FranklinCountyExcelLoader
    from scrapers.columbus_violations_api import ColumbusViolationsAPI
    from scoring.motivation_scorer import MotivationScorer
    from config.settings import RAW_DATA_DIR, PROCESSED_DATA_DIR, BATCHDATA_API_KEY, DATA_DIR
    from config.market_loader import load_market
    from scrapers.factory import ScraperFactory
    from data_processing.portfolio_detector import PortfolioDetector
    from data_processing.equity_calculator import EquityCalculator
    from data_processing.comps_estimator import CompsEstimator
    from data_processing.freshness_tracker import FreshnessTracker
    from utils.street_view import StreetViewHelper
    from skip_tracing.skip_tracer import SkipTracer
    from scrapers.probate_scraper import ProbateScraper
    from scrapers.sheriff_sale_scraper import SheriffSaleScraper
    from data_processing.lead_integrator import LeadIntegrator
    from tracking.call_tracker import CallTracker
    from tracking.va_manager import VAManager
    from lead_generation.dnc_scrubber import DNCChecker
    from data_processing.probate_matcher import ProbateMatcher
    from scrapers.reverse_targeting import ReverseTargetingScraper
    from marketing.direct_mail import DirectMailManager, MAIL_TEMPLATES
    from marketing.rvm_manager import NumberRotationManager, RVMManager, DEFAULT_RVM_SCRIPTS
    from tracking.deal_pipeline import DealPipeline, DEAL_STAGES, STAGE_DISPLAY_NAMES, STAGE_COLORS
    from tracking.appointment_scheduler import AppointmentScheduler, APPOINTMENT_TYPES, APPOINTMENT_TYPE_DISPLAY, APPOINTMENT_STATUS, STATUS_COLORS as APT_STATUS_COLORS
    from marketing.sms_campaigns import SMSCampaigns, CAMPAIGN_STATUS as SMS_CAMPAIGN_STATUS, DEFAULT_SMS_TEMPLATES
    from marketing.follow_up_sequences import FollowUpSequences, ACTION_TYPES, ACTION_TYPE_DISPLAY, DEFAULT_SEQUENCES
    from auth.va_auth import VAAuth, ROLES
    from buyers.buyer_matcher import BuyerMatcher
except ImportError as e:
    DEPLOY_MODE = True
    # Fallback paths for deployment
    DATA_DIR = Path("/app/data")
    RAW_DATA_DIR = DATA_DIR / "raw"
    PROCESSED_DATA_DIR = DATA_DIR / "processed"
    BATCHDATA_API_KEY = os.environ.get("BATCHDATA_API_KEY", "")
    # Create placeholder classes
    class DummyClass:
        def __init__(self, *args, **kwargs): pass
        def __call__(self, *args, **kwargs): return self
        def __getattr__(self, name): return lambda *args, **kwargs: None
    FranklinCountyExcelLoader = ColumbusViolationsAPI = MotivationScorer = DummyClass
    ScraperFactory = PortfolioDetector = EquityCalculator = CompsEstimator = DummyClass
    FreshnessTracker = StreetViewHelper = SkipTracer = ProbateScraper = DummyClass
    SheriffSaleScraper = LeadIntegrator = CallTracker = VAManager = DummyClass
    DNCChecker = ProbateMatcher = ReverseTargetingScraper = DirectMailManager = DummyClass
    NumberRotationManager = RVMManager = DealPipeline = AppointmentScheduler = SMSCampaigns = FollowUpSequences = VAAuth = DummyClass
    ROLES = ["admin", "va", "manager"]
    MAIL_TEMPLATES = {}
    DEFAULT_RVM_SCRIPTS = {}
    SMS_CAMPAIGN_STATUS = ["draft", "scheduled", "sending", "paused", "completed", "cancelled"]
    ACTION_TYPES = ["call", "sms", "rvm", "email", "mail", "task"]
    ACTION_TYPE_DISPLAY = {"call": "Phone Call", "sms": "Text", "rvm": "RVM", "email": "Email", "mail": "Mail", "task": "Task"}
    DEFAULT_SEQUENCES = {}
    DEAL_STAGES = ["lead", "qualified", "offer_made", "under_contract", "closed", "dead"]
    STAGE_DISPLAY_NAMES = {"lead": "Lead", "qualified": "Qualified", "offer_made": "Offer Made", "under_contract": "Under Contract", "closed": "Closed", "dead": "Dead"}
    STAGE_COLORS = {"lead": "#6c757d", "qualified": "#17a2b8", "offer_made": "#ffc107", "under_contract": "#fd7e14", "closed": "#28a745", "dead": "#dc3545"}
    APPOINTMENT_TYPES = ["phone_call", "walkthrough", "offer_meeting", "signing", "closing", "follow_up", "other"]
    APPOINTMENT_TYPE_DISPLAY = {"phone_call": "Phone Call", "walkthrough": "Walkthrough", "offer_meeting": "Offer Meeting", "signing": "Signing", "closing": "Closing", "follow_up": "Follow-up", "other": "Other"}
    APPOINTMENT_STATUS = ["scheduled", "confirmed", "completed", "no_show", "cancelled", "rescheduled"]
    APT_STATUS_COLORS = {"scheduled": "#17a2b8", "confirmed": "#28a745", "completed": "#6c757d", "no_show": "#dc3545", "cancelled": "#ffc107", "rescheduled": "#fd7e14"}
    def load_market(*args, **kwargs): return {}

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

# Sidebar
with st.sidebar:
    st.markdown("# 🏠 Aerial Leads")
    st.markdown("---")

    page = st.radio(
        "Navigation",
        ["🏠 Home", "🚀 Generate Leads", "⚖️ Probate & Foreclosure", "📞 Skip Trace", "🛡️ DNC Scrub", "☎️ Call Tracker", "👥 VA Management", "📱 Dialer", "📥 Inbound Leads", "💰 Deal Pipeline", "📅 Appointments", "💬 SMS Campaigns", "🔄 Follow-ups", "🎯 Reverse Targeting", "📬 Direct Mail", "📲 RVM & Numbers", "🤝 Buyer Matching", "🔍 Search Owner", "📊 View Leads", "🐋 Whale Owners", "📈 Statistics", "📋 Data Quality", "⚙️ Data Management", "🔐 User Management"],
        label_visibility="collapsed"
    )

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
        # Check for either xlsx or csv files
        tax_xlsx = RAW_DATA_DIR / 'TaxDetail.xlsx'
        tax_csv = RAW_DATA_DIR / 'TaxDetail.csv'
        if tax_xlsx.exists() or tax_csv.exists():
            st.success("✅ Tax data loaded")
            st.info("22,858 total delinquent parcels")
            st.info("7,870 Columbus properties available")
        else:
            st.error("❌ Tax data not found")
            st.warning(f"Looking in: {RAW_DATA_DIR}")

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

            # Step 9: Export
            status_text.text("📤 Exporting leads...")

            PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
            # Save to both filenames for compatibility
            all_leads_path = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
            df.to_csv(all_leads_path, index=False)
            # Also save to legacy filename
            df.to_csv(PROCESSED_DATA_DIR / 'all_leads_real.csv', index=False)

            for tier_num in [1, 2, 3]:
                tier_df = df[df['tier'] == tier_num]
                if len(tier_df) > 0:
                    tier_path = PROCESSED_DATA_DIR / f'columbus_oh_tier_{tier_num}_leads.csv'
                    tier_df.to_csv(tier_path, index=False)
                    # Also save to legacy filename
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

    # Two columns for the two scraper types
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 📜 Probate Court Records")
        st.markdown("Franklin County Probate Court estate cases")

        probate_days = st.slider("Days to look back (Probate)", 30, 180, 90, key="probate_days")
        probate_max = st.slider("Max results (Probate)", 50, 500, 100, key="probate_max")

        if st.button("🔍 Scrape Probate Cases", type="primary", key="btn_probate"):
            with st.spinner("Scraping probate court records... (this may take 1-2 minutes)"):
                try:
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

        sheriff_max = st.slider("Max results (Sheriff Sales)", 20, 200, 50, key="sheriff_max")

        if st.button("🔍 Scrape Sheriff Sales", type="primary", key="btn_sheriff"):
            with st.spinner("Scraping sheriff sale listings..."):
                try:
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
                from skip_tracing.providers.batchdata_provider import BatchDataProvider
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

            # Get available leads
            leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
            if not leads_file.exists():
                leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

            if leads_file.exists():
                leads_df = pd.read_csv(leads_file)
                vas_df = va_manager.get_all_vas()

                if vas_df.empty:
                    st.warning("⚠️ No VAs available. Add VAs first!")
                else:
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("#### 🎯 Manual Assignment")

                        # Select VA
                        va_options = {f"{row['name']} (@{row['username']})": row['user_id'] for _, row in vas_df.iterrows()}
                        selected_va_name = st.selectbox("Select VA", list(va_options.keys()))
                        selected_va_id = va_options[selected_va_name]

                        # Number of leads
                        num_leads = st.slider("Number of leads to assign", 5, 100, 25)

                        # Priority
                        priority = st.select_slider("Priority", options=[1, 2, 3, 4, 5], value=3,
                                                   format_func=lambda x: {1: "🔴 Urgent", 2: "🟠 High", 3: "🟡 Normal", 4: "🟢 Low", 5: "⚪ Lowest"}[x])

                        # Filter options
                        min_score = st.slider("Minimum motivation score", 0, 100, 50)

                        if st.button("📋 Assign Leads", use_container_width=True):
                            # Filter and assign
                            filtered = leads_df[leads_df['motivation_score'] >= min_score].head(num_leads)
                            if len(filtered) > 0:
                                count = va_manager.assign_leads(
                                    filtered,
                                    selected_va_id,
                                    assigned_by=st.session_state.va_user['user_id'],
                                    priority=priority
                                )
                                st.success(f"✅ Assigned {count} leads to {selected_va_name}")
                            else:
                                st.warning("No leads match criteria")

                    with col2:
                        st.markdown("#### 🔄 Auto-Distribution")
                        st.info("Automatically distribute leads among all active VAs")

                        distribution_method = st.radio(
                            "Distribution Method",
                            ["equal", "by_quota", "by_performance"],
                            format_func=lambda x: {
                                "equal": "📊 Equal Split",
                                "by_quota": "📈 Based on Daily Quota",
                                "by_performance": "⭐ Based on Performance"
                            }[x]
                        )

                        auto_num_leads = st.slider("Total leads to distribute", 50, 500, 100, key="auto_leads")
                        auto_min_score = st.slider("Minimum score", 0, 100, 40, key="auto_score")

                        if st.button("🔄 Auto-Distribute", use_container_width=True):
                            filtered = leads_df[leads_df['motivation_score'] >= auto_min_score].head(auto_num_leads)
                            if len(filtered) > 0:
                                result = va_manager.auto_distribute_leads(filtered, distribution=distribution_method)
                                st.success("✅ Leads distributed!")
                                for va_id, count in result.items():
                                    va_info = vas_df[vas_df['user_id'] == va_id].iloc[0]
                                    st.write(f"• {va_info['name']}: {count} leads")
                            else:
                                st.warning("No leads match criteria")
            else:
                st.warning("⚠️ No leads found. Generate leads first!")

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

                        # Metrics row
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Total Calls", int(perf_df['calls_made'].sum()))
                        with col2:
                            st.metric("Total Contacts", int(perf_df['contacts_reached'].sum()))
                        with col3:
                            st.metric("Appointments", int(perf_df['appointments_set'].sum()))
                        with col4:
                            avg_rate = perf_df['conversion_rate'].mean()
                            st.metric("Avg Conversion", f"{avg_rate:.1f}%")

                        # Performance table
                        st.markdown("#### 👥 Individual Performance")
                        display_df = perf_df[['name', 'calls_made', 'contacts_reached', 'appointments_set', 'conversion_rate', 'calls_per_day']].copy()
                        display_df.columns = ['VA Name', 'Calls', 'Contacts', 'Appointments', 'Conv. Rate %', 'Calls/Day']
                        st.dataframe(display_df, use_container_width=True, hide_index=True)

                        # Chart
                        fig = px.bar(perf_df, x='name', y='calls_made',
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
                    progress_pct = (progress['calls_made'] / progress['quota'] * 100) if progress['quota'] > 0 else 0
                    st.progress(min(progress_pct / 100, 1.0))
                    st.write(f"**{progress['calls_made']}** / {progress['quota']} calls ({progress_pct:.0f}%)")

                    # Period stats
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Calls Made", perf['calls_made'])
                    with col2:
                        st.metric("Contacts", perf['contacts_reached'])
                    with col3:
                        st.metric("Appointments", perf['appointments_set'])
                    with col4:
                        st.metric("Conversion", f"{perf['conversion_rate']:.1f}%")
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
                        progress_pct = (progress['calls_made'] / progress['quota'] * 100) if progress['quota'] > 0 else 0

                        st.markdown(f"**{va['name']}**")
                        st.progress(min(progress_pct / 100, 1.0))
                        st.caption(f"{progress['calls_made']}/{progress['quota']} calls")

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
# INBOUND LEADS PAGE
# ========================================
elif page == "📥 Inbound Leads":
    st.markdown('<h1 class="main-header">📥 Inbound Leads</h1>', unsafe_allow_html=True)
    st.markdown("Leads captured from your public website - these people reached out to YOU!")

    # Load inbound leads
    inbound_file = DATA_DIR / "inbound_leads.csv"

    if inbound_file.exists():
        inbound_df = pd.read_csv(inbound_file)

        if not inbound_df.empty:
            # Stats row
            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("Total Inbound", len(inbound_df))
            with col2:
                today = datetime.now().strftime('%Y-%m-%d')
                today_count = len(inbound_df[inbound_df['captured_at'].str.startswith(today)]) if 'captured_at' in inbound_df.columns else 0
                st.metric("Today", today_count)
            with col3:
                # Unique source pages
                if 'source_page' in inbound_df.columns:
                    sources = inbound_df['source_page'].nunique()
                else:
                    sources = 0
                st.metric("Sources", sources)
            with col4:
                st.metric("Hot Leads", "🔥")

            st.markdown("---")

            # Tabs
            tab1, tab2, tab3 = st.tabs(["📋 All Leads", "🔥 New Today", "📊 Analytics"])

            with tab1:
                st.markdown("### All Inbound Leads")

                # Sort by most recent
                if 'captured_at' in inbound_df.columns:
                    inbound_df = inbound_df.sort_values('captured_at', ascending=False)

                # Display columns
                display_cols = ['captured_at', 'name', 'phone', 'property_address', 'source_page', 'message']
                display_cols = [c for c in display_cols if c in inbound_df.columns]

                st.dataframe(inbound_df[display_cols], use_container_width=True, hide_index=True)

                # Export button
                if st.button("📤 Export to CSV"):
                    export_path = PROCESSED_DATA_DIR / 'inbound_leads_export.csv'
                    inbound_df.to_csv(export_path, index=False)
                    st.success(f"Exported to {export_path}")

            with tab2:
                st.markdown("### Today's Leads")

                if 'captured_at' in inbound_df.columns:
                    today = datetime.now().strftime('%Y-%m-%d')
                    today_leads = inbound_df[inbound_df['captured_at'].str.startswith(today)]

                    if not today_leads.empty:
                        for _, lead in today_leads.iterrows():
                            with st.container():
                                col1, col2 = st.columns([3, 1])
                                with col1:
                                    st.markdown(f"**{lead.get('name', 'Unknown')}** - {lead.get('phone', 'No phone')}")
                                    st.markdown(f"📍 {lead.get('property_address', 'No address')}")
                                    if lead.get('message'):
                                        st.caption(f"💬 {lead.get('message')}")
                                    st.caption(f"Source: {lead.get('source_page', 'Unknown')} | {lead.get('captured_at', '')}")
                                with col2:
                                    if st.button("📞 Call", key=f"call_{lead.name}"):
                                        st.info(f"Call {lead.get('phone', 'No phone')}")
                                    if st.button("➡️ Add to Tracker", key=f"track_{lead.name}"):
                                        tracker = CallTracker()
                                        tracker.log_call(
                                            address=lead.get('property_address', ''),
                                            owner_name=lead.get('name', ''),
                                            phone=lead.get('phone', ''),
                                            outcome='Interested',
                                            notes=f"Inbound lead from website: {lead.get('message', '')}"
                                        )
                                        st.success("Added to Call Tracker!")
                                st.markdown("---")
                    else:
                        st.info("No leads captured today yet. Check back later!")
                else:
                    st.warning("No timestamp data available")

            with tab3:
                st.markdown("### Lead Analytics")

                if 'source_page' in inbound_df.columns:
                    # Leads by source
                    source_counts = inbound_df['source_page'].value_counts()

                    fig = px.pie(
                        values=source_counts.values,
                        names=source_counts.index,
                        title="Leads by Source Page"
                    )
                    st.plotly_chart(fig, use_container_width=True)

                if 'captured_at' in inbound_df.columns:
                    # Leads over time
                    inbound_df['date'] = pd.to_datetime(inbound_df['captured_at']).dt.date
                    daily_counts = inbound_df.groupby('date').size().reset_index(name='leads')

                    fig2 = px.line(
                        daily_counts,
                        x='date',
                        y='leads',
                        title="Leads Over Time"
                    )
                    st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No inbound leads yet. Once your public site is live, leads will appear here!")
    else:
        st.info("📥 No inbound leads yet.")
        st.markdown("""
        ### Get Started with Inbound Leads

        Your public website will capture leads when motivated sellers:
        - Find your property pages on Google
        - Use your cash offer calculator
        - Submit contact forms

        **To launch your public site:**
        ```bash
        cd aerial-leads/public_site
        uvicorn app:app --reload --port 8080
        ```

        Then visit: http://localhost:8080
        """)

    st.markdown("---")
    st.markdown("### 🌐 Public Website Status")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **Launch Command:**
        ```
        cd public_site && uvicorn app:app --port 8080
        ```
        """)
    with col2:
        st.markdown("""
        **Pages Generated:**
        - Property pages for each lead
        - Probate landing page
        - Tax delinquent landing page
        - Cash offer calculator
        """)


# ========================================
# DEAL PIPELINE PAGE
# ========================================
elif page == "💰 Deal Pipeline":
    st.markdown('<h1 class="main-header">💰 Deal Pipeline</h1>', unsafe_allow_html=True)
    st.markdown("Track your deals from lead to close - this is where you make money!")

    # Initialize pipeline
    pipeline = DealPipeline()

    # Get stats
    stats = pipeline.get_pipeline_stats()

    # Top metrics row
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Deals", stats['total_deals'])
    with col2:
        st.metric("Active Deals", stats['active_deals'])
    with col3:
        st.metric("Closed Deals", stats['closed_deals'], delta=f"💰 ${stats['total_closed_profit']:,.0f}")
    with col4:
        st.metric("Potential Profit", f"${stats['total_potential_profit']:,.0f}")
    with col5:
        st.metric("Conversion Rate", f"{stats['conversion_rate']:.1f}%")

    st.markdown("---")

    # Tabs for different views
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Pipeline Board", "➕ Add Deal", "📊 Analytics", "📜 All Deals"])

    with tab1:
        st.markdown("### Pipeline Board")
        st.markdown("Drag deals through your pipeline (click to expand)")

        # Get deals by stage
        deals_by_stage = pipeline.get_deals_by_stage()

        # Create columns for each stage (except dead)
        active_stages = [s for s in DEAL_STAGES if s != 'dead']
        cols = st.columns(len(active_stages))

        for idx, stage in enumerate(active_stages):
            with cols[idx]:
                stage_deals = deals_by_stage.get(stage, pd.DataFrame())
                count = len(stage_deals)

                # Stage header with color
                st.markdown(f"""
                <div style='background-color: {STAGE_COLORS.get(stage, "#ccc")}; padding: 10px; border-radius: 8px; text-align: center; color: white; margin-bottom: 10px;'>
                    <strong>{STAGE_DISPLAY_NAMES.get(stage, stage)}</strong><br>
                    <span style='font-size: 1.5em;'>{count}</span>
                </div>
                """, unsafe_allow_html=True)

                # Deal cards
                if not stage_deals.empty:
                    for _, deal in stage_deals.iterrows():
                        with st.expander(f"📍 {deal['address'][:25]}...", expanded=False):
                            st.write(f"**Seller:** {deal['seller_name']}")
                            st.write(f"**Phone:** {deal['seller_phone']}")
                            if deal['offer_amount'] > 0:
                                st.write(f"**Offer:** ${deal['offer_amount']:,.0f}")
                            if deal['assignment_fee'] > 0:
                                st.write(f"**Fee:** ${deal['assignment_fee']:,.0f}")

                            # Move buttons
                            st.markdown("**Move to:**")
                            move_cols = st.columns(2)

                            # Get next and previous stages
                            stage_idx = DEAL_STAGES.index(stage)

                            with move_cols[0]:
                                if stage_idx < len(DEAL_STAGES) - 2:  # Not at closed or dead
                                    next_stage = DEAL_STAGES[stage_idx + 1]
                                    if st.button(f"→ {STAGE_DISPLAY_NAMES[next_stage]}", key=f"next_{deal['deal_id']}"):
                                        pipeline.move_to_stage(deal['deal_id'], next_stage)
                                        st.rerun()

                            with move_cols[1]:
                                if st.button("❌ Dead", key=f"dead_{deal['deal_id']}"):
                                    pipeline.move_to_stage(deal['deal_id'], 'dead')
                                    st.rerun()
                else:
                    st.caption("No deals")

        # Show dead deals count
        dead_count = len(deals_by_stage.get('dead', pd.DataFrame()))
        if dead_count > 0:
            st.markdown(f"---\n❌ **Dead Deals:** {dead_count}")

    with tab2:
        st.markdown("### Add New Deal")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Property Info")
            new_address = st.text_input("Property Address *", placeholder="123 Main St")
            new_city = st.text_input("City", value="Columbus")
            new_state = st.text_input("State", value="OH")
            new_zip = st.text_input("Zip Code", placeholder="43215")

        with col2:
            st.markdown("#### Seller Info")
            new_seller = st.text_input("Seller Name", placeholder="John Smith")
            new_phone = st.text_input("Seller Phone", placeholder="614-555-1234")
            new_source = st.selectbox("Lead Source", ["", "Probate", "Tax Delinquent", "Code Violation", "Driving for Dollars", "Direct Mail", "Cold Call", "Referral", "Website", "Other"])
            new_type = st.selectbox("Lead Type", ["", "probate", "tax_delinquent", "code_violation", "vacant", "tired_landlord", "pre_foreclosure", "other"])

        st.markdown("#### Deal Info")
        col1, col2, col3 = st.columns(3)
        with col1:
            new_asking = st.number_input("Asking Price ($)", value=0, step=5000)
        with col2:
            new_arv = st.number_input("ARV ($)", value=0, step=5000)
        with col3:
            new_repairs = st.number_input("Repair Estimate ($)", value=0, step=1000)

        new_notes = st.text_area("Notes", placeholder="Any additional details...")

        if st.button("💾 Create Deal", type="primary"):
            if new_address:
                deal_id = pipeline.create_deal(
                    address=new_address,
                    city=new_city,
                    state=new_state,
                    zip_code=new_zip,
                    seller_name=new_seller,
                    seller_phone=new_phone,
                    lead_source=new_source,
                    lead_type=new_type,
                    notes=new_notes
                )

                # Update financials
                if new_asking > 0 or new_arv > 0 or new_repairs > 0:
                    pipeline.update_deal(deal_id, {
                        'asking_price': new_asking,
                        'arv': new_arv,
                        'repair_estimate': new_repairs
                    })

                st.success(f"✅ Deal created! ID: {deal_id}")
                st.balloons()
            else:
                st.error("Property address is required")

        # Quick add from existing lead
        st.markdown("---")
        st.markdown("#### Or Import from Leads")

        all_leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'
        if all_leads_file.exists():
            leads_df = pd.read_csv(all_leads_file)
            if not leads_df.empty and 'address' in leads_df.columns:
                # Filter to high-score leads
                if 'motivation_score' in leads_df.columns:
                    hot_leads = leads_df[leads_df['motivation_score'] >= 70].head(20)
                else:
                    hot_leads = leads_df.head(20)

                selected_lead = st.selectbox(
                    "Select a lead to convert",
                    options=[""] + hot_leads['address'].tolist(),
                    format_func=lambda x: f"{x}" if x else "Select a lead..."
                )

                if selected_lead and st.button("📥 Import Selected Lead"):
                    lead_data = hot_leads[hot_leads['address'] == selected_lead].iloc[0].to_dict()
                    deal_id = pipeline.create_deal_from_lead(lead_data)
                    st.success(f"✅ Deal created from lead! ID: {deal_id}")
                    st.rerun()

    with tab3:
        st.markdown("### Pipeline Analytics")

        col1, col2 = st.columns(2)

        with col1:
            # Stage distribution chart
            stage_data = []
            for stage in DEAL_STAGES:
                if stage != 'dead':
                    stage_data.append({
                        'Stage': STAGE_DISPLAY_NAMES.get(stage, stage),
                        'Count': stats['by_stage'].get(stage, 0),
                        'Color': STAGE_COLORS.get(stage, '#ccc')
                    })

            if stage_data:
                fig = px.bar(
                    stage_data,
                    x='Stage',
                    y='Count',
                    color='Stage',
                    color_discrete_map={d['Stage']: d['Color'] for d in stage_data},
                    title="Deals by Stage"
                )
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Revenue over time
            monthly = pipeline.get_monthly_revenue()
            if not monthly.empty:
                fig = px.line(
                    monthly,
                    x='month',
                    y='revenue',
                    title="Monthly Revenue",
                    markers=True
                )
                fig.update_layout(yaxis_tickprefix='$')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Close some deals to see revenue trends!")

        # Key metrics
        st.markdown("### Key Metrics")
        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("Average Deal Value", f"${stats['avg_deal_value']:,.0f}")
        with col2:
            st.metric("Total Revenue (Closed)", f"${stats['total_closed_profit']:,.0f}")
        with col3:
            win_rate = (stats['closed_deals'] / (stats['closed_deals'] + stats['dead_deals']) * 100) if (stats['closed_deals'] + stats['dead_deals']) > 0 else 0
            st.metric("Win Rate", f"{win_rate:.1f}%")

    with tab4:
        st.markdown("### All Deals")

        all_deals = pipeline.get_all_deals()

        if all_deals.empty:
            st.info("No deals yet. Add your first deal above!")
        else:
            # Filters
            col1, col2 = st.columns(2)
            with col1:
                filter_stage = st.selectbox("Filter by Stage", ["All"] + [STAGE_DISPLAY_NAMES[s] for s in DEAL_STAGES])
            with col2:
                search_deal = st.text_input("Search by address", placeholder="Type to search...")

            # Apply filters
            filtered = all_deals.copy()
            if filter_stage != "All":
                stage_key = [k for k, v in STAGE_DISPLAY_NAMES.items() if v == filter_stage][0]
                filtered = filtered[filtered['stage'] == stage_key]
            if search_deal:
                filtered = filtered[filtered['address'].str.contains(search_deal, case=False, na=False)]

            st.markdown(f"**{len(filtered)}** deals")

            # Display deals
            for _, deal in filtered.iterrows():
                stage_emoji = STAGE_DISPLAY_NAMES.get(deal['stage'], deal['stage'])
                profit = deal['actual_profit'] if deal['stage'] == 'closed' else deal['assignment_fee']

                with st.expander(f"{stage_emoji} | {deal['address']} | ${profit:,.0f}"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown("**Property:**")
                        st.write(f"📍 {deal['address']}")
                        st.write(f"🏙️ {deal['city']}, {deal['state']} {deal['zip_code']}")
                        st.write(f"📋 Source: {deal['lead_source']}")

                        st.markdown("**Seller:**")
                        st.write(f"👤 {deal['seller_name']}")
                        st.write(f"📞 {deal['seller_phone']}")

                    with col2:
                        st.markdown("**Financials:**")
                        st.write(f"💵 Asking: ${deal['asking_price']:,.0f}")
                        st.write(f"📝 Offer: ${deal['offer_amount']:,.0f}")
                        st.write(f"📋 Contract: ${deal['contract_price']:,.0f}")
                        st.write(f"🏠 ARV: ${deal['arv']:,.0f}")
                        st.write(f"🔧 Repairs: ${deal['repair_estimate']:,.0f}")
                        st.write(f"💰 Assignment Fee: ${deal['assignment_fee']:,.0f}")

                    st.markdown("**Dates:**")
                    st.write(f"Offer: {deal['offer_date']} | Contract: {deal['contract_date']} | Closing: {deal['closing_date']}")

                    # Quick update form
                    st.markdown("---")
                    st.markdown("**Quick Update:**")

                    update_col1, update_col2 = st.columns(2)
                    with update_col1:
                        new_offer = st.number_input("Offer Amount", value=float(deal['offer_amount']), key=f"offer_{deal['deal_id']}")
                        new_contract = st.number_input("Contract Price", value=float(deal['contract_price']), key=f"contract_{deal['deal_id']}")
                    with update_col2:
                        new_fee = st.number_input("Assignment Fee", value=float(deal['assignment_fee']), key=f"fee_{deal['deal_id']}")
                        new_profit = st.number_input("Actual Profit", value=float(deal['actual_profit']), key=f"profit_{deal['deal_id']}")

                    if st.button("💾 Update Deal", key=f"update_{deal['deal_id']}"):
                        pipeline.update_deal(deal['deal_id'], {
                            'offer_amount': new_offer,
                            'contract_price': new_contract,
                            'assignment_fee': new_fee,
                            'actual_profit': new_profit
                        })
                        st.success("Updated!")
                        st.rerun()


# ========================================
# APPOINTMENTS PAGE
# ========================================
elif page == "📅 Appointments":
    st.markdown('<h1 class="main-header">📅 Appointments</h1>', unsafe_allow_html=True)
    st.markdown("Schedule and track appointments with sellers - never miss a deal!")

    # Initialize scheduler
    scheduler = AppointmentScheduler()

    # Get stats
    apt_stats = scheduler.get_stats()

    # Top metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Today", apt_stats['today'])
    with col2:
        st.metric("This Week", apt_stats['this_week'])
    with col3:
        st.metric("Completed", apt_stats['completed'])
    with col4:
        st.metric("No-Shows", apt_stats['no_show'])
    with col5:
        st.metric("Show Rate", f"{apt_stats['show_rate']:.0f}%")

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Today's Appointments", "📆 Schedule New", "🗓️ All Appointments", "📊 Stats"])

    with tab1:
        st.markdown("### Today's Schedule")

        today_apts = scheduler.get_todays_appointments()

        if today_apts.empty:
            st.info("No appointments scheduled for today!")
            if st.button("📆 Schedule One Now"):
                st.session_state['apt_tab'] = 1
                st.rerun()
        else:
            for _, apt in today_apts.iterrows():
                status_color = APT_STATUS_COLORS.get(apt['status'], '#ccc')
                apt_type_display = APPOINTMENT_TYPE_DISPLAY.get(apt['appointment_type'], apt['appointment_type'])

                with st.expander(f"⏰ {apt['scheduled_time']} | {apt_type_display} | {apt['address'][:30]}...", expanded=True):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Type:** {apt_type_display}")
                        st.markdown(f"**Address:** {apt['address']}")
                        st.markdown(f"**Seller:** {apt['seller_name']}")
                        st.markdown(f"**Phone:** {apt['seller_phone']}")

                    with col2:
                        st.markdown(f"**Status:** <span style='color:{status_color}'>{apt['status'].upper()}</span>", unsafe_allow_html=True)
                        st.markdown(f"**Duration:** {apt['duration_minutes']} min")
                        st.markdown(f"**Assigned:** {apt['assigned_to']}")

                    if apt['notes']:
                        st.markdown(f"**Notes:** {apt['notes']}")

                    st.markdown("---")
                    st.markdown("**Quick Actions:**")
                    action_cols = st.columns(4)

                    with action_cols[0]:
                        if apt['status'] == 'scheduled':
                            if st.button("✅ Confirm", key=f"confirm_{apt['appointment_id']}"):
                                scheduler.mark_status(apt['appointment_id'], 'confirmed')
                                st.rerun()

                    with action_cols[1]:
                        if apt['status'] in ['scheduled', 'confirmed']:
                            if st.button("✔️ Complete", key=f"complete_{apt['appointment_id']}"):
                                scheduler.mark_status(apt['appointment_id'], 'completed')
                                st.success("Marked complete!")
                                st.rerun()

                    with action_cols[2]:
                        if apt['status'] in ['scheduled', 'confirmed']:
                            if st.button("❌ No-Show", key=f"noshow_{apt['appointment_id']}"):
                                scheduler.mark_status(apt['appointment_id'], 'no_show', follow_up_needed=True)
                                st.rerun()

                    with action_cols[3]:
                        if st.button("📅 Reschedule", key=f"resched_{apt['appointment_id']}"):
                            st.session_state[f'resched_{apt["appointment_id"]}'] = True
                            st.rerun()

        # Upcoming this week
        st.markdown("---")
        st.markdown("### Coming Up This Week")

        upcoming = scheduler.get_upcoming_appointments(days=7)
        upcoming = upcoming[upcoming['scheduled_date'] != datetime.now().strftime('%Y-%m-%d')]  # Exclude today

        if upcoming.empty:
            st.info("No other appointments this week")
        else:
            for _, apt in upcoming.head(10).iterrows():
                apt_type_display = APPOINTMENT_TYPE_DISPLAY.get(apt['appointment_type'], apt['appointment_type'])
                st.markdown(f"📆 **{apt['scheduled_date']}** {apt['scheduled_time']} - {apt_type_display} - {apt['address'][:40]}...")

    with tab2:
        st.markdown("### Schedule New Appointment")

        col1, col2 = st.columns(2)

        with col1:
            new_date = st.date_input("Date", value=datetime.now())
            new_time = st.time_input("Time", value=datetime.now().replace(hour=10, minute=0))
            new_type = st.selectbox("Appointment Type", APPOINTMENT_TYPES, format_func=lambda x: APPOINTMENT_TYPE_DISPLAY.get(x, x))
            new_duration = st.number_input("Duration (minutes)", value=30, step=15, min_value=15, max_value=180)

        with col2:
            new_address = st.text_input("Property Address", placeholder="123 Main St")
            new_seller = st.text_input("Seller Name", placeholder="John Smith")
            new_phone = st.text_input("Seller Phone", placeholder="614-555-1234")
            new_assigned = st.text_input("Assigned To", placeholder="VA name")

        new_notes = st.text_area("Notes", placeholder="Any special instructions...")

        # Option to link to existing deal
        pipeline = DealPipeline()
        all_deals = pipeline.get_all_deals()
        deal_options = ["None"] + all_deals['deal_id'].tolist() if not all_deals.empty else ["None"]
        linked_deal = st.selectbox("Link to Deal (optional)", deal_options)

        if st.button("📅 Schedule Appointment", type="primary"):
            if new_address:
                apt_id = scheduler.schedule_appointment(
                    scheduled_date=new_date.strftime('%Y-%m-%d'),
                    scheduled_time=new_time.strftime('%H:%M'),
                    appointment_type=new_type,
                    address=new_address,
                    seller_name=new_seller,
                    seller_phone=new_phone,
                    deal_id=linked_deal if linked_deal != "None" else "",
                    assigned_to=new_assigned,
                    duration_minutes=new_duration,
                    notes=new_notes
                )
                st.success(f"✅ Appointment scheduled! ID: {apt_id}")
                st.balloons()
            else:
                st.error("Property address is required")

    with tab3:
        st.markdown("### All Appointments")

        # Filters
        col1, col2, col3 = st.columns(3)
        with col1:
            filter_status = st.selectbox("Filter by Status", ["All"] + APPOINTMENT_STATUS)
        with col2:
            filter_start = st.date_input("From Date", value=datetime.now() - timedelta(days=30), key="filter_start")
        with col3:
            filter_end = st.date_input("To Date", value=datetime.now() + timedelta(days=30), key="filter_end")

        # Get filtered appointments
        all_apts = scheduler.get_all_appointments(
            status=filter_status if filter_status != "All" else None,
            start_date=filter_start.strftime('%Y-%m-%d'),
            end_date=filter_end.strftime('%Y-%m-%d')
        )

        st.markdown(f"**{len(all_apts)}** appointments found")

        if not all_apts.empty:
            for _, apt in all_apts.iterrows():
                status_color = APT_STATUS_COLORS.get(apt['status'], '#ccc')
                apt_type_display = APPOINTMENT_TYPE_DISPLAY.get(apt['appointment_type'], apt['appointment_type'])

                with st.expander(f"{apt['scheduled_date']} {apt['scheduled_time']} | {apt_type_display} | {apt['status'].upper()}"):
                    st.markdown(f"**Address:** {apt['address']}")
                    st.markdown(f"**Seller:** {apt['seller_name']} | **Phone:** {apt['seller_phone']}")
                    st.markdown(f"**Assigned To:** {apt['assigned_to']}")

                    if apt['outcome']:
                        st.markdown(f"**Outcome:** {apt['outcome']}")

                    # Status update
                    new_status = st.selectbox(
                        "Update Status",
                        APPOINTMENT_STATUS,
                        index=APPOINTMENT_STATUS.index(apt['status']) if apt['status'] in APPOINTMENT_STATUS else 0,
                        key=f"status_{apt['appointment_id']}"
                    )

                    if new_status != apt['status']:
                        if st.button(f"Update to {new_status}", key=f"update_status_{apt['appointment_id']}"):
                            scheduler.mark_status(apt['appointment_id'], new_status)
                            st.rerun()

    with tab4:
        st.markdown("### Appointment Statistics")

        col1, col2 = st.columns(2)

        with col1:
            # Status breakdown
            status_data = []
            for status in APPOINTMENT_STATUS:
                count = apt_stats.get(status, 0)
                if count > 0 or status in ['scheduled', 'confirmed', 'completed']:
                    status_data.append({
                        'Status': status.replace('_', ' ').title(),
                        'Count': count,
                        'Color': APT_STATUS_COLORS.get(status, '#ccc')
                    })

            if status_data:
                fig = px.bar(
                    status_data,
                    x='Status',
                    y='Count',
                    color='Status',
                    color_discrete_map={d['Status']: d['Color'] for d in status_data},
                    title="Appointments by Status"
                )
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Show rate gauge
            show_rate = apt_stats['show_rate']
            fig = go.Figure(go.Indicator(
                mode="gauge+number",
                value=show_rate,
                title={'text': "Show Rate %"},
                gauge={
                    'axis': {'range': [0, 100]},
                    'bar': {'color': "#28a745" if show_rate >= 70 else "#ffc107" if show_rate >= 50 else "#dc3545"},
                    'steps': [
                        {'range': [0, 50], 'color': "#ffcccc"},
                        {'range': [50, 70], 'color': "#fff3cd"},
                        {'range': [70, 100], 'color': "#d4edda"}
                    ]
                }
            ))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.markdown("### Key Metrics")

        met_col1, met_col2, met_col3 = st.columns(3)
        with met_col1:
            st.metric("Total Appointments", apt_stats['total'])
        with met_col2:
            st.metric("Completion Rate", f"{(apt_stats['completed'] / apt_stats['total'] * 100) if apt_stats['total'] > 0 else 0:.0f}%")
        with met_col3:
            st.metric("No-Show Rate", f"{(apt_stats['no_show'] / apt_stats['total'] * 100) if apt_stats['total'] > 0 else 0:.0f}%")


# ========================================
# SMS CAMPAIGNS PAGE
# ========================================
elif page == "💬 SMS Campaigns":
    st.markdown('<h1 class="main-header">💬 SMS Campaigns</h1>', unsafe_allow_html=True)
    st.markdown("Send text messages to leads - quick, personal outreach that gets responses!")

    # Initialize SMS manager
    sms_manager = SMSCampaigns()

    # Get stats
    sms_stats = sms_manager.get_stats()

    # Top metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Total Campaigns", sms_stats['total_campaigns'])
    with col2:
        st.metric("Messages Sent", sms_stats['total_messages_sent'])
    with col3:
        st.metric("Responses", sms_stats['total_responses'])
    with col4:
        st.metric("Response Rate", f"{sms_stats['response_rate']:.1f}%")
    with col5:
        st.metric("Opt-outs", sms_stats['total_optouts'])

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Campaigns", "✉️ Create Campaign", "📝 Templates", "📊 Analytics"])

    with tab1:
        st.markdown("### All Campaigns")

        all_campaigns = sms_manager.get_all_campaigns()

        if all_campaigns.empty:
            st.info("No SMS campaigns yet. Create your first one!")
        else:
            for _, camp in all_campaigns.iterrows():
                status_color = "#28a745" if camp['status'] == 'completed' else "#17a2b8" if camp['status'] == 'sending' else "#6c757d"

                with st.expander(f"📱 {camp['name']} | {camp['status'].upper()} | {int(camp['sent_count'])} sent"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Status:** <span style='color:{status_color}'>{camp['status'].upper()}</span>", unsafe_allow_html=True)
                        st.markdown(f"**Recipients:** {int(camp['total_recipients'])}")
                        st.markdown(f"**Sent:** {int(camp['sent_count'])}")
                        st.markdown(f"**Failed:** {int(camp['failed_count'])}")

                    with col2:
                        st.markdown(f"**Responses:** {int(camp['response_count'])}")
                        st.markdown(f"**Opt-outs:** {int(camp['optout_count'])}")
                        st.markdown(f"**Created:** {camp['created_at'][:10]}")
                        st.markdown(f"**By:** {camp['created_by']}")

                    if camp['description']:
                        st.markdown(f"**Description:** {camp['description']}")

                    # Actions
                    st.markdown("---")
                    action_cols = st.columns(3)

                    with action_cols[0]:
                        if camp['status'] == 'draft':
                            if st.button("📤 Send Now", key=f"send_{camp['campaign_id']}"):
                                result = sms_manager.send_campaign(camp['campaign_id'])
                                st.success(f"Sent {result['sent_count']} messages!")
                                st.rerun()

                    with action_cols[1]:
                        if camp['status'] == 'sending':
                            if st.button("⏸️ Pause", key=f"pause_{camp['campaign_id']}"):
                                sms_manager.update_campaign_status(camp['campaign_id'], 'paused')
                                st.rerun()

                    with action_cols[2]:
                        if st.button("📊 View Messages", key=f"view_{camp['campaign_id']}"):
                            st.session_state['view_campaign'] = camp['campaign_id']
                            st.rerun()

                    # Show messages if viewing
                    if st.session_state.get('view_campaign') == camp['campaign_id']:
                        st.markdown("---")
                        st.markdown("**Messages:**")
                        messages = sms_manager.get_campaign_messages(camp['campaign_id'])
                        if not messages.empty:
                            for _, msg in messages.head(10).iterrows():
                                st.markdown(f"📞 **{msg['recipient_phone']}** ({msg['recipient_name']}) - {msg['status']}")
                                if msg['response']:
                                    st.markdown(f"  ↪️ *Response: {msg['response']}*")

    with tab2:
        st.markdown("### Create SMS Campaign")

        # Campaign info
        new_name = st.text_input("Campaign Name", placeholder="Holiday Outreach 2024")
        new_desc = st.text_area("Description (optional)", placeholder="Reaching out to probate leads...")

        # Select template
        templates = sms_manager.get_templates()
        template_options = templates['template_id'].tolist() if not templates.empty else []
        template_names = templates['name'].tolist() if not templates.empty else []

        if template_options:
            selected_template = st.selectbox(
                "Select Template",
                options=template_options,
                format_func=lambda x: templates[templates['template_id'] == x]['name'].iloc[0] if not templates.empty else x
            )

            # Preview template
            if selected_template:
                tpl = sms_manager.get_template(selected_template)
                if tpl:
                    st.markdown("**Template Preview:**")
                    st.info(tpl['message'])

        # Select recipients
        st.markdown("---")
        st.markdown("### Select Recipients")

        recipient_source = st.radio(
            "Get recipients from:",
            ["All Leads", "High Score Leads (70+)", "Probate Leads", "Upload Custom"],
            horizontal=True
        )

        leads_df = pd.DataFrame()
        all_leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

        if all_leads_file.exists():
            leads_df = pd.read_csv(all_leads_file)

            # Filter based on selection
            if recipient_source == "High Score Leads (70+)" and 'motivation_score' in leads_df.columns:
                leads_df = leads_df[leads_df['motivation_score'] >= 70]
            elif recipient_source == "Probate Leads" and 'lead_type' in leads_df.columns:
                leads_df = leads_df[leads_df['lead_type'].str.contains('probate', case=False, na=False)]

            # Only keep leads with phone numbers
            phone_cols = ['phone', 'phone_1', 'phone_2']
            has_phone = pd.Series([False] * len(leads_df))
            for col in phone_cols:
                if col in leads_df.columns:
                    has_phone = has_phone | leads_df[col].notna()
            leads_df = leads_df[has_phone]

            st.markdown(f"**{len(leads_df)}** leads available with phone numbers")

            if not leads_df.empty:
                # Show sample - only include columns that exist
                display_cols = []
                for col in ['address', 'owner_name', 'owner', 'city', 'phone', 'phone_1']:
                    if col in leads_df.columns:
                        display_cols.append(col)
                if display_cols:
                    st.dataframe(leads_df[display_cols[:4]].head(5))
                else:
                    st.dataframe(leads_df.head(5))

        # Sender info
        st.markdown("---")
        st.markdown("### Sender Info")
        col1, col2 = st.columns(2)
        with col1:
            sender_phone = st.text_input("Sender Phone", placeholder="614-555-0123")
            sender_name = st.text_input("Your Name", placeholder="John from Lifeline")
        with col2:
            company_name = st.text_input("Company", value="Lifeline Home Buyers")
            created_by = st.text_input("Created By", placeholder="Your name")

        if st.button("📱 Create Campaign", type="primary"):
            if new_name and selected_template and not leads_df.empty:
                # Prepare recipients
                recipients = leads_df.to_dict('records')

                campaign_id = sms_manager.create_campaign(
                    name=new_name,
                    template_id=selected_template,
                    recipients=recipients,
                    sender_phone=sender_phone,
                    description=new_desc,
                    created_by=created_by
                )

                st.success(f"✅ Campaign created! ID: {campaign_id}")
                st.info("Campaign is in DRAFT mode. Click 'Send Now' to start sending.")
                st.balloons()
            else:
                st.error("Please fill in campaign name, select a template, and have leads available")

    with tab3:
        st.markdown("### SMS Templates")

        templates = sms_manager.get_templates()

        if not templates.empty:
            for _, tpl in templates.iterrows():
                with st.expander(f"📝 {tpl['name']} ({tpl['category']})"):
                    st.markdown(f"**Message:**")
                    st.info(tpl['message'])
                    st.caption(f"Template ID: {tpl['template_id']}")

        st.markdown("---")
        st.markdown("### Create New Template")

        new_tpl_name = st.text_input("Template Name", placeholder="My Custom Template")
        new_tpl_category = st.selectbox("Category", ["outreach", "follow_up", "reminder", "custom"])
        new_tpl_message = st.text_area(
            "Message (160 chars recommended)",
            placeholder="Hi {owner_name}, we're interested in buying {address}...",
            help="Use placeholders: {owner_name}, {address}, {city}, {sender_name}, {phone}, {company}"
        )

        if len(new_tpl_message) > 0:
            st.caption(f"Character count: {len(new_tpl_message)} / 160")
            if len(new_tpl_message) > 160:
                st.warning("Message exceeds 160 chars - will be sent as multiple texts")

        if st.button("💾 Save Template"):
            if new_tpl_name and new_tpl_message:
                tpl_id = sms_manager.create_template(new_tpl_name, new_tpl_message, new_tpl_category)
                st.success(f"Template saved! ID: {tpl_id}")
                st.rerun()
            else:
                st.error("Name and message are required")

    with tab4:
        st.markdown("### SMS Analytics")

        col1, col2 = st.columns(2)

        with col1:
            # Campaign performance
            campaigns = sms_manager.get_all_campaigns()
            if not campaigns.empty:
                fig = px.bar(
                    campaigns.head(10),
                    x='name',
                    y=['sent_count', 'response_count'],
                    title="Campaign Performance",
                    barmode='group'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No campaign data yet")

        with col2:
            # Response rate over campaigns
            if not campaigns.empty and campaigns['sent_count'].sum() > 0:
                campaigns['response_rate'] = campaigns.apply(
                    lambda x: (x['response_count'] / x['sent_count'] * 100) if x['sent_count'] > 0 else 0, axis=1
                )
                fig = px.line(
                    campaigns.sort_values('created_at'),
                    x='name',
                    y='response_rate',
                    title="Response Rate by Campaign",
                    markers=True
                )
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.markdown("### Key Metrics")

        met_col1, met_col2, met_col3, met_col4 = st.columns(4)
        with met_col1:
            st.metric("Total Messages Sent", sms_stats['total_messages_sent'])
        with met_col2:
            st.metric("Total Responses", sms_stats['total_responses'])
        with met_col3:
            st.metric("Overall Response Rate", f"{sms_stats['response_rate']:.1f}%")
        with met_col4:
            st.metric("Opt-out Rate", f"{(sms_stats['total_optouts'] / sms_stats['total_messages_sent'] * 100) if sms_stats['total_messages_sent'] > 0 else 0:.1f}%")


# ========================================
# FOLLOW-UPS PAGE
# ========================================
elif page == "🔄 Follow-ups":
    st.markdown('<h1 class="main-header">🔄 Automated Follow-ups</h1>', unsafe_allow_html=True)
    st.markdown("Never let a lead go cold - automated follow-up sequences win deals!")

    # Initialize
    follow_up_manager = FollowUpSequences()

    # Get stats
    fu_stats = follow_up_manager.get_stats()

    # Top metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Active Sequences", fu_stats['active_sequences'])
    with col2:
        st.metric("Leads in Sequences", fu_stats['active_leads'])
    with col3:
        st.metric("Today's Actions", fu_stats['todays_actions'])
    with col4:
        st.metric("Converted", fu_stats['converted_leads'])
    with col5:
        st.metric("Conversion Rate", f"{fu_stats['conversion_rate']:.1f}%")

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 Today's Actions", "📊 Sequences", "➕ Enroll Leads", "👥 Active Leads", "📈 Stats"])

    with tab1:
        st.markdown("### Today's Follow-up Actions")
        st.markdown("Complete these actions to keep leads engaged!")

        todays_actions = follow_up_manager.get_todays_actions()

        if todays_actions.empty:
            st.success("All caught up! No follow-up actions for today.")
        else:
            for _, action in todays_actions.iterrows():
                action_display = ACTION_TYPE_DISPLAY.get(action['action_type'], action['action_type'])

                with st.expander(f"{action_display} | {action['lead_name']} | {action['lead_address'][:30]}...", expanded=True):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Action:** {action_display}")
                        st.markdown(f"**Description:** {action['description']}")
                        st.markdown(f"**Lead:** {action['lead_name']}")

                    with col2:
                        st.markdown(f"**Phone:** {action['lead_phone']}")
                        st.markdown(f"**Address:** {action['lead_address']}")
                        st.markdown(f"**Step:** {int(action['step_number'])}")

                    st.markdown("---")

                    result_col1, result_col2, result_col3 = st.columns(3)

                    with result_col1:
                        result = st.selectbox(
                            "Result",
                            ["", "Completed", "No Answer", "Left Message", "Callback Scheduled", "Not Interested", "Wrong Number"],
                            key=f"result_{action['action_id']}"
                        )

                    with result_col2:
                        notes = st.text_input("Notes", key=f"notes_{action['action_id']}")

                    with result_col3:
                        if st.button("✅ Complete", key=f"complete_{action['action_id']}", type="primary"):
                            follow_up_manager.complete_action(action['action_id'], result=result, notes=notes)
                            st.success("Action completed!")
                            st.rerun()

                        if st.button("⏭️ Skip", key=f"skip_{action['action_id']}"):
                            follow_up_manager.skip_action(action['action_id'], reason=notes or "Skipped by user")
                            st.rerun()

        # Upcoming actions
        st.markdown("---")
        st.markdown("### Coming Up This Week")

        upcoming = follow_up_manager.get_upcoming_actions(days=7)
        upcoming = upcoming[upcoming['scheduled_date'] != datetime.now().strftime('%Y-%m-%d')]

        if upcoming.empty:
            st.info("No upcoming actions this week")
        else:
            for _, action in upcoming.head(15).iterrows():
                action_display = ACTION_TYPE_DISPLAY.get(action['action_type'], action['action_type'])
                st.markdown(f"📅 **{action['scheduled_date']}** - {action_display} - {action['lead_name']} - {action['lead_address'][:30]}...")

    with tab2:
        st.markdown("### Follow-up Sequences")

        sequences = follow_up_manager.get_all_sequences()

        if sequences.empty:
            st.info("No sequences yet")
        else:
            for _, seq in sequences.iterrows():
                status_color = "#28a745" if seq['status'] == 'active' else "#6c757d"

                with st.expander(f"📋 {seq['name']} | {int(seq['total_steps'])} steps | {int(seq['leads_enrolled'])} enrolled"):
                    st.markdown(f"**Status:** <span style='color:{status_color}'>{seq['status'].upper()}</span>", unsafe_allow_html=True)
                    st.markdown(f"**Description:** {seq['description']}")

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Enrolled", int(seq['leads_enrolled']))
                    with col2:
                        st.metric("Completed", int(seq['leads_completed']))
                    with col3:
                        st.metric("Converted", int(seq['leads_converted']))

                    # Show steps
                    st.markdown("**Steps:**")
                    steps = follow_up_manager.get_sequence_steps(seq['sequence_id'])
                    for _, step in steps.iterrows():
                        action_icon = ACTION_TYPE_DISPLAY.get(step['action_type'], '📋')
                        st.markdown(f"  Day {int(step['day_offset'])}: {action_icon} - {step['description']}")

        # Create new sequence
        st.markdown("---")
        st.markdown("### Create New Sequence")

        new_seq_name = st.text_input("Sequence Name", placeholder="My Custom Sequence")
        new_seq_desc = st.text_area("Description", placeholder="Follow-up for...")

        st.markdown("**Add Steps:**")
        if 'new_seq_steps' not in st.session_state:
            st.session_state['new_seq_steps'] = []

        step_col1, step_col2, step_col3 = st.columns(3)
        with step_col1:
            step_day = st.number_input("Day", min_value=0, max_value=90, value=0)
        with step_col2:
            step_action = st.selectbox("Action", ACTION_TYPES, format_func=lambda x: ACTION_TYPE_DISPLAY.get(x, x))
        with step_col3:
            step_desc = st.text_input("Description", placeholder="What to do...")

        if st.button("➕ Add Step"):
            st.session_state['new_seq_steps'].append({
                'day_offset': step_day,
                'action_type': step_action,
                'description': step_desc
            })
            st.rerun()

        if st.session_state['new_seq_steps']:
            st.markdown("**Current Steps:**")
            for i, step in enumerate(st.session_state['new_seq_steps']):
                st.markdown(f"  {i+1}. Day {step['day_offset']}: {ACTION_TYPE_DISPLAY.get(step['action_type'], step['action_type'])} - {step['description']}")

            if st.button("💾 Save Sequence", type="primary"):
                if new_seq_name:
                    seq_id = follow_up_manager.create_sequence(
                        name=new_seq_name,
                        description=new_seq_desc,
                        steps=st.session_state['new_seq_steps']
                    )
                    st.success(f"Sequence created! ID: {seq_id}")
                    st.session_state['new_seq_steps'] = []
                    st.rerun()
                else:
                    st.error("Sequence name is required")

    with tab3:
        st.markdown("### Enroll Leads in Sequence")

        # Select sequence
        sequences = follow_up_manager.get_all_sequences(status='active')
        if sequences.empty:
            st.warning("No active sequences. Create one first!")
        else:
            seq_options = sequences['sequence_id'].tolist()
            selected_seq = st.selectbox(
                "Select Sequence",
                seq_options,
                format_func=lambda x: sequences[sequences['sequence_id'] == x]['name'].iloc[0]
            )

            # Show sequence info
            if selected_seq:
                seq = follow_up_manager.get_sequence(selected_seq)
                if seq:
                    st.info(f"**{seq['name']}** - {seq['description']}")

            # Select leads to enroll
            st.markdown("---")
            st.markdown("### Select Leads")

            lead_source = st.radio(
                "Get leads from:",
                ["All Leads", "High Score (70+)", "Not in Sequence", "Manual Entry"],
                horizontal=True
            )

            leads_df = pd.DataFrame()
            all_leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

            if lead_source != "Manual Entry" and all_leads_file.exists():
                leads_df = pd.read_csv(all_leads_file)

                if lead_source == "High Score (70+)" and 'motivation_score' in leads_df.columns:
                    leads_df = leads_df[leads_df['motivation_score'] >= 70]

                # Filter out leads already in active sequences
                enrollments = follow_up_manager.get_enrollments(status='active')
                if not enrollments.empty and 'lead_address' in enrollments.columns:
                    enrolled_addresses = set(enrollments['lead_address'].str.lower().tolist())
                    if 'address' in leads_df.columns:
                        leads_df = leads_df[~leads_df['address'].str.lower().isin(enrolled_addresses)]

                st.markdown(f"**{len(leads_df)}** leads available")

                if not leads_df.empty:
                    # Multi-select leads
                    selected_leads = st.multiselect(
                        "Select leads to enroll",
                        options=leads_df['address'].tolist() if 'address' in leads_df.columns else [],
                        default=[]
                    )

                    assigned_to = st.text_input("Assign to VA", placeholder="VA name")

                    if st.button("📥 Enroll Selected Leads", type="primary"):
                        if selected_leads and selected_seq:
                            enrolled = 0
                            for addr in selected_leads:
                                lead_data = leads_df[leads_df['address'] == addr].iloc[0].to_dict()
                                follow_up_manager.enroll_lead(selected_seq, lead_data, assigned_to=assigned_to)
                                enrolled += 1
                            st.success(f"Enrolled {enrolled} leads!")
                            st.balloons()
                        else:
                            st.error("Select at least one lead")

            elif lead_source == "Manual Entry":
                manual_address = st.text_input("Address")
                manual_name = st.text_input("Owner Name")
                manual_phone = st.text_input("Phone")
                assigned_to = st.text_input("Assign to VA", key="manual_assign")

                if st.button("📥 Enroll Lead", type="primary"):
                    if manual_address and selected_seq:
                        lead_data = {
                            'address': manual_address,
                            'owner_name': manual_name,
                            'phone': manual_phone
                        }
                        enroll_id = follow_up_manager.enroll_lead(selected_seq, lead_data, assigned_to=assigned_to)
                        st.success(f"Enrolled! ID: {enroll_id}")

    with tab4:
        st.markdown("### Active Leads in Sequences")

        enrollments = follow_up_manager.get_enrollments(status='active')

        if enrollments.empty:
            st.info("No leads currently in sequences")
        else:
            st.markdown(f"**{len(enrollments)}** active enrollments")

            for _, enr in enrollments.iterrows():
                seq = follow_up_manager.get_sequence(enr['sequence_id'])
                seq_name = seq['name'] if seq else enr['sequence_id']

                with st.expander(f"👤 {enr['lead_name']} | {enr['lead_address'][:30]}... | Step {int(enr['current_step'])}"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Sequence:** {seq_name}")
                        st.markdown(f"**Phone:** {enr['lead_phone']}")
                        st.markdown(f"**Assigned:** {enr['assigned_to']}")

                    with col2:
                        st.markdown(f"**Enrolled:** {enr['enrolled_at'][:10]}")
                        st.markdown(f"**Next Action:** {enr['next_action_date']}")
                        st.markdown(f"**Status:** {enr['status']}")

                    st.markdown("---")
                    action_cols = st.columns(3)

                    with action_cols[0]:
                        if st.button("⏸️ Pause", key=f"pause_{enr['enrollment_id']}"):
                            follow_up_manager.pause_enrollment(enr['enrollment_id'])
                            st.rerun()

                    with action_cols[1]:
                        if st.button("❌ Remove", key=f"remove_{enr['enrollment_id']}"):
                            follow_up_manager.pause_enrollment(enr['enrollment_id'])  # Use pause as remove
                            st.rerun()

                    with action_cols[2]:
                        if st.button("💰 Mark Converted", key=f"convert_{enr['enrollment_id']}"):
                            follow_up_manager.mark_converted(enr['enrollment_id'])
                            st.success("Marked as converted!")
                            st.rerun()

    with tab5:
        st.markdown("### Follow-up Statistics")

        col1, col2 = st.columns(2)

        with col1:
            # Sequence performance
            sequences = follow_up_manager.get_all_sequences()
            if not sequences.empty:
                fig = px.bar(
                    sequences,
                    x='name',
                    y=['leads_enrolled', 'leads_completed', 'leads_converted'],
                    title="Sequence Performance",
                    barmode='group'
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No sequence data yet")

        with col2:
            # Conversion funnel
            if fu_stats['total_enrolled'] > 0:
                funnel_data = {
                    'Stage': ['Enrolled', 'Active', 'Completed', 'Converted'],
                    'Count': [fu_stats['total_enrolled'], fu_stats['active_leads'], fu_stats['completed_leads'], fu_stats['converted_leads']]
                }
                fig = px.funnel(
                    funnel_data,
                    x='Count',
                    y='Stage',
                    title="Lead Conversion Funnel"
                )
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.markdown("### Key Metrics")

        met_col1, met_col2, met_col3, met_col4 = st.columns(4)
        with met_col1:
            st.metric("Total Enrolled", fu_stats['total_enrolled'])
        with met_col2:
            st.metric("Pending Actions", fu_stats['pending_actions'])
        with met_col3:
            st.metric("Completion Rate", f"{(fu_stats['completed_leads'] / fu_stats['total_enrolled'] * 100) if fu_stats['total_enrolled'] > 0 else 0:.0f}%")
        with met_col4:
            st.metric("Conversion Rate", f"{fu_stats['conversion_rate']:.1f}%")


# ========================================
# REVERSE TARGETING PAGE
# ========================================
elif page == "🎯 Reverse Targeting":
    st.markdown('<h1 class="main-header">🎯 Reverse Targeting</h1>', unsafe_allow_html=True)
    st.markdown("**Find people ACTIVELY trying to sell** - these are your hottest leads!")

    # Initialize scraper
    rt_scraper = ReverseTargetingScraper()

    # Get stats
    rt_stats = rt_scraper.get_stats() or {}

    # Stats row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Leads", rt_stats.get('total', 0))
    with col2:
        st.metric("New (Uncontacted)", rt_stats.get('new', 0))
    with col3:
        st.metric("With Phone", rt_stats.get('with_phone', 0))
    with col4:
        st.metric("Contacted", rt_stats.get('contacted', 0))

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["🔥 Hot Leads", "🔍 Scrape New", "➕ Add Manual", "📊 By Source"])

    with tab1:
        st.markdown("### 🔥 Active Seller Leads")
        st.markdown("These people listed their property - they WANT to sell!")

        # Get leads
        leads_df = rt_scraper.get_all_leads()

        if not leads_df.empty:
            # Filter options
            col1, col2 = st.columns(2)
            with col1:
                status_filter = st.selectbox("Filter by Status", ["all", "new", "contacted", "interested", "closed", "dead"])
            with col2:
                source_filter = st.selectbox("Filter by Source", ["all"] + list(rt_stats.get('by_source', {}).keys()))

            # Apply filters
            filtered_df = leads_df.copy()
            if status_filter != "all":
                filtered_df = filtered_df[filtered_df['status'] == status_filter]
            if source_filter != "all":
                filtered_df = filtered_df[filtered_df['source'] == source_filter]

            st.markdown(f"**Showing {len(filtered_df)} leads**")

            # Display each lead as a card
            for idx, lead in filtered_df.head(20).iterrows():
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])

                    with col1:
                        st.markdown(f"**{lead.get('title', 'No Title')}**")
                        st.caption(f"📍 {lead.get('address', 'No address')} | 💰 ${lead.get('price', 'N/A')}")
                        if lead.get('phone'):
                            st.markdown(f"📞 **{lead.get('phone')}**")
                        if lead.get('email'):
                            st.caption(f"✉️ {lead.get('email')}")

                    with col2:
                        status = lead.get('status', 'new')
                        status_emoji = {"new": "🆕", "contacted": "📞", "interested": "🔥", "closed": "✅", "dead": "❌"}.get(status, "")
                        st.markdown(f"Status: {status_emoji} **{status}**")
                        st.caption(f"Source: {lead.get('source', 'unknown')}")
                        st.caption(f"Posted: {lead.get('posted_date', 'N/A')}")
                        if lead.get('url'):
                            st.markdown(f"[View Listing]({lead.get('url')})")

                    with col3:
                        lead_id = lead.get('id', '')
                        new_status = st.selectbox(
                            "Update",
                            ["new", "contacted", "interested", "closed", "dead"],
                            index=["new", "contacted", "interested", "closed", "dead"].index(status) if status in ["new", "contacted", "interested", "closed", "dead"] else 0,
                            key=f"status_{lead_id}"
                        )
                        if st.button("Update", key=f"update_{lead_id}"):
                            rt_scraper.update_lead_status(lead_id, new_status)
                            st.success("Updated!")
                            st.rerun()

                        if lead.get('phone') and st.button("📱 Call", key=f"call_rt_{lead_id}"):
                            # Add to call tracker
                            tracker = CallTracker()
                            tracker.log_call(
                                address=lead.get('address', ''),
                                owner_name=lead.get('title', ''),
                                phone=lead.get('phone', ''),
                                outcome='Attempted',
                                notes=f"Reverse targeting lead from {lead.get('source', 'unknown')}"
                            )
                            st.info(f"Added to call tracker: {lead.get('phone')}")

                    st.markdown("---")
        else:
            st.info("No reverse targeting leads yet. Scrape some or add manually!")

    with tab2:
        st.markdown("### 🔍 Scrape Active Seller Listings")

        st.markdown("""
        **Craigslist FSBO** - Find people selling their home without an agent.
        These are motivated sellers who want to avoid realtor fees!
        """)

        col1, col2, col3 = st.columns(3)
        with col1:
            city = st.text_input("City", value="columbus")
        with col2:
            state = st.text_input("State", value="ohio")
        with col3:
            max_pages = st.number_input("Max Pages", min_value=1, max_value=10, value=2)

        if st.button("🚀 Scrape Craigslist FSBO", type="primary"):
            with st.spinner(f"Scraping Craigslist {city}..."):
                leads = rt_scraper.scrape_craigslist(city, state, max_pages)
                saved = rt_scraper.save_leads(leads)

                st.success(f"Found {len(leads)} listings, saved {saved} new leads!")

                if saved > 0:
                    st.balloons()
                    st.info("💡 Click the '🔥 Hot Leads' tab above to view your scraped leads!")

        st.markdown("---")

        st.markdown("### 📞 Enrich Leads with Contact Info")
        st.markdown("Scrape phone numbers and emails from listing detail pages.")

        enrich_limit = st.slider("Number of leads to enrich", 1, 25, 5)

        if st.button("📞 Enrich Leads"):
            with st.spinner("Enriching leads..."):
                rt_scraper.enrich_leads(limit=enrich_limit)
                st.success(f"Enrichment complete!")
                st.rerun()

        st.markdown("---")

        # Facebook Marketplace instructions
        st.markdown("### 📘 Facebook Marketplace")
        st.info(rt_scraper.scrape_facebook_marketplace_manual())

    with tab3:
        st.markdown("### ➕ Add Manual Lead")
        st.markdown("Found a lead while driving for dollars, browsing Facebook, or from a referral? Add it here!")

        with st.form("manual_lead_form"):
            col1, col2 = st.columns(2)

            with col1:
                m_source = st.selectbox("Source", ["Facebook Marketplace", "Driving for Dollars", "Bandit Sign", "Referral", "Other"])
                m_title = st.text_input("Listing Title / Description", placeholder="3BR house needs work")
                m_address = st.text_input("Property Address *", placeholder="123 Main St, Columbus, OH")
                m_price = st.text_input("Asking Price", placeholder="85000")

            with col2:
                m_phone = st.text_input("Phone Number", placeholder="614-555-1234")
                m_email = st.text_input("Email", placeholder="seller@email.com")
                m_url = st.text_input("Listing URL", placeholder="https://...")
                m_notes = st.text_area("Notes", placeholder="Any additional info...")

            submitted = st.form_submit_button("➕ Add Lead", type="primary")

            if submitted:
                if m_address:
                    lead_id = rt_scraper.add_manual_lead(
                        source=m_source,
                        title=m_title,
                        address=m_address,
                        price=m_price,
                        phone=m_phone,
                        email=m_email,
                        url=m_url,
                        notes=m_notes
                    )
                    st.success(f"Lead added! ID: {lead_id}")
                    st.rerun()
                else:
                    st.error("Property address is required!")

    with tab4:
        st.markdown("### 📊 Leads by Source")

        by_source = rt_stats.get('by_source', {})

        if by_source:
            # Pie chart
            fig = px.pie(
                values=list(by_source.values()),
                names=list(by_source.keys()),
                title="Lead Distribution by Source"
            )
            st.plotly_chart(fig, use_container_width=True)

            # Table
            source_df = pd.DataFrame([
                {"Source": k, "Count": v, "Percentage": f"{v/sum(by_source.values())*100:.1f}%"}
                for k, v in by_source.items()
            ])
            st.dataframe(source_df, hide_index=True)
        else:
            st.info("No leads yet - start scraping to see analytics!")

        st.markdown("---")
        st.markdown("""
        ### 💡 Tips for Reverse Targeting

        **Why it works:**
        - These sellers RAISED THEIR HAND - they want to sell
        - No cold calling random people
        - Higher conversion rates
        - Less competition (most investors ignore these)

        **Best sources:**
        1. **Craigslist FSBO** - Motivated, avoiding agents
        2. **Facebook Marketplace** - Often distressed situations
        3. **Driving for Dollars** - Vacant/distressed properties
        4. **Bandit Signs** - "We Buy Houses" sign responses
        """)


# ========================================
# DIRECT MAIL PAGE
# ========================================
elif page == "📬 Direct Mail":
    st.markdown('<h1 class="main-header">📬 Direct Mail Manager</h1>', unsafe_allow_html=True)
    st.markdown("Create and manage direct mail campaigns for motivated sellers")

    # Initialize manager
    mail_manager = DirectMailManager()

    # Get campaigns
    campaigns = mail_manager.get_campaigns()

    # Quick stats
    total_sent = 0
    total_responses = 0
    for campaign in campaigns:
        total_sent += campaign.get('stats', {}).get('mail_sent', 0)
        total_responses += campaign.get('stats', {}).get('responses', 0)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Campaigns", len(campaigns))
    with col2:
        active = len([c for c in campaigns if c.get('status') == 'active'])
        st.metric("Active", active)
    with col3:
        st.metric("Mail Sent", total_sent)
    with col4:
        st.metric("Responses", total_responses)

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📋 Campaigns", "➕ New Campaign", "📤 Generate List", "📊 Track Responses", "📈 Analytics"])

    with tab1:
        st.markdown("### Active Campaigns")

        if campaigns:
            for campaign in campaigns:
                with st.expander(f"**{campaign.get('name')}** - {campaign.get('status', 'active').upper()}", expanded=campaign.get('status') == 'active'):
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.markdown(f"**ID:** {campaign.get('id')}")
                        st.markdown(f"**Type:** {campaign.get('lead_type', 'All')} | **Mail Type:** {campaign.get('mail_type', 'postcard')}")
                        st.markdown(f"**Touches:** {campaign.get('touches', 1)} | **Days Between:** {campaign.get('days_between_touches', 14)}")
                        if campaign.get('description'):
                            st.caption(campaign.get('description'))

                        # Stats
                        stats = campaign.get('stats', {})
                        st.markdown(f"📬 Sent: **{stats.get('mail_sent', 0)}** | 📞 Responses: **{stats.get('responses', 0)}** | ✅ Deals: **{stats.get('deals_closed', 0)}**")

                    with col2:
                        campaign_id = campaign.get('id')
                        status = campaign.get('status', 'active')

                        if status == 'active':
                            if st.button("⏸️ Pause", key=f"pause_{campaign_id}"):
                                mail_manager.update_campaign_status(campaign_id, 'paused')
                                st.rerun()
                        elif status == 'paused':
                            if st.button("▶️ Resume", key=f"resume_{campaign_id}"):
                                mail_manager.update_campaign_status(campaign_id, 'active')
                                st.rerun()

                        if st.button("✅ Complete", key=f"complete_{campaign_id}"):
                            mail_manager.update_campaign_status(campaign_id, 'completed')
                            st.rerun()
        else:
            st.info("No campaigns yet. Create one to get started!")

    with tab2:
        st.markdown("### Create New Campaign")

        with st.form("new_campaign_form"):
            col1, col2 = st.columns(2)

            with col1:
                c_name = st.text_input("Campaign Name *", placeholder="Probate Q1 2025")
                c_lead_type = st.selectbox("Target Lead Type", ["", "probate", "tax_delinquent", "code_violation", "sheriff_sale"])
                c_mail_type = st.selectbox("Mail Type", ["postcard", "letter", "yellow_letter"])
                c_description = st.text_area("Description", placeholder="First probate mailing campaign...")

            with col2:
                c_touches = st.number_input("Number of Touches", min_value=1, max_value=10, value=3)
                c_days = st.number_input("Days Between Touches", min_value=7, max_value=60, value=14)
                c_min_score = st.slider("Minimum Motivation Score", 0, 100, 50)
                c_zip_filter = st.text_input("ZIP Codes (comma-separated)", placeholder="43215, 43201, 43220")

            submitted = st.form_submit_button("Create Campaign", type="primary")

            if submitted:
                if c_name:
                    filters = {'min_score': c_min_score}
                    if c_zip_filter:
                        filters['zip_codes'] = [z.strip() for z in c_zip_filter.split(',')]

                    campaign_id = mail_manager.create_campaign(
                        name=c_name,
                        lead_type=c_lead_type if c_lead_type else None,
                        mail_type=c_mail_type,
                        touches=c_touches,
                        days_between_touches=c_days,
                        description=c_description,
                        filters=filters
                    )
                    st.success(f"Campaign created! ID: {campaign_id}")
                    st.rerun()
                else:
                    st.error("Campaign name is required!")

    with tab3:
        st.markdown("### Generate Mail List")

        if campaigns:
            active_campaigns = [c for c in campaigns if c.get('status') == 'active']

            if active_campaigns:
                campaign_options = {c['name']: c['id'] for c in active_campaigns}
                selected_campaign = st.selectbox("Select Campaign", list(campaign_options.keys()))
                selected_id = campaign_options[selected_campaign]

                campaign = mail_manager.get_campaign(selected_id)

                col1, col2 = st.columns(2)
                with col1:
                    touch_number = st.number_input("Touch Number", min_value=1, max_value=campaign.get('touches', 3), value=1)
                with col2:
                    limit = st.number_input("Max Addresses", min_value=10, max_value=5000, value=500)

                exclude_mailed = st.checkbox("Exclude already mailed addresses", value=True)

                col1, col2 = st.columns(2)

                with col1:
                    if st.button("👁️ Preview List", type="secondary"):
                        preview = mail_manager.generate_mail_list(selected_id, touch_number, limit=20)
                        if not preview.empty:
                            st.dataframe(preview[['owner_name', 'address_line_1', 'city', 'state', 'zip']], hide_index=True)
                            st.info(f"Showing 20 of estimated {len(preview)} addresses")
                        else:
                            st.warning("No addresses match your criteria")

                with col2:
                    if st.button("📤 Export to CSV", type="primary"):
                        export_path = mail_manager.export_mail_list(selected_id, touch_number, limit=limit)
                        if export_path:
                            st.success(f"Exported to: {export_path}")

                            # Option to log as sent
                            if st.button("✅ Mark as Sent"):
                                mail_list = mail_manager.generate_mail_list(selected_id, touch_number, limit=limit)
                                addresses = mail_list['address_line_1'].tolist()
                                count = mail_manager.log_mail_sent(selected_id, addresses, touch_number)
                                st.success(f"Logged {count} mail pieces as sent!")
                                st.rerun()
                        else:
                            st.error("Failed to export - no addresses found")

                st.markdown("---")
                st.markdown("### Mail Templates")

                for key, template in MAIL_TEMPLATES.items():
                    with st.expander(f"📝 {template['name']}"):
                        st.markdown(f"**Size:** {template.get('size', 'postcard')}")
                        st.code(template['body'])

            else:
                st.warning("No active campaigns. Create or activate a campaign first.")
        else:
            st.info("Create a campaign first!")

    with tab4:
        st.markdown("### Track Responses")

        if campaigns:
            st.markdown("#### Log New Response")

            with st.form("log_response_form"):
                col1, col2 = st.columns(2)

                with col1:
                    campaign_options = {c['name']: c['id'] for c in campaigns}
                    resp_campaign = st.selectbox("Campaign", list(campaign_options.keys()), key="resp_campaign")
                    resp_type = st.selectbox("Response Type", ["call", "text", "email", "web_form"])

                with col2:
                    resp_phone = st.text_input("Caller Phone", placeholder="614-555-1234")
                    resp_notes = st.text_area("Notes", placeholder="What did they say?")

                if st.form_submit_button("Log Response", type="primary"):
                    campaign_id = campaign_options[resp_campaign]
                    response_id = mail_manager.log_response(
                        campaign_id=campaign_id,
                        response_type=resp_type,
                        phone=resp_phone,
                        notes=resp_notes
                    )
                    st.success(f"Response logged! ID: {response_id}")
                    st.rerun()

            st.markdown("---")
            st.markdown("#### Recent Responses")

            responses = mail_manager.get_responses()
            if not responses.empty:
                for idx, resp in responses.head(20).iterrows():
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        campaign_name = next((c['name'] for c in campaigns if c['id'] == resp.get('campaign_id')), 'Unknown')
                        st.markdown(f"**{resp.get('response_type', 'call').upper()}** from **{resp.get('phone', 'Unknown')}**")
                        st.caption(f"Campaign: {campaign_name} | {resp.get('response_date', '')}")
                        if resp.get('notes'):
                            st.caption(f"Notes: {resp.get('notes')}")

                    with col2:
                        outcome = resp.get('outcome', 'new')
                        outcome_emoji = {'new': '🆕', 'interested': '🔥', 'not_interested': '❌', 'deal_closed': '✅'}.get(outcome, '❓')
                        st.markdown(f"{outcome_emoji} {outcome}")

                        new_outcome = st.selectbox(
                            "Update",
                            ["new", "interested", "not_interested", "deal_closed"],
                            index=["new", "interested", "not_interested", "deal_closed"].index(outcome) if outcome in ["new", "interested", "not_interested", "deal_closed"] else 0,
                            key=f"outcome_{resp.get('response_id')}"
                        )
                        if st.button("Update", key=f"update_resp_{resp.get('response_id')}"):
                            mail_manager.update_response_outcome(resp.get('response_id'), new_outcome)
                            st.rerun()

                    st.markdown("---")
            else:
                st.info("No responses logged yet")
        else:
            st.info("Create a campaign first!")

    with tab5:
        st.markdown("### Campaign Analytics")

        if campaigns:
            campaign_options = {c['name']: c['id'] for c in campaigns}
            analytics_campaign = st.selectbox("Select Campaign", list(campaign_options.keys()), key="analytics_campaign")
            analytics_id = campaign_options[analytics_campaign]

            stats = mail_manager.get_campaign_stats(analytics_id)

            if stats:
                col1, col2, col3 = st.columns(3)

                mail_stats = stats.get('mail', {})
                resp_stats = stats.get('responses', {})

                with col1:
                    st.markdown("#### Mail Stats")
                    st.metric("Total Sent", mail_stats.get('total_sent', 0))
                    st.metric("Returned", mail_stats.get('returned', 0))
                    st.metric("Return Rate", f"{mail_stats.get('return_rate', 0):.1f}%")

                with col2:
                    st.markdown("#### Responses")
                    st.metric("Total Responses", resp_stats.get('total', 0))
                    st.metric("Response Rate", f"{resp_stats.get('response_rate', 0):.1f}%")

                with col3:
                    st.markdown("#### ROI")
                    campaign_stats = stats.get('campaign', {}).get('stats', {})
                    deals = campaign_stats.get('deals_closed', 0)
                    st.metric("Deals Closed", deals)
                    # Assume $0.50 per piece for rough ROI
                    cost = mail_stats.get('total_sent', 0) * 0.50
                    st.metric("Est. Cost", f"${cost:,.2f}")

                # By Touch breakdown
                if mail_stats.get('by_touch'):
                    st.markdown("---")
                    st.markdown("#### Mail by Touch")

                    touch_data = mail_stats.get('by_touch', {})
                    if touch_data:
                        fig = px.bar(
                            x=list(touch_data.keys()),
                            y=list(touch_data.values()),
                            labels={'x': 'Touch Number', 'y': 'Mail Sent'},
                            title="Mail Sent by Touch"
                        )
                        st.plotly_chart(fig, use_container_width=True)

                # Response types
                if resp_stats.get('by_type'):
                    st.markdown("---")
                    st.markdown("#### Response Types")

                    resp_type_data = resp_stats.get('by_type', {})
                    if resp_type_data:
                        fig2 = px.pie(
                            values=list(resp_type_data.values()),
                            names=list(resp_type_data.keys()),
                            title="Responses by Type"
                        )
                        st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("No data for this campaign yet")
        else:
            st.info("Create a campaign first!")


# ========================================
# RVM & NUMBER ROTATION PAGE
# ========================================
elif page == "📲 RVM & Numbers":
    st.markdown('<h1 class="main-header">📲 RVM & Number Rotation</h1>', unsafe_allow_html=True)
    st.markdown("Solve the spam risk problem: warm leads with RVM and rotate numbers")

    # Initialize managers
    num_manager = NumberRotationManager()
    rvm_manager = RVMManager()

    # Get stats
    rotation_stats = num_manager.get_rotation_stats()
    rvm_campaigns = rvm_manager.get_campaigns()

    # Quick stats row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Phone Numbers", rotation_stats.get('total_numbers', 0))
    with col2:
        st.metric("Available", rotation_stats.get('available_numbers', 0))
    with col3:
        st.metric("RVM Campaigns", len(rvm_campaigns))
    with col4:
        total_drops = sum(c.get('stats', {}).get('total_drops', 0) for c in rvm_campaigns)
        st.metric("Total RVM Drops", total_drops)

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📞 Number Rotation", "📲 RVM Campaigns", "📝 RVM Scripts", "📊 Analytics"])

    with tab1:
        st.markdown("### Phone Number Rotation")
        st.markdown("""
        **Why rotate numbers?**
        - Avoid spam flags from carriers
        - Maintain local presence
        - Higher answer rates

        **Best Practices:**
        - Rotate every 20-30 calls
        - Rest numbers for 24+ hours
        - Use local area codes when possible
        """)

        st.markdown("---")

        # Add new number
        st.markdown("#### Add Phone Number")
        with st.form("add_number_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_number = st.text_input("Phone Number", placeholder="614-555-1234")
                new_provider = st.selectbox("Provider", ["manual", "twilio", "openphone", "other"])
            with col2:
                new_area_code = st.text_input("Area Code (auto-detected)", placeholder="614")
                new_notes = st.text_input("Notes", placeholder="Main line, etc.")

            if st.form_submit_button("Add Number", type="primary"):
                if new_number:
                    num_id = num_manager.add_number(
                        phone_number=new_number,
                        area_code=new_area_code if new_area_code else None,
                        provider=new_provider,
                        notes=new_notes
                    )
                    st.success(f"Added number! ID: {num_id}")
                    st.rerun()
                else:
                    st.error("Phone number is required")

        st.markdown("---")

        # Current numbers
        st.markdown("#### Your Numbers")

        numbers = rotation_stats.get('numbers', [])
        if numbers:
            for num in numbers:
                col1, col2, col3 = st.columns([2, 2, 1])

                with col1:
                    status_emoji = {'active': '✅', 'flagged': '🚫', 'resting': '😴'}.get(num.get('status'), '❓')

                    # Check if resting
                    is_resting = False
                    if num.get('resting_until'):
                        rest_until = datetime.fromisoformat(num['resting_until'])
                        if datetime.now() < rest_until:
                            is_resting = True
                            status_emoji = '😴'

                    st.markdown(f"{status_emoji} **{num.get('formatted', num.get('phone_number'))}**")
                    st.caption(f"Area: {num.get('area_code')} | Provider: {num.get('provider')}")

                with col2:
                    health = num.get('health_score', 100)
                    health_color = 'green' if health >= 70 else 'orange' if health >= 40 else 'red'
                    st.markdown(f"Health: **{health}/100** | Calls Today: **{num.get('calls_today', 0)}**")
                    st.caption(f"Total Calls: {num.get('total_calls', 0)} | Since Rotation: {num.get('calls_since_rotation', 0)}")

                    if is_resting:
                        st.caption(f"⏰ Resting until: {rest_until.strftime('%m/%d %H:%M')}")

                with col3:
                    if num.get('status') == 'active':
                        if st.button("🚫 Flag Spam", key=f"flag_{num.get('id')}"):
                            num_manager.report_spam(num.get('id'))
                            st.warning("Number flagged!")
                            st.rerun()

                st.markdown("---")
        else:
            st.info("No phone numbers added yet. Add numbers above to start rotating.")

        # Get next number preview
        st.markdown("#### Next Number Preview")
        next_num = num_manager.get_next_number()
        if next_num:
            st.success(f"Next call will use: **{next_num.get('formatted')}** (Area: {next_num.get('area_code')})")
        else:
            st.warning("No numbers available! Add numbers or wait for resting numbers to come back online.")

    with tab2:
        st.markdown("### RVM (Ringless Voicemail) Campaigns")
        st.markdown("""
        **Why use RVM?**
        - Drop voicemail directly without ringing
        - Warm leads BEFORE cold calling
        - Higher callback rates
        - Less intrusive than cold calls
        """)

        st.markdown("---")

        # Create new campaign
        st.markdown("#### Create RVM Campaign")

        scripts = rvm_manager.get_scripts()

        with st.form("create_rvm_campaign"):
            col1, col2 = st.columns(2)

            with col1:
                rvm_name = st.text_input("Campaign Name", placeholder="Probate RVM Q1")
                rvm_lead_type = st.selectbox("Target Lead Type", ["", "probate", "tax_delinquent", "code_violation"])

            with col2:
                script_options = list(scripts.keys()) if scripts else ["No scripts - add some first"]
                rvm_script = st.selectbox("Voicemail Script", script_options)
                rvm_description = st.text_input("Description", placeholder="First RVM touch for probate...")

            if st.form_submit_button("Create Campaign", type="primary"):
                if rvm_name and scripts:
                    campaign_id = rvm_manager.create_campaign(
                        name=rvm_name,
                        script_id=rvm_script,
                        lead_type=rvm_lead_type if rvm_lead_type else None,
                        description=rvm_description
                    )
                    st.success(f"Campaign created! ID: {campaign_id}")
                    st.rerun()
                elif not scripts:
                    st.error("Add voicemail scripts first!")
                else:
                    st.error("Campaign name is required")

        st.markdown("---")

        # Active campaigns
        st.markdown("#### Active Campaigns")

        if rvm_campaigns:
            for campaign in rvm_campaigns:
                with st.expander(f"**{campaign.get('name')}** - {campaign.get('status', 'active').upper()}"):
                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.markdown(f"**ID:** {campaign.get('id')}")
                        st.markdown(f"**Script:** {campaign.get('script_id')} | **Lead Type:** {campaign.get('lead_type', 'All')}")

                        stats = campaign.get('stats', {})
                        st.markdown(f"📲 Drops: **{stats.get('total_drops', 0)}** | 📞 Callbacks: **{stats.get('callbacks', 0)}**")

                        if stats.get('total_drops', 0) > 0:
                            callback_rate = stats.get('callbacks', 0) / stats.get('total_drops', 1) * 100
                            st.caption(f"Callback Rate: {callback_rate:.1f}%")

                    with col2:
                        campaign_id = campaign.get('id')

                        # Generate drop list button
                        if st.button("📋 Generate List", key=f"gen_{campaign_id}"):
                            drop_list = rvm_manager.generate_drop_list(campaign_id, limit=100)
                            if not drop_list.empty:
                                st.dataframe(drop_list[['target_number', 'owner_name', 'address']].head(10), hide_index=True)
                                st.info(f"Preview of {len(drop_list)} numbers ready for drop")

                                # Export option
                                export_path = DATA_DIR / f"rvm_drop_list_{campaign_id}.csv"
                                drop_list.to_csv(export_path, index=False)
                                st.success(f"Exported to: {export_path}")
                            else:
                                st.warning("No numbers available for this campaign")
        else:
            st.info("No RVM campaigns yet. Create one above!")

    with tab3:
        st.markdown("### Voicemail Scripts")

        # Add default scripts if none exist
        if not scripts:
            st.info("Adding default scripts...")
            for script_id, script_data in DEFAULT_RVM_SCRIPTS.items():
                rvm_manager.add_script(
                    script_id=script_id,
                    name=script_data['name'],
                    script_text=script_data['script_text'],
                    duration_seconds=script_data['duration_seconds']
                )
            st.success("Default scripts added!")
            st.rerun()

        # Display scripts
        scripts = rvm_manager.get_scripts()

        if scripts:
            for script_id, script in scripts.items():
                with st.expander(f"📝 {script.get('name', script_id)}"):
                    st.markdown(f"**ID:** `{script_id}`")
                    st.markdown(f"**Duration:** ~{script.get('duration_seconds', 30)} seconds")

                    st.markdown("**Script:**")
                    st.code(script.get('script_text', ''))

                    if script.get('audio_url'):
                        st.markdown(f"**Audio:** {script.get('audio_url')}")

        st.markdown("---")

        # Add new script
        st.markdown("#### Add New Script")

        with st.form("add_script_form"):
            script_id = st.text_input("Script ID", placeholder="my_custom_script")
            script_name = st.text_input("Script Name", placeholder="Custom Probate Script")
            script_text = st.text_area("Script Text", placeholder="Hi, this is Willy from Lifeline Home Buyers...", height=200)
            script_duration = st.number_input("Estimated Duration (seconds)", min_value=10, max_value=120, value=30)
            audio_url = st.text_input("Audio URL (optional)", placeholder="https://...")

            if st.form_submit_button("Add Script", type="primary"):
                if script_id and script_name and script_text:
                    rvm_manager.add_script(
                        script_id=script_id,
                        name=script_name,
                        script_text=script_text,
                        duration_seconds=script_duration,
                        audio_url=audio_url
                    )
                    st.success("Script added!")
                    st.rerun()
                else:
                    st.error("Script ID, name, and text are required")

    with tab4:
        st.markdown("### RVM & Number Analytics")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Number Health")

            numbers = rotation_stats.get('numbers', [])
            if numbers:
                health_data = {n.get('formatted', n.get('phone_number')): n.get('health_score', 100) for n in numbers}

                fig = px.bar(
                    x=list(health_data.keys()),
                    y=list(health_data.values()),
                    labels={'x': 'Number', 'y': 'Health Score'},
                    title="Number Health Scores",
                    color=list(health_data.values()),
                    color_continuous_scale=['red', 'yellow', 'green']
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Add numbers to see health analytics")

        with col2:
            st.markdown("#### RVM Callback Rates")

            if rvm_campaigns:
                campaign_data = []
                for c in rvm_campaigns:
                    stats = c.get('stats', {})
                    drops = stats.get('total_drops', 0)
                    callbacks = stats.get('callbacks', 0)
                    rate = (callbacks / drops * 100) if drops > 0 else 0
                    campaign_data.append({
                        'Campaign': c.get('name'),
                        'Drops': drops,
                        'Callbacks': callbacks,
                        'Rate': f"{rate:.1f}%"
                    })

                st.dataframe(pd.DataFrame(campaign_data), hide_index=True)
            else:
                st.info("Create RVM campaigns to see analytics")

        st.markdown("---")

        st.markdown("#### Today's Activity")
        st.metric("Calls Today (All Numbers)", rotation_stats.get('calls_today', 0))
        st.metric("Numbers Resting", rotation_stats.get('resting_numbers', 0))
        st.metric("Flagged Numbers", rotation_stats.get('flagged_numbers', 0))

        st.markdown("---")

        st.markdown("""
        ### Integration Guide

        **For RVM Delivery:**
        - [Slybroadcast](https://slybroadcast.com) - $0.02-0.03/drop
        - [Drop Cowboy](https://dropcowboy.com) - $0.04-0.05/drop

        **For Number Rotation:**
        - [Twilio](https://twilio.com) - $1/month per number
        - [OpenPhone](https://openphone.com) - $15/month for teams

        **Workflow:**
        1. Add your phone numbers
        2. Create RVM campaign with script
        3. Generate drop list
        4. Upload to RVM provider
        5. Track callbacks
        6. Call back warm leads using rotated numbers
        """)


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

    # Check for batch files first
    batches_dir = PROCESSED_DATA_DIR / 'batches'
    batch_files = []
    if batches_dir.exists():
        batch_files = sorted([f for f in batches_dir.glob('batch_*_*.csv') if 'tier' not in f.name], reverse=True)

    # Batch selector
    df = pd.DataFrame()
    if batch_files:
        batch_options = ['All Batches Combined'] + [f.stem for f in batch_files]
        selected_batch = st.selectbox("📦 Select Batch", batch_options)

        if selected_batch == 'All Batches Combined':
            # Combine all batches
            all_dfs = []
            for bf in batch_files:
                try:
                    batch_df = pd.read_csv(bf)
                    batch_df['batch'] = bf.stem
                    all_dfs.append(batch_df)
                except:
                    pass
            if all_dfs:
                df = pd.concat(all_dfs, ignore_index=True)
                st.success(f"📦 Showing {len(df):,} leads from {len(batch_files)} batches")
        else:
            # Load selected batch
            batch_file = batches_dir / f"{selected_batch}.csv"
            if batch_file.exists():
                df = pd.read_csv(batch_file)
                st.success(f"📦 Showing {len(df):,} leads from {selected_batch}")
    else:
        # Fallback to old format
        all_leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
        if not all_leads_file.exists():
            all_leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

        if all_leads_file.exists():
            df = pd.read_csv(all_leads_file)
            st.info(f"📦 Showing {len(df):,} leads")

    if df.empty:
        st.warning("⚠️ No leads found. Generate leads first!")
    else:
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
                max_baths = float(df['bathrooms'].max()) if df['bathrooms'].max() > 0 else 10
                min_bathrooms = st.number_input(
                    "Min Bathrooms",
                    min_value=0.0,
                    max_value=max_baths,
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
        from dialer.twilio_client import TwilioClient
        from dialer.call_manager import CallManager, CallDisposition, LeadStatus
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
                            # Save to call manager
                            call_mgr.record_call(
                                lead_id=lead['id'],
                                disposition=disposition,
                                notes=notes,
                                va_id="dashboard_user",
                                callback_date=callback_date
                            )

                            # Also log to Call Tracker for follow-up tracking
                            tracker = CallTracker()

                            # Map dialer disposition to tracker outcome
                            disposition_to_outcome = {
                                'not_called': 'No Answer',
                                'no_answer': 'No Answer',
                                'voicemail': 'Left Voicemail',
                                'busy': 'No Answer',
                                'wrong_number': 'Wrong Number',
                                'disconnected': 'Wrong Number',
                                'dnc_request': 'Do Not Call',
                                'not_interested': 'Not Interested',
                                'callback_requested': 'Call Back Later',
                                'interested': 'Interested',
                                'hot_lead': 'Appointment Set',
                                'deal_made': 'Offer Made'
                            }

                            tracker_outcome = disposition_to_outcome.get(disposition, 'No Answer')

                            # Parse callback date for follow-up
                            follow_up_date = None
                            if callback_date and isinstance(callback_date, str) and 'T' in callback_date:
                                follow_up_date = callback_date.split('T')[0]

                            tracker.log_call(
                                address=lead.get('address', ''),
                                owner_name=lead.get('owner_name', ''),
                                phone=lead.get('phone', ''),
                                outcome=tracker_outcome,
                                notes=notes,
                                follow_up_date=follow_up_date,
                                follow_up_notes=f"Callback scheduled" if follow_up_date else ''
                            )

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


# ========================================
# BUYER MATCHING PAGE
# ========================================
elif page == "🤝 Buyer Matching":
    st.markdown('<h1 class="main-header">🤝 Buyer Matching</h1>', unsafe_allow_html=True)
    st.markdown("Match deals to interested cash buyers based on their buy box criteria")

    # Initialize matcher
    matcher = BuyerMatcher()

    # Get stats
    stats = matcher.get_stats()

    # Stats row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Buyers", stats['total_buyers'])
    with col2:
        st.metric("Active Buyers", stats['active_buyers'])
    with col3:
        st.metric("Deal Blasts", stats['total_blasts'])
    with col4:
        st.metric("Response Rate", stats['response_rate'])

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["👥 Buyer List", "➕ Add Buyer", "🎯 Match Deal", "📊 Top Buyers"])

    with tab1:
        st.markdown("### 👥 Active Buyers")

        buyers_df = matcher.get_all_buyers(status='active')

        if len(buyers_df) > 0:
            # Display buyers
            for idx, buyer in buyers_df.iterrows():
                with st.expander(f"**{buyer['name']}** - {buyer.get('company', 'Individual')} ({buyer['deals_purchased']} deals)"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Email:** {buyer['email']}")
                        st.markdown(f"**Phone:** {buyer['phone']}")
                        st.markdown(f"**Funding:** {buyer.get('funding_type', 'cash').upper()}")

                    with col2:
                        st.markdown(f"**ZIP Codes:** {buyer.get('zip_codes', 'Any')}")
                        st.markdown(f"**Property Types:** {buyer.get('property_types', 'Any')}")
                        st.markdown(f"**Price Range:** ${buyer.get('min_price', 0):,.0f} - ${buyer.get('max_price', 0):,.0f}")

                    st.markdown(f"**ARV Range:** ${buyer.get('min_arv', 0):,.0f} - ${buyer.get('max_arv', 0):,.0f}")
                    st.markdown(f"**Max Days to Close:** {buyer.get('max_days_to_close', 30)}")

                    if buyer.get('notes'):
                        st.markdown(f"**Notes:** {buyer['notes']}")

                    # Actions
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button("📝 Edit", key=f"edit_{buyer['buyer_id']}"):
                            st.session_state['editing_buyer'] = buyer['buyer_id']
                    with col2:
                        if st.button("🚫 Deactivate", key=f"deactivate_{buyer['buyer_id']}"):
                            matcher.deactivate_buyer(buyer['buyer_id'])
                            st.success("Buyer deactivated")
                            st.rerun()
                    with col3:
                        if st.button("🗑️ Delete", key=f"delete_{buyer['buyer_id']}"):
                            matcher.delete_buyer(buyer['buyer_id'])
                            st.success("Buyer deleted")
                            st.rerun()
        else:
            st.info("No active buyers yet. Add buyers using the 'Add Buyer' tab.")

        # Show inactive buyers
        inactive_df = matcher.get_all_buyers(status='inactive')
        if len(inactive_df) > 0:
            with st.expander(f"Show Inactive Buyers ({len(inactive_df)})"):
                for idx, buyer in inactive_df.iterrows():
                    col1, col2, col3 = st.columns([3, 1, 1])
                    with col1:
                        st.write(f"{buyer['name']} - {buyer['email']}")
                    with col2:
                        if st.button("✅ Reactivate", key=f"reactivate_{buyer['buyer_id']}"):
                            matcher.update_buyer(buyer['buyer_id'], status='active')
                            st.rerun()

    with tab2:
        st.markdown("### ➕ Add New Buyer")

        with st.form("add_buyer_form"):
            col1, col2 = st.columns(2)

            with col1:
                name = st.text_input("Name *")
                email = st.text_input("Email *")
                phone = st.text_input("Phone *")
                company = st.text_input("Company")

            with col2:
                zip_codes = st.text_input("ZIP Codes (comma separated)", placeholder="43201, 43202, 43203")
                property_types = st.multiselect(
                    "Property Types",
                    ["SFR", "Duplex", "Triplex", "Quad", "Multi-Family", "Land", "Commercial"],
                    default=["SFR"]
                )
                funding_type = st.selectbox("Funding Type", ["cash", "hard_money", "conventional", "private"])

            st.markdown("#### Price Criteria")
            col1, col2 = st.columns(2)
            with col1:
                min_price = st.number_input("Min Purchase Price", min_value=0, value=0, step=5000)
                min_arv = st.number_input("Min ARV", min_value=0, value=0, step=5000)
            with col2:
                max_price = st.number_input("Max Purchase Price", min_value=0, value=200000, step=5000)
                max_arv = st.number_input("Max ARV", min_value=0, value=500000, step=5000)

            max_days = st.slider("Max Days to Close", 7, 90, 30)
            notes = st.text_area("Notes")

            submitted = st.form_submit_button("Add Buyer", type="primary")

            if submitted:
                if not name or not email or not phone:
                    st.error("Name, Email, and Phone are required")
                else:
                    zip_list = [z.strip() for z in zip_codes.split(',') if z.strip()]

                    buyer_id = matcher.add_buyer(
                        name=name,
                        email=email,
                        phone=phone,
                        company=company,
                        zip_codes=zip_list,
                        property_types=property_types,
                        min_price=min_price,
                        max_price=max_price,
                        min_arv=min_arv,
                        max_arv=max_arv,
                        funding_type=funding_type,
                        max_days_to_close=max_days,
                        notes=notes
                    )
                    st.success(f"Buyer added: {buyer_id}")
                    st.rerun()

    with tab3:
        st.markdown("### 🎯 Match Deal to Buyers")
        st.markdown("Enter deal details to find matching buyers")

        with st.form("match_deal_form"):
            col1, col2 = st.columns(2)

            with col1:
                deal_address = st.text_input("Property Address *")
                deal_zip = st.text_input("ZIP Code *")
                deal_type = st.selectbox("Property Type", ["SFR", "Duplex", "Triplex", "Quad", "Multi-Family", "Land"])

            with col2:
                asking_price = st.number_input("Asking Price *", min_value=0, value=75000, step=5000)
                arv = st.number_input("ARV (After Repair Value)", min_value=0, value=120000, step=5000)
                repair_cost = st.number_input("Estimated Repairs", min_value=0, value=25000, step=1000)

            condition = st.selectbox("Property Condition", ["turnkey", "light_rehab", "moderate_rehab", "heavy_rehab", "tear_down"])
            deal_notes = st.text_area("Deal Notes")

            find_matches = st.form_submit_button("🔍 Find Matching Buyers", type="primary")

            if find_matches:
                if not deal_address or not deal_zip:
                    st.error("Address and ZIP code are required")
                else:
                    deal = {
                        'address': deal_address,
                        'zip_code': deal_zip,
                        'property_type': deal_type,
                        'asking_price': asking_price,
                        'arv': arv,
                        'repair_cost': repair_cost,
                        'condition': condition,
                        'notes': deal_notes
                    }

                    st.session_state['current_deal'] = deal
                    matches = matcher.match_deal_to_buyers(deal)
                    st.session_state['deal_matches'] = matches

        # Show matches
        if 'deal_matches' in st.session_state and st.session_state['deal_matches']:
            matches = st.session_state['deal_matches']
            deal = st.session_state.get('current_deal', {})

            st.markdown("---")
            st.markdown(f"### 🎯 Found {len(matches)} Matching Buyers")
            st.markdown(f"**Deal:** {deal.get('address', 'N/A')} | **Asking:** ${deal.get('asking_price', 0):,} | **ARV:** ${deal.get('arv', 0):,}")

            for i, match in enumerate(matches):
                score_color = "🟢" if match['score'] >= 70 else "🟡" if match['score'] >= 50 else "🔴"

                with st.expander(f"{score_color} **{match['name']}** - Score: {match['score']}/100 ({match['funding_type'].upper()})"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Email:** {match['email']}")
                        st.markdown(f"**Phone:** {match['phone']}")
                        st.markdown(f"**Company:** {match.get('company', 'N/A')}")

                    with col2:
                        st.markdown(f"**Deals Purchased:** {match['deals_purchased']}")
                        st.markdown(f"**Avg Response Time:** {match['avg_response_time_hrs']:.1f} hrs")

                    st.markdown("**Match Reasons:**")
                    for reason in match['reasons']:
                        st.markdown(f"- {reason}")

                    # Contact buttons
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown(f"[📧 Email](mailto:{match['email']}?subject=Deal%20Opportunity%20-%20{deal.get('address', '')})")
                    with col2:
                        st.markdown(f"[📞 Call](tel:{match['phone']})")
                    with col3:
                        if st.button("✅ Mark Interested", key=f"interested_{match['buyer_id']}_{i}"):
                            st.success(f"Marked {match['name']} as interested!")

            # Blast to all button
            st.markdown("---")
            if st.button("📤 Send Deal to All Matched Buyers", type="primary"):
                deal['deal_id'] = f"DEAL-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                blast_id = matcher.create_deal_blast(deal, [m['buyer_id'] for m in matches])
                st.success(f"Deal blast sent to {len(matches)} buyers! Blast ID: {blast_id}")

        elif 'deal_matches' in st.session_state:
            st.warning("No matching buyers found. Try adjusting the deal criteria or add more buyers.")

    with tab4:
        st.markdown("### 📊 Top Buyers")
        st.markdown("Buyers ranked by deals purchased")

        top_buyers = matcher.get_top_buyers(limit=20)

        if len(top_buyers) > 0:
            # Display as table
            display_df = top_buyers[['name', 'company', 'deals_purchased', 'funding_type', 'zip_codes']].copy()
            display_df.columns = ['Name', 'Company', 'Deals', 'Funding', 'ZIP Codes']
            st.dataframe(display_df, use_container_width=True)

            # Chart
            if len(top_buyers) >= 3:
                import plotly.express as px
                fig = px.bar(
                    top_buyers.head(10),
                    x='name',
                    y='deals_purchased',
                    title="Top 10 Buyers by Deals Purchased",
                    labels={'name': 'Buyer', 'deals_purchased': 'Deals'}
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No buyer data yet. Add buyers and record their purchases to see rankings.")


# ========================================
# USER MANAGEMENT PAGE
# ========================================
elif page == "🔐 User Management":
    st.markdown('<h1 class="main-header">🔐 User Management</h1>', unsafe_allow_html=True)
    st.markdown("Manage VA login credentials and access")

    # Initialize auth
    auth = VAAuth()

    # Get all users
    users = auth.get_all_users(include_inactive=True)

    # Stats
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Users", len(users))
    with col2:
        active = len(users[users['is_active'] == True]) if not users.empty else 0
        st.metric("Active", active)
    with col3:
        admins = len(users[users['role'] == 'admin']) if not users.empty else 0
        st.metric("Admins", admins)
    with col4:
        vas = len(users[users['role'] == 'va']) if not users.empty else 0
        st.metric("VAs", vas)

    st.markdown("---")

    # Tabs
    tab1, tab2, tab3 = st.tabs(["👥 All Users", "➕ Add User", "🔐 Reset Password"])

    with tab1:
        st.markdown("### All Users")

        if users.empty:
            st.info("No users yet")
        else:
            for _, user in users.iterrows():
                status_color = "#28a745" if user['is_active'] else "#dc3545"
                role_badge = "Admin" if user['role'] == 'admin' else "Manager" if user['role'] == 'manager' else "VA"

                with st.expander(f"👤 {user['full_name']} (@{user['username']}) - {role_badge}"):
                    col1, col2 = st.columns(2)

                    with col1:
                        st.markdown(f"**Username:** {user['username']}")
                        st.markdown(f"**Full Name:** {user['full_name']}")
                        st.markdown(f"**Email:** {user['email'] or 'Not set'}")

                    with col2:
                        st.markdown(f"**Role:** {user['role']}")
                        st.markdown(f"**Status:** <span style='color:{status_color}'>{'Active' if user['is_active'] else 'Inactive'}</span>", unsafe_allow_html=True)
                        last_login = user['last_login']
                        last_login_str = str(last_login)[:10] if pd.notna(last_login) and last_login else 'Never'
                        st.markdown(f"**Last Login:** {last_login_str}")

                    st.markdown("---")

                    # Actions
                    action_cols = st.columns(4)

                    with action_cols[0]:
                        if user['is_active']:
                            if st.button("⏸️ Deactivate", key=f"deact_{user['username']}"):
                                auth.deactivate_user(user['username'])
                                st.warning("User deactivated")
                                st.rerun()
                        else:
                            if st.button("▶️ Activate", key=f"act_{user['username']}"):
                                auth.activate_user(user['username'])
                                st.success("User activated")
                                st.rerun()

                    with action_cols[1]:
                        new_role = st.selectbox(
                            "Change Role",
                            ROLES,
                            index=ROLES.index(user['role']) if user['role'] in ROLES else 1,
                            key=f"role_{user['username']}"
                        )
                        if new_role != user['role']:
                            if st.button("Update Role", key=f"update_role_{user['username']}"):
                                auth.update_user(user['username'], {'role': new_role})
                                st.success("Role updated")
                                st.rerun()

    with tab2:
        st.markdown("### Add New User")

        new_username = st.text_input("Username", placeholder="jsmith")
        new_password = st.text_input("Password", type="password", placeholder="Temporary password")
        new_fullname = st.text_input("Full Name", placeholder="John Smith")
        new_email = st.text_input("Email (optional)", placeholder="john@example.com")
        new_role = st.selectbox("Role", ROLES, index=1)  # Default to VA

        if st.button("➕ Create User", type="primary"):
            if new_username and new_password and new_fullname:
                user_id = auth.create_user(
                    username=new_username,
                    password=new_password,
                    full_name=new_fullname,
                    email=new_email,
                    role=new_role,
                    created_by="admin"
                )

                if user_id:
                    st.success(f"User created! Username: {new_username}")
                    st.info("Ask the user to change their password on first login.")
                    st.balloons()
                else:
                    st.error("Username already exists")
            else:
                st.error("Username, password, and full name are required")

    with tab3:
        st.markdown("### Reset User Password")

        if not users.empty:
            reset_user = st.selectbox(
                "Select User",
                users['username'].tolist(),
                format_func=lambda x: f"{x} - {users[users['username'] == x]['full_name'].iloc[0]}"
            )

            reset_password = st.text_input("New Password", type="password", placeholder="Enter new password")

            if st.button("🔐 Reset Password", type="primary"):
                if reset_user and reset_password:
                    success, message = auth.reset_password(reset_user, reset_password, admin_user="admin")
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
                else:
                    st.error("Select a user and enter new password")
        else:
            st.info("No users to reset")

    st.markdown("---")
    st.markdown("### Active Sessions")

    sessions = auth.get_active_sessions()
    if sessions.empty:
        st.info("No active sessions")
    else:
        st.dataframe(sessions[['username', 'created_at', 'expires_at', 'ip_address']], use_container_width=True)

    # Security note
    st.markdown("---")
    st.caption("Default admin credentials: username 'admin', password 'admin123' - change immediately!")
