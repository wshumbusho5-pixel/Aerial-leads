"""
VA Application System

Handles job applications for Virtual Assistant positions.
Stores applications in PostgreSQL database.
"""

import os
import pandas as pd
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import logging
import json

logger = logging.getLogger(__name__)

# Import email notifications
EMAIL_AVAILABLE = False
try:
    from .email_notifications import (
        send_script_assignment_email,
        send_video_approved_email,
        send_application_received_email
    )
    EMAIL_AVAILABLE = True
except ImportError:
    try:
        from email_notifications import (
            send_script_assignment_email,
            send_video_approved_email,
            send_application_received_email
        )
        EMAIL_AVAILABLE = True
    except ImportError:
        logger.warning("Email notifications not available")

# Try database connection
DB_AVAILABLE = False
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL:
        DB_AVAILABLE = True
except ImportError:
    pass


# Application statuses
APPLICATION_STATUS = [
    'applied',              # Just submitted
    'reviewing',            # Under review
    'script_sent',          # Script assigned, waiting for video
    'video_submitted',      # Video received, pending review
    'video_approved',       # Video approved, ready for personal interview
    'interview',            # Personal interview scheduled
    'hired',                # Accepted
    'rejected',             # Not accepted
    'withdrawn'             # Applicant withdrew
]

STATUS_DISPLAY = {
    'applied': '📩 Applied',
    'reviewing': '👀 Under Review',
    'script_sent': '📝 Script Sent',
    'video_submitted': '🎬 Video Submitted',
    'video_approved': '✅ Video Approved',
    'interview': '📞 Personal Interview',
    'hired': '✅ Hired',
    'rejected': '❌ Rejected',
    'withdrawn': '🚪 Withdrawn'
}

# Default cold calling scripts for video interview
COLD_CALL_SCRIPTS = {
    'tax_delinquent': {
        'name': 'Tax Delinquent Script',
        'script': """Hi, is this [PROPERTY OWNER NAME]?

Hey [NAME], my name is [YOUR NAME] and I'm calling from Lifeline Home Buyers here in Columbus.

I'm reaching out because I noticed your property at [ADDRESS] has some outstanding taxes, and I wanted to see if you'd be interested in a cash offer for the property?

[If YES]: Great! So just a few quick questions...
- Are you the sole owner of the property, or is there anyone else on the title?
- Is anyone currently living in the property?
- What kind of condition would you say the property is in?
- If I could get you a fair cash offer this week, is that something you'd consider?

[If NO]: No problem at all. Would it be okay if I followed up with you in a few weeks? Sometimes situations change. Have a great day!

---
INSTRUCTIONS FOR VIDEO:
1. Pretend you're calling a property owner named "John Smith" at "123 Main Street"
2. Use your own name
3. Read the script naturally, as if you're on a real call
4. Show enthusiasm and professionalism
5. Video should be 60-90 seconds"""
    },
    'probate': {
        'name': 'Probate/Inherited Property Script',
        'script': """Hi, is this [PROPERTY OWNER NAME]?

Hey [NAME], my name is [YOUR NAME] calling from Lifeline Home Buyers.

I understand you may have recently inherited a property at [ADDRESS], and I know that can come with a lot of decisions to make.

I wanted to reach out and see if selling the property for cash might be something you're considering? We handle everything - repairs, cleanouts, closing costs - so you don't have to worry about any of that.

[If YES]: I'm sorry for your loss, and I appreciate you taking my call. Let me ask you a few questions...
- Is the property currently occupied or vacant?
- Has the estate been through probate yet?
- Are there multiple heirs involved, or just yourself?
- What condition is the property in?

[If NO]: I completely understand. If your situation changes, please keep my number. We're always here to help. Take care.

---
INSTRUCTIONS FOR VIDEO:
1. Pretend you're calling a property owner named "Mary Johnson" at "456 Oak Avenue"
2. Use your own name
3. Be empathetic - these are often sensitive situations
4. Read naturally and professionally
5. Video should be 60-90 seconds"""
    },
    'general': {
        'name': 'General Cold Call Script',
        'script': """Hi, is this [PROPERTY OWNER NAME]?

Hey [NAME], my name is [YOUR NAME] and I'm with Lifeline Home Buyers here in Columbus, Ohio.

The reason for my call is we're actively buying properties in your area, and I wanted to see if you've ever considered selling your property at [ADDRESS] for cash?

[If YES]: Awesome! I just have a few quick questions for you...
- How long have you owned the property?
- Is anyone currently living there?
- On a scale of 1-10, with 10 being move-in ready, how would you rate the condition?
- What's your timeline - are you looking to sell soon or just testing the waters?
- Do you have a price in mind?

[If NO]: No worries! Is it okay if I check back with you in a month or two? Sometimes situations change.

[Handle Objection - "How did you get my number?"]:
Your information is part of the public record as the property owner. We're just reaching out to homeowners in the area to see if anyone might be interested in selling.

---
INSTRUCTIONS FOR VIDEO:
1. Pretend you're calling "Robert Williams" at "789 Elm Street"
2. Use your own name
3. Be confident and friendly
4. Read the script naturally
5. Video should be 60-90 seconds"""
    }
}

