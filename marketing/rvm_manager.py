"""
Aerial Leads - RVM (Ringless Voicemail) & Number Rotation Manager

Solve the spam risk problem:
1. Warm leads with RVM before calling
2. Rotate phone numbers to avoid spam flags
3. Track number health and rotation

Integration Points:
- Slybroadcast for RVM delivery (INTEGRATED)
- Twilio / OpenPhone for number rotation
"""

import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import json
import random
from typing import List, Dict, Optional, Tuple

from config.settings import DATA_DIR
from config.logging_config import get_logger

# Slybroadcast integration
try:
    from marketing.slybroadcast_client import SlybroadcastClient, get_slybroadcast_client
    SLYBROADCAST_AVAILABLE = True
except ImportError:
    SLYBROADCAST_AVAILABLE = False


class NumberRotationManager:
    """
    Manage phone number rotation for outbound calling.

    Best Practices:
    - Rotate numbers every 20-30 calls
    - Rest numbers after high usage (24-48 hours)
    - Use local area codes when possible
    - Track spam reports and remove flagged numbers
    """

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.numbers_file = DATA_DIR / "phone_numbers.json"
        self.usage_log_file = DATA_DIR / "number_usage_log.csv"

        self._init_files()

    def _init_files(self):
        """Initialize data files."""
        if not self.numbers_file.exists():
            with open(self.numbers_file, 'w') as f:
                json.dump({
                    "numbers": [],
                    "settings": {
                        "calls_before_rotation": 25,
                        "rest_hours_after_limit": 24,
                        "max_daily_calls_per_number": 100
                    }
                }, f, indent=2)

        if not self.usage_log_file.exists():
            pd.DataFrame(columns=[
                'timestamp', 'phone_number', 'action', 'target_number',
                'outcome', 'duration', 'notes'
            ]).to_csv(self.usage_log_file, index=False)

    # ========================================
    # NUMBER MANAGEMENT
    # ========================================

    def add_number(
        self,
        phone_number: str,
        area_code: str = None,
        provider: str = "manual",
        notes: str = ""
    ) -> str:
        """
        Add a phone number to the rotation pool.

        Args:
            phone_number: The phone number (format: +1XXXXXXXXXX)
            area_code: Area code for local presence matching
            provider: Provider name (twilio, openphone, manual)
            notes: Any notes about the number

        Returns:
            Number ID
        """
        with open(self.numbers_file, 'r') as f:
            data = json.load(f)

        # Clean phone number
        clean_number = ''.join(filter(str.isdigit, phone_number))
        if len(clean_number) == 10:
            clean_number = '1' + clean_number

        # Extract area code if not provided
        if not area_code and len(clean_number) >= 4:
            area_code = clean_number[1:4] if clean_number.startswith('1') else clean_number[:3]

        number_id = f"NUM-{clean_number[-4:]}-{datetime.now().strftime('%H%M%S')}"

        number_record = {
            'id': number_id,
            'phone_number': clean_number,
            'formatted': f"+1 ({clean_number[1:4]}) {clean_number[4:7]}-{clean_number[7:]}",
            'area_code': area_code,
            'provider': provider,
            'status': 'active',
            'health_score': 100,
            'total_calls': 0,
            'calls_today': 0,
            'calls_since_rotation': 0,
            'last_used': None,
            'resting_until': None,
            'spam_reports': 0,
            'added_at': datetime.now().isoformat(),
            'notes': notes
        }

        data['numbers'].append(number_record)

        with open(self.numbers_file, 'w') as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Added number: {number_record['formatted']}")
        return number_id

    def get_numbers(self, status: str = None, area_code: str = None) -> List[Dict]:
        """Get all numbers, optionally filtered."""
        with open(self.numbers_file, 'r') as f:
            data = json.load(f)

        numbers = data.get('numbers', [])

        if status:
            numbers = [n for n in numbers if n.get('status') == status]

        if area_code:
            numbers = [n for n in numbers if n.get('area_code') == area_code]

        return numbers

    def get_available_numbers(self, area_code: str = None) -> List[Dict]:
        """Get numbers available for use (not resting, not flagged)."""
        numbers = self.get_numbers(status='active', area_code=area_code)

        now = datetime.now()
        available = []

        for num in numbers:
            # Check if resting
            if num.get('resting_until'):
                rest_until = datetime.fromisoformat(num['resting_until'])
                if now < rest_until:
                    continue

            # Check health score
            if num.get('health_score', 100) < 30:
                continue

            available.append(num)

        return available

    def get_next_number(self, target_area_code: str = None) -> Optional[Dict]:
        """
        Get the next best number to use for calling.

        Prioritizes:
        1. Local area code match (if provided)
        2. Least recently used
        3. Lowest calls since rotation
        4. Highest health score
        """
        # First try to match area code
        if target_area_code:
            local_numbers = self.get_available_numbers(area_code=target_area_code)
            if local_numbers:
                # Sort by calls since rotation (ascending)
                local_numbers.sort(key=lambda x: x.get('calls_since_rotation', 0))
                return local_numbers[0]

        # Fall back to any available number
        available = self.get_available_numbers()
        if not available:
            self.logger.warning("No available numbers for rotation!")
            return None

        # Sort by calls since rotation
        available.sort(key=lambda x: x.get('calls_since_rotation', 0))
        return available[0]

    def log_call(
        self,
        number_id: str,
        target_number: str,
        outcome: str,
        duration: int = 0,
        notes: str = ""
    ):
        """
        Log a call and update number statistics.

        Args:
            number_id: The number ID used for calling
            target_number: The number that was called
            outcome: Call outcome (connected, no_answer, voicemail, etc.)
            duration: Call duration in seconds
            notes: Additional notes
        """
        with open(self.numbers_file, 'r') as f:
            data = json.load(f)

        settings = data.get('settings', {})
        calls_before_rotation = settings.get('calls_before_rotation', 25)
        rest_hours = settings.get('rest_hours_after_limit', 24)
        max_daily = settings.get('max_daily_calls_per_number', 100)

        for num in data['numbers']:
            if num['id'] == number_id:
                num['total_calls'] = num.get('total_calls', 0) + 1
                num['calls_today'] = num.get('calls_today', 0) + 1
                num['calls_since_rotation'] = num.get('calls_since_rotation', 0) + 1
                num['last_used'] = datetime.now().isoformat()

                # Check if needs rotation rest
                if num['calls_since_rotation'] >= calls_before_rotation:
                    rest_until = datetime.now() + timedelta(hours=rest_hours)
                    num['resting_until'] = rest_until.isoformat()
                    num['calls_since_rotation'] = 0
                    self.logger.info(f"Number {num['formatted']} going to rest until {rest_until}")

                # Check daily limit
                if num['calls_today'] >= max_daily:
                    tomorrow = datetime.now() + timedelta(days=1)
                    tomorrow = tomorrow.replace(hour=8, minute=0, second=0)
                    num['resting_until'] = tomorrow.isoformat()
                    self.logger.info(f"Number {num['formatted']} hit daily limit, resting until tomorrow")

                break

        with open(self.numbers_file, 'w') as f:
            json.dump(data, f, indent=2)

        # Log to usage CSV
        log_df = pd.read_csv(self.usage_log_file)
        new_log = {
            'timestamp': datetime.now().isoformat(),
            'phone_number': number_id,
            'action': 'call',
            'target_number': target_number,
            'outcome': outcome,
            'duration': duration,
            'notes': notes
        }
        log_df = pd.concat([log_df, pd.DataFrame([new_log])], ignore_index=True)
        log_df.to_csv(self.usage_log_file, index=False)

    def report_spam(self, number_id: str, notes: str = ""):
        """Report a number as flagged for spam."""
        with open(self.numbers_file, 'r') as f:
            data = json.load(f)

        for num in data['numbers']:
            if num['id'] == number_id:
                num['spam_reports'] = num.get('spam_reports', 0) + 1
                num['health_score'] = max(0, num.get('health_score', 100) - 25)

                if num['health_score'] < 30:
                    num['status'] = 'flagged'
                    self.logger.warning(f"Number {num['formatted']} flagged as spam!")

                break

        with open(self.numbers_file, 'w') as f:
            json.dump(data, f, indent=2)

    def reset_daily_counts(self):
        """Reset daily call counts (run at midnight)."""
        with open(self.numbers_file, 'r') as f:
            data = json.load(f)

        for num in data['numbers']:
            num['calls_today'] = 0

        with open(self.numbers_file, 'w') as f:
            json.dump(data, f, indent=2)

        self.logger.info("Reset daily call counts")

    def get_rotation_stats(self) -> Dict:
        """Get statistics about number rotation."""
        numbers = self.get_numbers()
        available = self.get_available_numbers()

        total_calls = sum(n.get('total_calls', 0) for n in numbers)
        today_calls = sum(n.get('calls_today', 0) for n in numbers)
        avg_health = sum(n.get('health_score', 100) for n in numbers) / len(numbers) if numbers else 0

        return {
            'total_numbers': len(numbers),
            'available_numbers': len(available),
            'resting_numbers': len([n for n in numbers if n.get('resting_until')]),
            'flagged_numbers': len([n for n in numbers if n.get('status') == 'flagged']),
            'total_calls': total_calls,
            'calls_today': today_calls,
            'average_health': avg_health,
            'numbers': numbers
        }


