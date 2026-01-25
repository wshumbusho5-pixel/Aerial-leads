"""
Twilio Two-Leg Calling Module

Enables VAs to make calls through Twilio:
1. Twilio calls the VA's phone
2. When VA answers, connects to the lead
"""

import os
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

# Twilio setup
TWILIO_AVAILABLE = False
try:
    from twilio.rest import Client
    from twilio.twiml.voice_response import VoiceResponse, Dial

    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        TWILIO_AVAILABLE = True
        logger.info("Twilio calling initialized")
    else:
        logger.warning("Twilio credentials not fully configured")
except ImportError:
    logger.warning("Twilio library not installed. Run: pip install twilio")


def initiate_two_leg_call(
    va_phone: str,
    lead_phone: str,
    lead_name: str = "Unknown",
    lead_address: str = ""
) -> Tuple[bool, str, Optional[str]]:
    """
    Initiate a two-leg call: Twilio calls the VA, then connects to the lead.

    Args:
        va_phone: VA's phone number (where they receive the call)
        lead_phone: Lead's phone number (who they're calling)
        lead_name: Lead's name (for the whisper message)
        lead_address: Lead's address (for context)

    Returns:
        Tuple of (success, message, call_sid)
    """
    if not TWILIO_AVAILABLE:
        return False, "Twilio not configured", None

    if not va_phone or not lead_phone:
        return False, "Missing phone numbers", None

    # Clean phone numbers (ensure E.164 format for US)
    va_phone = clean_phone_number(va_phone)
    lead_phone = clean_phone_number(lead_phone)

    if not va_phone or not lead_phone:
        return False, "Invalid phone number format", None

    try:
        # Create TwiML that will:
        # 1. Play a whisper to the VA with lead info
        # 2. Connect to the lead's phone
        twiml = f"""
        <Response>
            <Say voice="alice">Connecting you to {lead_name} at {lead_address}. Please hold.</Say>
            <Dial callerId="{TWILIO_PHONE_NUMBER}" timeout="30" action="/call-complete">
                <Number>{lead_phone}</Number>
            </Dial>
            <Say>The call could not be completed. Goodbye.</Say>
        </Response>
        """

        # Initiate call to VA's phone
        call = twilio_client.calls.create(
            to=va_phone,
            from_=TWILIO_PHONE_NUMBER,
            twiml=twiml.strip()
        )

        logger.info(f"Call initiated: {call.sid} - VA: {va_phone} -> Lead: {lead_phone}")
        return True, f"Calling your phone now...", call.sid

    except Exception as e:
        logger.error(f"Error initiating call: {e}")
        return False, f"Call failed: {str(e)}", None


def clean_phone_number(phone: str) -> Optional[str]:
    """
    Clean and format phone number to E.164 format for US numbers.

    Args:
        phone: Raw phone number string

    Returns:
        Formatted phone number or None if invalid
    """
    if not phone:
        return None

    # Remove all non-digit characters
    digits = ''.join(filter(str.isdigit, str(phone)))

    # Handle different formats
    if len(digits) == 10:
        # US number without country code
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        # US number with country code
        return f"+{digits}"
    elif len(digits) > 10:
        # Assume international, add + if needed
        return f"+{digits}"
    else:
        # Too short, invalid
        return None


def get_call_status(call_sid: str) -> Optional[dict]:
    """Get the status of a call by SID."""
    if not TWILIO_AVAILABLE or not call_sid:
        return None

    try:
        call = twilio_client.calls(call_sid).fetch()
        return {
            'sid': call.sid,
            'status': call.status,
            'duration': call.duration,
            'direction': call.direction,
            'from': call.from_,
            'to': call.to
        }
    except Exception as e:
        logger.error(f"Error fetching call status: {e}")
        return None


def end_call(call_sid: str) -> Tuple[bool, str]:
    """End an in-progress call."""
    if not TWILIO_AVAILABLE or not call_sid:
        return False, "Cannot end call"

    try:
        call = twilio_client.calls(call_sid).update(status='completed')
        return True, "Call ended"
    except Exception as e:
        logger.error(f"Error ending call: {e}")
        return False, str(e)
