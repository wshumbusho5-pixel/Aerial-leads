"""
Lifeline Home Buyers - Appointment Scheduler

Schedule and track appointments with sellers:
- Phone appointments
- Property walkthroughs
- Closing appointments

Never miss a deal because of missed appointments!
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import uuid

from config.settings import DATA_DIR
from config.logging_config import get_logger

logger = get_logger("AppointmentScheduler")

# Appointment types
APPOINTMENT_TYPES = [
    "phone_call",      # Scheduled callback
    "walkthrough",     # Property visit
    "offer_meeting",   # Present offer
    "signing",         # Contract signing
    "closing",         # Final closing
    "follow_up",       # General follow-up
    "other"
]

APPOINTMENT_TYPE_DISPLAY = {
    "phone_call": "📞 Phone Call",
    "walkthrough": "🏠 Property Walkthrough",
    "offer_meeting": "📝 Offer Meeting",
    "signing": "✍️ Contract Signing",
    "closing": "💰 Closing",
    "follow_up": "🔄 Follow-up",
    "other": "📋 Other"
}

APPOINTMENT_STATUS = [
    "scheduled",   # Upcoming
    "confirmed",   # Seller confirmed
    "completed",   # Done
    "no_show",     # Seller didn't show
    "cancelled",   # Cancelled
    "rescheduled"  # Moved to new time
]

STATUS_COLORS = {
    "scheduled": "#17a2b8",
    "confirmed": "#28a745",
    "completed": "#6c757d",
    "no_show": "#dc3545",
    "cancelled": "#ffc107",
    "rescheduled": "#fd7e14"
}

# Data file
APPOINTMENTS_FILE = DATA_DIR / "appointments.csv"


class AppointmentScheduler:
    """
    Schedule and manage appointments with sellers.
    """

    def __init__(self):
        self._init_file()

    def _init_file(self):
        """Initialize data file if it doesn't exist."""
        if not APPOINTMENTS_FILE.exists():
            df = pd.DataFrame(columns=[
                'appointment_id', 'created_at', 'updated_at',
                # Scheduling
                'scheduled_date', 'scheduled_time', 'duration_minutes',
                'appointment_type', 'status',
                # Property/Seller
                'address', 'seller_name', 'seller_phone',
                'deal_id',  # Link to deal if exists
                # Assignment
                'assigned_to', 'created_by',
                # Details
                'notes', 'outcome', 'follow_up_needed',
                # Reminders
                'reminder_sent', 'reminder_time'
            ])
            df.to_csv(APPOINTMENTS_FILE, index=False)

    def schedule_appointment(
        self,
        scheduled_date: str,
        scheduled_time: str,
        appointment_type: str,
        address: str = "",
        seller_name: str = "",
        seller_phone: str = "",
        deal_id: str = "",
        assigned_to: str = "",
        created_by: str = "",
        duration_minutes: int = 30,
        notes: str = ""
    ) -> str:
        """
        Schedule a new appointment.

        Args:
            scheduled_date: Date (YYYY-MM-DD)
            scheduled_time: Time (HH:MM)
            appointment_type: Type of appointment
            address: Property address
            seller_name: Seller's name
            seller_phone: Seller's phone
            deal_id: Link to deal (optional)
            assigned_to: Who will attend
            created_by: Who created
            duration_minutes: Expected duration
            notes: Additional notes

        Returns:
            appointment_id
        """
        appointment_id = f"APT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:4].upper()}"

        appointment = {
            'appointment_id': appointment_id,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'scheduled_date': scheduled_date,
            'scheduled_time': scheduled_time,
            'duration_minutes': duration_minutes,
            'appointment_type': appointment_type,
            'status': 'scheduled',
            'address': address,
            'seller_name': seller_name,
            'seller_phone': seller_phone,
            'deal_id': deal_id,
            'assigned_to': assigned_to,
            'created_by': created_by,
            'notes': notes,
            'outcome': '',
            'follow_up_needed': False,
            'reminder_sent': False,
            'reminder_time': ''
        }

        df = pd.read_csv(APPOINTMENTS_FILE)
        df = pd.concat([df, pd.DataFrame([appointment])], ignore_index=True)
        df.to_csv(APPOINTMENTS_FILE, index=False)

        logger.info(f"Scheduled appointment {appointment_id} for {scheduled_date} {scheduled_time}")
        return appointment_id

    def get_appointment(self, appointment_id: str) -> Optional[Dict]:
        """Get a single appointment by ID."""
        df = pd.read_csv(APPOINTMENTS_FILE)
        apt = df[df['appointment_id'] == appointment_id]
        if apt.empty:
            return None
        return apt.iloc[0].to_dict()

    def get_all_appointments(
        self,
        status: str = None,
        assigned_to: str = None,
        start_date: str = None,
        end_date: str = None
    ) -> pd.DataFrame:
        """Get all appointments with optional filters."""
        df = pd.read_csv(APPOINTMENTS_FILE)

        if status:
            df = df[df['status'] == status]

        if assigned_to:
            df = df[df['assigned_to'] == assigned_to]

        if start_date:
            df = df[df['scheduled_date'] >= start_date]

        if end_date:
            df = df[df['scheduled_date'] <= end_date]

        return df.sort_values('scheduled_date')

    def get_todays_appointments(self, assigned_to: str = None) -> pd.DataFrame:
        """Get today's appointments."""
        today = datetime.now().strftime('%Y-%m-%d')
        return self.get_all_appointments(start_date=today, end_date=today, assigned_to=assigned_to)

    def get_upcoming_appointments(self, days: int = 7, assigned_to: str = None) -> pd.DataFrame:
        """Get upcoming appointments for the next N days."""
        today = datetime.now().strftime('%Y-%m-%d')
        end = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')
        df = self.get_all_appointments(start_date=today, end_date=end, assigned_to=assigned_to)
        return df[df['status'].isin(['scheduled', 'confirmed'])]

    def update_appointment(self, appointment_id: str, updates: Dict) -> bool:
        """Update an appointment."""
        df = pd.read_csv(APPOINTMENTS_FILE)
        idx = df[df['appointment_id'] == appointment_id].index

        if len(idx) == 0:
            logger.warning(f"Appointment not found: {appointment_id}")
            return False

        idx = idx[0]

        for key, value in updates.items():
            if key in df.columns:
                df.at[idx, key] = value

        df.at[idx, 'updated_at'] = datetime.now().isoformat()
        df.to_csv(APPOINTMENTS_FILE, index=False)

        logger.info(f"Updated appointment {appointment_id}")
        return True

    def mark_status(self, appointment_id: str, status: str, outcome: str = "", follow_up_needed: bool = False) -> bool:
        """Mark appointment status with outcome."""
        if status not in APPOINTMENT_STATUS:
            logger.error(f"Invalid status: {status}")
            return False

        updates = {
            'status': status,
            'outcome': outcome,
            'follow_up_needed': follow_up_needed
        }

        return self.update_appointment(appointment_id, updates)

    def reschedule(self, appointment_id: str, new_date: str, new_time: str, reason: str = "") -> str:
        """
        Reschedule an appointment.

        Creates a new appointment and marks old one as rescheduled.
        """
        old_apt = self.get_appointment(appointment_id)
        if not old_apt:
            return ""

        # Mark old as rescheduled
        self.mark_status(appointment_id, 'rescheduled', outcome=f"Rescheduled to {new_date} {new_time}. {reason}")

        # Create new appointment
        new_id = self.schedule_appointment(
            scheduled_date=new_date,
            scheduled_time=new_time,
            appointment_type=old_apt['appointment_type'],
            address=old_apt['address'],
            seller_name=old_apt['seller_name'],
            seller_phone=old_apt['seller_phone'],
            deal_id=old_apt['deal_id'],
            assigned_to=old_apt['assigned_to'],
            created_by=old_apt['created_by'],
            duration_minutes=int(old_apt['duration_minutes']),
            notes=f"Rescheduled from {old_apt['scheduled_date']}. {old_apt['notes']}"
        )

        return new_id

    def get_appointments_needing_reminder(self, hours_before: int = 24) -> pd.DataFrame:
        """Get appointments that need reminders sent."""
        df = pd.read_csv(APPOINTMENTS_FILE)

        # Filter to upcoming, not reminded
        df = df[df['status'].isin(['scheduled', 'confirmed'])]
        df = df[df['reminder_sent'] != True]

        # Check if within reminder window
        now = datetime.now()
        reminder_cutoff = (now + timedelta(hours=hours_before)).strftime('%Y-%m-%d')

        df = df[df['scheduled_date'] <= reminder_cutoff]

        return df

    def mark_reminder_sent(self, appointment_id: str) -> bool:
        """Mark that reminder was sent for appointment."""
        return self.update_appointment(appointment_id, {
            'reminder_sent': True,
            'reminder_time': datetime.now().isoformat()
        })

    def get_stats(self, assigned_to: str = None) -> Dict:
        """Get appointment statistics."""
        df = pd.read_csv(APPOINTMENTS_FILE)

        if assigned_to:
            df = df[df['assigned_to'] == assigned_to]

        if df.empty:
            return {
                'total': 0,
                'scheduled': 0,
                'confirmed': 0,
                'completed': 0,
                'no_show': 0,
                'cancelled': 0,
                'show_rate': 0,
                'today': 0,
                'this_week': 0
            }

        by_status = df['status'].value_counts().to_dict()

        # Calculate show rate
        completed = by_status.get('completed', 0)
        no_show = by_status.get('no_show', 0)
        total_past = completed + no_show
        show_rate = (completed / total_past * 100) if total_past > 0 else 0

        # Today and this week counts
        today = datetime.now().strftime('%Y-%m-%d')
        week_end = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

        today_count = len(df[(df['scheduled_date'] == today) & (df['status'].isin(['scheduled', 'confirmed']))])
        week_count = len(df[(df['scheduled_date'] >= today) & (df['scheduled_date'] <= week_end) & (df['status'].isin(['scheduled', 'confirmed']))])

        return {
            'total': len(df),
            'scheduled': by_status.get('scheduled', 0),
            'confirmed': by_status.get('confirmed', 0),
            'completed': completed,
            'no_show': no_show,
            'cancelled': by_status.get('cancelled', 0),
            'show_rate': show_rate,
            'today': today_count,
            'this_week': week_count
        }

    def get_calendar_data(self, year: int, month: int, assigned_to: str = None) -> Dict[str, List]:
        """
        Get appointment data formatted for calendar display.

        Returns dict with date strings as keys, list of appointments as values.
        """
        # Get date range for month
        start = f"{year}-{month:02d}-01"
        if month == 12:
            end = f"{year + 1}-01-01"
        else:
            end = f"{year}-{month + 1:02d}-01"

        df = self.get_all_appointments(start_date=start, end_date=end, assigned_to=assigned_to)

        calendar_data = {}
        for _, apt in df.iterrows():
            date = apt['scheduled_date']
            if date not in calendar_data:
                calendar_data[date] = []
            calendar_data[date].append({
                'id': apt['appointment_id'],
                'time': apt['scheduled_time'],
                'type': apt['appointment_type'],
                'type_display': APPOINTMENT_TYPE_DISPLAY.get(apt['appointment_type'], apt['appointment_type']),
                'address': apt['address'],
                'seller': apt['seller_name'],
                'status': apt['status'],
                'assigned_to': apt['assigned_to']
            })

        return calendar_data


# Export
__all__ = [
    'AppointmentScheduler',
    'APPOINTMENT_TYPES',
    'APPOINTMENT_TYPE_DISPLAY',
    'APPOINTMENT_STATUS',
    'STATUS_COLORS'
]
