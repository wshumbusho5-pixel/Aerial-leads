"""
Aerial Leads - Automated Follow-up Sequences

Automatically follow up with leads over time.
Never let a lead go cold - consistent follow-up wins deals!

Features:
- Multi-step follow-up sequences
- Multiple channels (call, SMS, RVM, mail)
- Scheduling and execution
- Lead assignment to sequences
- Pause/resume controls
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import uuid
import json

from config.settings import DATA_DIR
from config.logging_config import get_logger

logger = get_logger("FollowUpSequences")

# Follow-up action types
ACTION_TYPES = [
    "call",       # Phone call
    "sms",        # Text message
    "rvm",        # Ringless voicemail
    "email",      # Email (future)
    "mail",       # Direct mail
    "task"        # Manual task/reminder
]

ACTION_TYPE_DISPLAY = {
    "call": "📞 Phone Call",
    "sms": "💬 Text Message",
    "rvm": "📱 Ringless Voicemail",
    "email": "📧 Email",
    "mail": "📬 Direct Mail",
    "task": "📋 Manual Task"
}

SEQUENCE_STATUS = [
    "active",     # Currently running
    "paused",     # Temporarily stopped
    "completed",  # All steps done
    "stopped",    # Manually stopped
    "converted"   # Lead converted to deal
]

LEAD_SEQUENCE_STATUS = [
    "active",     # In sequence
    "paused",     # Paused for this lead
    "completed",  # Finished all steps
    "responded",  # Lead responded
    "converted",  # Became a deal
    "removed"     # Manually removed
]

# Data files
SEQUENCES_FILE = DATA_DIR / "follow_up_sequences.csv"
SEQUENCE_STEPS_FILE = DATA_DIR / "sequence_steps.csv"
LEAD_SEQUENCES_FILE = DATA_DIR / "lead_sequences.csv"
SEQUENCE_ACTIONS_FILE = DATA_DIR / "sequence_actions.csv"

# Default sequences
DEFAULT_SEQUENCES = {
    "new_lead_7day": {
        "name": "New Lead - 7 Day Follow-up",
        "description": "Standard follow-up for new leads over 7 days",
        "steps": [
            {"day": 0, "action": "call", "description": "Initial call - introduce yourself"},
            {"day": 0, "action": "sms", "description": "Send intro text if no answer"},
            {"day": 1, "action": "call", "description": "Day 1 follow-up call"},
            {"day": 2, "action": "rvm", "description": "Drop RVM - mention cash offer"},
            {"day": 3, "action": "call", "description": "Day 3 check-in"},
            {"day": 5, "action": "sms", "description": "Text: Still interested?"},
            {"day": 7, "action": "call", "description": "Final attempt - last call"},
        ]
    },
    "probate_gentle": {
        "name": "Probate - Gentle Approach",
        "description": "Sensitive follow-up for probate leads",
        "steps": [
            {"day": 0, "action": "mail", "description": "Send condolence letter"},
            {"day": 7, "action": "call", "description": "Gentle intro call"},
            {"day": 14, "action": "sms", "description": "Text: Here to help when ready"},
            {"day": 21, "action": "call", "description": "Follow-up call"},
            {"day": 30, "action": "mail", "description": "Second letter - cash offer"},
            {"day": 45, "action": "call", "description": "Check-in call"},
        ]
    },
    "hot_lead_aggressive": {
        "name": "Hot Lead - Aggressive",
        "description": "For high-motivation leads - move fast!",
        "steps": [
            {"day": 0, "action": "call", "description": "Call immediately!"},
            {"day": 0, "action": "sms", "description": "Text: Can close in 7 days"},
            {"day": 0, "action": "rvm", "description": "RVM: Cash buyer ready"},
            {"day": 1, "action": "call", "description": "Morning call"},
            {"day": 1, "action": "call", "description": "Afternoon call"},
            {"day": 2, "action": "call", "description": "Day 2 push"},
            {"day": 2, "action": "sms", "description": "Text: Making offers today"},
            {"day": 3, "action": "call", "description": "Last attempt"},
        ]
    }
}


class FollowUpSequences:
    """
    Manage automated follow-up sequences for leads.
    """

    def __init__(self):
        self._init_files()

    def _init_files(self):
        """Initialize data files."""
        needs_default_sequences = not SEQUENCES_FILE.exists()

        if not SEQUENCES_FILE.exists():
            df = pd.DataFrame(columns=[
                'sequence_id', 'name', 'description', 'status',
                'total_steps', 'created_at', 'created_by',
                'leads_enrolled', 'leads_completed', 'leads_converted'
            ])
            df.to_csv(SEQUENCES_FILE, index=False)

        if not SEQUENCE_STEPS_FILE.exists():
            df = pd.DataFrame(columns=[
                'step_id', 'sequence_id', 'step_number', 'day_offset',
                'action_type', 'description', 'template_id'
            ])
            df.to_csv(SEQUENCE_STEPS_FILE, index=False)

        if not LEAD_SEQUENCES_FILE.exists():
            df = pd.DataFrame(columns=[
                'enrollment_id', 'lead_id', 'sequence_id',
                'enrolled_at', 'status', 'current_step',
                'next_action_date', 'completed_at',
                'lead_address', 'lead_phone', 'lead_name',
                'assigned_to', 'notes'
            ])
            df.to_csv(LEAD_SEQUENCES_FILE, index=False)

        if not SEQUENCE_ACTIONS_FILE.exists():
            df = pd.DataFrame(columns=[
                'action_id', 'enrollment_id', 'step_id',
                'scheduled_date', 'executed_at', 'status',
                'result', 'notes', 'executed_by'
            ])
            df.to_csv(SEQUENCE_ACTIONS_FILE, index=False)

        # Create default sequences AFTER all files exist
        if needs_default_sequences:
            for seq_id, seq_data in DEFAULT_SEQUENCES.items():
                self._create_default_sequence(seq_id, seq_data)

    def _create_default_sequence(self, seq_id: str, seq_data: Dict):
        """Create a default sequence with steps."""
        sequence = {
            'sequence_id': seq_id,
            'name': seq_data['name'],
            'description': seq_data['description'],
            'status': 'active',
            'total_steps': len(seq_data['steps']),
            'created_at': datetime.now().isoformat(),
            'created_by': 'system',
            'leads_enrolled': 0,
            'leads_completed': 0,
            'leads_converted': 0
        }

        # Save sequence
        seq_df = pd.read_csv(SEQUENCES_FILE)
        seq_df = pd.concat([seq_df, pd.DataFrame([sequence])], ignore_index=True)
        seq_df.to_csv(SEQUENCES_FILE, index=False)

        # Save steps
        steps_df = pd.read_csv(SEQUENCE_STEPS_FILE)
        for i, step in enumerate(seq_data['steps']):
            step_record = {
                'step_id': f"{seq_id}_step_{i+1}",
                'sequence_id': seq_id,
                'step_number': i + 1,
                'day_offset': step['day'],
                'action_type': step['action'],
                'description': step['description'],
                'template_id': ''
            }
            steps_df = pd.concat([steps_df, pd.DataFrame([step_record])], ignore_index=True)

        steps_df.to_csv(SEQUENCE_STEPS_FILE, index=False)

    def get_all_sequences(self, status: str = None) -> pd.DataFrame:
        """Get all sequences."""
        df = pd.read_csv(SEQUENCES_FILE)
        if status:
            df = df[df['status'] == status]
        return df

    def get_sequence(self, sequence_id: str) -> Optional[Dict]:
        """Get a single sequence."""
        df = pd.read_csv(SEQUENCES_FILE)
        seq = df[df['sequence_id'] == sequence_id]
        if seq.empty:
            return None
        return seq.iloc[0].to_dict()

    def get_sequence_steps(self, sequence_id: str) -> pd.DataFrame:
        """Get steps for a sequence."""
        df = pd.read_csv(SEQUENCE_STEPS_FILE)
        return df[df['sequence_id'] == sequence_id].sort_values('step_number')

    def create_sequence(
        self,
        name: str,
        description: str = "",
        steps: List[Dict] = None,
        created_by: str = ""
    ) -> str:
        """
        Create a new follow-up sequence.

        Args:
            name: Sequence name
            description: Description
            steps: List of step dicts with day_offset, action_type, description
            created_by: Who created

        Returns:
            sequence_id
        """
        sequence_id = f"SEQ-{datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:4].upper()}"
        steps = steps or []

        sequence = {
            'sequence_id': sequence_id,
            'name': name,
            'description': description,
            'status': 'active',
            'total_steps': len(steps),
            'created_at': datetime.now().isoformat(),
            'created_by': created_by,
            'leads_enrolled': 0,
            'leads_completed': 0,
            'leads_converted': 0
        }

        # Save sequence
        df = pd.read_csv(SEQUENCES_FILE)
        df = pd.concat([df, pd.DataFrame([sequence])], ignore_index=True)
        df.to_csv(SEQUENCES_FILE, index=False)

        # Save steps
        if steps:
            steps_df = pd.read_csv(SEQUENCE_STEPS_FILE)
            for i, step in enumerate(steps):
                step_record = {
                    'step_id': f"{sequence_id}_step_{i+1}",
                    'sequence_id': sequence_id,
                    'step_number': i + 1,
                    'day_offset': step.get('day_offset', step.get('day', 0)),
                    'action_type': step.get('action_type', step.get('action', 'task')),
                    'description': step.get('description', ''),
                    'template_id': step.get('template_id', '')
                }
                steps_df = pd.concat([steps_df, pd.DataFrame([step_record])], ignore_index=True)
            steps_df.to_csv(SEQUENCE_STEPS_FILE, index=False)

        logger.info(f"Created sequence {sequence_id}: {name}")
        return sequence_id

    def enroll_lead(
        self,
        sequence_id: str,
        lead_data: Dict,
        assigned_to: str = "",
        notes: str = ""
    ) -> str:
        """
        Enroll a lead in a follow-up sequence.

        Args:
            sequence_id: The sequence to enroll in
            lead_data: Lead information dict
            assigned_to: VA assigned
            notes: Enrollment notes

        Returns:
            enrollment_id
        """
        enrollment_id = f"ENR-{datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:4].upper()}"

        # Get first step info for next action date
        steps = self.get_sequence_steps(sequence_id)
        first_step = steps.iloc[0] if not steps.empty else None

        enrollment = {
            'enrollment_id': enrollment_id,
            'lead_id': lead_data.get('lead_id', str(uuid.uuid4())[:8]),
            'sequence_id': sequence_id,
            'enrolled_at': datetime.now().isoformat(),
            'status': 'active',
            'current_step': 1,
            'next_action_date': datetime.now().strftime('%Y-%m-%d') if first_step is not None and first_step['day_offset'] == 0 else (datetime.now() + timedelta(days=int(first_step['day_offset']) if first_step is not None else 1)).strftime('%Y-%m-%d'),
            'completed_at': '',
            'lead_address': lead_data.get('address', lead_data.get('property_address', '')),
            'lead_phone': lead_data.get('phone', lead_data.get('phone_1', '')),
            'lead_name': lead_data.get('owner_name', lead_data.get('owner', '')),
            'assigned_to': assigned_to,
            'notes': notes
        }

        df = pd.read_csv(LEAD_SEQUENCES_FILE)
        df = pd.concat([df, pd.DataFrame([enrollment])], ignore_index=True)
        df.to_csv(LEAD_SEQUENCES_FILE, index=False)

        # Update sequence enrolled count
        seq_df = pd.read_csv(SEQUENCES_FILE)
        idx = seq_df[seq_df['sequence_id'] == sequence_id].index
        if len(idx) > 0:
            seq_df.at[idx[0], 'leads_enrolled'] = int(seq_df.at[idx[0], 'leads_enrolled']) + 1
            seq_df.to_csv(SEQUENCES_FILE, index=False)

        # Create action records for all steps
        self._create_action_records(enrollment_id, sequence_id)

        logger.info(f"Enrolled lead in sequence {sequence_id}: {enrollment_id}")
        return enrollment_id

    def _create_action_records(self, enrollment_id: str, sequence_id: str):
        """Create action records for an enrollment."""
        steps = self.get_sequence_steps(sequence_id)
        enrollment = self.get_enrollment(enrollment_id)

        if enrollment is None:
            return

        actions_df = pd.read_csv(SEQUENCE_ACTIONS_FILE)
        enrolled_date = datetime.fromisoformat(enrollment['enrolled_at'])

        for _, step in steps.iterrows():
            action = {
                'action_id': f"ACT-{str(uuid.uuid4())[:8].upper()}",
                'enrollment_id': enrollment_id,
                'step_id': step['step_id'],
                'scheduled_date': (enrolled_date + timedelta(days=int(step['day_offset']))).strftime('%Y-%m-%d'),
                'executed_at': '',
                'status': 'pending',
                'result': '',
                'notes': '',
                'executed_by': ''
            }
            actions_df = pd.concat([actions_df, pd.DataFrame([action])], ignore_index=True)

        actions_df.to_csv(SEQUENCE_ACTIONS_FILE, index=False)

    def get_enrollment(self, enrollment_id: str) -> Optional[Dict]:
        """Get an enrollment record."""
        df = pd.read_csv(LEAD_SEQUENCES_FILE)
        enr = df[df['enrollment_id'] == enrollment_id]
        if enr.empty:
            return None
        return enr.iloc[0].to_dict()

    def get_enrollments(self, sequence_id: str = None, status: str = None, assigned_to: str = None) -> pd.DataFrame:
        """Get enrollments with filters."""
        df = pd.read_csv(LEAD_SEQUENCES_FILE)

        if sequence_id:
            df = df[df['sequence_id'] == sequence_id]
        if status:
            df = df[df['status'] == status]
        if assigned_to:
            df = df[df['assigned_to'] == assigned_to]

        return df

    def get_todays_actions(self, assigned_to: str = None) -> pd.DataFrame:
        """Get actions scheduled for today."""
        today = datetime.now().strftime('%Y-%m-%d')

        actions_df = pd.read_csv(SEQUENCE_ACTIONS_FILE)
        actions_df = actions_df[(actions_df['scheduled_date'] == today) & (actions_df['status'] == 'pending')]

        # Join with enrollment data
        enroll_df = pd.read_csv(LEAD_SEQUENCES_FILE)
        steps_df = pd.read_csv(SEQUENCE_STEPS_FILE)

        result = actions_df.merge(enroll_df[['enrollment_id', 'lead_address', 'lead_phone', 'lead_name', 'assigned_to', 'status']], on='enrollment_id', how='left')
        result = result.merge(steps_df[['step_id', 'action_type', 'description', 'step_number']], on='step_id', how='left')

        # Filter by assigned_to if specified
        if assigned_to:
            result = result[result['assigned_to'] == assigned_to]

        # Filter out inactive enrollments
        result = result[result['status_y'] == 'active']

        return result.sort_values(['scheduled_date', 'step_number'])

    def get_upcoming_actions(self, days: int = 7, assigned_to: str = None) -> pd.DataFrame:
        """Get upcoming actions for the next N days."""
        today = datetime.now().strftime('%Y-%m-%d')
        end_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')

        actions_df = pd.read_csv(SEQUENCE_ACTIONS_FILE)
        actions_df = actions_df[
            (actions_df['scheduled_date'] >= today) &
            (actions_df['scheduled_date'] <= end_date) &
            (actions_df['status'] == 'pending')
        ]

        # Join with enrollment and steps
        enroll_df = pd.read_csv(LEAD_SEQUENCES_FILE)
        steps_df = pd.read_csv(SEQUENCE_STEPS_FILE)

        result = actions_df.merge(enroll_df[['enrollment_id', 'lead_address', 'lead_phone', 'lead_name', 'assigned_to', 'status']], on='enrollment_id', how='left')
        result = result.merge(steps_df[['step_id', 'action_type', 'description']], on='step_id', how='left')

        if assigned_to:
            result = result[result['assigned_to'] == assigned_to]

        result = result[result['status_y'] == 'active']

        return result.sort_values('scheduled_date')

    def complete_action(self, action_id: str, result: str = "", notes: str = "", executed_by: str = "") -> bool:
        """Mark an action as completed."""
        df = pd.read_csv(SEQUENCE_ACTIONS_FILE)
        idx = df[df['action_id'] == action_id].index

        if len(idx) == 0:
            return False

        df.at[idx[0], 'status'] = 'completed'
        df.at[idx[0], 'executed_at'] = datetime.now().isoformat()
        df.at[idx[0], 'result'] = result
        df.at[idx[0], 'notes'] = notes
        df.at[idx[0], 'executed_by'] = executed_by
        df.to_csv(SEQUENCE_ACTIONS_FILE, index=False)

        # Update enrollment current step
        enrollment_id = df.at[idx[0], 'enrollment_id']
        self._update_enrollment_progress(enrollment_id)

        logger.info(f"Completed action {action_id}")
        return True

    def skip_action(self, action_id: str, reason: str = "") -> bool:
        """Skip an action."""
        df = pd.read_csv(SEQUENCE_ACTIONS_FILE)
        idx = df[df['action_id'] == action_id].index

        if len(idx) == 0:
            return False

        df.at[idx[0], 'status'] = 'skipped'
        df.at[idx[0], 'notes'] = f"Skipped: {reason}"
        df.to_csv(SEQUENCE_ACTIONS_FILE, index=False)

        return True

    def _update_enrollment_progress(self, enrollment_id: str):
        """Update enrollment progress after action completion."""
        actions_df = pd.read_csv(SEQUENCE_ACTIONS_FILE)
        enroll_df = pd.read_csv(LEAD_SEQUENCES_FILE)

        # Get actions for this enrollment
        enrollment_actions = actions_df[actions_df['enrollment_id'] == enrollment_id]

        # Count completed
        completed = len(enrollment_actions[enrollment_actions['status'].isin(['completed', 'skipped'])])
        total = len(enrollment_actions)

        idx = enroll_df[enroll_df['enrollment_id'] == enrollment_id].index
        if len(idx) == 0:
            return

        enroll_df.at[idx[0], 'current_step'] = completed

        # Check if all done
        if completed >= total:
            enroll_df.at[idx[0], 'status'] = 'completed'
            enroll_df.at[idx[0], 'completed_at'] = datetime.now().isoformat()

            # Update sequence completed count
            sequence_id = enroll_df.at[idx[0], 'sequence_id']
            seq_df = pd.read_csv(SEQUENCES_FILE)
            seq_idx = seq_df[seq_df['sequence_id'] == sequence_id].index
            if len(seq_idx) > 0:
                seq_df.at[seq_idx[0], 'leads_completed'] = int(seq_df.at[seq_idx[0], 'leads_completed']) + 1
                seq_df.to_csv(SEQUENCES_FILE, index=False)

        enroll_df.to_csv(LEAD_SEQUENCES_FILE, index=False)

    def pause_enrollment(self, enrollment_id: str) -> bool:
        """Pause a lead's enrollment."""
        df = pd.read_csv(LEAD_SEQUENCES_FILE)
        idx = df[df['enrollment_id'] == enrollment_id].index
        if len(idx) == 0:
            return False
        df.at[idx[0], 'status'] = 'paused'
        df.to_csv(LEAD_SEQUENCES_FILE, index=False)
        return True

    def resume_enrollment(self, enrollment_id: str) -> bool:
        """Resume a paused enrollment."""
        df = pd.read_csv(LEAD_SEQUENCES_FILE)
        idx = df[df['enrollment_id'] == enrollment_id].index
        if len(idx) == 0:
            return False
        df.at[idx[0], 'status'] = 'active'
        df.to_csv(LEAD_SEQUENCES_FILE, index=False)
        return True

    def mark_converted(self, enrollment_id: str, deal_id: str = "") -> bool:
        """Mark a lead as converted (deal created)."""
        df = pd.read_csv(LEAD_SEQUENCES_FILE)
        idx = df[df['enrollment_id'] == enrollment_id].index
        if len(idx) == 0:
            return False

        df.at[idx[0], 'status'] = 'converted'
        df.at[idx[0], 'notes'] = f"{df.at[idx[0], 'notes']} | Converted to deal: {deal_id}".strip(' |')
        df.to_csv(LEAD_SEQUENCES_FILE, index=False)

        # Update sequence converted count
        sequence_id = df.at[idx[0], 'sequence_id']
        seq_df = pd.read_csv(SEQUENCES_FILE)
        seq_idx = seq_df[seq_df['sequence_id'] == sequence_id].index
        if len(seq_idx) > 0:
            seq_df.at[seq_idx[0], 'leads_converted'] = int(seq_df.at[seq_idx[0], 'leads_converted']) + 1
            seq_df.to_csv(SEQUENCES_FILE, index=False)

        return True

    def get_stats(self) -> Dict:
        """Get follow-up sequence statistics."""
        sequences = pd.read_csv(SEQUENCES_FILE)
        enrollments = pd.read_csv(LEAD_SEQUENCES_FILE)
        actions = pd.read_csv(SEQUENCE_ACTIONS_FILE)

        if sequences.empty:
            return {
                'total_sequences': 0,
                'active_sequences': 0,
                'total_enrolled': 0,
                'active_leads': 0,
                'completed_leads': 0,
                'converted_leads': 0,
                'todays_actions': 0,
                'pending_actions': 0,
                'conversion_rate': 0
            }

        today = datetime.now().strftime('%Y-%m-%d')
        todays_count = len(actions[(actions['scheduled_date'] == today) & (actions['status'] == 'pending')])

        active_leads = len(enrollments[enrollments['status'] == 'active'])
        completed = len(enrollments[enrollments['status'] == 'completed'])
        converted = len(enrollments[enrollments['status'] == 'converted'])

        total_finished = completed + converted
        conversion_rate = (converted / total_finished * 100) if total_finished > 0 else 0

        return {
            'total_sequences': len(sequences),
            'active_sequences': len(sequences[sequences['status'] == 'active']),
            'total_enrolled': len(enrollments),
            'active_leads': active_leads,
            'completed_leads': completed,
            'converted_leads': converted,
            'todays_actions': todays_count,
            'pending_actions': len(actions[actions['status'] == 'pending']),
            'conversion_rate': conversion_rate
        }


# Export
__all__ = [
    'FollowUpSequences',
    'ACTION_TYPES',
    'ACTION_TYPE_DISPLAY',
    'SEQUENCE_STATUS',
    'LEAD_SEQUENCE_STATUS',
    'DEFAULT_SEQUENCES'
]
