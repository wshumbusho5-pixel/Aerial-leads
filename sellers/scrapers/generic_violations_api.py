"""
Lifeline Home Buyers - Generic Code Violations API Client

Retrieves code enforcement violations from ArcGIS REST APIs using market configuration.
Works with any city/county that uses ArcGIS for open data.
"""

import requests
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime

from sellers.scrapers.base_scraper import BaseScraper
from shared.config.market_loader import MarketConfig
from shared.config.logging_config import log_success, log_failure


class GenericViolationsAPI(BaseScraper):
    """
    Generic ArcGIS REST API client for code violations.

    Uses field mappings from MarketConfig to handle different city data formats.
    """

    def __init__(self, market_config: MarketConfig):
        super().__init__()
        self.market = market_config
        self.logger = self.logger  # Already set by BaseScraper

        # Get violations config
        self.api_url = market_config.violations.url
        self.query_field = market_config.violations.query_field
        self.max_records = market_config.violations.max_records_per_request
        self.field_mappings = market_config.violations.field_mappings

        # Update logger name
        self.logger.name = f"ViolationsAPI[{market_config.id}]"

    def scrape(self, parcel_numbers: List[str] = None, addresses: List[str] = None, **kwargs):
        """
        Main scraping method (required by BaseScraper).

        Args:
            parcel_numbers: List of parcel IDs to query
            addresses: List of addresses to query (fallback)

        Returns:
            Dict or DataFrame of violations
        """
        if not self.api_url:
            self.logger.warning(f"No violations API configured for {self.market.name}")
            return {}

        if parcel_numbers:
            return self.get_violations_by_parcel(parcel_numbers)
        elif addresses:
            return self.get_violations_by_address(addresses)
        else:
            return self.get_all_violations()

    def get_violations_by_parcel(self, parcel_numbers: List[str]) -> Dict[str, List[Dict]]:
        """
        Get code violations for specific parcel numbers.

        Args:
            parcel_numbers: List of parcel IDs to query

        Returns:
            Dict mapping parcel_number -> list of violations
        """
        self.logger.info(f"Querying {self.market.name} violations for {len(parcel_numbers)} parcels...")

        results = {}

        for parcel in parcel_numbers:
            violations = self._query_by_parcel(parcel)
            if violations:
                results[parcel] = violations

        log_success(f"Found violations for {len(results)}/{len(parcel_numbers)} parcels")

        return results

    def get_violations_by_address(self, addresses: List[str]) -> Dict[str, List[Dict]]:
        """
        Get code violations by address (fallback method).

        Args:
            addresses: List of property addresses

        Returns:
            Dict mapping address -> list of violations
        """
        self.logger.info(f"Querying {self.market.name} violations for {len(addresses)} addresses...")

        results = {}

        for address in addresses:
            violations = self._query_by_address(address)
            if violations:
                results[address] = violations

        log_success(f"Found violations for {len(results)}/{len(addresses)} addresses")

        return results

    def get_all_violations(self, max_records: Optional[int] = None) -> pd.DataFrame:
        """
        Download all code enforcement violations.

        Args:
            max_records: Maximum records to retrieve (None = all)

        Returns:
            DataFrame with all violations
        """
        self.logger.info(f"Downloading all {self.market.name} code violations...")

        all_violations = []
        offset = 0

        while True:
            params = {
                'where': '1=1',
                'outFields': '*',
                'f': 'json',
                'resultOffset': offset,
                'resultRecordCount': self.max_records,
                'returnGeometry': 'false'
            }

            response = self._make_request(f"{self.api_url}/query", params=params)

            if not response:
                break

            data = response.json()
            features = data.get('features', [])

            if not features:
                break

            for feature in features:
                violation = self._parse_violation(feature.get('attributes', {}))
                all_violations.append(violation)

            self.logger.info(f"Retrieved {len(all_violations)} violations...")

            offset += self.max_records

            if max_records and len(all_violations) >= max_records:
                all_violations = all_violations[:max_records]
                break

        df = pd.DataFrame(all_violations)
        log_success(f"Downloaded {len(df)} total violations from {self.market.name}")

        return df

    def _query_by_parcel(self, parcel_number: str) -> List[Dict]:
        """Query violations for a specific parcel number"""

        query_url = f"{self.api_url}/query"
        params = {
            'where': f"{self.query_field}='{parcel_number}'",
            'outFields': '*',
            'f': 'json',
            'returnGeometry': 'false'
        }

        response = self._make_request(query_url, params=params)

        if not response:
            return []

        data = response.json()
        features = data.get('features', [])

        violations = []
        for feature in features:
            violation = self._parse_violation(feature.get('attributes', {}))
            violations.append(violation)

        return violations

    def _query_by_address(self, address: str) -> List[Dict]:
        """Query violations for a specific address"""

        # Get address field from mappings
        address_field = self.field_mappings.get('address', 'ADDRESS')

        # Normalize address for better matching
        address_normalized = address.upper().replace(',', '').strip()

        query_url = f"{self.api_url}/query"
        params = {
            'where': f"{address_field} LIKE '%{address_normalized}%'",
            'outFields': '*',
            'f': 'json',
            'returnGeometry': 'false'
        }

        response = self._make_request(query_url, params=params)

        if not response:
            return []

        data = response.json()
        features = data.get('features', [])

        violations = []
        for feature in features:
            violation = self._parse_violation(feature.get('attributes', {}))
            violations.append(violation)

        return violations

    def _parse_violation(self, attrs: Dict) -> Dict:
        """Parse ArcGIS feature attributes to violation dict using field mappings"""

        # Get field names from mappings (with defaults)
        fm = self.field_mappings

        violation_type = attrs.get(fm.get('violation_type', 'TYPE'), '')

        return {
            'case_id': attrs.get(fm.get('case_id', 'CASE_ID')),
            'parcel_number': attrs.get(fm.get('parcel_number', 'PARCEL_ID')),
            'address': attrs.get(fm.get('address', 'ADDRESS')),
            'violation_group': attrs.get(fm.get('violation_group', 'GROUP')),
            'violation_type': violation_type,
            'violation_subtype': attrs.get(fm.get('violation_subtype', 'SUBTYPE')),
            'violation_category': attrs.get(fm.get('violation_category', 'CATEGORY')),
            'status': attrs.get(fm.get('status', 'STATUS')),
            'file_date': self._parse_timestamp(attrs.get(fm.get('file_date', 'FILE_DATE'))),
            'first_inspection_date': self._parse_timestamp(attrs.get(fm.get('first_inspection_date', 'INSP_DATE'))),
            'first_inspection_result': attrs.get(fm.get('first_inspection_result', 'INSP_RESULT')),
            'last_inspection_date': self._parse_timestamp(attrs.get(fm.get('last_inspection_date', 'LAST_INSP'))),
            'last_inspection_result': attrs.get(fm.get('last_inspection_result', 'LAST_RESULT')),
            'severity': self._determine_severity(violation_type),
            'case_url': attrs.get(fm.get('case_url', 'URL')),
            'market_id': self.market.id,
        }

    def _parse_timestamp(self, timestamp: Optional[int]) -> Optional[str]:
        """Convert ArcGIS timestamp (milliseconds since epoch) to date string"""
        if not timestamp:
            return None

        try:
            dt = datetime.fromtimestamp(timestamp / 1000)
            return dt.strftime('%Y-%m-%d')
        except:
            return None

    def _determine_severity(self, violation_type: str) -> str:
        """
        Classify violation severity based on violation type.

        Returns: 'critical', 'major', or 'minor'
        """
        if not violation_type:
            return 'minor'

        violation_type_lower = violation_type.lower()

        critical_keywords = [
            'housing', 'safety', 'structural', 'emergency',
            'health', 'nuisance', 'vacant', 'blight', 'fire',
            'demolition', 'condemnation'
        ]

        major_keywords = [
            'zoning', 'property maintenance', 'building',
            'electrical', 'plumbing', 'sanitation', 'mechanical',
            'occupancy', 'environmental'
        ]

        if any(kw in violation_type_lower for kw in critical_keywords):
            return 'critical'
        elif any(kw in violation_type_lower for kw in major_keywords):
            return 'major'
        else:
            return 'minor'

    def aggregate_violations_by_parcel(self, violations_dict: Dict[str, List[Dict]]) -> pd.DataFrame:
        """
        Aggregate violations by parcel for scoring.

        Args:
            violations_dict: Output from get_violations_by_parcel()

        Returns:
            DataFrame with aggregated violation stats per parcel
        """
        aggregated = []

        for parcel_number, violations in violations_dict.items():
            if not violations:
                continue

            # Count by severity
            critical_count = sum(1 for v in violations if v['severity'] == 'critical')
            major_count = sum(1 for v in violations if v['severity'] == 'major')
            minor_count = sum(1 for v in violations if v['severity'] == 'minor')

            # Count open vs closed
            open_count = sum(1 for v in violations if v['status'] and 'open' in str(v['status']).lower())
            closed_count = sum(1 for v in violations if v['status'] and 'closed' in str(v['status']).lower())

            # Get dates
            dates = [v['file_date'] for v in violations if v['file_date']]
            most_recent = max(dates) if dates else None
            oldest = min(dates) if dates else None

            aggregated.append({
                'parcel_number': parcel_number,
                'total_violations': len(violations),
                'critical_violations': critical_count,
                'major_violations': major_count,
                'minor_violations': minor_count,
                'open_violations': open_count,
                'closed_violations': closed_count,
                'most_recent_violation_date': most_recent,
                'oldest_violation_date': oldest,
                'market_id': self.market.id,
            })

        return pd.DataFrame(aggregated)


# ========================================
# CLI Entry Point
# ========================================

if __name__ == '__main__':
    """Test the generic API with Columbus"""
    from shared.config.market_loader import load_market

    # Load Columbus market config
    market = load_market('columbus_oh')

    # Create API client
    api = GenericViolationsAPI(market)

    # Test with sample parcels
    print(f"\nTesting {market.name} violations API")
    print(f"API URL: {api.api_url}")
    print(f"Query field: {api.query_field}")

    # Download sample violations
    print("\nDownloading sample violations...")
    df = api.get_all_violations(max_records=100)
    print(f"Downloaded {len(df)} violations")

    if not df.empty:
        print(f"\nSeverity breakdown:")
        print(df['severity'].value_counts())

    print(f"\nAPI Stats: {api.get_stats()}")
