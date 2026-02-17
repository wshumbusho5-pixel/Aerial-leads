"""
Call Manager for Lifeline Home Buyers Dialer

Handles lead queue management, call tracking, and disposition recording.
"""

import os
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from enum import Enum


class CallDisposition(Enum):
    """Call outcome dispositions."""
    NOT_CALLED = "not_called"
    NO_ANSWER = "no_answer"
    VOICEMAIL = "voicemail"
    BUSY = "busy"
    WRONG_NUMBER = "wrong_number"
    DISCONNECTED = "disconnected"
    DNC_REQUEST = "dnc_request"  # Do Not Call request
    NOT_INTERESTED = "not_interested"
    CALLBACK_REQUESTED = "callback_requested"
    INTERESTED = "interested"
    HOT_LEAD = "hot_lead"
    DEAL_MADE = "deal_made"


class LeadStatus(Enum):
    """Lead lifecycle status."""
    NEW = "new"
    IN_QUEUE = "in_queue"
    CALLING = "calling"
    CONTACTED = "contacted"
    FOLLOW_UP = "follow_up"
    HOT = "hot"
    DEAD = "dead"
    CONVERTED = "converted"


class CallManager:
    """Manages call queue, tracking, and lead dispositions."""

    def __init__(self, data_dir: str = None):
        """Initialize call manager."""
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).parent.parent / 'data'
        self.calls_file = self.data_dir / 'call_history.json'
        self.queue_file = self.data_dir / 'call_queue.json'

        # Ensure data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Load existing data
        self.call_history = self._load_json(self.calls_file, [])
        self.call_queue = self._load_json(self.queue_file, [])

    def _load_json(self, filepath: Path, default) -> any:
        """Load JSON file or return default."""
        if filepath.exists():
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except:
                return default
        return default

    def _save_json(self, filepath: Path, data: any):
        """Save data to JSON file."""
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

    def load_leads_to_queue(self, csv_path: str, filter_criteria: Dict = None) -> int:
        """
        Load leads from CSV into call queue.

        Args:
            csv_path: Path to leads CSV file
            filter_criteria: Optional filters (min_score, has_phone, etc.)

        Returns:
            Number of leads added to queue
        """
        df = pd.read_csv(csv_path)

        # Apply filters
        if filter_criteria:
            if 'min_score' in filter_criteria:
                if 'motivation_score' in df.columns:
                    df = df[df['motivation_score'] >= filter_criteria['min_score']]
            if 'has_phone' in filter_criteria and filter_criteria['has_phone']:
                phone_cols = [c for c in df.columns if 'phone' in c.lower()]
                if phone_cols:
                    df = df[df[phone_cols[0]].notna() & (df[phone_cols[0]] != '')]
            if 'tier' in filter_criteria:
                if 'tier' in df.columns:
                    df = df[df['tier'] <= filter_criteria['tier']]

        # Add leads to queue
        added = 0
        existing_addresses = {lead.get('address') for lead in self.call_queue}

        for _, row in df.iterrows():
            address = row.get('address', row.get('property_address', ''))
            if address and address not in existing_addresses:
                # Find phone number
                phone = None
                for col in ['phone', 'phone_1', 'owner_phone', 'contact_phone']:
                    if col in row and pd.notna(row[col]) and row[col]:
                        phone = str(row[col])
                        break

                if phone:
                    lead_data = {
                        'id': f"lead_{len(self.call_queue) + added + 1}",
                        'address': address,
                        'owner_name': row.get('owner_name', ''),
                        'phone': phone,
                        'phone_2': row.get('phone_2', ''),
                        'phone_3': row.get('phone_3', ''),
                        'email': row.get('email', ''),
                        'motivation_score': row.get('motivation_score', 0),
                        'tier': row.get('tier', 5),
                        'reasons': row.get('reasons', ''),
                        'status': LeadStatus.IN_QUEUE.value,
                        'disposition': CallDisposition.NOT_CALLED.value,
                        'call_attempts': 0,
                        'last_called': None,
                        'next_callback': None,
                        'notes': '',
                        'added_to_queue': datetime.now().isoformat(),
                    }
                    self.call_queue.append(lead_data)
                    existing_addresses.add(address)
                    added += 1

        self._save_json(self.queue_file, self.call_queue)
        return added

    def get_next_lead(self, va_id: str = None) -> Optional[Dict]:
        """
        Get next lead from queue for calling.

        Prioritizes by:
        1. Scheduled callbacks that are due
        2. Highest motivation score
        3. Lowest call attempts
        """
        now = datetime.now()

        # First check for due callbacks
        for lead in self.call_queue:
            if lead['status'] == LeadStatus.FOLLOW_UP.value and lead.get('next_callback'):
                callback_time = datetime.fromisoformat(lead['next_callback'])
                if callback_time <= now:
                    lead['status'] = LeadStatus.CALLING.value
                    lead['assigned_to'] = va_id
                    self._save_json(self.queue_file, self.call_queue)
                    return lead

        # Then get highest priority uncalled/in_queue lead
        available = [
            lead for lead in self.call_queue
            if lead['status'] in [LeadStatus.IN_QUEUE.value, LeadStatus.NEW.value]
        ]

        if not available:
            return None

        # Sort by motivation score (desc), then by call attempts (asc)
        available.sort(key=lambda x: (-x.get('motivation_score', 0), x.get('call_attempts', 0)))

        lead = available[0]
        lead['status'] = LeadStatus.CALLING.value
        lead['assigned_to'] = va_id
        self._save_json(self.queue_file, self.call_queue)
        return lead

    def record_call(self, lead_id: str, disposition: str, duration: int = 0,
                    notes: str = '', call_sid: str = None, va_id: str = None,
                    callback_date: str = None) -> bool:
        """
        Record call outcome and update lead status.

        Args:
            lead_id: Lead identifier
            disposition: Call disposition (from CallDisposition enum)
            duration: Call duration in seconds
            notes: Call notes
            call_sid: Twilio call SID
            va_id: VA who made the call
            callback_date: ISO format date for callback (if applicable)
        """
        # Find lead in queue
        lead = None
        for l in self.call_queue:
            if l['id'] == lead_id:
                lead = l
                break

        if not lead:
            return False

        # Update lead
        lead['call_attempts'] = lead.get('call_attempts', 0) + 1
        lead['last_called'] = datetime.now().isoformat()
        lead['disposition'] = disposition

        # Update status based on disposition
        if disposition in [CallDisposition.HOT_LEAD.value, CallDisposition.INTERESTED.value]:
            lead['status'] = LeadStatus.HOT.value
        elif disposition == CallDisposition.CALLBACK_REQUESTED.value:
            lead['status'] = LeadStatus.FOLLOW_UP.value
            if callback_date:
                lead['next_callback'] = callback_date
        elif disposition in [CallDisposition.DNC_REQUEST.value, CallDisposition.WRONG_NUMBER.value,
                             CallDisposition.DISCONNECTED.value]:
            lead['status'] = LeadStatus.DEAD.value
        elif disposition == CallDisposition.DEAL_MADE.value:
            lead['status'] = LeadStatus.CONVERTED.value
        elif disposition == CallDisposition.NOT_INTERESTED.value:
            lead['status'] = LeadStatus.DEAD.value
        else:
            # No answer, voicemail, busy - keep in queue for retry
            if lead.get('call_attempts', 0) >= 5:
                lead['status'] = LeadStatus.DEAD.value
            else:
                lead['status'] = LeadStatus.IN_QUEUE.value

        if notes:
            existing_notes = lead.get('notes', '')
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            lead['notes'] = f"{existing_notes}\n[{timestamp}] {notes}".strip()

        # Record in call history
        call_record = {
            'id': f"call_{len(self.call_history) + 1}",
            'lead_id': lead_id,
            'address': lead.get('address'),
            'phone': lead.get('phone'),
            'disposition': disposition,
            'duration': duration,
            'notes': notes,
            'call_sid': call_sid,
            'va_id': va_id,
            'timestamp': datetime.now().isoformat(),
        }
        self.call_history.append(call_record)

        # Save both files
        self._save_json(self.queue_file, self.call_queue)
        self._save_json(self.calls_file, self.call_history)

        return True

    def get_queue_stats(self) -> Dict:
        """Get statistics about the call queue."""
        stats = {
            'total_in_queue': len(self.call_queue),
            'by_status': {},
            'by_disposition': {},
            'hot_leads': 0,
            'callbacks_due': 0,
            'total_calls_made': len(self.call_history),
        }

        now = datetime.now()

        for lead in self.call_queue:
            # Count by status
            status = lead.get('status', 'unknown')
            stats['by_status'][status] = stats['by_status'].get(status, 0) + 1

            # Count by disposition
            disp = lead.get('disposition', 'unknown')
            stats['by_disposition'][disp] = stats['by_disposition'].get(disp, 0) + 1

            # Count hot leads
            if lead.get('status') == LeadStatus.HOT.value:
                stats['hot_leads'] += 1

            # Count due callbacks
            if lead.get('next_callback'):
                try:
                    cb_time = datetime.fromisoformat(lead['next_callback'])
                    if cb_time <= now:
                        stats['callbacks_due'] += 1
                except:
                    pass

        return stats

    def get_va_stats(self, va_id: str = None, date_from: str = None) -> Dict:
        """Get call statistics for VA(s)."""
        calls = self.call_history

        if date_from:
            from_dt = datetime.fromisoformat(date_from)
            calls = [c for c in calls if datetime.fromisoformat(c['timestamp']) >= from_dt]

        if va_id:
            calls = [c for c in calls if c.get('va_id') == va_id]

        stats = {
            'total_calls': len(calls),
            'total_duration': sum(c.get('duration', 0) for c in calls),
            'by_disposition': {},
            'hot_leads': 0,
            'conversion_rate': 0,
        }

        for call in calls:
            disp = call.get('disposition', 'unknown')
            stats['by_disposition'][disp] = stats['by_disposition'].get(disp, 0) + 1

            if disp in [CallDisposition.HOT_LEAD.value, CallDisposition.INTERESTED.value]:
                stats['hot_leads'] += 1

        if stats['total_calls'] > 0:
            stats['conversion_rate'] = (stats['hot_leads'] / stats['total_calls']) * 100

        return stats

    def get_hot_leads(self) -> List[Dict]:
        """Get all hot/interested leads."""
        return [
            lead for lead in self.call_queue
            if lead.get('status') == LeadStatus.HOT.value
        ]

    def get_callbacks(self) -> List[Dict]:
        """Get all scheduled callbacks."""
        callbacks = [
            lead for lead in self.call_queue
            if lead.get('status') == LeadStatus.FOLLOW_UP.value and lead.get('next_callback')
        ]
        callbacks.sort(key=lambda x: x.get('next_callback', ''))
        return callbacks

    def export_hot_leads(self, output_path: str) -> int:
        """Export hot leads to CSV."""
        hot_leads = self.get_hot_leads()
        if not hot_leads:
            return 0

        df = pd.DataFrame(hot_leads)
        df.to_csv(output_path, index=False)
        return len(hot_leads)

    def remove_from_queue(self, lead_id: str) -> bool:
        """Remove a lead from the queue."""
        for i, lead in enumerate(self.call_queue):
            if lead['id'] == lead_id:
                self.call_queue.pop(i)
                self._save_json(self.queue_file, self.call_queue)
                return True
        return False

    def clear_queue(self) -> int:
        """Clear the entire call queue. Returns count of removed leads."""
        count = len(self.call_queue)
        self.call_queue = []
        self._save_json(self.queue_file, self.call_queue)
        return count
