"""
Lifeline Home Buyers - Configuration Settings

Centralized configuration for the entire application.
Loads from environment variables and provides sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ========================================
# Project Paths
# ========================================
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / 'config'
DATA_DIR = BASE_DIR / 'data'
RAW_DATA_DIR = DATA_DIR / 'sellers' / 'raw'
PROCESSED_DATA_DIR = DATA_DIR / 'sellers' / 'processed'
REPORTS_DIR = PROCESSED_DATA_DIR / 'reports'
TEMPLATES_DIR = BASE_DIR / 'templates'
LOGS_DIR = BASE_DIR / 'logs'
WEB_DIR = BASE_DIR / 'web'
STATIC_DIR = WEB_DIR / 'static'
WEB_TEMPLATES_DIR = WEB_DIR / 'templates'

# Create directories if they don't exist
for directory in [DATA_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR, REPORTS_DIR, LOGS_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# ========================================
# API Keys & Credentials
# ========================================
# BatchData.com API - Real skip tracing (~$0.15-0.25 per record)
# Get your API key at: https://batchdata.com

# Try to get from Streamlit secrets first (for Streamlit Cloud deployment)
# Fall back to environment variables (for local development)
def _get_secret(key, default=''):
    """Get secret from Streamlit secrets or environment variables."""
    try:
        import streamlit as st
        if hasattr(st, 'secrets') and key in st.secrets:
            return st.secrets[key]
    except:
        pass
    return os.getenv(key, default)

BATCHDATA_API_KEY = _get_secret('BATCHDATA_API_KEY', '')

# Legacy BatchSkipTracing (deprecated)
BATCH_SKIP_TRACE_API_KEY = os.getenv('BATCH_SKIP_TRACE_API_KEY', '')
BATCH_SKIP_TRACE_URL = os.getenv('BATCH_SKIP_TRACE_URL', 'https://api.batchskiptracing.com/v1')

# Google Maps API (for Street View images)
GOOGLE_MAPS_API_KEY = _get_secret('GOOGLE_MAPS_API_KEY', '')

BEEN_VERIFIED_USERNAME = os.getenv('BEEN_VERIFIED_USERNAME', '')
BEEN_VERIFIED_PASSWORD = os.getenv('BEEN_VERIFIED_PASSWORD', '')

# ========================================
# Data Source URLs
# ========================================
# Franklin County Tax Data
FRANKLIN_COUNTY_AUDITOR_URL = "https://property.franklincountyauditor.com/_web/search/commonsearch.aspx"
FRANKLIN_COUNTY_TREASURER_URL = "https://treapropsearch.franklincountyohio.gov/"

# Columbus Code Enforcement
COLUMBUS_CODE_ENFORCEMENT_URL = "https://portal.columbus.gov/permits/Cap/CapHome.aspx?module=Enforcement"
COLUMBUS_311_URL = "https://311.columbus.gov/"

# Do Not Call Registry
DNC_REGISTRY_URL = "https://www.donotcall.gov/"
DNC_API_URL = "https://telemarketing.donotcall.gov/"

# ========================================
# Scraping Settings
# ========================================
REQUEST_DELAY = int(os.getenv('REQUEST_DELAY', 2))  # Seconds between requests
REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', 30))  # Seconds
MAX_RETRIES = int(os.getenv('MAX_RETRIES', 3))

USER_AGENT = os.getenv(
    'USER_AGENT',
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Proxy settings
USE_PROXY = os.getenv('USE_PROXY', 'false').lower() == 'true'
PROXY_URL = os.getenv('PROXY_URL', '')

# ========================================
# Motivation Scoring Weights
# ========================================
# These weights determine how each factor contributes to the final score (0-100)
MOTIVATION_SCORE_WEIGHTS = {
    'tax_delinquency': 35,          # Years behind on taxes
    'tax_debt_ratio': 30,           # Debt as % of property value
    'code_violations': 20,          # Property neglect indicators
    'absentee_owner': 15,           # Owner doesn't live at property
    'ownership_lifecycle': 10,      # Estate planning probability (age proxy)
    'vacancy': 25,                  # Vacancy indicators
    'out_of_state': 10,             # Out-of-state owner (long-distance landlord)
    'inheritance': 15,              # Estate/trust/heir indicators in name
    'corporate_owner': 8,           # LLC/Corp owner (tired investor)
    'probate': 40,                  # Property in probate (HIGHEST VALUE)
    'pre_foreclosure': 35,          # Scheduled for sheriff sale
}

# Tier thresholds (0-100 score)
TIER_1_THRESHOLD = int(os.getenv('TIER_1_THRESHOLD', 80))  # 5-star, call immediately
TIER_2_THRESHOLD = int(os.getenv('TIER_2_THRESHOLD', 60))  # 4-star, call within 48hrs
TIER_3_THRESHOLD = int(os.getenv('TIER_3_THRESHOLD', 40))  # 3-star, call this week
TIER_4_THRESHOLD = int(os.getenv('TIER_4_THRESHOLD', 0))   # 1-2 star, low priority

# Pricing tiers (for reference)
TIER_1_PRICE = int(os.getenv('TIER_1_PRICE', 100))
TIER_2_PRICE = int(os.getenv('TIER_2_PRICE', 75))
TIER_3_PRICE = int(os.getenv('TIER_3_PRICE', 50))

# ========================================
# Export Settings
# ========================================
DEFAULT_EXPORT_FORMAT = os.getenv('DEFAULT_EXPORT_FORMAT', 'csv')  # csv, json, excel
ENABLE_PDF_REPORTS = os.getenv('ENABLE_PDF_REPORTS', 'true').lower() == 'true'
ENABLE_JSON_EXPORT = os.getenv('ENABLE_JSON_EXPORT', 'true').lower() == 'true'

# CSV export columns
CSV_EXPORT_COLUMNS = [
    'address',
    'owner_name',
    'mailing_address',
    'phone',
    'email',
    'motivation_score',
    'tier',
    'rating',
    'reasons',
    'taxes_owed',
    'years_delinquent',
    'assessed_value',
    'tax_debt_ratio',
    'code_violations',
    'is_absentee',
    'owner_age',
    'dnc_status',
    'safe_to_call',
    'parcel_number',
    'property_type',
    'square_feet',
    'bedrooms',
    'bathrooms',
    'year_built',
]

# ========================================
# Database Settings
# ========================================
USE_DATABASE = os.getenv('USE_DATABASE', 'false').lower() == 'true'
DATABASE_PATH = Path(os.getenv('DATABASE_PATH', str(DATA_DIR / 'leads.db')))
DATABASE_TYPE = os.getenv('DATABASE_TYPE', 'sqlite')  # sqlite, postgresql, mysql

# PostgreSQL settings (if using)
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_NAME = os.getenv('DB_NAME', 'aerial_leads')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')

# Build database URL
if DATABASE_TYPE == 'sqlite':
    DATABASE_URL = f'sqlite:///{DATABASE_PATH}'
elif DATABASE_TYPE == 'postgresql':
    DATABASE_URL = f'postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
elif DATABASE_TYPE == 'mysql':
    DATABASE_URL = f'mysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}'
else:
    DATABASE_URL = f'sqlite:///{DATABASE_PATH}'

# ========================================
# Logging Settings
# ========================================
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_FILE = Path(os.getenv('LOG_FILE', str(LOGS_DIR / 'lifeline.log')))
LOG_FORMAT = os.getenv(
    'LOG_FORMAT',
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Rich logging format (for terminal)
RICH_LOG_FORMAT = "[%(asctime)s] %(message)s"

# ========================================
# Web Dashboard Settings
# ========================================
FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
FLASK_DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))
FLASK_HOST = os.getenv('FLASK_HOST', '0.0.0.0')

# ========================================
# Feature Flags
# ========================================
ENABLE_CODE_VIOLATIONS_SCRAPER = os.getenv('ENABLE_CODE_VIOLATIONS_SCRAPER', 'true').lower() == 'true'
ENABLE_DNC_SCRUBBING = os.getenv('ENABLE_DNC_SCRUBBING', 'true').lower() == 'true'
ENABLE_VACANCY_DETECTION = os.getenv('ENABLE_VACANCY_DETECTION', 'true').lower() == 'true'
ENABLE_COMPARABLE_SALES = os.getenv('ENABLE_COMPARABLE_SALES', 'false').lower() == 'true'

# ========================================
# Email Notification Settings (optional)
# ========================================
SMTP_HOST = os.getenv('SMTP_HOST', '')
SMTP_PORT = int(os.getenv('SMTP_PORT', 587))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
NOTIFICATION_EMAIL = os.getenv('NOTIFICATION_EMAIL', '')

# ========================================
# Business Logic Constants
# ========================================
# Minimum years tax delinquent to consider
MIN_YEARS_DELINQUENT = 2

# Minimum motivation score to export
MIN_MOTIVATION_SCORE = 40

# Maximum results to scrape in one session
MAX_SCRAPE_RESULTS = 1000

# Property type filters
PROPERTY_TYPES = ['residential', 'commercial', 'multi-family', 'land']
DEFAULT_PROPERTY_TYPE = 'residential'

# Code violation severity levels
VIOLATION_SEVERITY = {
    'critical': ['housing', 'safety', 'structural'],
    'major': ['property maintenance', 'zoning'],
    'minor': ['landscaping', 'cosmetic'],
}

# ========================================
# Legal Compliance
# ========================================
# Opt-out list file
OPT_OUT_FILE = DATA_DIR / 'opt_out_list.json'

# Legal disclaimer template
LEGAL_DISCLAIMER = """
LEGAL DISCLAIMER

