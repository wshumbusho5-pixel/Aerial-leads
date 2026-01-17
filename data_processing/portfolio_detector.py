"""
Aerial Leads - Portfolio Detector

Detects owners with multiple distressed properties.
These "whale" owners are often highly motivated sellers.

Why this matters:
- Owner with 5 distressed properties = tired landlord ready to sell all
- Inherited multiple properties = can't manage, wants out
- Failed investor = cutting losses, motivated to negotiate
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from collections import defaultdict
import re

from config.logging_config import get_logger

logger = get_logger("PortfolioDetector")


class PortfolioDetector:
    """
    Detects and analyzes multi-property owners in lead datasets.
    """

    def __init__(self):
        self.owner_portfolios = {}
        self.whale_threshold = 2  # 2+ properties = whale

    def analyze_portfolios(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Analyze dataset and add portfolio information.

        Adds columns:
        - portfolio_size: Number of properties owned by this owner
        - is_whale: True if owner has 2+ properties
        - owner_total_debt: Total tax debt across all owner's properties
        - owner_total_value: Total assessed value across all properties
        - portfolio_rank: Rank by portfolio size (1 = largest)

        Args:
            df: DataFrame with owner_name column

        Returns:
            DataFrame with portfolio columns added
        """
        if 'owner_name' not in df.columns:
            logger.warning("No owner_name column found, skipping portfolio detection")
            df['portfolio_size'] = 1
            df['is_whale'] = False
            return df

        logger.info("Analyzing owner portfolios...")

        # Normalize owner names for better matching
        df['owner_name_normalized'] = df['owner_name'].apply(self._normalize_name)

        # Count properties per owner
        owner_counts = df.groupby('owner_name_normalized').size().to_dict()

        # Calculate total debt per owner
        owner_debt = df.groupby('owner_name_normalized')['taxes_owed'].sum().to_dict()

        # Calculate total value per owner
        if 'assessed_value' in df.columns:
            owner_value = df.groupby('owner_name_normalized')['assessed_value'].sum().to_dict()
        else:
            owner_value = defaultdict(int)

        # Add portfolio columns
        df['portfolio_size'] = df['owner_name_normalized'].map(owner_counts).fillna(1).astype(int)
        df['is_whale'] = df['portfolio_size'] >= self.whale_threshold
        df['owner_total_debt'] = df['owner_name_normalized'].map(owner_debt).fillna(0)
        df['owner_total_value'] = df['owner_name_normalized'].map(owner_value).fillna(0)

        # Rank by portfolio size
        portfolio_ranks = df.groupby('owner_name_normalized')['portfolio_size'].first().rank(
            method='dense', ascending=False
        ).to_dict()
        df['portfolio_rank'] = df['owner_name_normalized'].map(portfolio_ranks).fillna(999).astype(int)

        # Clean up temp column
        df = df.drop(columns=['owner_name_normalized'])

        # Log stats
        total_owners = df['owner_name'].nunique()
        whale_owners = df[df['is_whale']]['owner_name'].nunique()
        whale_properties = df[df['is_whale']].shape[0]

        logger.info(f"Portfolio analysis complete:")
        logger.info(f"  Total unique owners: {total_owners}")
        logger.info(f"  Whale owners (2+ properties): {whale_owners}")
        logger.info(f"  Properties owned by whales: {whale_properties}")

        return df

    def _normalize_name(self, name: str) -> str:
        """
        Normalize owner name for better matching.

        Handles variations like:
        - "SMITH JOHN" vs "JOHN SMITH"
        - "SMITH, JOHN" vs "SMITH JOHN"
        - "SMITH JOHN A" vs "SMITH JOHN"
        - "THE SMITH FAMILY TRUST" vs "SMITH FAMILY TRUST"
        """
        if pd.isna(name) or not isinstance(name, str):
            return "UNKNOWN"

        # Uppercase
        name = name.upper().strip()

        # Remove common prefixes/suffixes
        remove_patterns = [
            r'^THE\s+',
            r'\s+LLC$',
            r'\s+INC$',
            r'\s+CORP$',
            r'\s+LTD$',
            r'\s+TRUST$',
            r'\s+ESTATE$',
            r'\s+ET\s*AL\.?$',
            r'\s+ETAL$',
            r'\s+&\s+',
            r'\s+AND\s+',
        ]

        for pattern in remove_patterns:
            name = re.sub(pattern, ' ', name)

        # Remove punctuation
        name = re.sub(r'[,.\-\'\"()]', ' ', name)

        # Normalize whitespace
        name = ' '.join(name.split())

        return name

    def get_whale_summary(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Get summary of whale owners (2+ properties).

        Returns DataFrame with:
        - owner_name
        - property_count
        - total_debt
        - total_value
        - avg_score
        - properties (list of addresses)
        """
        if 'is_whale' not in df.columns:
            df = self.analyze_portfolios(df)

        whales = df[df['is_whale']].copy()

        if whales.empty:
            return pd.DataFrame()

        # Group by owner
        summary = whales.groupby('owner_name').agg({
            'address': lambda x: list(x),
            'taxes_owed': 'sum',
            'assessed_value': 'sum' if 'assessed_value' in whales.columns else 'count',
            'motivation_score': 'mean' if 'motivation_score' in whales.columns else 'count',
            'parcel_id': 'count'
        }).reset_index()

        summary.columns = ['owner_name', 'properties', 'total_debt', 'total_value', 'avg_score', 'property_count']

        # Reorder columns
        summary = summary[['owner_name', 'property_count', 'total_debt', 'total_value', 'avg_score', 'properties']]

        # Sort by property count descending
        summary = summary.sort_values('property_count', ascending=False)

        return summary

    def get_top_whales(self, df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
        """Get top N whale owners by property count."""
        summary = self.get_whale_summary(df)
        return summary.head(top_n)

    def boost_whale_scores(self, df: pd.DataFrame, boost_per_property: int = 5) -> pd.DataFrame:
        """
        Boost motivation scores for whale owners.

        Each additional property adds points to the score.
        Example: 3 properties = +10 points (2 extra * 5)

        Args:
            df: DataFrame with portfolio_size and motivation_score
            boost_per_property: Points to add per extra property

        Returns:
            DataFrame with boosted scores
        """
        if 'portfolio_size' not in df.columns:
            df = self.analyze_portfolios(df)

        if 'motivation_score' not in df.columns:
            return df

        # Calculate boost (extra properties * boost amount)
        extra_properties = (df['portfolio_size'] - 1).clip(lower=0)
        boost = extra_properties * boost_per_property

        # Apply boost (cap at 100)
        df['motivation_score_original'] = df['motivation_score']
        df['motivation_score'] = (df['motivation_score'] + boost).clip(upper=100)
        df['whale_boost'] = boost

        boosted_count = (boost > 0).sum()
        logger.info(f"Boosted scores for {boosted_count} properties owned by whales")

        return df


def detect_portfolios(df: pd.DataFrame) -> pd.DataFrame:
    """Convenience function to detect portfolios."""
    detector = PortfolioDetector()
    return detector.analyze_portfolios(df)


def get_whale_owners(df: pd.DataFrame) -> pd.DataFrame:
    """Convenience function to get whale summary."""
    detector = PortfolioDetector()
    return detector.get_whale_summary(df)


# ========================================
# CLI Test
# ========================================

if __name__ == '__main__':
    from rich.console import Console
    from rich.table import Table

    console = Console()

    # Load test data
    from config.settings import PROCESSED_DATA_DIR

    test_file = PROCESSED_DATA_DIR / 'all_leads_real.csv'

    if not test_file.exists():
        console.print("[red]No test data found. Generate leads first.[/red]")
        exit(1)

    df = pd.read_csv(test_file)
    console.print(f"\n[cyan]Loaded {len(df)} properties[/cyan]")

    # Detect portfolios
    detector = PortfolioDetector()
    df = detector.analyze_portfolios(df)

    # Show whale summary
    whales = detector.get_top_whales(df, top_n=10)

    if whales.empty:
        console.print("[yellow]No whale owners found (owners with 2+ properties)[/yellow]")
    else:
        console.print(f"\n[bold green]Top Whale Owners ({len(whales)} found)[/bold green]\n")

        table = Table(title="Whale Owners - Multiple Distressed Properties")
        table.add_column("Owner", style="cyan", width=30)
        table.add_column("Properties", justify="center", style="green")
        table.add_column("Total Debt", justify="right", style="red")
        table.add_column("Addresses", style="white", width=50)

        for _, row in whales.iterrows():
            addresses = ", ".join(row['properties'][:3])
            if len(row['properties']) > 3:
                addresses += f" (+{len(row['properties']) - 3} more)"

            table.add_row(
                row['owner_name'][:28],
                str(row['property_count']),
                f"${row['total_debt']:,.0f}",
                addresses[:48]
            )

        console.print(table)
