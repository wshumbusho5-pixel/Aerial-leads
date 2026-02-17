"""
Email Notifications for VA Recruiting
Uses SendGrid to send email notifications.
"""

import os
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# SendGrid setup - check at runtime for flexibility
SENDGRID_INSTALLED = False
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content
    SENDGRID_INSTALLED = True
except ImportError:
    logger.warning("SendGrid not installed. Run: pip install sendgrid")

def is_sendgrid_available():
    """Check if SendGrid is available at runtime."""
    return SENDGRID_INSTALLED and bool(os.environ.get('SENDGRID_API_KEY'))

# For backward compatibility
SENDGRID_AVAILABLE = is_sendgrid_available()

def get_from_email():
    return os.environ.get('SENDGRID_FROM_EMAIL', 'admin@areliga.com')

def get_from_name():
    return os.environ.get('SENDGRID_FROM_NAME', 'Orteza groups')


def send_email(to_email: str, subject: str, html_content: str) -> Tuple[bool, str]:
    """
    Send an email using SendGrid.

    Returns:
        Tuple of (success, message)
    """
    # Check at runtime if SendGrid is available
    if not is_sendgrid_available():
        logger.warning("SendGrid not available, email not sent")
        return False, "Email service not configured"

    try:
        from_email = get_from_email()
        from_name = get_from_name()

        message = Mail(
            from_email=(from_email, from_name),
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


def send_hired_email(
    applicant_name: str,
    applicant_email: str
) -> Tuple[bool, str]:
    """
    Send email notification when applicant is hired.
    """
    subject = "Welcome to the Team - Lifeline Home Buyers"

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
            .celebration {{ background: #d1fae5; padding: 25px; border-radius: 12px; text-align: center; margin: 20px 0; border: 2px solid #10b981; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Congratulations!</h1>
            </div>
            <div class="content">
                <h2>Hello {applicant_name},</h2>
                <div class="celebration">
                    <h2 style="color: #065f46; margin: 0;">You're Hired!</h2>
                    <p style="color: #047857;">Welcome to the Lifeline Home Buyers team!</p>
                </div>
                <p>We're thrilled to welcome you as a Virtual Assistant. Our team will reach out within 24-48 hours with onboarding details.</p>
                <p>Best regards,<br><strong>The Lifeline Home Buyers Team</strong></p>
            </div>
            <div class="footer">
                <p>Lifeline Home Buyers</p>
            </div>
        </div>
    </body>
    </html>
    """
    return send_email(applicant_email, subject, html_content)


def send_rejected_email(
    applicant_name: str,
    applicant_email: str
) -> Tuple[bool, str]:
    """
    Send email notification when applicant is rejected.
    """
    subject = "Application Update - Lifeline Home Buyers"

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
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Application Update</h1>
            </div>
            <div class="content">
                <h2>Hello {applicant_name},</h2>
                <p>Thank you for applying for the Virtual Assistant position at Lifeline Home Buyers.</p>
                <p>After careful consideration, we have decided to move forward with other candidates. This does not reflect on your abilities - we received many strong applications.</p>
                <p>We encourage you to apply again in the future as new positions open up.</p>
                <p>Best wishes,<br><strong>The Lifeline Home Buyers Team</strong></p>
            </div>
            <div class="footer">
                <p>Lifeline Home Buyers</p>
            </div>
        </div>
    </body>
    </html>
    """
    return send_email(applicant_email, subject, html_content)


def send_interview_scheduled_email(
    applicant_name: str,
    applicant_email: str,
    interview_link: str
) -> Tuple[bool, str]:
    """
    Send email with interview scheduling link.
    """
    subject = "Schedule Your Interview - Lifeline Home Buyers"

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
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Video Approved!</h1>
                <p>Time to Schedule Your Interview</p>
            </div>
            <div class="content">
                <h2>Hello {applicant_name},</h2>
                <p>Great news! Your video interview has been approved. The next step is a live interview with our team.</p>
                <p style="text-align: center;">
                    <a href="{interview_link}" class="button">Schedule Your Interview</a>
                </p>
                <p>Please select a time that works best for you. The interview will be approximately 15-20 minutes.</p>
                <p>Best regards,<br><strong>The Lifeline Home Buyers Team</strong></p>
            </div>
            <div class="footer">
                <p>Lifeline Home Buyers</p>
            </div>
        </div>
    </body>
    </html>
    """
    return send_email(applicant_email, subject, html_content)


def send_welcome_pas_email(
    applicant_name: str,
    applicant_email: str,
    start_date: str = "TBD",
    portal_url: str = "",
    username: str = "",
    password: str = ""
) -> Tuple[bool, str]:
    """
    Send welcome email to newly hired PAS (Property Acquisition Specialist) team member.
    """
    subject = "Welcome to PAS Team - Lifeline Home Buyers"

    # Build credentials section if provided
    credentials_html = ""
    if username and password:
        credentials_html = f"""
                <div class="info-box" style="background: #d1fae5; border: 2px solid #10b981;">
                    <h3 style="margin-top: 0;">Your VA Portal Credentials:</h3>
                    <p><strong>Portal URL:</strong> {portal_url if portal_url else 'Will be provided'}</p>
                    <p><strong>Username:</strong> {username}</p>
                    <p><strong>Password:</strong> {password}</p>
                    <p style="font-size: 12px; color: #666;">Please change your password after first login.</p>
                </div>
        """

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
            .role-box {{ background: linear-gradient(135deg, #059669 0%, #10b981 100%); color: white; padding: 20px; border-radius: 10px; margin: 20px 0; }}
            .info-box {{ background: #e0f2fe; padding: 15px; border-radius: 8px; margin: 15px 0; }}
            .metrics-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            .metrics-table th, .metrics-table td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
            .metrics-table th {{ background: #1e3a5f; color: white; }}
            ul {{ padding-left: 20px; }}
            li {{ margin: 8px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Welcome to the PAS Team!</h1>
                <p>Property Acquisition Specialist</p>
            </div>
            <div class="content">
                <h2>Hello {applicant_name},</h2>

                <div class="role-box">
                    <h3 style="margin-top: 0;">Your Role: Property Acquisition Specialist (PAS)</h3>
                    <p>You'll be the first point of contact with motivated sellers who may want to sell their properties.</p>
                </div>

                {credentials_html}

                <h3>Your Responsibilities:</h3>
                <ul>
                    <li>Call motivated property owners (distressed sellers, probate, tax delinquent, etc.)</li>
                    <li>Build rapport and identify their motivation to sell</li>
                    <li>Gather property information</li>
                    <li>Set appointments for property walkthroughs</li>
                    <li>Follow up with leads who need more time</li>
                </ul>

                <h3>Daily Expectations:</h3>
                <table class="metrics-table">
                    <tr><th>Metric</th><th>Daily Target</th></tr>
                    <tr><td>Calls Made</td><td>100+</td></tr>
                    <tr><td>Conversations</td><td>20+</td></tr>
                    <tr><td>Leads Qualified</td><td>5+</td></tr>
                    <tr><td>Appointments Set</td><td>1-2</td></tr>
                </table>

                <div class="info-box">
                    <h3 style="margin-top: 0;">Compensation:</h3>
                    <p><strong>Base:</strong> UGX 500,000/month</p>
                    <p><strong>Bonuses:</strong> Top 2 performers each month receive performance bonuses</p>
                </div>

                <h3>Work Schedule:</h3>
                <p>9:00 AM - 5:00 PM Eastern Time (US), 5 days per week<br>
                Sunday is compulsory off + one additional day of your choice (approved by company)</p>

                <h3>Important Reminders:</h3>
                <ul>
                    <li>Always be professional and respectful on calls</li>
                    <li>Never promise anything we can't deliver</li>
                    <li>Log every call in the system - no exceptions</li>
                    <li>If you're unsure about something, ask before acting</li>
                </ul>

                <p>We're excited to have you on board. Let's find some deals!</p>

                <p>Best regards,<br>
                <strong>The Lifeline Home Buyers Team</strong><br>
                Columbus, Ohio</p>
            </div>
            <div class="footer">
                <p>Lifeline Home Buyers<br>
                Columbus, Ohio</p>
            </div>
        </div>
    </body>
    </html>
    """
    return send_email(applicant_email, subject, html_content)


def send_welcome_ids_email(
    applicant_name: str,
    applicant_email: str,
    start_date: str = "TBD",
    portal_url: str = "",
    username: str = "",
    password: str = ""
) -> Tuple[bool, str]:
    """
    Send welcome email to newly hired IDS (Investor Development Specialist) team member.
    """
    subject = "Welcome to IDS Team - Lifeline Home Buyers"

    # Build credentials section if provided
    credentials_html = ""
    if username and password:
        credentials_html = f"""
                <div class="info-box" style="background: #ede9fe; border: 2px solid #7c3aed;">
                    <h3 style="margin-top: 0;">Your VA Portal Credentials:</h3>
                    <p><strong>Portal URL:</strong> {portal_url if portal_url else 'Will be provided'}</p>
                    <p><strong>Username:</strong> {username}</p>
                    <p><strong>Password:</strong> {password}</p>
                    <p style="font-size: 12px; color: #666;">Please change your password after first login.</p>
                </div>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: linear-gradient(135deg, #7c3aed 0%, #a855f7 100%); color: white; padding: 30px; text-align: center; border-radius: 10px 10px 0 0; }}
            .content {{ background: #f9f9f9; padding: 30px; border-radius: 0 0 10px 10px; }}
            .footer {{ text-align: center; margin-top: 30px; color: #666; font-size: 12px; }}
            .role-box {{ background: linear-gradient(135deg, #7c3aed 0%, #a855f7 100%); color: white; padding: 20px; border-radius: 10px; margin: 20px 0; }}
            .info-box {{ background: #f3e8ff; padding: 15px; border-radius: 8px; margin: 15px 0; }}
            .metrics-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            .metrics-table th, .metrics-table td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
            .metrics-table th {{ background: #7c3aed; color: white; }}
            ul {{ padding-left: 20px; }}
            li {{ margin: 8px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>Welcome to the IDS Team!</h1>
                <p>Investor Development Specialist</p>
            </div>
            <div class="content">
                <h2>Hello {applicant_name},</h2>

                <div class="role-box">
                    <h3 style="margin-top: 0;">Your Role: Investor Development Specialist (IDS)</h3>
                    <p>You'll be building relationships with real estate investors who buy properties. When we find deals, we need buyers ready to purchase!</p>
                </div>

                {credentials_html}

                <h3>Your Responsibilities:</h3>
                <ul>
                    <li>Call and qualify real estate investors</li>
                    <li>Build our buyers list with serious, active investors</li>
                    <li>Understand what types of properties they buy (location, price range, condition)</li>
                    <li>Maintain relationships with existing buyers</li>
                    <li>Match buyers to our available deals</li>
                </ul>

                <h3>Daily Expectations:</h3>
                <table class="metrics-table">
                    <tr><th>Metric</th><th>Daily Target</th></tr>
                    <tr><td>Calls Made</td><td>80+</td></tr>
                    <tr><td>Conversations</td><td>15+</td></tr>
                    <tr><td>Investors Qualified</td><td>3+</td></tr>
                    <tr><td>Buyers Added to List</td><td>2+</td></tr>
                </table>

                <div class="info-box">
                    <h3 style="margin-top: 0;">What Makes a Qualified Buyer:</h3>
                    <ul style="margin-bottom: 0;">
                        <li>Has purchased investment property before (or has funds ready)</li>
                        <li>Can close within 14-30 days</li>
                        <li>Has specific buying criteria (area, price, property type)</li>
                        <li>Is actively looking for deals</li>
                    </ul>
                </div>

                <div class="info-box">
                    <h3 style="margin-top: 0;">Compensation:</h3>
                    <p><strong>Base:</strong> UGX 500,000/month</p>
                    <p><strong>Bonuses:</strong> Top 2 performers each month receive performance bonuses</p>
                </div>

                <h3>Work Schedule:</h3>
                <p>9:00 AM - 5:00 PM Eastern Time (US), 5 days per week<br>
                Sunday is compulsory off + one additional day of your choice (approved by company)</p>

                <h3>Important Reminders:</h3>
                <ul>
                    <li>Investors are busy people - be respectful of their time</li>
                    <li>Get specific criteria: What areas? What price range? What condition?</li>
                    <li>Always log qualified buyers in the system immediately</li>
                    <li>Follow up is key - investors who aren't ready today may be ready next month</li>
                </ul>

                <p>We're excited to have you on board. Let's build a powerful buyers list!</p>

                <p>Best regards,<br>
                <strong>The Lifeline Home Buyers Team</strong><br>
                Columbus, Ohio</p>
            </div>
            <div class="footer">
                <p>Lifeline Home Buyers<br>
                Columbus, Ohio</p>
            </div>
        </div>
    </body>
    </html>
    """
    return send_email(applicant_email, subject, html_content)
