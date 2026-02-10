"""
Qualified Buyers Module

Handles storing and managing qualified buyers (investors who expressed interest).
Used by IDS VAs to add buyers and Admin to view/manage the buyer list.
"""

import os
import logging
import json
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import pandas as pd
from pathlib import Path

logger = logging.getLogger(__name__)

# Data file path
DATA_DIR = Path(__file__).parent.parent / "data" / "buyers"
BUYERS_FILE = DATA_DIR / "qualified_buyers.csv"

# Ensure directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Buyer status options
BUYER_STATUS = ['active', 'inactive', 'vip', 'do_not_contact']
STATUS_DISPLAY = {
    'active': 'Active',
    'inactive': 'Inactive',
    'vip': 'VIP Buyer',
    'do_not_contact': 'Do Not Contact'
}

# Property type options
PROPERTY_TYPES = ['SFR', 'Duplex', 'Triplex', 'Quadplex', 'Multi-Family (5+)', 'Commercial', 'Land', 'Any']

# Condition preferences
CONDITION_PREFS = ['Turnkey', 'Light Rehab', 'Heavy Rehab', 'Gut Job', 'Any']

# Interest level
INTEREST_LEVELS = ['hot', 'warm', 'cold']
INTEREST_DISPLAY = {
    'hot': '🔥 Hot - Ready to buy now',
    'warm': '👍 Warm - Interested',
    'cold': '❄️ Cold - Maybe later'
}


def get_buyers_df() -> pd.DataFrame:
    """Load the qualified buyers list."""
    if BUYERS_FILE.exists():
        return pd.read_csv(BUYERS_FILE)
    else:
        # Create empty DataFrame with schema
        return pd.DataFrame(columns=[
            'id', 'created_at', 'created_by',
            'name', 'company', 'phone', 'phone_2', 'email',
            'address', 'city', 'state', 'zip_code',
            'price_min', 'price_max',
            'property_types', 'areas', 'condition_pref',
            'cash_buyer', 'financing_type',
            'interest_level', 'status',
            'notes', 'last_contacted', 'deals_closed'
        ])


def save_buyers_df(df: pd.DataFrame):
    """Save the buyers DataFrame to CSV."""
    df.to_csv(BUYERS_FILE, index=False)


def add_buyer(
    name: str,
    phone: str,
    created_by: str,
    company: str = '',
    phone_2: str = '',
    email: str = '',
    address: str = '',
    city: str = '',
    state: str = 'OH',
    zip_code: str = '',
    price_min: float = 0,
    price_max: float = 0,
    property_types: List[str] = None,
    areas: str = '',
    condition_pref: str = 'Any',
    cash_buyer: bool = True,
    financing_type: str = '',
    interest_level: str = 'warm',
    notes: str = ''
) -> Tuple[bool, str, Optional[str]]:
    """
    Add a new qualified buyer to the list.

    Args:
        name: Buyer's name
        phone: Primary phone number
        created_by: Username of VA who added the buyer
        ... other fields

    Returns:
        Tuple of (success, message, buyer_id)
    """
    try:
        df = get_buyers_df()

        # Check for duplicate (same phone)
        if phone and len(df) > 0 and 'phone' in df.columns:
            clean_phone = ''.join(filter(str.isdigit, phone))
            existing_phones = df['phone'].astype(str).apply(lambda x: ''.join(filter(str.isdigit, x)))
            if clean_phone in existing_phones.values:
                return False, "Buyer with this phone number already exists", None

        # Generate ID
        buyer_id = f"BUY_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(df)}"

        # Create new buyer record
        new_buyer = {
            'id': buyer_id,
            'created_at': datetime.now().isoformat(),
            'created_by': created_by,
            'name': name,
            'company': company,
            'phone': phone,
            'phone_2': phone_2,
            'email': email,
            'address': address,
            'city': city,
            'state': state,
            'zip_code': zip_code,
            'price_min': price_min,
            'price_max': price_max,
            'property_types': ','.join(property_types) if property_types else 'Any',
            'areas': areas,
            'condition_pref': condition_pref,
            'cash_buyer': cash_buyer,
            'financing_type': financing_type,
            'interest_level': interest_level,
            'status': 'active',
            'notes': notes,
            'last_contacted': datetime.now().strftime('%Y-%m-%d'),
            'deals_closed': 0
        }

        # Add to DataFrame
        df = pd.concat([df, pd.DataFrame([new_buyer])], ignore_index=True)
        save_buyers_df(df)

        logger.info(f"Added new buyer: {name} by {created_by}")
        return True, f"Successfully added buyer: {name}", buyer_id

    except Exception as e:
        logger.error(f"Error adding buyer: {e}")
        return False, f"Error: {str(e)}", None


