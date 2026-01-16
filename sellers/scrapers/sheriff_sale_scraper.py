"""
Aerial Leads - Sheriff Sale / Pre-Foreclosure Scraper

Scrapes upcoming sheriff sales and pre-foreclosure properties.
These are highly motivated sellers facing auction deadlines.

Data Sources:
- ohiosheriffsales.com (aggregator)
- County sheriff auction sites
"""

import re
import time
from typing import List, Dict, Optional
from datetime import datetime
from bs4 import BeautifulSoup
import pandas as pd

from sellers.scrapers.base_scraper import BaseScraper


class SheriffSaleScraper(BaseScraper):
    """
    Scraper for Ohio sheriff sales and pre-foreclosure properties.

    Targets properties scheduled for sheriff sale auction.
    These owners have limited time and high motivation to sell.
    """

    BASE_URL = "https://www.ohiosheriffsales.com"
    UPCOMING_URL = f"{BASE_URL}/upcoming_auctions"

    # Franklin County cities for filtering
    FRANKLIN_CITIES = [
        'Columbus', 'Hilliard', 'Grove City', 'Westerville', 'Dublin',
        'Gahanna', 'Reynoldsburg', 'Whitehall', 'Bexley', 'Upper Arlington',
        'Harrisburg', 'Worthington', 'Grandview Heights', 'Groveport',
        'Canal Winchester', 'Pickerington', 'New Albany', 'Powell'
    ]

    def __init__(self, county: str = "franklin"):
        super().__init__()
        self.county = county.lower()
        self.properties = []

    def scrape(
        self,
        max_results: int = 200,
        include_details: bool = True
    ) -> pd.DataFrame:
        """
        Scrape sheriff sale listings for the county.

        Args:
            max_results: Maximum number of properties to scrape
            include_details: Whether to fetch detailed property info

        Returns:
            DataFrame with sheriff sale property data
        """
        self.logger.info(f"Starting sheriff sale scrape for {self.county} county")

        # Get listing page
        listings = self._get_listings(max_results)

        if not listings:
            self.logger.warning("No sheriff sale listings found")
            return pd.DataFrame()

        self.logger.info(f"Found {len(listings)} sheriff sale listings")

        # Optionally get details for each property
        if include_details:
            listings = self._enrich_listings(listings)

        # Convert to DataFrame
        df = pd.DataFrame(listings)

        if not df.empty:
            # Add metadata
            df['source'] = 'ohio_sheriff_sales'
            df['scraped_at'] = datetime.now().isoformat()
            df['lead_type'] = 'pre_foreclosure'
            df['county'] = self.county.title()
            df['state'] = 'OH'

        self.logger.info(f"Total sheriff sale properties: {len(df)}")
        return df

    def _get_listings(self, max_results: int) -> List[Dict]:
        """Get list of properties from sheriff sale listings."""
        listings = []

        # Use the upcoming auctions page which has all counties
        url = self.UPCOMING_URL
        self.logger.debug(f"Fetching upcoming auctions: {url}")

        response = self._make_request(url)

        if not response:
            self.logger.warning("Failed to fetch upcoming auctions page")
            return listings

        # Parse all listings from the page
        all_listings = self._parse_listing_page(response.text)

        # Filter for Franklin County only
        for listing in all_listings:
            if self._is_franklin_county(listing):
                listings.append(listing)
                if len(listings) >= max_results:
                    break

        return listings[:max_results]

    def _is_franklin_county(self, listing: Dict) -> bool:
        """Check if a listing is in Franklin County."""
        city = listing.get('city', '').title()
        return city in self.FRANKLIN_CITIES or 'Franklin' in listing.get('county', '')

    def _parse_listing_page(self, html: str) -> List[Dict]:
        """Parse a listings page to extract property cards."""
        listings = []
        soup = BeautifulSoup(html, 'html.parser')

        # The site uses Bootstrap grid - each property is in col-lg-4 divs
        property_cards = soup.find_all('div', class_='col-lg-4')

        self.logger.debug(f"Found {len(property_cards)} property cards")

        for card in property_cards:
            listing = self._parse_property_card(card)
            if listing and listing.get('address'):
                listings.append(listing)

        return listings

    def _parse_property_card(self, card) -> Optional[Dict]:
        """Parse a single property card/listing."""
        try:
            listing = {
                'address': '',
                'city': '',
                'zip_code': '',
                'county': '',
                'auction_date': '',
                'starting_bid': 0,
                'property_type': '',
                'bedrooms': 0,
                'bathrooms': 0,
                'sqft': 0,
                'lot_size': '',
                'detail_url': '',
                'image_url': '',
                'case_number': '',
            }

            # Get full card text for parsing
            full_text = card.get_text(strip=True)

            # Extract county
            county_match = re.search(r'(\w+)\s*COUNTY', full_text)
            if county_match:
                listing['county'] = county_match.group(1).title()

            # Extract date from post-date div
            date_div = card.find('div', class_='post-date')
            if date_div:
                listing['auction_date'] = date_div.get_text(strip=True)

            # Extract address - text starts with MonDD then address
            # Format: Jan09513-515 Kelton AveColumbusFranklin COUNTYOH 43205...
            cities_pattern = '|'.join(self.FRANKLIN_CITIES)
            addr_match = re.search(
                rf'(?:[A-Z][a-z]{{2}}\d{{2}})?(.+?)(?:{cities_pattern})',
                full_text
            )
            if addr_match:
                addr = addr_match.group(1).strip()
                # Remove leading date if present (MonDD format)
                addr = re.sub(r'^[A-Z][a-z]{2}\d{2}', '', addr)
                listing['address'] = addr

            # Extract city
            city_match = re.search(rf'({cities_pattern})', full_text)
            if city_match:
                listing['city'] = city_match.group(1)

            # Extract zip code
            zip_match = re.search(r'OH\s*(\d{5})', full_text)
            if zip_match:
                listing['zip_code'] = zip_match.group(1)

            # Extract starting bid
            bid_match = re.search(r'Bidding starts at \$([\d,]+)', full_text)
            if bid_match:
                listing['starting_bid'] = int(bid_match.group(1).replace(',', ''))

            # Extract beds/baths/sqft
            beds_match = re.search(r'(\d+)\s*bedrooms?', full_text, re.I)
            if beds_match:
                listing['bedrooms'] = int(beds_match.group(1))

            baths_match = re.search(r'([\d.]+)\s*(?:full\s+)?bathrooms?', full_text, re.I)
            if baths_match:
                listing['bathrooms'] = float(baths_match.group(1))

            sqft_match = re.search(r'([\d,]+)\s*sq\.?\s*ft', full_text, re.I)
            if sqft_match:
                listing['sqft'] = int(sqft_match.group(1).replace(',', ''))

            # Get detail link
            link = card.find('a', href=True)
            if link:
                href = link['href']
                if href.startswith('/'):
                    listing['detail_url'] = self.BASE_URL + href
                elif href.startswith('http'):
                    listing['detail_url'] = href

            # Extract image
            img = card.find('img', src=True)
            if img:
                listing['image_url'] = img['src']

            # Only return if we got an address
            if listing['address']:
                return listing

            return None

        except Exception as e:
            self.logger.debug(f"Error parsing property card: {e}")
            return None

    def _enrich_listings(self, listings: List[Dict]) -> List[Dict]:
        """Fetch additional details for each listing."""
        enriched = []

        for i, listing in enumerate(listings):
            if listing.get('detail_url'):
                self.logger.debug(f"Enriching {i+1}/{len(listings)}: {listing['address']}")

                details = self._get_property_details(listing['detail_url'])

                if details:
                    listing.update(details)

                # Rate limiting
                time.sleep(0.5)

            enriched.append(listing)

        return enriched

    def _get_property_details(self, url: str) -> Dict:
        """Fetch detailed property information from detail page."""
        details = {}

        response = self._make_request(url)

        if not response:
            return details

        soup = BeautifulSoup(response.text, 'html.parser')

        # Look for case number
        case_match = re.search(r'case\s*(?:#|number|no\.?)?\s*:?\s*([A-Z0-9\-]+)', soup.get_text(), re.I)
        if case_match:
            details['case_number'] = case_match.group(1)

        # Look for auction date
        date_match = re.search(r'(?:auction|sale)\s*date\s*:?\s*(\d{1,2}/\d{1,2}/\d{2,4})', soup.get_text(), re.I)
        if date_match:
            details['auction_date'] = date_match.group(1)

        # Look for minimum/starting bid
        bid_match = re.search(r'(?:minimum|starting|opening)\s*bid\s*:?\s*\$?([\d,]+)', soup.get_text(), re.I)
        if bid_match:
            details['starting_bid'] = self._parse_currency(bid_match.group(1))

        # Look for property type
        type_patterns = [
            (r'single\s*family', 'Single Family'),
            (r'duplex', 'Duplex'),
            (r'multi\s*family', 'Multi Family'),
            (r'condo', 'Condo'),
            (r'townhouse', 'Townhouse'),
            (r'mobile\s*home', 'Mobile Home'),
            (r'commercial', 'Commercial'),
            (r'vacant\s*land', 'Vacant Land'),
        ]

        text_lower = soup.get_text().lower()
        for pattern, prop_type in type_patterns:
            if re.search(pattern, text_lower):
                details['property_type'] = prop_type
                break

        # Look for owner name (defendant in foreclosure)
        defendant_match = re.search(r'(?:defendant|owner|borrower)\s*:?\s*([A-Za-z\s,\.]+?)(?:\n|$|;)', soup.get_text(), re.I)
        if defendant_match:
            details['owner_name'] = defendant_match.group(1).strip()

        # Look for assessed/appraised value
        value_match = re.search(r'(?:assessed|appraised|market)\s*value\s*:?\s*\$?([\d,]+)', soup.get_text(), re.I)
        if value_match:
            details['assessed_value'] = self._parse_currency(value_match.group(1))

        return details

    def scrape_direct_from_county(self) -> pd.DataFrame:
        """
        Alternative method to scrape directly from county auction site.
        Use this if the aggregator site is unavailable.
        """
        # Franklin County Sheriff auction site
        county_url = "https://franklin.sheriffsaleauction.ohio.gov/"

        self.logger.info(f"Attempting direct county scrape: {county_url}")

        # Note: This site may require Selenium due to JavaScript rendering
        response = self._make_request(county_url)

        if not response:
            self.logger.warning("Could not access county auction site (may require JavaScript)")
            return pd.DataFrame()

        # Parse if accessible
        listings = self._parse_listing_page(response.text)

        return pd.DataFrame(listings)


