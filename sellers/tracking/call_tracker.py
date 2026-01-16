"""
Aerial Leads - Cold Calling Tracker

Track calls, follow-ups, and conversion metrics for your outreach campaigns.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import json

from shared.config.settings import PROCESSED_DATA_DIR
from shared.config.logging_config import get_logger


class CallTracker:
    """
    Track cold calling activities and follow-ups.

    Features:
    - Log every call with outcome and notes
    - Set follow-up reminders
    - Track lead status pipeline
    - Calculate conversion metrics
    """

    # Call outcomes
    OUTCOMES = [
        'No Answer',
        'Left Voicemail',
        'Wrong Number',
        'Not Interested',
        'Call Back Later',
        'Interested',
        'Appointment Set',
        'Offer Made',
        'Under Contract',
        'Closed Deal',
        'Do Not Call'
    ]

    # Lead status pipeline
    STATUSES = [
        'New Lead',
        'Contacted',
        'Follow Up',
        'Interested',
        'Hot Lead',
        'Appointment',
        'Offer Made',
        'Under Contract',
        'Closed',
        'Dead Lead'
    ]

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.calls_file = PROCESSED_DATA_DIR / 'call_log.csv'
        self.leads_file = PROCESSED_DATA_DIR / 'tracked_leads.csv'

        # Initialize files if they don't exist
        self._init_files()

    def _init_files(self):
        """Initialize tracking files if they don't exist."""
        # Call log columns
        call_cols = [
            'call_id', 'lead_id', 'address', 'owner_name', 'phone',
            'call_date', 'call_time', 'outcome', 'notes',
            'follow_up_date', 'follow_up_notes', 'duration_seconds',
            'created_at'
        ]

        # Tracked leads columns
        lead_cols = [
            'lead_id', 'address', 'owner_name', 'phone', 'email',
            'status', 'total_calls', 'last_call_date', 'last_outcome',
            'next_follow_up', 'follow_up_notes', 'priority',
            'motivation_score', 'taxes_owed', 'notes',
            'created_at', 'updated_at'
        ]

        if not self.calls_file.exists():
            pd.DataFrame(columns=call_cols).to_csv(self.calls_file, index=False)
            self.logger.info(f"Created call log: {self.calls_file}")

        if not self.leads_file.exists():
            pd.DataFrame(columns=lead_cols).to_csv(self.leads_file, index=False)
            self.logger.info(f"Created tracked leads: {self.leads_file}")

    def log_call(
        self,
        address: str,
        owner_name: str,
        phone: str,
        outcome: str,
        notes: str = '',
        follow_up_date: Optional[str] = None,
        follow_up_notes: str = '',
        duration_seconds: int = 0
    ) -> Dict:
        """
        Log a call and update lead status.

        Args:
            address: Property address
            owner_name: Owner's name
            phone: Phone number called
            outcome: Call outcome (from OUTCOMES list)
            notes: Notes from the conversation
            follow_up_date: Date to follow up (YYYY-MM-DD)
            follow_up_notes: Notes for follow-up
            duration_seconds: Call duration

        Returns:
            Dict with call details and lead status
        """
        now = datetime.now()

        # Generate IDs
        call_id = f"CALL-{now.strftime('%Y%m%d%H%M%S')}"
        lead_id = self._get_or_create_lead_id(address, owner_name, phone)

        # Log the call
        call_record = {
            'call_id': call_id,
            'lead_id': lead_id,
            'address': address,
            'owner_name': owner_name,
            'phone': phone,
            'call_date': now.strftime('%Y-%m-%d'),
            'call_time': now.strftime('%H:%M:%S'),
            'outcome': outcome,
            'notes': notes,
            'follow_up_date': follow_up_date or '',
            'follow_up_notes': follow_up_notes,
            'duration_seconds': duration_seconds,
            'created_at': now.isoformat()
        }

        # Append to call log
        calls_df = pd.read_csv(self.calls_file)
        calls_df = pd.concat([calls_df, pd.DataFrame([call_record])], ignore_index=True)
        calls_df.to_csv(self.calls_file, index=False)

        # Update lead status
        new_status = self._outcome_to_status(outcome)
        self._update_lead(
            lead_id=lead_id,
            address=address,
            owner_name=owner_name,
            phone=phone,
            outcome=outcome,
            status=new_status,
            follow_up_date=follow_up_date,
            follow_up_notes=follow_up_notes
        )

        self.logger.info(f"Logged call: {call_id} - {outcome}")

        return {
            'call_id': call_id,
            'lead_id': lead_id,
            'outcome': outcome,
            'new_status': new_status
        }

    def _get_or_create_lead_id(self, address: str, owner_name: str, phone: str) -> str:
        """Get existing lead ID or create new one."""
        leads_df = pd.read_csv(self.leads_file)

        # Try to find existing lead by address or phone
        existing = leads_df[
            (leads_df['address'].str.upper() == address.upper()) |
            (leads_df['phone'] == phone)
        ]

        if not existing.empty:
            return existing.iloc[0]['lead_id']

        # Create new lead ID
        return f"LEAD-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    def _outcome_to_status(self, outcome: str) -> str:
        """Map call outcome to lead status."""
        mapping = {
            'No Answer': 'Follow Up',
            'Left Voicemail': 'Follow Up',
            'Wrong Number': 'Dead Lead',
            'Not Interested': 'Dead Lead',
            'Call Back Later': 'Follow Up',
            'Interested': 'Interested',
            'Appointment Set': 'Appointment',
            'Offer Made': 'Offer Made',
            'Under Contract': 'Under Contract',
            'Closed Deal': 'Closed',
            'Do Not Call': 'Dead Lead'
        }
        return mapping.get(outcome, 'Contacted')

    def _update_lead(
        self,
        lead_id: str,
        address: str,
        owner_name: str,
        phone: str,
        outcome: str,
        status: str,
        follow_up_date: Optional[str] = None,
        follow_up_notes: str = ''
    ):
        """Update or create lead record."""
        leads_df = pd.read_csv(self.leads_file)
        now = datetime.now()

        # Check if lead exists
        existing_idx = leads_df[leads_df['lead_id'] == lead_id].index

        if len(existing_idx) > 0:
            # Update existing
            idx = existing_idx[0]
            leads_df.at[idx, 'status'] = status
            leads_df.at[idx, 'total_calls'] = leads_df.at[idx, 'total_calls'] + 1
            leads_df.at[idx, 'last_call_date'] = now.strftime('%Y-%m-%d')
            leads_df.at[idx, 'last_outcome'] = outcome
            leads_df.at[idx, 'next_follow_up'] = follow_up_date or ''
            leads_df.at[idx, 'follow_up_notes'] = follow_up_notes
            leads_df.at[idx, 'updated_at'] = now.isoformat()

            # Update priority based on status
            leads_df.at[idx, 'priority'] = self._status_to_priority(status)
        else:
            # Create new lead
            new_lead = {
                'lead_id': lead_id,
                'address': address,
                'owner_name': owner_name,
                'phone': phone,
                'email': '',
                'status': status,
                'total_calls': 1,
                'last_call_date': now.strftime('%Y-%m-%d'),
                'last_outcome': outcome,
                'next_follow_up': follow_up_date or '',
                'follow_up_notes': follow_up_notes,
                'priority': self._status_to_priority(status),
                'motivation_score': 0,
                'taxes_owed': 0,
                'notes': '',
                'created_at': now.isoformat(),
                'updated_at': now.isoformat()
            }
            leads_df = pd.concat([leads_df, pd.DataFrame([new_lead])], ignore_index=True)

        leads_df.to_csv(self.leads_file, index=False)

    def _status_to_priority(self, status: str) -> int:
        """Map status to priority (1=highest, 5=lowest)."""
        priorities = {
            'Hot Lead': 1,
            'Appointment': 1,
            'Interested': 2,
            'Offer Made': 2,
            'Under Contract': 2,
            'Follow Up': 3,
            'Contacted': 4,
            'New Lead': 4,
            'Closed': 5,
            'Dead Lead': 5
        }
        return priorities.get(status, 3)

    def get_follow_ups_due(self, days_ahead: int = 0) -> pd.DataFrame:
        """
        Get leads with follow-ups due.

        Args:
            days_ahead: Include follow-ups due within this many days

        Returns:
            DataFrame of leads needing follow-up
        """
        leads_df = pd.read_csv(self.leads_file)

        if leads_df.empty:
            return leads_df

        # Filter to leads with follow-up dates
        leads_df = leads_df[leads_df['next_follow_up'].notna() & (leads_df['next_follow_up'] != '')]

        if leads_df.empty:
            return leads_df

        # Parse dates and filter
        today = datetime.now().date()
        cutoff = today + timedelta(days=days_ahead)

        leads_df['follow_up_parsed'] = pd.to_datetime(leads_df['next_follow_up'], errors='coerce')
        due = leads_df[leads_df['follow_up_parsed'].dt.date <= cutoff]

        return due.sort_values('follow_up_parsed')

    def get_todays_stats(self) -> Dict:
        """Get today's calling statistics."""
        calls_df = pd.read_csv(self.calls_file)

        if calls_df.empty:
            return {
                'total_calls': 0,
                'conversations': 0,
                'interested': 0,
                'appointments': 0,
                'offers': 0
            }

        today = datetime.now().strftime('%Y-%m-%d')
        today_calls = calls_df[calls_df['call_date'] == today]

        conversations = today_calls[today_calls['outcome'].isin([
            'Not Interested', 'Call Back Later', 'Interested',
            'Appointment Set', 'Offer Made'
        ])]

        interested = today_calls[today_calls['outcome'].isin([
            'Interested', 'Appointment Set', 'Offer Made'
        ])]

        appointments = today_calls[today_calls['outcome'] == 'Appointment Set']
        offers = today_calls[today_calls['outcome'] == 'Offer Made']

        return {
            'total_calls': len(today_calls),
            'conversations': len(conversations),
            'interested': len(interested),
            'appointments': len(appointments),
            'offers': len(offers)
        }

    def get_weekly_stats(self) -> Dict:
        """Get this week's calling statistics."""
        calls_df = pd.read_csv(self.calls_file)

        if calls_df.empty:
            return {
                'total_calls': 0,
                'conversations': 0,
                'interested': 0,
                'appointments': 0,
                'offers': 0,
                'conversion_rate': 0
            }

        # Get start of week (Monday)
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        start_date = start_of_week.strftime('%Y-%m-%d')

        week_calls = calls_df[calls_df['call_date'] >= start_date]

        conversations = week_calls[week_calls['outcome'].isin([
            'Not Interested', 'Call Back Later', 'Interested',
            'Appointment Set', 'Offer Made'
        ])]

        interested = week_calls[week_calls['outcome'].isin([
            'Interested', 'Appointment Set', 'Offer Made'
        ])]

        appointments = week_calls[week_calls['outcome'] == 'Appointment Set']
        offers = week_calls[week_calls['outcome'] == 'Offer Made']

        total = len(week_calls)
        conversion_rate = (len(interested) / total * 100) if total > 0 else 0

        return {
            'total_calls': total,
            'conversations': len(conversations),
            'interested': len(interested),
            'appointments': len(appointments),
            'offers': len(offers),
            'conversion_rate': round(conversion_rate, 1)
        }

    def get_pipeline_summary(self) -> Dict:
        """Get lead pipeline summary."""
        leads_df = pd.read_csv(self.leads_file)

        if leads_df.empty:
            return {status: 0 for status in self.STATUSES}

        summary = leads_df['status'].value_counts().to_dict()

        # Ensure all statuses are represented
        for status in self.STATUSES:
            if status not in summary:
                summary[status] = 0

        return summary

    def get_all_calls(self, limit: int = 100) -> pd.DataFrame:
        """Get recent call history."""
        calls_df = pd.read_csv(self.calls_file)
        return calls_df.sort_values('created_at', ascending=False).head(limit)

    def get_all_leads(self) -> pd.DataFrame:
        """Get all tracked leads."""
        return pd.read_csv(self.leads_file)

    def get_leads_by_status(self, status: str) -> pd.DataFrame:
        """Get leads filtered by status."""
        leads_df = pd.read_csv(self.leads_file)
        return leads_df[leads_df['status'] == status]

    def update_lead_status(self, lead_id: str, new_status: str, notes: str = ''):
        """Manually update a lead's status."""
        leads_df = pd.read_csv(self.leads_file)

        idx = leads_df[leads_df['lead_id'] == lead_id].index
        if len(idx) > 0:
            leads_df.at[idx[0], 'status'] = new_status
            leads_df.at[idx[0], 'priority'] = self._status_to_priority(new_status)
            leads_df.at[idx[0], 'updated_at'] = datetime.now().isoformat()
            if notes:
                existing_notes = leads_df.at[idx[0], 'notes'] or ''
                leads_df.at[idx[0], 'notes'] = f"{existing_notes}\n{datetime.now().strftime('%m/%d')}: {notes}".strip()

            leads_df.to_csv(self.leads_file, index=False)
            self.logger.info(f"Updated lead {lead_id} to status: {new_status}")

    def set_follow_up(self, lead_id: str, follow_up_date: str, notes: str = ''):
        """Set a follow-up reminder for a lead."""
        leads_df = pd.read_csv(self.leads_file)

        idx = leads_df[leads_df['lead_id'] == lead_id].index
        if len(idx) > 0:
            leads_df.at[idx[0], 'next_follow_up'] = follow_up_date
            leads_df.at[idx[0], 'follow_up_notes'] = notes
            leads_df.at[idx[0], 'updated_at'] = datetime.now().isoformat()

            leads_df.to_csv(self.leads_file, index=False)
            self.logger.info(f"Set follow-up for {lead_id}: {follow_up_date}")

    def import_leads_from_main(self, main_leads_df: pd.DataFrame, limit: int = 50):
        """
        Import leads from main leads file into tracker.

        Args:
            main_leads_df: DataFrame from main leads generation
            limit: Max leads to import
        """
        leads_df = pd.read_csv(self.leads_file)
        now = datetime.now()

        imported = 0
        for _, row in main_leads_df.head(limit).iterrows():
            address = row.get('address', '')

            # Skip if already tracked
            if not leads_df.empty and address.upper() in leads_df['address'].str.upper().values:
                continue

            lead_id = f"LEAD-{now.strftime('%Y%m%d')}-{imported:04d}"

            new_lead = {
                'lead_id': lead_id,
                'address': address,
                'owner_name': row.get('owner_name', ''),
                'phone': row.get('phone', ''),
                'email': row.get('email', ''),
                'status': 'New Lead',
                'total_calls': 0,
                'last_call_date': '',
                'last_outcome': '',
                'next_follow_up': '',
                'follow_up_notes': '',
                'priority': 4,
                'motivation_score': row.get('motivation_score', 0),
                'taxes_owed': row.get('taxes_owed', 0),
                'notes': '',
                'created_at': now.isoformat(),
                'updated_at': now.isoformat()
            }

            leads_df = pd.concat([leads_df, pd.DataFrame([new_lead])], ignore_index=True)
            imported += 1

        leads_df.to_csv(self.leads_file, index=False)
        self.logger.info(f"Imported {imported} leads into tracker")

        return imported


# Example usage
if __name__ == '__main__':
    tracker = CallTracker()

    # Log a sample call
    result = tracker.log_call(
        address="123 Main St",
        owner_name="John Smith",
        phone="555-123-4567",
        outcome="Interested",
        notes="Owner wants to sell, needs to talk to spouse",
        follow_up_date="2024-01-15",
        follow_up_notes="Call back after weekend"
    )

    print(f"Logged call: {result}")

    # Get stats
    print(f"\nToday's stats: {tracker.get_todays_stats()}")
    print(f"Weekly stats: {tracker.get_weekly_stats()}")
    print(f"Pipeline: {tracker.get_pipeline_summary()}")
