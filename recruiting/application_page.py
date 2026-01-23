"""
VA Application Portal - Orteza Groups
Professional application form for Virtual Assistant positions at Lifeline Home Buyers.

Run with: streamlit run application_page.py --server.port 8502
"""

# CRITICAL: Set up Python path FIRST before any other imports
import sys
import os
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

import streamlit as st
from datetime import datetime, date
from dotenv import load_dotenv

load_dotenv()

# Country salary data
COUNTRIES = {
    "Rwanda": {"currency": "RWF", "salary": "210,000", "flag": "🇷🇼"},
    "Uganda": {"currency": "UGX", "salary": "500,000", "flag": "🇺🇬"},
    "Kenya": {"currency": "KES", "salary": "20,000", "flag": "🇰🇪"},
    "Tanzania": {"currency": "TZS", "salary": "375,000", "flag": "🇹🇿"},
    "Burundi": {"currency": "BIF", "salary": "450,000", "flag": "🇧🇮"},
    "Philippines": {"currency": "PHP", "salary": "10,000", "flag": "🇵🇭"},
    "India": {"currency": "INR", "salary": "12,500", "flag": "🇮🇳"},
    "Pakistan": {"currency": "PKR", "salary": "42,000", "flag": "🇵🇰"},
    "Bangladesh": {"currency": "BDT", "salary": "18,000", "flag": "🇧🇩"},
    "Nepal": {"currency": "NPR", "salary": "20,000", "flag": "🇳🇵"},
    "Sri Lanka": {"currency": "LKR", "salary": "48,000", "flag": "🇱🇰"},
    "South Africa": {"currency": "ZAR", "salary": "2,800", "flag": "🇿🇦"},
    "Ghana": {"currency": "GHS", "salary": "2,400", "flag": "🇬🇭"},
    "Nigeria": {"currency": "NGN", "salary": "230,000", "flag": "🇳🇬"},
}

