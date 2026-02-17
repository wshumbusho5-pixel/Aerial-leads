"""
Lifeline Home Buyers - Lead Integration Module

Integrates probate and sheriff sale leads with tax delinquent data
to create comprehensive lead profiles for motivation scoring.
"""

import pandas as pd
import re
from typing import Optional, Tuple
from shared.config.logging_config import get_logger


class LeadIntegrator:
    """
    Integrates multiple lead sources into a unified dataset.

    Matches:
    - Probate cases to properties by owner name
    - Sheriff sales to properties by address
    - Adds flags for motivation scoring
    """

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    def integrate_all_sources(
        self,
        tax_df: pd.DataFrame,
        probate_df: Optional[pd.DataFrame] = None,
        sheriff_df: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Integrate all lead sources into the tax delinquent data.

        Args:
            tax_df: Main tax delinquent DataFrame
            probate_df: Probate cases DataFrame (optional)
            sheriff_df: Sheriff sale properties DataFrame (optional)

        Returns:
            Enriched DataFrame with probate/foreclosure flags
        """
        self.logger.info("Starting lead integration...")

        # Start with tax data
        df = tax_df.copy()

        # Initialize scoring columns
        df['is_probate'] = False
        df['probate_case_number'] = ''
        df['decedent_name'] = ''
        df['is_pre_foreclosure'] = False
        df['is_sheriff_sale'] = False
        df['auction_date'] = ''
        df['starting_bid'] = 0

        # Integrate probate data
        if probate_df is not None and not probate_df.empty:
            df = self._integrate_probate(df, probate_df)

        # Integrate sheriff sale data
        if sheriff_df is not None and not sheriff_df.empty:
            df = self._integrate_sheriff_sales(df, sheriff_df)

        # Log summary
        probate_count = df['is_probate'].sum()
        sheriff_count = df['is_sheriff_sale'].sum()
        self.logger.info(f"Integration complete: {probate_count} probate matches, {sheriff_count} sheriff sale matches")

        return df

    def _integrate_probate(
        self,
        tax_df: pd.DataFrame,
        probate_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Match probate cases to tax records by owner name.

        Uses fuzzy matching on normalized names.
        """
        self.logger.info(f"Integrating {len(probate_df)} probate cases...")

        # Normalize owner names in tax data
        tax_df['_owner_normalized'] = tax_df['owner_name'].apply(self._normalize_name)

        # Normalize decedent names in probate data
        probate_df = probate_df.copy()
        probate_df['_decedent_normalized'] = probate_df['decedent_name'].apply(self._normalize_name)

        # Create lookup dict for probate cases
        probate_lookup = {}
        for _, row in probate_df.iterrows():
            normalized = row['_decedent_normalized']
            if normalized:
                probate_lookup[normalized] = {
                    'case_number': row.get('case_number', ''),
                    'decedent_name': row.get('decedent_name', ''),
                    'case_type': row.get('case_type', ''),
                    'filing_date': row.get('filing_date', '')
                }

        # Match by exact normalized name
        matches = 0
        for idx, row in tax_df.iterrows():
            owner_norm = row['_owner_normalized']

            if owner_norm in probate_lookup:
                probate_info = probate_lookup[owner_norm]
                tax_df.at[idx, 'is_probate'] = True
                tax_df.at[idx, 'probate_case_number'] = probate_info['case_number']
                tax_df.at[idx, 'decedent_name'] = probate_info['decedent_name']
                matches += 1
            else:
                # Try partial match (last name match)
                owner_parts = owner_norm.split()
                if owner_parts:
                    last_name = owner_parts[-1] if len(owner_parts) > 1 else owner_parts[0]
                    for decedent_norm, probate_info in probate_lookup.items():
                        decedent_parts = decedent_norm.split()
                        if decedent_parts:
                            decedent_last = decedent_parts[0]  # Usually "LASTNAME, FIRSTNAME"
                            if last_name == decedent_last and len(last_name) > 3:
                                tax_df.at[idx, 'is_probate'] = True
                                tax_df.at[idx, 'probate_case_number'] = probate_info['case_number']
                                tax_df.at[idx, 'decedent_name'] = probate_info['decedent_name']
                                matches += 1
                                break

        # Clean up temp column
        tax_df.drop('_owner_normalized', axis=1, inplace=True)

        self.logger.info(f"Matched {matches} properties to probate cases")
        return tax_df

    def _integrate_sheriff_sales(
        self,
        tax_df: pd.DataFrame,
        sheriff_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Match sheriff sale properties to tax records by address.

        Uses normalized address matching.
        """
        self.logger.info(f"Integrating {len(sheriff_df)} sheriff sale properties...")

        # Normalize addresses in tax data
        tax_df['_address_normalized'] = tax_df['address'].apply(self._normalize_address)

        # Normalize addresses in sheriff data
        sheriff_df = sheriff_df.copy()
        sheriff_df['_address_normalized'] = sheriff_df['address'].apply(self._normalize_address)

        # Create lookup dict for sheriff sales
        sheriff_lookup = {}
        for _, row in sheriff_df.iterrows():
            normalized = row['_address_normalized']
            if normalized:
                sheriff_lookup[normalized] = {
                    'auction_date': row.get('auction_date', ''),
                    'starting_bid': row.get('starting_bid', 0),
                    'city': row.get('city', ''),
                    'case_number': row.get('case_number', '')
                }

        # Match by normalized address
        matches = 0
        for idx, row in tax_df.iterrows():
            addr_norm = row['_address_normalized']

            if addr_norm in sheriff_lookup:
                sheriff_info = sheriff_lookup[addr_norm]
                tax_df.at[idx, 'is_sheriff_sale'] = True
                tax_df.at[idx, 'is_pre_foreclosure'] = True
                tax_df.at[idx, 'auction_date'] = sheriff_info['auction_date']
                tax_df.at[idx, 'starting_bid'] = sheriff_info['starting_bid']
                matches += 1
            else:
                # Try matching just the street number and name
                addr_parts = self._extract_street_parts(addr_norm)
                if addr_parts:
                    for sheriff_addr, sheriff_info in sheriff_lookup.items():
                        sheriff_parts = self._extract_street_parts(sheriff_addr)
                        if addr_parts == sheriff_parts:
                            tax_df.at[idx, 'is_sheriff_sale'] = True
                            tax_df.at[idx, 'is_pre_foreclosure'] = True
                            tax_df.at[idx, 'auction_date'] = sheriff_info['auction_date']
                            tax_df.at[idx, 'starting_bid'] = sheriff_info['starting_bid']
                            matches += 1
                            break

        # Clean up temp column
        tax_df.drop('_address_normalized', axis=1, inplace=True)

        self.logger.info(f"Matched {matches} properties to sheriff sales")
        return tax_df

    def _normalize_name(self, name: str) -> str:
        """Normalize a name for matching."""
        if not name or pd.isna(name):
            return ''

        # Uppercase and strip
        name = str(name).upper().strip()

        # Remove common suffixes
        suffixes = [' JR', ' SR', ' II', ' III', ' IV', ' EST', ' ESTATE', ' TR', ' TRUST']
        for suffix in suffixes:
            name = name.replace(suffix, '')

        # Remove punctuation
        name = re.sub(r'[^\w\s]', '', name)

        # Remove extra spaces
        name = ' '.join(name.split())

        return name

    def _normalize_address(self, address: str) -> str:
        """Normalize an address for matching."""
        if not address or pd.isna(address):
            return ''

        # Uppercase and strip
        addr = str(address).upper().strip()

        # Standardize common abbreviations
        replacements = {
            ' STREET': ' ST',
            ' AVENUE': ' AVE',
            ' ROAD': ' RD',
            ' DRIVE': ' DR',
            ' LANE': ' LN',
            ' COURT': ' CT',
            ' BOULEVARD': ' BLVD',
            ' CIRCLE': ' CIR',
            ' PLACE': ' PL',
            ' NORTH ': ' N ',
            ' SOUTH ': ' S ',
            ' EAST ': ' E ',
            ' WEST ': ' W ',
        }

        for old, new in replacements.items():
            addr = addr.replace(old, new)

        # Remove apartment/unit info
        addr = re.sub(r'\s*(APT|UNIT|#|STE|SUITE)\s*\d*\w*', '', addr)

        # Remove punctuation
        addr = re.sub(r'[^\w\s]', '', addr)

        # Remove extra spaces
        addr = ' '.join(addr.split())

        return addr

    def _extract_street_parts(self, address: str) -> Optional[Tuple[str, str]]:
        """Extract street number and name from address."""
        if not address:
            return None

        # Match pattern: number + street name
        match = re.match(r'^(\d+)\s+(.+?)(?:\s+(?:ST|AVE|RD|DR|LN|CT|BLVD|CIR|PL|WAY))?', address)
        if match:
            return (match.group(1), match.group(2))

        return None

    def add_standalone_probate_leads(
        self,
        main_df: pd.DataFrame,
        probate_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Add probate leads that didn't match tax records as standalone entries.

        These are still valuable leads even without tax delinquency.
        """
        self.logger.info("Adding standalone probate leads...")

        # Get probate cases that weren't matched
        matched_cases = set(main_df[main_df['is_probate']]['probate_case_number'].tolist())

        standalone = []
        for _, row in probate_df.iterrows():
            case_num = row.get('case_number', '')
            if case_num not in matched_cases:
                standalone.append({
                    'address': '',  # Unknown
                    'owner_name': row.get('decedent_name', ''),
                    'is_probate': True,
                    'probate_case_number': case_num,
                    'decedent_name': row.get('decedent_name', ''),
                    'case_type': row.get('case_type', ''),
                    'filing_date': row.get('filing_date', ''),
                    'lead_type': 'probate',
                    'taxes_owed': 0,
                    'years_delinquent': 0,
                })

        if standalone:
            standalone_df = pd.DataFrame(standalone)
            main_df = pd.concat([main_df, standalone_df], ignore_index=True)
            self.logger.info(f"Added {len(standalone)} standalone probate leads")

        return main_df

    def add_standalone_sheriff_leads(
        self,
        main_df: pd.DataFrame,
        sheriff_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Add sheriff sale leads that didn't match tax records as standalone entries.
        """
        self.logger.info("Adding standalone sheriff sale leads...")

        # Normalize existing addresses
        main_addresses = set(main_df['address'].apply(self._normalize_address).tolist())

        standalone = []
        for _, row in sheriff_df.iterrows():
            addr_norm = self._normalize_address(row.get('address', ''))
            if addr_norm and addr_norm not in main_addresses:
                standalone.append({
                    'address': row.get('address', ''),
                    'city': row.get('city', ''),
                    'zip_code': row.get('zip_code', ''),
                    'owner_name': row.get('owner_name', ''),
                    'is_sheriff_sale': True,
                    'is_pre_foreclosure': True,
                    'auction_date': row.get('auction_date', ''),
                    'starting_bid': row.get('starting_bid', 0),
                    'lead_type': 'sheriff_sale',
                    'taxes_owed': 0,
                    'years_delinquent': 0,
                    'bedrooms': row.get('bedrooms', 0),
                    'bathrooms': row.get('bathrooms', 0),
                    'sqft': row.get('sqft', 0),
                })

        if standalone:
            standalone_df = pd.DataFrame(standalone)
            main_df = pd.concat([main_df, standalone_df], ignore_index=True)
            self.logger.info(f"Added {len(standalone)} standalone sheriff sale leads")

        return main_df


# Example usage
if __name__ == '__main__':
    # Test with sample data
    tax_data = pd.DataFrame({
        'address': ['123 Main St', '456 Oak Ave', '789 Elm Rd'],
        'owner_name': ['John Smith', 'Jane Doe', 'Bob Johnson'],
        'taxes_owed': [5000, 3000, 8000],
        'years_delinquent': [2, 1, 3],
    })

    probate_data = pd.DataFrame({
        'case_number': ['2024-001', '2024-002'],
        'decedent_name': ['Smith, John', 'Williams, Mary'],
        'case_type': ['ESTATE', 'ESTATE'],
        'filing_date': ['01/15/2024', '02/01/2024'],
    })

    sheriff_data = pd.DataFrame({
        'address': ['789 Elm Road', '999 Pine St'],
        'city': ['Columbus', 'Columbus'],
        'auction_date': ['03/15/2024', '03/22/2024'],
        'starting_bid': [50000, 75000],
    })

    integrator = LeadIntegrator()
    result = integrator.integrate_all_sources(tax_data, probate_data, sheriff_data)

    print("\nIntegration Results:")
    print(result[['address', 'owner_name', 'is_probate', 'is_sheriff_sale']].to_string())
