"""
VA Video Interview Portal - Orteza Groups
Applicants check status, view scripts, and submit video interviews.

Run with: streamlit run recording_page.py --server.port 8503
"""

import streamlit as st
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Page config - only set if running directly (not imported)
if __name__ == "__main__":
    st.set_page_config(
        page_title="Video Interview | Lifeline Home Buyers - Orteza Groups",
        page_icon="🎬",
        layout="centered",
        initial_sidebar_state="collapsed"
    )

# Professional CSS (matching application page)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .stApp {
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* Header styles */
    .hero-section {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 50%, #1e3a5f 100%);
        padding: 2.5rem 2rem;
        border-radius: 0 0 24px 24px;
        margin: -6rem -4rem 2rem -4rem;
        text-align: center;
        box-shadow: 0 4px 20px rgba(30, 58, 95, 0.15);
    }

    .hero-logo {
        display: inline-block;
        margin-bottom: 0.75rem;
    }

    .hero-logo svg {
        width: 70px;
        height: auto;
    }

    .company-badge {
        display: inline-block;
        background: rgba(255,255,255,0.1);
        padding: 0.4rem 1rem;
        border-radius: 20px;
        font-size: 0.75rem;
        color: rgba(255,255,255,0.8);
        letter-spacing: 0.5px;
        text-transform: uppercase;
        margin-bottom: 0.75rem;
        border: 1px solid rgba(255,255,255,0.2);
    }

    .footer-logo {
        display: inline-block;
        vertical-align: middle;
        margin-right: 0.5rem;
    }

    .footer-logo svg {
        width: 28px;
        height: auto;
    }

    .hero-title {
        font-size: 2rem;
        font-weight: 700;
        color: white;
        margin-bottom: 0.5rem;
        letter-spacing: -0.5px;
    }

    .hero-subtitle {
        font-size: 1rem;
        color: rgba(255,255,255,0.85);
        font-weight: 400;
    }

    /* Status cards */
    .status-card {
        background: white;
        padding: 2rem;
        border-radius: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 12px rgba(0,0,0,0.04);
        margin-bottom: 1.5rem;
        border: 1px solid #e2e8f0;
    }

    .status-pending {
        border-left: 4px solid #f59e0b;
        background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
    }

    .status-ready {
        border-left: 4px solid #10b981;
        background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
    }

    .status-submitted {
        border-left: 4px solid #3b82f6;
        background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
    }

    .status-approved {
        border-left: 4px solid #10b981;
        background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
    }

    .status-rejected {
        border-left: 4px solid #ef4444;
        background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
    }

    .status-icon {
        font-size: 2.5rem;
        margin-bottom: 1rem;
    }

    .status-title {
        font-size: 1.25rem;
        font-weight: 700;
        color: #1e293b;
        margin-bottom: 0.5rem;
    }

    .status-message {
        font-size: 0.95rem;
        color: #475569;
        line-height: 1.6;
    }

    /* Script box */
    .script-container {
        background: white;
        border-radius: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 12px rgba(0,0,0,0.04);
        margin: 1.5rem 0;
        overflow: hidden;
        border: 1px solid #e2e8f0;
    }

    .script-header {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%);
        padding: 1rem 1.5rem;
        color: white;
    }

    .script-header h3 {
        margin: 0;
        font-size: 1rem;
        font-weight: 600;
    }

    .script-body {
        padding: 1.5rem;
        font-family: 'SF Mono', 'Consolas', monospace;
        font-size: 0.9rem;
        line-height: 1.8;
        color: #374151;
        white-space: pre-wrap;
        background: #f8fafc;
        max-height: 400px;
        overflow-y: auto;
    }

    /* Instructions box */
    .instructions-box {
        background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
        border: 1px solid #93c5fd;
        padding: 1.5rem;
        border-radius: 12px;
        margin: 1.5rem 0;
    }

    .instructions-title {
        font-size: 1rem;
        font-weight: 600;
        color: #1e40af;
        margin-bottom: 0.75rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    .instructions-list {
        margin: 0;
        padding-left: 1.25rem;
        color: #1e3a8a;
    }

    .instructions-list li {
        margin-bottom: 0.5rem;
        font-size: 0.9rem;
    }

    /* Form elements */
    .email-form {
        background: white;
        padding: 2rem;
        border-radius: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 4px 12px rgba(0,0,0,0.04);
        border: 1px solid #e2e8f0;
    }

    .stTextInput > div > div > input {
        border-radius: 10px !important;
        border: 1.5px solid #e2e8f0 !important;
        padding: 0.75rem 1rem !important;
        font-size: 0.95rem !important;
    }

    .stTextInput > div > div > input:focus {
        border-color: #1e3a5f !important;
        box-shadow: 0 0 0 3px rgba(30, 58, 95, 0.1) !important;
    }

    /* Button styling */
    .stButton > button {
        background: linear-gradient(135deg, #1e3a5f 0%, #2d5a87 100%) !important;
        color: white !important;
        border: none !important;
        padding: 0.75rem 1.5rem !important;
        font-size: 0.95rem !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        transition: all 0.3s ease !important;
        box-shadow: 0 4px 12px rgba(30, 58, 95, 0.25) !important;
    }

    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(30, 58, 95, 0.35) !important;
    }

    /* Upload area */
    .upload-area {
        background: white;
        border: 2px dashed #cbd5e1;
        border-radius: 12px;
        padding: 2rem;
        text-align: center;
        transition: all 0.2s ease;
    }

    .upload-area:hover {
        border-color: #1e3a5f;
        background: #f8fafc;
    }

    /* Success container */
    .success-container {
        background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
        padding: 2.5rem 2rem;
        border-radius: 16px;
        text-align: center;
        border: 2px solid #10b981;
        margin: 1.5rem 0;
    }

    .success-icon {
        font-size: 3.5rem;
        margin-bottom: 1rem;
    }

    .success-title {
        font-size: 1.5rem;
        font-weight: 700;
        color: #065f46;
        margin-bottom: 0.5rem;
    }

    .success-message {
        font-size: 0.95rem;
        color: #047857;
        line-height: 1.6;
    }

    /* Footer */
    .footer {
        text-align: center;
        padding: 2rem;
        color: #64748b;
        font-size: 0.85rem;
    }

    .footer-brand {
        font-weight: 600;
        color: #1e3a5f;
    }

    /* Timeline */
    .timeline {
        position: relative;
        padding-left: 2rem;
        margin: 1.5rem 0;
    }

    .timeline::before {
        content: '';
        position: absolute;
        left: 7px;
        top: 0;
        bottom: 0;
        width: 2px;
        background: #e2e8f0;
    }

    .timeline-item {
        position: relative;
        padding-bottom: 1.5rem;
    }

    .timeline-item::before {
        content: '';
        position: absolute;
        left: -2rem;
        top: 4px;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: #cbd5e1;
    }

    .timeline-item.completed::before {
        background: #10b981;
    }

    .timeline-item.current::before {
        background: #3b82f6;
        box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.2);
    }

    .timeline-title {
        font-weight: 600;
        color: #1e293b;
        font-size: 0.9rem;
    }

    .timeline-desc {
        color: #64748b;
        font-size: 0.85rem;
    }
