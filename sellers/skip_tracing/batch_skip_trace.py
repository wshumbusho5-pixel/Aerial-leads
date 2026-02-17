"""
Lifeline Home Buyers - Skip Tracing Integration

Integrates with BatchSkipTracing.com API to enrich property data with:
- Phone numbers
- Email addresses
- Owner age
- Additional contact info
"""

import requests
import pandas as pd
from typing import List, Dict, Optional
import time

from shared.config.settings import BATCH_SKIP_TRACE_API_KEY, BATCH_SKIP_TRACE_URL, RAW_DATA_DIR
from shared.config.logging_config import log_success, log_failure, get_logger


class BatchSkipTracer:
    """
    Integration with BatchSkipTracing.com API

    Enriches property owner data with contact information
    """

    def __init__(self, api_key: str = BATCH_SKIP_TRACE_API_KEY):
        self.logger = get_logger(self.__class__.__name__)
        self.api_key = api_key
        self.api_url = BATCH_SKIP_TRACE_URL
        self.session = requests.Session()

        if not self.api_key:
            self.logger.warning("No BatchSkipTracing API key provided - using mock mode")
            self.mock_mode = True
        else:
            self.mock_mode = False

    def skip_trace_batch(self, properties: List[Dict]) -> List[Dict]:
        """
        Skip trace a batch of properties

        Args:
            properties: List of property dictionaries with at least 'address' and 'owner_name'

        Returns:
            List of enriched properties with contact info
        """
        self.logger.info(f"🔍 Skip tracing {len(properties)} properties...")

        if self.mock_mode:
            self.logger.warning("Running in MOCK mode - using sample data")
            return self._mock_skip_trace(properties)

        enriched = []

        for i, prop in enumerate(properties, 1):
            self.logger.info(f"Skip tracing {i}/{len(properties)}: {prop.get('address', 'Unknown')}")

            # Skip trace this property
            contact_info = self._skip_trace_single(prop)

            # Add contact info to property
            enriched_prop = {**prop, **contact_info}
            enriched.append(enriched_prop)

            # Rate limiting
            time.sleep(0.5)

        log_success(f"Skip traced {len(enriched)} properties")
        return enriched

    def _skip_trace_single(self, property_data: Dict) -> Dict:
        """
        Skip trace a single property

        Args:
            property_data: Property dictionary

        Returns:
            Contact information dictionary
        """
        # Prepare request payload
        payload = {
            'name': property_data.get('owner_name', ''),
            'address': property_data.get('address', ''),
            'city': self._extract_city(property_data.get('address', '')),
            'state': self._extract_state(property_data.get('address', '')),
            'zip': self._extract_zip(property_data.get('address', ''))
        }

        # Make API request
        try:
            response = self.session.post(
                f"{self.api_url}/skip-trace",
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json'
                },
                json=payload,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                return self._parse_skip_trace_response(data)
            else:
                self.logger.error(f"Skip trace API error: {response.status_code}")
                return self._empty_contact_info()

        except Exception as e:
            self.logger.error(f"Skip trace error: {e}")
            return self._empty_contact_info()

    def _parse_skip_trace_response(self, data: Dict) -> Dict:
        """
        Parse skip trace API response

        Args:
            data: API response data

        Returns:
            Cleaned contact information
        """
        return {
            'phone': data.get('phone', ''),
            'phone_2': data.get('phone_2', ''),
            'email': data.get('email', ''),
            'email_2': data.get('email_2', ''),
            'owner_age': data.get('age', None),
            'owner_dob': data.get('dob', ''),
            'relatives': data.get('relatives', []),
            'previous_addresses': data.get('previous_addresses', []),
            'skip_traced': True,
            'skip_trace_date': pd.Timestamp.now().strftime('%Y-%m-%d')
        }

    def _empty_contact_info(self) -> Dict:
        """Return empty contact info structure"""
        return {
            'phone': '',
            'phone_2': '',
            'email': '',
            'email_2': '',
            'owner_age': None,
            'owner_dob': '',
            'relatives': [],
            'previous_addresses': [],
            'skip_traced': False,
            'skip_trace_date': ''
        }

    def _extract_city(self, address: str) -> str:
        """Extract city from address string"""
        try:
            parts = address.split(',')
            if len(parts) >= 2:
                return parts[1].strip()
        except:
            pass
        return ''

    def _extract_state(self, address: str) -> str:
        """Extract state from address string"""
        try:
            parts = address.split(',')
            if len(parts) >= 3:
                state_zip = parts[2].strip().split()
                return state_zip[0] if state_zip else ''
        except:
            pass
        return ''

    def _extract_zip(self, address: str) -> str:
        """Extract ZIP code from address string"""
        try:
            parts = address.split(',')
            if len(parts) >= 3:
                state_zip = parts[2].strip().split()
                return state_zip[1] if len(state_zip) > 1 else ''
        except:
            pass
        return ''

    def _mock_skip_trace(self, properties: List[Dict]) -> List[Dict]:
        """
        Mock skip trace for testing (when no API key)

        Generates realistic-looking fake data
        """
        import random

        enriched = []

        for prop in properties:
            # Generate mock contact info
            mock_phone = f"614-555-{random.randint(1000, 9999)}"
            mock_email_base = prop.get('owner_name', 'owner').replace(' ', '.').lower()
            mock_email = f"{mock_email_base}@email.com"

            contact_info = {
                'phone': mock_phone,
                'phone_2': '',
                'email': mock_email,
                'email_2': '',
                'owner_age': random.choice([None, random.randint(45, 80)]),
                'owner_dob': '',
                'relatives': [],
                'previous_addresses': [],
                'skip_traced': True,
                'skip_trace_date': pd.Timestamp.now().strftime('%Y-%m-%d'),
                'note': 'MOCK DATA - Get real API key for production'
            }

            enriched_prop = {**prop, **contact_info}
            enriched.append(enriched_prop)

        return enriched

    def export_skip_traced(self, properties: List[Dict], filename: str = 'skip_traced.csv') -> str:
        """
        Export skip traced properties to CSV

        Args:
            properties: Enriched properties
            filename: Output filename

        Returns:
            Path to exported file
        """
        if not properties:
            log_failure("No properties to export")
            return ''

        df = pd.DataFrame(properties)
        output_path = RAW_DATA_DIR / filename
        df.to_csv(output_path, index=False)

        log_success(f"Exported {len(properties)} skip traced properties to {output_path}")
        return str(output_path)


