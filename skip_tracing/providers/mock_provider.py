"""
Mock Skip Trace Provider

Generates realistic fake contact data for testing and demos.
No API key required - use this for development and demos.
"""

import random
import hashlib
from typing import List, Dict, Optional

from .base import SkipTraceProvider, SkipTraceResult


class MockSkipTraceProvider(SkipTraceProvider):
    """
    Mock provider that generates realistic fake contact data.

    Uses deterministic random generation based on owner name,
    so the same owner always gets the same fake data.
    """

    name = "mock"
    requires_api_key = False
    cost_per_lookup = 0.0

    # Sample data pools
    AREA_CODES = ['614', '740', '937', '513', '419', '330', '216', '440']
    EMAIL_DOMAINS = ['gmail.com', 'yahoo.com', 'hotmail.com', 'aol.com', 'outlook.com', 'icloud.com']
    FIRST_NAMES = ['James', 'John', 'Robert', 'Michael', 'William', 'David', 'Mary', 'Patricia',
                   'Jennifer', 'Linda', 'Elizabeth', 'Barbara', 'Susan', 'Jessica', 'Sarah']
    LAST_NAMES = ['Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis']

    def __init__(self, success_rate: float = 0.75):
        """
        Initialize mock provider.

        Args:
            success_rate: Probability of finding contact info (0.0 to 1.0)
        """
        self.success_rate = success_rate

    def _get_seed(self, owner_name: str, address: str) -> int:
        """Generate deterministic seed from owner/address."""
        combined = f"{owner_name}:{address}".lower()
        return int(hashlib.md5(combined.encode()).hexdigest()[:8], 16)

    def _generate_phone(self, seed: int, index: int = 0) -> str:
        """Generate a realistic phone number."""
        random.seed(seed + index)
        area_code = random.choice(self.AREA_CODES)
        exchange = random.randint(200, 999)
        number = random.randint(1000, 9999)
        return f"({area_code}) {exchange}-{number}"

    def _generate_email(self, owner_name: str, seed: int) -> str:
        """Generate a realistic email from owner name."""
        random.seed(seed)

        # Parse name
        parts = owner_name.upper().replace(',', ' ').split()
        if len(parts) >= 2:
            # Try last.first format
            first = parts[-1].lower() if len(parts) > 1 else parts[0].lower()
            last = parts[0].lower()
        else:
            first = parts[0].lower() if parts else 'owner'
            last = ''

        # Clean name parts
        first = ''.join(c for c in first if c.isalnum())[:10]
        last = ''.join(c for c in last if c.isalnum())[:10]

        # Generate email variations
        domain = random.choice(self.EMAIL_DOMAINS)
        variations = [
            f"{first}.{last}@{domain}" if last else f"{first}@{domain}",
            f"{first}{last}@{domain}" if last else f"{first}123@{domain}",
            f"{first[0]}{last}@{domain}" if last and first else f"{first}@{domain}",
        ]

        return random.choice(variations)

    def _generate_relative(self, seed: int) -> str:
        """Generate a relative name."""
        random.seed(seed)
        first = random.choice(self.FIRST_NAMES)
        last = random.choice(self.LAST_NAMES)
        return f"{first} {last}"

    def lookup(self, owner_name: str, address: str, **kwargs) -> SkipTraceResult:
        """
        Perform a mock skip trace lookup.

        Args:
            owner_name: Property owner's name
            address: Property address

        Returns:
            SkipTraceResult with mock contact data
        """
        seed = self._get_seed(owner_name, address)
        random.seed(seed)

        # Determine if we "find" this person
        found = random.random() < self.success_rate

        if not found:
            return SkipTraceResult(
                owner_name=owner_name,
                address=address,
                success=False,
                provider=self.name,
                error_message="No records found"
            )

        # Generate mock data
        num_phones = random.randint(1, 3)
        num_emails = random.randint(1, 2)
        num_relatives = random.randint(0, 3)

        phones = [self._generate_phone(seed, i) for i in range(num_phones)]
        emails = [self._generate_email(owner_name, seed + i) for i in range(num_emails)]
        relatives = [self._generate_relative(seed + 100 + i) for i in range(num_relatives)]

        # Confidence based on data quality
        confidence = 0.5 + (num_phones * 0.1) + (num_emails * 0.1)
        confidence = min(confidence, 0.95)

        return SkipTraceResult(
            owner_name=owner_name,
            address=address,
            phones=phones,
            emails=emails,
            primary_phone=phones[0] if phones else None,
            primary_email=emails[0] if emails else None,
            relatives=relatives,
            success=True,
            provider=self.name,
            confidence_score=confidence,
        )

    def bulk_lookup(self, records: List[Dict[str, str]]) -> List[SkipTraceResult]:
        """
        Perform bulk mock skip trace lookups.

        Args:
            records: List of dicts with 'owner_name' and 'address' keys

        Returns:
            List of SkipTraceResult objects
        """
        results = []
        for record in records:
            owner_name = record.get('owner_name', '')
            address = record.get('address', '')
            result = self.lookup(owner_name, address)
            results.append(result)
        return results

    def check_api_key(self) -> bool:
        """Mock provider doesn't need an API key."""
        return True

    def get_balance(self) -> Optional[float]:
        """Mock provider has unlimited balance."""
        return float('inf')


# ========================================
# Test
# ========================================

if __name__ == '__main__':
    provider = MockSkipTraceProvider(success_rate=0.8)

    # Test single lookup
    result = provider.lookup("SMITH JOHN", "123 MAIN ST, COLUMBUS OH")

    print(f"Owner: {result.owner_name}")
    print(f"Success: {result.success}")
    print(f"Phone: {result.primary_phone}")
    print(f"Email: {result.primary_email}")
    print(f"All Phones: {result.phones}")
    print(f"Relatives: {result.relatives}")
    print(f"Confidence: {result.confidence_score:.0%}")