def update_buyer(buyer_id: str, updates: Dict) -> Tuple[bool, str]:
    """Update a buyer's information."""
    try:
        df = get_buyers_df()

        if buyer_id not in df['id'].values:
            return False, "Buyer not found"

        # Update fields
        for key, value in updates.items():
            if key in df.columns and key != 'id':
                df.loc[df['id'] == buyer_id, key] = value

        save_buyers_df(df)
        return True, "Buyer updated successfully"

    except Exception as e:
        logger.error(f"Error updating buyer: {e}")
        return False, f"Error: {str(e)}"


def get_buyer(buyer_id: str) -> Optional[Dict]:
    """Get a single buyer by ID."""
    df = get_buyers_df()
    if buyer_id in df['id'].values:
        return df[df['id'] == buyer_id].iloc[0].to_dict()
    return None


def get_active_buyers() -> pd.DataFrame:
    """Get all active buyers."""
    df = get_buyers_df()
    if len(df) > 0 and 'status' in df.columns:
        return df[df['status'].isin(['active', 'vip'])]
    return df


def get_buyers_by_criteria(
    price: float = None,
    property_type: str = None,
    area: str = None
) -> pd.DataFrame:
    """
    Find buyers matching deal criteria.

    Args:
        price: Deal price to match against buyer's range
        property_type: Property type to match
        area: Zip code or area to match

    Returns:
        DataFrame of matching buyers
    """
    df = get_active_buyers()

    if len(df) == 0:
        return df

    matches = df.copy()

    # Filter by price range
    if price is not None:
        matches = matches[
            ((matches['price_min'].isna()) | (matches['price_min'] <= price)) &
            ((matches['price_max'].isna()) | (matches['price_max'] >= price) | (matches['price_max'] == 0))
        ]

    # Filter by property type
    if property_type:
        matches = matches[
            (matches['property_types'].isna()) |
            (matches['property_types'].str.contains(property_type, case=False, na=False)) |
            (matches['property_types'].str.contains('Any', case=False, na=False))
        ]

    # Filter by area
    if area:
        matches = matches[
            (matches['areas'].isna()) |
            (matches['areas'] == '') |
            (matches['areas'].str.contains(str(area), case=False, na=False))
        ]

    # Sort by interest level (hot first)
    interest_order = {'hot': 0, 'warm': 1, 'cold': 2}
    if 'interest_level' in matches.columns:
        matches['_sort'] = matches['interest_level'].map(interest_order).fillna(1)
        matches = matches.sort_values('_sort').drop(columns=['_sort'])

    return matches


def get_buyer_stats() -> Dict:
    """Get statistics about the buyer list."""
    df = get_buyers_df()

    if len(df) == 0:
        return {
            'total': 0,
            'active': 0,
            'vip': 0,
            'hot': 0,
            'cash_buyers': 0,
            'avg_budget': 0
        }

    return {
        'total': len(df),
        'active': len(df[df['status'] == 'active']) if 'status' in df.columns else len(df),
        'vip': len(df[df['status'] == 'vip']) if 'status' in df.columns else 0,
        'hot': len(df[df['interest_level'] == 'hot']) if 'interest_level' in df.columns else 0,
        'cash_buyers': len(df[df['cash_buyer'] == True]) if 'cash_buyer' in df.columns else 0,
        'avg_budget': df['price_max'].mean() if 'price_max' in df.columns else 0
    }
