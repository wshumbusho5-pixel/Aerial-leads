"""
Lifeline Home Buyers - Direct Mail Manager

Create and manage direct mail campaigns for lead outreach.
Supports multi-touch sequences, tracking, and integration with print services.
"""

import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import json
from typing import List, Dict, Optional
import hashlib

from config.settings import DATA_DIR, PROCESSED_DATA_DIR
from config.logging_config import get_logger


class DirectMailManager:
    """
    Manage direct mail campaigns for lead outreach.

    Features:
    - Create mail campaigns targeting specific lead types
    - Generate print-ready mail lists (CSV)
    - Track mail sent, delivered, returned
    - Multi-touch follow-up sequences
    - Response tracking
    """

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.campaigns_file = DATA_DIR / "mail_campaigns.json"
        self.mail_log_file = DATA_DIR / "mail_log.csv"
        self.responses_file = DATA_DIR / "mail_responses.csv"

        self._init_files()

    def _init_files(self):
        """Initialize data files if they don't exist."""
        # Campaigns JSON
        if not self.campaigns_file.exists():
            with open(self.campaigns_file, 'w') as f:
                json.dump({"campaigns": []}, f)

        # Mail log CSV
        if not self.mail_log_file.exists():
            pd.DataFrame(columns=[
                'mail_id', 'campaign_id', 'lead_id', 'address', 'owner_name',
                'mail_type', 'touch_number', 'sent_date', 'status',
                'returned_date', 'notes'
            ]).to_csv(self.mail_log_file, index=False)

        # Responses CSV
        if not self.responses_file.exists():
            pd.DataFrame(columns=[
                'response_id', 'mail_id', 'campaign_id', 'response_date',
                'response_type', 'phone', 'notes', 'outcome'
            ]).to_csv(self.responses_file, index=False)

    # ========================================
    # CAMPAIGN MANAGEMENT
    # ========================================

    def create_campaign(
        self,
        name: str,
        lead_type: str = None,
        mail_type: str = "postcard",
        touches: int = 3,
        days_between_touches: int = 14,
        description: str = "",
        filters: Dict = None
    ) -> str:
        """
        Create a new direct mail campaign.

        Args:
            name: Campaign name
            lead_type: Filter by lead type (probate, tax_delinquent, etc.)
            mail_type: Type of mail (postcard, letter, yellow_letter)
            touches: Number of mailings in sequence
            days_between_touches: Days between each touch
            description: Campaign description
            filters: Additional filters (min_score, zip_codes, etc.)

        Returns:
            Campaign ID
        """
        campaign_id = f"CAMP-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        campaign = {
            'id': campaign_id,
            'name': name,
            'lead_type': lead_type,
            'mail_type': mail_type,
            'touches': touches,
            'days_between_touches': days_between_touches,
            'description': description,
            'filters': filters or {},
            'created_at': datetime.now().isoformat(),
            'status': 'active',
            'stats': {
                'total_leads': 0,
                'mail_sent': 0,
                'responses': 0,
                'deals_closed': 0
            }
        }

        # Load and update campaigns
        with open(self.campaigns_file, 'r') as f:
            data = json.load(f)

        data['campaigns'].append(campaign)

        with open(self.campaigns_file, 'w') as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Created campaign: {name} ({campaign_id})")
        return campaign_id

    def get_campaigns(self, status: str = None) -> List[Dict]:
        """Get all campaigns, optionally filtered by status."""
        with open(self.campaigns_file, 'r') as f:
            data = json.load(f)

        campaigns = data.get('campaigns', [])

        if status:
            campaigns = [c for c in campaigns if c.get('status') == status]

        return campaigns

    def get_campaign(self, campaign_id: str) -> Optional[Dict]:
        """Get a specific campaign by ID."""
        campaigns = self.get_campaigns()
        for campaign in campaigns:
            if campaign['id'] == campaign_id:
                return campaign
        return None

    def update_campaign_status(self, campaign_id: str, status: str):
        """Update campaign status (active, paused, completed)."""
        with open(self.campaigns_file, 'r') as f:
            data = json.load(f)

        for campaign in data['campaigns']:
            if campaign['id'] == campaign_id:
                campaign['status'] = status
                campaign['updated_at'] = datetime.now().isoformat()
                break

        with open(self.campaigns_file, 'w') as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Updated campaign {campaign_id} to status: {status}")

    # ========================================
    # MAIL LIST GENERATION
    # ========================================

    def generate_mail_list(
        self,
        campaign_id: str,
        touch_number: int = 1,
        limit: int = None
    ) -> pd.DataFrame:
        """
        Generate a mail list for a campaign touch.

        Returns DataFrame with mailing addresses ready for print.
        """
        campaign = self.get_campaign(campaign_id)
        if not campaign:
            self.logger.error(f"Campaign not found: {campaign_id}")
            return pd.DataFrame()

        # Load leads
        leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
        if not leads_file.exists():
            leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

        if not leads_file.exists():
            self.logger.error("No leads file found")
            return pd.DataFrame()

        df = pd.read_csv(leads_file)

        # Apply campaign filters
        if campaign.get('lead_type') and 'lead_type' in df.columns:
            df = df[df['lead_type'] == campaign['lead_type']]

        filters = campaign.get('filters', {})

        if filters.get('min_score') and 'motivation_score' in df.columns:
            df = df[df['motivation_score'] >= filters['min_score']]

        if filters.get('zip_codes') and 'zip' in df.columns:
            df = df[df['zip'].isin(filters['zip_codes'])]

        if filters.get('exclude_mailed'):
            # Get already mailed addresses for this campaign
            mailed = self._get_mailed_addresses(campaign_id, touch_number)
            df = df[~df['address'].isin(mailed)]

        # Limit results
        if limit:
            df = df.head(limit)

        # Format for mailing
        mail_list = []
        for _, row in df.iterrows():
            # Generate unique mail ID
            mail_id = self._generate_mail_id(campaign_id, row.get('address', ''), touch_number)

            mail_item = {
                'mail_id': mail_id,
                'campaign_id': campaign_id,
                'touch_number': touch_number,
                'owner_name': row.get('owner_name', 'Current Resident'),
                'address_line_1': row.get('address', ''),
                'city': row.get('city', 'Columbus'),
                'state': row.get('state', 'OH'),
                'zip': row.get('zip', ''),
                'lead_type': row.get('lead_type', ''),
                'motivation_score': row.get('motivation_score', 0),
                'lead_id': row.get('parcel_id', row.get('id', ''))
            }
            mail_list.append(mail_item)

        result_df = pd.DataFrame(mail_list)

        self.logger.info(f"Generated mail list with {len(result_df)} addresses for campaign {campaign_id}, touch {touch_number}")

        return result_df

    def _generate_mail_id(self, campaign_id: str, address: str, touch: int) -> str:
        """Generate unique mail ID."""
        hash_input = f"{campaign_id}-{address}-{touch}"
        hash_val = hashlib.md5(hash_input.encode()).hexdigest()[:8]
        return f"MAIL-{hash_val}"

    def _get_mailed_addresses(self, campaign_id: str, touch_number: int) -> set:
        """Get addresses already mailed for a campaign touch."""
        df = pd.read_csv(self.mail_log_file)
        mailed = df[
            (df['campaign_id'] == campaign_id) &
            (df['touch_number'] == touch_number)
        ]['address'].tolist()
        return set(mailed)

    def export_mail_list(
        self,
        campaign_id: str,
        touch_number: int = 1,
        format: str = "csv",
        limit: int = None
    ) -> str:
        """
        Export mail list to file for print service.

        Args:
            campaign_id: Campaign ID
            touch_number: Which touch in sequence
            format: Export format (csv, xlsx)
            limit: Max addresses to export

        Returns:
            Path to exported file
        """
        mail_list = self.generate_mail_list(campaign_id, touch_number, limit)

        if mail_list.empty:
            return ""

        campaign = self.get_campaign(campaign_id)
        campaign_name = campaign.get('name', 'campaign').replace(' ', '_').lower()

        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        filename = f"mail_list_{campaign_name}_touch{touch_number}_{timestamp}"

        export_dir = DATA_DIR / "mail_exports"
        export_dir.mkdir(exist_ok=True)

        if format == "xlsx":
            filepath = export_dir / f"{filename}.xlsx"
            mail_list.to_excel(filepath, index=False)
        else:
            filepath = export_dir / f"{filename}.csv"
            mail_list.to_csv(filepath, index=False)

        self.logger.info(f"Exported mail list to {filepath}")
        return str(filepath)

    # ========================================
    # MAIL TRACKING
    # ========================================

    def log_mail_sent(
        self,
        campaign_id: str,
        addresses: List[str],
        touch_number: int = 1,
        mail_type: str = "postcard"
    ) -> int:
        """
        Log mail as sent for tracking.

        Returns number of records logged.
        """
        df = pd.read_csv(self.mail_log_file)

        new_records = []
        for address in addresses:
            mail_id = self._generate_mail_id(campaign_id, address, touch_number)

            record = {
                'mail_id': mail_id,
                'campaign_id': campaign_id,
                'lead_id': '',
                'address': address,
                'owner_name': '',
                'mail_type': mail_type,
                'touch_number': touch_number,
                'sent_date': datetime.now().strftime('%Y-%m-%d'),
                'status': 'sent',
                'returned_date': '',
                'notes': ''
            }
            new_records.append(record)

        df = pd.concat([df, pd.DataFrame(new_records)], ignore_index=True)
        df.to_csv(self.mail_log_file, index=False)

        # Update campaign stats
        self._update_campaign_stats(campaign_id, mail_sent=len(addresses))

        self.logger.info(f"Logged {len(addresses)} mail pieces sent for campaign {campaign_id}")
        return len(new_records)

    def log_mail_returned(self, mail_id: str, reason: str = ""):
        """Log a returned mail piece."""
        df = pd.read_csv(self.mail_log_file)

        idx = df[df['mail_id'] == mail_id].index
        if len(idx) > 0:
            df.at[idx[0], 'status'] = 'returned'
            df.at[idx[0], 'returned_date'] = datetime.now().strftime('%Y-%m-%d')
            df.at[idx[0], 'notes'] = reason
            df.to_csv(self.mail_log_file, index=False)

            self.logger.info(f"Logged mail returned: {mail_id}")

    def log_response(
        self,
        campaign_id: str,
        response_type: str,
        phone: str = "",
        notes: str = "",
        mail_id: str = None
    ) -> str:
        """
        Log a response to a mail piece.

        Args:
            campaign_id: Campaign that generated the response
            response_type: Type of response (call, text, email, web_form)
            phone: Phone number of responder
            notes: Notes about the response
            mail_id: Specific mail piece if known

        Returns:
            Response ID
        """
        response_id = f"RESP-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        df = pd.read_csv(self.responses_file)

        new_record = {
            'response_id': response_id,
            'mail_id': mail_id or '',
            'campaign_id': campaign_id,
            'response_date': datetime.now().isoformat(),
            'response_type': response_type,
            'phone': phone,
            'notes': notes,
            'outcome': 'new'
        }

        df = pd.concat([df, pd.DataFrame([new_record])], ignore_index=True)
        df.to_csv(self.responses_file, index=False)

        # Update campaign stats
        self._update_campaign_stats(campaign_id, responses=1)

        self.logger.info(f"Logged response for campaign {campaign_id}")
        return response_id

    def update_response_outcome(self, response_id: str, outcome: str, notes: str = ""):
        """Update a response outcome (interested, not_interested, deal_closed)."""
        df = pd.read_csv(self.responses_file)

        idx = df[df['response_id'] == response_id].index
        if len(idx) > 0:
            df.at[idx[0], 'outcome'] = outcome
            if notes:
                existing = df.at[idx[0], 'notes'] or ''
                df.at[idx[0], 'notes'] = f"{existing}\n{notes}".strip()
            df.to_csv(self.responses_file, index=False)

            # If deal closed, update campaign stats
            if outcome == 'deal_closed':
                campaign_id = df.at[idx[0], 'campaign_id']
                self._update_campaign_stats(campaign_id, deals_closed=1)

    def _update_campaign_stats(
        self,
        campaign_id: str,
        mail_sent: int = 0,
        responses: int = 0,
        deals_closed: int = 0
    ):
        """Update campaign statistics."""
        with open(self.campaigns_file, 'r') as f:
            data = json.load(f)

        for campaign in data['campaigns']:
            if campaign['id'] == campaign_id:
                campaign['stats']['mail_sent'] += mail_sent
                campaign['stats']['responses'] += responses
                campaign['stats']['deals_closed'] += deals_closed
                break

        with open(self.campaigns_file, 'w') as f:
            json.dump(data, f, indent=2)

    # ========================================
    # ANALYTICS
    # ========================================

    def get_campaign_stats(self, campaign_id: str) -> Dict:
        """Get detailed statistics for a campaign."""
        campaign = self.get_campaign(campaign_id)
        if not campaign:
            return {}

        # Get mail log stats
        mail_df = pd.read_csv(self.mail_log_file)
        campaign_mail = mail_df[mail_df['campaign_id'] == campaign_id]

        # Get response stats
        resp_df = pd.read_csv(self.responses_file)
        campaign_resp = resp_df[resp_df['campaign_id'] == campaign_id]

        stats = {
            'campaign': campaign,
            'mail': {
                'total_sent': len(campaign_mail),
                'by_touch': campaign_mail['touch_number'].value_counts().to_dict() if not campaign_mail.empty else {},
                'returned': len(campaign_mail[campaign_mail['status'] == 'returned']),
                'return_rate': len(campaign_mail[campaign_mail['status'] == 'returned']) / len(campaign_mail) * 100 if len(campaign_mail) > 0 else 0
            },
            'responses': {
                'total': len(campaign_resp),
                'by_type': campaign_resp['response_type'].value_counts().to_dict() if not campaign_resp.empty else {},
                'by_outcome': campaign_resp['outcome'].value_counts().to_dict() if not campaign_resp.empty else {},
                'response_rate': len(campaign_resp) / len(campaign_mail) * 100 if len(campaign_mail) > 0 else 0
            }
        }

        return stats

    def get_mail_log(self, campaign_id: str = None) -> pd.DataFrame:
        """Get mail log, optionally filtered by campaign."""
        df = pd.read_csv(self.mail_log_file)

        if campaign_id:
            df = df[df['campaign_id'] == campaign_id]

        return df.sort_values('sent_date', ascending=False) if not df.empty else df

    def get_responses(self, campaign_id: str = None) -> pd.DataFrame:
        """Get responses, optionally filtered by campaign."""
        df = pd.read_csv(self.responses_file)

        if campaign_id:
            df = df[df['campaign_id'] == campaign_id]

        return df.sort_values('response_date', ascending=False) if not df.empty else df

    def get_due_for_followup(self, campaign_id: str) -> pd.DataFrame:
        """
        Get leads due for next touch in a multi-touch campaign.

        Returns addresses that received previous touch but not current one,
        and enough time has passed.
        """
        campaign = self.get_campaign(campaign_id)
        if not campaign:
            return pd.DataFrame()

        days_between = campaign.get('days_between_touches', 14)
        max_touches = campaign.get('touches', 3)

        mail_df = pd.read_csv(self.mail_log_file)
        campaign_mail = mail_df[mail_df['campaign_id'] == campaign_id]

        if campaign_mail.empty:
            return pd.DataFrame()

        # Find the max touch number sent
        max_touch_sent = campaign_mail['touch_number'].max()

        if max_touch_sent >= max_touches:
            # Campaign complete
            return pd.DataFrame()

        next_touch = max_touch_sent + 1

        # Get addresses that got previous touch
        prev_touch = campaign_mail[campaign_mail['touch_number'] == max_touch_sent]

        # Check if enough time has passed
        cutoff_date = datetime.now() - timedelta(days=days_between)
        prev_touch['sent_date'] = pd.to_datetime(prev_touch['sent_date'])
        due_for_followup = prev_touch[prev_touch['sent_date'] <= cutoff_date]

        # Exclude addresses that already got this touch
        already_sent = campaign_mail[campaign_mail['touch_number'] == next_touch]['address'].tolist()
        due_for_followup = due_for_followup[~due_for_followup['address'].isin(already_sent)]

        return due_for_followup


