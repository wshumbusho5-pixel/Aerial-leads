"""
Aerial Leads - Franklin County Probate Court Scraper

Scrapes probate/estate cases from Franklin County Probate Court.
Identifies properties likely to be inherited and sold.

Data Source: https://probate.franklincountyohio.gov/record-search/general-case-index

Uses Selenium for browser automation to handle ASP.NET forms.
"""

import re
import time
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import pandas as pd

from sellers.scrapers.base_scraper import BaseScraper

# Selenium imports
try:
    from selenium import webdriver
    from selenium.webdriver.firefox.service import Service
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait, Select
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.firefox import GeckoDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False


class ProbateScraper(BaseScraper):
    """
    Scraper for Franklin County Probate Court records.

    Targets estate administration cases which often involve
    real property that heirs want to liquidate quickly.

    Uses Selenium to handle ASP.NET form submissions.
    """

    BASE_URL = "https://probate.franklincountyohio.gov"
    SEARCH_URL = f"{BASE_URL}/record-search/general-case-index"

    # Case types that typically involve real estate
    ESTATE_CASE_TYPES = [
        'EST',      # Estate Administration
        'REL',      # Release from Administration
        'SUM',      # Summary Release
    ]

    def __init__(self, headless: bool = True):
        super().__init__()
        self.cases = []
        self.headless = headless
        self.driver = None

    def _setup_driver(self):
        """Initialize Selenium WebDriver with Firefox."""
        if not SELENIUM_AVAILABLE:
            raise ImportError(
                "Selenium not installed. Run: pip install selenium webdriver-manager"
            )

        if self.driver is not None:
            return  # Already initialized

        self.logger.info("Setting up Firefox WebDriver...")

        firefox_options = Options()
        if self.headless:
            firefox_options.add_argument("--headless")
        firefox_options.add_argument("--width=1920")
        firefox_options.add_argument("--height=1080")

        # Set user agent
        firefox_options.set_preference(
            "general.useragent.override",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0"
        )

        service = Service(GeckoDriverManager().install())
        self.driver = webdriver.Firefox(service=service, options=firefox_options)
        # Don't use implicit wait - use explicit waits instead
        # self.driver.implicitly_wait(10)

        self.logger.info("WebDriver initialized successfully")

    def _close_driver(self):
        """Close the WebDriver."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def scrape(
        self,
        days_back: int = 90,
        case_types: Optional[List[str]] = None,
        max_results: int = 500
    ) -> pd.DataFrame:
        """
        Scrape recent probate/estate cases using Selenium.

        Args:
            days_back: Number of days to look back
            case_types: List of case types to search (default: estate cases)
            max_results: Maximum number of results to return

        Returns:
            DataFrame with probate case data
        """
        self.logger.info(f"Starting probate scrape (last {days_back} days)")

        if not SELENIUM_AVAILABLE:
            self.logger.error("Selenium not available. Install with: pip install selenium webdriver-manager")
            return pd.DataFrame()

        if case_types is None:
            case_types = self.ESTATE_CASE_TYPES

        all_cases = []

        try:
            # Initialize browser
            self._setup_driver()

            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)

            # Search for each case type
            for case_type in case_types:
                self.logger.info(f"Searching case type: {case_type}")

                cases = self._search_cases_selenium(
                    case_type=case_type,
                    start_date=start_date,
                    end_date=end_date,
                    max_results=max_results // len(case_types)
                )

                all_cases.extend(cases)
                self.logger.info(f"Found {len(cases)} {case_type} cases")

        except Exception as e:
            self.logger.error(f"Scraping error: {e}")
        finally:
            self._close_driver()

        # Convert to DataFrame
        df = pd.DataFrame(all_cases)

        if not df.empty:
            # Add metadata
            df['source'] = 'franklin_probate'
            df['scraped_at'] = datetime.now().isoformat()
            df['lead_type'] = 'probate'

            # Deduplicate
            df = df.drop_duplicates(subset=['case_number'], keep='first')

        self.logger.info(f"Total probate cases found: {len(df)}")
        return df

    # Mapping of our case types to the actual form values
    CASE_TYPE_VALUES = {
        'EST': 'E%20',   # Estate Administration
        'E': 'E%20',
        'REL': 'E%20',   # Release - also under Estate
        'SUM': 'E%20',   # Summary - also under Estate
        'TRUST': 'T%20', # Trust
        'T': 'T%20',
        'GA': 'GA',      # Adult Guardianship
        'GM': 'GM',      # Minor Guardianship
    }

    def _search_cases_selenium(
        self,
        case_type: str,
        start_date: datetime,
        end_date: datetime,
        max_results: int = 100
    ) -> List[Dict]:
        """
        Search for cases using Selenium browser automation.

        The probate court search is inside an iframe that redirects to
        a results page on a different subdomain.
        """
        cases = []

        try:
            # Always navigate fresh to search page for each case type
            self.logger.debug(f"Navigating to {self.SEARCH_URL}")
            self.driver.get(self.SEARCH_URL)

            # Wait for page to fully load
            time.sleep(3)

            # Wait for iframe to be present
            try:
                iframe = WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.TAG_NAME, "iframe"))
                )
            except Exception as e:
                self.logger.warning(f"Could not find iframe: {e}")
                return cases

            # Switch to iframe
            self.driver.switch_to.frame(iframe)
            self.logger.debug("Switched to iframe")
            time.sleep(2)

            # Select search method: Case Type/Subtype
            try:
                search_method = Select(self.driver.find_element(By.NAME, "searchMethod"))
                search_method.select_by_value("CaseTypeSubtype")
                time.sleep(1)
            except Exception as e:
                self.logger.warning(f"Could not select search method: {e}")

            # Map our case type to the form value
            form_value = self.CASE_TYPE_VALUES.get(case_type.upper(), 'E%20')

            # Select case type
            try:
                case_type_select = Select(self.driver.find_element(By.NAME, "s_CaseType"))
                case_type_select.select_by_value(form_value)
                self.logger.debug(f"Selected case type value: {form_value}")
            except Exception as e:
                self.logger.debug(f"Could not set case type: {e}")

            # Find and click the submit button (4th one for case type search)
            try:
                submit_buttons = self.driver.find_elements(
                    By.CSS_SELECTOR, "input[type='submit'][value='Submit']"
                )
                self.logger.debug(f"Found {len(submit_buttons)} submit buttons")

                if len(submit_buttons) >= 4:
                    btn = submit_buttons[3]
                else:
                    btn = submit_buttons[0]

                # Use JavaScript click - more reliable for form submissions
                self.driver.execute_script("arguments[0].click();", btn)
                self.logger.debug("Clicked submit button via JavaScript")
            except Exception as e:
                self.logger.warning(f"Could not click submit: {e}")
                return cases

            # Wait a moment for click to register
            time.sleep(1)

            # Switch back to default content IMMEDIATELY after click
            # The form causes full page navigation to probatesearch subdomain
            try:
                self.driver.switch_to.default_content()
                self.logger.debug("Switched back to default content")
            except Exception as e:
                self.logger.debug(f"Already in default content or error: {e}")

            # Wait for page to fully load after navigation
            time.sleep(8)

            # Check if navigation happened
            current_url = self.driver.current_url
            self.logger.info(f"Current URL after submit: {current_url}")

            # Get the results from the main page source
            html = self.driver.page_source
            self.logger.info(f"Got page source: {len(html)} chars")

            # Parse results
            cases = self._parse_search_results(html, max_results)
            self.logger.info(f"Parsed {len(cases)} cases from results")

        except Exception as e:
            self.logger.warning(f"Selenium search error for {case_type}: {e}")
            try:
                self.driver.switch_to.default_content()
            except:
                pass

        return cases

    def _search_cases(
        self,
        case_type: str,
        start_date: datetime,
        end_date: datetime,
        max_results: int = 100
    ) -> List[Dict]:
        """
        Search for cases of a specific type within date range (non-Selenium fallback).

        Note: The probate court website uses ASP.NET postback forms.
        This method attempts to work with the form structure.
        """
        cases = []

        # First, get the search page to extract form tokens
        response = self._make_request(self.SEARCH_URL)

        if not response:
            self.logger.error("Could not access probate search page")
            return cases

        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract ASP.NET form fields
        viewstate = soup.find('input', {'name': '__VIEWSTATE'})
        viewstate_gen = soup.find('input', {'name': '__VIEWSTATEGENERATOR'})
        event_validation = soup.find('input', {'name': '__EVENTVALIDATION'})

        # Build form data for search
        form_data = {
            '__VIEWSTATE': viewstate['value'] if viewstate else '',
            '__VIEWSTATEGENERATOR': viewstate_gen['value'] if viewstate_gen else '',
            '__EVENTVALIDATION': event_validation['value'] if event_validation else '',
            'ctl00$ContentPlaceHolder1$txtCaseType': case_type,
            'ctl00$ContentPlaceHolder1$txtFromDate': start_date.strftime('%m/%d/%Y'),
            'ctl00$ContentPlaceHolder1$txtToDate': end_date.strftime('%m/%d/%Y'),
            'ctl00$ContentPlaceHolder1$btnSearch': 'Search',
        }

        # Submit search
        search_response = self._make_request(
            self.SEARCH_URL,
            method='POST',
            data=form_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )

        if not search_response:
            self.logger.warning(f"Search failed for case type {case_type}")
            return cases

        # Parse results
        cases = self._parse_search_results(search_response.text, max_results)

        return cases

    def _parse_search_results(self, html: str, max_results: int) -> List[Dict]:
        """Parse search results HTML to extract case data."""
        cases = []
        soup = BeautifulSoup(html, 'html.parser')

        # The probate results page has multiple tables
        # We need the one with actual case data rows
        tables = soup.find_all('table')

        for table in tables:
            rows = table.find_all('tr')

            # Skip tables with too few rows
            if len(rows) < 3:
                continue

            # Look for rows with case data
            # Skip rows that contain headers like "Case Number", "Total Records", etc.
            for row in rows:
                cells = row.find_all('td')

                # Need at least 6 cells for case data (number, name, type, subtype, status, date)
                if len(cells) < 6:
                    continue

                # First cell should be a case number (digits)
                first_cell = cells[0].get_text(strip=True)
                if not first_cell or not first_cell[0].isdigit():
                    continue

                case = self._parse_case_row(cells)
                if case and case.get('case_number'):
                    cases.append(case)

                    if len(cases) >= max_results:
                        break

            # If we found cases in this table, we're done
            if cases:
                break

        self.logger.debug(f"Parsed {len(cases)} cases from HTML")
        return cases

    def _parse_case_row(self, cells) -> Optional[Dict]:
        """Parse a single case row from search results.

        Expected column order from Franklin County Probate:
        0: Case Number
        1: Case Name (decedent)
        2: Type (ESTATE, etc.)
        3: SubType (FULL ADMINISTRATION WITH WILL, etc.)
        4: Status
        5: Opened (filing date)
        6: Closed (if applicable)
        """
        try:
            case_number = cells[0].get_text(strip=True)

            # Skip if this doesn't look like a case number
            if not case_number or not any(c.isdigit() for c in case_number):
                return None

            decedent_name = cells[1].get_text(strip=True) if len(cells) > 1 else ''
            case_type = cells[2].get_text(strip=True) if len(cells) > 2 else ''
            sub_type = cells[3].get_text(strip=True) if len(cells) > 3 else ''
            status = cells[4].get_text(strip=True) if len(cells) > 4 else ''
            filing_date = cells[5].get_text(strip=True) if len(cells) > 5 else ''
            closed_date = cells[6].get_text(strip=True) if len(cells) > 6 else ''

            # Extract detail link if available
            detail_link = cells[0].find('a')
            detail_url = detail_link['href'] if detail_link else None

            return {
                'case_number': case_number,
                'decedent_name': decedent_name,
                'case_type': case_type,
                'sub_type': sub_type,
                'status': status,
                'filing_date': filing_date,
                'closed_date': closed_date,
                'detail_url': detail_url,
                'county': 'Franklin',
                'state': 'OH',
            }

        except Exception as e:
            self.logger.debug(f"Error parsing case row: {e}")
            return None

    FIDUCIARY_URL = "http://probatesearch.franklincountyohio.gov/netdata/PBFidy.ndm/input"

    def scrape_executor_info(self, case_number: str) -> Dict:
        """
        Scrape executor/fiduciary info from the case fiduciary page.

        Args:
            case_number: Probate case number (e.g., "010006")

        Returns:
            Dictionary with executor_name and attorney_name
        """
        result = {
            'executor_name': '',
            'attorney_name': '',
        }

        # Clean case number (remove any non-digits)
        clean_case = ''.join(c for c in str(case_number) if c.isdigit())

        url = f"{self.FIDUCIARY_URL}?caseno={clean_case}"

        try:
            response = self._make_request(url)
            if not response:
                return result

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find the data table - look for table with fiduciary headers
            tables = soup.find_all('table')

            for table in tables:
                rows = table.find_all('tr')

                for row in rows:
                    cells = row.find_all('td')

                    # Need at least 4 cells for fiduciary data
                    # Columns: Fid#, Name, Title, TitleDesc, ApptDate, TermDate, CloseDate, AttyNum, AttyName
                    if len(cells) >= 4:
                        # Column 1: Estate Fiduciaries (the name)
                        name = cells[1].get_text(strip=True)

                        # Column 3: Title Description (EXECUTOR, ADMINISTRATOR, APPLICANT, etc.)
                        title = cells[3].get_text(strip=True).upper()

                        # Column 8: Attorney Name (if exists)
                        attorney = cells[8].get_text(strip=True) if len(cells) > 8 else ''

                        # Accept any person handling the estate - EXECUTOR, ADMINISTRATOR, APPLICANT, etc.
                        # These are all people who can make decisions about selling the property
                        valid_roles = ['EXECUTOR', 'ADMINISTRATOR', 'APPLICANT', 'FIDUCIARY', 'TRUSTEE', 'GUARDIAN']

                        # Save the first valid name we find
                        if not result['executor_name'] and name and ',' in name and len(name) < 50:
                            # Either match a known role, or accept any name if no role specified
                            if any(role in title for role in valid_roles) or (name and not title):
                                result['executor_name'] = name

                        # Save attorney if we don't have one
                        if not result['attorney_name'] and attorney and ',' in attorney and len(attorney) < 50:
                            result['attorney_name'] = attorney

        except Exception as e:
            self.logger.debug(f"Error scraping executor for case {case_number}: {e}")

        return result

    def enrich_with_executor_info(
        self,
        probate_df: pd.DataFrame,
        progress_callback=None
    ) -> pd.DataFrame:
        """
        Scrape executor info for all cases in the DataFrame.

        Args:
            probate_df: DataFrame with probate cases (must have case_number column)
            progress_callback: Optional callback(current, total) for progress

        Returns:
            DataFrame with executor_name and attorney_name columns added
        """
        probate_df = probate_df.copy()

        # Initialize columns
        if 'executor_name' not in probate_df.columns:
            probate_df['executor_name'] = ''
        if 'attorney_name' not in probate_df.columns:
            probate_df['attorney_name'] = ''

        total = len(probate_df)
        scraped = 0

        self.logger.info(f"Scraping executor info for {total} cases...")

        for idx, row in probate_df.iterrows():
            case_number = str(row.get('case_number', ''))

            if not case_number:
                continue

            # Skip if already has executor
            if pd.notna(row.get('executor_name')) and str(row.get('executor_name', '')).strip():
                scraped += 1
                if progress_callback:
                    progress_callback(scraped, total)
                continue

            # Scrape executor info
            info = self.scrape_executor_info(case_number)

            if info['executor_name']:
                probate_df.at[idx, 'executor_name'] = info['executor_name']

            if info['attorney_name']:
                probate_df.at[idx, 'attorney_name'] = info['attorney_name']

            scraped += 1
            if progress_callback:
                progress_callback(scraped, total)

            # Small delay to be polite
            time.sleep(0.5)

        found = probate_df['executor_name'].notna().sum()
        self.logger.info(f"Scraped executor info: {found}/{total} found")

        return probate_df

    def get_case_details(self, case_number: str) -> Optional[Dict]:
        """
        Get detailed information for a specific case.

        Args:
            case_number: Probate case number

        Returns:
            Dictionary with case details including property info if available
        """
        # Build detail URL
        detail_url = f"{self.SEARCH_URL}?case={case_number}"

        response = self._make_request(detail_url)

        if not response:
            return None

        soup = BeautifulSoup(response.text, 'html.parser')

        details = {
            'case_number': case_number,
            'decedent_name': '',
            'executor_name': '',
            'executor_address': '',
            'attorney_name': '',
            'filing_date': '',
            'assets_value': 0,
            'real_property': False,
            'property_address': '',
        }

        # Parse detail fields
        for row in soup.find_all('tr'):
            label_cell = row.find('td', class_=re.compile(r'label', re.I))
            value_cell = row.find('td', class_=re.compile(r'value', re.I))

            if label_cell and value_cell:
                label = label_cell.get_text(strip=True).lower()
                value = value_cell.get_text(strip=True)

                if 'decedent' in label:
                    details['decedent_name'] = value
                elif 'executor' in label or 'administrator' in label:
                    details['executor_name'] = value
                elif 'attorney' in label:
                    details['attorney_name'] = value
                elif 'filing date' in label:
                    details['filing_date'] = value
                elif 'real property' in label or 'real estate' in label:
                    details['real_property'] = True
                    details['property_address'] = value
                elif 'assets' in label or 'value' in label:
                    details['assets_value'] = self._parse_currency(value)

        return details

    def enrich_with_property_data(
        self,
        probate_df: pd.DataFrame,
        property_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Match probate cases with property records.

        Args:
            probate_df: DataFrame of probate cases
            property_df: DataFrame of property records (from tax data)

        Returns:
            Merged DataFrame with matched properties
        """
        if probate_df.empty or property_df.empty:
            return probate_df

        self.logger.info("Matching probate cases with property records...")

        # Normalize names for matching
        probate_df['decedent_name_normalized'] = probate_df['decedent_name'].str.upper().str.strip()
        property_df['owner_name_normalized'] = property_df['owner_name'].str.upper().str.strip()

        # Merge on normalized name
        merged = probate_df.merge(
            property_df,
            left_on='decedent_name_normalized',
            right_on='owner_name_normalized',
            how='left',
            suffixes=('', '_property')
        )

        # Count matches
        matches = merged['owner_name_normalized'].notna().sum()
        self.logger.info(f"Matched {matches} probate cases with property records")

        return merged


# Example usage and testing
if __name__ == '__main__':
    from rich.console import Console
    from rich.table import Table

    console = Console()

    console.print("\n[bold cyan]Probate Scraper Test[/bold cyan]\n")

    # Test with headless browser
    scraper = ProbateScraper(headless=True)

    # Test with all estate case types
    df = scraper.scrape(days_back=90, max_results=100)

    if not df.empty:
        table = Table(title=f"Probate Cases Found: {len(df)}")
        table.add_column("Case #", style="cyan")
        table.add_column("Type", style="yellow")
        table.add_column("Decedent", style="green")
        table.add_column("Filing Date", style="white")

        for _, row in df.head(10).iterrows():
            table.add_row(
                str(row.get('case_number', '')),
                str(row.get('case_type', '')),
                str(row.get('decedent_name', '')),
                str(row.get('filing_date', ''))
            )

        console.print(table)
    else:
        console.print("[yellow]No probate cases found[/yellow]")

    # Print stats
    stats = scraper.get_stats()
    console.print(f"\n[dim]Stats: {stats}[/dim]")
