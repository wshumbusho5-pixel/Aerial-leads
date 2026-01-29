"""
Browser-Based Calling Module using Twilio Client (WebRTC)

Allows VAs to make calls directly from their browser without needing their phone.
Much cheaper than two-leg calling (no international call to VA's phone).

Requires:
- Twilio Account with Voice capabilities
- TwiML App configured in Twilio Console
"""

import os
import logging
from typing import Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Twilio setup
TWILIO_CLIENT_AVAILABLE = False
try:
    from twilio.rest import Client
    from twilio.jwt.client import ClientCapabilityToken
    from twilio.jwt.access_token import AccessToken
    from twilio.jwt.access_token.grants import VoiceGrant
    from twilio.twiml.voice_response import VoiceResponse, Dial

    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')
    TWILIO_TWIML_APP_SID = os.environ.get('TWILIO_TWIML_APP_SID', '')
    TWILIO_API_KEY = os.environ.get('TWILIO_API_KEY', '')
    TWILIO_API_SECRET = os.environ.get('TWILIO_API_SECRET', '')

    if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        TWILIO_CLIENT_AVAILABLE = True
        logger.info("Twilio browser calling initialized")
    else:
        logger.warning("Twilio credentials not fully configured")
except ImportError:
    logger.warning("Twilio library not installed. Run: pip install twilio")


def generate_access_token(identity: str) -> Tuple[bool, str, Optional[str]]:
    """
    Generate an access token for Twilio Client (browser-based calling).

    Args:
        identity: Unique identifier for the VA (username)

    Returns:
        Tuple of (success, message/token, error)
    """
    if not TWILIO_CLIENT_AVAILABLE:
        return False, "Twilio not configured", None

    if not TWILIO_API_KEY or not TWILIO_API_SECRET:
        # Fall back to capability token if API key not set
        return generate_capability_token(identity)

    try:
        # Create access token
        token = AccessToken(
            TWILIO_ACCOUNT_SID,
            TWILIO_API_KEY,
            TWILIO_API_SECRET,
            identity=identity,
            ttl=3600  # 1 hour
        )

        # Create Voice grant
        voice_grant = VoiceGrant(
            outgoing_application_sid=TWILIO_TWIML_APP_SID,
            incoming_allow=False  # VAs don't receive browser calls
        )
        token.add_grant(voice_grant)

        logger.info(f"Generated access token for: {identity}")
        return True, token.to_jwt(), None

    except Exception as e:
        logger.error(f"Error generating access token: {e}")
        return False, str(e), None