# Job description
JOB_DESCRIPTION = """
## Virtual Assistant - Real Estate Acquisitions (Contractor)

**Company:** Lifeline Home Buyers
**Location:** Remote (Work from anywhere)
**Type:** Independent Contractor
**Hours:** 20-40 hours/week (flexible)
**Pay:** $4-6/hour USD (based on experience)

---

### About Us

Lifeline Home Buyers is a real estate investment company based in Columbus, Ohio. We help homeowners in difficult situations (tax delinquency, probate, foreclosure) sell their properties quickly for cash. We're looking for motivated Virtual Assistants to join our acquisitions team.

---

### What You'll Do

- **Cold Calling:** Contact property owners from our lead lists using our dialer system
- **Lead Qualification:** Ask qualifying questions to identify motivated sellers
- **Data Entry:** Log call outcomes and update lead information in our CRM
- **Follow-ups:** Make follow-up calls to warm leads
- **Appointment Setting:** Schedule property walkthroughs for our acquisitions team
- **Skip Tracing:** Use our tools to find contact information for property owners

---

### Requirements

- Excellent English communication skills (spoken and written)
- Reliable internet connection (minimum 10 Mbps)
- Computer with headset/microphone
- Quiet workspace for making calls
- Available to work during US Eastern Time business hours (9 AM - 6 PM EST)
- Experience with cold calling preferred but not required
- Self-motivated and able to work independently

---

### What We Provide

- Full training on our systems and scripts
- All leads and data provided
- Dialer software and CRM access
- Ongoing coaching and support
- Performance bonuses for appointments that close

---

### To Apply

1. Fill out the application form below
2. Upload your resume
3. We'll review your application within 48 hours
4. If selected, we'll schedule a video interview

---

**This is a 1099 contractor position, not employment.**
"""


