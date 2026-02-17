"""
Lifeline Home Buyers - Reverse Targeting Scraper

Find motivated sellers who are ACTIVELY trying to sell their property.
Instead of cold calling - find people who raised their hand.

Sources:
- Craigslist FSBO listings
- Facebook Marketplace (manual/API)
- Zillow FSBO
- ForSaleByOwner.com
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import re
import time
import json
from typing import List, Dict, Optional

from config.settings import DATA_DIR, PROCESSED_DATA_DIR
from config.logging_config import get_logger


class ReverseTargetingScraper:
    """
    Scrape active seller listings from various sources.
    These are HOT leads - they're actively trying to sell.
    """

    def __init__(self):
        self.logger = get_logger(self.__class__.__name__)
        self.leads_file = DATA_DIR / "reverse_targeting_leads.csv"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })

        # Initialize leads file
        self._init_leads_file()

    def _init_leads_file(self):
        """Initialize the leads CSV if it doesn't exist."""
        columns = [
            'id', 'source', 'title', 'description', 'price', 'address',
            'city', 'state', 'phone', 'email', 'url', 'posted_date',
            'scraped_at', 'status', 'notes'
        ]

        if not self.leads_file.exists():
            pd.DataFrame(columns=columns).to_csv(self.leads_file, index=False)
            self.logger.info(f"Created reverse targeting leads file: {self.leads_file}")

    def scrape_craigslist(self, city: str = "columbus", state: str = "ohio", max_pages: int = 3) -> List[Dict]:
        """
        Scrape Craigslist real estate by owner (FSBO) listings.

        Args:
            city: City to search
            state: State
            max_pages: Max pages to scrape

        Returns:
            List of lead dictionaries
        """
        leads = []
        base_url = f"https://{city}.craigslist.org"

        self.logger.info(f"Scraping Craigslist FSBO for {city}, {state}...")

        for page in range(max_pages):
            offset = page * 120
            url = f"{base_url}/search/rea?purveyor=owner&s={offset}"

            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()

                soup = BeautifulSoup(response.text, 'html.parser')

                # Try multiple selectors - Craigslist changes their layout
                listings = soup.select('li.cl-static-search-result')
                if not listings:
                    listings = soup.select('.cl-search-result, .result-row')
                if not listings:
                    listings = soup.select('.gallery-card')

                if not listings:
                    self.logger.info(f"No more listings on page {page + 1}")
                    break

                for listing in listings:
                    try:
                        lead = self._parse_craigslist_listing(listing, base_url)
                        if lead:
                            lead['source'] = 'craigslist'
                            lead['city'] = city.title()
                            lead['state'] = state.upper()[:2]
                            leads.append(lead)
                    except Exception as e:
                        self.logger.debug(f"Error parsing listing: {e}")
                        continue

                self.logger.info(f"Page {page + 1}: Found {len(listings)} listings")
                time.sleep(2)  # Be nice to the server

            except Exception as e:
                self.logger.error(f"Error scraping Craigslist page {page + 1}: {e}")
                break

        self.logger.info(f"Total Craigslist leads found: {len(leads)}")
        return leads

    def _parse_craigslist_listing(self, listing, base_url: str) -> Optional[Dict]:
        """Parse a single Craigslist listing."""
        # New Craigslist structure (2024+):
        # <li class="cl-static-search-result">
        #   <a href="...">
        #     <div class="title">TITLE</div>
        #     <div class="details">
        #       <div class="price">$X</div>
        #       <div class="location">LOCATION</div>
        #     </div>
        #   </a>
        # </li>

        # Get the link element first
        link_elem = listing.select_one('a')
        if not link_elem:
            return None

        link = link_elem.get('href', '')
        if not link:
            return None

        if not link.startswith('http'):
            link = base_url + link

        # Try new structure first, then fall back to old selectors
        title_elem = listing.select_one('.title, .posting-title, .result-title, a.titlestring')
        title = title_elem.get_text(strip=True) if title_elem else listing.get('title', '')

        if not title:
            return None

        # Get price - try new structure first
        price_elem = listing.select_one('.price, .priceinfo, .result-price')
        price = price_elem.get_text(strip=True) if price_elem else ''
        price = re.sub(r'[^\d]', '', price)  # Extract numbers only

        # Get location/neighborhood - try new structure first
        location_elem = listing.select_one('.location, .meta, .result-hood')
        location = location_elem.get_text(strip=True) if location_elem else ''
        location = location.strip('() ')

        # Get date if available
        date_elem = listing.select_one('time, .meta .date')
        posted_date = ''
        if date_elem:
            if date_elem.has_attr('datetime'):
                posted_date = date_elem['datetime'][:10]
            else:
                posted_date = date_elem.get_text(strip=True)

        return {
            'id': f"CL-{hash(link) % 100000:05d}",
            'title': title,
            'description': '',
            'price': price,
            'address': location,
            'url': link,
            'posted_date': posted_date,
            'phone': '',
            'email': '',
            'status': 'new',
            'notes': ''
        }

    def scrape_craigslist_detail(self, url: str) -> Dict:
        """
        Scrape details from a single Craigslist listing page.
        Gets phone numbers, email, full description.
        """
        details = {'description': '', 'phone': '', 'email': ''}

        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Get description
            body = soup.select_one('#postingbody')
            if body:
                # Remove the "QR Code" link text if present
                for qr in body.select('.print-qrcode-label'):
                    qr.decompose()
                details['description'] = body.get_text(strip=True)

            # Look for phone numbers in the text
            text = soup.get_text()
            phones = re.findall(r'[\(]?\d{3}[\)\-\.\s]?\d{3}[\-\.\s]?\d{4}', text)
            if phones:
                details['phone'] = phones[0]

            # Look for email
            emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', text)
            if emails:
                # Filter out craigslist relay emails
                real_emails = [e for e in emails if 'craigslist' not in e.lower()]
                if real_emails:
                    details['email'] = real_emails[0]

        except Exception as e:
            self.logger.error(f"Error scraping detail page: {e}")

        return details

    def scrape_facebook_marketplace_manual(self) -> str:
        """
        Facebook Marketplace requires login and has anti-scraping measures.
        This returns instructions for manual monitoring.
        """
        instructions = """
        FACEBOOK MARKETPLACE - Manual Monitoring Guide

        Facebook blocks automated scraping. Here's how to manually find leads:

        1. Go to: https://www.facebook.com/marketplace/columbus/propertyrentals
           (Change 'columbus' to your target city)

        2. Filter by:
           - Category: Property For Sale
           - Sort by: Newest First

        3. Search terms to try:
           - "selling house"
           - "must sell"
           - "motivated seller"
           - "as is"
           - "cash only"
           - "inherited"
           - "estate sale"

        4. When you find a listing:
           - Copy the details into the dashboard
           - Or use the 'Add Manual Lead' feature

        TIP: Set up Facebook notifications for new listings in your area.
        """
        return instructions

    def add_manual_lead(
        self,
        source: str,
        title: str,
        address: str,
        price: str = '',
        phone: str = '',
        email: str = '',
        url: str = '',
        description: str = '',
        notes: str = ''
    ) -> str:
        """
        Add a manually found lead (from Facebook, driving for dollars, etc.)

        Returns:
            Lead ID
        """
        lead_id = f"MANUAL-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        lead = {
            'id': lead_id,
            'source': source,
            'title': title,
            'description': description,
            'price': price,
            'address': address,
            'city': '',
            'state': 'OH',
            'phone': phone,
            'email': email,
            'url': url,
            'posted_date': datetime.now().strftime('%Y-%m-%d'),
            'scraped_at': datetime.now().isoformat(),
            'status': 'new',
            'notes': notes
        }

        # Append to file
        df = pd.read_csv(self.leads_file)
        df = pd.concat([df, pd.DataFrame([lead])], ignore_index=True)
        df.to_csv(self.leads_file, index=False)

        self.logger.info(f"Added manual lead: {lead_id}")
        return lead_id

    def save_leads(self, leads: List[Dict]) -> int:
        """
        Save scraped leads to file, avoiding duplicates.

        Returns:
            Number of new leads saved
        """
        if not leads:
            return 0

        df = pd.read_csv(self.leads_file)
        existing_urls = set(df['url'].dropna().tolist())

        new_leads = []
        for lead in leads:
            if lead.get('url') not in existing_urls:
                lead['scraped_at'] = datetime.now().isoformat()
                new_leads.append(lead)
                existing_urls.add(lead.get('url'))

        if new_leads:
            df = pd.concat([df, pd.DataFrame(new_leads)], ignore_index=True)
            df.to_csv(self.leads_file, index=False)
            self.logger.info(f"Saved {len(new_leads)} new leads")

        return len(new_leads)

    def get_all_leads(self, status: str = None) -> pd.DataFrame:
        """Get all reverse targeting leads, optionally filtered by status."""
        df = pd.read_csv(self.leads_file)

        if status and not df.empty:
            df = df[df['status'] == status]

        return df.sort_values('scraped_at', ascending=False) if not df.empty else df

    def get_new_leads(self) -> pd.DataFrame:
        """Get leads that haven't been contacted yet."""
        return self.get_all_leads(status='new')

    def update_lead_status(self, lead_id: str, status: str, notes: str = ''):
        """Update a lead's status (new, contacted, interested, closed, dead)."""
        df = pd.read_csv(self.leads_file)

        idx = df[df['id'] == lead_id].index
        if len(idx) > 0:
            df.at[idx[0], 'status'] = status
            if notes:
                existing = df.at[idx[0], 'notes'] or ''
                df.at[idx[0], 'notes'] = f"{existing}\n{datetime.now().strftime('%m/%d')}: {notes}".strip()

            df.to_csv(self.leads_file, index=False)
            self.logger.info(f"Updated lead {lead_id} to status: {status}")

    def enrich_leads(self, limit: int = 10):
        """
        Enrich leads by scraping detail pages for phone/email.
        Only processes leads without phone numbers.
        """
        df = pd.read_csv(self.leads_file)

        # Find leads needing enrichment
        needs_enrichment = df[
            (df['phone'].isna() | (df['phone'] == '')) &
            (df['url'].notna()) &
            (df['source'] == 'craigslist')
        ].head(limit)

        self.logger.info(f"Enriching {len(needs_enrichment)} leads...")

        for idx, row in needs_enrichment.iterrows():
            details = self.scrape_craigslist_detail(row['url'])

            if details['phone']:
                df.at[idx, 'phone'] = details['phone']
            if details['email']:
                df.at[idx, 'email'] = details['email']
            if details['description']:
                df.at[idx, 'description'] = details['description'][:500]  # Limit length

            time.sleep(2)  # Be nice

        df.to_csv(self.leads_file, index=False)
        self.logger.info("Enrichment complete")

    def get_stats(self) -> Dict:
        """Get statistics about reverse targeting leads."""
        df = pd.read_csv(self.leads_file)

        if df.empty:
            return {
                'total': 0,
                'new': 0,
                'contacted': 0,
                'with_phone': 0,
                'by_source': {}
            }

        return {
            'total': len(df),
            'new': len(df[df['status'] == 'new']),
            'contacted': len(df[df['status'] == 'contacted']),
            'with_phone': len(df[df['phone'].notna() & (df['phone'] != '')]),
            'by_source': df['source'].value_counts().to_dict()
        }


# CLI for testing
if __name__ == '__main__':
    scraper = ReverseTargetingScraper()

    print("Scraping Craigslist Columbus...")
    leads = scraper.scrape_craigslist('columbus', 'ohio', max_pages=2)

    saved = scraper.save_leads(leads)
    print(f"Saved {saved} new leads")

    print("\nEnriching leads with contact info...")
    scraper.enrich_leads(limit=5)

    print("\nStats:")
    print(scraper.get_stats())
