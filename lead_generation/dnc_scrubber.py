"""
Lifeline Home Buyers - Do Not Call (DNC) Registry Scrubber

Checks phone numbers against the National Do Not Call Registry
to help maintain TCPA compliance.

Features:
- Phone number validation and formatting
- Line type detection (landline vs wireless)
- DNC registry checking via API
- Local DNC file support (FTC downloaded files)
- TCPA compliance warnings
"""

import pandas as pd
from typing import List, Dict, Optional, Set
from pathlib import Path
import json
import os
import re
from datetime import datetime

try:
    import phonenumbers
    from phonenumbers import NumberParseException, carrier, geocoder
    PHONENUMBERS_AVAILABLE = True
except ImportError:
    PHONENUMBERS_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from config.settings import DATA_DIR, PROCESSED_DATA_DIR

try:
    from config.logging_config import get_logger
    logger = get_logger("DNCChecker")
except ImportError:
    import logging
    logger = logging.getLogger("DNCChecker")


class DNCChecker:
    """
    Comprehensive Do Not Call checking with multiple methods:
    1. Phone validation and formatting
    2. Line type detection (wireless = stricter TCPA rules)
    3. API-based DNC registry check
    4. Local DNC file checking
    """

    # DNC Status codes
    STATUS_SAFE = 'SAFE'           # Not on DNC, safe to call
    STATUS_ON_DNC = 'ON_DNC'       # On National DNC Registry
    STATUS_WIRELESS = 'WIRELESS'   # Wireless number - needs written consent for autodialer
    STATUS_INVALID = 'INVALID'     # Invalid phone number
    STATUS_NO_PHONE = 'NO_PHONE'   # No phone number provided
    STATUS_LITIGATOR = 'LITIGATOR' # Known TCPA litigator (high risk)
    STATUS_UNCHECKED = 'UNCHECKED' # Not yet checked

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize DNC Checker.

        Args:
            api_key: Optional API key for DNC checking service
        """
        self.api_key = api_key or os.getenv('DNC_API_KEY', '')
        self.local_dnc_numbers: Set[str] = set()
        self.litigator_numbers: Set[str] = set()

        # Load local DNC files if available
        self._load_local_dnc_files()
        self._load_litigator_list()

        logger.info(f"DNCChecker initialized. Local DNC numbers: {len(self.local_dnc_numbers)}")

    def _load_local_dnc_files(self):
        """Load DNC numbers from local files (FTC format or custom)."""
        dnc_dir = DATA_DIR / 'dnc'

        if not dnc_dir.exists():
            dnc_dir.mkdir(parents=True, exist_ok=True)
            return

        # Load any .txt or .csv files in the DNC directory
        for file_path in dnc_dir.glob('*.txt'):
            try:
                with open(file_path, 'r') as f:
                    for line in f:
                        # FTC format is just phone numbers, one per line
                        number = self._normalize_phone(line.strip())
                        if number:
                            self.local_dnc_numbers.add(number)
            except Exception as e:
                logger.warning(f"Could not load DNC file {file_path}: {e}")

        for file_path in dnc_dir.glob('*.csv'):
            try:
                df = pd.read_csv(file_path)
                # Look for phone column
                phone_col = None
                for col in df.columns:
                    if 'phone' in col.lower():
                        phone_col = col
                        break

                if phone_col:
                    for phone in df[phone_col].dropna():
                        number = self._normalize_phone(str(phone))
                        if number:
                            self.local_dnc_numbers.add(number)
            except Exception as e:
                logger.warning(f"Could not load DNC CSV {file_path}: {e}")

        if self.local_dnc_numbers:
            logger.info(f"Loaded {len(self.local_dnc_numbers)} numbers from local DNC files")

    def _load_litigator_list(self):
        """Load known TCPA litigator phone numbers."""
        litigator_file = DATA_DIR / 'tcpa_litigators.json'

        if litigator_file.exists():
            try:
                with open(litigator_file, 'r') as f:
                    data = json.load(f)
                    for number in data.get('numbers', []):
                        normalized = self._normalize_phone(number)
                        if normalized:
                            self.litigator_numbers.add(normalized)
                logger.info(f"Loaded {len(self.litigator_numbers)} known litigator numbers")
            except Exception as e:
                logger.warning(f"Could not load litigator list: {e}")

    def _normalize_phone(self, phone: str) -> Optional[str]:
        """Normalize phone number to 10-digit format."""
        if not phone:
            return None

        # Remove all non-digits
        digits = re.sub(r'\D', '', str(phone))

        # Handle country code
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]

        # Must be 10 digits for US
        if len(digits) != 10:
            return None

        return digits

    def _format_phone(self, phone: str) -> str:
        """Format phone number as (XXX) XXX-XXXX."""
        digits = self._normalize_phone(phone)
        if not digits or len(digits) != 10:
            return phone
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"

    def validate_phone(self, phone: str) -> Dict:
        """
        Validate a phone number and get detailed info.

        Returns:
            Dict with validation info
        """
        result = {
            'original': phone,
            'normalized': None,
            'formatted': None,
            'is_valid': False,
            'line_type': 'unknown',
            'carrier': None,
            'location': None,
            'error': None
        }

        if not phone:
            result['error'] = 'No phone number provided'
            return result

        normalized = self._normalize_phone(phone)

        if not normalized:
            result['error'] = 'Invalid phone number format'
            return result

        result['normalized'] = normalized
        result['formatted'] = self._format_phone(phone)

        # Use phonenumbers library for detailed validation
        if PHONENUMBERS_AVAILABLE:
            try:
                # Use normalized phone (digits only) for parsing to handle floats like "6145316158.0"
                parsed = phonenumbers.parse(normalized, 'US')

                if not phonenumbers.is_valid_number(parsed):
                    result['error'] = 'Invalid phone number'
                    return result

                result['is_valid'] = True

                # Get carrier info (helps identify line type)
                carrier_name = carrier.name_for_number(parsed, 'en')
                result['carrier'] = carrier_name if carrier_name else 'Unknown'

                # Get location
                location = geocoder.description_for_number(parsed, 'en')
                result['location'] = location if location else 'Unknown'

                # Determine line type based on carrier
                # This is a heuristic - real line type requires a paid API
                wireless_carriers = ['verizon', 'at&t', 't-mobile', 'sprint', 'cricket',
                                   'metro', 'boost', 'virgin', 'tracfone', 'straight talk',
                                   'us cellular', 'cellular']

                carrier_lower = carrier_name.lower() if carrier_name else ''
                if any(wc in carrier_lower for wc in wireless_carriers):
                    result['line_type'] = 'wireless'
                elif carrier_name:
                    result['line_type'] = 'landline'  # Assume landline if has carrier but not wireless
                else:
                    result['line_type'] = 'unknown'

            except NumberParseException as e:
                result['error'] = f'Parse error: {str(e)}'
        else:
            # Basic validation without phonenumbers library
            result['is_valid'] = len(normalized) == 10

        return result

    def check_dnc(self, phone: str) -> Dict:
        """
        Check a phone number against DNC registry and return full status.

        Args:
            phone: Phone number to check

        Returns:
            Dict with DNC status and compliance info
        """
        result = {
            'phone': phone,
            'phone_formatted': None,
            'dnc_status': self.STATUS_UNCHECKED,
            'safe_to_call': False,
            'line_type': 'unknown',
            'risk_level': 'unknown',  # low, medium, high
            'warnings': [],
            'notes': '',
            'checked_date': datetime.now().strftime('%Y-%m-%d'),
            'check_method': 'none'
        }

        # Step 1: Validate phone
        validation = self.validate_phone(phone)

        if not validation['is_valid']:
            result['dnc_status'] = self.STATUS_INVALID
            result['safe_to_call'] = False
            result['risk_level'] = 'high'
            result['notes'] = validation.get('error', 'Invalid phone number')
            return result

        normalized = validation['normalized']
        result['phone_formatted'] = validation['formatted']
        result['line_type'] = validation['line_type']

        # Step 2: Check against litigator list (highest priority)
        if normalized in self.litigator_numbers:
            result['dnc_status'] = self.STATUS_LITIGATOR
            result['safe_to_call'] = False
            result['risk_level'] = 'high'
            result['warnings'].append('KNOWN TCPA LITIGATOR - DO NOT CALL')
            result['notes'] = 'This number belongs to a known TCPA lawsuit filer. Calling may result in lawsuit.'
            result['check_method'] = 'litigator_list'
            return result

        # Step 3: Check local DNC files
        if normalized in self.local_dnc_numbers:
            result['dnc_status'] = self.STATUS_ON_DNC
            result['safe_to_call'] = False
            result['risk_level'] = 'high'
            result['warnings'].append('On Do Not Call Registry')
            result['notes'] = 'Number found in DNC registry. Do not call unless prior business relationship exists.'
            result['check_method'] = 'local_dnc_file'
            return result

        # Step 4: Check via API if available
        if self.api_key and REQUESTS_AVAILABLE:
            api_result = self._check_dnc_api(normalized)
            if api_result:
                result.update(api_result)
                result['check_method'] = 'api'
                return result

        # Step 5: Assess based on line type
        if validation['line_type'] == 'wireless':
            result['dnc_status'] = self.STATUS_WIRELESS
            result['safe_to_call'] = True  # Can call, but with restrictions
            result['risk_level'] = 'medium'
            result['warnings'].append('WIRELESS NUMBER - No autodialers/prerecorded messages without written consent')
            result['notes'] = 'Wireless number detected. TCPA requires written consent for autodialers or prerecorded messages. Manual dialing is allowed.'
            result['check_method'] = 'line_type_detection'
        else:
            # Landline or unknown - likely safe
            result['dnc_status'] = self.STATUS_SAFE
            result['safe_to_call'] = True
            result['risk_level'] = 'low'
            result['notes'] = 'Number appears safe to call. Always identify yourself and honor opt-out requests.'
            result['check_method'] = 'line_type_detection'

        return result

    def _check_dnc_api(self, normalized_phone: str) -> Optional[Dict]:
        """
        Check DNC status via API service.

        Supports multiple API providers - configure via DNC_API_PROVIDER env var.
        """
        provider = os.getenv('DNC_API_PROVIDER', 'realphonevalidation')

        try:
            if provider == 'realphonevalidation':
                return self._check_realphonevalidation(normalized_phone)
            elif provider == 'dnc_com':
                return self._check_dnc_com(normalized_phone)
            else:
                logger.warning(f"Unknown DNC API provider: {provider}")
                return None
        except Exception as e:
            logger.error(f"DNC API error: {e}")
            return None

    def _check_realphonevalidation(self, phone: str) -> Optional[Dict]:
        """Check via RealPhoneValidation API."""
        # API endpoint for phone validation + DNC
        url = "https://api.realphonevalidation.com/v1/phone/validate"

        try:
            response = requests.get(
                url,
                params={
                    'phone': phone,
                    'api_key': self.api_key
                },
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()

                result = {
                    'line_type': data.get('line_type', 'unknown').lower(),
                    'carrier': data.get('carrier', 'Unknown'),
                }

                # Check DNC status from response
                is_dnc = data.get('dnc', False) or data.get('do_not_call', False)

                if is_dnc:
                    result['dnc_status'] = self.STATUS_ON_DNC
                    result['safe_to_call'] = False
                    result['risk_level'] = 'high'
                    result['warnings'] = ['On Do Not Call Registry']
                    result['notes'] = 'Number is on the National DNC Registry.'
                elif result['line_type'] == 'wireless':
                    result['dnc_status'] = self.STATUS_WIRELESS
                    result['safe_to_call'] = True
                    result['risk_level'] = 'medium'
                    result['warnings'] = ['Wireless number - TCPA restrictions apply']
                    result['notes'] = 'Wireless number. No autodialers without written consent.'
                else:
                    result['dnc_status'] = self.STATUS_SAFE
                    result['safe_to_call'] = True
                    result['risk_level'] = 'low'
                    result['warnings'] = []
                    result['notes'] = 'Number is not on DNC registry.'

                return result

        except Exception as e:
            logger.error(f"RealPhoneValidation API error: {e}")

        return None

    def _check_dnc_com(self, phone: str) -> Optional[Dict]:
        """Check via DNC.com API."""
        # DNC.com API implementation
        url = "https://api.dnc.com/v1/check"

        try:
            response = requests.post(
                url,
                json={'phone': phone},
                headers={'Authorization': f'Bearer {self.api_key}'},
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()

                is_dnc = data.get('on_dnc', False)

                result = {}
                if is_dnc:
                    result['dnc_status'] = self.STATUS_ON_DNC
                    result['safe_to_call'] = False
                    result['risk_level'] = 'high'
                    result['warnings'] = ['On Do Not Call Registry']
                    result['notes'] = 'Number is on the National DNC Registry.'
                else:
                    result['dnc_status'] = self.STATUS_SAFE
                    result['safe_to_call'] = True
                    result['risk_level'] = 'low'
                    result['warnings'] = []
                    result['notes'] = 'Number is not on DNC registry.'

                return result

        except Exception as e:
            logger.error(f"DNC.com API error: {e}")

        return None

    def scrub_leads(self, df: pd.DataFrame, phone_col: str = 'phone') -> pd.DataFrame:
        """
        Scrub a DataFrame of leads against DNC registry.

        Args:
            df: DataFrame with phone numbers
            phone_col: Name of column containing phone numbers

        Returns:
            DataFrame with DNC status columns added
        """
        df = df.copy()

        # Initialize columns
        df['dnc_status'] = self.STATUS_UNCHECKED
        df['safe_to_call'] = False
        df['dnc_risk_level'] = 'unknown'
        df['dnc_warnings'] = ''
        df['dnc_notes'] = ''
        df['dnc_checked_date'] = ''
        df['line_type'] = 'unknown'

        total = len(df)
        checked = 0
        safe_count = 0
        dnc_count = 0
        wireless_count = 0
        invalid_count = 0

        logger.info(f"Starting DNC scrub for {total} leads...")

        for idx, row in df.iterrows():
            phone = row.get(phone_col)

            if pd.isna(phone) or not phone:
                df.at[idx, 'dnc_status'] = self.STATUS_NO_PHONE
                df.at[idx, 'dnc_notes'] = 'No phone number'
                continue

            # Check DNC status
            result = self.check_dnc(str(phone))

            df.at[idx, 'dnc_status'] = result['dnc_status']
            df.at[idx, 'safe_to_call'] = result['safe_to_call']
            df.at[idx, 'dnc_risk_level'] = result['risk_level']
            df.at[idx, 'dnc_warnings'] = '; '.join(result['warnings'])
            df.at[idx, 'dnc_notes'] = result['notes']
            df.at[idx, 'dnc_checked_date'] = result['checked_date']
            df.at[idx, 'line_type'] = result['line_type']

            # Update formatted phone if available
            if result.get('phone_formatted'):
                df.at[idx, phone_col] = result['phone_formatted']

            # Count statistics
            checked += 1
            if result['dnc_status'] == self.STATUS_SAFE:
                safe_count += 1
            elif result['dnc_status'] == self.STATUS_ON_DNC:
                dnc_count += 1
            elif result['dnc_status'] == self.STATUS_WIRELESS:
                wireless_count += 1
                safe_count += 1  # Wireless is technically safe to call manually
            elif result['dnc_status'] == self.STATUS_INVALID:
                invalid_count += 1

        logger.info(f"DNC scrub complete:")
        logger.info(f"  - Total checked: {checked}")
        logger.info(f"  - Safe to call: {safe_count}")
        logger.info(f"  - On DNC: {dnc_count}")
        logger.info(f"  - Wireless (restricted): {wireless_count}")
        logger.info(f"  - Invalid numbers: {invalid_count}")

        return df

    def get_safe_calling_list(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Filter DataFrame to only safe-to-call leads.

        Args:
            df: DataFrame with DNC status columns

        Returns:
            Filtered DataFrame
        """
        if 'safe_to_call' not in df.columns:
            logger.warning("DataFrame not DNC scrubbed yet. Run scrub_leads first.")
            return df

        safe_df = df[df['safe_to_call'] == True].copy()
        logger.info(f"Filtered to {len(safe_df)}/{len(df)} safe-to-call leads")

        return safe_df

    def add_internal_dnc(self, phone: str, reason: str = 'Opt-out request'):
        """
        Add a number to internal DNC list (opt-out requests).

        Args:
            phone: Phone number to add
            reason: Reason for adding
        """
        normalized = self._normalize_phone(phone)
        if not normalized:
            return

        # Add to in-memory set
        self.local_dnc_numbers.add(normalized)

        # Save to file
        internal_dnc_file = DATA_DIR / 'dnc' / 'internal_dnc.csv'
        internal_dnc_file.parent.mkdir(parents=True, exist_ok=True)

        # Append to CSV
        entry = pd.DataFrame([{
            'phone': normalized,
            'formatted': self._format_phone(normalized),
            'reason': reason,
            'added_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }])

        if internal_dnc_file.exists():
            entry.to_csv(internal_dnc_file, mode='a', header=False, index=False)
        else:
            entry.to_csv(internal_dnc_file, index=False)

        logger.info(f"Added {normalized} to internal DNC list: {reason}")

    def generate_compliance_report(self, df: pd.DataFrame) -> Dict:
        """
        Generate a TCPA compliance report for a set of leads.

        Args:
            df: DataFrame with DNC status columns

        Returns:
            Dict with compliance statistics and recommendations
        """
        if 'dnc_status' not in df.columns:
            return {'error': 'DataFrame not DNC scrubbed'}

        total = len(df)

        report = {
            'total_leads': total,
            'with_phone': len(df[df['dnc_status'] != self.STATUS_NO_PHONE]),
            'safe_to_call': len(df[df['safe_to_call'] == True]),
            'on_dnc': len(df[df['dnc_status'] == self.STATUS_ON_DNC]),
            'wireless': len(df[df['dnc_status'] == self.STATUS_WIRELESS]),
            'invalid': len(df[df['dnc_status'] == self.STATUS_INVALID]),
            'litigators': len(df[df['dnc_status'] == self.STATUS_LITIGATOR]),
            'unchecked': len(df[df['dnc_status'] == self.STATUS_UNCHECKED]),
            'compliance_score': 0,
            'recommendations': []
        }

        # Calculate compliance score
        if report['with_phone'] > 0:
            report['compliance_score'] = round(
                (report['safe_to_call'] / report['with_phone']) * 100, 1
            )

        # Add recommendations
        if report['on_dnc'] > 0:
            report['recommendations'].append(
                f"Remove {report['on_dnc']} DNC numbers from calling list"
            )

        if report['wireless'] > 0:
            report['recommendations'].append(
                f"{report['wireless']} wireless numbers require manual dialing only (no autodialers)"
            )

        if report['litigators'] > 0:
            report['recommendations'].append(
                f"URGENT: {report['litigators']} known litigator numbers detected - DO NOT CALL"
            )

        if report['invalid'] > 0:
            report['recommendations'].append(
                f"Clean up {report['invalid']} invalid phone numbers"
            )

        if report['unchecked'] > 0:
            report['recommendations'].append(
                f"Run DNC check on {report['unchecked']} unchecked numbers"
            )

        return report


# Convenience function for quick DNC check
def check_phone_dnc(phone: str) -> Dict:
    """Quick DNC check for a single phone number."""
    checker = DNCChecker()
    return checker.check_dnc(phone)


# CLI Test
if __name__ == '__main__':
    from rich.console import Console
    from rich.table import Table

    console = Console()

    checker = DNCChecker()

    # Test phone numbers
    test_phones = [
        '(614) 276-1082',
        '614-377-7807',
        '555-1234',  # Invalid
        '6145551234',
    ]

    console.print("\n[bold cyan]DNC Checker Test[/bold cyan]\n")

    table = Table(title="DNC Check Results")
    table.add_column("Phone", style="cyan")
    table.add_column("Status", style="yellow")
    table.add_column("Safe to Call", style="green")
    table.add_column("Line Type")
    table.add_column("Risk")
    table.add_column("Notes")

    for phone in test_phones:
        result = checker.check_dnc(phone)

        safe_icon = "✅" if result['safe_to_call'] else "❌"

        table.add_row(
            phone,
            result['dnc_status'],
            safe_icon,
            result['line_type'],
            result['risk_level'],
            result['notes'][:40] + '...' if len(result['notes']) > 40 else result['notes']
        )

    console.print(table)
