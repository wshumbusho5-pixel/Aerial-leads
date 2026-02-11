"""
Base Skip Trace Provider

Abstract base class for skip tracing providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class SkipTraceResult:
    """Result from a skip trace lookup."""

    # Input data
    owner_name: str
    address: str

    # Contact info found
    phones: List[str] = field(default_factory=list)
    emails: List[str] = field(default_factory=list)

    # Best contact (primary)
    primary_phone: Optional[str] = None
    primary_email: Optional[str] = None

    # Additional info
    relatives: List[str] = field(default_factory=list)
    other_addresses: List[str] = field(default_factory=list)
    other_properties: List[str] = field(default_factory=list)

    # Metadata
    success: bool = False
    provider: str = ""
    confidence_score: float = 0.0
    lookup_date: str = field(default_factory=lambda: datetime.now().strftime('%Y-%m-%d'))
    raw_response: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for DataFrame."""
        return {
            'skip_traced': self.success,
            'phone': self.primary_phone or (self.phones[0] if self.phones else None),
            'phone_2': self.phones[1] if len(self.phones) > 1 else None,
            'phone_3': self.phones[2] if len(self.phones) > 2 else None,
            'phone_4': self.phones[3] if len(self.phones) > 3 else None,
            'phone_5': self.phones[4] if len(self.phones) > 4 else None,
            'phone_6': self.phones[5] if len(self.phones) > 5 else None,
            'email': self.primary_email or (self.emails[0] if self.emails else None),
            'email_2': self.emails[1] if len(self.emails) > 1 else None,
            'all_phones': '; '.join(self.phones) if self.phones else None,
            'all_emails': '; '.join(self.emails) if self.emails else None,
            'relatives': '; '.join(self.relatives) if self.relatives else None,
            'other_addresses': '; '.join(self.other_addresses) if self.other_addresses else None,
            'skip_trace_provider': self.provider,
            'skip_trace_confidence': self.confidence_score,
            'skip_trace_date': self.lookup_date,
        }


class SkipTraceProvider(ABC):
    """
    Abstract base class for skip trace providers.

    Implement this class to add support for new skip tracing services.
    """

    name: str = "base"
    requires_api_key: bool = True
    cost_per_lookup: float = 0.0

    @abstractmethod
    def lookup(self, owner_name: str, address: str, **kwargs) -> SkipTraceResult:
        """
        Perform a skip trace lookup for a single record.

        Args:
            owner_name: Property owner's name
            address: Property address
            **kwargs: Additional parameters (city, state, zip, etc.)

        Returns:
            SkipTraceResult with contact information
        """
        pass

    @abstractmethod
    def bulk_lookup(self, records: List[Dict[str, str]]) -> List[SkipTraceResult]:
        """
        Perform bulk skip trace lookups.

        Args:
            records: List of dicts with 'owner_name' and 'address' keys

        Returns:
            List of SkipTraceResult objects
        """
        pass

    @abstractmethod
    def check_api_key(self) -> bool:
        """Verify API key is valid."""
        pass

    @abstractmethod
    def get_balance(self) -> Optional[float]:
        """Get remaining balance/credits if applicable."""
        pass
