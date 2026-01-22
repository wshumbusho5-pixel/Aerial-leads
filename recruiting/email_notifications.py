"""
Email Notifications for VA Recruiting
Uses SendGrid to send email notifications.
"""

import os
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# SendGrid setup
SENDGRID_AVAILABLE = False
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content
    SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
    if SENDGRID_API_KEY:
        SENDGRID_AVAILABLE = True
except ImportError:
    logger.warning("SendGrid not installed. Run: pip install sendgrid")

FROM_EMAIL = os.environ.get('SENDGRID_FROM_EMAIL', 'admin@areliga.com')
FROM_NAME = os.environ.get('SENDGRID_FROM_NAME', 'Orteza groups')


def send_email(to_email: str, subject: str, html_content: str) -> Tuple[bool, str]:
    """
    Send an email using SendGrid.

    Returns:
        Tuple of (success, message)
    """
    if not SENDGRID_AVAILABLE:
        logger.warning("SendGrid not available, email not sent")
        return False, "Email service not configured"

    try:
        message = Mail(
            from_email=(FROM_EMAIL, FROM_NAME),
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )

        sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        response = sg.send(message)

        if response.status_code in [200, 201, 202]:
            logger.info(f"Email sent successfully to {to_email}")
            return True, "Email sent successfully"
        else:
            logger.error(f"SendGrid returned status {response.status_code}")
            return False, f"Failed to send email: status {response.status_code}"

    except Exception as e:
        logger.error(f"Error sending email: {e}")
        return False, f"Error sending email: {str(e)}"


def send_script_assignment_email(
    applicant_name: str,
    applicant_email: str,
    script_name: str,
    recording_url: str
) -> Tuple[bool, str]:
    """
    Send email notification when a script is assigned to an applicant.
    """
    subject = "Your Video Interview Script - Lifeline Home Buyers"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .button {{ display: inline-block; background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; margin: 20px 0; font-weight: bold; }}
            .button:hover {{ background: #059669; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
            .highlight {{ background: #e0f2fe; padding: 15px; border-radius: 8px; margin: 15px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Orteza groups</h1>
                <p>Lifeline Home Buyers - VA Application</p>
            </div>
            <div class="content">
                <h2>Hello {applicant_name}!</h2>

                <p>Great news! Your application has been reviewed and you've been selected to move forward to the video interview stage.</p>

                <div class="highlight">
                    <strong>Assigned Script:</strong> {script_name}
                </div>

                <p>Here's what you need to do:</p>
                <ol>
                    <li>Click the button below to access your script and recording portal</li>
                    <li>Review the script carefully</li>
                    <li>Record yourself reading the script naturally (60-90 seconds)</li>
                    <li>Upload your video</li>
                </ol>

                <p style="text-align: center;">
                    <a href="{recording_url}" class="button">Access Your Script & Record Video</a>
                </p>

                <p><strong>Tips for a great video:</strong></p>
                <ul>
                    <li>Find a quiet place with good lighting</li>
                    <li>Speak clearly and at a natural pace</li>
                    <li>Show enthusiasm - imagine you're on a real call!</li>
                    <li>It's okay to have the script visible, but try to sound natural</li>
                </ul>

                <p>Once you submit your video, our team will review it within 48 hours and get back to you with next steps.</p>

                <p>Good luck!</p>

                <p>Best regards,<br>
                <strong>The Lifeline Home Buyers Team</strong></p>
            </div>
            <div class="footer">
                <p>Orteza groups | Lifeline Home Buyers<br>
                Columbus, Ohio</p>
                <p>This email was sent because you applied for a VA position with us.</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(applicant_email, subject, html_content)


def send_video_approved_email(
    applicant_name: str,
    applicant_email: str
) -> Tuple[bool, str]:
    """
    Send email notification when video is approved.
    """
    subject = "Congratulations! Your Video Has Been Approved - Lifeline Home Buyers"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #059669 0%, #10b981 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
            .success {{ background: #d1fae5; padding: 20px; border-radius: 8px; text-align: center; margin: 20px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Congratulations!</h1>
            </div>
            <div class="content">
                <h2>Hello {applicant_name}!</h2>

                <div class="success">
                    <h3>Your video interview has been approved!</h3>
                </div>

                <p>We were impressed with your video submission and would like to move forward with your application.</p>

                <p><strong>Next Steps:</strong></p>
                <p>A member of our team will reach out to you shortly to schedule a personal interview. Please keep an eye on your email and phone.</p>

                <p>Thank you for your interest in joining Lifeline Home Buyers!</p>

                <p>Best regards,<br>
                <strong>The Lifeline Home Buyers Team</strong></p>
            </div>
            <div class="footer">
                <p>Orteza groups | Lifeline Home Buyers<br>
                Columbus, Ohio</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(applicant_email, subject, html_content)


def send_application_received_email(
    applicant_name: str,
    applicant_email: str
) -> Tuple[bool, str]:
    """
    Send email confirmation when application is received.
    """
    subject = "Application Received - Lifeline Home Buyers"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
            .info {{ background: #e0f2fe; padding: 15px; border-radius: 8px; margin: 15px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Orteza groups</h1>
                <p>Application Received</p>
            </div>
            <div class="content">
                <h2>Hello {applicant_name}!</h2>

                <p>Thank you for applying to join the Lifeline Home Buyers team as a Virtual Assistant!</p>

                <div class="info">
                    <p><strong>What happens next?</strong></p>
                    <p>Our team will review your application within 48 hours. If you're selected to move forward, we'll send you a script for a short video interview.</p>
                </div>

                <p>In the meantime, please make sure to check your email (including spam folder) for updates from us.</p>

                <p>Best regards,<br>
                <strong>The Lifeline Home Buyers Team</strong></p>
            </div>
            <div class="footer">
                <p>Orteza groups | Lifeline Home Buyers<br>
                Columbus, Ohio</p>
            </div>
        </div>
    </body>
    </html>
    """

    return send_email(applicant_email, subject, html_content)
