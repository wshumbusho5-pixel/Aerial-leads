"""
Lifeline Home Buyers - Probate to Property Matcher

Matches probate case decedent names to property ownership records
from Franklin County Auditor data to find properties owned by deceased.

This enables skip tracing with both name + address for higher hit rates.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from pathlib import Path
import re
from difflib import SequenceMatcher

from shared.config.settings import RAW_DATA_DIR, PROCESSED_DATA_DIR

try:
    from shared.config.logging_config import get_logger
    logger = get_logger("ProbateMatcher")
except ImportError:
    import logging
    logger = logging.getLogger("ProbateMatcher")


class ProbateMatcher:
    """
    Match probate cases to property records by owner name.

    Uses Franklin County Parcel.xlsx to find properties owned by decedents.
    """

    def __init__(self, data_dir: Path = RAW_DATA_DIR):
        """
        Initialize the matcher.

        Args:
            data_dir: Directory containing Parcel.xlsx
        """
        self.data_dir = data_dir
        self.parcel_file = data_dir / 'Parcel.xlsx'
        self.property_df = None

    def load_property_records(self) -> bool:
        """
        Load property records from Franklin County Parcel.xlsx.

        Returns:
            True if loaded successfully, False otherwise
        """
        if not self.parcel_file.exists():
            logger.warning(f"Parcel.xlsx not found at {self.parcel_file}")
            return False

        try:
            logger.info("Loading Franklin County property records...")

            df = pd.read_excel(self.parcel_file, engine='openpyxl')

            # Keep relevant columns (Franklin County format)
            columns_map = {
                'PARCEL ID': 'parcel_id',
                'OwnerName1': 'owner_name',
                'SiteAddress': 'address',
                'TaxpayerAddress1': 'mailing_address',
                'ZipCode': 'zip_code',
                'City': 'city',
                'LUCDesc': 'property_type',
            }

            # Filter to columns that exist
            existing_cols = {k: v for k, v in columns_map.items() if k in df.columns}
            df = df[list(existing_cols.keys())].copy()
            df.columns = list(existing_cols.values())

            # Clean owner names
            df['owner_name'] = df['owner_name'].fillna('').astype(str).str.upper().str.strip()
            df['owner_name_normalized'] = df['owner_name'].apply(self._normalize_name)

            # Clean addresses
            df['address'] = df['address'].fillna('').astype(str).str.strip()

            # Clean zip codes
            if 'zip_code' in df.columns:
                df['zip_code'] = df['zip_code'].fillna(0).astype(int).astype(str)
                df['zip_code'] = df['zip_code'].replace('0', '')

            self.property_df = df
            logger.info(f"Loaded {len(df)} property records")

            return True

        except Exception as e:
            logger.error(f"Error loading property records: {e}")
            return False

    def _normalize_name(self, name: str) -> str:
        """
        Normalize a name for matching.

        - Remove suffixes (JR, SR, II, III, etc.)
        - Remove titles (MR, MRS, DR, etc.)
        - Remove punctuation
        - Standardize format to "LASTNAME FIRSTNAME"
        """
        if not name:
            return ''

        name = name.upper().strip()

        # Remove common suffixes
        suffixes = [' JR', ' SR', ' II', ' III', ' IV', ' MD', ' PHD', ' ESQ',
                   ' JR.', ' SR.', ' JUNIOR', ' SENIOR']
        for suffix in suffixes:
            name = name.replace(suffix, '')

        # Remove titles
        titles = ['MR ', 'MRS ', 'MS ', 'DR ', 'MISS ', 'MR. ', 'MRS. ', 'MS. ', 'DR. ']
        for title in titles:
            if name.startswith(title):
                name = name[len(title):]

        # Remove punctuation except spaces
        name = re.sub(r'[^\w\s]', '', name)

        # Remove extra spaces
        name = ' '.join(name.split())

        return name

    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """
        Calculate similarity between two names.

        Returns:
            Similarity score between 0 and 1
        """
        if not name1 or not name2:
            return 0.0

        # Exact match
        if name1 == name2:
            return 1.0

        # Check if one contains the other (partial match)
        if name1 in name2 or name2 in name1:
            return 0.9

        # Split into parts and check overlap
        parts1 = set(name1.split())
        parts2 = set(name2.split())

        if len(parts1) == 0 or len(parts2) == 0:
            return 0.0

        # Calculate Jaccard similarity of name parts
        intersection = len(parts1 & parts2)
        union = len(parts1 | parts2)
        jaccard = intersection / union if union > 0 else 0

        # Also use sequence matching for overall similarity
        sequence_sim = SequenceMatcher(None, name1, name2).ratio()

        # Weight both methods
        return max(jaccard, sequence_sim)

    def find_properties_by_owner(
        self,
        owner_name: str,
        min_similarity: float = 0.7
    ) -> pd.DataFrame:
        """
        Find properties owned by a given name.

        Args:
            owner_name: Name to search for
            min_similarity: Minimum name similarity score (0-1)

        Returns:
            DataFrame of matching properties
        """
        if self.property_df is None:
            if not self.load_property_records():
                return pd.DataFrame()

        normalized_search = self._normalize_name(owner_name)

        if not normalized_search:
            return pd.DataFrame()

        # Calculate similarity for each property owner
        self.property_df['similarity'] = self.property_df['owner_name_normalized'].apply(
            lambda x: self._calculate_similarity(normalized_search, x)
        )

        # Filter by minimum similarity
        matches = self.property_df[self.property_df['similarity'] >= min_similarity].copy()

        # Sort by similarity (best matches first)
        matches = matches.sort_values('similarity', ascending=False)

        return matches

    def match_probate_to_properties(
        self,
        probate_df: pd.DataFrame,
        decedent_col: str = 'decedent_name',
        min_similarity: float = 0.75,
        progress_callback=None
    ) -> pd.DataFrame:
        """
        Match probate cases to property records.

        Args:
            probate_df: DataFrame with probate cases
            decedent_col: Column containing decedent names
            min_similarity: Minimum name match similarity
            progress_callback: Optional callback(current, total) for progress

        Returns:
            Enhanced probate DataFrame with property info
        """
        if self.property_df is None:
            if not self.load_property_records():
                logger.error("Cannot match - no property records loaded")
                return probate_df

        probate_df = probate_df.copy()

        # Initialize new columns
        probate_df['property_address'] = None
        probate_df['property_city'] = None
        probate_df['property_zip'] = None
        probate_df['property_parcel_id'] = None
        probate_df['property_type'] = None
        probate_df['match_confidence'] = 0.0
        probate_df['properties_found'] = 0

        total = len(probate_df)
        matched_count = 0

        logger.info(f"Matching {total} probate cases to property records...")

        for idx, row in probate_df.iterrows():
            decedent_name = str(row.get(decedent_col, ''))

            if not decedent_name or decedent_name.lower() == 'nan':
                continue

            # Find matching properties
            matches = self.find_properties_by_owner(decedent_name, min_similarity)

            if len(matches) > 0:
                matched_count += 1

                # Use best match
                best_match = matches.iloc[0]

                probate_df.at[idx, 'property_address'] = best_match.get('address', '')
                probate_df.at[idx, 'property_city'] = best_match.get('city', 'Columbus')
                probate_df.at[idx, 'property_zip'] = best_match.get('zip_code', '')
                probate_df.at[idx, 'property_parcel_id'] = best_match.get('parcel_id', '')
                probate_df.at[idx, 'property_type'] = best_match.get('property_type', '')
                probate_df.at[idx, 'match_confidence'] = best_match.get('similarity', 0)
                probate_df.at[idx, 'properties_found'] = len(matches)

            # Progress callback
            if progress_callback:
                progress_callback(idx + 1, total)

        match_rate = (matched_count / total * 100) if total > 0 else 0
        logger.info(f"Matched {matched_count}/{total} probate cases ({match_rate:.1f}%)")

        return probate_df

    def get_match_stats(self, probate_df: pd.DataFrame) -> Dict:
        """
        Get statistics about probate-property matching.

        Args:
            probate_df: DataFrame with match results

        Returns:
            Dict with statistics
        """
        total = len(probate_df)
        matched = len(probate_df[probate_df['properties_found'] > 0])

        return {
            'total_cases': total,
            'matched_cases': matched,
            'match_rate': (matched / total * 100) if total > 0 else 0,
            'avg_confidence': probate_df['match_confidence'].mean() if 'match_confidence' in probate_df.columns else 0,
            'multi_property_owners': len(probate_df[probate_df['properties_found'] > 1])
        }


# Convenience function
def match_probate_cases(probate_file: Path = None, output_file: Path = None) -> pd.DataFrame:
    """
    Match probate cases to properties and save results.

    Args:
        probate_file: Path to probate CSV (default: data/processed/probate_leads.csv)
        output_file: Path to save results (default: same as input)

    Returns:
        Enhanced DataFrame
    """
    if probate_file is None:
        probate_file = PROCESSED_DATA_DIR / 'probate_leads.csv'

    if output_file is None:
        output_file = probate_file

    if not probate_file.exists():
        logger.error(f"Probate file not found: {probate_file}")
        return pd.DataFrame()

    # Load probate data
    probate_df = pd.read_csv(probate_file)

    # Match to properties
    matcher = ProbateMatcher()
    enhanced_df = matcher.match_probate_to_properties(probate_df)

    # Save results
    enhanced_df.to_csv(output_file, index=False)
    logger.info(f"Saved enhanced probate data to {output_file}")

    # Print stats
    stats = matcher.get_match_stats(enhanced_df)
    logger.info(f"Match stats: {stats}")

    return enhanced_df


# CLI Test
if __name__ == '__main__':
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print("\n[bold cyan]Probate to Property Matcher Test[/bold cyan]\n")

    # Test matching
    matcher = ProbateMatcher()

    if matcher.load_property_records():
        # Test with a sample name
        test_name = "SMITH JOHN"
        console.print(f"Searching for properties owned by: [yellow]{test_name}[/yellow]")

        matches = matcher.find_properties_by_owner(test_name, min_similarity=0.8)

        if len(matches) > 0:
            console.print(f"Found [green]{len(matches)}[/green] matching properties\n")

            table = Table(title="Top Matches")
            table.add_column("Owner", style="cyan")
            table.add_column("Address", style="green")
            table.add_column("Similarity", style="yellow")

            for _, row in matches.head(5).iterrows():
                table.add_row(
                    row['owner_name'][:30],
                    row['address'][:40],
                    f"{row['similarity']:.2f}"
                )

            console.print(table)
        else:
            console.print("[red]No matches found[/red]")
    else:
        console.print("[red]Could not load property records. Make sure Parcel.xlsx exists.[/red]")
