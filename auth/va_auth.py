"""
Aerial Leads - VA Authentication

Simple but effective authentication for Virtual Assistants.
Keeps unauthorized users out while remaining easy to use.

Features:
- Username/password login
- Session management
- Role-based access (admin vs VA)
- Password hashing
- Login attempt tracking
"""

import hashlib
import secrets
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import uuid

from config.settings import DATA_DIR
from config.logging_config import get_logger

logger = get_logger("VAAuth")

# Data files
USERS_FILE = DATA_DIR / "auth_users.csv"
SESSIONS_FILE = DATA_DIR / "auth_sessions.csv"
LOGIN_ATTEMPTS_FILE = DATA_DIR / "login_attempts.csv"

# Settings
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
SESSION_DURATION_HOURS = 8

# Roles
ROLES = ["admin", "va", "manager"]


class VAAuth:
    """
    Handle authentication for VA dashboard.
    """

    def __init__(self):
        self._init_files()

    def _init_files(self):
        """Initialize data files."""
        if not USERS_FILE.exists():
            df = pd.DataFrame(columns=[
                'user_id', 'username', 'password_hash', 'salt',
                'full_name', 'email', 'role',
                'created_at', 'last_login', 'is_active',
                'created_by'
            ])
            df.to_csv(USERS_FILE, index=False)

            # Create default admin user
            self.create_user(
                username="admin",
                password="admin123",  # Should be changed!
                full_name="System Admin",
                role="admin",
                email="",
                created_by="system"
            )

        if not SESSIONS_FILE.exists():
            df = pd.DataFrame(columns=[
                'session_id', 'user_id', 'username',
                'created_at', 'expires_at', 'ip_address',
                'is_active'
            ])
            df.to_csv(SESSIONS_FILE, index=False)

        if not LOGIN_ATTEMPTS_FILE.exists():
            df = pd.DataFrame(columns=[
                'attempt_id', 'username', 'timestamp',
                'success', 'ip_address', 'user_agent'
            ])
            df.to_csv(LOGIN_ATTEMPTS_FILE, index=False)

    def _hash_password(self, password: str, salt: str = None) -> Tuple[str, str]:
        """Hash a password with salt."""
        if salt is None:
            salt = secrets.token_hex(16)

        combined = f"{password}{salt}".encode('utf-8')
        hash_obj = hashlib.sha256(combined)
        password_hash = hash_obj.hexdigest()

        return password_hash, salt

    def create_user(
        self,
        username: str,
        password: str,
        full_name: str,
        role: str = "va",
        email: str = "",
        created_by: str = ""
    ) -> Optional[str]:
        """
        Create a new user.

        Args:
            username: Login username (unique)
            password: Plain text password (will be hashed)
            full_name: User's full name
            role: admin, va, or manager
            email: User's email
            created_by: Who created this user

        Returns:
            user_id if successful, None if username exists
        """
        # Check if username exists
        df = pd.read_csv(USERS_FILE)
        if not df.empty and username.lower() in df['username'].str.lower().values:
            logger.warning(f"Username already exists: {username}")
            return None

        if role not in ROLES:
            role = "va"

        user_id = f"USER-{datetime.now().strftime('%Y%m%d%H%M%S')}-{str(uuid.uuid4())[:4].upper()}"
        password_hash, salt = self._hash_password(password)

        user = {
            'user_id': user_id,
            'username': username.lower(),
            'password_hash': password_hash,
            'salt': salt,
            'full_name': full_name,
            'email': email,
            'role': role,
            'created_at': datetime.now().isoformat(),
            'last_login': '',
            'is_active': True,
            'created_by': created_by
        }

        df = pd.concat([df, pd.DataFrame([user])], ignore_index=True)
        df.to_csv(USERS_FILE, index=False)

        logger.info(f"Created user: {username} ({role})")
        return user_id

    def authenticate(
        self,
        username: str,
        password: str,
        ip_address: str = "",
        user_agent: str = ""
    ) -> Tuple[bool, Optional[str], str]:
        """
        Authenticate a user.

        Args:
            username: Username to check
            password: Password to verify
            ip_address: Client IP for logging
            user_agent: Client user agent for logging

        Returns:
            Tuple of (success, session_id or None, message)
        """
        username = username.lower()

        # Check for lockout
        if self._is_locked_out(username):
            return False, None, f"Account locked. Try again in {LOCKOUT_MINUTES} minutes."

        # Get user
        df = pd.read_csv(USERS_FILE)
        user_row = df[df['username'] == username]

        if user_row.empty:
            self._log_attempt(username, False, ip_address, user_agent)
            return False, None, "Invalid username or password."

        user = user_row.iloc[0]

        # Check if active
        if not user['is_active']:
            return False, None, "Account is disabled."

        # Verify password
        password_hash, _ = self._hash_password(password, user['salt'])

        if password_hash != user['password_hash']:
            self._log_attempt(username, False, ip_address, user_agent)
            remaining = self._get_remaining_attempts(username)
            return False, None, f"Invalid username or password. {remaining} attempts remaining."

        # Success - create session
        self._log_attempt(username, True, ip_address, user_agent)
        session_id = self._create_session(user['user_id'], username, ip_address)

        # Update last login
        idx = df[df['username'] == username].index[0]
        df.at[idx, 'last_login'] = datetime.now().isoformat()
        df.to_csv(USERS_FILE, index=False)

        logger.info(f"User logged in: {username}")
        return True, session_id, f"Welcome, {user['full_name']}!"

    def _log_attempt(self, username: str, success: bool, ip_address: str, user_agent: str):
        """Log a login attempt."""
        df = pd.read_csv(LOGIN_ATTEMPTS_FILE)

        attempt = {
            'attempt_id': f"ATT-{str(uuid.uuid4())[:8]}",
            'username': username,
            'timestamp': datetime.now().isoformat(),
            'success': success,
            'ip_address': ip_address,
            'user_agent': user_agent
        }

        df = pd.concat([df, pd.DataFrame([attempt])], ignore_index=True)
        df.to_csv(LOGIN_ATTEMPTS_FILE, index=False)

    def _is_locked_out(self, username: str) -> bool:
        """Check if a user is locked out due to failed attempts."""
        df = pd.read_csv(LOGIN_ATTEMPTS_FILE)

        # Get recent failed attempts
        cutoff = (datetime.now() - timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
        recent = df[
            (df['username'] == username) &
            (df['timestamp'] >= cutoff) &
            (df['success'] == False)
        ]

        return len(recent) >= MAX_LOGIN_ATTEMPTS

    def _get_remaining_attempts(self, username: str) -> int:
        """Get remaining login attempts before lockout."""
        df = pd.read_csv(LOGIN_ATTEMPTS_FILE)

        cutoff = (datetime.now() - timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
        recent = df[
            (df['username'] == username) &
            (df['timestamp'] >= cutoff) &
            (df['success'] == False)
        ]

        return max(0, MAX_LOGIN_ATTEMPTS - len(recent))

    def _create_session(self, user_id: str, username: str, ip_address: str) -> str:
        """Create a new session."""
        session_id = secrets.token_urlsafe(32)

        session = {
            'session_id': session_id,
            'user_id': user_id,
            'username': username,
            'created_at': datetime.now().isoformat(),
            'expires_at': (datetime.now() + timedelta(hours=SESSION_DURATION_HOURS)).isoformat(),
            'ip_address': ip_address,
            'is_active': True
        }

        df = pd.read_csv(SESSIONS_FILE)
        df = pd.concat([df, pd.DataFrame([session])], ignore_index=True)
        df.to_csv(SESSIONS_FILE, index=False)

        return session_id

    def validate_session(self, session_id: str) -> Tuple[bool, Optional[Dict]]:
        """
        Validate a session.

        Returns:
            Tuple of (is_valid, user_info or None)
        """
        df = pd.read_csv(SESSIONS_FILE)
        session_row = df[df['session_id'] == session_id]

        if session_row.empty:
            return False, None

        session = session_row.iloc[0]

        # Check if active and not expired
        if not session['is_active']:
            return False, None

        if datetime.now() > datetime.fromisoformat(session['expires_at']):
            # Expire the session
            idx = df[df['session_id'] == session_id].index[0]
            df.at[idx, 'is_active'] = False
            df.to_csv(SESSIONS_FILE, index=False)
            return False, None

        # Get user info
        users_df = pd.read_csv(USERS_FILE)
        user_row = users_df[users_df['username'] == session['username']]

        if user_row.empty or not user_row.iloc[0]['is_active']:
            return False, None

        user = user_row.iloc[0]
        return True, {
            'user_id': user['user_id'],
            'username': user['username'],
            'full_name': user['full_name'],
            'role': user['role'],
            'email': user['email']
        }

    def logout(self, session_id: str) -> bool:
        """End a session."""
        df = pd.read_csv(SESSIONS_FILE)
        idx = df[df['session_id'] == session_id].index

        if len(idx) == 0:
            return False

        df.at[idx[0], 'is_active'] = False
        df.to_csv(SESSIONS_FILE, index=False)

        logger.info(f"Session ended: {session_id[:10]}...")
        return True

    def change_password(self, username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
        """Change a user's password."""
        username = username.lower()

        df = pd.read_csv(USERS_FILE)
        user_row = df[df['username'] == username]

        if user_row.empty:
            return False, "User not found."

        user = user_row.iloc[0]

        # Verify old password
        old_hash, _ = self._hash_password(old_password, user['salt'])
        if old_hash != user['password_hash']:
            return False, "Current password is incorrect."

        # Set new password
        new_hash, new_salt = self._hash_password(new_password)

        idx = df[df['username'] == username].index[0]
        df.at[idx, 'password_hash'] = new_hash
        df.at[idx, 'salt'] = new_salt
        df.to_csv(USERS_FILE, index=False)

        logger.info(f"Password changed for: {username}")
        return True, "Password changed successfully."

    def reset_password(self, username: str, new_password: str, admin_user: str = "") -> Tuple[bool, str]:
        """Admin reset of a user's password."""
        username = username.lower()

        df = pd.read_csv(USERS_FILE)
        idx = df[df['username'] == username].index

        if len(idx) == 0:
            return False, "User not found."

        new_hash, new_salt = self._hash_password(new_password)
        df.at[idx[0], 'password_hash'] = new_hash
        df.at[idx[0], 'salt'] = new_salt
        df.to_csv(USERS_FILE, index=False)

        logger.info(f"Password reset for {username} by {admin_user}")
        return True, "Password reset successfully."

    def get_all_users(self, include_inactive: bool = False) -> pd.DataFrame:
        """Get all users."""
        df = pd.read_csv(USERS_FILE)

        if not include_inactive:
            df = df[df['is_active'] == True]

        # Don't return password fields
        return df[['user_id', 'username', 'full_name', 'email', 'role', 'created_at', 'last_login', 'is_active']]

    def get_user(self, username: str) -> Optional[Dict]:
        """Get a single user."""
        df = pd.read_csv(USERS_FILE)
        user = df[df['username'] == username.lower()]

        if user.empty:
            return None

        u = user.iloc[0]
        return {
            'user_id': u['user_id'],
            'username': u['username'],
            'full_name': u['full_name'],
            'email': u['email'],
            'role': u['role'],
            'is_active': u['is_active'],
            'created_at': u['created_at'],
            'last_login': u['last_login']
        }

    def update_user(self, username: str, updates: Dict) -> bool:
        """Update user info (not password)."""
        username = username.lower()
        df = pd.read_csv(USERS_FILE)
        idx = df[df['username'] == username].index

        if len(idx) == 0:
            return False

        allowed_fields = ['full_name', 'email', 'role', 'is_active']
        for key, value in updates.items():
            if key in allowed_fields:
                df.at[idx[0], key] = value

        df.to_csv(USERS_FILE, index=False)
        return True

    def deactivate_user(self, username: str) -> bool:
        """Deactivate a user account."""
        return self.update_user(username, {'is_active': False})

    def activate_user(self, username: str) -> bool:
        """Activate a user account."""
        return self.update_user(username, {'is_active': True})

    def get_active_sessions(self) -> pd.DataFrame:
        """Get all active sessions."""
        df = pd.read_csv(SESSIONS_FILE)
        now = datetime.now().isoformat()

        return df[(df['is_active'] == True) & (df['expires_at'] > now)]

    def end_all_sessions(self, username: str) -> int:
        """End all sessions for a user."""
        df = pd.read_csv(SESSIONS_FILE)

        count = 0
        for idx, row in df.iterrows():
            if row['username'] == username.lower() and row['is_active']:
                df.at[idx, 'is_active'] = False
                count += 1

        df.to_csv(SESSIONS_FILE, index=False)
        return count


# Streamlit helper functions
def check_login(session_state) -> Tuple[bool, Optional[Dict]]:
    """
    Check if user is logged in from Streamlit session state.

    Returns:
        Tuple of (is_logged_in, user_info)
    """
    auth = VAAuth()

    session_id = session_state.get('session_id')
    if not session_id:
        return False, None

    return auth.validate_session(session_id)


def require_login(session_state, required_role: str = None) -> Tuple[bool, Optional[Dict], str]:
    """
    Check login and optionally require a specific role.

    Returns:
        Tuple of (authorized, user_info, message)
    """
    is_logged_in, user_info = check_login(session_state)

    if not is_logged_in:
        return False, None, "Please log in to continue."

    if required_role:
        if required_role == "admin" and user_info['role'] != 'admin':
            return False, user_info, "Admin access required."

    return True, user_info, "Authorized."


# Export
__all__ = [
    'VAAuth',
    'ROLES',
    'check_login',
    'require_login'
]
