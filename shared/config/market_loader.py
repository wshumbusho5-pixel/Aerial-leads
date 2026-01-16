"""
Aerial Leads - Market Configuration Loader

Loads market-specific configurations from YAML files.
Enables multi-market support without code changes.
"""

import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from shared.config.settings import CONFIG_DIR
from shared.config.logging_config import get_logger


# Default markets directory
MARKETS_DIR = CONFIG_DIR / 'markets'


@dataclass
class TaxDataConfig:
    """Configuration for tax delinquency data source"""
    type: str  # excel, web_scraper, api
    source: str
    urls: Dict[str, str] = field(default_factory=dict)
    files: Dict[str, str] = field(default_factory=dict)
    field_mappings: Dict[str, str] = field(default_factory=dict)


@dataclass
class ViolationsConfig:
    """Configuration for code violations data source"""
    type: str  # arcgis_api, web_scraper, none
    source: str
    url: str = ""
    query_field: str = ""
    max_records_per_request: int = 1000
    field_mappings: Dict[str, str] = field(default_factory=dict)


@dataclass
class ScoringConfig:
    """Market-specific scoring adjustments"""
    tax_debt_ratio: Dict[str, float] = field(default_factory=lambda: {
        'high': 0.20,
        'medium': 0.10,
        'low': 0.05
    })
    estimated_annual_tax_rate: float = 0.04


@dataclass
class DataQualityConfig:
    """Data quality filter settings"""
    min_amount_owed: float = 1000.0
    min_years_delinquent: int = 2
    max_data_age_days: int = 30


@dataclass
class MarketConfig:
    """Complete market configuration"""
    id: str
    name: str
    state: str
    county: str
    timezone: str
    zip_codes: List[str]
    tax_data: TaxDataConfig
    violations: ViolationsConfig
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    data_quality: DataQualityConfig = field(default_factory=DataQualityConfig)

    def __post_init__(self):
        """Validate configuration after initialization"""
        if not self.id:
            raise ValueError("Market ID is required")
        if not self.zip_codes:
            raise ValueError(f"Market {self.id} has no zip codes defined")

    @property
    def display_name(self) -> str:
        """Human-readable market name with county"""
        return f"{self.name} ({self.county} County)"


class MarketLoader:
    """
    Loads and caches market configurations from YAML files.

    Usage:
        loader = MarketLoader()
        markets = loader.list_available_markets()
        config = loader.load('columbus_oh')
    """

    def __init__(self, markets_dir: Path = MARKETS_DIR):
        self.markets_dir = Path(markets_dir)
        self._cache: Dict[str, MarketConfig] = {}
        self.logger = get_logger(self.__class__.__name__)

        if not self.markets_dir.exists():
            self.logger.warning(f"Markets directory not found: {self.markets_dir}")

    def list_available_markets(self) -> List[str]:
        """
        List all available market IDs.

        Returns:
            List of market IDs (e.g., ['columbus_oh', 'cleveland_oh'])
        """
        if not self.markets_dir.exists():
            return []

        markets = []
        for file_path in self.markets_dir.glob("*.yaml"):
            # Skip template files
            if file_path.stem.startswith('_'):
                continue
            markets.append(file_path.stem)

        return sorted(markets)

    def get_market_info(self) -> List[Dict[str, str]]:
        """
        Get basic info about all available markets.

        Returns:
            List of dicts with id, name, county for each market
        """
        info = []
        for market_id in self.list_available_markets():
            try:
                config = self.load(market_id)
                info.append({
                    'id': config.id,
                    'name': config.name,
                    'county': config.county,
                    'state': config.state,
                    'zip_count': len(config.zip_codes)
                })
            except Exception as e:
                self.logger.warning(f"Could not load market {market_id}: {e}")
        return info

    def load(self, market_id: str) -> MarketConfig:
        """
        Load a market configuration by ID.

        Args:
            market_id: Market identifier (e.g., 'columbus_oh')

        Returns:
            MarketConfig object

        Raises:
            ValueError: If market not found
            yaml.YAMLError: If YAML parsing fails
        """
        # Check cache first
        if market_id in self._cache:
            return self._cache[market_id]

        # Find config file
        config_path = self.markets_dir / f"{market_id}.yaml"
        if not config_path.exists():
            available = self.list_available_markets()
            raise ValueError(
                f"Market '{market_id}' not found. "
                f"Available markets: {available}"
            )

        # Load YAML
        self.logger.info(f"Loading market config: {market_id}")
        with open(config_path, 'r') as f:
            data = yaml.safe_load(f)

        # Parse into dataclasses
        config = self._parse_config(market_id, data)

        # Cache for future use
        self._cache[market_id] = config

        return config

    def _parse_config(self, market_id: str, data: Dict[str, Any]) -> MarketConfig:
        """Parse YAML data into MarketConfig dataclass"""

        market_data = data.get('market', {})
        tax_data = data.get('tax_data', {})
        violations_data = data.get('violations', {})
        geography_data = data.get('geography', {})
        scoring_data = data.get('scoring', {})
        quality_data = data.get('data_quality', {})

        # Parse tax data config
        tax_config = TaxDataConfig(
            type=tax_data.get('type', 'excel'),
            source=tax_data.get('source', ''),
            urls=tax_data.get('urls', {}),
            files=tax_data.get('files', {}),
            field_mappings=tax_data.get('field_mappings', {})
        )

        # Parse violations config
        violations_config = ViolationsConfig(
            type=violations_data.get('type', 'none'),
            source=violations_data.get('source', ''),
            url=violations_data.get('url', ''),
            query_field=violations_data.get('query_field', ''),
            max_records_per_request=violations_data.get('max_records_per_request', 1000),
            field_mappings=violations_data.get('field_mappings', {})
        )

        # Parse scoring config
        scoring_config = ScoringConfig(
            tax_debt_ratio=scoring_data.get('tax_debt_ratio', {
                'high': 0.20,
                'medium': 0.10,
                'low': 0.05
            }),
            estimated_annual_tax_rate=scoring_data.get('estimated_annual_tax_rate', 0.04)
        )

        # Parse data quality config
        quality_config = DataQualityConfig(
            min_amount_owed=quality_data.get('min_amount_owed', 1000.0),
            min_years_delinquent=quality_data.get('min_years_delinquent', 2),
            max_data_age_days=quality_data.get('max_data_age_days', 30)
        )

        # Build final config
        return MarketConfig(
            id=market_data.get('id', market_id),
            name=market_data.get('name', market_id),
            state=market_data.get('state', ''),
            county=market_data.get('county', ''),
            timezone=market_data.get('timezone', 'America/New_York'),
            zip_codes=geography_data.get('zip_codes', []),
            tax_data=tax_config,
            violations=violations_config,
            scoring=scoring_config,
            data_quality=quality_config
        )

    def reload(self, market_id: str) -> MarketConfig:
        """
        Force reload a market config (clear cache).

        Args:
            market_id: Market identifier

        Returns:
            Fresh MarketConfig object
        """
        if market_id in self._cache:
            del self._cache[market_id]
        return self.load(market_id)

    def clear_cache(self):
        """Clear all cached market configs"""
        self._cache.clear()

    def validate_all(self) -> Dict[str, Optional[str]]:
        """
        Validate all market config files.

        Returns:
            Dict mapping market_id -> error message (None if valid)
        """
        results = {}
        for market_id in self.list_available_markets():
            try:
                self.load(market_id)
                results[market_id] = None  # Valid
            except Exception as e:
                results[market_id] = str(e)
        return results