# Page config
st.set_page_config(
    page_title="Careers | Lifeline Home Buyers - Orteza Groups",
    page_icon="🏢",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Professional CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .stApp {
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Header styles */
    .hero-section {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 50%, #1e3a5f 100%);
        padding: 3rem 2rem;
        border-radius: 0 0 24px 24px;
        margin: -6rem -4rem 2rem -4rem;
        text-align: center;
        box-shadow: 0 4px 20px rgba(30, 58, 95, 0.15);
    }

    .company-badge {
        display: inline-block;
        background: rgba(255,255,255,0.1);
        padding: 0.4rem 1rem;
        border-radius: 20px;
        font-size: 0.75rem;
        color: rgba(255,255,255,0.8);
        letter-spacing: 0.5px;
        text-transform: uppercase;
        margin-bottom: 1rem;
        border: 1px solid rgba(255,255,255,0.2);
    }

    .hero-title {
        font-size: 2.5rem;
        font-weight: 700;
        color: white;
        margin-bottom: 0.5rem;
        letter-spacing: -0.5px;
    }

    .hero-subtitle {
        font-size: 1.1rem;
        color: rgba(255,255,255,0.85);
        font-weight: 400;
        margin-bottom: 1.5rem;
    }

    .hero-tag {
        display: inline-block;
        background: #10b981;
        color: white;
        padding: 0.5rem 1.25rem;
        border-radius: 25px;
        font-size: 0.9rem;
        font-weight: 500;
    }

    /* Card styles */
    .info-card {
        background: white;
        padding: 1.75rem;
        border-radius: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 12px rgba(0,0,0,0.04);
        margin-bottom: 1.5rem;
        border: 1px solid #e2e8f0;
    }

    .card-header {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin-bottom: 1rem;
        padding-bottom: 1rem;
        border-bottom: 1px solid #f1f5f9;
    }

    .card-icon {
        width: 40px;
        height: 40px;
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.2rem;
    }

    .card-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #1e293b;
        margin: 0;
    }

    /* Salary display */
    .salary-display {
        background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
        border: 2px solid #10b981;
        padding: 1.5rem;
        border-radius: 16px;
        text-align: center;
        margin: 1.5rem 0;
    }

    .salary-label {
        font-size: 0.85rem;
        color: #065f46;
        text-transform: uppercase;
        letter-spacing: 1px;
        font-weight: 500;
        margin-bottom: 0.5rem;
    }

    .salary-amount {
        font-size: 2.25rem;
        font-weight: 700;
        color: #047857;
        line-height: 1;
    }

    .salary-period {
        font-size: 0.9rem;
        color: #065f46;
        margin-top: 0.25rem;
    }

    /* Benefits grid */
    .benefits-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 1rem;
        margin: 1rem 0;
    }

    .benefit-item {
        background: #f8fafc;
        padding: 1rem;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
    }

    .benefit-icon {
        font-size: 1.5rem;
        margin-bottom: 0.5rem;
    }

    .benefit-title {
        font-size: 0.9rem;
        font-weight: 600;
        color: #1e293b;
        margin-bottom: 0.25rem;
    }

    .benefit-desc {
        font-size: 0.8rem;
        color: #64748b;
    }

    /* Form styles */
    .form-section {
        background: white;
        padding: 2rem;
        border-radius: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 12px rgba(0,0,0,0.04);
        margin-bottom: 1.5rem;
        border: 1px solid #e2e8f0;
    }

    .section-title {
        font-size: 1rem;
        font-weight: 600;
        color: #1e293b;
        margin-bottom: 1.25rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .section-number {
        width: 24px;
        height: 24px;
        background: #1e3a5f;
        color: white;
        border-radius: 50%;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 0.75rem;
        font-weight: 600;
    }

    /* Input styling */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea {
        border-radius: 10px !important;
        border: 1.5px solid #e2e8f0 !important;
        padding: 0.75rem 1rem !important;
        font-size: 0.95rem !important;
        transition: all 0.2s ease !important;
        background-color: #ffffff !important;
        color: #1e293b !important;
    }

    .stTextInput > div > div > input::placeholder,
    .stTextArea > div > div > textarea::placeholder {
        color: #94a3b8 !important;
    }

    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: #1e3a5f !important;
        box-shadow: 0 0 0 3px rgba(30, 58, 95, 0.1) !important;
        background-color: #ffffff !important;
        color: #1e293b !important;
    }

    /* Selectbox styling */
    .stSelectbox > div > div {
        background-color: #ffffff !important;
        color: #1e293b !important;
    }

    .stSelectbox [data-baseweb="select"] {
        background-color: #ffffff !important;
    }

    .stSelectbox [data-baseweb="select"] > div {
        background-color: #ffffff !important;
        color: #1e293b !important;
        border-radius: 10px !important;
        border: 1.5px solid #e2e8f0 !important;
    }

    /* Radio buttons */
    .stRadio > div {
        background-color: transparent !important;
    }

    .stRadio label {
        color: #1e293b !important;
    }

    /* Checkbox */
    .stCheckbox label {
        color: #1e293b !important;
    }

    /* Labels */
    .stTextInput label, .stTextArea label, .stSelectbox label, .stDateInput label {
        color: #374151 !important;
        font-weight: 500 !important;
    }

    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%) !important;
        color: white !important;
        border: none !important;
        padding: 0.875rem 2rem !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        border-radius: 12px !important;
        width: 100% !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 12px rgba(30, 58, 95, 0.25) !important;
    }

    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(30, 58, 95, 0.35) !important;
    }

    /* Success state */
    .success-container {
        background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
        padding: 3rem 2rem;
        border-radius: 20px;
        text-align: center;
        border: 2px solid #10b981;
        margin: 2rem 0;
    }

    .success-icon {
        font-size: 4rem;
        margin-bottom: 1rem;
    }

    .success-title {
        font-size: 1.75rem;
        font-weight: 700;
        color: #065f46;
        margin-bottom: 0.5rem;
    }

    .success-message {
        font-size: 1rem;
        color: #047857;
        line-height: 1.6;
    }

    /* Footer */
    .footer {
        text-align: center;
        padding: 2rem;
        color: #64748b;
        font-size: 0.85rem;
    }

    .footer-brand {
        font-weight: 600;
        color: #1e3a5f;
    }

    /* Checkbox styling */
    .stCheckbox {
        background: #f8fafc;
        padding: 1rem;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
    }

    /* Requirements list */
    .requirements-list {
        list-style: none;
        padding: 0;
        margin: 0;
    }

    .requirements-list li {
        display: flex;
        align-items: flex-start;
        gap: 0.75rem;
        padding: 0.75rem 0;
        border-bottom: 1px solid #f1f5f9;
        font-size: 0.95rem;
        color: #475569;
    }

    .requirements-list li:last-child {
        border-bottom: none;
    }

    .check-icon {
        color: #10b981;
        font-weight: bold;
    }

    /* Mobile Responsive - Fix shaky edges */
    @media (max-width: 768px) {
        .stApp {
            overflow-x: hidden !important;
        }

        .main .block-container {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            max-width: 100% !important;
        }

        .hero-section {
            margin: -1rem -1rem 1.5rem -1rem !important;
            padding: 2rem 1rem !important;
            border-radius: 0 0 16px 16px !important;
        }

        .hero-title {
            font-size: 1.8rem !important;
        }

        .hero-subtitle {
            font-size: 1rem !important;
        }

        .benefits-grid {
            grid-template-columns: 1fr !important;
            gap: 0.75rem !important;
        }

        .form-container {
            padding: 1.5rem 1rem !important;
        }

        .stTextInput > div > div,
        .stSelectbox > div > div,
        .stTextArea > div > div {
            max-width: 100% !important;
        }
    }

    /* Prevent horizontal scroll globally */
    html, body {
        overflow-x: hidden !important;
        max-width: 100vw !important;
    }

    /* Expander Job Description - FORCE visible in ALL modes */
    [data-testid="stExpander"] {
        background-color: #ffffff !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 12px !important;
    }

    [data-testid="stExpander"] details {
        background-color: #ffffff !important;
    }

    [data-testid="stExpander"] summary {
        background-color: #f8fafc !important;
        color: #1e3a5f !important;
        font-weight: 600 !important;
    }

    [data-testid="stExpander"] summary:hover {
        background-color: #f1f5f9 !important;
    }

    [data-testid="stExpander"] [data-testid="stMarkdownContainer"] {
        background-color: #ffffff !important;
    }

    [data-testid="stExpander"] [data-testid="stMarkdownContainer"] * {
        color: #374151 !important;
    }

    [data-testid="stExpander"] [data-testid="stMarkdownContainer"] h3 {
        color: #1e3a5f !important;
        font-weight: 600 !important;
    }

    [data-testid="stExpander"] [data-testid="stMarkdownContainer"] strong {
        color: #1e3a5f !important;
    }

    [data-testid="stExpander"] [data-testid="stMarkdownContainer"] li {
        color: #374151 !important;
    }

    [data-testid="stExpander"] [data-testid="stMarkdownContainer"] hr {
        border-color: #e5e7eb !important;
    }

    /* Force light theme inside expander - works in all modes */
    [data-testid="stExpander"] {
        background-color: #ffffff !important;
    }

    [data-testid="stExpander"] div,
    [data-testid="stExpander"] p,
    [data-testid="stExpander"] span,
    [data-testid="stExpander"] li,
    [data-testid="stExpander"] ul,
    [data-testid="stExpander"] strong,
    [data-testid="stExpander"] em {
        color: #374151 !important;
        background-color: transparent !important;
    }

    [data-testid="stExpander"] h1,
    [data-testid="stExpander"] h2,
    [data-testid="stExpander"] h3,
    [data-testid="stExpander"] h4 {
        color: #1e3a5f !important;
    }

    /* Expander header button text */
    [data-testid="stExpander"] summary,
    [data-testid="stExpander"] button,
    [data-testid="stExpander"] [data-testid="stExpanderToggleIcon"] {
        color: #374151 !important;
    }

    /* Media query for system dark mode */
    @media (prefers-color-scheme: dark) {
        [data-testid="stExpander"] {
            background-color: #ffffff !important;
            border: 1px solid #e5e7eb !important;
        }

        [data-testid="stExpander"] div,
        [data-testid="stExpander"] p,
        [data-testid="stExpander"] span,
        [data-testid="stExpander"] li {
            color: #374151 !important;
        }
    }
