"""
Lifeline Home Buyers - Skip Tracer

Main class for skip tracing operations.
Supports multiple providers and caching.
"""

import pandas as pd
from typing import List, Dict, Optional, Type
from pathlib import Path
import json
from datetime import datetime
import time

from .providers.base import SkipTraceProvider, SkipTraceResult
from .providers.mock_provider import MockSkipTraceProvider
from .providers.batchdata_provider import BatchDataProvider

try:
    from config.logging_config import get_logger
    logger = get_logger("SkipTracer")
except ImportError:
    import logging
    logger = logging.getLogger("SkipTracer")


# Re-export for convenience
__all__ = ['SkipTracer', 'SkipTraceResult']


class SkipTracer:
    """
    Main skip tracing orchestrator.

    Handles provider selection, caching, rate limiting, and DataFrame integration.
    """

    # Available providers
    PROVIDERS = {
        'mock': MockSkipTraceProvider,
        'batchdata': BatchDataProvider,  # Real skip tracing via BatchData.com API
        # Add more providers here:
        # 'propstream': PropStreamProvider,
    }

    def __init__(
        self,
        provider: str = 'mock',
        api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        rate_limit: float = 0.5,  # seconds between requests
    ):
        """
        Initialize skip tracer.

        Args:
            provider: Provider name ('mock', 'batch_skip_tracing', etc.)
            api_key: API key for the provider (if required)
            cache_dir: Directory for caching results
            rate_limit: Minimum seconds between API calls
        """
        self.provider_name = provider
        self.api_key = api_key
        self.rate_limit = rate_limit
        self.last_request_time = 0

        # Initialize provider
        if provider not in self.PROVIDERS:
            available = ', '.join(self.PROVIDERS.keys())
            raise ValueError(f"Unknown provider: {provider}. Available: {available}")

        provider_class = self.PROVIDERS[provider]

        if provider == 'mock':
            self.provider = provider_class()
        else:
            if api_key is None:
                raise ValueError(f"Provider '{provider}' requires an API key")
            self.provider = provider_class(api_key=api_key)

        # Setup cache
        if cache_dir:
            self.cache_dir = Path(cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.cache_dir = None

        self.cache = {}
        self._load_cache()

        logger.info(f"SkipTracer initialized with provider: {provider}")

    def _load_cache(self):
        """Load cached results from disk."""
        if not self.cache_dir:
            return

        cache_file = self.cache_dir / 'skip_trace_cache.json'
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    self.cache = json.load(f)
                logger.info(f"Loaded {len(self.cache)} cached skip trace results")
            except Exception as e:
                logger.warning(f"Could not load cache: {e}")
                self.cache = {}

    def _save_cache(self):
        """Save cache to disk."""
        if not self.cache_dir:
            return

        cache_file = self.cache_dir / 'skip_trace_cache.json'
        try:
            with open(cache_file, 'w') as f:
                json.dump(self.cache, f)
        except Exception as e:
            logger.warning(f"Could not save cache: {e}")

    def _get_cache_key(self, owner_name: str, address: str) -> str:
        """Generate cache key for a lookup."""
        return f"{owner_name}|{address}".lower().strip()

    def _rate_limit_wait(self):
        """Wait if needed to respect rate limit."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    def lookup(self, owner_name: str, address: str, use_cache: bool = True, **kwargs) -> SkipTraceResult:
        """
        Perform a single skip trace lookup.

        Args:
            owner_name: Property owner's name
            address: Property address
            use_cache: Whether to use cached results
            **kwargs: Additional args like city, state, zip_code for BatchData

        Returns:
            SkipTraceResult with contact information
        """
        cache_key = self._get_cache_key(owner_name, address)

        # Check cache
        if use_cache and cache_key in self.cache:
            cached = self.cache[cache_key]
            return SkipTraceResult(
                owner_name=owner_name,
                address=address,
                phones=cached.get('phones', []),
                emails=cached.get('emails', []),
                primary_phone=cached.get('primary_phone'),
                primary_email=cached.get('primary_email'),
                relatives=cached.get('relatives', []),
                success=cached.get('success', False),
                provider=cached.get('provider', ''),
                confidence_score=cached.get('confidence_score', 0),
                lookup_date=cached.get('lookup_date', ''),
            )

        # Rate limit
        self._rate_limit_wait()

        # Perform lookup - pass kwargs for city, state, zip_code
        result = self.provider.lookup(owner_name, address, **kwargs)

        # Cache result
        if result.success:
            self.cache[cache_key] = {
                'phones': result.phones,
                'emails': result.emails,
                'primary_phone': result.primary_phone,
                'primary_email': result.primary_email,
                'relatives': result.relatives,
                'success': result.success,
                'provider': result.provider,
                'confidence_score': result.confidence_score,
                'lookup_date': result.lookup_date,
            }
            self._save_cache()

        return result

    def skip_trace_dataframe(
        self,
        df: pd.DataFrame,
        owner_col: str = 'owner_name',
        address_col: str = 'address',
        max_lookups: Optional[int] = None,
        progress_callback=None,
    ) -> pd.DataFrame:
        """
        Add skip trace data to a DataFrame.

        Args:
            df: Input DataFrame with owner and address columns
            owner_col: Name of owner name column
            address_col: Name of address column
            max_lookups: Maximum number of lookups to perform
            progress_callback: Optional callback function(current, total)

        Returns:
            DataFrame with added contact columns
        """
        df = df.copy()

        # Initialize columns
        df['skip_traced'] = False
        df['phone'] = None
        df['phone_2'] = None
        df['email'] = None
        df['email_2'] = None
        df['skip_trace_confidence'] = 0.0

        total = len(df) if max_lookups is None else min(len(df), max_lookups)
        traced_count = 0
        found_count = 0

        logger.info(f"Skip tracing {total} records...")

        for idx, row in df.iterrows():
            if max_lookups and traced_count >= max_lookups:
                break

            owner_name = str(row.get(owner_col, ''))
            address = str(row.get(address_col, ''))

            if not owner_name or owner_name.lower() == 'nan':
                continue

            # Perform lookup
            result = self.lookup(owner_name, address)
            traced_count += 1

            # Update DataFrame
            df.at[idx, 'skip_traced'] = result.success

            if result.success:
                found_count += 1
                df.at[idx, 'phone'] = result.primary_phone
                df.at[idx, 'email'] = result.primary_email
                df.at[idx, 'skip_trace_confidence'] = result.confidence_score

                if len(result.phones) > 1:
                    df.at[idx, 'phone_2'] = result.phones[1]
                if len(result.emails) > 1:
                    df.at[idx, 'email_2'] = result.emails[1]

            # Progress callback
            if progress_callback:
                progress_callback(traced_count, total)

        logger.info(f"Skip trace complete: {found_count}/{traced_count} records found ({found_count/traced_count*100:.1f}%)")

        return df

    def get_stats(self) -> Dict:
        """Get skip tracing statistics."""
        return {
            'provider': self.provider_name,
            'cached_results': len(self.cache),
            'provider_balance': self.provider.get_balance(),
        }


# ========================================
# CLI Test
# ========================================

if __name__ == '__main__':
    from rich.console import Console
    from rich.table import Table

    console = Console()

    # Test with mock provider
    tracer = SkipTracer(provider='mock')

    console.print("\n[bold cyan]Skip Tracer Test[/bold cyan]\n")

    # Test single lookup
    result = tracer.lookup("SMITH JOHN A", "123 MAIN ST, COLUMBUS OH 43215")

    table = Table(title="Skip Trace Result")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Owner", result.owner_name)
    table.add_row("Address", result.address)
    table.add_row("Found", "Yes" if result.success else "No")
    table.add_row("Phone", result.primary_phone or "N/A")
    table.add_row("Email", result.primary_email or "N/A")
    table.add_row("All Phones", ", ".join(result.phones) if result.phones else "N/A")
    table.add_row("Relatives", ", ".join(result.relatives) if result.relatives else "N/A")
    table.add_row("Confidence", f"{result.confidence_score:.0%}")

    console.print(table)

    # Test DataFrame integration
    console.print("\n[bold]Testing DataFrame Integration[/bold]\n")

    import pandas as pd
    test_df = pd.DataFrame({
        'owner_name': ['SMITH JOHN', 'JONES MARY', 'WILLIAMS ROBERT'],
        'address': ['123 MAIN ST', '456 OAK AVE', '789 ELM ST'],
    })

    traced_df = tracer.skip_trace_dataframe(test_df)

    console.print(traced_df[['owner_name', 'phone', 'email', 'skip_traced']].to_string())
