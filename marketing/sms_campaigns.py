"""
Lifeline Home Buyers - SMS/Text Campaigns

Send text messages to leads for marketing outreach.
Note: Uses placeholder for actual SMS provider (Twilio, etc.)

Features:
- SMS campaign management
- Message templates
- Delivery tracking
- Opt-out handling
- Response tracking
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import uuid
import re

from config.settings import DATA_DIR
from config.logging_config import get_logger

logger = get_logger("SMSCampaigns")

# SMS campaign status
CAMPAIGN_STATUS = [
    "draft",       # Being created
    "scheduled",   # Ready to send
    "sending",     # Currently sending
    "paused",      # Paused mid-send
    "completed",   # All sent
    "cancelled"    # Cancelled
]

MESSAGE_STATUS = [
    "pending",     # Not yet sent
    "sent",        # Sent to provider
    "delivered",   # Confirmed delivered
    "failed",      # Failed to deliver
    "opted_out"    # Recipient opted out
]

# Data files
SMS_CAMPAIGNS_FILE = DATA_DIR / "sms_campaigns.csv"
SMS_MESSAGES_FILE = DATA_DIR / "sms_messages.csv"
SMS_OPTOUTS_FILE = DATA_DIR / "sms_optouts.csv"
SMS_TEMPLATES_FILE = DATA_DIR / "sms_templates.csv"

# Default SMS templates
DEFAULT_SMS_TEMPLATES = {
    "initial_contact": {
        "name": "Initial Contact",
        "message": "Hi {owner_name}, this is {sender_name} with Lifeline Home Buyers. We buy houses for cash in {city}. Interested in a no-obligation offer for {address}? Reply YES or call {phone}",
        "category": "outreach"
    },
    "follow_up_1": {
        "name": "Follow-up #1",
        "message": "Hi {owner_name}, just following up on your property at {address}. We can close in as little as 7 days. Still interested? Reply or call {phone}",
        "category": "follow_up"
    },
    "follow_up_2": {
        "name": "Follow-up #2",
        "message": "{owner_name}, we're still interested in buying {address}. Cash offer, no repairs needed, you pick the closing date. Text CALL if you'd like us to reach out.",
        "category": "follow_up"
    },
    "probate_outreach": {
        "name": "Probate Outreach",
        "message": "Hi {owner_name}, I understand you may have inherited property at {address}. We buy estates as-is for cash. Can help with the process. Reply for info or call {phone}",
        "category": "outreach"
    },
    "motivated_seller": {
        "name": "Motivated Seller",
        "message": "Hi {owner_name}, we have cash buyers looking for properties like {address}. Quick close, no fees. Would you consider a fair cash offer? Reply YES",
        "category": "outreach"
    },
    "appointment_reminder": {
        "name": "Appointment Reminder",
        "message": "Reminder: Your appointment with Lifeline Home Buyers is tomorrow at {time} for {address}. See you then! Reply to confirm or reschedule.",
        "category": "reminder"
    }
}


class SMSCampaigns:
    """
    Manage SMS marketing campaigns.
    """

    def __init__(self):
        self._init_files()

    def _init_files(self):
        """Initialize data files."""
        if not SMS_CAMPAIGNS_FILE.exists():
            df = pd.DataFrame(columns=[
                'campaign_id', 'created_at', 'updated_at',
                'name', 'description', 'template_id',
                'status', 'scheduled_at',
                'total_recipients', 'sent_count', 'delivered_count',
                'failed_count', 'response_count', 'optout_count',
                'created_by', 'sender_phone'
            ])
            df.to_csv(SMS_CAMPAIGNS_FILE, index=False)

        if not SMS_MESSAGES_FILE.exists():
            df = pd.DataFrame(columns=[
                'message_id', 'campaign_id', 'created_at',
                'recipient_phone', 'recipient_name', 'address',
                'message_text', 'status', 'sent_at',
                'delivered_at', 'response', 'response_at',
                'error_message'
            ])
            df.to_csv(SMS_MESSAGES_FILE, index=False)

        if not SMS_OPTOUTS_FILE.exists():
            df = pd.DataFrame(columns=[
                'phone', 'opted_out_at', 'campaign_id', 'reason'
            ])
            df.to_csv(SMS_OPTOUTS_FILE, index=False)

        if not SMS_TEMPLATES_FILE.exists():
            # Create default templates
            templates = []
            for template_id, template in DEFAULT_SMS_TEMPLATES.items():
                templates.append({
                    'template_id': template_id,
                    'name': template['name'],
                    'message': template['message'],
                    'category': template['category'],
                    'created_at': datetime.now().isoformat(),
                    'is_default': True
                })
            df = pd.DataFrame(templates)
            df.to_csv(SMS_TEMPLATES_FILE, index=False)

    def get_templates(self) -> pd.DataFrame:
        """Get all SMS templates."""
        return pd.read_csv(SMS_TEMPLATES_FILE)

    def create_template(self, name: str, message: str, category: str = "custom") -> str:
        """Create a new SMS template."""
        template_id = f"tpl_{datetime.now().strftime('%Y%m%d%H%M%S')}_{str(uuid.uuid4())[:4]}"

        template = {
            'template_id': template_id,
            'name': name,
            'message': message,
            'category': category,
            'created_at': datetime.now().isoformat(),
            'is_default': False
        }

        df = pd.read_csv(SMS_TEMPLATES_FILE)
        df = pd.concat([df, pd.DataFrame([template])], ignore_index=True)
        df.to_csv(SMS_TEMPLATES_FILE, index=False)

        logger.info(f"Created SMS template: {template_id}")
        return template_id

    def get_template(self, template_id: str) -> Optional[Dict]:
        """Get a specific template."""
        df = pd.read_csv(SMS_TEMPLATES_FILE)
        tpl = df[df['template_id'] == template_id]
        if tpl.empty:
            return None
        return tpl.iloc[0].to_dict()

    def personalize_message(self, template_message: str, lead_data: Dict, sender_info: Dict = None) -> str:
        """
        Personalize a template message with lead data.

        Available placeholders:
        {owner_name}, {address}, {city}, {state}, {zip_code}
        {sender_name}, {phone}, {company}
        """
        sender_info = sender_info or {}

        replacements = {
            '{owner_name}': lead_data.get('owner_name', lead_data.get('owner', 'there')),
            '{address}': lead_data.get('address', lead_data.get('property_address', '')),
            '{city}': lead_data.get('city', 'your area'),
            '{state}': lead_data.get('state', 'OH'),
            '{zip_code}': lead_data.get('zip_code', lead_data.get('zip', '')),
            '{sender_name}': sender_info.get('name', 'Our team'),
            '{phone}': sender_info.get('phone', ''),
            '{company}': sender_info.get('company', 'Lifeline Home Buyers'),
            '{time}': lead_data.get('time', ''),
        }

        message = template_message
        for placeholder, value in replacements.items():
            message = message.replace(placeholder, str(value))

        return message

    def create_campaign(
        self,
        name: str,
        template_id: str,
        recipients: List[Dict],
        sender_phone: str = "",
        description: str = "",
        schedule_at: str = None,
        created_by: str = ""
    ) -> str:
        """
        Create a new SMS campaign.

        Args:
            name: Campaign name
            template_id: Template to use
            recipients: List of dicts with phone, name, address, etc.
            sender_phone: Phone number to send from
            description: Campaign description
            schedule_at: When to send (ISO format) or None for draft
            created_by: Who created

        Returns:
            campaign_id
        """
        campaign_id = f"SMS-{datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:4].upper()}"

        # Filter out opted-out numbers
        optouts = self.get_optouts()
        opted_out_phones = set(optouts['phone'].str.replace(r'\D', '', regex=True).tolist())

        valid_recipients = []
        for r in recipients:
            phone = re.sub(r'\D', '', str(r.get('phone', r.get('phone_1', ''))))
            if phone and len(phone) >= 10 and phone not in opted_out_phones:
                valid_recipients.append(r)

        campaign = {
            'campaign_id': campaign_id,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'name': name,
            'description': description,
            'template_id': template_id,
            'status': 'scheduled' if schedule_at else 'draft',
            'scheduled_at': schedule_at or '',
            'total_recipients': len(valid_recipients),
            'sent_count': 0,
            'delivered_count': 0,
            'failed_count': 0,
            'response_count': 0,
            'optout_count': len(recipients) - len(valid_recipients),
            'created_by': created_by,
            'sender_phone': sender_phone
        }

        # Save campaign
        df = pd.read_csv(SMS_CAMPAIGNS_FILE)
        df = pd.concat([df, pd.DataFrame([campaign])], ignore_index=True)
        df.to_csv(SMS_CAMPAIGNS_FILE, index=False)

        # Create message records
        template = self.get_template(template_id)
        if template:
            messages = []
            for r in valid_recipients:
                phone = re.sub(r'\D', '', str(r.get('phone', r.get('phone_1', ''))))
                personalized = self.personalize_message(template['message'], r)

                messages.append({
                    'message_id': f"MSG-{str(uuid.uuid4())[:8].upper()}",
                    'campaign_id': campaign_id,
                    'created_at': datetime.now().isoformat(),
                    'recipient_phone': phone,
                    'recipient_name': r.get('owner_name', r.get('owner', '')),
                    'address': r.get('address', r.get('property_address', '')),
                    'message_text': personalized,
                    'status': 'pending',
                    'sent_at': '',
                    'delivered_at': '',
                    'response': '',
                    'response_at': '',
                    'error_message': ''
                })

            if messages:
                msg_df = pd.read_csv(SMS_MESSAGES_FILE)
                msg_df = pd.concat([msg_df, pd.DataFrame(messages)], ignore_index=True)
                msg_df.to_csv(SMS_MESSAGES_FILE, index=False)

        logger.info(f"Created SMS campaign {campaign_id} with {len(valid_recipients)} recipients")
        return campaign_id

    def get_campaign(self, campaign_id: str) -> Optional[Dict]:
        """Get a single campaign."""
        df = pd.read_csv(SMS_CAMPAIGNS_FILE)
        campaign = df[df['campaign_id'] == campaign_id]
        if campaign.empty:
            return None
        return campaign.iloc[0].to_dict()

    def get_all_campaigns(self, status: str = None) -> pd.DataFrame:
        """Get all campaigns."""
        df = pd.read_csv(SMS_CAMPAIGNS_FILE)
        if status:
            df = df[df['status'] == status]
        return df.sort_values('created_at', ascending=False)

    def get_campaign_messages(self, campaign_id: str, status: str = None) -> pd.DataFrame:
        """Get messages for a campaign."""
        df = pd.read_csv(SMS_MESSAGES_FILE)
        df = df[df['campaign_id'] == campaign_id]
        if status:
            df = df[df['status'] == status]
        return df

    def update_campaign_status(self, campaign_id: str, status: str) -> bool:
        """Update campaign status."""
        if status not in CAMPAIGN_STATUS:
            return False

        df = pd.read_csv(SMS_CAMPAIGNS_FILE)
        idx = df[df['campaign_id'] == campaign_id].index

        if len(idx) == 0:
            return False

        df.at[idx[0], 'status'] = status
        df.at[idx[0], 'updated_at'] = datetime.now().isoformat()
        df.to_csv(SMS_CAMPAIGNS_FILE, index=False)

        logger.info(f"Updated campaign {campaign_id} status to {status}")
        return True

    def send_campaign(self, campaign_id: str) -> Dict:
        """
        Send a campaign (mark messages as sent).

        In production, this would integrate with Twilio/similar.
        For now, it simulates sending by marking messages as sent.

        Returns:
            Dict with sent_count, failed_count
        """
        campaign = self.get_campaign(campaign_id)
        if not campaign:
            return {'error': 'Campaign not found'}

        self.update_campaign_status(campaign_id, 'sending')

        # Get pending messages
        messages = self.get_campaign_messages(campaign_id, status='pending')

        sent_count = 0
        failed_count = 0

        msg_df = pd.read_csv(SMS_MESSAGES_FILE)

        for _, msg in messages.iterrows():
            idx = msg_df[msg_df['message_id'] == msg['message_id']].index
            if len(idx) == 0:
                continue

            # Simulate sending (in production: call Twilio API)
            # For demo purposes, mark 95% as sent, 5% as failed
            import random
            if random.random() < 0.95:
                msg_df.at[idx[0], 'status'] = 'sent'
                msg_df.at[idx[0], 'sent_at'] = datetime.now().isoformat()
                sent_count += 1
            else:
                msg_df.at[idx[0], 'status'] = 'failed'
                msg_df.at[idx[0], 'error_message'] = 'Simulated failure'
                failed_count += 1

        msg_df.to_csv(SMS_MESSAGES_FILE, index=False)

        # Update campaign counts
        df = pd.read_csv(SMS_CAMPAIGNS_FILE)
        idx = df[df['campaign_id'] == campaign_id].index
        if len(idx) > 0:
            df.at[idx[0], 'sent_count'] = int(df.at[idx[0], 'sent_count']) + sent_count
            df.at[idx[0], 'failed_count'] = int(df.at[idx[0], 'failed_count']) + failed_count
            df.at[idx[0], 'status'] = 'completed'
            df.at[idx[0], 'updated_at'] = datetime.now().isoformat()
            df.to_csv(SMS_CAMPAIGNS_FILE, index=False)

        logger.info(f"Campaign {campaign_id} sent: {sent_count} sent, {failed_count} failed")
        return {'sent_count': sent_count, 'failed_count': failed_count}

    def record_response(self, phone: str, response: str, campaign_id: str = None) -> bool:
        """Record a response from a recipient."""
        phone = re.sub(r'\D', '', phone)

        df = pd.read_csv(SMS_MESSAGES_FILE)

        # Find most recent message to this phone
        if campaign_id:
            matches = df[(df['recipient_phone'] == phone) & (df['campaign_id'] == campaign_id)]
        else:
            matches = df[df['recipient_phone'] == phone]

        if matches.empty:
            return False

        # Get most recent
        idx = matches.sort_values('sent_at', ascending=False).index[0]

        df.at[idx, 'response'] = response
        df.at[idx, 'response_at'] = datetime.now().isoformat()
        df.to_csv(SMS_MESSAGES_FILE, index=False)

        # Update campaign response count
        camp_id = df.at[idx, 'campaign_id']
        camp_df = pd.read_csv(SMS_CAMPAIGNS_FILE)
        camp_idx = camp_df[camp_df['campaign_id'] == camp_id].index
        if len(camp_idx) > 0:
            camp_df.at[camp_idx[0], 'response_count'] = int(camp_df.at[camp_idx[0], 'response_count']) + 1
            camp_df.to_csv(SMS_CAMPAIGNS_FILE, index=False)

        # Check for opt-out keywords
        optout_keywords = ['stop', 'unsubscribe', 'opt out', 'optout', 'remove', 'quit']
        if any(kw in response.lower() for kw in optout_keywords):
            self.add_optout(phone, camp_id, reason=f"Replied: {response}")

        logger.info(f"Recorded response from {phone}")
        return True

    def add_optout(self, phone: str, campaign_id: str = "", reason: str = "") -> bool:
        """Add a phone number to opt-out list."""
        phone = re.sub(r'\D', '', phone)

        df = pd.read_csv(SMS_OPTOUTS_FILE)

        # Check if already opted out
        if phone in df['phone'].values:
            return False

        optout = {
            'phone': phone,
            'opted_out_at': datetime.now().isoformat(),
            'campaign_id': campaign_id,
            'reason': reason
        }

        df = pd.concat([df, pd.DataFrame([optout])], ignore_index=True)
        df.to_csv(SMS_OPTOUTS_FILE, index=False)

        logger.info(f"Added {phone} to opt-out list")
        return True

    def get_optouts(self) -> pd.DataFrame:
        """Get all opt-out numbers."""
        return pd.read_csv(SMS_OPTOUTS_FILE)

    def is_opted_out(self, phone: str) -> bool:
        """Check if a phone number is opted out."""
        phone = re.sub(r'\D', '', phone)
        df = pd.read_csv(SMS_OPTOUTS_FILE)
        return phone in df['phone'].values

    def get_stats(self) -> Dict:
        """Get overall SMS statistics."""
        campaigns = pd.read_csv(SMS_CAMPAIGNS_FILE)
        messages = pd.read_csv(SMS_MESSAGES_FILE)
        optouts = pd.read_csv(SMS_OPTOUTS_FILE)

        if campaigns.empty:
            return {
                'total_campaigns': 0,
                'active_campaigns': 0,
                'total_messages_sent': 0,
                'total_delivered': 0,
                'total_responses': 0,
                'total_optouts': 0,
                'delivery_rate': 0,
                'response_rate': 0
            }

        total_sent = campaigns['sent_count'].sum()
        total_delivered = campaigns['delivered_count'].sum()
        total_responses = campaigns['response_count'].sum()

        return {
            'total_campaigns': len(campaigns),
            'active_campaigns': len(campaigns[campaigns['status'].isin(['scheduled', 'sending'])]),
            'total_messages_sent': int(total_sent),
            'total_delivered': int(total_delivered),
            'total_responses': int(total_responses),
            'total_optouts': len(optouts),
            'delivery_rate': (total_delivered / total_sent * 100) if total_sent > 0 else 0,
            'response_rate': (total_responses / total_sent * 100) if total_sent > 0 else 0
        }


# Export
__all__ = [
    'SMSCampaigns',
    'CAMPAIGN_STATUS',
    'MESSAGE_STATUS',
    'DEFAULT_SMS_TEMPLATES'
]