# Singleton instance for easy access
_default_loader: Optional[MarketLoader] = None


def get_market_loader() -> MarketLoader:
    """Get the default MarketLoader instance"""
    global _default_loader
    if _default_loader is None:
        _default_loader = MarketLoader()
    return _default_loader


def load_market(market_id: str) -> MarketConfig:
    """
    Convenience function to load a market config.

    Args:
        market_id: Market identifier (e.g., 'columbus_oh')

    Returns:
        MarketConfig object
    """
    return get_market_loader().load(market_id)


def list_markets() -> List[str]:
    """Convenience function to list available markets"""
    return get_market_loader().list_available_markets()


# ========================================
# CLI Entry Point
# ========================================

if __name__ == '__main__':
    """Test the market loader"""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    loader = MarketLoader()

    # List available markets
    console.print("\n[bold green]Available Markets:[/bold green]")
    markets = loader.list_available_markets()
    console.print(f"Found {len(markets)} markets: {markets}")

    # Load and display each market
    table = Table(title="Market Configurations")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("County", style="yellow")
    table.add_column("Tax Data Type", style="magenta")
    table.add_column("Violations Type", style="blue")
    table.add_column("Zip Codes", style="white")

    for market_id in markets:
        try:
            config = loader.load(market_id)
            table.add_row(
                config.id,
                config.name,
                config.county,
                config.tax_data.type,
                config.violations.type,
                str(len(config.zip_codes))
            )
        except Exception as e:
            table.add_row(market_id, f"ERROR: {e}", "", "", "", "")

    console.print(table)

    # Show detailed config for columbus_oh
    if 'columbus_oh' in markets:
        console.print("\n[bold]Columbus OH Details:[/bold]")
        config = loader.load('columbus_oh')
        console.print(f"  Tax Data URL: {config.tax_data.urls.get('web_search', 'N/A')}")
        console.print(f"  Violations URL: {config.violations.url}")
        console.print(f"  Min Amount Owed: ${config.data_quality.min_amount_owed:,.0f}")
        console.print(f"  Annual Tax Rate: {config.scoring.estimated_annual_tax_rate:.1%}")

    # Validate all configs
    console.print("\n[bold]Validating all configs...[/bold]")
    results = loader.validate_all()
    for market_id, error in results.items():
        if error:
            console.print(f"  [red]✗ {market_id}: {error}[/red]")
        else:
            console.print(f"  [green]✓ {market_id}: Valid[/green]")
