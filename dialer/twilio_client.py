"""
Twilio Client Wrapper for Lifeline Home Buyers Dialer

Handles all Twilio API interactions for outbound calling.
"""

import os
from typing import Optional, Dict, List
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from dotenv import load_dotenv

load_dotenv()


class TwilioClient:
    """Wrapper for Twilio API operations."""

    def __init__(self):
        """Initialize Twilio client with credentials from environment."""
        self.account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.default_from_number = os.getenv('TWILIO_PHONE_NUMBER')

        if not self.account_sid or not self.auth_token:
            raise ValueError("Twilio credentials not found in environment variables")

        self.client = Client(self.account_sid, self.auth_token)
        self._phone_numbers_cache = None

    def get_account_info(self) -> Dict:
        """Get Twilio account information."""
        try:
            account = self.client.api.accounts(self.account_sid).fetch()
            return {
                'sid': account.sid,
                'friendly_name': account.friendly_name,
                'status': account.status,
                'type': account.type,
            }
        except TwilioRestException as e:
            return {'error': str(e)}

    def get_balance(self) -> Dict:
        """Get account balance."""
        try:
            balance = self.client.api.accounts(self.account_sid).balance.fetch()
            return {
                'balance': balance.balance,
                'currency': balance.currency,
            }
        except TwilioRestException as e:
            return {'error': str(e)}

    def get_phone_numbers(self, force_refresh: bool = False) -> List[Dict]:
        """Get list of phone numbers in account."""
        if self._phone_numbers_cache and not force_refresh:
            return self._phone_numbers_cache

        try:
            numbers = self.client.incoming_phone_numbers.list()
            self._phone_numbers_cache = [
                {
                    'sid': num.sid,
                    'phone_number': num.phone_number,
                    'friendly_name': num.friendly_name,
                    'capabilities': {
                        'voice': num.capabilities.get('voice', False),
                        'sms': num.capabilities.get('sms', False),
                    }
                }
                for num in numbers
            ]
            return self._phone_numbers_cache
        except TwilioRestException as e:
            return [{'error': str(e)}]

    def search_available_numbers(self, area_code: str = None, contains: str = None,
                                  limit: int = 10) -> List[Dict]:
        """Search for available phone numbers to purchase."""
        try:
            search_params = {
                'voice_enabled': True,
                'limit': limit,
            }
            if area_code:
                search_params['area_code'] = area_code
            if contains:
                search_params['contains'] = contains

            numbers = self.client.available_phone_numbers('US').local.list(**search_params)
            return [
                {
                    'phone_number': num.phone_number,
                    'friendly_name': num.friendly_name,
                    'locality': num.locality,
                    'region': num.region,
                    'postal_code': num.postal_code,
                    'capabilities': {
                        'voice': num.capabilities.get('voice', False),
                        'sms': num.capabilities.get('sms', False),
                    }
                }
                for num in numbers
            ]
        except TwilioRestException as e:
            return [{'error': str(e)}]

    def buy_phone_number(self, phone_number: str, friendly_name: str = None) -> Dict:
        """Purchase a phone number."""
        try:
            params = {'phone_number': phone_number}
            if friendly_name:
                params['friendly_name'] = friendly_name

            number = self.client.incoming_phone_numbers.create(**params)
            self._phone_numbers_cache = None  # Clear cache
            return {
                'success': True,
                'sid': number.sid,
                'phone_number': number.phone_number,
                'friendly_name': number.friendly_name,
            }
        except TwilioRestException as e:
            return {'success': False, 'error': str(e)}

    def make_call(self, to_number: str, from_number: str = None,
                  twiml_url: str = None, twiml: str = None,
                  status_callback: str = None, record: bool = False) -> Dict:
        """
        Initiate an outbound call.

        Args:
            to_number: Phone number to call (E.164 format)
            from_number: Caller ID to display (must be owned number)
            twiml_url: URL returning TwiML instructions
            twiml: Raw TwiML string for call instructions
            status_callback: URL to receive call status updates
            record: Whether to record the call

        Returns:
            Call details dictionary
        """
        try:
            from_number = from_number or self.default_from_number

            if not from_number:
                return {'success': False, 'error': 'No from_number specified'}

            call_params = {
                'to': to_number,
                'from_': from_number,
                'record': record,
            }

            if twiml_url:
                call_params['url'] = twiml_url
            elif twiml:
                call_params['twiml'] = twiml
            else:
                # Default: Simple connection TwiML
                call_params['twiml'] = '<Response><Say>Connecting your call.</Say><Dial><Client>agent</Client></Dial></Response>'

            if status_callback:
                call_params['status_callback'] = status_callback
                call_params['status_callback_event'] = ['initiated', 'ringing', 'answered', 'completed']

            call = self.client.calls.create(**call_params)

            return {
                'success': True,
                'call_sid': call.sid,
                'status': call.status,
                'to': call.to,
                'from': getattr(call, 'from_', None) or 'Unknown',
                'direction': call.direction,
            }
        except TwilioRestException as e:
            return {'success': False, 'error': str(e)}

    def get_call_status(self, call_sid: str) -> Dict:
        """Get current status of a call."""
        try:
            call = self.client.calls(call_sid).fetch()
            return {
                'call_sid': call.sid,
                'status': call.status,
                'duration': call.duration,
                'start_time': str(call.start_time) if call.start_time else None,
                'end_time': str(call.end_time) if call.end_time else None,
                'to': call.to,
                'from': getattr(call, 'from_', None) or 'Unknown',
            }
        except TwilioRestException as e:
            return {'error': str(e)}

    def end_call(self, call_sid: str) -> Dict:
        """End an active call."""
        try:
            call = self.client.calls(call_sid).update(status='completed')
            return {
                'success': True,
                'call_sid': call.sid,
                'status': call.status,
            }
        except TwilioRestException as e:
            return {'success': False, 'error': str(e)}

    def get_call_recordings(self, call_sid: str) -> List[Dict]:
        """Get recordings for a specific call."""
        try:
            recordings = self.client.recordings.list(call_sid=call_sid)
            return [
                {
                    'recording_sid': rec.sid,
                    'duration': rec.duration,
                    'url': f"https://api.twilio.com{rec.uri.replace('.json', '.mp3')}",
                    'date_created': str(rec.date_created),
                }
                for rec in recordings
            ]
        except TwilioRestException as e:
            return [{'error': str(e)}]

    def get_recent_calls(self, limit: int = 20) -> List[Dict]:
        """Get recent call history."""
        try:
            calls = self.client.calls.list(limit=limit)
            result = []
            for call in calls:
                call_data = {
                    'call_sid': call.sid,
                    'status': call.status,
                    'direction': call.direction,
                    'duration': call.duration,
                    'to': call.to,
                    'from': getattr(call, 'from_', None) or getattr(call, 'caller', 'Unknown'),
                    'start_time': str(call.start_time) if call.start_time else None,
                }
                result.append(call_data)
            return result
        except TwilioRestException as e:
            return [{'error': str(e)}]

    def validate_phone_number(self, phone_number: str) -> Dict:
        """Validate and format a phone number."""
        try:
            lookup = self.client.lookups.v2.phone_numbers(phone_number).fetch()
            return {
                'valid': lookup.valid,
                'phone_number': lookup.phone_number,
                'country_code': lookup.country_code,
                'calling_country_code': lookup.calling_country_code,
                'national_format': lookup.national_format,
            }
        except TwilioRestException as e:
            return {'valid': False, 'error': str(e)}


def test_connection():
    """Test Twilio connection with current credentials."""
    try:
        client = TwilioClient()
        info = client.get_account_info()
        balance = client.get_balance()
        numbers = client.get_phone_numbers()

        print("Twilio Connection Test")
        print("=" * 40)
        print(f"Account: {info.get('friendly_name', 'N/A')}")
        print(f"Status: {info.get('status', 'N/A')}")
        print(f"Balance: ${balance.get('balance', 'N/A')} {balance.get('currency', '')}")
        print(f"Phone Numbers: {len(numbers)}")
        for num in numbers:
            if 'error' not in num:
                print(f"  - {num['phone_number']} ({num['friendly_name']})")

        return True
    except Exception as e:
        print(f"Connection failed: {e}")
        return False


if __name__ == '__main__':
    test_connection()