The contact information provided is sourced from public records.
The buyer is solely responsible for ensuring compliance with all
applicable laws, including but not limited to:

- Telephone Consumer Protection Act (TCPA)
- Fair Debt Collection Practices Act (FDCPA)
- State-specific telemarketing laws
- Do Not Call Registry requirements

RECOMMENDATIONS FOR BUYERS:
1. Scrub phone numbers against Do Not Call Registry
2. Do not use autodialers or prerecorded messages
3. Maintain internal Do Not Call list
4. Keep records of all opt-out requests
5. Call during permitted hours (8am-9pm local time)
6. Identify yourself and purpose of call immediately

SELLER MAKES NO WARRANTY that calling these numbers is
legally permissible. Buyer assumes all legal risk.

By purchasing these leads, you acknowledge you have read
and understand this notice.
"""

# Equal Housing Opportunity statement
EQUAL_HOUSING_STATEMENT = """
EQUAL HOUSING OPPORTUNITY STATEMENT

This lead generation service provides property ownership
information derived from public records for real estate
investment research purposes.

All data is provided without regard to the race, color,
religion, sex, handicap, familial status, or national
origin of property owners.

Motivation scores are calculated based solely on objective
financial distress indicators including tax delinquency,
code violations, and property equity positions.

Buyers agree to comply with all Fair Housing laws in their
use of this information.
"""

# ========================================
# Environment
# ========================================
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')  # development, staging, production
DEBUG_MODE = os.getenv('DEBUG_MODE', 'true').lower() == 'true'

# ========================================
# Version
# ========================================
VERSION = '1.0.0'
APP_NAME = 'Lifeline Home Buyers'
COMPANY_NAME = 'Lifeline Home Buyers LLC'
SUPPORT_EMAIL = 'support@lifelinehomebuyers.com'
