"""
Voice Server for Lifeline Home Buyers Dialer

Flask server that handles:
1. Twilio webhook callbacks (TwiML responses)
2. Access token generation for browser clients
3. Call status updates

Run with: python -m dialer.voice_server
"""

import os
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse, Dial
from dotenv import load_dotenv
import logging

load_dotenv()

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests from Streamlit

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
TWILIO_API_KEY = os.getenv('TWILIO_API_KEY', '')
TWILIO_API_SECRET = os.getenv('TWILIO_API_SECRET', '')
TWIML_APP_SID = os.getenv('TWIML_APP_SID', '')


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok', 'service': 'aerial-leads-voice'})


@app.route('/token', methods=['GET', 'POST'])
def get_token():
    """
    Generate an access token for Twilio Client (browser calling).

    Query params:
        identity: The VA's identifier (default: 'agent')
    """
    identity = request.args.get('identity', 'agent')

    if not TWILIO_API_KEY or not TWILIO_API_SECRET:
        return jsonify({'error': 'API Key and Secret not configured'}), 500

    if not TWIML_APP_SID:
        return jsonify({'error': 'TwiML App SID not configured'}), 500

    # Create access token
    token = AccessToken(
        TWILIO_ACCOUNT_SID,
        TWILIO_API_KEY,
        TWILIO_API_SECRET,
        identity=identity,
        ttl=3600  # Token valid for 1 hour
    )

    # Create Voice grant
    voice_grant = VoiceGrant(
        outgoing_application_sid=TWIML_APP_SID,
        incoming_allow=True  # Allow incoming calls to this client
    )

    token.add_grant(voice_grant)

    return jsonify({
        'token': token.to_jwt(),
        'identity': identity
    })


@app.route('/voice', methods=['POST'])
def voice():
    """
    Handle outbound calls from browser client.

    This is called by Twilio when the browser initiates a call.
    Returns TwiML instructions for connecting the call.
    """
    # Get the number to call from the request
    to_number = request.form.get('To', '')
    from_number = request.form.get('From', TWILIO_PHONE_NUMBER)
    caller_id = request.form.get('CallerId', TWILIO_PHONE_NUMBER)

    logger.info(f"Outbound call request: To={to_number}, From={from_number}")

    response = VoiceResponse()

    if to_number:
        # Clean the number
        to_number = to_number.strip()

        # If it's a phone number, dial it
        if to_number.startswith('+') or to_number[0].isdigit():
            dial = Dial(
                caller_id=caller_id or TWILIO_PHONE_NUMBER,
                record='record-from-answer',  # Record the call
                timeout=30,
                action='/call-complete'  # Webhook when call ends
            )
            dial.number(to_number)
            response.append(dial)
        else:
            # It's a client identifier, connect to that client
            dial = Dial()
            dial.client(to_number)
            response.append(dial)
    else:
        response.say("No destination number provided.")

    return Response(str(response), mimetype='text/xml')


@app.route('/call-complete', methods=['POST'])
def call_complete():
    """
    Called when a call completes.
    Used for logging and analytics.
    """
    call_sid = request.form.get('CallSid', '')
    call_status = request.form.get('CallStatus', '')
    call_duration = request.form.get('CallDuration', '0')
    recording_url = request.form.get('RecordingUrl', '')

    logger.info(f"Call complete: SID={call_sid}, Status={call_status}, Duration={call_duration}s")

    if recording_url:
        logger.info(f"Recording available: {recording_url}")

    # Return empty TwiML
    response = VoiceResponse()
    return Response(str(response), mimetype='text/xml')


