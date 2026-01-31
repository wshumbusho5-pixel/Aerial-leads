"""
Shared Database Authentication Module

This module provides PostgreSQL-based authentication that can be shared
across multiple apps (Admin Dashboard, VA Portal, Public Site).

Supports both PostgreSQL (production) and SQLite (local development).
"""

import os
import hashlib
import secrets
from datetime import datetime
from typing import Optional, Tuple, Dict, List
import logging

logger = logging.getLogger(__name__)

# Try to import database libraries
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

try:
    import sqlite3
    HAS_SQLITE = True
except ImportError:
    HAS_SQLITE = False


class DatabaseAuth:
    """
    Database-backed authentication system.

    Usage:
        # For PostgreSQL (Railway)
        auth = DatabaseAuth(database_url="postgresql://user:pass@host:port/db")

        # For SQLite (local)
        auth = DatabaseAuth(sqlite_path="data/auth.db")

        # Auto-detect from environment
        auth = DatabaseAuth()  # Uses DATABASE_URL env var or falls back to SQLite
    """

    def __init__(self, database_url: str = None, sqlite_path: str = None):
        """
        Initialize database connection.

        Args:
            database_url: PostgreSQL connection string
            sqlite_path: Path to SQLite database file
        """
        self.database_url = database_url or os.getenv('DATABASE_URL')
        self.sqlite_path = sqlite_path
        self.connection = None
        self.db_type = None

        # Determine database type
        if self.database_url and self.database_url.startswith('postgres'):
            if not HAS_PSYCOPG2:
                raise ImportError("psycopg2 is required for PostgreSQL. Install with: pip install psycopg2-binary")
            self.db_type = 'postgresql'
        else:
            if not HAS_SQLITE:
                raise ImportError("sqlite3 is required")
            self.db_type = 'sqlite'
            if not self.sqlite_path:
                self.sqlite_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'auth.db')

        # Initialize database
        self._init_db()

    def _get_connection(self):
        """Get database connection."""
        if self.db_type == 'postgresql':
            return psycopg2.connect(self.database_url, cursor_factory=RealDictCursor)
        else:
            # Ensure directory exists
            os.makedirs(os.path.dirname(os.path.abspath(self.sqlite_path)), exist_ok=True)
            conn = sqlite3.connect(self.sqlite_path)
            conn.row_factory = sqlite3.Row
            return conn

    def _init_db(self):
        """Initialize database tables."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if self.db_type == 'postgresql':
            # PostgreSQL schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    full_name VARCHAR(255),
                    email VARCHAR(255),
                    role VARCHAR(50) DEFAULT 'va',
                    status VARCHAR(50) DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    phone VARCHAR(50),
                    notes TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(255) UNIQUE NOT NULL,
                    username VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    ip_address VARCHAR(50),
                    user_agent TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100),
                    action VARCHAR(100),
                    details TEXT,
                    ip_address VARCHAR(50),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            # SQLite schema
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT,
                    email TEXT,
                    role TEXT DEFAULT 'va',
                    status TEXT DEFAULT 'active',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    last_login TEXT,
                    phone TEXT,
                    notes TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT UNIQUE NOT NULL,
                    username TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT,
                    ip_address TEXT,
                    user_agent TEXT
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS activity_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT,
                    action TEXT,
                    details TEXT,
                    ip_address TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

        conn.commit()

        # Create default admin if no users exist
        cursor.execute("SELECT COUNT(*) as count FROM users")
        result = cursor.fetchone()
        count = result['count'] if isinstance(result, dict) else result[0]

        if count == 0:
            self._create_default_admin(cursor)
            conn.commit()
        else:
            # Ensure VA users exist even if admin was already created
            self._ensure_va_users(cursor)
            conn.commit()

        conn.close()

    def _ensure_va_users(self, cursor):
        """Ensure VA users exist (for database recovery)."""
        va_hash = self._hash_password('Lifeline2026')
        va_users = [
            ('naomi', 'Naomi Keza', 'naomikezau@gmail.com'),
            ('keomi', 'Naomi Keza Uwase', 'naomikezau@gmail.com'),
            ('monalisa', 'Naomi Keza', 'naomikezau@gmail.com'),
            ('brent', 'Willy Miles', 'wshumbusho5@gmail.com'),
        ]

        for username, full_name, email in va_users:
            # Check if user exists
            if self.db_type == 'postgresql':
                cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            else:
                cursor.execute("SELECT id FROM users WHERE username = ?", (username,))

            if not cursor.fetchone():
                # User doesn't exist, create them
                if self.db_type == 'postgresql':
                    cursor.execute("""
                        INSERT INTO users (username, password_hash, full_name, email, role, status)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (username, va_hash, full_name, email, 'va', 'active'))
                else:
                    cursor.execute("""
                        INSERT INTO users (username, password_hash, full_name, email, role, status)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (username, va_hash, full_name, email, 'va', 'active'))
                logger.info(f"Created VA user: {username}")

    def _create_default_admin(self, cursor):
        """Create default admin and VA users."""
        admin_hash = self._hash_password('admin123')
        va_hash = self._hash_password('Lifeline2026')

        # VA users to seed
        va_users = [
            ('naomi', 'Naomi Keza', 'naomikezau@gmail.com'),
            ('keomi', 'Naomi Keza Uwase', 'naomikezau@gmail.com'),
            ('monalisa', 'Naomi Keza', 'naomikezau@gmail.com'),
            ('brent', 'Willy Miles', 'wshumbusho5@gmail.com'),
        ]

        if self.db_type == 'postgresql':
            # Admin
            cursor.execute("""
                INSERT INTO users (username, password_hash, full_name, role, status)
                VALUES (%s, %s, %s, %s, %s)
            """, ('admin', admin_hash, 'Administrator', 'admin', 'active'))

            # VA users
            for username, full_name, email in va_users:
                cursor.execute("""
                    INSERT INTO users (username, password_hash, full_name, email, role, status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (username, va_hash, full_name, email, 'va', 'active'))
        else:
            # Admin
            cursor.execute("""
                INSERT INTO users (username, password_hash, full_name, role, status)
                VALUES (?, ?, ?, ?, ?)
            """, ('admin', admin_hash, 'Administrator', 'admin', 'active'))

            # VA users
            for username, full_name, email in va_users:
                cursor.execute("""
                    INSERT INTO users (username, password_hash, full_name, email, role, status)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (username, va_hash, full_name, email, 'va', 'active'))

        logger.info("Created admin (admin123) and 4 VA users (Lifeline2026)")

    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()

    def _generate_session_id(self) -> str:
        """Generate a secure session ID."""
        return secrets.token_hex(32)

    def authenticate(self, username: str, password: str, ip_address: str = None) -> Tuple[bool, str, str]:
        """
        Authenticate a user.

        Args:
            username: User's username
            password: User's password
            ip_address: Optional IP address for logging

        Returns:
            Tuple of (success, session_id or None, message)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            password_hash = self._hash_password(password)

            if self.db_type == 'postgresql':
                cursor.execute("""
                    SELECT * FROM users
                    WHERE username = %s AND password_hash = %s AND status = 'active'
                """, (username, password_hash))
            else:
                cursor.execute("""
                    SELECT * FROM users
                    WHERE username = ? AND password_hash = ? AND status = 'active'
                """, (username, password_hash))

            user = cursor.fetchone()

            if not user:
                self._log_activity(cursor, username, 'login_failed', 'Invalid credentials', ip_address)
                conn.commit()
                conn.close()
                return False, None, "Invalid username or password"

            # Create session
            session_id = self._generate_session_id()
            now = datetime.now().isoformat()

            if self.db_type == 'postgresql':
                cursor.execute("""
                    INSERT INTO sessions (session_id, username, ip_address)
                    VALUES (%s, %s, %s)
                """, (session_id, username, ip_address))

                cursor.execute("""
                    UPDATE users SET last_login = %s WHERE username = %s
                """, (now, username))
            else:
                cursor.execute("""
                    INSERT INTO sessions (session_id, username, ip_address)
                    VALUES (?, ?, ?)
                """, (session_id, username, ip_address))

                cursor.execute("""
                    UPDATE users SET last_login = ? WHERE username = ?
                """, (now, username))

            self._log_activity(cursor, username, 'login_success', 'User logged in', ip_address)
            conn.commit()
            conn.close()

            return True, session_id, "Login successful"

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            conn.close()
            return False, None, f"Authentication error: {str(e)}"

    def get_user(self, username: str) -> Optional[Dict]:
        """Get user by username."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if self.db_type == 'postgresql':
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
            else:
                cursor.execute("SELECT * FROM users WHERE username = ?", (username,))

            row = cursor.fetchone()
            conn.close()

            if row:
                if isinstance(row, dict):
                    return row
                else:
                    # SQLite Row object
                    return dict(row)
            return None

        except Exception as e:
            logger.error(f"Error getting user: {e}")
            conn.close()
            return None

    def create_user(self, username: str, password: str, full_name: str = None,
                    email: str = None, role: str = 'va', phone: str = None) -> Tuple[bool, str]:
        """
        Create a new user.

        Returns:
            Tuple of (success, message)
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Check if username exists
            if self.db_type == 'postgresql':
                cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
            else:
                cursor.execute("SELECT id FROM users WHERE username = ?", (username,))

            if cursor.fetchone():
                conn.close()
                return False, "Username already exists"

            password_hash = self._hash_password(password)

            if self.db_type == 'postgresql':
                cursor.execute("""
                    INSERT INTO users (username, password_hash, full_name, email, role, phone, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'active')
                """, (username, password_hash, full_name, email, role, phone))
            else:
                cursor.execute("""
                    INSERT INTO users (username, password_hash, full_name, email, role, phone, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'active')
                """, (username, password_hash, full_name, email, role, phone))

            conn.commit()
            conn.close()

            logger.info(f"Created user: {username} with role: {role}")
            return True, "User created successfully"

        except Exception as e:
            logger.error(f"Error creating user: {e}")
            conn.close()
            return False, f"Error creating user: {str(e)}"

    def update_user(self, username: str, **kwargs) -> Tuple[bool, str]:
        """Update user fields."""
        conn = self._get_connection()
        cursor = conn.cursor()

        allowed_fields = ['full_name', 'email', 'role', 'status', 'phone', 'notes']
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if 'password' in kwargs:
            updates['password_hash'] = self._hash_password(kwargs['password'])

        if not updates:
            conn.close()
            return False, "No valid fields to update"

        try:
            if self.db_type == 'postgresql':
                set_clause = ', '.join([f"{k} = %s" for k in updates.keys()])
                values = list(updates.values()) + [username]
                cursor.execute(f"UPDATE users SET {set_clause} WHERE username = %s", values)
            else:
                set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
                values = list(updates.values()) + [username]
                cursor.execute(f"UPDATE users SET {set_clause} WHERE username = ?", values)

            conn.commit()
            conn.close()
            return True, "User updated successfully"

        except Exception as e:
            logger.error(f"Error updating user: {e}")
            conn.close()
            return False, f"Error updating user: {str(e)}"

    def delete_user(self, username: str) -> Tuple[bool, str]:
        """Delete a user."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if self.db_type == 'postgresql':
                cursor.execute("DELETE FROM users WHERE username = %s", (username,))
            else:
                cursor.execute("DELETE FROM users WHERE username = ?", (username,))

            conn.commit()
            conn.close()
            return True, "User deleted successfully"

        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            conn.close()
            return False, f"Error deleting user: {str(e)}"

    def change_password(self, username: str, current_password: str, new_password: str) -> Tuple[bool, str]:
        """
        Change user's password after verifying current password.

        Args:
            username: User's username
            current_password: Current password for verification
            new_password: New password to set

        Returns:
            Tuple of (success, message)
        """
        if len(new_password) < 8:
            return False, "New password must be at least 8 characters"

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Verify current password
            current_hash = self._hash_password(current_password)

            if self.db_type == 'postgresql':
                cursor.execute("""
                    SELECT id FROM users
                    WHERE username = %s AND password_hash = %s AND status = 'active'
                """, (username, current_hash))
            else:
                cursor.execute("""
                    SELECT id FROM users
                    WHERE username = ? AND password_hash = ? AND status = 'active'
                """, (username, current_hash))

            if not cursor.fetchone():
                conn.close()
                return False, "Current password is incorrect"

            # Update to new password
            new_hash = self._hash_password(new_password)

            if self.db_type == 'postgresql':
                cursor.execute("""
                    UPDATE users SET password_hash = %s WHERE username = %s
                """, (new_hash, username))
            else:
                cursor.execute("""
                    UPDATE users SET password_hash = ? WHERE username = ?
                """, (new_hash, username))

            conn.commit()
            conn.close()

            logger.info(f"Password changed for user: {username}")
            return True, "Password changed successfully"

        except Exception as e:
            logger.error(f"Error changing password: {e}")
            conn.close()
            return False, f"Error changing password: {str(e)}"

    def get_all_users(self, role: str = None) -> List[Dict]:
        """Get all users, optionally filtered by role."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if role:
                if self.db_type == 'postgresql':
                    cursor.execute("SELECT * FROM users WHERE role = %s ORDER BY created_at DESC", (role,))
                else:
                    cursor.execute("SELECT * FROM users WHERE role = ? ORDER BY created_at DESC", (role,))
            else:
                cursor.execute("SELECT * FROM users ORDER BY created_at DESC")

            rows = cursor.fetchall()
            conn.close()

            if rows:
                if isinstance(rows[0], dict):
                    return rows
                else:
                    return [dict(row) for row in rows]
            return []

        except Exception as e:
            logger.error(f"Error getting users: {e}")
            conn.close()
            return []

    def validate_session(self, session_id: str) -> Optional[Dict]:
        """Validate a session and return user if valid."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if self.db_type == 'postgresql':
                cursor.execute("""
                    SELECT u.* FROM users u
                    JOIN sessions s ON u.username = s.username
                    WHERE s.session_id = %s AND u.status = 'active'
                """, (session_id,))
            else:
                cursor.execute("""
                    SELECT u.* FROM users u
                    JOIN sessions s ON u.username = s.username
                    WHERE s.session_id = ? AND u.status = 'active'
                """, (session_id,))

            row = cursor.fetchone()
            conn.close()

            if row:
                if isinstance(row, dict):
                    return row
                else:
                    return dict(row)
            return None

        except Exception as e:
            logger.error(f"Error validating session: {e}")
            conn.close()
            return None

    def logout(self, session_id: str) -> bool:
        """Invalidate a session."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if self.db_type == 'postgresql':
                cursor.execute("DELETE FROM sessions WHERE session_id = %s", (session_id,))
            else:
                cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

            conn.commit()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"Error logging out: {e}")
            conn.close()
            return False

    def _log_activity(self, cursor, username: str, action: str, details: str, ip_address: str = None):
        """Log user activity."""
        try:
            if self.db_type == 'postgresql':
                cursor.execute("""
                    INSERT INTO activity_log (username, action, details, ip_address)
                    VALUES (%s, %s, %s, %s)
                """, (username, action, details, ip_address))
            else:
                cursor.execute("""
                    INSERT INTO activity_log (username, action, details, ip_address)
                    VALUES (?, ?, ?, ?)
                """, (username, action, details, ip_address))
        except Exception as e:
            logger.error(f"Error logging activity: {e}")

    def get_activity_log(self, username: str = None, limit: int = 100) -> List[Dict]:
        """Get activity log, optionally filtered by username."""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            if username:
                if self.db_type == 'postgresql':
                    cursor.execute("""
                        SELECT * FROM activity_log
                        WHERE username = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (username, limit))
                else:
                    cursor.execute("""
                        SELECT * FROM activity_log
                        WHERE username = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                    """, (username, limit))
            else:
                if self.db_type == 'postgresql':
                    cursor.execute("""
                        SELECT * FROM activity_log
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (limit,))
                else:
                    cursor.execute("""
                        SELECT * FROM activity_log
                        ORDER BY created_at DESC
                        LIMIT ?
                    """, (limit,))

            rows = cursor.fetchall()
            conn.close()

            if rows:
                if isinstance(rows[0], dict):
                    return rows
                else:
                    return [dict(row) for row in rows]
            return []

        except Exception as e:
            logger.error(f"Error getting activity log: {e}")
            conn.close()
            return []

    def migrate_from_csv(self, csv_path: str) -> Tuple[int, int]:
        """
        Migrate users from CSV file to database.

        Args:
            csv_path: Path to auth_users.csv

        Returns:
            Tuple of (migrated_count, skipped_count)
        """
        try:
            import pandas as pd

            if not os.path.exists(csv_path):
                logger.warning(f"CSV file not found: {csv_path}")
                return 0, 0

            df = pd.read_csv(csv_path)
            migrated = 0
            skipped = 0

            for _, row in df.iterrows():
                username = row.get('username', '')
                if not username:
                    skipped += 1
                    continue

                # Check if user already exists
                existing = self.get_user(username)
                if existing:
                    skipped += 1
                    continue

                # Get password hash or create new password
                password_hash = row.get('password_hash', '')
                if not password_hash:
                    password_hash = self._hash_password('changeme123')

                # Insert user directly with hash
                conn = self._get_connection()
                cursor = conn.cursor()

                try:
                    if self.db_type == 'postgresql':
                        cursor.execute("""
                            INSERT INTO users (username, password_hash, full_name, email, role, phone, status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            username,
                            password_hash,
                            row.get('full_name', ''),
                            row.get('email', ''),
                            row.get('role', 'va'),
                            row.get('phone', ''),
                            row.get('status', 'active')
                        ))
                    else:
                        cursor.execute("""
                            INSERT INTO users (username, password_hash, full_name, email, role, phone, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            username,
                            password_hash,
                            row.get('full_name', ''),
                            row.get('email', ''),
                            row.get('role', 'va'),
                            row.get('phone', ''),
                            row.get('status', 'active')
                        ))

                    conn.commit()
                    migrated += 1
                    logger.info(f"Migrated user: {username}")

                except Exception as e:
                    logger.error(f"Error migrating user {username}: {e}")
                    skipped += 1
                finally:
                    conn.close()

            return migrated, skipped

        except Exception as e:
            logger.error(f"Error during migration: {e}")
            return 0, 0


# Singleton instance for easy import
_db_auth_instance = None

def get_db_auth() -> DatabaseAuth:
    """Get or create DatabaseAuth singleton."""
    global _db_auth_instance
    if _db_auth_instance is None:
        _db_auth_instance = DatabaseAuth()
    return _db_auth_instance