</style>
""", unsafe_allow_html=True)

# Try to import application system
APP_SYSTEM_AVAILABLE = False
try:
    # Try relative import first (when running as module)
    from .va_applications import VAApplications
    APP_SYSTEM_AVAILABLE = True
except ImportError:
    try:
        # Try direct import (when running as script)
        from va_applications import VAApplications
        APP_SYSTEM_AVAILABLE = True
    except ImportError:
        try:
            # Add current directory to path and try again
            import sys
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from va_applications import VAApplications
            APP_SYSTEM_AVAILABLE = True
        except Exception as e:
            print(f"Could not import VAApplications: {e}")
            APP_SYSTEM_AVAILABLE = False


def main():
    # Hero Section
    st.markdown("""
    <div class="hero-section">
        <div class="company-badge">Orteza Groups of Companies</div>
        <h1 class="hero-title">Join Lifeline Home Buyers</h1>
        <p class="hero-subtitle">Build your career as a Virtual Assistant in Real Estate</p>
        <span class="hero-tag">🌍 Remote Position • Now Hiring</span>
    </div>
    """, unsafe_allow_html=True)

    # Check for success state
    if st.session_state.get('application_submitted'):
        st.markdown("""
        <div class="success-container">
            <div class="success-icon">✅</div>
            <h2 class="success-title">Application Received!</h2>
            <p class="success-message">
                Thank you for applying to Lifeline Home Buyers.<br>
                Our team will review your application and contact you within <strong>48 hours</strong>.<br><br>
                Please check your email for updates and next steps.
            </p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Submit Another Application"):
            st.session_state.application_submitted = False
            st.rerun()

        st.markdown("""
        <div class="footer">
            <span class="footer-brand">Lifeline Home Buyers</span> • A company of Orteza Groups<br>
            Columbus, Ohio, USA
        </div>
        """, unsafe_allow_html=True)
        return

    # Country Selection & Salary Display
    st.markdown("""
    <div class="info-card">
        <div class="card-header">
            <div class="card-icon">🌍</div>
            <h3 class="card-title">Select Your Location</h3>
        </div>
    </div>
    """, unsafe_allow_html=True)

    country = st.selectbox(
        "Where are you applying from?",
        options=["Select your country..."] + list(COUNTRIES.keys()),
        label_visibility="collapsed"
    )

    if country and country != "Select your country...":
        country_data = COUNTRIES[country]
        st.markdown(f"""
        <div class="salary-display">
            <div class="salary-label">Monthly Compensation</div>
            <div class="salary-amount">{country_data['flag']} {country_data['salary']} {country_data['currency']}</div>
            <div class="salary-period">Paid monthly • Full-time position</div>
        </div>
        """, unsafe_allow_html=True)

    # Position Overview
    st.markdown("""
    <div class="info-card">
        <div class="card-header">
            <div class="card-icon">💼</div>
            <h3 class="card-title">Position Overview</h3>
        </div>
        <p style="color: #475569; line-height: 1.7; margin-bottom: 1.5rem;">
            <strong>Lifeline Home Buyers</strong>, a subsidiary of <strong>Orteza Groups</strong>, is a real estate investment company based in Columbus, Ohio. We help homeowners in difficult situations sell their properties quickly for cash. We're looking for motivated Virtual Assistants to join our acquisitions team.
        </p>
        <div class="benefits-grid">
            <div class="benefit-item">
                <div class="benefit-icon">⏰</div>
                <div class="benefit-title">40 Hours/Week</div>
                <div class="benefit-desc">Full-time commitment</div>
            </div>
            <div class="benefit-item">
                <div class="benefit-icon">📅</div>
                <div class="benefit-title">6 Days/Week</div>
                <div class="benefit-desc">Sunday off + 1 day of choice</div>
            </div>
            <div class="benefit-item">
                <div class="benefit-icon">🏠</div>
                <div class="benefit-title">100% Remote</div>
                <div class="benefit-desc">Work from anywhere</div>
            </div>
            <div class="benefit-item">
                <div class="benefit-icon">💰</div>
                <div class="benefit-title">Monthly Pay</div>
                <div class="benefit-desc">Reliable income</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # What You'll Do
    with st.expander("📋 View Full Job Description", expanded=False):
        st.markdown("""
        ### What You'll Do

        - **Cold Calling:** Contact property owners from our lead lists using our dialer system
        - **Lead Qualification:** Ask qualifying questions to identify motivated sellers
        - **Data Entry:** Log call outcomes and update lead information in our CRM
        - **Follow-ups:** Make follow-up calls to warm leads
        - **Appointment Setting:** Schedule property walkthroughs for our acquisitions team
        - **Skip Tracing:** Use our tools to find contact information for property owners

        ---

        ### Requirements

        - Excellent English communication skills (spoken and written)
        - Reliable internet connection (minimum 10 Mbps)
        - Computer with headset/microphone
        - Quiet workspace for making calls
        - Available to work during US Eastern Time business hours (9 AM - 6 PM EST)
        - Self-motivated and able to work independently
        - **Bachelor's degree not required, but preferred** — we value skills and attitude over credentials

        ---

        ### What We Provide

        - Full training on our systems and scripts
        - All leads and data provided
        - Dialer software and CRM access
        - Ongoing coaching and support
        - Performance bonuses for appointments that close

        ---

        ### Schedule

        - **40 hours per week**
        - **Sunday is a mandatory day off**
        - **Choose 1 additional day off** (Monday-Saturday)
        - Working hours aligned with US Eastern Time

        ---

        *This is an independent contractor position.*
        """)

    if not APP_SYSTEM_AVAILABLE:
        st.error("Application system is currently unavailable. Please try again later.")
        return

    if not country or country == "Select your country...":
        st.info("👆 Please select your country above to continue with the application.")
        return

    # Application Form
    st.markdown("---")
    st.markdown("## 📝 Application Form")

    with st.form("va_application_form"):

        # Section 1: Personal Information
        st.markdown("""
        <div class="section-title">
            <span class="section-number">1</span>
            Personal Information
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full Name *", placeholder="John Doe")
            email = st.text_input("Email Address *", placeholder="john@example.com")
        with col2:
            phone = st.text_input("Phone Number (with country code) *", placeholder="+254 712 345 678")
            city = st.text_input("City *", placeholder="Nairobi")

        timezone = st.selectbox(
            "Your Timezone *",
            [
                "Select timezone...",
                "Africa/Nairobi (EAT, GMT+3)",
                "Africa/Kampala (EAT, GMT+3)",
                "Africa/Kigali (CAT, GMT+2)",
                "Africa/Dar_es_Salaam (EAT, GMT+3)",
                "Africa/Bujumbura (CAT, GMT+2)",
                "Asia/Manila (PHT, GMT+8)",
                "Asia/Kolkata (IST, GMT+5:30)",
                "Asia/Karachi (PKT, GMT+5)",
                "Asia/Dhaka (BST, GMT+6)",
                "Asia/Kathmandu (NPT, GMT+5:45)",
                "Asia/Colombo (IST, GMT+5:30)",
                "Africa/Johannesburg (SAST, GMT+2)",
                "Africa/Lagos (WAT, GMT+1)",
                "Africa/Accra (GMT)",
                "Other"
            ]
        )

        st.markdown("---")

        # Section 2: Experience
        st.markdown("""
        <div class="section-title">
            <span class="section-number">2</span>
            Experience & Skills
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            education_level = st.selectbox(
                "Highest Education Level *",
                [
                    "Select level...",
                    "High School / Secondary School",
                    "Some College / Diploma",
                    "Bachelor's Degree",
                    "Master's Degree or higher"
                ]
            )
            years_exp = st.selectbox(
                "Years of VA/Call Center Experience",
                ["No experience", "Less than 1 year", "1-2 years", "2-3 years", "3-5 years", "5+ years"]
            )
        with col2:
            english_level = st.selectbox(
                "English Proficiency *",
                [
                    "Select level...",
                    "Native Speaker",
                    "Fluent (C1-C2)",
                    "Advanced (B2)",
                    "Intermediate (B1)",
                    "Basic (A1-A2)"
                ]
            )
            current_job = st.text_input("Current/Most Recent Job Title", placeholder="Customer Service Rep")

        cold_calling_exp = st.text_area(
            "Cold Calling Experience",
            placeholder="Describe any cold calling or telemarketing experience. How many calls per day? What industries? What were your results?",
            height=100
        )

        real_estate_exp = st.text_area(
            "Real Estate Experience (if any)",
            placeholder="Have you worked in real estate before? As a VA, agent, or other role?",
            height=100
        )

        st.markdown("---")

        # Section 3: Availability
        st.markdown("""
        <div class="section-title">
            <span class="section-number">3</span>
            Availability
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            preferred_day_off = st.selectbox(
                "Preferred Second Day Off (Sunday is mandatory off) *",
                ["Select day...", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
            )
            start_date = st.date_input(
                "Available Start Date *",
                min_value=date.today()
            )
        with col2:
            us_hours = st.radio(
                "Can you work US Eastern Time hours? (9 AM - 6 PM EST) *",
                ["Yes, fully available", "Partially (some overlap)", "No, not available"],
                horizontal=False
            )

        st.markdown("---")

        # Section 4: Technical Requirements
        st.markdown("""
        <div class="section-title">
            <span class="section-number">4</span>
            Technical Setup
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns(2)
        with col1:
            internet_speed = st.selectbox(
                "Internet Speed *",
                ["Select...", "50+ Mbps", "25-50 Mbps", "10-25 Mbps", "Less than 10 Mbps", "Not sure"]
            )
        with col2:
            st.markdown("**Equipment Check:**")
            has_computer = st.checkbox("I have a computer/laptop", value=True)
            has_headset = st.checkbox("I have a headset with microphone", value=True)
            has_quiet_space = st.checkbox("I have a quiet workspace for calls", value=True)

        st.markdown("---")

        # Section 5: Final Questions
        st.markdown("""
        <div class="section-title">
            <span class="section-number">5</span>
            Tell Us About Yourself
        </div>
        """, unsafe_allow_html=True)

        why_interested = st.text_area(
            "Why are you interested in this position? *",
            placeholder="Tell us why you want to work as a VA for a real estate company. What excites you about this opportunity?",
            height=150
        )

        st.markdown("---")

        # Section 6: Resume
        st.markdown("""
        <div class="section-title">
            <span class="section-number">6</span>
            Upload Resume
        </div>
        """, unsafe_allow_html=True)

        resume_file = st.file_uploader(
            "Upload your Resume (PDF, DOC, DOCX) *",
            type=['pdf', 'doc', 'docx'],
            help="Maximum file size: 5MB"
        )

        st.markdown("---")

        # Agreement
        agree = st.checkbox(
            "I confirm that all information provided is accurate. I understand this is an independent contractor position with Lifeline Home Buyers (Orteza Groups) and I am committed to working 40 hours per week."
        )

        # Submit button
        submitted = st.form_submit_button("Submit Application", type="primary", use_container_width=True)

        if submitted:
            # Validation
            errors = []
            if not full_name:
                errors.append("Full name is required")
            if not email or "@" not in email:
                errors.append("Valid email is required")
            if not phone:
                errors.append("Phone number is required")
            if not city:
                errors.append("City is required")
            if timezone == "Select timezone...":
                errors.append("Please select your timezone")
            if education_level == "Select level...":
                errors.append("Please select your education level")
            if english_level == "Select level...":
                errors.append("Please select your English proficiency")
            if preferred_day_off == "Select day...":
                errors.append("Please select your preferred day off")
            if internet_speed == "Select...":
                errors.append("Please select your internet speed")
            if not why_interested:
                errors.append("Please tell us why you're interested")
            if not resume_file:
                errors.append("Please upload your resume")
            if not agree:
                errors.append("Please confirm the information is accurate")

            if errors:
                for error in errors:
                    st.error(error)
            else:
                # Map experience to years
                exp_map = {
                    "No experience": 0,
                    "Less than 1 year": 0,
                    "1-2 years": 1,
                    "2-3 years": 2,
                    "3-5 years": 4,
                    "5+ years": 5
                }

                # Prepare data
                app_data = {
                    'full_name': full_name,
                    'email': email,
                    'phone': phone,
                    'country': country,
                    'timezone': timezone,
                    'cold_calling_experience': cold_calling_exp,
                    'real_estate_experience': real_estate_exp,
                    'years_experience': exp_map.get(years_exp, 0),
                    'current_job': current_job,
                    'hours_per_week': 40,
                    'available_start_date': start_date,
                    'us_timezone_hours': us_hours == "Yes, fully available",
                    'internet_speed': internet_speed,
                    'has_computer': has_computer,
                    'has_headset': has_headset,
                    'has_quiet_workspace': has_quiet_space,
                    'english_proficiency': english_level,
                    'why_interested': f"City: {city}\nPreferred day off: {preferred_day_off}\nEducation: {education_level}\n\n{why_interested}",
                    'resume_filename': resume_file.name if resume_file else None,
                    'resume_data': resume_file.read() if resume_file else None
                }

                # Submit
                apps = VAApplications()
                success, message = apps.submit_application(app_data)

                if success:
                    st.session_state.application_submitted = True
                    st.rerun()
                else:
                    st.error(message)

    # Footer
    st.markdown("""
    <div class="footer">
        <span class="footer-brand">Lifeline Home Buyers</span> • A company of Orteza Groups<br>
        Columbus, Ohio, USA<br><br>
        <small>© 2024 Orteza Groups. All rights reserved.</small>
    </div>
    """, unsafe_allow_html=True)


def recording_page():
    """Recording/Interview status page - accessed via email link."""
    # Import the recording page functionality
    try:
        from recording_page import main as recording_main
        recording_main()
    except ImportError:
        st.error("Recording page not available. Please contact support.")


if __name__ == "__main__":
    # Check for query parameters to determine which page to show
    # Use experimental API for older Streamlit versions
    try:
        query_params = st.query_params
        page = query_params.get("page", "apply")
        email_param = query_params.get("email", "")
    except AttributeError:
        # Fallback for older Streamlit versions
        query_params = st.experimental_get_query_params()
        page = query_params.get("page", ["apply"])[0]
        email_param = query_params.get("email", [""])[0]

    if page == "recording":
        # Pre-fill email if provided in URL
        if email_param:
            st.session_state['prefill_email'] = email_param
        recording_page()
    else:
        main()