@app.route('/incoming', methods=['POST'])
def incoming():
    """
    Handle incoming calls to our Twilio number.
    Forwards to personal phone with original caller ID preserved.
    Also tries browser client first.
    """
    from_number = request.form.get('From', '')
    PERSONAL_PHONE = os.getenv('PERSONAL_PHONE_NUMBER', '')

    logger.info(f"Incoming call from: {from_number}")

    response = VoiceResponse()
    response.say("Welcome to Lifeline Home Buyers. Connecting you now.", voice='alice')

    # Forward to personal phone with the ORIGINAL caller's number as caller ID
    # This way you see who's actually calling you
    if PERSONAL_PHONE:
        dial = Dial(
            caller_id=from_number,  # Show the ORIGINAL caller's number
            timeout=20,
            action='/incoming-fallback'
        )
        dial.number(PERSONAL_PHONE)
        response.append(dial)
    else:
        # Fallback to browser client
        dial = Dial()
        dial.client('agent')
        response.append(dial)

    return Response(str(response), mimetype='text/xml')


@app.route('/incoming-fallback', methods=['POST'])
def incoming_fallback():
    """
    Called if the personal phone doesn't answer.
    Sends to voicemail or browser client.
    """
    dial_status = request.form.get('DialCallStatus', '')
    from_number = request.form.get('From', '')

    logger.info(f"Incoming fallback: status={dial_status}, from={from_number}")

    response = VoiceResponse()

    if dial_status in ('no-answer', 'busy', 'failed'):
        response.say("Sorry, no one is available right now. Please leave a message after the beep.", voice='alice')
        response.record(max_length=120, transcribe=True)
        response.say("Thank you. We will get back to you soon.")

    return Response(str(response), mimetype='text/xml')


@app.route('/status', methods=['POST'])
def call_status():
    """
    Receive call status updates from Twilio.
    """
    call_sid = request.form.get('CallSid', '')
    call_status = request.form.get('CallStatus', '')

    logger.info(f"Call status update: SID={call_sid}, Status={call_status}")

    return jsonify({'received': True})


def create_twiml_app():
    """
    Create or update the TwiML App in Twilio.
    Run this once to set up the app.
    """
    from twilio.rest import Client

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    # Check if app already exists
    apps = client.applications.list(friendly_name='Lifeline Home Buyers Dialer')

    if apps:
        app = apps[0]
        print(f"TwiML App already exists: {app.sid}")
        return app.sid

    # Create new app (URLs will be updated later when we have ngrok/production URL)
    app = client.applications.create(
        friendly_name='Lifeline Home Buyers Dialer',
        voice_method='POST',
    )

    print(f"Created TwiML App: {app.sid}")
    print("Add this to your .env file:")
    print(f"TWIML_APP_SID={app.sid}")

    return app.sid


def create_api_key():
    """
    Create an API Key for generating access tokens.
    Run this once to get credentials.
    """
    from twilio.rest import Client

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    # Create a new API key
    key = client.new_keys.create(friendly_name='Lifeline Home Buyers Voice')

    print("API Key created!")
    print("Add these to your .env file:")
    print(f"TWILIO_API_KEY={key.sid}")
    print(f"TWILIO_API_SECRET={key.secret}")
    print("")
    print("IMPORTANT: Save the secret now! It won't be shown again.")

    return key.sid, key.secret


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == 'setup':
            print("Setting up Twilio Voice...")
            print("=" * 50)

            print("\n1. Creating API Key...")
            api_key, api_secret = create_api_key()

            print("\n2. Creating TwiML App...")
            app_sid = create_twiml_app()

            print("\n" + "=" * 50)
            print("Setup complete! Add these to your .env file:")
            print(f"TWILIO_API_KEY={api_key}")
            print(f"TWILIO_API_SECRET={api_secret}")
            print(f"TWIML_APP_SID={app_sid}")

        elif sys.argv[1] == 'create-key':
            create_api_key()

        elif sys.argv[1] == 'create-app':
            create_twiml_app()
    else:
        # Run the server
        print("Starting Lifeline Home Buyers Voice Server...")
        print("Endpoints:")
        print("  GET  /health - Health check")
        print("  GET  /token  - Get access token")
        print("  POST /voice  - Handle outbound calls")
        print("")
        app.run(host='0.0.0.0', port=5001, debug=True)
