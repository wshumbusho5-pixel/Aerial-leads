"""
Comparable Sales (Comps) Estimator

Estimates After Repair Value (ARV) based on:
- Market averages for the area
- Property characteristics
- Price per square foot analysis

Note: For production, integrate with Zillow, Redfin, or PropStream API
for actual comparable sales data.
"""

import pandas as pd
from typing import Dict, Optional, Tuple, List
from pathlib import Path

try:
    from shared.config.logging_config import get_logger
    logger = get_logger("CompsEstimator")
except ImportError:
    import logging
    logger = logging.getLogger("CompsEstimator")


class CompsEstimator:
    """
    Estimates After Repair Value (ARV) for properties.

    Uses market averages and property characteristics to estimate value.
    For production, replace with actual comp data from MLS or API.
    """

    # Average price per square foot by zip code (Columbus, OH data)
    # These are estimates - replace with real data for production
    ZIP_CODE_PSF = {
        '43201': 185,  # Short North / Italian Village
        '43202': 170,  # Clintonville
        '43203': 85,   # Near East
        '43204': 95,   # Hilltop
        '43205': 130,  # Olde Towne East
        '43206': 165,  # German Village
        '43207': 90,   # South Side
        '43209': 155,  # Bexley adjacent
        '43210': 200,  # Ohio State area
        '43211': 80,   # Linden
        '43212': 185,  # Grandview
        '43213': 90,   # East Columbus
        '43214': 135,  # Worthington adjacent
        '43215': 220,  # Downtown
        '43217': 110,  # Lockbourne
        '43219': 75,   # East Side
        '43220': 175,  # Upper Arlington adjacent
        '43221': 185,  # Upper Arlington
        '43222': 85,   # Franklinton
        '43223': 95,   # South Side
        '43224': 90,   # Northeast
        '43227': 70,   # Whitehall area
        '43228': 100,  # Westland
        '43229': 105,  # Northland
        '43230': 130,  # Gahanna adjacent
        '43231': 110,  # Northland
        '43232': 75,   # Southeast
    }

    # Default PSF for unknown zip codes
    DEFAULT_PSF = 100

    # Adjustment factors
    CONDITION_ADJUSTMENTS = {
        'excellent': 1.15,
        'good': 1.05,
        'average': 1.00,
        'fair': 0.90,
        'poor': 0.75,
        'distressed': 0.65,
    }

    # Repair cost estimates per square foot
    REPAIR_COSTS = {
        'light': 15,     # Cosmetic only
        'moderate': 35,  # Some systems work
        'heavy': 60,     # Major renovation
        'gut': 100,      # Full rehab
    }

    def __init__(self):
        """Initialize comps estimator."""
        pass

    def get_market_psf(self, zip_code: str) -> float:
        """
        Get price per square foot for a zip code.

        Args:
            zip_code: 5-digit zip code

        Returns:
            Price per square foot estimate
        """
        zip5 = str(zip_code)[:5]
        return self.ZIP_CODE_PSF.get(zip5, self.DEFAULT_PSF)

    def estimate_condition(
        self,
        years_delinquent: int,
        violations: int,
        property_age: int
    ) -> str:
        """
        Estimate property condition based on distress signals.

        Args:
            years_delinquent: Years behind on taxes
            violations: Number of code violations
            property_age: Age of property in years

        Returns:
            Condition rating
        """
        # Higher distress = worse condition
        distress_score = (years_delinquent * 2) + (violations * 3)

        if distress_score >= 10:
            return 'distressed'
        elif distress_score >= 7:
            return 'poor'
        elif distress_score >= 4:
            return 'fair'
        elif property_age > 50:
            return 'fair'
        elif property_age > 30:
            return 'average'
        else:
            return 'good'

    def estimate_arv(
        self,
        zip_code: str,
        square_feet: float,
        condition: str = None,
        years_delinquent: int = 0,
        violations: int = 0,
        property_age: int = 0,
    ) -> Tuple[float, Dict]:
        """
        Estimate After Repair Value (ARV).

        Args:
            zip_code: Property zip code
            square_feet: Property square footage
            condition: Property condition (or auto-estimate)
            years_delinquent: For condition estimation
            violations: For condition estimation
            property_age: For condition estimation

        Returns:
            Tuple of (ARV estimate, details dict)
        """
        if square_feet <= 0:
            return 0.0, {'error': 'No square footage data'}

        # Get market PSF
        market_psf = self.get_market_psf(zip_code)

        # Estimate condition if not provided
        if not condition:
            condition = self.estimate_condition(
                years_delinquent, violations, property_age
            )

        # Calculate base ARV (fully renovated value)
        base_arv = square_feet * market_psf

        # Adjust for condition (current as-is value)
        condition_factor = self.CONDITION_ADJUSTMENTS.get(condition, 1.0)
        as_is_value = base_arv * condition_factor

        # Estimate repair costs based on condition
        if condition in ['distressed', 'poor']:
            repair_level = 'heavy'
        elif condition == 'fair':
            repair_level = 'moderate'
        else:
            repair_level = 'light'

        repair_cost = square_feet * self.REPAIR_COSTS[repair_level]

        # Calculate potential profit
        potential_profit = base_arv - as_is_value - repair_cost

        return base_arv, {
            'arv': base_arv,
            'as_is_value': as_is_value,
            'market_psf': market_psf,
            'condition': condition,
            'repair_level': repair_level,
            'repair_cost_estimate': repair_cost,
            'potential_profit': potential_profit,
            'profit_margin': (potential_profit / base_arv * 100) if base_arv > 0 else 0,
        }

    def add_arv_columns(
        self,
        df: pd.DataFrame,
        zip_col: str = 'zip_code',
        sqft_col: str = 'square_feet',
    ) -> pd.DataFrame:
        """
        Add ARV and comp data columns to DataFrame.

        Args:
            df: DataFrame with property data
            zip_col: Name of zip code column
            sqft_col: Name of square footage column

        Returns:
            DataFrame with ARV columns added
        """
        df = df.copy()

        # Initialize columns
        df['arv_estimate'] = 0.0
        df['as_is_value'] = 0.0
        df['repair_cost_estimate'] = 0.0
        df['potential_profit'] = 0.0
        df['market_psf'] = 0.0
        df['estimated_condition'] = 'unknown'

        estimated_count = 0

        for idx, row in df.iterrows():
            zip_code = str(row.get(zip_col, ''))
            square_feet = float(row.get(sqft_col, 0) or 0)
            years_del = int(row.get('years_delinquent', 0) or 0)
            violations = int(row.get('total_violations', 0) or 0)
            property_age = int(row.get('property_age', 0) or 0)

            if square_feet > 0:
                arv, details = self.estimate_arv(
                    zip_code=zip_code,
                    square_feet=square_feet,
                    years_delinquent=years_del,
                    violations=violations,
                    property_age=property_age,
                )

                df.at[idx, 'arv_estimate'] = details.get('arv', 0)
                df.at[idx, 'as_is_value'] = details.get('as_is_value', 0)
                df.at[idx, 'repair_cost_estimate'] = details.get('repair_cost_estimate', 0)
                df.at[idx, 'potential_profit'] = details.get('potential_profit', 0)
                df.at[idx, 'market_psf'] = details.get('market_psf', 0)
                df.at[idx, 'estimated_condition'] = details.get('condition', 'unknown')

                if arv > 0:
                    estimated_count += 1

        logger.info(f"ARV estimation complete: {estimated_count}/{len(df)} properties")

        return df

    def get_arv_summary(self, df: pd.DataFrame) -> Dict:
        """
        Get summary statistics for ARV estimates.

        Args:
            df: DataFrame with ARV columns

        Returns:
            Dictionary with summary stats
        """
        if 'arv_estimate' not in df.columns:
            return {}

        valid = df[df['arv_estimate'] > 0]

        return {
            'total_properties': len(df),
            'with_arv': len(valid),
            'avg_arv': valid['arv_estimate'].mean() if len(valid) > 0 else 0,
            'total_arv': valid['arv_estimate'].sum(),
            'avg_profit': valid['potential_profit'].mean() if len(valid) > 0 else 0,
            'total_potential_profit': valid['potential_profit'].sum(),
            'avg_repair_cost': valid['repair_cost_estimate'].mean() if len(valid) > 0 else 0,
        }