class VAApplications:
    """Manages VA job applications."""

    def __init__(self):
        """Initialize application manager."""
        self.db_url = os.environ.get('DATABASE_URL')
        self._init_db()

    def _get_connection(self):
        """Get database connection."""
        if DB_AVAILABLE and self.db_url:
            return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)
        return None

    def _init_db(self):
        """Initialize database tables."""
        conn = self._get_connection()
        if not conn:
            logger.warning("Database not available for VA applications")
            return

        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS va_applications (
                id SERIAL PRIMARY KEY,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(50) DEFAULT 'applied',

                -- Personal Info
                full_name VARCHAR(255) NOT NULL,
                email VARCHAR(255) NOT NULL,
                phone VARCHAR(50),
                country VARCHAR(100),
                timezone VARCHAR(100),

                -- Experience
                cold_calling_experience TEXT,
                real_estate_experience TEXT,
                years_experience INTEGER DEFAULT 0,
                current_job VARCHAR(255),

                -- Availability
                hours_per_week INTEGER,
                available_start_date DATE,
                us_timezone_hours BOOLEAN DEFAULT TRUE,

                -- Technical
                internet_speed VARCHAR(50),
                has_computer BOOLEAN DEFAULT TRUE,
                has_headset BOOLEAN DEFAULT TRUE,
                has_quiet_workspace BOOLEAN DEFAULT TRUE,

                -- Assessment
                english_proficiency VARCHAR(50),
                why_interested TEXT,

                -- Resume
                resume_filename VARCHAR(255),
                resume_data BYTEA,

                -- Admin notes
                admin_notes TEXT,
                interview_date TIMESTAMP,
                interviewer VARCHAR(100),

                -- Video Interview
                assigned_script_key VARCHAR(50),
                assigned_script_text TEXT,
                script_assigned_at TIMESTAMP,
                video_filename VARCHAR(255),
                video_data BYTEA,
                video_submitted_at TIMESTAMP,
                video_notes TEXT
            )
        """)

        # Add new columns if they don't exist (for existing tables)
        try:
            cursor.execute("""
                ALTER TABLE va_applications
                ADD COLUMN IF NOT EXISTS assigned_script_key VARCHAR(50),
                ADD COLUMN IF NOT EXISTS assigned_script_text TEXT,
                ADD COLUMN IF NOT EXISTS script_assigned_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS video_filename VARCHAR(255),
                ADD COLUMN IF NOT EXISTS video_data BYTEA,
                ADD COLUMN IF NOT EXISTS video_submitted_at TIMESTAMP,
                ADD COLUMN IF NOT EXISTS video_notes TEXT
            """)
            conn.commit()
        except Exception as e:
            logger.warning(f"Could not add new columns (may already exist): {e}")
        conn.commit()
        conn.close()
        logger.info("VA applications table initialized")

    def submit_application(self, data: Dict) -> Tuple[bool, str]:
        """
        Submit a new VA application.

        Returns:
            Tuple of (success, message)
        """
        conn = self._get_connection()
        if not conn:
            return False, "Application system unavailable"

        try:
            cursor = conn.cursor()

            # Check for duplicate email
            cursor.execute(
                "SELECT id FROM va_applications WHERE email = %s AND status NOT IN ('rejected', 'withdrawn')",
                (data.get('email'),)
            )
            if cursor.fetchone():
                conn.close()
                return False, "An application with this email already exists"

            cursor.execute("""
                INSERT INTO va_applications (
                    full_name, email, phone, country, timezone,
                    cold_calling_experience, real_estate_experience, years_experience, current_job,
                    hours_per_week, available_start_date, us_timezone_hours,
                    internet_speed, has_computer, has_headset, has_quiet_workspace,
                    english_proficiency, why_interested,
                    resume_filename, resume_data
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s,
                    %s, %s
                )
            """, (
                data.get('full_name'),
                data.get('email'),
                data.get('phone'),
                data.get('country'),
                data.get('timezone'),
                data.get('cold_calling_experience'),
                data.get('real_estate_experience'),
                data.get('years_experience', 0),
                data.get('current_job'),
                data.get('hours_per_week'),
                data.get('available_start_date'),
                data.get('us_timezone_hours', True),
                data.get('internet_speed'),
                data.get('has_computer', True),
                data.get('has_headset', True),
                data.get('has_quiet_workspace', True),
                data.get('english_proficiency'),
                data.get('why_interested'),
                data.get('resume_filename'),
                data.get('resume_data')
            ))

            conn.commit()
            conn.close()

            # Send confirmation email
            if EMAIL_AVAILABLE:
                try:
                    send_application_received_email(
                        applicant_name=data.get('full_name'),
                        applicant_email=data.get('email')
                    )
                    logger.info(f"Confirmation email sent to {data.get('email')}")
                except Exception as email_error:
                    logger.warning(f"Could not send confirmation email: {email_error}")

            return True, "Application submitted successfully! We'll review it within 48 hours."

        except Exception as e:
            logger.error(f"Error submitting application: {e}")
            conn.close()
            return False, f"Error submitting application: {str(e)}"

    def get_all_applications(self, status: str = None) -> List[Dict]:
        """Get all applications, optionally filtered by status."""
        conn = self._get_connection()
        if not conn:
            return []

        try:
            cursor = conn.cursor()

            if status:
                cursor.execute(
                    "SELECT * FROM va_applications WHERE status = %s ORDER BY created_at DESC",
                    (status,)
                )
            else:
                cursor.execute("SELECT * FROM va_applications ORDER BY created_at DESC")

            rows = cursor.fetchall()
            conn.close()
            return list(rows) if rows else []

        except Exception as e:
            logger.error(f"Error getting applications: {e}")
            conn.close()
            return []

    def get_application(self, app_id: int) -> Optional[Dict]:
        """Get a single application by ID."""
        conn = self._get_connection()
        if not conn:
            return None

        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM va_applications WHERE id = %s", (app_id,))
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None

        except Exception as e:
            logger.error(f"Error getting application: {e}")
            conn.close()
            return None

    def update_status(self, app_id: int, new_status: str, notes: str = None) -> Tuple[bool, str]:
        """Update application status."""
        if new_status not in APPLICATION_STATUS:
            return False, f"Invalid status: {new_status}"

        conn = self._get_connection()
        if not conn:
            return False, "Database unavailable"

        try:
            cursor = conn.cursor()

            if notes:
                cursor.execute("""
                    UPDATE va_applications
                    SET status = %s, admin_notes = COALESCE(admin_notes, '') || %s, updated_at = NOW()
                    WHERE id = %s
                """, (new_status, f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Status → {new_status}: {notes}", app_id))
            else:
                cursor.execute("""
                    UPDATE va_applications
                    SET status = %s, updated_at = NOW()
                    WHERE id = %s
                """, (new_status, app_id))

            conn.commit()
            conn.close()
            return True, f"Status updated to {new_status}"

        except Exception as e:
            logger.error(f"Error updating status: {e}")
            conn.close()
            return False, str(e)

    def schedule_interview(self, app_id: int, interview_date: datetime, interviewer: str = None) -> Tuple[bool, str]:
        """Schedule an interview for an applicant."""
        conn = self._get_connection()
        if not conn:
            return False, "Database unavailable"

        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE va_applications
                SET status = 'interview', interview_date = %s, interviewer = %s, updated_at = NOW()
                WHERE id = %s
            """, (interview_date, interviewer, app_id))

            conn.commit()
            conn.close()
            return True, f"Interview scheduled for {interview_date.strftime('%Y-%m-%d %H:%M')}"

        except Exception as e:
            logger.error(f"Error scheduling interview: {e}")
            conn.close()
            return False, str(e)

    def hire_applicant(self, app_id: int) -> Tuple[bool, str]:
        """Mark applicant as hired and create VA account."""
        app = self.get_application(app_id)
        if not app:
            return False, "Application not found"

        # Update status to hired
        success, msg = self.update_status(app_id, 'hired', 'Applicant hired')
        if not success:
            return False, msg

        return True, f"Applicant {app['full_name']} marked as hired. Create their VA account in User Management."

    def get_stats(self) -> Dict:
        """Get application statistics."""
        conn = self._get_connection()
        if not conn:
            return {}

        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT status, COUNT(*) as count
                FROM va_applications
                GROUP BY status
            """)
            rows = cursor.fetchall()
            conn.close()

            stats = {row['status']: row['count'] for row in rows}
            stats['total'] = sum(stats.values())
            return stats

        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            conn.close()
            return {}

    def get_resume(self, app_id: int) -> Optional[Tuple[str, bytes]]:
        """Get resume file for an application."""
        conn = self._get_connection()
        if not conn:
            return None

        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT resume_filename, resume_data FROM va_applications WHERE id = %s",
                (app_id,)
            )
            row = cursor.fetchone()
            conn.close()

            if row and row['resume_data']:
                return (row['resume_filename'], bytes(row['resume_data']))
            return None

        except Exception as e:
            logger.error(f"Error getting resume: {e}")
            conn.close()
            return None

    def get_application_by_email(self, email: str) -> Optional[Dict]:
        """Get application by email address."""
        conn = self._get_connection()
        if not conn:
            return None

        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM va_applications WHERE email = %s AND status NOT IN ('rejected', 'withdrawn') ORDER BY created_at DESC LIMIT 1",
                (email,)
            )
            row = cursor.fetchone()
            conn.close()
            return dict(row) if row else None

        except Exception as e:
            logger.error(f"Error getting application by email: {e}")
            conn.close()
            return None

    def assign_script(self, app_id: int, script_key: str, custom_script: str = None, recording_url: str = None) -> Tuple[bool, str]:
        """Assign a cold calling script to an applicant for video interview."""
        conn = self._get_connection()
        if not conn:
            return False, "Database unavailable"

        # Get script text and name
        if custom_script:
            script_text = custom_script
            script_name = "Custom Script"
        elif script_key in COLD_CALL_SCRIPTS:
            script_text = COLD_CALL_SCRIPTS[script_key]['script']
            script_name = COLD_CALL_SCRIPTS[script_key]['name']
        else:
            return False, f"Invalid script key: {script_key}"

        try:
            cursor = conn.cursor()

            # Get applicant info for email
            cursor.execute("SELECT full_name, email FROM va_applications WHERE id = %s", (app_id,))
            applicant = cursor.fetchone()
            if not applicant:
                conn.close()
                return False, "Application not found"

            cursor.execute("""
                UPDATE va_applications
                SET status = 'script_sent',
                    assigned_script_key = %s,
                    assigned_script_text = %s,
                    script_assigned_at = NOW(),
                    updated_at = NOW(),
                    admin_notes = COALESCE(admin_notes, '') || %s
                WHERE id = %s
            """, (
                script_key,
                script_text,
                f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Script assigned: {script_key}",
                app_id
            ))

            conn.commit()
            conn.close()

            # Send email notification
            email_sent = False
            if EMAIL_AVAILABLE and recording_url:
                try:
                    email_sent, email_msg = send_script_assignment_email(
                        applicant_name=applicant['full_name'],
                        applicant_email=applicant['email'],
                        script_name=script_name,
                        recording_url=recording_url
                    )
                    if email_sent:
                        logger.info(f"Script assignment email sent to {applicant['email']}")
                    else:
                        logger.warning(f"Failed to send email: {email_msg}")
                except Exception as e:
                    logger.error(f"Error sending email: {e}")

            msg = "Script assigned successfully."
            if email_sent:
                msg += " Email notification sent to applicant."
            elif EMAIL_AVAILABLE:
                msg += " (Email notification failed - applicant should check recording portal)"
            else:
                msg += " (Email notifications not configured)"

            return True, msg

        except Exception as e:
            logger.error(f"Error assigning script: {e}")
            conn.close()
            return False, str(e)

    def submit_video(self, app_id: int, video_filename: str, video_data: bytes) -> Tuple[bool, str]:
        """Submit video recording for an application."""
        conn = self._get_connection()
        if not conn:
            return False, "Database unavailable"

        try:
            cursor = conn.cursor()

            # Verify application exists and is in correct status
            cursor.execute(
                "SELECT status FROM va_applications WHERE id = %s",
                (app_id,)
            )
            row = cursor.fetchone()
            if not row:
                conn.close()
                return False, "Application not found"

            if row['status'] != 'script_sent':
                conn.close()
                return False, f"Cannot submit video. Current status: {row['status']}"

            cursor.execute("""
                UPDATE va_applications
                SET status = 'video_submitted',
                    video_filename = %s,
                    video_data = %s,
                    video_submitted_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
            """, (video_filename, video_data, app_id))

            conn.commit()
            conn.close()
            return True, "Video submitted successfully! We'll review it within 48 hours."

        except Exception as e:
            logger.error(f"Error submitting video: {e}")
            conn.close()
            return False, str(e)

    def get_video(self, app_id: int) -> Optional[Tuple[str, bytes]]:
        """Get video recording for an application."""
        conn = self._get_connection()
        if not conn:
            return None

        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT video_filename, video_data FROM va_applications WHERE id = %s",
                (app_id,)
            )
            row = cursor.fetchone()
            conn.close()

            if row and row['video_data']:
                return (row['video_filename'], bytes(row['video_data']))
            return None

        except Exception as e:
            logger.error(f"Error getting video: {e}")
            conn.close()
            return None

    def approve_video(self, app_id: int, notes: str = None) -> Tuple[bool, str]:
        """Approve video interview and move to personal interview stage."""
        conn = self._get_connection()
        if not conn:
            return False, "Database unavailable"

        try:
            cursor = conn.cursor()

            # Get applicant info for email
            cursor.execute("SELECT full_name, email FROM va_applications WHERE id = %s", (app_id,))
            applicant = cursor.fetchone()

            note_text = f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Video APPROVED"
            if notes:
                note_text += f": {notes}"

            cursor.execute("""
                UPDATE va_applications
                SET status = 'video_approved',
                    video_notes = %s,
                    admin_notes = COALESCE(admin_notes, '') || %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (notes, note_text, app_id))

            conn.commit()
            conn.close()

            # Send approval email
            email_sent = False
            if EMAIL_AVAILABLE and applicant:
                try:
                    email_sent, email_msg = send_video_approved_email(
                        applicant_name=applicant['full_name'],
                        applicant_email=applicant['email']
                    )
                    if email_sent:
                        logger.info(f"Video approval email sent to {applicant['email']}")
                except Exception as e:
                    logger.error(f"Error sending approval email: {e}")

            msg = "Video approved! Applicant is ready for personal interview."
            if email_sent:
                msg += " Congratulations email sent."

            return True, msg

        except Exception as e:
            logger.error(f"Error approving video: {e}")
            conn.close()
            return False, str(e)

    def reject_video(self, app_id: int, reason: str = None) -> Tuple[bool, str]:
        """Reject video interview."""
        conn = self._get_connection()
        if not conn:
            return False, "Database unavailable"

        try:
            cursor = conn.cursor()
            note_text = f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Video REJECTED"
            if reason:
                note_text += f": {reason}"

            cursor.execute("""
                UPDATE va_applications
                SET status = 'rejected',
                    video_notes = %s,
                    admin_notes = COALESCE(admin_notes, '') || %s,
                    updated_at = NOW()
                WHERE id = %s
            """, (reason, note_text, app_id))

            conn.commit()
            conn.close()
            return True, "Application rejected."

        except Exception as e:
            logger.error(f"Error rejecting video: {e}")
            conn.close()
            return False, str(e)

    def get_pending_videos(self) -> List[Dict]:
        """Get all applications with videos pending review."""
        return self.get_all_applications(status='video_submitted')

    def get_pending_scripts(self) -> List[Dict]:
        """Get all applications waiting for video submission."""
        return self.get_all_applications(status='script_sent')

    def reset_all_applications(self) -> Tuple[bool, str]:
        """
        Delete all applications from the database.
        USE WITH CAUTION - this cannot be undone!

        Returns:
            Tuple of (success, message)
        """
        conn = self._get_connection()
        if not conn:
            return False, "Database connection unavailable"

        try:
            cursor = conn.cursor()

            # Get count before deletion
            cursor.execute("SELECT COUNT(*) as count FROM va_applications")
            result = cursor.fetchone()
            count = result['count'] if result else 0

            # Delete all applications
            cursor.execute("DELETE FROM va_applications")

            conn.commit()
            conn.close()

            logger.info(f"Reset all applications - deleted {count} records")
            return True, f"Successfully deleted {count} applications"

        except Exception as e:
            logger.error(f"Error resetting applications: {e}")
            conn.close()
            return False, f"Error resetting applications: {str(e)}"

    def delete_application(self, app_id: int) -> Tuple[bool, str]:
        """
        Delete a single application by ID.

        Returns:
            Tuple of (success, message)
        """
        conn = self._get_connection()
        if not conn:
            return False, "Database connection unavailable"

        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM va_applications WHERE id = %s", (app_id,))

            if cursor.rowcount == 0:
                conn.close()
                return False, "Application not found"

            conn.commit()
            conn.close()

            logger.info(f"Deleted application {app_id}")
            return True, "Application deleted successfully"

        except Exception as e:
            logger.error(f"Error deleting application: {e}")
            conn.close()
            return False, f"Error: {str(e)}"
