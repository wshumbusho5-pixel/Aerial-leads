"""
Aerial Leads - VA (Virtual Assistant) Management

Manage VAs, assign leads, track performance, and monitor calling activities.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import hashlib
import secrets

from shared.config.settings import PROCESSED_DATA_DIR
from shared.config.logging_config import get_logger


class VAManager:
    """
    Manage Virtual Assistants and their lead assignments.

    Features:
    - Add/remove VAs with login credentials
    - Assign leads to specific VAs
    - Track VA performance metrics
    - Role-based access (admin vs VA)
    """

    ROLES = ['admin', 'va']

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.users_file = PROCESSED_DATA_DIR / 'users.csv'
        self.assignments_file = PROCESSED_DATA_DIR / 'lead_assignments.csv'

        self._init_files()

    def _init_files(self):
        """Initialize user and assignment files."""
        # Users columns
        user_cols = [
            'user_id', 'username', 'password_hash', 'name', 'email',
            'role', 'daily_quota', 'is_active', 'created_at', 'last_login'
        ]

        # Lead assignments columns
        assignment_cols = [
            'assignment_id', 'lead_id', 'address', 'owner_name', 'phone',
            'assigned_to', 'assigned_by', 'assigned_date', 'due_date',
            'priority', 'status', 'notes', 'motivation_score'
        ]

        if not self.users_file.exists():
            df = pd.DataFrame(columns=user_cols)
            df.to_csv(self.users_file, index=False)
            # Create default admin
            self._create_default_admin()
            self.logger.info(f"Created users file: {self.users_file}")

        if not self.assignments_file.exists():
            pd.DataFrame(columns=assignment_cols).to_csv(self.assignments_file, index=False)
            self.logger.info(f"Created assignments file: {self.assignments_file}")

    def _create_default_admin(self):
        """Create default admin user."""
        self.add_user(
            username='admin',
            password='admin123',  # User should change this!
            name='Administrator',
            email='admin@aerial-leads.com',
            role='admin'
        )

    def _hash_password(self, password: str) -> str:
        """Hash password for storage."""
        return hashlib.sha256(password.encode()).hexdigest()

    # ==================== USER MANAGEMENT ====================

    def add_user(
        self,
        username: str,
        password: str,
        name: str,
        email: str = '',
        role: str = 'va',
        daily_quota: int = 50
    ) -> Dict:
        """
        Add a new user (VA or admin).

        Args:
            username: Login username
            password: Login password
            name: Display name
            email: Email address
            role: 'admin' or 'va'
            daily_quota: Daily call target for VAs

        Returns:
            Dict with user info
        """
        users_df = pd.read_csv(self.users_file)

        # Check if username exists
        if username.lower() in users_df['username'].str.lower().values:
            return {'success': False, 'error': 'Username already exists'}

        user_id = f"USER-{secrets.token_hex(4).upper()}"
        now = datetime.now()

        new_user = {
            'user_id': user_id,
            'username': username.lower(),
            'password_hash': self._hash_password(password),
            'name': name,
            'email': email,
            'role': role,
            'daily_quota': daily_quota,
            'is_active': True,
            'created_at': now.isoformat(),
            'last_login': ''
        }

        users_df = pd.concat([users_df, pd.DataFrame([new_user])], ignore_index=True)
        users_df.to_csv(self.users_file, index=False)

        self.logger.info(f"Added user: {username} ({role})")

        return {
            'success': True,
            'user_id': user_id,
            'username': username,
            'role': role
        }

    def authenticate(self, username: str, password: str) -> Optional[Dict]:
        """
        Authenticate a user.

        Returns:
            User dict if valid, None if invalid
        """
        users_df = pd.read_csv(self.users_file)

        user = users_df[
            (users_df['username'].str.lower() == username.lower()) &
            (users_df['is_active'] == True)
        ]

        if user.empty:
            return None

        user_row = user.iloc[0]

        if user_row['password_hash'] != self._hash_password(password):
            return None

        # Update last login
        idx = user.index[0]
        users_df.at[idx, 'last_login'] = datetime.now().isoformat()
        users_df.to_csv(self.users_file, index=False)

        return {
            'user_id': user_row['user_id'],
            'username': user_row['username'],
            'name': user_row['name'],
            'role': user_row['role'],
            'daily_quota': user_row['daily_quota']
        }

    def get_all_vas(self) -> pd.DataFrame:
        """Get all VA users."""
        users_df = pd.read_csv(self.users_file)
        return users_df[users_df['role'] == 'va']

    def get_all_users(self) -> pd.DataFrame:
        """Get all users."""
        users_df = pd.read_csv(self.users_file)
        # Don't expose password hash
        return users_df.drop(columns=['password_hash'])

    def deactivate_user(self, user_id: str):
        """Deactivate a user (soft delete)."""
        users_df = pd.read_csv(self.users_file)
        idx = users_df[users_df['user_id'] == user_id].index
        if len(idx) > 0:
            users_df.at[idx[0], 'is_active'] = False
            users_df.to_csv(self.users_file, index=False)
            self.logger.info(f"Deactivated user: {user_id}")

    def update_quota(self, user_id: str, new_quota: int):
        """Update a VA's daily quota."""
        users_df = pd.read_csv(self.users_file)
        idx = users_df[users_df['user_id'] == user_id].index
        if len(idx) > 0:
            users_df.at[idx[0], 'daily_quota'] = new_quota
            users_df.to_csv(self.users_file, index=False)

    def reset_password(self, user_id: str, new_password: str):
        """Reset a user's password."""
        users_df = pd.read_csv(self.users_file)
        idx = users_df[users_df['user_id'] == user_id].index
        if len(idx) > 0:
            users_df.at[idx[0], 'password_hash'] = self._hash_password(new_password)
            users_df.to_csv(self.users_file, index=False)
            self.logger.info(f"Reset password for user: {user_id}")

    # ==================== LEAD ASSIGNMENT ====================

    def assign_leads(
        self,
        leads_df: pd.DataFrame,
        va_user_id: str,
        assigned_by: str = 'admin',
        due_date: Optional[str] = None,
        priority: int = 3
    ) -> int:
        """
        Assign a batch of leads to a VA.

        Args:
            leads_df: DataFrame with leads to assign
            va_user_id: User ID of the VA
            assigned_by: Who assigned (user_id or 'admin')
            due_date: Optional due date (YYYY-MM-DD)
            priority: 1-5 (1 = urgent)

        Returns:
            Number of leads assigned
        """
        assignments_df = pd.read_csv(self.assignments_file)
        now = datetime.now()

        new_assignments = []

        for _, lead in leads_df.iterrows():
            address = lead.get('address', '')

            # Skip if already assigned to this VA
            existing = assignments_df[
                (assignments_df['address'] == address) &
                (assignments_df['assigned_to'] == va_user_id) &
                (assignments_df['status'] != 'completed')
            ]

            if not existing.empty:
                continue

            assignment_id = f"ASSIGN-{now.strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"

            new_assignments.append({
                'assignment_id': assignment_id,
                'lead_id': lead.get('lead_id', ''),
                'address': address,
                'owner_name': lead.get('owner_name', ''),
                'phone': lead.get('phone', ''),
                'assigned_to': va_user_id,
                'assigned_by': assigned_by,
                'assigned_date': now.strftime('%Y-%m-%d'),
                'due_date': due_date or '',
                'priority': priority,
                'status': 'pending',
                'notes': '',
                'motivation_score': lead.get('motivation_score', 0)
            })

        if new_assignments:
            assignments_df = pd.concat([
                assignments_df,
                pd.DataFrame(new_assignments)
            ], ignore_index=True)
            assignments_df.to_csv(self.assignments_file, index=False)

        self.logger.info(f"Assigned {len(new_assignments)} leads to {va_user_id}")
        return len(new_assignments)

    def auto_distribute_leads(
        self,
        leads_df: pd.DataFrame,
        distribution: str = 'equal'
    ) -> Dict:
        """
        Automatically distribute leads among active VAs.

        Args:
            leads_df: DataFrame with leads to distribute
            distribution: 'equal', 'by_quota', or 'by_performance'

        Returns:
            Dict with assignment counts per VA
        """
        vas = self.get_all_vas()
        active_vas = vas[vas['is_active'] == True]

        if active_vas.empty:
            return {'error': 'No active VAs'}

        results = {}
        leads_list = leads_df.to_dict('records')

        if distribution == 'equal':
            # Split equally
            num_vas = len(active_vas)
            chunk_size = len(leads_list) // num_vas

            for i, (_, va) in enumerate(active_vas.iterrows()):
                start = i * chunk_size
                end = start + chunk_size if i < num_vas - 1 else len(leads_list)

                va_leads = pd.DataFrame(leads_list[start:end])
                assigned = self.assign_leads(va_leads, va['user_id'])
                results[va['name']] = assigned

        elif distribution == 'by_quota':
            # Distribute based on daily quota
            total_quota = active_vas['daily_quota'].sum()
            lead_idx = 0

            for _, va in active_vas.iterrows():
                # Proportion based on quota
                proportion = va['daily_quota'] / total_quota
                num_leads = int(len(leads_list) * proportion)

                va_leads = pd.DataFrame(leads_list[lead_idx:lead_idx + num_leads])
                assigned = self.assign_leads(va_leads, va['user_id'])
                results[va['name']] = assigned
                lead_idx += num_leads

        return results

    def get_va_assignments(
        self,
        va_user_id: str,
        status: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Get leads assigned to a specific VA.

        Args:
            va_user_id: The VA's user ID
            status: Filter by status ('pending', 'in_progress', 'completed')

        Returns:
            DataFrame of assigned leads
        """
        assignments_df = pd.read_csv(self.assignments_file)

        va_assignments = assignments_df[assignments_df['assigned_to'] == va_user_id]

        if status:
            va_assignments = va_assignments[va_assignments['status'] == status]

        return va_assignments.sort_values(['priority', 'assigned_date'])

    def update_assignment_status(
        self,
        assignment_id: str,
        new_status: str,
        notes: str = ''
    ):
        """Update the status of an assignment."""
        assignments_df = pd.read_csv(self.assignments_file)

        idx = assignments_df[assignments_df['assignment_id'] == assignment_id].index
        if len(idx) > 0:
            assignments_df.at[idx[0], 'status'] = new_status
            if notes:
                existing = assignments_df.at[idx[0], 'notes'] or ''
                assignments_df.at[idx[0], 'notes'] = f"{existing}\n{notes}".strip()

            assignments_df.to_csv(self.assignments_file, index=False)

    def unassign_lead(self, assignment_id: str):
        """Remove a lead assignment."""
        assignments_df = pd.read_csv(self.assignments_file)
        assignments_df = assignments_df[assignments_df['assignment_id'] != assignment_id]
        assignments_df.to_csv(self.assignments_file, index=False)

    # ==================== PERFORMANCE TRACKING ====================

    def get_va_performance(
        self,
        va_user_id: str,
        days: int = 7
    ) -> Dict:
        """
        Get performance metrics for a VA.

        Args:
            va_user_id: The VA's user ID
            days: Number of days to analyze

        Returns:
            Dict with performance metrics
        """
        # Load call log
        calls_file = PROCESSED_DATA_DIR / 'call_log.csv'
        if not calls_file.exists():
            return self._empty_performance()

        calls_df = pd.read_csv(calls_file)

        # Filter to this VA's calls (by matching assignments)
        assignments = self.get_va_assignments(va_user_id)
        va_addresses = assignments['address'].str.upper().tolist()

        # Filter calls by address and date
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

        va_calls = calls_df[
            (calls_df['address'].str.upper().isin(va_addresses)) &
            (calls_df['call_date'] >= cutoff)
        ]

        if va_calls.empty:
            return self._empty_performance()

        # Calculate metrics
        total_calls = len(va_calls)

        conversations = va_calls[va_calls['outcome'].isin([
            'Not Interested', 'Call Back Later', 'Interested',
            'Appointment Set', 'Offer Made'
        ])]

        interested = va_calls[va_calls['outcome'].isin([
            'Interested', 'Appointment Set', 'Offer Made'
        ])]

        appointments = va_calls[va_calls['outcome'] == 'Appointment Set']

        # Calls per day
        call_dates = va_calls['call_date'].nunique()
        calls_per_day = total_calls / max(call_dates, 1)

        # Conversion rate
        conversion_rate = (len(interested) / total_calls * 100) if total_calls > 0 else 0

        return {
            'total_calls': total_calls,
            'conversations': len(conversations),
            'interested': len(interested),
            'appointments': len(appointments),
            'calls_per_day': round(calls_per_day, 1),
            'conversion_rate': round(conversion_rate, 1),
            'contact_rate': round(len(conversations) / total_calls * 100, 1) if total_calls > 0 else 0
        }

    def _empty_performance(self) -> Dict:
        """Return empty performance metrics."""
        return {
            'total_calls': 0,
            'conversations': 0,
            'interested': 0,
            'appointments': 0,
            'calls_per_day': 0,
            'conversion_rate': 0,
            'contact_rate': 0
        }

    def get_all_va_performance(self, days: int = 7) -> pd.DataFrame:
        """Get performance metrics for all VAs."""
        vas = self.get_all_vas()

        results = []
        for _, va in vas.iterrows():
            perf = self.get_va_performance(va['user_id'], days)
            perf['user_id'] = va['user_id']
            perf['name'] = va['name']
            perf['quota'] = va['daily_quota']
            results.append(perf)

        return pd.DataFrame(results)

    def get_team_stats(self, days: int = 7) -> Dict:
        """Get aggregated team statistics."""
        all_perf = self.get_all_va_performance(days)

        if all_perf.empty:
            return {
                'total_vas': 0,
                'total_calls': 0,
                'total_appointments': 0,
                'avg_conversion_rate': 0,
                'top_performer': 'N/A'
            }

        return {
            'total_vas': len(all_perf),
            'total_calls': int(all_perf['total_calls'].sum()),
            'total_appointments': int(all_perf['appointments'].sum()),
            'avg_conversion_rate': round(all_perf['conversion_rate'].mean(), 1),
            'top_performer': all_perf.loc[all_perf['appointments'].idxmax(), 'name'] if all_perf['appointments'].sum() > 0 else 'N/A'
        }

    # ==================== TODAY'S DASHBOARD ====================

    def get_va_today_progress(self, va_user_id: str) -> Dict:
        """Get a VA's progress for today."""
        # Get user quota
        users_df = pd.read_csv(self.users_file)
        user = users_df[users_df['user_id'] == va_user_id]
        quota = int(user.iloc[0]['daily_quota']) if not user.empty else 50

        # Get today's calls
        calls_file = PROCESSED_DATA_DIR / 'call_log.csv'
        if not calls_file.exists():
            return {'calls': 0, 'quota': quota, 'progress_pct': 0}

        calls_df = pd.read_csv(calls_file)
        today = datetime.now().strftime('%Y-%m-%d')

        # Get VA's assignments
        assignments = self.get_va_assignments(va_user_id)
        va_addresses = assignments['address'].str.upper().tolist()

        today_calls = calls_df[
            (calls_df['address'].str.upper().isin(va_addresses)) &
            (calls_df['call_date'] == today)
        ]

        calls_made = len(today_calls)
        progress_pct = min(100, int(calls_made / quota * 100))

        return {
            'calls': calls_made,
            'quota': quota,
            'progress_pct': progress_pct,
            'remaining': max(0, quota - calls_made)
        }


# Example usage
if __name__ == '__main__':
    manager = VAManager()

    # Add some VAs
    print("Adding VAs...")
    manager.add_user('maria', 'password123', 'Maria Garcia', role='va', daily_quota=50)
    manager.add_user('juan', 'password123', 'Juan Rodriguez', role='va', daily_quota=40)

    # List VAs
    print("\nAll VAs:")
    print(manager.get_all_vas()[['username', 'name', 'daily_quota']])

    # Test authentication
    print("\nTesting login...")
    user = manager.authenticate('maria', 'password123')
    print(f"Logged in: {user}")

    print("\nVA Manager initialized successfully!")