# Mail piece templates
MAIL_TEMPLATES = {
    'postcard_probate': {
        'name': 'Probate Postcard',
        'subject': 'We Can Help With Your Inherited Property',
        'body': '''Dear {owner_name},

We understand you may have recently inherited a property at {address}.

Managing an inherited property can be overwhelming - especially during a difficult time.

Lifeline Home Buyers specializes in helping families like yours. We offer:
- Fair cash offers (no lowball games)
- Close on YOUR timeline
- No repairs or cleaning needed
- We handle all the paperwork

I started this company because my own family lost our home when no one would help.
Now I make sure other families have options.

Call or text for a no-obligation offer: (614) 555-CASH

Respectfully,
Willy Shumbusho
Lifeline Home Buyers
''',
        'size': '4x6'
    },
    'postcard_tax': {
        'name': 'Tax Delinquent Postcard',
        'subject': "Don't Lose Your Home to Back Taxes",
        'body': '''Dear {owner_name},

I know what it's like to fall behind on property taxes - my family lost our home that way.

If you're receiving tax notices about {address}, please know you have options.

Lifeline Home Buyers can:
- Pay off your tax debt
- Put cash in your pocket
- Close fast (before auction)
- Handle everything discreetly

You don't have to lose your home like my family did.

Let's talk about your options: (614) 555-CASH

I'm here to help,
Willy Shumbusho
Lifeline Home Buyers
''',
        'size': '4x6'
    },
    'yellow_letter': {
        'name': 'Yellow Letter (Handwritten Style)',
        'subject': 'Interested in Your Property',
        'body': '''Hi {owner_name},

I'm interested in buying your house at {address}.

I buy houses for cash, as-is, and can close fast.

If you've thought about selling, give me a call.

{phone}

- Willy
''',
        'size': 'letter'
    }
}


# CLI for testing
if __name__ == '__main__':
    manager = DirectMailManager()

    # Create a test campaign
    campaign_id = manager.create_campaign(
        name="Probate Q1 2025",
        lead_type="probate",
        mail_type="postcard",
        touches=3,
        days_between_touches=14,
        description="First probate mail campaign"
    )

    print(f"Created campaign: {campaign_id}")

    # Generate mail list
    mail_list = manager.generate_mail_list(campaign_id, touch_number=1, limit=10)
    print(f"\nMail list preview ({len(mail_list)} addresses):")
    print(mail_list.head())

    # Export
    export_path = manager.export_mail_list(campaign_id, touch_number=1, limit=10)
    print(f"\nExported to: {export_path}")
