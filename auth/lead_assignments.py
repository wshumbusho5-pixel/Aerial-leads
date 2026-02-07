"""
Lead Assignments Database Module

Handles storing and retrieving lead assignments in PostgreSQL
so they can be shared between the admin dashboard and VA Portal.
"""

import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Tuple
import pandas as pd

logger = logging.getLogger(__name__)

# Database connection
DB_AVAILABLE = False
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
    if DATABASE_URL and DATABASE_URL.startswith('postgres'):
        DB_AVAILABLE = True
except ImportError:
    logger.warning("psycopg2 not installed")


def get_connection():
    """Get database connection."""
    if not DB_AVAILABLE:
        return None
    try:
        return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    except Exception as e:
        logger.error(f"Database connection error: {e}")
        return None


def assign_leads_to_db(leads_df: pd.DataFrame, assigned_to: str, assigned_by: str = 'admin', priority: str = 'normal') -> Tuple[int, str]:
    """
    Save lead assignments to the database.

    Args:
        leads_df: DataFrame with leads to assign
        assigned_to: Username of VA to assign leads to
        assigned_by: Username of admin assigning leads
        priority: Priority level (low, normal, high, urgent)

    Returns:
        Tuple of (count_assigned, message)
    """
    conn = get_connection()
    if not conn:
        return 0, "Database not available"

    try:
        cursor = conn.cursor()
        count = 0

        for _, lead in leads_df.iterrows():
            # Extract lead data with fallbacks
            address = lead.get('address', lead.get('property_address', ''))
            owner_name = lead.get('owner_name', lead.get('owner', lead.get('owner_1', '')))
            phone = lead.get('phone', lead.get('phone_1', ''))
            phone_2 = lead.get('phone_2', '')
            phone_3 = lead.get('phone_3', '')
            phone_4 = lead.get('phone_4', '')
            phone_5 = lead.get('phone_5', '')
            phone_6 = lead.get('phone_6', '')
            email = lead.get('email', '')

            property_type = lead.get('property_type', '')
            bedrooms = lead.get('bedrooms', lead.get('beds', None))
            bathrooms = lead.get('bathrooms', lead.get('baths', None))
            sqft = lead.get('sqft', lead.get('square_feet', None))
            year_built = lead.get('year_built', None)
            estimated_value = lead.get('estimated_value', lead.get('value', None))

            motivation_score = lead.get('motivation_score', lead.get('score', 50))
            lead_type = lead.get('lead_type', lead.get('source', ''))
            notes = lead.get('notes', '')

            # Check if this lead is already assigned to this VA (avoid duplicates)
            cursor.execute(
                "SELECT id FROM lead_assignments WHERE address = %s AND assigned_to = %s AND status != 'completed'",
                (address, assigned_to)
            )
            if cursor.fetchone():
                continue  # Skip duplicate

            cursor.execute("""
                INSERT INTO lead_assignments (
                    assigned_to, assigned_by, priority, address, owner_name,
                    phone, phone_2, phone_3, phone_4, phone_5, phone_6,
                    email, property_type, bedrooms, bathrooms,
                    sqft, year_built, estimated_value, motivation_score, lead_type, notes
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                assigned_to, assigned_by, priority, address, owner_name,
                phone, phone_2, phone_3, phone_4, phone_5, phone_6,
                email, property_type, bedrooms, bathrooms,
                sqft, year_built, estimated_value, motivation_score, lead_type, notes
            ))
            count += 1

        conn.commit()
        conn.close()
        return count, f"Successfully assigned {count} leads"

    except Exception as e:
        logger.error(f"Error assigning leads: {e}")
        conn.close()
        return 0, f"Error: {str(e)}"


def get_leads_for_va(username: str, status: str = None) -> pd.DataFrame:
    """
    Get all leads assigned to a VA.

    Args:
        username: VA's username
        status: Optional filter by status (assigned, in_progress, completed, etc.)

    Returns:
        DataFrame with assigned leads
    """
    conn = get_connection()
    if not conn:
        return pd.DataFrame()

    try:
        cursor = conn.cursor()

        if status:
            cursor.execute(
                "SELECT * FROM lead_assignments WHERE assigned_to = %s AND status = %s ORDER BY priority DESC, assigned_at DESC",
                (username, status)
            )
        else:
            cursor.execute(
                "SELECT * FROM lead_assignments WHERE assigned_to = %s AND status != 'completed' ORDER BY priority DESC, assigned_at DESC",
                (username,)
            )

        rows = cursor.fetchall()
        conn.close()

        if rows:
            return pd.DataFrame(rows)
        return pd.DataFrame()

    except Exception as e:
        logger.error(f"Error getting leads: {e}")
        conn.close()
        return pd.DataFrame()


def update_lead_status(lead_id: int, status: str, notes: str = None) -> Tuple[bool, str]:
    """Update lead assignment status."""
    conn = get_connection()
    if not conn:
        return False, "Database not available"

    try:
        cursor = conn.cursor()

        if notes:
            cursor.execute(
                "UPDATE lead_assignments SET status = %s, notes = COALESCE(notes, '') || %s WHERE id = %s",
                (status, f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {notes}", lead_id)
            )
        else:
            cursor.execute(
                "UPDATE lead_assignments SET status = %s WHERE id = %s",
                (status, lead_id)
            )

        conn.commit()
        conn.close()
        return True, "Status updated"

    except Exception as e:
        logger.error(f"Error updating status: {e}")
        conn.close()
        return False, str(e)


def log_call(lead_id: int, result: str, notes: str = None, callback_date: datetime = None) -> Tuple[bool, str]:
    """Log a call made on a lead."""
    conn = get_connection()
    if not conn:
        return False, "Database not available"

    try:
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE lead_assignments
            SET last_call_at = NOW(),
                call_count = call_count + 1,
                last_result = %s,
                callback_date = %s,
                notes = COALESCE(notes, '') || %s
            WHERE id = %s
        """, (
            result,
            callback_date,
            f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] Call: {result}" + (f" - {notes}" if notes else ""),
            lead_id
        ))

        conn.commit()
        conn.close()
        return True, "Call logged"

    except Exception as e:
        logger.error(f"Error logging call: {e}")
        conn.close()
        return False, str(e)


def get_all_assignments(assigned_by: str = None) -> pd.DataFrame:
    """Get all lead assignments (for admin view)."""
    conn = get_connection()
    if not conn:
        return pd.DataFrame()

    try:
        cursor = conn.cursor()

        if assigned_by:
            cursor.execute(
                "SELECT * FROM lead_assignments WHERE assigned_by = %s ORDER BY assigned_at DESC",
                (assigned_by,)
            )
        else:
            cursor.execute("SELECT * FROM lead_assignments ORDER BY assigned_at DESC")

        rows = cursor.fetchall()
        conn.close()

        if rows:
            return pd.DataFrame(rows)
        return pd.DataFrame()

    except Exception as e:
        logger.error(f"Error getting assignments: {e}")
        conn.close()
        return pd.DataFrame()


def get_assignment_stats() -> Dict:
    """Get statistics on lead assignments."""
    conn = get_connection()
    if not conn:
        return {}

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                assigned_to,
                COUNT(*) as total_leads,
                SUM(CASE WHEN status = 'assigned' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(call_count) as total_calls
            FROM lead_assignments
            GROUP BY assigned_to
        """)

        rows = cursor.fetchall()
        conn.close()

        return {row['assigned_to']: dict(row) for row in rows}

    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        conn.close()
        return {}