# ========================================
# CLI Test
# ========================================

if __name__ == '__main__':
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print("\n[bold cyan]Comps Estimator Test[/bold cyan]\n")

    estimator = CompsEstimator()

    # Test properties
    test_properties = [
        {'zip': '43206', 'sqft': 1500, 'years_del': 2, 'violations': 1},
        {'zip': '43204', 'sqft': 1200, 'years_del': 4, 'violations': 3},
        {'zip': '43215', 'sqft': 1800, 'years_del': 1, 'violations': 0},
        {'zip': '43211', 'sqft': 1000, 'years_del': 5, 'violations': 2},
    ]

    table = Table(title="ARV Estimates")
    table.add_column("Zip", style="cyan")
    table.add_column("Sq Ft", justify="right")
    table.add_column("Condition", style="yellow")
    table.add_column("ARV", justify="right", style="green")
    table.add_column("As-Is", justify="right")
    table.add_column("Repairs", justify="right", style="red")
    table.add_column("Profit", justify="right", style="magenta")

    for prop in test_properties:
        arv, details = estimator.estimate_arv(
            zip_code=prop['zip'],
            square_feet=prop['sqft'],
            years_delinquent=prop['years_del'],
            violations=prop['violations'],
            property_age=50
        )

        table.add_row(
            prop['zip'],
            f"{prop['sqft']:,}",
            details['condition'].upper(),
            f"${details['arv']:,.0f}",
            f"${details['as_is_value']:,.0f}",
            f"${details['repair_cost_estimate']:,.0f}",
            f"${details['potential_profit']:,.0f}",
        )

    console.print(table)