class RVMManager:
    """
    Manage Ringless Voicemail campaigns.

    RVM drops a voicemail directly without ringing the phone.
    Great for warming leads before cold calling.

    Integration options:
    - Slybroadcast ($0.02-0.03 per drop)
    - Drop Cowboy ($0.04-0.05 per drop)
    - Stratics Networks
    """

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.campaigns_file = DATA_DIR / "rvm_campaigns.json"
        self.drops_log_file = DATA_DIR / "rvm_drops.csv"

        self._init_files()

    def _init_files(self):
        """Initialize data files."""
        if not self.campaigns_file.exists():
            with open(self.campaigns_file, 'w') as f:
                json.dump({
                    "campaigns": [],
                    "voicemail_scripts": {},
                    "settings": {
                        "provider": "manual",  # or slybroadcast, dropcowboy
                        "api_key": "",
                        "default_caller_id": ""
                    }
                }, f, indent=2)

        if not self.drops_log_file.exists():
            pd.DataFrame(columns=[
                'drop_id', 'campaign_id', 'target_number', 'script_id',
                'dropped_at', 'status', 'callback', 'notes'
            ]).to_csv(self.drops_log_file, index=False)

    # ========================================
    # CAMPAIGN MANAGEMENT
    # ========================================

    def create_campaign(
        self,
        name: str,
        script_id: str,
        lead_type: str = None,
        description: str = ""
    ) -> str:
        """Create a new RVM campaign."""
        campaign_id = f"RVM-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        with open(self.campaigns_file, 'r') as f:
            data = json.load(f)

        campaign = {
            'id': campaign_id,
            'name': name,
            'script_id': script_id,
            'lead_type': lead_type,
            'description': description,
            'status': 'active',
            'created_at': datetime.now().isoformat(),
            'stats': {
                'total_drops': 0,
                'successful': 0,
                'failed': 0,
                'callbacks': 0
            }
        }

        data['campaigns'].append(campaign)

        with open(self.campaigns_file, 'w') as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Created RVM campaign: {name}")
        return campaign_id

    def get_campaigns(self, status: str = None) -> List[Dict]:
        """Get all RVM campaigns."""
        with open(self.campaigns_file, 'r') as f:
            data = json.load(f)

        campaigns = data.get('campaigns', [])

        if status:
            campaigns = [c for c in campaigns if c.get('status') == status]

        return campaigns

    # ========================================
    # VOICEMAIL SCRIPTS
    # ========================================

    def add_script(
        self,
        script_id: str,
        name: str,
        script_text: str,
        audio_url: str = "",
        duration_seconds: int = 30
    ):
        """Add a voicemail script."""
        with open(self.campaigns_file, 'r') as f:
            data = json.load(f)

        data['voicemail_scripts'][script_id] = {
            'id': script_id,
            'name': name,
            'script_text': script_text,
            'audio_url': audio_url,
            'duration_seconds': duration_seconds,
            'created_at': datetime.now().isoformat()
        }

        with open(self.campaigns_file, 'w') as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Added voicemail script: {name}")

    def get_scripts(self) -> Dict:
        """Get all voicemail scripts."""
        with open(self.campaigns_file, 'r') as f:
            data = json.load(f)
        return data.get('voicemail_scripts', {})

    # ========================================
    # RVM DROP MANAGEMENT
    # ========================================

    def generate_drop_list(
        self,
        campaign_id: str,
        limit: int = 500
    ) -> pd.DataFrame:
        """Generate a list of numbers for RVM drops."""
        with open(self.campaigns_file, 'r') as f:
            data = json.load(f)

        # Find campaign
        campaign = None
        for c in data.get('campaigns', []):
            if c['id'] == campaign_id:
                campaign = c
                break

        if not campaign:
            self.logger.error(f"Campaign not found: {campaign_id}")
            return pd.DataFrame()

        # Load leads with phone numbers
        from config.settings import PROCESSED_DATA_DIR
        leads_file = PROCESSED_DATA_DIR / 'columbus_oh_all_leads.csv'
        if not leads_file.exists():
            leads_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

        if not leads_file.exists():
            return pd.DataFrame()

        df = pd.read_csv(leads_file)

        # Filter for leads with phone numbers
        if 'phone' in df.columns:
            df = df[df['phone'].notna() & (df['phone'] != '')]
        else:
            self.logger.warning("No phone column in leads data")
            return pd.DataFrame()

        # Filter by lead type if specified
        if campaign.get('lead_type') and 'lead_type' in df.columns:
            df = df[df['lead_type'] == campaign['lead_type']]

        # Exclude already dropped numbers
        drops_df = pd.read_csv(self.drops_log_file)
        campaign_drops = drops_df[drops_df['campaign_id'] == campaign_id]['target_number'].tolist()
        df = df[~df['phone'].isin(campaign_drops)]

        # Limit results
        df = df.head(limit)

        # Format for RVM
        drop_list = []
        for _, row in df.iterrows():
            drop_list.append({
                'campaign_id': campaign_id,
                'target_number': row.get('phone', ''),
                'owner_name': row.get('owner_name', ''),
                'address': row.get('address', ''),
                'lead_type': row.get('lead_type', '')
            })

        return pd.DataFrame(drop_list)

    def log_drops(
        self,
        campaign_id: str,
        numbers: List[str],
        script_id: str
    ) -> int:
        """Log RVM drops as sent."""
        df = pd.read_csv(self.drops_log_file)

        new_records = []
        for number in numbers:
            drop_id = f"DROP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"
            new_records.append({
                'drop_id': drop_id,
                'campaign_id': campaign_id,
                'target_number': number,
                'script_id': script_id,
                'dropped_at': datetime.now().isoformat(),
                'status': 'sent',
                'callback': False,
                'notes': ''
            })

        df = pd.concat([df, pd.DataFrame(new_records)], ignore_index=True)
        df.to_csv(self.drops_log_file, index=False)

        # Update campaign stats
        self._update_campaign_stats(campaign_id, total_drops=len(numbers))

        self.logger.info(f"Logged {len(numbers)} RVM drops for campaign {campaign_id}")
        return len(new_records)

    def log_callback(self, target_number: str, notes: str = ""):
        """Log a callback from an RVM drop."""
        df = pd.read_csv(self.drops_log_file)

        # Find the most recent drop to this number
        matches = df[df['target_number'] == target_number]
        if not matches.empty:
            idx = matches.index[-1]
            df.at[idx, 'callback'] = True
            df.at[idx, 'notes'] = notes
            df.to_csv(self.drops_log_file, index=False)

            # Update campaign stats
            campaign_id = df.at[idx, 'campaign_id']
            self._update_campaign_stats(campaign_id, callbacks=1)

            self.logger.info(f"Logged callback from {target_number}")

    def _update_campaign_stats(
        self,
        campaign_id: str,
        total_drops: int = 0,
        callbacks: int = 0
    ):
        """Update campaign statistics."""
        with open(self.campaigns_file, 'r') as f:
            data = json.load(f)

        for campaign in data['campaigns']:
            if campaign['id'] == campaign_id:
                campaign['stats']['total_drops'] += total_drops
                campaign['stats']['callbacks'] += callbacks
                break

        with open(self.campaigns_file, 'w') as f:
            json.dump(data, f, indent=2)

    def get_campaign_stats(self, campaign_id: str) -> Dict:
        """Get detailed stats for an RVM campaign."""
        campaigns = self.get_campaigns()
        campaign = next((c for c in campaigns if c['id'] == campaign_id), None)

        if not campaign:
            return {}

        df = pd.read_csv(self.drops_log_file)
        campaign_drops = df[df['campaign_id'] == campaign_id]

        total = len(campaign_drops)
        callbacks = len(campaign_drops[campaign_drops['callback'] == True])

        return {
            'campaign': campaign,
            'total_drops': total,
            'callbacks': callbacks,
            'callback_rate': (callbacks / total * 100) if total > 0 else 0,
            'recent_drops': campaign_drops.tail(10).to_dict('records')
        }

    # ========================================
    # SLYBROADCAST INTEGRATION
    # ========================================

    def get_slybroadcast_client(self) -> Optional['SlybroadcastClient']:
        """Get Slybroadcast client if available."""
        if not SLYBROADCAST_AVAILABLE:
            self.logger.warning("Slybroadcast client not available")
            return None
        return get_slybroadcast_client()

    def check_slybroadcast_connection(self) -> Tuple[bool, str]:
        """Test Slybroadcast API connection."""
        client = self.get_slybroadcast_client()
        if not client:
            return False, "Slybroadcast not configured"
        return client.test_connection()

    def get_slybroadcast_credits(self) -> Tuple[bool, Dict]:
        """Get remaining Slybroadcast credits."""
        client = self.get_slybroadcast_client()
        if not client:
            return False, {"error": "Slybroadcast not configured"}
        return client.get_credits()

    def get_slybroadcast_audio_files(self) -> Tuple[bool, List[Dict]]:
        """Get list of audio files from Slybroadcast account."""
        client = self.get_slybroadcast_client()
        if not client:
            return False, []
        return client.get_audio_files()

    def send_rvm_campaign(
        self,
        campaign_id: str,
        audio_file: str = None,
        audio_url: str = None,
        caller_id: str = None,
        phone_numbers: List[str] = None,
        max_numbers: int = 500,
        schedule_time: str = "now"
    ) -> Tuple[bool, Dict]:
        """
        Send RVM campaign through Slybroadcast.

        Args:
            campaign_id: Internal campaign ID
            audio_file: Name of audio file in Slybroadcast account
            audio_url: URL to external audio file
            caller_id: Caller ID to display
            phone_numbers: List of phone numbers (or auto-generate from leads)
            max_numbers: Max numbers if auto-generating
            schedule_time: "now" or "YYYY-MM-DD HH:MM:SS"

        Returns:
            Tuple of (success, result_dict)
        """
        client = self.get_slybroadcast_client()
        if not client:
            return False, {"error": "Slybroadcast not configured"}

        if not client.configured:
            return False, {"error": "Slybroadcast credentials not set"}

        # Get campaign info
        campaigns = self.get_campaigns()
        campaign = next((c for c in campaigns if c['id'] == campaign_id), None)
        if not campaign:
            return False, {"error": f"Campaign not found: {campaign_id}"}

        # Get phone numbers
        if not phone_numbers:
            drop_list = self.generate_drop_list(campaign_id, limit=max_numbers)
            if drop_list.empty:
                return False, {"error": "No phone numbers available for this campaign"}
            phone_numbers = drop_list['target_number'].tolist()

        # Get audio from script if not provided
        if not audio_file and not audio_url:
            scripts = self.get_scripts()
            script = scripts.get(campaign.get('script_id', ''))
            if script and script.get('audio_url'):
                audio_url = script['audio_url']
            else:
                return False, {"error": "No audio file or URL provided"}

        # Send through Slybroadcast
        success, result = client.send_campaign(
            phone_numbers=phone_numbers,
            audio_file=audio_file,
            audio_url=audio_url,
            caller_id=caller_id,
            campaign_title=campaign.get('name', campaign_id),
            schedule_time=schedule_time
        )

        if success:
            # Log the drops
            self.log_drops(campaign_id, phone_numbers, campaign.get('script_id', ''))

            # Store Slybroadcast session ID
            self._save_slybroadcast_session(
                campaign_id,
                result.get('session_id'),
                len(phone_numbers)
            )

            self.logger.info(f"RVM campaign sent: {len(phone_numbers)} drops, session_id={result.get('session_id')}")

        return success, result

    def _save_slybroadcast_session(self, campaign_id: str, session_id: str, count: int):
        """Save Slybroadcast session ID for tracking."""
        with open(self.campaigns_file, 'r') as f:
            data = json.load(f)

        for campaign in data['campaigns']:
            if campaign['id'] == campaign_id:
                if 'slybroadcast_sessions' not in campaign:
                    campaign['slybroadcast_sessions'] = []
                campaign['slybroadcast_sessions'].append({
                    'session_id': session_id,
                    'count': count,
                    'sent_at': datetime.now().isoformat()
                })
                break

        with open(self.campaigns_file, 'w') as f:
            json.dump(data, f, indent=2)

    def get_slybroadcast_campaign_status(self, session_id: str) -> Tuple[bool, Dict]:
        """Get status of a Slybroadcast campaign."""
        client = self.get_slybroadcast_client()
        if not client:
            return False, {"error": "Slybroadcast not configured"}
        return client.get_campaign_status(session_id)

    def pause_slybroadcast_campaign(self, session_id: str) -> Tuple[bool, str]:
        """Pause a Slybroadcast campaign."""
        client = self.get_slybroadcast_client()
        if not client:
            return False, "Slybroadcast not configured"
        return client.pause_campaign(session_id)

    def resume_slybroadcast_campaign(self, session_id: str) -> Tuple[bool, str]:
        """Resume a paused Slybroadcast campaign."""
        client = self.get_slybroadcast_client()
        if not client:
            return False, "Slybroadcast not configured"
        return client.resume_campaign(session_id)

    def stop_slybroadcast_campaign(self, session_id: str) -> Tuple[bool, str]:
        """Stop a Slybroadcast campaign (irreversible)."""
        client = self.get_slybroadcast_client()
        if not client:
            return False, "Slybroadcast not configured"
        return client.stop_campaign(session_id)


