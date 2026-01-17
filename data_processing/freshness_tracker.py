"""
Lead Freshness Tracker

Tracks data age, detects changes over time, and alerts on increasing distress.
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json

try:
    from config.logging_config import get_logger
    logger = get_logger("FreshnessTracker")
except ImportError:
    import logging
    logger = logging.getLogger("FreshnessTracker")


class FreshnessTracker:
    """
    Tracks lead data freshness and detects changes over time.

    Features:
    - Data age tracking
    - Change detection between scrapes
    - Increasing distress alerts
    - Stale data warnings
    """

    # Freshness thresholds (in days)
    FRESHNESS_THRESHOLDS = {
        'fresh': 7,       # Less than 7 days old
        'recent': 30,     # 7-30 days old
        'aging': 90,      # 30-90 days old
        'stale': float('inf'),  # Over 90 days
    }

    # Change detection thresholds
    ALERT_THRESHOLDS = {
        'tax_increase_pct': 10,      # Alert if taxes increase 10%+
        'violations_increase': 2,     # Alert if 2+ new violations
        'years_delinquent_increase': 1,  # Alert if 1+ more years delinquent
    }

    def __init__(self, history_dir: Optional[Path] = None):
        """
        Initialize freshness tracker.

        Args:
            history_dir: Directory to store historical data
        """
        if history_dir:
            self.history_dir = Path(history_dir)
            self.history_dir.mkdir(parents=True, exist_ok=True)
        else:
            from config.settings import PROCESSED_DATA_DIR
            self.history_dir = PROCESSED_DATA_DIR / 'history'
            self.history_dir.mkdir(parents=True, exist_ok=True)

    def get_data_age_days(self, scraped_date: str) -> int:
        """Calculate days since data was scraped."""
        if not scraped_date or scraped_date == 'nan':
            return 999  # Unknown age treated as very old

        try:
            scrape_dt = datetime.strptime(str(scraped_date)[:10], '%Y-%m-%d')
            return (datetime.now() - scrape_dt).days
        except:
            return 999

    def get_freshness_tier(self, days_old: int) -> str:
        """Determine freshness tier based on age."""
        if days_old < self.FRESHNESS_THRESHOLDS['fresh']:
            return 'fresh'
        elif days_old < self.FRESHNESS_THRESHOLDS['recent']:
            return 'recent'
        elif days_old < self.FRESHNESS_THRESHOLDS['aging']:
            return 'aging'
        else:
            return 'stale'

    def add_freshness_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add data freshness columns to DataFrame.

        Args:
            df: DataFrame with scraped_date column

        Returns:
            DataFrame with freshness columns added
        """
        df = df.copy()

        # Add data age
        df['data_age_days'] = df['scraped_date'].apply(self.get_data_age_days)

        # Add freshness tier
        df['freshness_tier'] = df['data_age_days'].apply(self.get_freshness_tier)

        # Add freshness score (0-100, higher = fresher)
        df['freshness_score'] = df['data_age_days'].apply(
            lambda days: max(0, 100 - (days * 1.1))  # Degrades ~1% per day
        )

        logger.info(f"Freshness analysis complete:")
        for tier in ['fresh', 'recent', 'aging', 'stale']:
            count = (df['freshness_tier'] == tier).sum()
            logger.info(f"  {tier.capitalize()}: {count} properties")

        return df

    def save_snapshot(self, df: pd.DataFrame, market_id: str) -> str:
        """
        Save a dated snapshot for change detection.

        Args:
            df: DataFrame to snapshot
            market_id: Market identifier

        Returns:
            Path to saved snapshot
        """
        date_str = datetime.now().strftime('%Y%m%d')
        snapshot_path = self.history_dir / f'{market_id}_snapshot_{date_str}.csv'

        # Keep only essential columns for comparison
        compare_cols = [
            'parcel_id', 'address', 'owner_name', 'taxes_owed',
            'years_delinquent', 'total_violations', 'motivation_score',
            'scraped_date'
        ]
        compare_cols = [c for c in compare_cols if c in df.columns]

        df[compare_cols].to_csv(snapshot_path, index=False)
        logger.info(f"Saved snapshot to {snapshot_path}")

        return str(snapshot_path)

    def get_previous_snapshot(self, market_id: str) -> Optional[pd.DataFrame]:
        """
        Get the most recent previous snapshot.

        Args:
            market_id: Market identifier

        Returns:
            DataFrame of previous snapshot, or None if not found
        """
        snapshots = list(self.history_dir.glob(f'{market_id}_snapshot_*.csv'))

        if len(snapshots) < 2:
            return None

        # Sort by date and get second most recent (current is most recent)
        snapshots.sort(reverse=True)

        if len(snapshots) >= 2:
            try:
                return pd.read_csv(snapshots[1])
            except:
                return None

        return None

    def detect_changes(
        self,
        current_df: pd.DataFrame,
        previous_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Detect changes between current and previous data.

        Args:
            current_df: Current data
            previous_df: Previous snapshot

        Returns:
            DataFrame with change columns added
        """
        current_df = current_df.copy()

        # Initialize change columns
        current_df['is_new_lead'] = False
        current_df['tax_change'] = 0.0
        current_df['tax_change_pct'] = 0.0
        current_df['violations_change'] = 0
        current_df['years_delinquent_change'] = 0
        current_df['distress_increasing'] = False
        current_df['change_alert'] = ''

        if previous_df is None or previous_df.empty:
            current_df['is_new_lead'] = True
            return current_df

        # Create lookup from previous data
        prev_lookup = previous_df.set_index('parcel_id').to_dict('index')

        alerts_list = []

        for idx, row in current_df.iterrows():
            parcel_id = row.get('parcel_id')

            if parcel_id not in prev_lookup:
                current_df.at[idx, 'is_new_lead'] = True
                current_df.at[idx, 'change_alert'] = 'NEW LEAD'
                continue

            prev_row = prev_lookup[parcel_id]
            alerts = []

            # Check tax changes
            prev_taxes = float(prev_row.get('taxes_owed', 0) or 0)
            curr_taxes = float(row.get('taxes_owed', 0) or 0)

            if prev_taxes > 0:
                tax_change = curr_taxes - prev_taxes
                tax_change_pct = (tax_change / prev_taxes) * 100

                current_df.at[idx, 'tax_change'] = tax_change
                current_df.at[idx, 'tax_change_pct'] = tax_change_pct

                if tax_change_pct >= self.ALERT_THRESHOLDS['tax_increase_pct']:
                    alerts.append(f'TAX +{tax_change_pct:.0f}%')

            # Check violations changes
            prev_violations = int(prev_row.get('total_violations', 0) or 0)
            curr_violations = int(row.get('total_violations', 0) or 0)
            violations_change = curr_violations - prev_violations

            current_df.at[idx, 'violations_change'] = violations_change

            if violations_change >= self.ALERT_THRESHOLDS['violations_increase']:
                alerts.append(f'+{violations_change} VIOLATIONS')

            # Check years delinquent changes
            prev_years = int(prev_row.get('years_delinquent', 0) or 0)
            curr_years = int(row.get('years_delinquent', 0) or 0)
            years_change = curr_years - prev_years

            current_df.at[idx, 'years_delinquent_change'] = years_change

            if years_change >= self.ALERT_THRESHOLDS['years_delinquent_increase']:
                alerts.append(f'+{years_change}YR DELINQUENT')

            # Mark if distress is increasing
            if any([
                tax_change_pct >= 5,
                violations_change >= 1,
                years_change >= 1
            ]):
                current_df.at[idx, 'distress_increasing'] = True

            # Combine alerts
            if alerts:
                current_df.at[idx, 'change_alert'] = ' | '.join(alerts)
                alerts_list.append({
                    'parcel_id': parcel_id,
                    'address': row.get('address', ''),
                    'alerts': alerts
                })

        # Log summary
        new_leads = current_df['is_new_lead'].sum()
        distress_increasing = current_df['distress_increasing'].sum()

        logger.info(f"Change detection complete:")
        logger.info(f"  New leads: {new_leads}")
        logger.info(f"  Distress increasing: {distress_increasing}")
        logger.info(f"  Alerts generated: {len(alerts_list)}")

        return current_df

    def get_freshness_summary(self, df: pd.DataFrame) -> Dict:
        """
        Get summary statistics for data freshness.

        Args:
            df: DataFrame with freshness columns

        Returns:
            Dictionary with summary stats
        """
        if 'freshness_tier' not in df.columns:
            return {}

        return {
            'total_properties': len(df),
            'fresh_count': (df['freshness_tier'] == 'fresh').sum(),
            'recent_count': (df['freshness_tier'] == 'recent').sum(),
            'aging_count': (df['freshness_tier'] == 'aging').sum(),
            'stale_count': (df['freshness_tier'] == 'stale').sum(),
            'avg_age_days': df['data_age_days'].mean(),
            'avg_freshness_score': df['freshness_score'].mean() if 'freshness_score' in df.columns else 0,
            'new_leads': df['is_new_lead'].sum() if 'is_new_lead' in df.columns else 0,
            'distress_increasing': df['distress_increasing'].sum() if 'distress_increasing' in df.columns else 0,
        }

    def get_stale_data_warning(self, df: pd.DataFrame) -> Optional[str]:
        """
        Generate warning message if data is too stale.

        Args:
            df: DataFrame with freshness columns

        Returns:
            Warning message or None
        """
        if 'data_age_days' not in df.columns:
            return None

        avg_age = df['data_age_days'].mean()
        stale_pct = (df['freshness_tier'] == 'stale').mean() * 100

        warnings = []

        if avg_age > 30:
            warnings.append(f"Average data age is {avg_age:.0f} days - consider refreshing")

        if stale_pct > 20:
            warnings.append(f"{stale_pct:.0f}% of leads are stale (>90 days old)")

        return ' | '.join(warnings) if warnings else None


# ========================================
# CLI Test
# ========================================

if __name__ == '__main__':
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print("\n[bold cyan]Freshness Tracker Test[/bold cyan]\n")

    tracker = FreshnessTracker()

    # Create test data
    test_df = pd.DataFrame({
        'parcel_id': ['001', '002', '003', '004'],
        'address': ['123 Main St', '456 Oak Ave', '789 Elm St', '321 Pine Rd'],
        'owner_name': ['John Smith', 'Jane Doe', 'Bob Wilson', 'Alice Brown'],
        'taxes_owed': [5000, 8000, 3000, 12000],
        'years_delinquent': [2, 4, 1, 6],
        'total_violations': [0, 3, 1, 5],
        'motivation_score': [65, 80, 45, 90],
        'scraped_date': [
            datetime.now().strftime('%Y-%m-%d'),
            (datetime.now() - timedelta(days=15)).strftime('%Y-%m-%d'),
            (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d'),
            (datetime.now() - timedelta(days=120)).strftime('%Y-%m-%d'),
        ],
    })

    # Add freshness columns
    result_df = tracker.add_freshness_columns(test_df)

    table = Table(title="Freshness Analysis")
    table.add_column("Address", style="cyan")
    table.add_column("Age (days)", justify="right")
    table.add_column("Tier", style="magenta")
    table.add_column("Score", justify="right", style="green")

    for _, row in result_df.iterrows():
        table.add_row(
            row['address'],
            str(row['data_age_days']),
            row['freshness_tier'].upper(),
            f"{row['freshness_score']:.0f}",
        )

    console.print(table)

    # Test change detection
    console.print("\n[bold]Testing Change Detection[/bold]\n")

    # Simulate previous snapshot
    previous_df = test_df.copy()
    previous_df['taxes_owed'] = [4500, 7000, 3000, 10000]  # Less taxes before
    previous_df['total_violations'] = [0, 1, 1, 3]  # Fewer violations before

    # Detect changes
    with_changes = tracker.detect_changes(test_df, previous_df)

    change_table = Table(title="Change Detection")
    change_table.add_column("Address", style="cyan")
    change_table.add_column("Tax Change", justify="right")
    change_table.add_column("Viol. Change", justify="right")
    change_table.add_column("Alert", style="yellow")

    for _, row in with_changes.iterrows():
        change_table.add_row(
            row['address'],
            f"${row['tax_change']:,.0f}" if row['tax_change'] != 0 else "-",
            str(int(row['violations_change'])) if row['violations_change'] != 0 else "-",
            row['change_alert'] or "-",
        )

    console.print(change_table)

    # Show summary
    summary = tracker.get_freshness_summary(with_changes)
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  Fresh: {summary['fresh_count']}")
    console.print(f"  Distress Increasing: {summary['distress_increasing']}")
