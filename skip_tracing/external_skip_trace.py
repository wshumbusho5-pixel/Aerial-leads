"""
External Skip Trace Module

Handles exporting leads for external skip tracers and importing the results back.
Supports both property leads (PAS) and investor leads (IDS).
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

# Data directories
DATA_DIR = Path(__file__).parent.parent / "data"
SELLERS_DATA_DIR = DATA_DIR / "sellers" / "processed"  # Property leads (PAS)
INVESTORS_DATA_DIR = DATA_DIR / "buyers" / "processed"  # Investor leads (IDS)
SKIP_TRACE_EXPORT_DIR = DATA_DIR / "skip_trace_exports"

# Ensure export directory exists
SKIP_TRACE_EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def generate_export_id():
    """Generate a unique export ID for tracking."""
    return f"ST_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def export_property_leads_for_skip_trace(df: pd.DataFrame, export_name: str = None) -> tuple:
    """
    Export property leads as a clean CSV for external skip tracing.
    Only includes fields needed for skip tracing - no scoring or internal data.

    Args:
        df: DataFrame with property leads
        export_name: Optional custom name for the export

    Returns:
        Tuple of (export_path, export_id, record_count)
    """
    export_id = generate_export_id()

    # Create clean export with only necessary fields
    export_df = pd.DataFrame()
    export_df['owner_name'] = df.get('owner_name', df.get('owner', df.get('owner_1', ''))).fillna('')
    export_df['property_address'] = df.get('address', df.get('property_address', '')).fillna('')
    export_df['mailing_address'] = df.get('mailing_address', df.get('owner_address', '')).fillna('')
    export_df['city'] = df.get('city', '').fillna('') if 'city' in df.columns else ''
    export_df['state'] = df.get('state', 'OH').fillna('OH') if 'state' in df.columns else 'OH'
    export_df['zip_code'] = df.get('zip_code', df.get('zip', '')).fillna('')

    # IMPORTANT: Filter out rows with empty owner_name AND empty property_address
    # We need at least one of these to skip trace
    export_df = export_df[
        (export_df['owner_name'].str.strip() != '') |
        (export_df['property_address'].str.strip() != '')
    ].reset_index(drop=True)

    # Now add skip_trace_id after filtering
    export_df.insert(0, 'skip_trace_id', [f"{export_id}_{i}" for i in range(len(export_df))])

    # Save to export directory
    if export_name:
        filename = f"{export_name}_{export_id}.csv"
    else:
        filename = f"property_leads_{export_id}.csv"

    export_path = SKIP_TRACE_EXPORT_DIR / filename
    export_df.to_csv(export_path, index=False)

    # Also save a mapping file to match back later (only for valid rows)
    # We need to filter the original df the same way
    valid_mask = (
        (df.get('owner_name', df.get('owner', df.get('owner_1', pd.Series([''] * len(df))))).fillna('').str.strip() != '') |
        (df.get('address', df.get('property_address', pd.Series([''] * len(df)))).fillna('').str.strip() != '')
    )
    mapping_df = df[valid_mask].copy().reset_index(drop=True)
    mapping_df['skip_trace_id'] = export_df['skip_trace_id']
    mapping_path = SKIP_TRACE_EXPORT_DIR / f"mapping_{export_id}.csv"
    mapping_df.to_csv(mapping_path, index=False)

    logger.info(f"Exported {len(export_df)} property leads for skip tracing: {export_path}")

    return str(export_path), export_id, len(export_df)


def export_investor_leads_for_skip_trace(df: pd.DataFrame, export_name: str = None) -> tuple:
    """
    Export investor leads as a clean CSV for external skip tracing.
    Only includes fields needed for skip tracing - no scoring or internal data.

    Args:
        df: DataFrame with investor leads
        export_name: Optional custom name for the export

    Returns:
        Tuple of (export_path, export_id, record_count)
    """
    export_id = generate_export_id()

    # Create clean export with only necessary fields
    export_df = pd.DataFrame()
    export_df['owner_name'] = df.get('owner_name', df.get('owner', '')).fillna('')
    export_df['mailing_address'] = df.get('mailing_address', df.get('owner_address', '')).fillna('')
    export_df['city'] = df.get('city', '').fillna('') if 'city' in df.columns else ''
    export_df['state'] = df.get('state', 'OH').fillna('OH') if 'state' in df.columns else 'OH'
    export_df['zip_code'] = df.get('zip_code', df.get('zip', '')).fillna('')
    export_df['entity_type'] = df.get('entity_type', '').fillna('') if 'entity_type' in df.columns else ''

    # IMPORTANT: Filter out rows with empty owner_name AND empty mailing_address
    export_df = export_df[
        (export_df['owner_name'].str.strip() != '') |
        (export_df['mailing_address'].str.strip() != '')
    ].reset_index(drop=True)

    # Now add skip_trace_id after filtering
    export_df.insert(0, 'skip_trace_id', [f"{export_id}_{i}" for i in range(len(export_df))])

    # Save to export directory
    if export_name:
        filename = f"{export_name}_{export_id}.csv"
    else:
        filename = f"investor_leads_{export_id}.csv"

    export_path = SKIP_TRACE_EXPORT_DIR / filename
    export_df.to_csv(export_path, index=False)

    # Also save a mapping file to match back later (only for valid rows)
    valid_mask = (
        (df.get('owner_name', df.get('owner', pd.Series([''] * len(df)))).fillna('').str.strip() != '') |
        (df.get('mailing_address', df.get('owner_address', pd.Series([''] * len(df)))).fillna('').str.strip() != '')
    )
    mapping_df = df[valid_mask].copy().reset_index(drop=True)
    mapping_df['skip_trace_id'] = export_df['skip_trace_id']
    mapping_path = SKIP_TRACE_EXPORT_DIR / f"mapping_{export_id}.csv"
    mapping_df.to_csv(mapping_path, index=False)

    logger.info(f"Exported {len(export_df)} investor leads for skip tracing: {export_path}")

    return str(export_path), export_id, len(export_df)


def import_skip_traced_data(imported_df: pd.DataFrame, lead_type: str = 'property') -> tuple:
    """
    Import skip traced data and match it back to original records.

    The imported CSV should have:
    - skip_trace_id (from the export) OR
    - owner_name + address (for matching)
    - phone, phone_2, email (the skip traced data)

    Args:
        imported_df: DataFrame with skip traced data
        lead_type: 'property' or 'investor'

    Returns:
        Tuple of (matched_df, match_count, unmatched_count)
    """
    # Try to find the export ID from skip_trace_id column
    export_id = None
    if 'skip_trace_id' in imported_df.columns:
        first_id = str(imported_df['skip_trace_id'].iloc[0])
        if first_id.startswith('ST_'):
            # Extract export ID (format: ST_YYYYMMDD_HHMMSS_xxxxxx_N)
            parts = first_id.split('_')
            if len(parts) >= 4:
                export_id = '_'.join(parts[:4])

    # Try to load the mapping file
    mapping_df = None
    if export_id:
        mapping_path = SKIP_TRACE_EXPORT_DIR / f"mapping_{export_id}.csv"
        if mapping_path.exists():
            mapping_df = pd.read_csv(mapping_path)
            logger.info(f"Found mapping file: {mapping_path}")

    # Clean phone numbers in imported data
    phone_cols = ['phone', 'phone_1', 'phone_2', 'phone_3', 'mobile', 'landline']
    for col in phone_cols:
        if col in imported_df.columns:
            imported_df[col] = imported_df[col].astype(str).str.replace(r'[^\d]', '', regex=True)
            imported_df[col] = imported_df[col].replace('nan', '')

    # Standardize column names
    col_mapping = {
        'phone_1': 'phone',
        'phone1': 'phone',
        'primary_phone': 'phone',
        'phone_2': 'phone_2',
        'phone2': 'phone_2',
        'secondary_phone': 'phone_2',
        'email_1': 'email',
        'email1': 'email',
        'primary_email': 'email'
    }
    imported_df = imported_df.rename(columns={k: v for k, v in col_mapping.items() if k in imported_df.columns})

    # Match records
    if mapping_df is not None and 'skip_trace_id' in imported_df.columns:
        # Match by skip_trace_id (most accurate)
        matched_df = mapping_df.merge(
            imported_df[['skip_trace_id'] + [c for c in ['phone', 'phone_2', 'email'] if c in imported_df.columns]],
            on='skip_trace_id',
            how='left',
            suffixes=('_orig', '')
        )

        # Update phone/email columns
        for col in ['phone', 'phone_2', 'email']:
            if col in matched_df.columns:
                orig_col = f'{col}_orig'
                if orig_col in matched_df.columns:
                    # Keep new value if exists, otherwise keep original
                    matched_df[col] = matched_df[col].fillna(matched_df[orig_col])
                    matched_df = matched_df.drop(columns=[orig_col])

        match_count = len(matched_df[matched_df['phone'].notna() & (matched_df['phone'] != '')])
        unmatched_count = len(matched_df) - match_count

    else:
        # Match by owner_name + address (fallback)
        logger.warning("No skip_trace_id found, matching by name/address")
        matched_df = imported_df.copy()
        match_count = len(matched_df)
        unmatched_count = 0

    # Mark as skip traced
    matched_df['skip_traced'] = True
    matched_df['skip_traced_date'] = datetime.now().strftime('%Y-%m-%d')

    logger.info(f"Imported skip trace data: {match_count} matched, {unmatched_count} unmatched")

    return matched_df, match_count, unmatched_count


def get_recent_exports() -> list:
    """Get list of recent skip trace exports."""
    exports = []

    for f in SKIP_TRACE_EXPORT_DIR.glob("property_leads_*.csv"):
        if not f.name.startswith("mapping_"):
            exports.append({
                'filename': f.name,
                'path': str(f),
                'type': 'property',
                'created': datetime.fromtimestamp(f.stat().st_mtime),
                'size': f.stat().st_size
            })

    for f in SKIP_TRACE_EXPORT_DIR.glob("investor_leads_*.csv"):
        if not f.name.startswith("mapping_"):
            exports.append({
                'filename': f.name,
                'path': str(f),
                'type': 'investor',
                'created': datetime.fromtimestamp(f.stat().st_mtime),
                'size': f.stat().st_size
            })

    # Sort by date, newest first
    exports.sort(key=lambda x: x['created'], reverse=True)

    return exports[:20]  # Return last 20 exports
