"""
Google Street View Integration

Generates Street View image URLs for properties.
"""

import urllib.parse
from typing import Optional, Tuple
import pandas as pd

try:
    from shared.config.logging_config import get_logger
    logger = get_logger("StreetView")
except ImportError:
    import logging
    logger = logging.getLogger("StreetView")


class StreetViewHelper:
    """
    Helper class for generating Google Street View URLs.

    Street View Static API provides images of locations.
    Free tier: 28,000 image loads per month with API key
    Without API key: Uses embed URL (may have limits)
    """

    # Base URLs
    STATIC_API_URL = "https://maps.googleapis.com/maps/api/streetview"
    EMBED_URL = "https://www.google.com/maps/embed/v1/streetview"
    MAPS_URL = "https://www.google.com/maps"

    # Default image parameters
    DEFAULT_SIZE = (600, 400)
    DEFAULT_HEADING = 0  # 0 = north
    DEFAULT_PITCH = 0    # 0 = horizontal
    DEFAULT_FOV = 90     # Field of view

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Street View helper.

        Args:
            api_key: Google Maps API key (optional, enables higher quality/limits)
        """
        self.api_key = api_key

    def format_address(self, address: str, city: str = "", state: str = "", zip_code: str = "") -> str:
        """
        Format address for geocoding.

        Args:
            address: Street address
            city: City name
            state: State code
            zip_code: ZIP code

        Returns:
            Formatted address string
        """
        parts = [address]
        if city:
            parts.append(city)
        if state:
            parts.append(state)
        if zip_code:
            parts.append(str(zip_code))

        return ", ".join(filter(None, parts))

    def get_static_image_url(
        self,
        address: str,
        city: str = "Columbus",
        state: str = "OH",
        zip_code: str = "",
        size: Tuple[int, int] = None,
        heading: int = None,
        pitch: int = None,
        fov: int = None
    ) -> str:
        """
        Get Street View Static API URL for an address.

        Args:
            address: Street address
            city: City name
            state: State code
            zip_code: ZIP code
            size: Image size (width, height)
            heading: Camera heading (0-360)
            pitch: Camera pitch (-90 to 90)
            fov: Field of view (10-120)

        Returns:
            Street View Static API URL
        """
        if not self.api_key:
            # Fall back to maps URL without API key
            return self.get_maps_url(address, city, state, zip_code)

        size = size or self.DEFAULT_SIZE
        heading = heading if heading is not None else self.DEFAULT_HEADING
        pitch = pitch if pitch is not None else self.DEFAULT_PITCH
        fov = fov or self.DEFAULT_FOV

        full_address = self.format_address(address, city, state, zip_code)

        params = {
            'size': f'{size[0]}x{size[1]}',
            'location': full_address,
            'heading': heading,
            'pitch': pitch,
            'fov': fov,
            'key': self.api_key
        }

        return f"{self.STATIC_API_URL}?{urllib.parse.urlencode(params)}"

    def get_maps_url(
        self,
        address: str,
        city: str = "Columbus",
        state: str = "OH",
        zip_code: str = ""
    ) -> str:
        """
        Get Google Maps URL for an address (opens in browser).

        Args:
            address: Street address
            city: City name
            state: State code
            zip_code: ZIP code

        Returns:
            Google Maps URL
        """
        full_address = self.format_address(address, city, state, zip_code)

        params = {
            'api': 1,
            'map_action': 'pano',
            'viewpoint': full_address,
        }

        return f"{self.MAPS_URL}/@?{urllib.parse.urlencode(params)}"

    def get_street_view_link(
        self,
        address: str,
        city: str = "Columbus",
        state: str = "OH",
        zip_code: str = ""
    ) -> str:
        """
        Get direct Street View link for an address.

        Args:
            address: Street address
            city: City name
            state: State code
            zip_code: ZIP code

        Returns:
            Street View URL
        """
        full_address = self.format_address(address, city, state, zip_code)
        encoded = urllib.parse.quote(full_address)

        # Use the search URL which then allows clicking into Street View
        return f"https://www.google.com/maps/search/{encoded}"

    def get_thumbnail_url(
        self,
        address: str,
        city: str = "Columbus",
        state: str = "OH",
        zip_code: str = ""
    ) -> str:
        """
        Get a thumbnail placeholder URL.

        Without API key, returns a placeholder or maps link.

        Args:
            address: Street address
            city: City name
            state: State code
            zip_code: ZIP code

        Returns:
            Thumbnail URL or maps link
        """
        if self.api_key:
            return self.get_static_image_url(
                address, city, state, zip_code,
                size=(200, 150)
            )
        else:
            # Return maps link as fallback
            return self.get_street_view_link(address, city, state, zip_code)

    def add_street_view_columns(
        self,
        df: pd.DataFrame,
        address_col: str = 'address',
        city: str = "Columbus",
        state: str = "OH",
        zip_col: str = 'zip_code'
    ) -> pd.DataFrame:
        """
        Add Street View URL columns to DataFrame.

        Args:
            df: DataFrame with address column
            address_col: Name of address column
            city: Default city
            state: Default state
            zip_col: Name of ZIP code column

        Returns:
            DataFrame with street_view_url column added
        """
        df = df.copy()

        urls = []
        for idx, row in df.iterrows():
            address = str(row.get(address_col, ''))
            zip_code = str(row.get(zip_col, '')) if zip_col in df.columns else ''

            url = self.get_street_view_link(address, city, state, zip_code)
            urls.append(url)

        df['street_view_url'] = urls

        logger.info(f"Added Street View URLs for {len(df)} properties")

        return df


# ========================================
# CLI Test
# ========================================

if __name__ == '__main__':
    from rich.console import Console

    console = Console()

    console.print("\n[bold cyan]Street View Helper Test[/bold cyan]\n")

    helper = StreetViewHelper()

    # Test addresses
    test_addresses = [
        "355 WHEATLAND AV",
        "123 MAIN ST",
        "785 787 PARK ST",
    ]

    for address in test_addresses:
        url = helper.get_street_view_link(address, "Columbus", "OH")
        console.print(f"[cyan]{address}[/cyan]")
        console.print(f"  [dim]{url}[/dim]\n")

    # Test with API key (placeholder)
    console.print("[yellow]Note: For higher quality images, set GOOGLE_MAPS_API_KEY[/yellow]")