# Default voicemail scripts
DEFAULT_RVM_SCRIPTS = {
    'probate_warm': {
        'name': 'Probate Warm Introduction',
        'script_text': '''Hi, this is Willy from Lifeline Home Buyers.

I understand you may have inherited a property recently. I know this can be a difficult time, and I wanted to reach out personally.

My family lost our home years ago when no one would help, so I started Lifeline to make sure other families have options.

If you're thinking about selling the property, I'd love to chat. No pressure - just options.

Give me a call back at [YOUR NUMBER]. Again, this is Willy from Lifeline Home Buyers.

Take care.''',
        'duration_seconds': 35
    },
    'tax_delinquent_warm': {
        'name': 'Tax Delinquent Warm Introduction',
        'script_text': '''Hi there, this is Willy from Lifeline Home Buyers.

I noticed your property may have some tax issues. I'm calling because my own family lost our home to back taxes, and I don't want to see that happen to anyone else.

I buy houses for cash and can help with tax situations. No judgment, just solutions.

If you'd like to talk about your options, call me back at [YOUR NUMBER].

This is Willy from Lifeline Home Buyers. Hope to hear from you.''',
        'duration_seconds': 32
    },
    'general_investor': {
        'name': 'General Investor Introduction',
        'script_text': '''Hi, this is Willy with Lifeline Home Buyers.

I'm a local real estate investor and I'm interested in buying properties in your area for cash.

If you've ever thought about selling your house - whether it needs work, you're relocating, or you just want a quick, hassle-free sale - I'd love to make you an offer.

Call or text me back at [YOUR NUMBER].

Thanks, and have a great day!''',
        'duration_seconds': 28
    }
}


# CLI for testing
if __name__ == '__main__':
    # Test Number Rotation
    print("=== Number Rotation Manager ===")
    num_manager = NumberRotationManager()

    # Add some test numbers
    num_manager.add_number("614-555-1001", provider="test")
    num_manager.add_number("614-555-1002", provider="test")
    num_manager.add_number("740-555-1003", area_code="740", provider="test")

    print("\nRotation Stats:")
    print(num_manager.get_rotation_stats())

    # Test RVM
    print("\n=== RVM Manager ===")
    rvm_manager = RVMManager()

    # Add default scripts
    for script_id, script in DEFAULT_RVM_SCRIPTS.items():
        rvm_manager.add_script(
            script_id=script_id,
            name=script['name'],
            script_text=script['script_text'],
            duration_seconds=script['duration_seconds']
        )

    print("\nScripts added:")
    for script_id, script in rvm_manager.get_scripts().items():
        print(f"  - {script['name']}")
