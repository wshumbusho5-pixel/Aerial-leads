"""
Aerial Leads - Deal Pipeline / CRM

Track deals from lead to close:
Lead → Qualified → Offer Made → Under Contract → Closed

This is where you make money - track every deal to closing!
"""

import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import json
import uuid

from config.settings import DATA_DIR, PROCESSED_DATA_DIR
from config.logging_config import get_logger

logger = get_logger("DealPipeline")

# Deal stages in order
DEAL_STAGES = [
    "lead",           # Initial contact, showing interest
    "qualified",      # Verified motivation, confirmed details
    "offer_made",     # Sent offer to seller
    "under_contract", # Offer accepted, signed contract
    "closed",         # Deal completed, got paid!
    "dead"            # Deal fell through (lost)
]

STAGE_DISPLAY_NAMES = {
    "lead": "🎯 Lead",
    "qualified": "✅ Qualified",
    "offer_made": "📝 Offer Made",
    "under_contract": "📋 Under Contract",
    "closed": "💰 Closed",
    "dead": "❌ Dead"
}

STAGE_COLORS = {
    "lead": "#6c757d",
    "qualified": "#17a2b8",
    "offer_made": "#ffc107",
    "under_contract": "#fd7e14",
    "closed": "#28a745",
    "dead": "#dc3545"
}

# Data file
DEALS_FILE = DATA_DIR / "deals_pipeline.csv"
DEAL_ACTIVITY_FILE = DATA_DIR / "deal_activity.csv"


