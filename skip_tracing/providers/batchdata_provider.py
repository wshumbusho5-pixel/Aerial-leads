"""
BatchData Skip Trace Provider

Real skip tracing using BatchData.com API (formerly BatchSkipTracing).
Requires API key from https://batchdata.com

Pricing: ~$0.15-0.25 per record
"""

import requests
from typing import List, Dict, Optional
from datetime import datetime

from .base import SkipTraceProvider, SkipTraceResult

try:
    from config.logging_config import get_logger
    logger = get_logger("BatchDataProvider")
except ImportError:
    import logging
    logger = logging.getLogger("BatchDataProvider")


class BatchDataProvider(SkipTraceProvider):
    """
    BatchData.com skip trace provider.

    API Documentation: https://developer.batchdata.com

    Returns real phone numbers and emails for property owners.
    """

    name = "batchdata"
    requires_api_key = True
    cost_per_lookup = 0.20  # Approximate cost

    # API endpoints
    BASE_URL = "https://api.batchdata.com/api/v1"
    SKIP_TRACE_ENDPOINT = "/property/skip-trace"

    def __init__(self, api_key: str):
        """
        Initialize BatchData provider.

        Args:
            api_key: Your BatchData API key
        """
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        })

    def _normalize_name(self, name: str) -> str:
        """
        Convert name from "LASTNAME FIRSTNAME" or "LASTNAME, FIRSTNAME" to "FIRSTNAME LASTNAME" format.

        BatchData works better with "FIRSTNAME LASTNAME" format.
        """
        if not name:
            return name

        name = name.strip().upper()

        # Remove common suffixes that confuse matching
        suffixes = [' JR', ' SR', ' II', ' III', ' IV', ' TTEE', ' TRUSTEE', ' ET AL', ' ETAL']
        for suffix in suffixes:
            if name.endswith(suffix):
                name = name[:-len(suffix)].strip()

        # Check if name is in "LASTNAME, FIRSTNAME" format
        if ',' in name:
            parts = name.split(',', 1)
            if len(parts) == 2:
                last_name = parts[0].strip()
                first_name = parts[1].strip().split()[0] if parts[1].strip() else ''
                return f"{first_name} {last_name}".strip()

        # Handle "LASTNAME FIRSTNAME MIDDLE" format (no comma)
        # Assume first word is last name, rest is first name
        parts = name.split()
        if len(parts) >= 2:
            last_name = parts[0]
            first_name = parts[1]  # Take just the first name, ignore middle
            return f"{first_name} {last_name}".strip()

        return name

    def lookup(self, owner_name: str, address: str, **kwargs) -> SkipTraceResult:
        """
        Perform a skip trace lookup for a single property.

        Args:
            owner_name: Property owner's name
            address: Property address
            **kwargs: Additional fields (city, state, zip)

        Returns:
            SkipTraceResult with contact information
        """
        city = kwargs.get('city', '')
        state = kwargs.get('state', 'OH')
        zip_code = kwargs.get('zip_code', '')

        # Normalize name from "LASTNAME, FIRSTNAME" to "FIRSTNAME LASTNAME"
        normalized_name = self._normalize_name(owner_name)
        logger.debug(f"Name normalized: '{owner_name}' -> '{normalized_name}'")

        # Parse address if it contains city/state/zip
        if ',' in address:
            parts = address.split(',')
            street = parts[0].strip()
            if len(parts) > 1 and not city:
                city = parts[1].strip()
        else:
            street = address

        # Build request payload
        payload = {
            "requests": [
                {
                    "propertyAddress": {
                        "street": street,
                        "city": city,
                        "state": state,
                        "zip": str(zip_code)[:5] if zip_code else ""
                    },
                    "ownerName": normalized_name
                }
            ]
        }

        try:
            response = self.session.post(
                f"{self.BASE_URL}{self.SKIP_TRACE_ENDPOINT}",
                json=payload,
                timeout=30
            )

            if response.status_code == 401:
                logger.error("BatchData API: Invalid API key")
                return SkipTraceResult(
                    owner_name=owner_name,
                    address=address,
                    success=False,
                    provider=self.name,
                    error_message="Invalid API key"
                )

            if response.status_code == 402:
                logger.error("BatchData API: Insufficient credits")
                return SkipTraceResult(
                    owner_name=owner_name,
                    address=address,
                    success=False,
                    provider=self.name,
                    error_message="Insufficient credits - add funds to your account"
                )

            response.raise_for_status()
            data = response.json()

            # Parse response
            return self._parse_response(owner_name, address, data)

        except requests.exceptions.RequestException as e:
            logger.error(f"BatchData API error: {e}")
            return SkipTraceResult(
                owner_name=owner_name,
                address=address,
                success=False,
                provider=self.name,
                error_message=str(e)
            )

    def _parse_response(self, owner_name: str, address: str, data: dict) -> SkipTraceResult:
        """Parse BatchData API response into SkipTraceResult."""

        # BatchData returns results in results.persons array
        results_data = data.get('results', {})
        persons = results_data.get('persons', [])

        if not persons:
            return SkipTraceResult(
                owner_name=owner_name,
                address=address,
                success=False,
                provider=self.name,
                error_message="No results found"
            )

        person = persons[0]

        # Check if matched
        meta = person.get('meta', {})
        if not meta.get('matched', False):
            return SkipTraceResult(
                owner_name=owner_name,
                address=address,
                success=False,
                provider=self.name,
                error_message="No match found"
            )

        # Extract phone numbers from ALL possible fields
        phones = []
        seen_phones = set()  # Avoid duplicates

        # Check multiple possible phone fields in BatchData response
        phone_fields = ['phoneNumbers', 'phones', 'phone', 'mobilePhones', 'landlinePhones']
        for field in phone_fields:
            phone_data = person.get(field, [])
            if isinstance(phone_data, str):
                phone_data = [phone_data]
            elif isinstance(phone_data, dict):
                phone_data = [phone_data]

            for phone in phone_data:
                number = None
                if isinstance(phone, dict):
                    number = phone.get('number') or phone.get('phoneNumber') or phone.get('phone')
                elif isinstance(phone, str):
                    number = phone

                if number:
                    formatted = self._format_phone(number)
                    digits = ''.join(c for c in formatted if c.isdigit())
                    if digits and digits not in seen_phones and len(digits) >= 10:
                        seen_phones.add(digits)
                        phones.append(formatted)

        # Also check for individual phone fields
        for single_field in ['mobilePhone', 'cellPhone', 'landlinePhone', 'homePhone', 'workPhone']:
            single_phone = person.get(single_field)
            if single_phone:
                if isinstance(single_phone, dict):
                    single_phone = single_phone.get('number') or single_phone.get('phone')
                if single_phone:
                    formatted = self._format_phone(str(single_phone))
                    digits = ''.join(c for c in formatted if c.isdigit())
                    if digits and digits not in seen_phones and len(digits) >= 10:
                        seen_phones.add(digits)
                        phones.append(formatted)

        # Extract emails
        emails = []
        email_data = person.get('emails', [])
        for email in email_data:
            if isinstance(email, dict):
                addr = email.get('address') or email.get('email')
                if addr:
                    emails.append(addr.lower())
            elif isinstance(email, str):
                emails.append(email.lower())

        # Extract name from response
        name_data = person.get('name', {})
        found_name = name_data.get('full', owner_name)

        # Extract relatives/associates
        relatives = []
        relative_data = person.get('associates', []) or person.get('relatives', [])
        for rel in relative_data:
            if isinstance(rel, dict):
                name = rel.get('name') or rel.get('fullName') or rel.get('full')
                if name:
                    relatives.append(name)
            elif isinstance(rel, str):
                relatives.append(rel)

        # Calculate confidence based on data quality
        confidence = 0.5
        if phones:
            confidence += 0.2
            # Check phone score from API
            if phone_data and isinstance(phone_data[0], dict):
                phone_score = phone_data[0].get('score', 0)
                if phone_score >= 80:
                    confidence += 0.15
                elif phone_score >= 50:
                    confidence += 0.1
        if emails:
            confidence += 0.2
        if len(phones) > 1:
            confidence += 0.05
        if len(emails) > 1:
            confidence += 0.05
        confidence = min(confidence, 0.95)

        success = bool(phones or emails)

        return SkipTraceResult(
            owner_name=found_name,
            address=address,
            phones=phones,
            emails=emails,
            primary_phone=phones[0] if phones else None,
            primary_email=emails[0] if emails else None,
            relatives=relatives[:5],
            success=success,
            provider=self.name,
            confidence_score=confidence,
            raw_response=person
        )

    def _format_phone(self, phone: str) -> str:
        """Format phone number to (XXX) XXX-XXXX."""
        digits = ''.join(c for c in str(phone) if c.isdigit())
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == '1':
            return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
        return phone

    def bulk_lookup(self, records: List[Dict[str, str]]) -> List[SkipTraceResult]:
        """
        Perform bulk skip trace lookups.

        BatchData supports up to 100 records per request.

        Args:
            records: List of dicts with 'owner_name' and 'address' keys

        Returns:
            List of SkipTraceResult objects
        """
        results = []

        # Process in batches of 100
        batch_size = 100
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]

            # Build bulk request
            requests_list = []
            for record in batch:
                owner_name = record.get('owner_name', '')
                address = record.get('address', '')

                # Normalize name format
                normalized_name = self._normalize_name(owner_name)

                requests_list.append({
                    "propertyAddress": {
                        "street": address.split(',')[0].strip() if ',' in address else address,
                        "city": record.get('city', ''),
                        "state": record.get('state', 'OH'),
                        "zip": str(record.get('zip_code', ''))[:5]
                    },
                    "ownerName": normalized_name
                })

            payload = {"requests": requests_list}

            try:
                response = self.session.post(
                    f"{self.BASE_URL}{self.SKIP_TRACE_ENDPOINT}",
                    json=payload,
                    timeout=60
                )
                response.raise_for_status()
                data = response.json()

                # Parse each result
                api_results = data.get('results', [])
                for j, record in enumerate(batch):
                    if j < len(api_results):
                        result = self._parse_response(
                            record.get('owner_name', ''),
                            record.get('address', ''),
                            {'results': [api_results[j]]}
                        )
                    else:
                        result = SkipTraceResult(
                            owner_name=record.get('owner_name', ''),
                            address=record.get('address', ''),
                            success=False,
                            provider=self.name,
                            error_message="No data returned"
                        )
                    results.append(result)

            except requests.exceptions.RequestException as e:
                logger.error(f"Bulk lookup error: {e}")
                # Return failed results for this batch
                for record in batch:
                    results.append(SkipTraceResult(
                        owner_name=record.get('owner_name', ''),
                        address=record.get('address', ''),
                        success=False,
                        provider=self.name,
                        error_message=str(e)
                    ))

        return results

    def check_api_key(self) -> bool:
        """Verify API key is valid."""
        try:
            # Make a minimal request to check auth
            response = self.session.get(
                f"{self.BASE_URL}/account",
                timeout=10
            )
            return response.status_code == 200
        except:
            return False

    def get_balance(self) -> Optional[float]:
        """Get remaining account balance/credits."""
        try:
            response = self.session.get(
                f"{self.BASE_URL}/account",
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                return data.get('credits') or data.get('balance')
        except:
            pass
        return None


# ========================================
# Test
# ========================================

if __name__ == '__main__':
    import os

    api_key = os.environ.get('BATCHDATA_API_KEY')

    if not api_key:
        print("Set BATCHDATA_API_KEY environment variable to test")
        print("Example: export BATCHDATA_API_KEY=your_key_here")
    else:
        provider = BatchDataProvider(api_key)

        # Test lookup
        result = provider.lookup(
            owner_name="SMITH JOHN",
            address="123 MAIN ST",
            city="Columbus",
            state="OH",
            zip_code="43215"
        )

        print(f"Success: {result.success}")
        print(f"Phone: {result.primary_phone}")
        print(f"Email: {result.primary_email}")
        print(f"All Phones: {result.phones}")