def generate_capability_token(identity: str) -> Tuple[bool, str, Optional[str]]:
    """
    Generate a capability token (legacy method) for Twilio Client.

    Args:
        identity: Unique identifier for the VA (username)

    Returns:
        Tuple of (success, message/token, error)
    """
    if not TWILIO_CLIENT_AVAILABLE:
        return False, "Twilio not configured", None

    try:
        # Create capability token
        capability = ClientCapabilityToken(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        # Allow outgoing calls via the TwiML App
        if TWILIO_TWIML_APP_SID:
            capability.allow_client_outgoing(TWILIO_TWIML_APP_SID)

        # Generate token (valid for 1 hour)
        token = capability.to_jwt()

        logger.info(f"Generated capability token for: {identity}")
        return True, token, None

    except Exception as e:
        logger.error(f"Error generating capability token: {e}")
        return False, str(e), None


def create_outbound_twiml(to_number: str, caller_id: str = None, lead_name: str = "", lead_address: str = "") -> str:
    """
    Create TwiML for outbound browser call.

    Args:
        to_number: Phone number to call
        caller_id: Caller ID to display (your Twilio number)
        lead_name: Name of the lead (for whisper)
        lead_address: Address of the property

    Returns:
        TwiML XML string
    """
    response = VoiceResponse()

    # Brief whisper to VA before connecting
    if lead_name or lead_address:
        whisper = f"Calling {lead_name}" if lead_name else "Calling lead"
        if lead_address:
            whisper += f" at {lead_address}"
        response.say(whisper, voice='alice')

    # Dial the lead
    dial = Dial(
        caller_id=caller_id or TWILIO_PHONE_NUMBER,
        timeout=30,
        action='/api/call-status',  # Webhook for call completion
        record='record-from-answer'  # Optional: record calls
    )
    dial.number(to_number)
    response.append(dial)

    # If call fails or ends
    response.say("The call has ended. Goodbye.", voice='alice')

    return str(response)


def clean_phone_for_browser(phone: str) -> Optional[str]:
    """
    Clean and format phone number to E.164 format.

    Args:
        phone: Raw phone number string

    Returns:
        Formatted phone number or None if invalid
    """
    if not phone:
        return None

    # Remove all non-digit characters except +
    clean = ''.join(c for c in str(phone) if c.isdigit() or c == '+')

    # Extract digits only
    digits = ''.join(filter(str.isdigit, clean))

    # Handle different formats
    if len(digits) == 10:
        # US number without country code
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        # US number with country code
        return f"+{digits}"
    elif len(digits) > 10:
        # International number
        if clean.startswith('+'):
            return clean
        return f"+{digits}"
    else:
        # Too short, invalid
        return None


def get_twiml_app_info() -> dict:
    """Get information about the TwiML App configuration."""
    return {
        'configured': bool(TWILIO_TWIML_APP_SID),
        'twiml_app_sid': TWILIO_TWIML_APP_SID[:10] + '...' if TWILIO_TWIML_APP_SID else None,
        'phone_number': TWILIO_PHONE_NUMBER,
        'api_key_configured': bool(TWILIO_API_KEY and TWILIO_API_SECRET)
    }


# HTML template for the browser dialer
BROWSER_DIALER_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <title>Aerial Leads - Browser Dialer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://sdk.twilio.com/js/client/releases/1.14.0/twilio.min.js"></script>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .dialer-container {
            background: white;
            border-radius: 20px;
            padding: 30px;
            max-width: 400px;
            width: 100%;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
        }
        .dialer-header {
            text-align: center;
            margin-bottom: 20px;
        }
        .dialer-header h1 {
            font-size: 1.5rem;
            color: #1a1a2e;
        }
        .dialer-header .status {
            font-size: 0.9rem;
            padding: 5px 15px;
            border-radius: 20px;
            display: inline-block;
            margin-top: 10px;
        }
        .status.ready { background: #d4edda; color: #155724; }
        .status.connecting { background: #fff3cd; color: #856404; }
        .status.on-call { background: #cce5ff; color: #004085; }
        .status.error { background: #f8d7da; color: #721c24; }

        .lead-info {
            background: #f8f9fa;
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
        }
        .lead-info h3 { font-size: 1rem; color: #1a1a2e; margin-bottom: 5px; }
        .lead-info p { color: #666; font-size: 0.9rem; }
        .lead-info .phone {
            font-size: 1.3rem;
            font-weight: 700;
            color: #4CAF50;
            margin-top: 10px;
        }

        .phone-input {
            width: 100%;
            padding: 15px;
            font-size: 1.2rem;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            margin-bottom: 15px;
            text-align: center;
        }
        .phone-input:focus {
            outline: none;
            border-color: #4CAF50;
        }

        .btn {
            width: 100%;
            padding: 15px;
            font-size: 1.1rem;
            font-weight: 600;
            border: none;
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .btn-call {
            background: #4CAF50;
            color: white;
        }
        .btn-call:hover { background: #45a049; }
        .btn-call:disabled { background: #ccc; cursor: not-allowed; }

        .btn-hangup {
            background: #dc3545;
            color: white;
        }
        .btn-hangup:hover { background: #c82333; }

        .call-timer {
            text-align: center;
            font-size: 2rem;
            font-weight: 700;
            color: #1a1a2e;
            margin: 20px 0;
        }

        .volume-indicator {
            height: 10px;
            background: #e0e0e0;
            border-radius: 5px;
            margin: 10px 0;
            overflow: hidden;
        }
        .volume-bar {
            height: 100%;
            background: #4CAF50;
            width: 0%;
            transition: width 0.1s;
        }

        .quick-actions {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }
        .quick-actions .btn {
            flex: 1;
            padding: 10px;
            font-size: 0.9rem;
        }

        .mute-btn { background: #6c757d; color: white; }
        .mute-btn.muted { background: #dc3545; }

        #log {
            margin-top: 20px;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 5px;
            font-size: 0.8rem;
            color: #666;
            max-height: 100px;
            overflow-y: auto;
        }
    </style>
</head>
<body>
    <div class="dialer-container">
        <div class="dialer-header">
            <h1>Browser Dialer</h1>
            <div id="status" class="status">Initializing...</div>
        </div>

        <div id="lead-info" class="lead-info" style="display:none;">
            <h3 id="lead-name">Lead Name</h3>
            <p id="lead-address">Address</p>
            <div id="lead-phone" class="phone">Phone Number</div>
        </div>

        <input type="tel" id="phone-input" class="phone-input" placeholder="Enter phone number">

        <div id="call-timer" class="call-timer" style="display:none;">00:00</div>

        <div class="volume-indicator">
            <div id="volume-bar" class="volume-bar"></div>
        </div>

        <button id="call-btn" class="btn btn-call" disabled>Call</button>
        <button id="hangup-btn" class="btn btn-hangup" style="display:none;">Hang Up</button>

        <div class="quick-actions" style="display:none;" id="call-actions">
            <button id="mute-btn" class="btn mute-btn">Mute</button>
        </div>

        <div id="log"></div>
    </div>

    <script>
        // Configuration passed from server
        const config = {
            token: '{{TOKEN}}',
            leadName: '{{LEAD_NAME}}',
            leadAddress: '{{LEAD_ADDRESS}}',
            leadPhone: '{{LEAD_PHONE}}'
        };

        let device = null;
        let activeCall = null;
        let callStartTime = null;
        let timerInterval = null;
        let isMuted = false;

        // UI Elements
        const statusEl = document.getElementById('status');
        const phoneInput = document.getElementById('phone-input');
        const callBtn = document.getElementById('call-btn');
        const hangupBtn = document.getElementById('hangup-btn');
        const callTimer = document.getElementById('call-timer');
        const callActions = document.getElementById('call-actions');
        const muteBtn = document.getElementById('mute-btn');
        const volumeBar = document.getElementById('volume-bar');
        const logEl = document.getElementById('log');
        const leadInfo = document.getElementById('lead-info');

        function log(msg) {
            console.log(msg);
            logEl.innerHTML = new Date().toLocaleTimeString() + ': ' + msg + '<br>' + logEl.innerHTML;
        }

        function setStatus(text, className) {
            statusEl.textContent = text;
            statusEl.className = 'status ' + className;
        }

        function formatTime(seconds) {
            const mins = Math.floor(seconds / 60);
            const secs = seconds % 60;
            return String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
        }

        function startTimer() {
            callStartTime = Date.now();
            timerInterval = setInterval(() => {
                const elapsed = Math.floor((Date.now() - callStartTime) / 1000);
                callTimer.textContent = formatTime(elapsed);
            }, 1000);
        }

        function stopTimer() {
            if (timerInterval) {
                clearInterval(timerInterval);
                timerInterval = null;
            }
        }

        // Initialize Twilio Device
        async function initDevice() {
            try {
                log('Initializing Twilio Device...');

                device = new Twilio.Device(config.token, {
                    codecPreferences: ['opus', 'pcmu'],
                    fakeLocalDTMF: true,
                    enableRingingState: true
                });

                device.on('ready', () => {
                    log('Device ready');
                    setStatus('Ready to call', 'ready');
                    callBtn.disabled = false;
                });

                device.on('error', (error) => {
                    log('Error: ' + error.message);
                    setStatus('Error: ' + error.message, 'error');
                });

                device.on('connect', (conn) => {
                    log('Call connected');
                    activeCall = conn;
                    setStatus('On Call', 'on-call');
                    callBtn.style.display = 'none';
                    hangupBtn.style.display = 'block';
                    callTimer.style.display = 'block';
                    callActions.style.display = 'flex';
                    startTimer();

                    // Volume monitoring
                    conn.on('volume', (inputVolume, outputVolume) => {
                        volumeBar.style.width = (inputVolume * 100) + '%';
                    });
                });

                device.on('disconnect', () => {
                    log('Call ended');
                    activeCall = null;
                    setStatus('Call ended', 'ready');
                    callBtn.style.display = 'block';
                    hangupBtn.style.display = 'none';
                    callActions.style.display = 'none';
                    stopTimer();

                    // Notify parent window (Streamlit) that call ended
                    if (window.parent) {
                        window.parent.postMessage({type: 'call_ended', duration: callTimer.textContent}, '*');
                    }
                });

                device.on('offline', () => {
                    log('Device offline');
                    setStatus('Offline - check connection', 'error');
                    callBtn.disabled = true;
                });

            } catch (err) {
                log('Init error: ' + err.message);
                setStatus('Failed to initialize', 'error');
            }
        }

        // Make call
        function makeCall() {
            const phoneNumber = phoneInput.value.trim();
            if (!phoneNumber) {
                alert('Please enter a phone number');
                return;
            }

            log('Calling ' + phoneNumber);
            setStatus('Connecting...', 'connecting');

            // Connect with parameters that will be sent to TwiML App
            device.connect({
                To: phoneNumber,
                LeadName: config.leadName || '',
                LeadAddress: config.leadAddress || ''
            });
        }

        // Hang up
        function hangUp() {
            if (activeCall) {
                activeCall.disconnect();
            }
            device.disconnectAll();
        }

        // Toggle mute
        function toggleMute() {
            if (activeCall) {
                isMuted = !isMuted;
                activeCall.mute(isMuted);
                muteBtn.textContent = isMuted ? 'Unmute' : 'Mute';
                muteBtn.classList.toggle('muted', isMuted);
            }
        }

        // Event listeners
        callBtn.addEventListener('click', makeCall);
        hangupBtn.addEventListener('click', hangUp);
        muteBtn.addEventListener('click', toggleMute);

        phoneInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !callBtn.disabled) {
                makeCall();
            }
        });

        // Pre-fill lead info if provided
        if (config.leadPhone) {
            phoneInput.value = config.leadPhone;
            leadInfo.style.display = 'block';
            document.getElementById('lead-name').textContent = config.leadName || 'Unknown';
            document.getElementById('lead-address').textContent = config.leadAddress || '';
            document.getElementById('lead-phone').textContent = config.leadPhone;
        }

        // Initialize on load
        if (config.token && config.token !== '{{TOKEN}}') {
            initDevice();
        } else {
            setStatus('No token - contact admin', 'error');
            log('Token not provided');
        }
    </script>
</body>
</html>
'''


def get_dialer_html(token: str, lead_name: str = "", lead_address: str = "", lead_phone: str = "") -> str:
    """
    Get the browser dialer HTML with token and lead info embedded.

    Args:
        token: Twilio capability/access token
        lead_name: Name of the lead
        lead_address: Property address
        lead_phone: Phone number to call

    Returns:
        HTML string for the dialer
    """
    html = BROWSER_DIALER_HTML
    html = html.replace('{{TOKEN}}', token)
    html = html.replace('{{LEAD_NAME}}', lead_name or '')
    html = html.replace('{{LEAD_ADDRESS}}', lead_address or '')
    html = html.replace('{{LEAD_PHONE}}', lead_phone or '')
    return html
