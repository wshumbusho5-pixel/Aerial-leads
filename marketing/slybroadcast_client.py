"""
Slybroadcast API Client - Ringless Voicemail Integration

Official API for dropping voicemails directly without ringing phones.
Docs: https://www.slybroadcast.com/documentation.php

Requires:
- SLYBROADCAST_EMAIL: Your Slybroadcast login email
- SLYBROADCAST_PASSWORD: Your Slybroadcast password
"""

import os
import requests
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from config.logging_config import get_logger

logger = get_logger("SlybroadcastClient")


class SlybroadcastClient:
    """
    Client for Slybroadcast Ringless Voicemail API.

    Usage:
        client = SlybroadcastClient()

        # Check credits
        credits = client.get_credits()

        # Send RVM campaign
        result = client.send_campaign(
            phone_numbers=["+16145551234", "+16145555678"],
            audio_file="my_recording.mp3",
            caller_id="+16145550000",
            campaign_title="Tax Delinquent Outreach"
        )
    """

    # API Endpoints
    BASE_URL = "https://www.mobile-sphere.com/gateway"
    CAMPAIGN_URL = f"{BASE_URL}/vmb.php"
    AUDIO_LIST_URL = f"{BASE_URL}/vmb.aflist.php"
    AUDIO_DOWNLOAD_URL = f"{BASE_URL}/vmb.dla.php"

    def __init__(self, email: str = None, password: str = None):
        """
        Initialize Slybroadcast client.

        Args:
            email: Slybroadcast login email (or set SLYBROADCAST_EMAIL env var)
            password: Slybroadcast password (or set SLYBROADCAST_PASSWORD env var)
        """
        self.email = email or os.environ.get('SLYBROADCAST_EMAIL', '')
        self.password = password or os.environ.get('SLYBROADCAST_PASSWORD', '')

        if not self.email or not self.password:
            logger.warning("Slybroadcast credentials not configured")
            self.configured = False
        else:
            self.configured = True
            logger.info("Slybroadcast client initialized")

    def _make_request(self, url: str, data: Dict) -> Tuple[bool, str]:
        """Make API request to Slybroadcast."""
        if not self.configured:
            return False, "Slybroadcast credentials not configured"

        # Add auth credentials
        data['c_uid'] = self.email
        data['c_password'] = self.password

        try:
            response = requests.post(url, data=data, timeout=30)
            response.raise_for_status()
            return True, response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"Slybroadcast API error: {e}")
            return False, str(e)

    # ========================================
    # CAMPAIGN MANAGEMENT
    # ========================================

    def send_campaign(
        self,
        phone_numbers: List[str],
        audio_file: str = None,
        audio_url: str = None,
        caller_id: str = None,
        campaign_title: str = None,
        schedule_time: str = "now",
        mobile_only: bool = False,
        callback_url: str = None
    ) -> Tuple[bool, Dict]:
        """
        Send a ringless voicemail campaign.

        Args:
            phone_numbers: List of phone numbers (max 10,000 per request)
            audio_file: Name of pre-recorded audio file in your Slybroadcast account
            audio_url: URL to external audio file (WAV, MP3, M4A only)
            caller_id: Caller ID to display (required)
            campaign_title: Title for the campaign
            schedule_time: "now" or "YYYY-MM-DD HH:MM:SS" (Eastern Time, 24hr)
            mobile_only: Only target mobile phones
            callback_url: Webhook URL for status updates

        Returns:
            Tuple of (success, result_dict)
            result_dict contains: session_id, phone_count, message
        """
        if not phone_numbers:
            return False, {"error": "No phone numbers provided"}

        if len(phone_numbers) > 10000:
            return False, {"error": "Maximum 10,000 phone numbers per request"}

        if not audio_file and not audio_url:
            return False, {"error": "Either audio_file or audio_url required"}

        if not caller_id:
            caller_id = os.environ.get('SLYBROADCAST_CALLER_ID', '')
            if not caller_id:
                return False, {"error": "Caller ID required"}

        # Build request data
        data = {
            'c_phone': ','.join(phone_numbers),
            'c_callerID': caller_id,
            'c_date': schedule_time,
        }

        if audio_file:
            data['c_record_audio'] = audio_file
        elif audio_url:
            data['c_url'] = audio_url
            # Determine audio type from URL
            if audio_url.lower().endswith('.mp3'):
                data['c_audio'] = 'MP3'
            elif audio_url.lower().endswith('.wav'):
                data['c_audio'] = 'WAV'
            elif audio_url.lower().endswith('.m4a'):
                data['c_audio'] = 'M4a'
            else:
                data['c_audio'] = 'MP3'  # Default

        if campaign_title:
            data['c_title'] = campaign_title

        if mobile_only:
            data['mobile_only'] = '1'

        if callback_url:
            data['c_dispo_url'] = callback_url

        # Send request
        success, response = self._make_request(self.CAMPAIGN_URL, data)

        if not success:
            return False, {"error": response}

        # Parse response: "OK session_id=9377466671 number of phone=1"
        result = {"raw_response": response}

        if response.startswith("OK"):
            parts = response.split()
            for part in parts:
                if part.startswith("session_id="):
                    result["session_id"] = part.split("=")[1]
                elif "phone=" in part:
                    try:
                        result["phone_count"] = int(part.split("=")[1])
                    except:
                        pass
            result["status"] = "success"
            logger.info(f"Campaign sent: session_id={result.get('session_id')}, phones={result.get('phone_count')}")
            return True, result
        else:
            result["status"] = "failed"
            result["error"] = response
            logger.error(f"Campaign failed: {response}")
            return False, result

    def get_campaign_status(self, session_id: str) -> Tuple[bool, Dict]:
        """Get status of a campaign."""
        data = {
            'c_option': 'campaign_result',
            'session_id': session_id
        }

        success, response = self._make_request(self.CAMPAIGN_URL, data)

        if success:
            return True, {"session_id": session_id, "results": response}
        return False, {"error": response}

    def pause_campaign(self, session_id: str) -> Tuple[bool, str]:
        """Pause a running campaign."""
        data = {
            'c_option': 'pause',
            'session_id': session_id
        }
        return self._make_request(self.CAMPAIGN_URL, data)

    def resume_campaign(self, session_id: str) -> Tuple[bool, str]:
        """Resume a paused campaign."""
        data = {
            'c_option': 'run',
            'session_id': session_id
        }
        return self._make_request(self.CAMPAIGN_URL, data)

    def cancel_campaign(self, session_id: str) -> Tuple[bool, str]:
        """Cancel a scheduled campaign."""
        data = {
            'c_option': 'cancel',
            'session_id': session_id
        }
        return self._make_request(self.CAMPAIGN_URL, data)

    def stop_campaign(self, session_id: str) -> Tuple[bool, str]:
        """Stop a running campaign (irreversible)."""
        data = {
            'c_option': 'stop',
            'session_id': session_id
        }
        return self._make_request(self.CAMPAIGN_URL, data)

    # ========================================
    # AUDIO MANAGEMENT
    # ========================================

    def get_audio_files(self, include_duration: bool = True) -> Tuple[bool, List[Dict]]:
        """Get list of audio files in your account."""
        data = {
            'c_option': 'get_audio_list_with_duration' if include_duration else 'get_audio_list'
        }

        success, response = self._make_request(self.AUDIO_LIST_URL, data)

        if success:
            # Parse audio list
            files = []
            lines = response.strip().split('\n')
            for line in lines:
                if line and '|' in line:
                    parts = line.split('|')
                    file_info = {"name": parts[0].strip('"')}
                    if len(parts) > 1:
                        file_info["duration"] = parts[1].strip('"')
                    files.append(file_info)
            return True, files
        return False, []

    # ========================================
    # ACCOUNT MANAGEMENT
    # ========================================

    def get_credits(self) -> Tuple[bool, Dict]:
        """Get remaining message credits."""
        data = {'remain_message': '1'}

        success, response = self._make_request(self.CAMPAIGN_URL, data)

        if success:
            # Parse: "remaining=500 pending=50"
            result = {"raw_response": response}
            parts = response.split()
            for part in parts:
                if part.startswith("remaining="):
                    try:
                        result["remaining"] = int(part.split("=")[1])
                    except:
                        pass
                elif part.startswith("pending="):
                    try:
                        result["pending"] = int(part.split("=")[1])
                    except:
                        pass
            return True, result
        return False, {"error": response}

    def add_to_dnc(self, phone_numbers: List[str]) -> Tuple[bool, str]:
        """Add phone numbers to Do Not Call list."""
        data = {
            'c_option': 'do_not_dial',
            'c_phone': ','.join(phone_numbers)
        }
        return self._make_request(self.CAMPAIGN_URL, data)

    def remove_from_dnc(self, phone_numbers: List[str]) -> Tuple[bool, str]:
        """Remove phone numbers from Do Not Call list."""
        data = {
            'c_option': 'remove_do_not_dial',
            'c_phone': ','.join(phone_numbers)
        }
        return self._make_request(self.CAMPAIGN_URL, data)

    # ========================================
    # HELPER METHODS
    # ========================================

    def test_connection(self) -> Tuple[bool, str]:
        """Test API connection by checking credits."""
        success, result = self.get_credits()

        if success:
            remaining = result.get('remaining', 'unknown')
            return True, f"Connected! Remaining credits: {remaining}"
        return False, f"Connection failed: {result.get('error', 'Unknown error')}"


# Convenience function
def get_slybroadcast_client() -> SlybroadcastClient:
    """Get configured Slybroadcast client instance."""
    return SlybroadcastClient()


if __name__ == "__main__":
    # Test the client
    client = SlybroadcastClient()

    print("Testing Slybroadcast connection...")
    success, message = client.test_connection()
    print(f"Result: {message}")

    if success:
        print("\nGetting audio files...")
        success, files = client.get_audio_files()
        if success:
            print(f"Audio files: {files}")
