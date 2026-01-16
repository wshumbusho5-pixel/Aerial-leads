"""
Aerial Leads - Generic Excel Data Loader

Loads tax delinquent properties from county Excel files using market configuration.
Works with any county that provides bulk Excel downloads.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime

from shared.config.settings import RAW_DATA_DIR
from shared.config.market_loader import MarketConfig
from shared.config.logging_config import log_success, log_failure, get_logger


class GenericExcelLoader:
    """
    Generic Excel data loader that works with any market configuration.

    Uses field mappings from MarketConfig to handle different county data formats.
    """

    def __init__(self, market_config: MarketConfig, data_dir: Path = RAW_DATA_DIR):
        self.logger = get_logger(f"ExcelLoader[{market_config.id}]")
        self.market = market_config
        self.data_dir = data_dir / market_config.id

        # Ensure market-specific data directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # Get file configuration
        self.files = market_config.tax_data.files
        self.field_mappings = market_config.tax_data.field_mappings

    def load_tax_delinquent_properties(
        self,
        min_amount_owed: Optional[float] = None,
        min_years_delinquent: Optional[int] = None,
        filter_by_zip: bool = True,
        max_properties: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Load tax delinquent properties from Excel files.

        Args:
            min_amount_owed: Minimum tax debt (uses market default if None)
            min_years_delinquent: Minimum years behind (uses market default if None)
            filter_by_zip: Filter to market's zip codes
            max_properties: Maximum properties to return

        Returns:
            DataFrame with tax delinquent properties
        """
        # Use market defaults if not specified
        min_amount_owed = min_amount_owed or self.market.data_quality.min_amount_owed
        min_years_delinquent = min_years_delinquent or self.market.data_quality.min_years_delinquent

        self.logger.info(f"Loading {self.market.name} tax data from Excel files...")

        # Step 1: Load tax detail (find delinquent properties)
        self.logger.info(f"Loading {self.files.get('tax_detail', 'TaxDetail.xlsx')}...")
        df_tax = self._load_tax_details()

        # Step 2: Load parcel data (addresses, owners)
        self.logger.info(f"Loading {self.files.get('parcel', 'Parcel.xlsx')}...")
        df_parcel = self._load_parcels()

        # Step 3: Load values (assessed values)
        self.logger.info(f"Loading {self.files.get('value', 'Value.xlsx')}...")
        df_value = self._load_values()

        # Step 4: Load building data (year_built, bedrooms, bathrooms, sqft)
        df_building = self._load_building()

        # Step 5: Join datasets
        self.logger.info("Joining datasets...")
        df_merged = self._merge_datasets(df_tax, df_parcel, df_value, df_building)

        # Step 5: Filter for delinquent properties
        self.logger.info("Filtering for tax delinquent properties...")
        df_delinquent = df_merged[df_merged['taxes_owed'] >= min_amount_owed].copy()

        # Step 6: Filter by zip codes if requested
        if filter_by_zip and self.market.zip_codes:
            df_delinquent = df_delinquent[
                df_delinquent['zip_code'].isin(self.market.zip_codes)
            ]
            self.logger.info(f"Filtered to {self.market.name} zip codes: {len(df_delinquent)} properties")

        # Step 7: Calculate years delinquent
        df_delinquent['years_delinquent'] = self._estimate_years_delinquent(df_delinquent)

        # Step 8: Filter by minimum years
        df_delinquent = df_delinquent[
            df_delinquent['years_delinquent'] >= min_years_delinquent
        ]

        # Step 9: Limit results if requested
        if max_properties:
            df_delinquent = df_delinquent.head(max_properties)

        # Step 10: Clean and format
        df_final = self._format_for_export(df_delinquent)

        log_success(f"Loaded {len(df_final)} tax delinquent properties from {self.market.name}")

        return df_final

    def _load_tax_details(self) -> pd.DataFrame:
        """Load tax detail file and extract total owed"""
        file_name = self.files.get('tax_detail', 'TaxDetail.xlsx')
        file_path = self.data_dir / file_name

        # Also check raw data dir (for backward compatibility)
        if not file_path.exists():
            file_path = RAW_DATA_DIR / file_name

        if not file_path.exists():
            raise FileNotFoundError(f"{file_name} not found at {file_path}")

        # Read Excel file
        df = pd.read_excel(file_path, engine='openpyxl')

        # Map columns using market config
        parcel_col = self.field_mappings.get('parcel_id', 'Parcel Id')
        taxes_col = self.field_mappings.get('taxes_owed', 'TotTotal')

        df = df[[parcel_col, taxes_col]].copy()
        df.columns = ['parcel_id', 'taxes_owed']

        # Remove nulls and zeros
        df = df[df['taxes_owed'].notna()]
        df = df[df['taxes_owed'] > 0]

        self.logger.info(f"Found {len(df)} parcels with tax debt")

        return df

    def _load_parcels(self) -> pd.DataFrame:
        """Load parcel file and extract property details"""
        file_name = self.files.get('parcel', 'Parcel.xlsx')
        file_path = self.data_dir / file_name

        # Also check raw data dir (for backward compatibility)
        if not file_path.exists():
            file_path = RAW_DATA_DIR / file_name

        if not file_path.exists():
            raise FileNotFoundError(f"{file_name} not found at {file_path}")

        # Read Excel file
        df = pd.read_excel(file_path, engine='openpyxl')

        # Build column mapping from market config (parcel file may have different parcel_id column)
        parcel_id_col = self.field_mappings.get('parcel_parcel_id', self.field_mappings.get('parcel_id', 'PARCEL ID'))
        column_map = {
            parcel_id_col: 'parcel_id',
            self.field_mappings.get('address', 'SiteAddress'): 'address',
            self.field_mappings.get('owner_name', 'OwnerName1'): 'owner_name',
            self.field_mappings.get('owner_address', 'OwnerAddress1'): 'owner_address',
            self.field_mappings.get('mailing_address', 'TaxpayerAddress1'): 'mailing_address',
            self.field_mappings.get('zip_code', 'ZipCode'): 'zip_code',
            self.field_mappings.get('property_type', 'LUCDesc'): 'property_type',
        }

        # Filter to columns that exist
        available_cols = [col for col in column_map.keys() if col in df.columns]
        df = df[available_cols].copy()

        # Rename columns
        rename_map = {k: v for k, v in column_map.items() if k in df.columns}
        df = df.rename(columns=rename_map)

        self.logger.info(f"Loaded {len(df)} parcel records")

        return df

    def _load_values(self) -> pd.DataFrame:
        """Load value file and extract assessed values"""
        file_name = self.files.get('value', 'Value.xlsx')
        file_path = self.data_dir / file_name

        # Also check raw data dir (for backward compatibility)
        if not file_path.exists():
            file_path = RAW_DATA_DIR / file_name

        if not file_path.exists():
            # Values file is optional
            self.logger.warning(f"{file_name} not found, skipping value data")
            return pd.DataFrame(columns=['parcel_id', 'market_value', 'assessed_value'])

        # Read Excel file
        df = pd.read_excel(file_path, engine='openpyxl')

        # Get column names from mapping
        parcel_col = self.field_mappings.get('parcel_id', 'Parcel Id')
        market_land_col = self.field_mappings.get('market_land', 'MarketLand')
        market_impr_col = self.field_mappings.get('market_improvements', 'MarketImpr')
        taxable_land_col = self.field_mappings.get('taxable_land', 'TaxableLand')
        taxable_impr_col = self.field_mappings.get('taxable_improvements', 'TaxableImpr')

        # Calculate total values
        if market_land_col in df.columns and market_impr_col in df.columns:
            df['market_value'] = df[market_land_col].fillna(0) + df[market_impr_col].fillna(0)
        else:
            df['market_value'] = 0

        if taxable_land_col in df.columns and taxable_impr_col in df.columns:
            df['assessed_value'] = df[taxable_land_col].fillna(0) + df[taxable_impr_col].fillna(0)
        else:
            df['assessed_value'] = df['market_value']

        # Keep only necessary columns
        if parcel_col in df.columns:
            df = df[[parcel_col, 'market_value', 'assessed_value']].copy()
            df = df.rename(columns={parcel_col: 'parcel_id'})
        else:
            df = pd.DataFrame(columns=['parcel_id', 'market_value', 'assessed_value'])

        # Remove duplicates
        df = df.drop_duplicates(subset=['parcel_id'], keep='last')

        self.logger.info(f"Loaded {len(df)} value records")

        return df

    def _load_building(self) -> pd.DataFrame:
        """Load building file and extract year built, bedrooms, bathrooms, sqft"""
        file_name = self.files.get('building', 'Residential.xlsx')
        file_path = self.data_dir / file_name

        # Also check raw data dir (for backward compatibility)
        if not file_path.exists():
            file_path = RAW_DATA_DIR / file_name

        if not file_path.exists():
            # Building file is optional
            self.logger.warning(f"{file_name} not found, skipping building data (year_built, bedrooms, etc.)")
            return pd.DataFrame(columns=['parcel_id', 'year_built', 'bedrooms', 'bathrooms', 'square_feet'])

        # Read Excel file
        self.logger.info(f"Loading building data from {file_name}...")
        df = pd.read_excel(file_path, engine='openpyxl')

        # Get column names from mapping (building file may have different parcel column name)
        parcel_col = self.field_mappings.get('building_parcel_id', self.field_mappings.get('parcel_id', 'PARCEL ID'))
        year_built_col = self.field_mappings.get('year_built', 'YRBLT')
        bedrooms_col = self.field_mappings.get('bedrooms', 'RMBED')
        bathrooms_col = self.field_mappings.get('bathrooms', 'FIXBATH')
        half_baths_col = self.field_mappings.get('half_baths', 'FIXHALF')
        sqft_col = self.field_mappings.get('square_feet', 'SFLA')

        # Build result dataframe
        result = pd.DataFrame()

        # Parcel ID
        if parcel_col in df.columns:
            result['parcel_id'] = df[parcel_col]
        else:
            self.logger.warning(f"Parcel ID column '{parcel_col}' not found in building file")
            return pd.DataFrame(columns=['parcel_id', 'year_built', 'bedrooms', 'bathrooms', 'square_feet'])

        # Year built
        if year_built_col in df.columns:
            result['year_built'] = pd.to_numeric(df[year_built_col], errors='coerce').fillna(0).astype(int)
        else:
            result['year_built'] = 0

        # Bedrooms
        if bedrooms_col in df.columns:
            result['bedrooms'] = pd.to_numeric(df[bedrooms_col], errors='coerce').fillna(0).astype(int)
        else:
            result['bedrooms'] = 0

        # Bathrooms (full + half)
        if bathrooms_col in df.columns:
            full_baths = pd.to_numeric(df[bathrooms_col], errors='coerce').fillna(0)
            if half_baths_col in df.columns:
                half_baths = pd.to_numeric(df[half_baths_col], errors='coerce').fillna(0)
                result['bathrooms'] = (full_baths + half_baths * 0.5).round(1)
            else:
                result['bathrooms'] = full_baths
        else:
            result['bathrooms'] = 0

        # Square feet
        if sqft_col in df.columns:
            result['square_feet'] = pd.to_numeric(df[sqft_col], errors='coerce').fillna(0).astype(int)
        else:
            result['square_feet'] = 0

        # Remove duplicates (keep first/primary building)
        result = result.drop_duplicates(subset=['parcel_id'], keep='first')

        self.logger.info(f"Loaded building data for {len(result)} properties")

        return result

    def _merge_datasets(
        self,
        df_tax: pd.DataFrame,
        df_parcel: pd.DataFrame,
        df_value: pd.DataFrame,
        df_building: pd.DataFrame = None
    ) -> pd.DataFrame:
        """Merge all datasets on parcel_id"""

        # Start with tax data
        df = df_tax.copy()

        # Merge parcel data
        if not df_parcel.empty:
            df = df.merge(df_parcel, on='parcel_id', how='left')

        # Merge value data
        if not df_value.empty:
            df = df.merge(df_value, on='parcel_id', how='left')

        # Merge building data (year_built, bedrooms, bathrooms, sqft)
        if df_building is not None and not df_building.empty:
            df = df.merge(df_building, on='parcel_id', how='left')
            # Fill missing building data
            df['year_built'] = df.get('year_built', pd.Series([0] * len(df))).fillna(0).astype(int)
            df['bedrooms'] = df.get('bedrooms', pd.Series([0] * len(df))).fillna(0).astype(int)
            df['bathrooms'] = df.get('bathrooms', pd.Series([0] * len(df))).fillna(0)
            df['square_feet'] = df.get('square_feet', pd.Series([0] * len(df))).fillna(0).astype(int)
        else:
            # Add empty columns if no building data
            df['year_built'] = 0
            df['bedrooms'] = 0
            df['bathrooms'] = 0
            df['square_feet'] = 0

        # Fill missing values
        df['assessed_value'] = df.get('assessed_value', pd.Series([0] * len(df))).fillna(0)
        df['market_value'] = df.get('market_value', pd.Series([0] * len(df))).fillna(0)

        # Convert zip code to string
        if 'zip_code' in df.columns:
            df['zip_code'] = df['zip_code'].fillna(0).astype(str).str.split('.').str[0]
            df['zip_code'] = df['zip_code'].replace('0', '')

        self.logger.info(f"Merged datasets: {len(df)} properties")

        return df

    def _estimate_years_delinquent(self, df: pd.DataFrame) -> pd.Series:
        """
        Estimate years delinquent based on tax amount owed.

        Uses market-specific annual tax rate from configuration.
        """
        # Get annual tax rate from market config
        annual_rate = self.market.scoring.estimated_annual_tax_rate

        # Calculate estimated annual tax
        estimated_annual_tax = df['assessed_value'] * annual_rate

        # Avoid division by zero - use reasonable default
        estimated_annual_tax = estimated_annual_tax.replace(0, 3000)

        # Calculate years delinquent
        years = (df['taxes_owed'] / estimated_annual_tax).fillna(0)

        # Round and cap between 1 and 10
        years = years.clip(lower=1, upper=10).round().astype(int)

        return years

    def _format_for_export(self, df: pd.DataFrame) -> pd.DataFrame:
        """Format data to match expected schema"""

        # Calculate tax debt ratio
        df['tax_debt_ratio'] = np.where(
            df['assessed_value'] > 0,
            df['taxes_owed'] / df['assessed_value'],
            0
        )

        # Detect absentee owners
        if 'mailing_address' in df.columns and 'owner_address' in df.columns:
            df['is_absentee'] = df['mailing_address'] != df['owner_address']
        else:
            df['is_absentee'] = False
        df['is_absentee'] = df['is_absentee'].fillna(False)

        # Add metadata
        df['data_source'] = f"{self.market.county} County (Excel)"
        df['market_id'] = self.market.id
        df['scraped_date'] = datetime.now().strftime('%Y-%m-%d')

        # Calculate property age if year_built is available
        if 'year_built' in df.columns:
            current_year = datetime.now().year
            df['property_age'] = df['year_built'].apply(
                lambda y: current_year - y if y > 1800 else 0
            )
        else:
            df['property_age'] = 0

        # Select and order columns
        columns = [
            'parcel_id',
            'address',
            'owner_name',
            'owner_address',
            'mailing_address',
            'zip_code',
            'assessed_value',
            'market_value',
            'taxes_owed',
            'years_delinquent',
            'tax_debt_ratio',
            'is_absentee',
            'property_type',
            'year_built',
            'property_age',
            'bedrooms',
            'bathrooms',
            'square_feet',
            'data_source',
            'market_id',
            'scraped_date'
        ]

        # Only include columns that exist
        available_columns = [col for col in columns if col in df.columns]

        return df[available_columns].copy()

    def export_to_csv(self, df: pd.DataFrame, filename: Optional[str] = None) -> str:
        """Export properties to CSV"""
        if df.empty:
            log_failure("No properties to export")
            return ''

        if filename is None:
            filename = f"{self.market.id}_tax_data.csv"

        output_path = self.data_dir / filename
        df.to_csv(output_path, index=False)

        log_success(f"Exported {len(df)} properties to {output_path}")
        return str(output_path)


# ========================================
# CLI Entry Point
# ========================================

if __name__ == '__main__':
    """Test the generic loader with Columbus"""
    from shared.config.market_loader import load_market

    # Load Columbus market config
    market = load_market('columbus_oh')

    # Create loader
    loader = GenericExcelLoader(market)

    # Load first 100 delinquent properties
    df = loader.load_tax_delinquent_properties(
        min_amount_owed=2000,
        min_years_delinquent=2,
        max_properties=100
    )

    # Show summary
    print(f"\nLoaded: {len(df)} properties")
    print(f"Average tax debt: ${df['taxes_owed'].mean():,.0f}")
    print(f"Average years delinquent: {df['years_delinquent'].mean():.1f}")
    print(f"\nTop 5 by tax debt:")
    print(df.nlargest(5, 'taxes_owed')[['address', 'owner_name', 'taxes_owed', 'years_delinquent']])
