"""
Property Lookup Utility

Looks up property details (square footage, year built, etc.) from Zillow.
Uses non-headless Chrome to avoid bot detection.
"""

import re
from typing import Dict, Optional
import time
import random


# Simple cache to avoid repeated lookups
_lookup_cache = {}


class PropertyLookup:
    """
    Look up property details using Chrome browser
    """

    def __init__(self):
        self.driver = None

    def _get_driver(self):
        """Get or create Chrome WebDriver"""
        if self.driver is None:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options

            options = Options()
            # Use non-headless to avoid detection - window will appear briefly
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--window-position=-2000,-2000')  # Position off-screen
            options.add_argument('user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36')
            options.add_experimental_option('excludeSwitches', ['enable-automation'])
            options.add_experimental_option('useAutomationExtension', False)

            self.driver = webdriver.Chrome(options=options)

            # Hide automation indicators
            self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                '''
            })

            # Minimize window immediately
            try:
                self.driver.minimize_window()
            except:
                pass

        return self.driver

    def close(self):
        """Close the browser"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None

    def lookup_by_address(self, address: str) -> Optional[Dict]:
        """
        Look up property details by street address

        Args:
            address: Full address (e.g., "123 Main St, Columbus, OH 43201")

        Returns:
            Dict with property details or None if not found
        """
        # Check cache first
        cache_key = address.lower().strip()
        if cache_key in _lookup_cache:
            cached = _lookup_cache[cache_key]
            if cached and cached.get('square_feet'):
                return cached

        result = None

        # Try Zillow lookup
        try:
            result = self._lookup_zillow(address)
        except Exception as e:
            print(f"Zillow lookup failed: {e}")

        # Cache the result
        if result and result.get('square_feet'):
            _lookup_cache[cache_key] = result

        return result

    def _lookup_zillow(self, address: str) -> Optional[Dict]:
        """Look up property from Zillow"""
        try:
            driver = self._get_driver()

            # Format address for Zillow URL
            addr_formatted = address.replace(',', '').replace(' ', '-')
            url = f'https://www.zillow.com/homes/{addr_formatted}_rb/'

            driver.get(url)
            time.sleep(4)  # Wait for page to load

            page_text = driver.page_source

            # Extract details (works even with captcha overlay)
            return self._extract_property_details(page_text, address, 'Zillow')

        except Exception as e:
            print(f"Zillow error: {e}")
            return None

    def _extract_property_details(self, page_text: str, address: str, source: str) -> Optional[Dict]:
        """Extract property details from page HTML"""
        details = {'address': address, 'source': source}

        # Square footage patterns
        sqft_patterns = [
            r'([0-9,]+)\s*(?:sqft|sq\s*ft|square feet)',
            r'"livingArea"\s*:\s*(\d+)',
            r'Living Area[:\s]*([0-9,]+)',
        ]

        for pattern in sqft_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                sqft_str = match.group(1).replace(',', '')
                if sqft_str.isdigit() and 100 < int(sqft_str) < 20000:
                    details['square_feet'] = int(sqft_str)
                    break

        # Bedrooms
        bed_patterns = [
            r'(\d+)\s*(?:bd|bed|bedroom)',
            r'"bedrooms"\s*:\s*(\d+)',
        ]

        for pattern in bed_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                beds = int(match.group(1))
                if 0 < beds < 20:
                    details['bedrooms'] = beds
                    break

        # Bathrooms
        bath_patterns = [
            r'([\d.]+)\s*(?:ba|bath)',
            r'"bathrooms"\s*:\s*([\d.]+)',
        ]

        for pattern in bath_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                baths = float(match.group(1))
                if 0 < baths < 20:
                    details['bathrooms'] = baths
                    break

        # Year built
        year_patterns = [
            r'(?:built|year built)[:\s]*(\d{4})',
            r'"yearBuilt"\s*:\s*(\d{4})',
        ]

        for pattern in year_patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                year = int(match.group(1))
                if 1800 < year < 2030:
                    details['year_built'] = year
                    break

        # Only return if we found square footage
        if 'square_feet' in details:
            return details

        return None


def lookup_property_sqft(address: str) -> Optional[int]:
    """
    Quick helper to just get square footage for an address
    """
    lookup = PropertyLookup()
    try:
        result = lookup.lookup_by_address(address)
        if result and 'square_feet' in result:
            return result['square_feet']
        return None
    finally:
        lookup.close()


# Test
if __name__ == '__main__':
    address = "1381 HAMLET ST, Columbus, OH 43201"
    print(f"Testing: {address}")

    lookup = PropertyLookup()
    try:
        result = lookup.lookup_by_address(address)
        if result:
            print(f"Found: {result}")
        else:
            print("Not found")
    finally:
        lookup.close()