class PreForeclosureScraper(BaseScraper):
    """
    Scraper for pre-foreclosure properties (Lis Pendens filings).

    These are properties where foreclosure has been filed but
    auction hasn't occurred yet - maximum motivation window.
    """

    def __init__(self, county: str = "franklin"):
        super().__init__()
        self.county = county

    def scrape(self, days_back: int = 90, max_results: int = 200) -> pd.DataFrame:
        """
        Scrape pre-foreclosure filings.

        Note: This requires access to county court records or
        a paid data service. This implementation provides the structure
        for when that access is available.
        """
        self.logger.info(f"Pre-foreclosure scrape for {self.county} county")

        # TODO: Implement when we have access to:
        # - Franklin County Clerk of Courts API
        # - Lis Pendens filing search
        # - Or a paid data service like ATTOM, PropertyShark, etc.

        self.logger.warning("Pre-foreclosure scraper requires court records access")
        self.logger.info("Use SheriffSaleScraper for properties already scheduled for auction")

        return pd.DataFrame()


# Example usage and testing
if __name__ == '__main__':
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print("\n[bold cyan]Sheriff Sale Scraper Test[/bold cyan]\n")

    scraper = SheriffSaleScraper(county="franklin")

    # Scrape sheriff sale listings
    df = scraper.scrape(max_results=20, include_details=False)

    if not df.empty:
        table = Table(title=f"Sheriff Sale Properties: {len(df)}")
        table.add_column("Address", style="cyan", max_width=40)
        table.add_column("City", style="yellow")
        table.add_column("Auction Date", style="red")
        table.add_column("Starting Bid", style="green", justify="right")

        for _, row in df.head(10).iterrows():
            table.add_row(
                str(row.get('address', ''))[:40],
                str(row.get('city', '')),
                str(row.get('auction_date', '')),
                f"${row.get('starting_bid', 0):,.0f}"
            )

        console.print(table)
    else:
        console.print("[yellow]No sheriff sale properties found[/yellow]")

    # Print stats
    stats = scraper.get_stats()
    console.print(f"\n[dim]Stats: {stats}[/dim]")