</style>
""", unsafe_allow_html=True)

# Try to import application system
try:
    from va_applications import VAApplications, STATUS_DISPLAY
    APP_SYSTEM_AVAILABLE = True
except ImportError:
    try:
        import sys
        sys.path.insert(0, os.path.dirname(__file__))
        from va_applications import VAApplications, STATUS_DISPLAY
        APP_SYSTEM_AVAILABLE = True
    except:
        APP_SYSTEM_AVAILABLE = False
        STATUS_DISPLAY = {}


def main():
    # Hero Section
    st.markdown("""
    <div class="hero-section">
        <div class="hero-logo">
            <svg viewBox="40 40 160 80" xmlns="http://www.w3.org/2000/svg">
                <path d="M 50 80 L 80 50 L 110 80 L 110 110 L 50 110 Z" fill="none" stroke="white" stroke-width="2.5" stroke-linejoin="miter"/>
                <path d="M 110 80 L 135 80 L 145 65 L 155 95 L 165 80 L 190 80" fill="none" stroke="white" stroke-width="2.5" stroke-linecap="butt"/>
            </svg>
        </div>
        <div class="company-badge">Orteza Groups of Companies</div>
        <h1 class="hero-title">Video Interview Portal</h1>
        <p class="hero-subtitle">Lifeline Home Buyers • Application Status</p>
    </div>
    """, unsafe_allow_html=True)

    if not APP_SYSTEM_AVAILABLE:
        st.error("Application system is currently unavailable. Please try again later.")
        return

    # Email lookup section
    st.markdown("""
    <div class="email-form">
        <h3 style="margin-top: 0; color: #1e293b; font-size: 1.1rem;">Check Your Application Status</h3>
        <p style="color: #64748b; font-size: 0.9rem; margin-bottom: 1rem;">Enter the email address you used when applying.</p>
    </div>
    """, unsafe_allow_html=True)

    # Check for pre-filled email from URL parameter
    prefill_email = st.session_state.get('prefill_email', '')
    email = st.text_input("Email Address", value=prefill_email, placeholder="your@email.com", label_visibility="collapsed")

    # Auto-check status if email was pre-filled
    if prefill_email and not st.session_state.get('email_verified'):
        apps = VAApplications()
        application = apps.get_application_by_email(prefill_email)
        if application:
            st.session_state.application = application
            st.session_state.email_verified = True
            st.rerun()

    if st.button("Check Status", type="primary", use_container_width=True):
        if not email or "@" not in email:
            st.error("Please enter a valid email address")
        else:
            apps = VAApplications()
            application = apps.get_application_by_email(email)

            if not application:
                st.warning("No active application found with this email address.")
                st.info("If you haven't applied yet, please submit your application first.")
            else:
                st.session_state.application = application
                st.session_state.email_verified = True
                st.rerun()

    # Show application status if verified
    if st.session_state.get('email_verified') and st.session_state.get('application'):
        apps = VAApplications()
        app = apps.get_application(st.session_state.application['id'])

        if not app:
            st.error("Application not found")
            return

        st.markdown("---")

        # Welcome message
        st.markdown(f"""
        <div style="text-align: center; margin-bottom: 1.5rem;">
            <h2 style="color: #1e293b; margin-bottom: 0.25rem;">Welcome back, {app['full_name'].split()[0]}!</h2>
            <p style="color: #64748b;">Here's your application status</p>
        </div>
        """, unsafe_allow_html=True)

        status = app['status']

        # Status-specific content
        if status == 'applied':
            st.markdown("""
            <div class="status-card status-pending">
                <div class="status-icon">📩</div>
                <div class="status-title">Application Under Review</div>
                <div class="status-message">
                    Your application has been received and is being reviewed by our team.<br>
                    You'll receive a cold calling script to record once approved.
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Timeline
            st.markdown("""
            <div class="timeline">
                <div class="timeline-item completed">
                    <div class="timeline-title">Application Submitted</div>
                    <div class="timeline-desc">Completed</div>
                </div>
                <div class="timeline-item current">
                    <div class="timeline-title">Under Review</div>
                    <div class="timeline-desc">In Progress</div>
                </div>
                <div class="timeline-item">
                    <div class="timeline-title">Video Interview</div>
                    <div class="timeline-desc">Pending</div>
                </div>
                <div class="timeline-item">
                    <div class="timeline-title">Personal Interview</div>
                    <div class="timeline-desc">Pending</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        elif status == 'reviewing':
            st.markdown("""
            <div class="status-card status-pending">
                <div class="status-icon">👀</div>
                <div class="status-title">Application Being Reviewed</div>
                <div class="status-message">
                    Our hiring team is currently reviewing your application.<br>
                    You'll receive a script assignment soon!
                </div>
            </div>
            """, unsafe_allow_html=True)

        elif status == 'script_sent':
            st.markdown("""
            <div class="status-card status-ready">
                <div class="status-icon">🎬</div>
                <div class="status-title">Ready to Record Your Video!</div>
                <div class="status-message">
                    Great news! Please record yourself reading the script below and upload your video.
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Script display
            st.markdown(f"""
            <div class="script-container">
                <div class="script-header">
                    <h3>📝 Your Cold Calling Script</h3>
                </div>
                <div class="script-body">{app.get('assigned_script_text', 'Script not found')}</div>
            </div>
            """, unsafe_allow_html=True)

            # Recording instructions
            st.markdown("""
            <div class="instructions-box">
                <div class="instructions-title">📹 Recording Instructions</div>
                <ul class="instructions-list">
                    <li><strong>Length:</strong> 60-90 seconds</li>
                    <li><strong>Format:</strong> MP4, MOV, or WebM (max 100MB)</li>
                    <li><strong>Setup:</strong> Good lighting, clear audio, face visible</li>
                    <li><strong>Content:</strong> Read the script naturally, as if on a real call</li>
                    <li><strong>Tips:</strong> Be confident, smile, show enthusiasm!</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)

            # Video upload
            st.markdown("### 📤 Upload Your Video")

            video_file = st.file_uploader(
                "Select your video file",
                type=['mp4', 'mov', 'webm', 'avi'],
                help="Maximum file size: 100MB",
                label_visibility="collapsed"
            )

            if video_file:
                if video_file.size > 100 * 1024 * 1024:
                    st.error("File too large. Maximum size is 100MB.")
                else:
                    st.video(video_file)
                    st.success(f"Video loaded: {video_file.name} ({video_file.size / 1024 / 1024:.1f} MB)")

                    if st.button("📤 Submit Video", type="primary", use_container_width=True):
                        with st.spinner("Uploading your video..."):
                            video_data = video_file.read()
                            success, message = apps.submit_video(
                                app['id'],
                                video_file.name,
                                video_data
                            )

                            if success:
                                st.session_state.application = apps.get_application(app['id'])
                                st.rerun()
                            else:
                                st.error(message)

        elif status == 'video_submitted':
            st.markdown("""
            <div class="status-card status-submitted">
                <div class="status-icon">🎬</div>
                <div class="status-title">Video Under Review</div>
                <div class="status-message">
                    Your video has been submitted successfully!<br>
                    Our team is reviewing it and will get back to you within <strong>48 hours</strong>.
                </div>
            </div>
            """, unsafe_allow_html=True)

            submitted_at = app.get('video_submitted_at')
            if submitted_at:
                st.info(f"Video submitted on: {submitted_at.strftime('%B %d, %Y at %I:%M %p')}")

            # Timeline
            st.markdown("""
            <div class="timeline">
                <div class="timeline-item completed">
                    <div class="timeline-title">Application Submitted</div>
                    <div class="timeline-desc">Completed</div>
                </div>
                <div class="timeline-item completed">
                    <div class="timeline-title">Script Received</div>
                    <div class="timeline-desc">Completed</div>
                </div>
                <div class="timeline-item current">
                    <div class="timeline-title">Video Under Review</div>
                    <div class="timeline-desc">In Progress</div>
                </div>
                <div class="timeline-item">
                    <div class="timeline-title">Personal Interview</div>
                    <div class="timeline-desc">Pending</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        elif status == 'video_approved':
            st.markdown("""
            <div class="success-container">
                <div class="success-icon">🎉</div>
                <h2 class="success-title">Video Approved!</h2>
                <p class="success-message">
                    Congratulations! Your video interview has been approved.<br>
                    We'll reach out to schedule a personal interview with you soon.<br><br>
                    <strong>Please keep an eye on your email for scheduling details.</strong>
                </p>
            </div>
            """, unsafe_allow_html=True)
            st.balloons()

        elif status == 'interview':
            interview_date = app.get('interview_date')
            st.markdown(f"""
            <div class="status-card status-approved">
                <div class="status-icon">📞</div>
                <div class="status-title">Personal Interview Scheduled</div>
                <div class="status-message">
                    Your interview has been scheduled!<br>
                    {f'<strong>Date:</strong> {interview_date.strftime("%B %d, %Y at %I:%M %p")}' if interview_date else 'Check your email for the exact date and time.'}
                </div>
            </div>
            """, unsafe_allow_html=True)

        elif status == 'hired':
            st.markdown("""
            <div class="success-container">
                <div class="success-icon">🎊</div>
                <h2 class="success-title">Welcome to the Team!</h2>
                <p class="success-message">
                    Congratulations! You've been hired as a Virtual Assistant<br>
                    at Lifeline Home Buyers!<br><br>
                    <strong>Check your email for onboarding instructions.</strong>
                </p>
            </div>
            """, unsafe_allow_html=True)
            st.balloons()

        elif status == 'rejected':
            st.markdown("""
            <div class="status-card status-rejected">
                <div class="status-icon">📋</div>
                <div class="status-title">Application Status: Not Selected</div>
                <div class="status-message">
                    Thank you for your interest in Lifeline Home Buyers.<br>
                    Unfortunately, we've decided to move forward with other candidates at this time.<br><br>
                    We appreciate your time and wish you the best in your job search.
                </div>
            </div>
            """, unsafe_allow_html=True)

        elif status == 'withdrawn':
            st.markdown("""
            <div class="status-card" style="border-left: 4px solid #94a3b8;">
                <div class="status-icon">📋</div>
                <div class="status-title">Application Withdrawn</div>
                <div class="status-message">
                    This application has been withdrawn.
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Check status button
        st.markdown("---")
        if st.button("🔄 Refresh Status", use_container_width=True):
            st.session_state.application = apps.get_application(app['id'])
            st.rerun()

    # Footer
    st.markdown("""
    <div class="footer">
        <span class="footer-logo"><svg viewBox="40 40 160 80" xmlns="http://www.w3.org/2000/svg"><path d="M 50 80 L 80 50 L 110 80 L 110 110 L 50 110 Z" fill="none" stroke="#1e3a5f" stroke-width="2.5" stroke-linejoin="miter"/><path d="M 110 80 L 135 80 L 145 65 L 155 95 L 165 80 L 190 80" fill="none" stroke="#1e3a5f" stroke-width="2.5" stroke-linecap="butt"/></svg></span>
        <span class="footer-brand">Lifeline Home Buyers</span> • A company of Orteza Groups<br>
        Columbus, Ohio, USA<br><br>
        <small>Questions? Email us at hiring@lifelinehomebuyers.com</small>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
