"""
Lifeline Home Buyers - Scraper Factory

Creates the appropriate scraper instances based on market configuration.
Enables multi-market support with a unified interface.
"""

from typing import Optional, Union
from pathlib import Path

from shared.config.market_loader import MarketConfig, load_market, MarketLoader
from shared.config.settings import RAW_DATA_DIR
from shared.config.logging_config import get_logger

logger = get_logger("ScraperFactory")


class ScraperFactory:
    """
    Factory for creating market-specific scraper instances.

    Usage:
        market = load_market('columbus_oh')
        tax_scraper = ScraperFactory.create_tax_scraper(market)
        violations_scraper = ScraperFactory.create_violations_scraper(market)
    """

    @staticmethod
    def create_tax_scraper(market: MarketConfig, data_dir: Optional[Path] = None):
        """
        Create a tax data scraper based on market configuration.

        Args:
            market: MarketConfig object
            data_dir: Optional data directory override

        Returns:
            Appropriate scraper instance for the market's tax data source

        Raises:
            ValueError: If tax data type is not supported
        """
        data_dir = data_dir or RAW_DATA_DIR
        source_type = market.tax_data.type

        logger.info(f"Creating tax scraper for {market.name} (type: {source_type})")

        if source_type == "excel":
            from sellers.scrapers.generic_excel_loader import GenericExcelLoader
            return GenericExcelLoader(market, data_dir)

        elif source_type == "web_scraper":
            # For markets that need web scraping
            # Fall back to generic Excel loader if files exist, otherwise raise error
            logger.warning(
                f"Web scraper requested for {market.name} but not yet implemented. "
                f"Falling back to Excel loader if files exist."
            )
            from sellers.scrapers.generic_excel_loader import GenericExcelLoader
            return GenericExcelLoader(market, data_dir)

        elif source_type == "api":
            # For markets with a direct API
            logger.warning(
                f"API scraper requested for {market.name} but not yet implemented. "
                f"Falling back to Excel loader if files exist."
            )
            from sellers.scrapers.generic_excel_loader import GenericExcelLoader
            return GenericExcelLoader(market, data_dir)

        else:
            raise ValueError(f"Unknown tax data type: {source_type}")

    @staticmethod
    def create_violations_scraper(market: MarketConfig):
        """
        Create a violations scraper based on market configuration.

        Args:
            market: MarketConfig object

        Returns:
            Appropriate scraper instance for the market's violations data source,
            or None if violations are not configured

        Raises:
            ValueError: If violations type is not supported
        """
        source_type = market.violations.type

        if source_type == "none" or not market.violations.url:
            logger.warning(f"No violations data source configured for {market.name}")
            return None

        logger.info(f"Creating violations scraper for {market.name} (type: {source_type})")

        if source_type == "arcgis_api":
            from sellers.scrapers.generic_violations_api import GenericViolationsAPI
            return GenericViolationsAPI(market)

        elif source_type == "web_scraper":
            logger.warning(
                f"Web scraper requested for {market.name} violations but not yet implemented. "
                f"Returning None."
            )
            return None

        else:
            raise ValueError(f"Unknown violations type: {source_type}")

    @staticmethod
    def create_all_scrapers(market: MarketConfig, data_dir: Optional[Path] = None) -> dict:
        """
        Create all scrapers for a market.

        Args:
            market: MarketConfig object
            data_dir: Optional data directory override

        Returns:
            Dict with 'tax' and 'violations' scraper instances
        """
        return {
            'tax': ScraperFactory.create_tax_scraper(market, data_dir),
            'violations': ScraperFactory.create_violations_scraper(market)
        }


def get_scrapers_for_market(
    market_id: str,
    data_dir: Optional[Path] = None
) -> dict:
    """
    Convenience function to get all scrapers for a market.

    Args:
        market_id: Market identifier (e.g., 'columbus_oh')
        data_dir: Optional data directory override

    Returns:
        Dict with 'market', 'tax', and 'violations' keys
    """
    market = load_market(market_id)
    scrapers = ScraperFactory.create_all_scrapers(market, data_dir)
    return {
        'market': market,
        **scrapers
    }


# ========================================
# CLI Entry Point
# ========================================

if __name__ == '__main__':
    """Test the scraper factory"""
    from rich.console import Console
    from rich.table import Table

    console = Console()

    loader = MarketLoader()
    markets = loader.list_available_markets()

    console.print(f"\n[bold green]Testing ScraperFactory for {len(markets)} markets[/bold green]\n")

    table = Table(title="Scraper Factory Results")
    table.add_column("Market", style="cyan")
    table.add_column("Tax Scraper", style="green")
    table.add_column("Violations Scraper", style="yellow")

    for market_id in markets:
        try:
            market = loader.load(market_id)
            scrapers = ScraperFactory.create_all_scrapers(market)

            tax_type = type(scrapers['tax']).__name__ if scrapers['tax'] else "None"
            viol_type = type(scrapers['violations']).__name__ if scrapers['violations'] else "None"

            table.add_row(market.name, tax_type, viol_type)

        except Exception as e:
            table.add_row(market_id, f"ERROR: {e}", "")

    console.print(table)

    # Test with Columbus
    console.print("\n[bold]Testing Columbus OH scrapers:[/bold]")
    result = get_scrapers_for_market('columbus_oh')
    console.print(f"  Market: {result['market'].name}")
    console.print(f"  Tax Scraper: {type(result['tax']).__name__}")
    console.print(f"  Violations Scraper: {type(result['violations']).__name__ if result['violations'] else 'None'}")
