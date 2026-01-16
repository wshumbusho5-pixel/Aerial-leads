"""
Browser Dialer Component for Streamlit

Embeds the Twilio Client JavaScript SDK for browser-based calling.
"""

import streamlit.components.v1 as components


def render_dialer(token: str, phone_number: str = "", lead_info: dict = None):
    """
    Render the browser-based dialer component.

    Args:
        token: Twilio access token for this session
        phone_number: Phone number to call (optional, can be entered manually)
        lead_info: Lead information to display (optional)
    """

    lead_html = ""
    if lead_info:
        lead_html = f"""
        <div class="lead-info">
            <h4>Current Lead</h4>
            <p><strong>Name:</strong> {lead_info.get('owner_name', 'N/A')}</p>
            <p><strong>Address:</strong> {lead_info.get('address', 'N/A')}</p>
            <p><strong>Score:</strong> {lead_info.get('motivation_score', 0)}/100</p>
        </div>
        """

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://sdk.twilio.com/js/voice/2.10/twilio.min.js"></script>
        <style>
            * {{
                box-sizing: border-box;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }}

            .dialer-container {{
                padding: 20px;
                max-width: 500px;
                margin: 0 auto;
            }}

            .status-bar {{
                padding: 10px 15px;
                border-radius: 8px;
                margin-bottom: 15px;
                font-weight: 500;
            }}

            .status-ready {{
                background: #d4edda;
                color: #155724;
            }}

            .status-connecting {{
                background: #fff3cd;
                color: #856404;
            }}

            .status-oncall {{
                background: #cce5ff;
                color: #004085;
                animation: pulse 2s infinite;
            }}

            .status-error {{
                background: #f8d7da;
                color: #721c24;
            }}

            @keyframes pulse {{
                0%, 100% {{ opacity: 1; }}
                50% {{ opacity: 0.7; }}
            }}

            .phone-input {{
                width: 100%;
                padding: 15px;
                font-size: 18px;
                border: 2px solid #ddd;
                border-radius: 8px;
                margin-bottom: 15px;
                text-align: center;
            }}

            .phone-input:focus {{
                outline: none;
                border-color: #667eea;
            }}

            .btn-row {{
                display: flex;
                gap: 10px;
                margin-bottom: 15px;
            }}

            .btn {{
                flex: 1;
                padding: 15px 20px;
                font-size: 16px;
                font-weight: bold;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                transition: transform 0.1s, opacity 0.2s;
            }}

            .btn:hover {{
                transform: scale(1.02);
            }}

            .btn:disabled {{
                opacity: 0.5;
                cursor: not-allowed;
                transform: none;
            }}

            .btn-call {{
                background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                color: white;
            }}

            .btn-hangup {{
                background: linear-gradient(135deg, #dc3545 0%, #c82333 100%);
                color: white;
            }}

            .btn-mute {{
                background: linear-gradient(135deg, #6c757d 0%, #5a6268 100%);
                color: white;
            }}

            .call-timer {{
                text-align: center;
                font-size: 32px;
                font-weight: bold;
                color: #333;
                margin: 15px 0;
            }}

            .lead-info {{
                background: #f8f9fa;
                padding: 15px;
                border-radius: 8px;
                margin-bottom: 15px;
            }}

            .lead-info h4 {{
                margin: 0 0 10px 0;
                color: #667eea;
            }}

            .lead-info p {{
                margin: 5px 0;
                color: #333;
            }}

            .keypad {{
                display: grid;
                grid-template-columns: repeat(3, 1fr);
                gap: 10px;
                margin-top: 15px;
            }}

            .keypad button {{
                padding: 15px;
                font-size: 20px;
                border: 1px solid #ddd;
                border-radius: 8px;
                background: white;
                cursor: pointer;
            }}

            .keypad button:hover {{
                background: #f0f0f0;
            }}

            .volume-control {{
                margin-top: 15px;
            }}

            .volume-control label {{
                display: block;
                margin-bottom: 5px;
                color: #666;
            }}

            .volume-control input {{
                width: 100%;
            }}
        </style>
    </head>
    <body>
        <div class="dialer-container">
            <div id="status" class="status-bar status-connecting">Initializing...</div>

            {lead_html}

            <input type="tel" id="phoneNumber" class="phone-input"
                   value="{phone_number}" placeholder="+1 (614) 555-1234">

            <div class="call-timer" id="timer" style="display: none;">00:00</div>

            <div class="btn-row">
                <button id="btnCall" class="btn btn-call" disabled>
                    📞 Call
                </button>
                <button id="btnHangup" class="btn btn-hangup" disabled>
                    📵 Hang Up
                </button>
            </div>

            <div class="btn-row">
                <button id="btnMute" class="btn btn-mute" disabled>
                    🔇 Mute
                </button>
            </div>

            <div class="keypad" id="keypad" style="display: none;">
                <button onclick="sendDigit('1')">1</button>
                <button onclick="sendDigit('2')">2</button>
                <button onclick="sendDigit('3')">3</button>
                <button onclick="sendDigit('4')">4</button>
                <button onclick="sendDigit('5')">5</button>
                <button onclick="sendDigit('6')">6</button>
                <button onclick="sendDigit('7')">7</button>
                <button onclick="sendDigit('8')">8</button>
                <button onclick="sendDigit('9')">9</button>
                <button onclick="sendDigit('*')">*</button>
                <button onclick="sendDigit('0')">0</button>
                <button onclick="sendDigit('#')">#</button>
            </div>

            <div class="volume-control">
                <label>Speaker Volume</label>
                <input type="range" id="volumeSlider" min="0" max="100" value="80"
                       onchange="setVolume(this.value)">
            </div>
        </div>

        <script>
            // Elements
            const statusEl = document.getElementById('status');
            const phoneInput = document.getElementById('phoneNumber');
            const btnCall = document.getElementById('btnCall');
            const btnHangup = document.getElementById('btnHangup');
            const btnMute = document.getElementById('btnMute');
            const timerEl = document.getElementById('timer');
            const keypadEl = document.getElementById('keypad');

            // State
            let device = null;
            let activeCall = null;
            let isMuted = false;
            let timerInterval = null;
            let callStartTime = null;

            // Initialize Twilio Device (SDK 2.x)
            async function initDevice() {{
                const token = "{token}";

                if (!token) {{
                    setStatus('No token provided', 'error');
                    return;
                }}

                try {{
                    // Create device with SDK 2.x
                    device = new Twilio.Device(token, {{
                        codecPreferences: [Twilio.Device.Codec.Opus, Twilio.Device.Codec.PCMU],
                        allowIncomingWhileBusy: true,
                        logLevel: 1
                    }});

                    // SDK 2.x events
                    device.on('registered', function() {{
                        setStatus('Ready to make calls', 'ready');
                        btnCall.disabled = false;
                        console.log('Twilio Device registered');
                    }});

                    device.on('error', function(error) {{
                        console.error('Twilio error:', error);
                        setStatus('Error: ' + (error.message || error), 'error');
                    }});

                    device.on('incoming', function(call) {{
                        setStatus('Incoming call...', 'connecting');
                        activeCall = call;
                        call.accept();
                    }});

                    device.on('unregistered', function() {{
                        setStatus('Device unregistered', 'error');
                    }});

                    device.on('tokenWillExpire', function() {{
                        console.log('Token will expire soon');
                        setStatus('Token expiring - refresh page', 'error');
                    }});

                    // Register the device
                    await device.register();
                    console.log('Device registration initiated');

                }} catch (e) {{
                    setStatus('Failed to initialize: ' + e.message, 'error');
                    console.error('Init error:', e);
                }}
            }}

            function setStatus(message, type) {{
                statusEl.textContent = message;
                statusEl.className = 'status-bar status-' + type;
            }}

            async function makeCall() {{
                const number = phoneInput.value.trim();
                if (!number) {{
                    alert('Please enter a phone number');
                    return;
                }}

                if (!device) {{
                    setStatus('Device not ready', 'error');
                    return;
                }}

                setStatus('Connecting...', 'connecting');
                btnCall.disabled = true;

                try {{
                    // SDK 2.x connect with params
                    activeCall = await device.connect({{
                        params: {{ To: number }}
                    }});

                    // Set up call event handlers
                    activeCall.on('accept', function() {{
                        setStatus('On call...', 'oncall');
                        btnHangup.disabled = false;
                        btnMute.disabled = false;
                        keypadEl.style.display = 'grid';
                        startTimer();
                    }});

                    activeCall.on('disconnect', function() {{
                        setStatus('Call ended', 'ready');
                        btnCall.disabled = false;
                        btnHangup.disabled = true;
                        btnMute.disabled = true;
                        keypadEl.style.display = 'none';
                        stopTimer();
                        isMuted = false;
                        btnMute.textContent = '🔇 Mute';
                        activeCall = null;
                    }});

                    activeCall.on('error', function(error) {{
                        console.error('Call error:', error);
                        setStatus('Call error: ' + error.message, 'error');
                        btnCall.disabled = false;
                    }});

                    activeCall.on('ringing', function() {{
                        setStatus('Ringing...', 'connecting');
                    }});

                }} catch (e) {{
                    console.error('Connect error:', e);
                    setStatus('Failed to connect: ' + e.message, 'error');
                    btnCall.disabled = false;
                }}
            }}

            function hangUp() {{
                if (activeCall) {{
                    activeCall.disconnect();
                }}
            }}

            function toggleMute() {{
                if (activeCall) {{
                    isMuted = !isMuted;
                    activeCall.mute(isMuted);
                    btnMute.textContent = isMuted ? '🔊 Unmute' : '🔇 Mute';
                }}
            }}

            function sendDigit(digit) {{
                if (activeCall) {{
                    activeCall.sendDigits(digit);
                }}
            }}

            function setVolume(value) {{
                if (device) {{
                    device.audio.speakerDevices.set('default').then(() => {{
                        // Volume is 0-1, slider is 0-100
                        // Note: Actual volume control may vary by browser
                    }});
                }}
            }}

            function startTimer() {{
                callStartTime = new Date();
                timerEl.style.display = 'block';
                timerEl.textContent = '00:00';

                timerInterval = setInterval(function() {{
                    const elapsed = Math.floor((new Date() - callStartTime) / 1000);
                    const minutes = Math.floor(elapsed / 60).toString().padStart(2, '0');
                    const seconds = (elapsed % 60).toString().padStart(2, '0');
                    timerEl.textContent = minutes + ':' + seconds;
                }}, 1000);
            }}

            function stopTimer() {{
                if (timerInterval) {{
                    clearInterval(timerInterval);
                    timerInterval = null;
                }}
                timerEl.style.display = 'none';
            }}

            // Event listeners
            btnCall.addEventListener('click', makeCall);
            btnHangup.addEventListener('click', hangUp);
            btnMute.addEventListener('click', toggleMute);

            // Allow Enter key to call
            phoneInput.addEventListener('keypress', function(e) {{
                if (e.key === 'Enter') {{
                    makeCall();
                }}
            }});

            // Initialize on load
            initDevice();
        </script>
    </body>
    </html>
    """

    components.html(html_code, height=650, scrolling=False)


def get_access_token(identity: str = "agent") -> str:
    """
    Generate an access token for the browser client.

    Args:
        identity: Unique identifier for this client session

    Returns:
        JWT access token string
    """
    import os
    from twilio.jwt.access_token import AccessToken
    from twilio.jwt.access_token.grants import VoiceGrant
    from dotenv import load_dotenv

    load_dotenv()

    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    api_key = os.getenv('TWILIO_API_KEY')
    api_secret = os.getenv('TWILIO_API_SECRET')
    twiml_app_sid = os.getenv('TWIML_APP_SID')

    if not all([account_sid, api_key, api_secret, twiml_app_sid]):
        raise ValueError("Missing Twilio credentials. Check your .env file.")

    # Create access token
    token = AccessToken(
        account_sid,
        api_key,
        api_secret,
        identity=identity,
        ttl=3600
    )

    # Add voice grant
    voice_grant = VoiceGrant(
        outgoing_application_sid=twiml_app_sid,
        incoming_allow=True
    )
    token.add_grant(voice_grant)

    return token.to_jwt()
