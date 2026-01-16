"""
Setup Twilio Function for Voice Webhooks

This creates a serverless Twilio Function to handle voice webhooks,
eliminating the need for ngrok or a separate server.
"""

import os
from twilio.rest import Client
from dotenv import load_dotenv

load_dotenv()

# Twilio credentials
ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWIML_APP_SID = os.getenv('TWIML_APP_SID')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# The TwiML Function code
VOICE_FUNCTION_CODE = '''
exports.handler = function(context, event, callback) {
    const twiml = new Twilio.twiml.VoiceResponse();

    // Get the number to dial
    const toNumber = event.To || '';
    const fromNumber = context.TWILIO_PHONE_NUMBER || event.From;

    if (toNumber && (toNumber.startsWith('+') || /^\\d/.test(toNumber))) {
        // Dial the phone number
        const dial = twiml.dial({
            callerId: fromNumber,
            record: 'record-from-answer',
            timeout: 30
        });
        dial.number(toNumber);
    } else if (toNumber) {
        // Connect to a client
        const dial = twiml.dial();
        dial.client(toNumber);
    } else {
        twiml.say('No destination number provided.');
    }

    callback(null, twiml);
};
'''


def setup_twilio_function():
    """Create or update Twilio Function for voice handling."""
    client = Client(ACCOUNT_SID, AUTH_TOKEN)

    print("Setting up Twilio Functions...")
    print("=" * 50)

    # Check for existing service
    services = client.serverless.services.list()
    service = None

    for s in services:
        if s.friendly_name == 'aerial-leads-voice':
            service = s
            print(f"Found existing service: {s.sid}")
            break

    if not service:
        # Create new service
        print("Creating new service...")
        service = client.serverless.services.create(
            friendly_name='aerial-leads-voice',
            unique_name='aerial-leads-voice'
        )
        print(f"Created service: {service.sid}")

    # Check for existing environment
    environments = client.serverless.services(service.sid).environments.list()
    env = environments[0] if environments else None

    if not env:
        print("Creating environment...")
        env = client.serverless.services(service.sid).environments.create(
            unique_name='production',
            domain_suffix='aerial'
        )
        print(f"Created environment: {env.sid}")

    # Create or update the function
    functions = client.serverless.services(service.sid).functions.list()
    func = None

    for f in functions:
        if f.friendly_name == 'voice':
            func = f
            print(f"Found existing function: {f.sid}")
            break

    if not func:
        print("Creating function...")
        func = client.serverless.services(service.sid).functions.create(
            friendly_name='voice'
        )
        print(f"Created function: {func.sid}")

    # Create a new version with our code
    print("Uploading function code...")
    version = client.serverless.services(service.sid).functions(func.sid).function_versions.create(
        path='/voice',
        visibility='public',
        content=VOICE_FUNCTION_CODE,
        content_type='application/javascript'
    )
    print(f"Created version: {version.sid}")

    # Build and deploy
    print("Building and deploying...")
    build = client.serverless.services(service.sid).builds.create(
        function_versions=[version.sid]
    )
    print(f"Build created: {build.sid}")

    # Wait for build to complete
    import time
    for _ in range(30):
        build = client.serverless.services(service.sid).builds(build.sid).fetch()
        if build.status == 'completed':
            break
        elif build.status == 'failed':
            print(f"Build failed!")
            return None
        print(f"Build status: {build.status}...")
        time.sleep(2)

    # Deploy to environment
    deployment = client.serverless.services(service.sid).environments(env.sid).deployments.create(
        build_sid=build.sid
    )
    print(f"Deployed: {deployment.sid}")

    # Get the URL
    voice_url = f"https://{env.domain_name}/voice"
    print(f"\nVoice URL: {voice_url}")

    # Update TwiML App
    print(f"\nUpdating TwiML App {TWIML_APP_SID}...")
    app = client.applications(TWIML_APP_SID).update(
        voice_url=voice_url,
        voice_method='POST'
    )
    print(f"TwiML App updated with voice URL!")

    return voice_url


def simple_twiml_update():
    """
    Simpler approach: Use a TwiML Bin or direct TwiML.
    This doesn't require Twilio Functions.
    """
    client = Client(ACCOUNT_SID, AUTH_TOKEN)

    print("Setting up simple TwiML solution...")
    print("=" * 50)

    # For outbound calls from browser, we need the TwiML App to handle the connection
    # The simplest solution is to use inline TwiML in the browser client

    # Update TwiML App to use a TwiML bin or webhook
    # For now, let's create a TwiML bin

    twiml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Dial callerId="{TWILIO_PHONE_NUMBER}" record="record-from-answer">
        <Number>{{{{To}}}}</Number>
    </Dial>
</Response>'''

    print("Creating TwiML Bin...")
    # Note: TwiML Bins don't support dynamic parameters like {{To}}
    # So we need to use Twilio Functions or a webhook server

    print("\nFor browser-based calling, you need one of these options:")
    print("1. Run the voice server locally with ngrok")
    print("2. Deploy the voice server to a cloud provider")
    print("3. Use Twilio Studio for visual call flows")
    print("")
    print("For quick testing, let's use option 1:")
    print("  1. Sign up at https://dashboard.ngrok.com/signup")
    print("  2. Get your authtoken")
    print("  3. Run: ngrok config add-authtoken YOUR_TOKEN")
    print("  4. Run: ./start_dialer.sh")


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == '--simple':
        simple_twiml_update()
    else:
        try:
            setup_twilio_function()
        except Exception as e:
            print(f"Error setting up Twilio Function: {e}")
            print("\nFalling back to simple instructions...")
            simple_twiml_update()