# ========================================
# Free Skip Tracing (Manual Backup)
# ========================================

class FreeSkipTracer:
    """
    Free skip tracing using public sources

    Not as comprehensive but works without API costs
    """

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)

    def skip_trace_batch(self, properties: List[Dict]) -> List[Dict]:
        """
        Attempt free skip tracing

        Sources:
        - TruePeopleSearch.com
        - FastPeopleSearch.com
        - WhitePages.com
        """
        self.logger.info("Using FREE skip tracing (limited results)")

        # For now, just add empty contact fields
        # In production, you'd scrape the free sites
        enriched = []

        for prop in properties:
            enriched_prop = {
                **prop,
                'phone': '',
                'email': '',
                'owner_age': None,
                'skip_traced': False,
                'skip_trace_method': 'manual_required'
            }
            enriched.append(enriched_prop)

        return enriched


# Example usage
if __name__ == '__main__':
    # Sample property data
    sample_properties = [
        {
            'address': '123 Main St, Columbus, OH 43215',
            'owner_name': 'John Smith',
            'assessed_value': 85000,
            'taxes_owed': 12500
        }
    ]

    # Skip trace
    tracer = BatchSkipTracer()
    enriched = tracer.skip_trace_batch(sample_properties)

    # Show results
    for prop in enriched:
        print(f"\n{prop['address']}")
        print(f"  Owner: {prop['owner_name']}")
        print(f"  Phone: {prop.get('phone', 'N/A')}")
        print(f"  Email: {prop.get('email', 'N/A')}")
        print(f"  Age: {prop.get('owner_age', 'N/A')}")