class DealPipeline:
    """
    Manage deals through the pipeline from lead to close.
    """

    def __init__(self):
        self._init_files()

    def _init_files(self):
        """Initialize data files if they don't exist."""
        if not DEALS_FILE.exists():
            df = pd.DataFrame(columns=[
                'deal_id', 'created_at', 'updated_at',
                # Property info
                'address', 'city', 'state', 'zip_code',
                # Seller info
                'seller_name', 'seller_phone', 'seller_email',
                # Lead source
                'lead_source', 'lead_type',  # probate, tax, code_violation, etc.
                # Pipeline
                'stage', 'stage_changed_at',
                # Financials
                'asking_price', 'offer_amount', 'contract_price',
                'arv', 'repair_estimate', 'assignment_fee',
                # Wholesale specific
                'buyer_name', 'buyer_phone', 'buyer_company',
                # Dates
                'offer_date', 'contract_date', 'closing_date',
                # Outcome
                'actual_profit', 'deal_type',  # wholesale, flip, rental
                # Notes
                'notes', 'assigned_to'
            ])
            df.to_csv(DEALS_FILE, index=False)

        if not DEAL_ACTIVITY_FILE.exists():
            df = pd.DataFrame(columns=[
                'activity_id', 'deal_id', 'timestamp',
                'activity_type', 'description', 'user'
            ])
            df.to_csv(DEAL_ACTIVITY_FILE, index=False)

    def create_deal(
        self,
        address: str,
        seller_name: str = "",
        seller_phone: str = "",
        lead_source: str = "",
        lead_type: str = "",
        city: str = "",
        state: str = "OH",
        zip_code: str = "",
        notes: str = "",
        assigned_to: str = ""
    ) -> str:
        """
        Create a new deal in the pipeline.

        Returns:
            deal_id: Unique identifier for the deal
        """
        deal_id = f"DEAL-{datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:4].upper()}"

        deal = {
            'deal_id': deal_id,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'address': address,
            'city': city,
            'state': state,
            'zip_code': zip_code,
            'seller_name': seller_name,
            'seller_phone': seller_phone,
            'seller_email': "",
            'lead_source': lead_source,
            'lead_type': lead_type,
            'stage': 'lead',
            'stage_changed_at': datetime.now().isoformat(),
            'asking_price': 0,
            'offer_amount': 0,
            'contract_price': 0,
            'arv': 0,
            'repair_estimate': 0,
            'assignment_fee': 0,
            'buyer_name': "",
            'buyer_phone': "",
            'buyer_company': "",
            'offer_date': "",
            'contract_date': "",
            'closing_date': "",
            'actual_profit': 0,
            'deal_type': "wholesale",
            'notes': notes,
            'assigned_to': assigned_to
        }

        df = pd.read_csv(DEALS_FILE)
        df = pd.concat([df, pd.DataFrame([deal])], ignore_index=True)
        df.to_csv(DEALS_FILE, index=False)

        # Log activity
        self._log_activity(deal_id, "created", f"Deal created for {address}", assigned_to)

        logger.info(f"Created deal {deal_id} for {address}")
        return deal_id

    def create_deal_from_lead(self, lead_data: Dict, assigned_to: str = "") -> str:
        """
        Create a deal from an existing lead record.

        Args:
            lead_data: Dictionary with lead information
            assigned_to: Who's working this deal

        Returns:
            deal_id
        """
        return self.create_deal(
            address=lead_data.get('address', lead_data.get('property_address', '')),
            seller_name=lead_data.get('owner_name', lead_data.get('owner', '')),
            seller_phone=lead_data.get('phone', lead_data.get('phone_1', '')),
            lead_source=lead_data.get('source', lead_data.get('data_source', '')),
            lead_type=lead_data.get('lead_type', ''),
            city=lead_data.get('city', ''),
            state=lead_data.get('state', 'OH'),
            zip_code=str(lead_data.get('zip', lead_data.get('zip_code', ''))),
            notes=f"Imported from leads. Score: {lead_data.get('motivation_score', 'N/A')}",
            assigned_to=assigned_to
        )

    def get_deal(self, deal_id: str) -> Optional[Dict]:
        """Get a single deal by ID."""
        df = pd.read_csv(DEALS_FILE)
        deal = df[df['deal_id'] == deal_id]
        if deal.empty:
            return None
        return deal.iloc[0].to_dict()

    def get_all_deals(self, stage: str = None, assigned_to: str = None) -> pd.DataFrame:
        """Get all deals, optionally filtered."""
        df = pd.read_csv(DEALS_FILE)

        if stage:
            df = df[df['stage'] == stage]

        if assigned_to:
            df = df[df['assigned_to'] == assigned_to]

        return df

    def get_deals_by_stage(self) -> Dict[str, pd.DataFrame]:
        """Get deals grouped by stage."""
        df = pd.read_csv(DEALS_FILE)
        result = {}
        for stage in DEAL_STAGES:
            result[stage] = df[df['stage'] == stage]
        return result

    def update_deal(self, deal_id: str, updates: Dict, user: str = "") -> bool:
        """
        Update a deal with new information.

        Args:
            deal_id: The deal to update
            updates: Dictionary of fields to update
            user: Who made the update

        Returns:
            True if successful
        """
        df = pd.read_csv(DEALS_FILE)
        idx = df[df['deal_id'] == deal_id].index

        if len(idx) == 0:
            logger.warning(f"Deal not found: {deal_id}")
            return False

        idx = idx[0]
        old_stage = df.at[idx, 'stage']

        for key, value in updates.items():
            if key in df.columns:
                df.at[idx, key] = value

        df.at[idx, 'updated_at'] = datetime.now().isoformat()

        # Check if stage changed
        if 'stage' in updates and updates['stage'] != old_stage:
            df.at[idx, 'stage_changed_at'] = datetime.now().isoformat()
            self._log_activity(
                deal_id, "stage_changed",
                f"Stage changed: {STAGE_DISPLAY_NAMES.get(old_stage, old_stage)} → {STAGE_DISPLAY_NAMES.get(updates['stage'], updates['stage'])}",
                user
            )

        df.to_csv(DEALS_FILE, index=False)
        logger.info(f"Updated deal {deal_id}")
        return True

    def move_to_stage(self, deal_id: str, new_stage: str, user: str = "", notes: str = "") -> bool:
        """
        Move a deal to a new stage.

        Args:
            deal_id: The deal to move
            new_stage: Target stage
            user: Who moved it
            notes: Optional notes about the move

        Returns:
            True if successful
        """
        if new_stage not in DEAL_STAGES:
            logger.error(f"Invalid stage: {new_stage}")
            return False

        updates = {'stage': new_stage}

        # Auto-set dates based on stage
        if new_stage == 'offer_made':
            updates['offer_date'] = datetime.now().strftime('%Y-%m-%d')
        elif new_stage == 'under_contract':
            updates['contract_date'] = datetime.now().strftime('%Y-%m-%d')
        elif new_stage == 'closed':
            updates['closing_date'] = datetime.now().strftime('%Y-%m-%d')

        if notes:
            deal = self.get_deal(deal_id)
            existing_notes = deal.get('notes', '') if deal else ''
            updates['notes'] = f"{existing_notes}\n[{datetime.now().strftime('%Y-%m-%d')}] {notes}".strip()

        return self.update_deal(deal_id, updates, user)

    def _log_activity(self, deal_id: str, activity_type: str, description: str, user: str = ""):
        """Log an activity for a deal."""
        activity = {
            'activity_id': f"ACT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:4]}",
            'deal_id': deal_id,
            'timestamp': datetime.now().isoformat(),
            'activity_type': activity_type,
            'description': description,
            'user': user
        }

        df = pd.read_csv(DEAL_ACTIVITY_FILE)
        df = pd.concat([df, pd.DataFrame([activity])], ignore_index=True)
        df.to_csv(DEAL_ACTIVITY_FILE, index=False)

    def get_deal_activity(self, deal_id: str) -> pd.DataFrame:
        """Get activity history for a deal."""
        df = pd.read_csv(DEAL_ACTIVITY_FILE)
        return df[df['deal_id'] == deal_id].sort_values('timestamp', ascending=False)

    def get_pipeline_stats(self) -> Dict:
        """Get statistics about the pipeline."""
        df = pd.read_csv(DEALS_FILE)

        if df.empty:
            return {
                'total_deals': 0,
                'by_stage': {stage: 0 for stage in DEAL_STAGES},
                'total_potential_profit': 0,
                'total_closed_profit': 0,
                'avg_deal_value': 0,
                'conversion_rate': 0
            }

        by_stage = df['stage'].value_counts().to_dict()
        for stage in DEAL_STAGES:
            if stage not in by_stage:
                by_stage[stage] = 0

        # Calculate profits
        closed_deals = df[df['stage'] == 'closed']
        total_closed_profit = closed_deals['actual_profit'].sum() if not closed_deals.empty else 0

        # Potential profit from active deals
        active_deals = df[~df['stage'].isin(['closed', 'dead'])]
        total_potential_profit = active_deals['assignment_fee'].sum() if not active_deals.empty else 0

        # Conversion rate (closed / total non-dead)
        total_non_dead = len(df[df['stage'] != 'dead'])
        closed_count = len(closed_deals)
        conversion_rate = (closed_count / total_non_dead * 100) if total_non_dead > 0 else 0

        return {
            'total_deals': len(df),
            'by_stage': by_stage,
            'total_potential_profit': total_potential_profit,
            'total_closed_profit': total_closed_profit,
            'avg_deal_value': total_closed_profit / closed_count if closed_count > 0 else 0,
            'conversion_rate': conversion_rate,
            'active_deals': len(active_deals),
            'closed_deals': closed_count,
            'dead_deals': by_stage.get('dead', 0)
        }

    def get_monthly_revenue(self, year: int = None) -> pd.DataFrame:
        """Get revenue by month for closed deals."""
        df = pd.read_csv(DEALS_FILE)
        closed = df[df['stage'] == 'closed'].copy()

        if closed.empty:
            return pd.DataFrame(columns=['month', 'deals', 'revenue'])

        closed['closing_date'] = pd.to_datetime(closed['closing_date'], errors='coerce')
        closed = closed.dropna(subset=['closing_date'])

        if year:
            closed = closed[closed['closing_date'].dt.year == year]

        monthly = closed.groupby(closed['closing_date'].dt.to_period('M')).agg({
            'deal_id': 'count',
            'actual_profit': 'sum'
        }).reset_index()

        monthly.columns = ['month', 'deals', 'revenue']
        monthly['month'] = monthly['month'].astype(str)

        return monthly


# Export constants
__all__ = [
    'DealPipeline',
    'DEAL_STAGES',
    'STAGE_DISPLAY_NAMES',
    'STAGE_COLORS'
]
