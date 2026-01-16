"""
Equity Calculator

Calculates estimated equity for properties based on:
- Market value (from county assessor)
- Known liens (tax debt)
- Estimated mortgage (based on typical LTV ratios)
"""

import pandas as pd
from typing import Optional, Dict, Tuple
from pathlib import Path

try:
    from shared.config.logging_config import get_logger
    logger = get_logger("EquityCalculator")
except ImportError:
    import logging
    logger = logging.getLogger("EquityCalculator")


class EquityCalculator:
    """
    Calculates property equity estimates.

    Equity = Market Value - Total Liens
    Where Liens = Tax Debt + Estimated Mortgage
    """

    # Average LTV ratios by owner type
    DEFAULT_LTV_RATIOS = {
        'absentee_investor': 0.65,  # Investors often have more equity
        'owner_occupied': 0.80,     # Homeowners typically 80% LTV
        'distressed': 0.50,         # Distressed properties often have equity
        'unknown': 0.70,            # Conservative default
    }

    # Equity tiers for filtering
    EQUITY_TIERS = {
        'high': (50000, float('inf')),    # $50k+ equity
        'medium': (20000, 50000),          # $20k-$50k
        'low': (0, 20000),                 # Under $20k
        'underwater': (float('-inf'), 0),  # Negative equity
    }

    def __init__(
        self,
        default_ltv: float = 0.70,
        include_estimated_mortgage: bool = True,
    ):
        """
        Initialize equity calculator.

        Args:
            default_ltv: Default loan-to-value ratio assumption
            include_estimated_mortgage: Whether to estimate mortgage debt
        """
        self.default_ltv = default_ltv
        self.include_estimated_mortgage = include_estimated_mortgage

    def estimate_mortgage(
        self,
        market_value: float,
        is_absentee: bool = False,
        years_owned: Optional[int] = None,
    ) -> float:
        """
        Estimate remaining mortgage balance.

        Args:
            market_value: Property market value
            is_absentee: Whether owner is absentee (investor)
            years_owned: Years property has been owned

        Returns:
            Estimated mortgage balance
        """
        if not self.include_estimated_mortgage:
            return 0.0

        # Select LTV based on owner type
        if is_absentee:
            base_ltv = self.DEFAULT_LTV_RATIOS['absentee_investor']
        else:
            base_ltv = self.DEFAULT_LTV_RATIOS['owner_occupied']

        # Adjust for years owned (properties owned longer have more equity)
        if years_owned and years_owned > 0:
            # Reduce LTV by ~2% per year of ownership
            ltv_reduction = min(years_owned * 0.02, 0.40)
            adjusted_ltv = max(base_ltv - ltv_reduction, 0.20)
        else:
            adjusted_ltv = base_ltv

        return market_value * adjusted_ltv

    def calculate_equity(
        self,
        market_value: float,
        taxes_owed: float,
        is_absentee: bool = False,
        years_owned: Optional[int] = None,
        known_liens: float = 0.0,
    ) -> Tuple[float, float, str]:
        """
        Calculate equity for a single property.

        Args:
            market_value: Property market value
            taxes_owed: Outstanding tax debt
            is_absentee: Whether owner is absentee
            years_owned: Years property has been owned
            known_liens: Any other known liens

        Returns:
            Tuple of (estimated_equity, equity_percentage, equity_tier)
        """
        if market_value <= 0:
            return 0.0, 0.0, 'unknown'

        # Total known liens
        total_liens = taxes_owed + known_liens

        # Estimate mortgage
        estimated_mortgage = self.estimate_mortgage(
            market_value,
            is_absentee,
            years_owned
        )

        # Calculate equity
        estimated_equity = market_value - total_liens - estimated_mortgage

        # Calculate percentage
        equity_percentage = (estimated_equity / market_value) * 100

        # Determine tier
        if estimated_equity >= 50000:
            tier = 'high'
        elif estimated_equity >= 20000:
            tier = 'medium'
        elif estimated_equity >= 0:
            tier = 'low'
        else:
            tier = 'underwater'

        return estimated_equity, equity_percentage, tier

    def add_equity_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add equity calculations to DataFrame.

        Args:
            df: DataFrame with market_value and taxes_owed columns

        Returns:
            DataFrame with added equity columns
        """
        df = df.copy()

        # Initialize columns
        df['estimated_equity'] = 0.0
        df['equity_percentage'] = 0.0
        df['equity_tier'] = 'unknown'
        df['estimated_mortgage'] = 0.0

        logger.info(f"Calculating equity for {len(df)} properties...")

        for idx, row in df.iterrows():
            market_value = float(row.get('market_value', 0) or 0)
            taxes_owed = float(row.get('taxes_owed', 0) or 0)
            is_absentee = bool(row.get('is_absentee', False))

            # Try to estimate years owned from property age
            # (This is a rough proxy - ideally we'd have purchase date)
            property_age = row.get('property_age')
            years_owned = min(property_age, 30) if property_age and property_age > 0 else None

            # Calculate equity
            equity, equity_pct, tier = self.calculate_equity(
                market_value=market_value,
                taxes_owed=taxes_owed,
                is_absentee=is_absentee,
                years_owned=years_owned,
            )

            # Also store estimated mortgage for transparency
            mortgage = self.estimate_mortgage(market_value, is_absentee, years_owned)

            df.at[idx, 'estimated_equity'] = equity
            df.at[idx, 'equity_percentage'] = equity_pct
            df.at[idx, 'equity_tier'] = tier
            df.at[idx, 'estimated_mortgage'] = mortgage

        # Summary stats
        high_equity = (df['equity_tier'] == 'high').sum()
        medium_equity = (df['equity_tier'] == 'medium').sum()
        low_equity = (df['equity_tier'] == 'low').sum()
        underwater = (df['equity_tier'] == 'underwater').sum()

        logger.info(f"Equity analysis complete:")
        logger.info(f"  High equity ($50k+): {high_equity}")
        logger.info(f"  Medium equity ($20k-$50k): {medium_equity}")
        logger.info(f"  Low equity (<$20k): {low_equity}")
        logger.info(f"  Underwater: {underwater}")

        return df

    def get_equity_summary(self, df: pd.DataFrame) -> Dict:
        """
        Get summary statistics for equity analysis.

        Args:
            df: DataFrame with equity columns

        Returns:
            Dictionary with summary stats
        """
        if 'estimated_equity' not in df.columns:
            return {}

        return {
            'total_properties': len(df),
            'avg_equity': df['estimated_equity'].mean(),
            'median_equity': df['estimated_equity'].median(),
            'total_equity': df['estimated_equity'].sum(),
            'high_equity_count': (df['equity_tier'] == 'high').sum(),
            'medium_equity_count': (df['equity_tier'] == 'medium').sum(),
            'low_equity_count': (df['equity_tier'] == 'low').sum(),
            'underwater_count': (df['equity_tier'] == 'underwater').sum(),
            'avg_equity_percentage': df['equity_percentage'].mean(),
        }


# ========================================
# CLI Test
# ========================================

if __name__ == '__main__':
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print("\n[bold cyan]Equity Calculator Test[/bold cyan]\n")

    calc = EquityCalculator()

    # Test single property
    test_cases = [
        {'market_value': 150000, 'taxes_owed': 5000, 'is_absentee': False},
        {'market_value': 80000, 'taxes_owed': 15000, 'is_absentee': True},
        {'market_value': 200000, 'taxes_owed': 2000, 'is_absentee': False, 'years_owned': 15},
        {'market_value': 50000, 'taxes_owed': 20000, 'is_absentee': True},
    ]

    table = Table(title="Equity Calculations")
    table.add_column("Market Value", style="cyan", justify="right")
    table.add_column("Taxes Owed", style="red", justify="right")
    table.add_column("Est. Mortgage", style="yellow", justify="right")
    table.add_column("Est. Equity", style="green", justify="right")
    table.add_column("Equity %", justify="right")
    table.add_column("Tier", style="magenta")

    for case in test_cases:
        equity, pct, tier = calc.calculate_equity(**case)
        mortgage = calc.estimate_mortgage(
            case['market_value'],
            case.get('is_absentee', False),
            case.get('years_owned')
        )

        table.add_row(
            f"${case['market_value']:,}",
            f"${case['taxes_owed']:,}",
            f"${mortgage:,.0f}",
            f"${equity:,.0f}",
            f"{pct:.1f}%",
            tier.upper(),
        )

    console.print(table)

    # Test DataFrame
    console.print("\n[bold]Testing DataFrame Integration[/bold]\n")

    test_df = pd.DataFrame({
        'address': ['123 Main St', '456 Oak Ave', '789 Elm St'],
        'market_value': [150000, 80000, 200000],
        'taxes_owed': [5000, 15000, 2000],
        'is_absentee': [False, True, False],
        'property_age': [10, 5, 25],
    })

    result_df = calc.add_equity_columns(test_df)

    console.print(result_df[['address', 'market_value', 'estimated_equity', 'equity_tier']].to_string())
