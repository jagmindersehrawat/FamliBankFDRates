"""Rate extraction component for FD rates from bank websites."""

import re
import logging
from datetime import datetime
from typing import List, Optional, Dict, Tuple, Set
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup, Tag
import time

from ..core.models import FDRateData, RateEntry
from ..config import Config


logger = logging.getLogger(__name__)


class RateExtractor:
    """Extracts FD rate data from bank websites."""
    
    def __init__(self, config: Config):
        """Initialize the rate extractor with configuration."""
        self.config = config
        self.session = requests.Session()
        self.session.headers.update(config.scraping.headers)
        
        # Common patterns for identifying rate tables
        self.rate_table_indicators = [
            'fd', 'fixed deposit', 'deposit', 'rate', 'interest',
            'tenure', 'maturity', 'term', 'senior citizen'
        ]
        
        # Patterns for extracting tenure information
        self.tenure_patterns = [
            r'(\d+)\s*(?:year|yr|y)s?',
            r'(\d+)\s*(?:month|mon|m)s?',
            r'(\d+)\s*(?:day|d)s?',
            r'(\d+)\s*to\s*(\d+)\s*(?:year|yr|y)s?',
            r'(\d+)\s*to\s*(\d+)\s*(?:month|mon|m)s?'
        ]
        
        # Patterns for extracting rate information
        self.rate_patterns = [
            r'(\d+\.?\d*)\s*%',
            r'(\d+\.?\d*)\s*percent',
            r'(\d+\.?\d*)\s*p\.?a\.?'
        ]
    
    def extract_rates(self, url: str) -> FDRateData:
        """
        Extract FD rate data from the given URL with retry logic and alternative strategies.
        
        Args:
            url: The URL to extract rates from
            
        Returns:
            FDRateData object containing extracted rates or error information
        """
        logger.info(f"Starting rate extraction from: {url}")
        
        # Store current URL for bank-specific handlers
        self._current_url = url
        
        # Initialize result object
        result = FDRateData(
            bank_name=self._extract_bank_name_from_url(url),
            source_url=url,
            extraction_timestamp=datetime.now(),
            extraction_success=False
        )
        
        # Special handling for ICICI bank - use JSON API instead of HTML parsing
        if self._is_icici_bank(url):
            logger.info("ICICI bank detected - using JSON API parser")
            try:
                rates = self._parse_icici_json()
                if rates:
                    result.rates = rates
                    result.extraction_success = True
                    logger.info(f"Successfully extracted {len(result.rates)} rate entries from ICICI JSON API")
                    return result
                else:
                    result.error_message = "No rates found in ICICI JSON API"
                    return result
            except Exception as e:
                logger.error(f"Error extracting ICICI rates from JSON: {str(e)}")
                result.error_message = f"ICICI JSON extraction error: {str(e)}"
                return result
        
        # Special handling for Axis bank - PDF file
        if self._is_axis_bank(url) and url.lower().endswith('.pdf'):
            logger.info("Axis bank PDF detected - using PDF parser")
            try:
                rates = self._parse_axis_bank_pdf(url)
                if rates:
                    result.rates = rates
                    result.extraction_success = True
                    logger.info(f"Successfully extracted {len(result.rates)} rate entries from Axis Bank PDF")
                    return result
                else:
                    result.error_message = "No rates found in Axis Bank PDF"
                    return result
            except Exception as e:
                logger.error(f"Error extracting Axis Bank rates from PDF: {str(e)}")
                result.error_message = f"Axis Bank PDF extraction error: {str(e)}"
                return result
        
        # Try extraction with retry logic and exponential backoff
        for attempt in range(self.config.scraping.max_retries):
            try:
                # Fetch the webpage content
                html_content = self._fetch_webpage_with_retry(url, attempt)
                if not html_content:
                    if attempt == self.config.scraping.max_retries - 1:
                        result.error_message = "Failed to fetch webpage content after all retries"
                    continue
                
                # Try different parsing strategies
                success = self._try_parsing_strategies(html_content, result)
                
                if success:
                    result.extraction_success = True
                    logger.info(f"Successfully extracted {len(result.rates)} rate entries from {url}")
                    break
                elif attempt == self.config.scraping.max_retries - 1:
                    result.error_message = "All parsing strategies failed"
                    
            except Exception as e:
                logger.error(f"Error extracting rates from {url} (attempt {attempt + 1}): {str(e)}")
                if attempt == self.config.scraping.max_retries - 1:
                    result.error_message = f"Extraction error: {str(e)}"
                else:
                    # Wait before retry with exponential backoff
                    wait_time = self.config.scraping.backoff_factor ** attempt
                    wait_time = min(wait_time, self.config.scraping.max_backoff_delay)
                    logger.info(f"Waiting {wait_time} seconds before retry...")
                    time.sleep(wait_time)
        
        return result
    
    def _is_sbi_bank(self, url: str) -> bool:
        """Check if the URL is for SBI bank."""
        return 'sbi.bank.in' in url.lower() or 'sbi.co.in' in url.lower()
    
    def _is_icici_bank(self, url: str) -> bool:
        """Check if the URL is for ICICI bank."""
        return 'icici.bank.in' in url.lower() or 'icicibank.com' in url.lower()
    
    def _is_central_bank(self, url: str) -> bool:
        """Check if the URL is for Central Bank of India."""
        return 'centralbank.bank.in' in url.lower() or 'centralbankofindia.co.in' in url.lower()
    
    def _is_federal_bank(self, url: str) -> bool:
        """Check if the URL is for Federal Bank."""
        return 'federal.bank.in' in url.lower() or 'federalbank.co.in' in url.lower()
    
    def _is_pnb_bank(self, url: str) -> bool:
        """Check if the URL is for Punjab National Bank."""
        return 'pnb.bank.in' in url.lower() or 'pnbindia.in' in url.lower()
    
    def _is_uco_bank(self, url: str) -> bool:
        """Check if the URL is for UCO Bank."""
        return 'uco.bank.in' in url.lower() or 'ucobank.com' in url.lower()
    
    def _is_hdfc_bank(self, url: str) -> bool:
        """Check if the URL is for HDFC Bank."""
        return 'hdfc.bank.in' in url.lower() or 'hdfcbank.com' in url.lower()
    
    def _is_bank_of_maharashtra(self, url: str) -> bool:
        """Check if the URL is for Bank of Maharashtra."""
        return 'bankofmaharashtra.bank.in' in url.lower() or 'mahabank.co.in' in url.lower()
    
    def _is_bank_of_baroda(self, url: str) -> bool:
        """Check if the URL is for Bank of Baroda."""
        return 'bankofbaroda.bank.in' in url.lower() or 'bankofbaroda.in' in url.lower()
    
    def _is_canara_bank(self, url: str) -> bool:
        """Check if the URL is for Canara Bank."""
        return 'canarabank.bank.in' in url.lower() or 'canarabank.com' in url.lower()
    
    def _is_axis_bank(self, url: str) -> bool:
        """Check if the URL is for Axis Bank."""
        return 'axis.bank.in' in url.lower() or 'axisbank.com' in url.lower()
    
    def _is_au_small_finance_bank(self, url: str) -> bool:
        """Check if the URL is for AU Small Finance Bank."""
        return 'au.bank.in' in url.lower() or 'aubank.in' in url.lower()
    
    def _is_union_bank(self, url: str) -> bool:
        """Check if the URL is for Union Bank of India."""
        return 'unionbankofindia.bank.in' in url.lower() or 'unionbankofindia.co.in' in url.lower()
    
    def _is_shivalik_bank(self, url: str) -> bool:
        """Check if the URL is for Shivalik Bank."""
        return 'shivalik.bank.in' in url.lower() or 'shivalikbank.com' in url.lower()
    def _is_federal_bank(self, url: str) -> bool:
        """Check if the URL is for Federal Bank."""
        return 'federal.bank.in' in url.lower() or 'federalbank.co.in' in url.lower()

    def _is_shivalik_bank(self, url: str) -> bool:
        """Check if the URL is for Shivalik Bank."""
        return 'shivalik.bank.in' in url.lower() or 'shivalikbank.com' in url.lower()
    
    def _is_indusind_bank(self, url: str) -> bool:
        """Check if the URL is for IndusInd Bank."""
        return 'indusind.bank.in' in url.lower() or 'indusindbank.com' in url.lower()
    
    def _is_idfc_first_bank(self, url: str) -> bool:
        """Check if the URL is for IDFC FIRST Bank."""
        return 'idfcfirst' in url.lower() or 'idfcfirstbank' in url.lower()
    
    def _parse_sbi_table(self, table: Tag) -> List[RateEntry]:
        """
        Special parser for SBI bank tables with multiple rate columns.
        SBI tables have: Tenors, Existing Rates (Public), Revised Rates (Public), 
        Existing Rates (Senior), Revised Rates (Senior)
        We want columns 3 and 5 (Revised rates).
        
        Args:
            table: HTML table element
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            rows = table.find_all('tr')
            if len(rows) < 2:
                return rates
            
            # Get header row to identify columns
            header_row = rows[0]
            header_cells = header_row.find_all(['th', 'td'])
            
            # Find column indices for revised rates
            tenure_col = 0  # First column is always tenure
            revised_public_col = None
            revised_senior_col = None
            
            for i, cell in enumerate(header_cells):
                cell_text = cell.get_text().lower().strip()
                # Look for "revised" rates for public (column 3)
                if 'revised' in cell_text and 'public' in cell_text and 'senior' not in cell_text:
                    revised_public_col = i
                    logger.info(f"SBI: Found revised public rates in column {i}")
                # Look for "revised" rates for senior citizen (column 5)
                elif 'revised' in cell_text and 'senior' in cell_text:
                    revised_senior_col = i
                    logger.info(f"SBI: Found revised senior rates in column {i}")
            
            # If we didn't find "revised" columns, fall back to columns 2 and 4 (indices 2 and 4)
            if revised_public_col is None:
                # Try to find any public rate column (not senior)
                for i, cell in enumerate(header_cells):
                    cell_text = cell.get_text().lower().strip()
                    if any(word in cell_text for word in ['rate', 'public', '%']) and 'senior' not in cell_text and i > 0:
                        if revised_public_col is None or 'revised' in cell_text or 'w.e.f' in cell_text:
                            revised_public_col = i
            
            if revised_senior_col is None:
                # Try to find any senior rate column
                for i, cell in enumerate(header_cells):
                    cell_text = cell.get_text().lower().strip()
                    if 'senior' in cell_text and any(word in cell_text for word in ['rate', '%']) and i > 0:
                        if revised_senior_col is None or 'revised' in cell_text or 'w.e.f' in cell_text:
                            revised_senior_col = i
            
            logger.info(f"SBI: Using columns - Tenure: {tenure_col}, Public: {revised_public_col}, Senior: {revised_senior_col}")
            
            # Process data rows
            for row in rows[1:]:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:
                    continue
                
                try:
                    # Extract tenure
                    tenure = cells[tenure_col].get_text().strip()
                    if not tenure:
                        continue
                    
                    # Extract revised public rate
                    general_rate = None
                    if revised_public_col is not None and revised_public_col < len(cells):
                        rate_text = cells[revised_public_col].get_text().strip()
                        rate_text = re.sub(r'[^\d.]', '', rate_text)  # Remove non-numeric chars
                        if rate_text:
                            general_rate = float(rate_text)
                    
                    if general_rate is None:
                        continue
                    
                    # Extract revised senior rate
                    senior_rate = None
                    if revised_senior_col is not None and revised_senior_col < len(cells):
                        rate_text = cells[revised_senior_col].get_text().strip()
                        rate_text = re.sub(r'[^\d.]', '', rate_text)  # Remove non-numeric chars and asterisks
                        if rate_text:
                            senior_rate = float(rate_text)
                    
                    # Create rate entry
                    rate_entry = RateEntry(
                        tenure=tenure,
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate
                    )
                    rates.append(rate_entry)
                    logger.debug(f"SBI: Extracted {tenure}: {general_rate}% / {senior_rate}%")
                    
                except Exception as e:
                    logger.warning(f"SBI: Error extracting rate from row: {str(e)}")
                    continue
        
        except Exception as e:
            logger.error(f"SBI: Error parsing table: {str(e)}")
        
        return rates
    
    def _parse_icici_json(self) -> List[RateEntry]:
            """
            Special parser for ICICI bank - fetches rates from JSON API.
            ICICI rates are available via JSON API, not HTML tables.

            Returns:
                List of RateEntry objects
            """
            rates = []

            try:
                json_url = "https://www.icici.bank.in/content/dam/icicibank-revamp/deposits/fixed-deposits/json/fd-interest-rate.json"

                logger.info(f"ICICI: Fetching rates from JSON API: {json_url}")

                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                }

                response = requests.get(json_url, timeout=30, headers=headers)

                if response.status_code != 200:
                    logger.error(f"ICICI: Failed to fetch JSON: {response.status_code}")
                    return rates

                data = response.json()

                # Extract rates from the first array (standard rates for deposits < 5 Cr)
                # interestData[0] contains the standard rates
                # c1 = General/Regular rate
                # c2 = Senior Citizen rate

                if 'interestData' in data and len(data['interestData']) > 0:
                    rate_data = data['interestData'][0]  # First array has standard rates

                    logger.info(f"ICICI: Found {len(rate_data)} rate entries in JSON")

                    for item in rate_data:
                        tenure = item.get('tenure')
                        general_rate = item.get('c1')  # Column 1: General rate
                        senior_rate = item.get('c2')   # Column 2: Senior citizen rate

                        if tenure and general_rate is not None:
                            try:
                                # Convert to float if they're strings
                                general_rate_float = float(general_rate)
                                senior_rate_float = float(senior_rate) if senior_rate is not None else None

                                rate_entry = RateEntry(
                                    tenure=tenure,
                                    general_rate=general_rate_float,
                                    senior_citizen_rate=senior_rate_float
                                )
                                rates.append(rate_entry)
                                logger.debug(f"ICICI: Extracted {tenure}: {general_rate_float}% / {senior_rate_float}%")
                            except (ValueError, TypeError) as e:
                                logger.warning(f"ICICI: Error converting rate values for {tenure}: {str(e)}")
                                continue
                else:
                    logger.warning("ICICI: No interestData found in JSON response")

            except Exception as e:
                logger.error(f"ICICI: Error fetching/parsing JSON: {str(e)}")

            return rates

    def _parse_axis_bank_pdf(self, url: str) -> List[RateEntry]:
        """
        Special parser for Axis Bank - extracts rates from PDF file.
        Axis Bank provides rates in a PDF with a table structure:
        - Column 0: Maturity Period
        - Column 1: General (Less than ₹ 3 Cr) - **We want this**
        - Column 2: General (₹ 3 Cr to less than ₹ 5 Cr)
        - Column 3: Senior Citizens (Less than ₹ 3 Cr) - **We want this**
        - Column 4: Senior Citizens (₹ 3 Cr to less than ₹ 5 Cr)
        
        Args:
            url: URL to the PDF file
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            import io
            import PyPDF2
            
            logger.info(f"Axis Bank: Downloading PDF from {url}")
            
            # Download PDF
            response = self.session.get(url, timeout=30)
            if response.status_code != 200:
                logger.error(f"Axis Bank: Failed to download PDF: {response.status_code}")
                return rates
            
            # Parse PDF
            pdf_file = io.BytesIO(response.content)
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            logger.info(f"Axis Bank: PDF has {len(pdf_reader.pages)} pages")
            
            # Extract text from first page (rates are in first table)
            first_page = pdf_reader.pages[0]
            text = first_page.extract_text()
            
            # Parse the text to extract table data
            lines = text.split('\n')
            
            # Find the table start (after "Maturity Period")
            table_start = -1
            for i, line in enumerate(lines):
                if 'Maturity Period' in line and 'Interest Rates' in line:
                    table_start = i + 1
                    break
            
            if table_start == -1:
                logger.warning("Axis Bank: Could not find table start in PDF")
                return rates
            
            # Skip header rows (General, Senior Citizens, Less than ₹ 3 Cr, etc.)
            # The actual data starts after these headers
            data_start = table_start
            for i in range(table_start, min(table_start + 5, len(lines))):
                if 'General' in lines[i] or 'Senior Citizens' in lines[i]:
                    data_start = i + 1
            
            # Parse data rows
            for line in lines[data_start:]:
                line = line.strip()
                
                # Stop at disclaimer or empty lines
                if not line or 'Disclaimer' in line or '*' in line[:5]:
                    break
                
                # Split by multiple spaces to get columns
                parts = line.split()
                
                if len(parts) < 5:
                    continue
                
                try:
                    # First part(s) are the tenure (may have multiple words/tokens)
                    # Last 4 parts are the rates (2 for general, 2 for senior)
                    # Extract rates from the end
                    rate_parts = parts[-4:]
                    
                    # Column 1: General (Less than ₹ 3 Cr)
                    general_rate = float(rate_parts[0])
                    
                    # Column 3: Senior Citizens (Less than ₹ 3 Cr)
                    senior_rate = float(rate_parts[2])
                    
                    # Tenure is everything except the last 4 rate values
                    tenure = ' '.join(parts[:-4])
                    
                    if not tenure:
                        continue
                    
                    rate_entry = RateEntry(
                        tenure=tenure,
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate
                    )
                    rates.append(rate_entry)
                    logger.debug(f"Axis Bank: Extracted {tenure}: {general_rate}% / {senior_rate}%")
                    
                except (ValueError, IndexError) as e:
                    logger.debug(f"Axis Bank: Skipping line (not a data row): {line[:50]}")
                    continue
            
            logger.info(f"Axis Bank: Successfully extracted {len(rates)} rates from PDF")
            
        except ImportError:
            logger.error("Axis Bank: PyPDF2 library not available for PDF parsing")
        except Exception as e:
            logger.error(f"Axis Bank: Error parsing PDF: {str(e)}")
        
        return rates

    def _parse_central_bank_table(self, soup: BeautifulSoup) -> List[RateEntry]:
        """
        Special parser for Central Bank of India tables.
        Central Bank has separate columns for General Public and Senior Citizen rates.
        Table structure:
        - Column 0: Maturity Period
        - Column 1: General Public Rate
        - Column 2: General Public Annualized Yield
        - Column 3: Senior Citizen Rate
        - Column 4: Senior Citizen Annualized Yield
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            # Find all tables
            tables = soup.find_all('table')
            
            # Table 3 (index 2) is the main FD rates table for deposits < 3 Cr
            if len(tables) < 3:
                logger.warning("Central Bank: Could not find the FD rates table")
                return rates
            
            fd_table = tables[2]  # Third table (index 2)
            logger.info("Central Bank: Found FD rates table (deposits < Rs. 3 Crore)")
            
            rows = fd_table.find_all('tr')
            
            # Skip first 3 rows (headers)
            # Row 0: "Maturity Period" | "Rates for Deposits less than Rs. 3 Crore"
            # Row 1: "General Public" | "Senior Citizen"
            # Row 2: "Rates w.e.f..." | "Annualised yield" | "Rates w.e.f..." | "Annualised yield"
            # Row 3+: Data rows
            
            for row_idx in range(3, len(rows)):
                row = rows[row_idx]
                cells = row.find_all(['td', 'th'])
                
                if len(cells) < 5:
                    continue
                
                try:
                    # Column 0: Maturity Period
                    tenure = cells[0].get_text().strip()
                    if not tenure or len(tenure) < 2:
                        continue
                    
                    # Column 1: General Public Rate
                    general_rate_text = cells[1].get_text().strip()
                    general_rate_text = re.sub(r'[^\d.]', '', general_rate_text)
                    if not general_rate_text:
                        continue
                    general_rate = float(general_rate_text)
                    
                    # Column 3: Senior Citizen Rate (skip column 2 which is annualized yield)
                    senior_rate = None
                    if len(cells) >= 4:
                        senior_text = cells[3].get_text().strip()
                        senior_text = re.sub(r'[^\d.]', '', senior_text)
                        if senior_text:
                            senior_rate = float(senior_text)
                    
                    rate_entry = RateEntry(
                        tenure=tenure,
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate
                    )
                    rates.append(rate_entry)
                    logger.debug(f"Central Bank: Extracted {tenure}: {general_rate}% / {senior_rate}%")
                    
                except Exception as e:
                    logger.warning(f"Central Bank: Error parsing row {row_idx}: {str(e)}")
                    continue
            
            logger.info(f"Central Bank: Successfully extracted {len(rates)} rates")
            
        except Exception as e:
            logger.error(f"Central Bank: Error parsing table: {str(e)}")
        
        return rates
    
    def _parse_shivalik_bank_table(self, soup: BeautifulSoup) -> List[RateEntry]:
        """
        Special parser for Shivalik Bank tables.
        Shivalik Bank has multiple tables:
        - Table 2 (index 1): Short duration rates (7 days to 6 months)
        - Table 4 (index 3): Longer duration rates (6 months to 10 years) with cleaner formats
        
        We parse Table 4 which has cleaner tenure formats that are easier to convert to days.
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            # Find all tables
            tables = soup.find_all('table')
            
            # Table 4 (index 3) is the FD rates table with cleaner tenure formats
            if len(tables) < 4:
                logger.warning("Shivalik Bank: Could not find the FD rates table (Table 4)")
                return rates
            
            fd_table = tables[3]  # Fourth table (index 3)
            logger.info("Shivalik Bank: Found FD rates table (Table 4 - longer durations)")
            
            rows = fd_table.find_all('tr')
            
            # Skip first 2 rows (headers)
            # Row 0: "Tenure Bucket" | ""
            # Row 1: "General" | "Senior Citizen"
            # Row 2+: Data rows
            
            for row_idx in range(2, len(rows)):
                row = rows[row_idx]
                cells = row.find_all(['td', 'th'])
                
                if len(cells) < 3:
                    continue
                
                try:
                    # Column 0: Tenure
                    tenure = cells[0].get_text().strip()
                    if not tenure or len(tenure) < 2:
                        continue
                    
                    # Column 1: General Rate
                    general_rate_text = cells[1].get_text().strip()
                    general_rate_text = re.sub(r'[^\d.]', '', general_rate_text)
                    if not general_rate_text:
                        continue
                    general_rate = float(general_rate_text)
                    
                    # Column 2: Senior Citizen Rate
                    senior_rate = None
                    if len(cells) >= 3:
                        senior_text = cells[2].get_text().strip()
                        senior_text = re.sub(r'[^\d.]', '', senior_text)
                        if senior_text:
                            senior_rate = float(senior_text)
                    
                    rate_entry = RateEntry(
                        tenure=tenure,
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate
                    )
                    rates.append(rate_entry)
                    logger.debug(f"Shivalik Bank: Extracted {tenure}: {general_rate}% / {senior_rate}%")
                    
                except Exception as e:
                    logger.warning(f"Shivalik Bank: Error parsing row {row_idx}: {str(e)}")
                    continue
            
            logger.info(f"Shivalik Bank: Successfully extracted {len(rates)} rates from Table 4")
            
        except Exception as e:
            logger.error(f"Shivalik Bank: Error parsing table: {str(e)}")
        
        return rates
    
    def _parse_federal_bank_table(self, soup: BeautifulSoup) -> List[RateEntry]:
        """
        Special parser for Federal Bank tables.
        Federal Bank has separate columns for General Public and Senior Citizen rates.
        - Table 1 (index 0): Deposits < ₹300 Lakhs with 3 columns: Period, General, Senior
        - Table 3 (index 2): Deposits < ₹3 Cr (special rates) with 3 columns: Period, General, Senior
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            # Find all tables
            tables = soup.find_all('table')
            
            if len(tables) < 3:
                logger.warning("Federal Bank: Could not find enough tables")
                return rates
            
            # Parse Table 1 (index 0) - deposits < ₹300 Lakhs
            logger.info("Federal Bank: Parsing Table 1 (deposits < ₹300 Lakhs)")
            rates.extend(self._parse_federal_single_table(tables[0], "Table 1"))
            
            # Parse Table 3 (index 2) - deposits < ₹3 Cr (special rates)
            logger.info("Federal Bank: Parsing Table 3 (deposits < ₹3 Cr - special rates)")
            rates.extend(self._parse_federal_single_table(tables[2], "Table 3"))
            
            logger.info(f"Federal Bank: Successfully extracted {len(rates)} rates total")
            
        except Exception as e:
            logger.error(f"Federal Bank: Error parsing tables: {str(e)}")
        
        return rates
    
    def _parse_federal_single_table(self, table: Tag, table_name: str) -> List[RateEntry]:
        """
        Parse a single Federal Bank table with 3 columns: Period, General, Senior.
        
        Args:
            table: HTML table element
            table_name: Name of the table for logging
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            rows = table.find_all('tr')
            
            # Skip first row (header)
            # For some tables, also skip second row which has "General Public" and "Senior Citizen*" labels
            start_row = 1
            
            # Check if second row has "General Public" text (indicates it's a sub-header)
            if len(rows) > 1:
                second_row_text = rows[1].get_text().lower()
                if 'general public' in second_row_text:
                    start_row = 2
            
            for row_idx in range(start_row, len(rows)):
                row = rows[row_idx]
                cells = row.find_all(['td', 'th'])
                
                # Federal Bank tables have 3 columns: Period, General Rate, Senior Rate
                if len(cells) < 3:
                    continue
                
                try:
                    # Column 0: Period
                    tenure = cells[0].get_text().strip()
                    if not tenure or len(tenure) < 2:
                        continue
                    
                    # Column 1: General Rate
                    general_rate_text = cells[1].get_text().strip()
                    general_rate_text = re.sub(r'[^\d.]', '', general_rate_text)
                    if not general_rate_text:
                        continue
                    general_rate = float(general_rate_text)
                    
                    # Column 2: Senior Citizen Rate
                    senior_rate = None
                    if len(cells) >= 3:
                        senior_text = cells[2].get_text().strip()
                        senior_text = re.sub(r'[^\d.]', '', senior_text)
                        if senior_text:
                            senior_rate = float(senior_text)
                    
                    rate_entry = RateEntry(
                        tenure=tenure,
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate
                    )
                    rates.append(rate_entry)
                    logger.debug(f"Federal Bank ({table_name}): Extracted {tenure}: {general_rate}% / {senior_rate}%")
                    
                except Exception as e:
                    logger.warning(f"Federal Bank ({table_name}): Error parsing row {row_idx}: {str(e)}")
                    continue
            
        except Exception as e:
            logger.error(f"Federal Bank ({table_name}): Error parsing table: {str(e)}")
        
        return rates
    
    def _parse_pnb_bank_table(self, soup: BeautifulSoup) -> List[RateEntry]:
        """
        Special parser for Punjab National Bank tables.
        PNB has nested divs with a section titled "Domestic term deposits (Below Rs. 3 crore)".
        Table structure:
        - Column 0: Sl. No
        - Column 1: Period
        - Column 2: Public Rate
        - Column 3: Senior Citizen Rate
        - Column 4: Super Senior Citizen Rate (optional)
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            # Find the section for "Domestic term deposits (Below Rs. 3 crore)"
            target_text = soup.find(string=re.compile('Domestic term deposits.*Below Rs. 3 crore', re.IGNORECASE))
            
            if not target_text:
                logger.warning("PNB: Could not find 'Domestic term deposits (Below Rs. 3 crore)' section")
                return rates
            
            logger.info("PNB: Found 'Domestic term deposits (Below Rs. 3 crore)' section")
            
            # Navigate to find the table
            parent = target_text.parent
            table = None
            
            for _ in range(10):  # Search up to 10 levels up
                if parent is None:
                    break
                
                table = parent.find('table')
                if table:
                    logger.info("PNB: Found table in section")
                    break
                
                parent = parent.parent
            
            if not table:
                logger.warning("PNB: Could not find table")
                return rates
            
            rows = table.find_all('tr')
            
            # Skip first row (header)
            for row_idx in range(1, len(rows)):
                row = rows[row_idx]
                cells = row.find_all(['td', 'th'])
                
                # Need at least 4 columns (Sl.No, Period, Public, Senior)
                if len(cells) < 4:
                    continue
                
                try:
                    # Column 1: Period/Term
                    tenure = cells[1].get_text().strip()
                    if not tenure or len(tenure) < 2:
                        continue
                    
                    # Skip if it's a header row
                    if 'period' in tenure.lower() or 'sl' in tenure.lower():
                        continue
                    
                    # Column 2: Public Rate
                    general_rate_text = cells[2].get_text().strip()
                    general_rate_text = re.sub(r'[^\d.]', '', general_rate_text)
                    if not general_rate_text:
                        continue
                    general_rate = float(general_rate_text)
                    
                    # Column 3: Senior Citizen Rate
                    senior_rate = None
                    if len(cells) >= 4:
                        senior_text = cells[3].get_text().strip()
                        senior_text = re.sub(r'[^\d.]', '', senior_text)
                        if senior_text:
                            senior_rate = float(senior_text)
                    
                    rate_entry = RateEntry(
                        tenure=tenure,
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate
                    )
                    rates.append(rate_entry)
                    logger.debug(f"PNB: Extracted {tenure}: {general_rate}% / {senior_rate}%")
                    
                except Exception as e:
                    logger.warning(f"PNB: Error parsing row {row_idx}: {str(e)}")
                    continue
            
            logger.info(f"PNB: Successfully extracted {len(rates)} rates")
            
        except Exception as e:
            logger.error(f"PNB: Error parsing table: {str(e)}")
        
        return rates
    
    def _parse_uco_bank_table(self, soup: BeautifulSoup) -> List[RateEntry]:
        """
        Special parser for UCO Bank tables.
        UCO Bank has general customer rates in Table 2, and we apply hardcoded rules for senior citizens:
        - For deposits <= 1 Lakh: Senior rate = General rate + 0.25%
        - For deposits > 1 Lakh: Senior rate = General rate + 0.50%
        
        We create two sets of rates: one for <= 1L and one for > 1L.
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            # Find all tables
            tables = soup.find_all('table')
            
            # Table 2 (index 1) contains the general customer rates for deposits < Rs. 3 Crore
            if len(tables) < 2:
                logger.warning("UCO Bank: Could not find the FD rates table")
                return rates
            
            fd_table = tables[1]  # Second table (index 1)
            logger.info("UCO Bank: Found FD rates table (deposits < Rs. 3 Crore)")
            
            rows = fd_table.find_all('tr')
            
            # Skip first 2 rows (headers)
            # Row 0: "Maturity Period" | "Existing ROI for General Customer" | "Revised ROI for General Customer"
            # Row 1: "Rate % p.a." | "Yield in %" | "Rate % p.a." | "Yield in %"
            # Row 2+: Data rows
            
            for row_idx in range(2, len(rows)):
                row = rows[row_idx]
                cells = row.find_all(['td', 'th'])
                
                # Need at least 5 columns (Maturity, Existing Rate, Existing Yield, Revised Rate, Revised Yield)
                if len(cells) < 5:
                    continue
                
                try:
                    # Column 0: Maturity Period
                    tenure = cells[0].get_text().strip()
                    if not tenure or len(tenure) < 2:
                        continue
                    
                    # Column 3: Revised Rate for General Customer (Rate % p.a.)
                    general_rate_text = cells[3].get_text().strip()
                    general_rate_text = re.sub(r'[^\d.]', '', general_rate_text)
                    if not general_rate_text:
                        continue
                    general_rate = float(general_rate_text)
                    
                    # Apply hardcoded rules for senior citizen rates based on amount
                    # Rule 1: For deposits <= 1 Lakh, senior rate = general rate + 0.25%
                    senior_rate_upto_1l = round(general_rate + 0.25, 2)
                    
                    # Rule 2: For deposits > 1 Lakh, senior rate = general rate + 0.50%
                    senior_rate_above_1l = round(general_rate + 0.50, 2)
                    
                    # Create two rate entries: one for <= 1L and one for > 1L
                    # Entry 1: For deposits <= 1 Lakh
                    rate_entry_upto = RateEntry(
                        tenure=f"{tenure} (<= 1 Lakh)",
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate_upto_1l,
                        min_amount=0,
                        max_amount=100000  # <= 1 Lakh
                    )
                    rates.append(rate_entry_upto)
                    logger.debug(f"UCO Bank: Extracted {tenure} (<= 1L): {general_rate}% / {senior_rate_upto_1l}%")
                    
                    # Entry 2: For deposits > 1 Lakh
                    rate_entry_above = RateEntry(
                        tenure=f"{tenure} (> 1 Lakh)",
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate_above_1l,
                        min_amount=100001,  # > 1 Lakh
                        max_amount=29999999  # < 3 Crore
                    )
                    rates.append(rate_entry_above)
                    logger.debug(f"UCO Bank: Extracted {tenure} (> 1L): {general_rate}% / {senior_rate_above_1l}%")
                    
                except Exception as e:
                    logger.warning(f"UCO Bank: Error parsing row {row_idx}: {str(e)}")
                    continue
            
            logger.info(f"UCO Bank: Successfully extracted {len(rates)} rates (with amount-based senior rates)")
            
        except Exception as e:
            logger.error(f"UCO Bank: Error parsing table: {str(e)}")
        
        return rates
    
    def _parse_hdfc_bank_table(self, soup: BeautifulSoup) -> List[RateEntry]:
        """
        Special parser for HDFC Bank tables.
        HDFC Bank has tables with 3 columns: Tenor Bucket, Interest Rate, Senior Citizen Rates
        - Table 1 (index 0): Deposits < ₹3 Crore
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            # Find all tables
            tables = soup.find_all('table')
            
            # Table 1 (index 0) contains rates for deposits < ₹3 Crore
            if len(tables) < 1:
                logger.warning("HDFC Bank: Could not find the FD rates table")
                return rates
            
            fd_table = tables[0]  # First table (index 0)
            logger.info("HDFC Bank: Found FD rates table (deposits < ₹3 Crore)")
            
            rows = fd_table.find_all('tr')
            
            # Skip first 2 rows (headers)
            # Row 0: "Tenor Bucket" | "< ₹3 Crore" | ""
            # Row 1: "" | "Interest Rate (per annum)" | "**Senior Citizen Rates (per annum)"
            # Row 2+: Data rows
            
            for row_idx in range(2, len(rows)):
                row = rows[row_idx]
                cells = row.find_all(['td', 'th'])
                
                # Need at least 3 columns (Tenor, General Rate, Senior Rate)
                if len(cells) < 3:
                    continue
                
                try:
                    # Column 0: Tenor Bucket
                    tenure = cells[0].get_text().strip()
                    if not tenure or len(tenure) < 2:
                        continue
                    
                    # Column 1: Interest Rate (General)
                    general_rate_text = cells[1].get_text().strip()
                    general_rate_text = re.sub(r'[^\d.]', '', general_rate_text)
                    if not general_rate_text:
                        continue
                    general_rate = float(general_rate_text)
                    
                    # Column 2: Senior Citizen Rate
                    senior_rate = None
                    if len(cells) >= 3:
                        senior_text = cells[2].get_text().strip()
                        senior_text = re.sub(r'[^\d.]', '', senior_text)
                        if senior_text:
                            senior_rate = float(senior_text)
                    
                    rate_entry = RateEntry(
                        tenure=tenure,
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate
                    )
                    rates.append(rate_entry)
                    logger.debug(f"HDFC Bank: Extracted {tenure}: {general_rate}% / {senior_rate}%")
                    
                except Exception as e:
                    logger.warning(f"HDFC Bank: Error parsing row {row_idx}: {str(e)}")
                    continue
            
            logger.info(f"HDFC Bank: Successfully extracted {len(rates)} rates")
            
        except Exception as e:
            logger.error(f"HDFC Bank: Error parsing table: {str(e)}")
        
        return rates
    
    def _parse_bank_of_maharashtra_table(self, soup: BeautifulSoup) -> List[RateEntry]:
        """
        Special parser for Bank of Maharashtra.
        The page has a staircase-structured table (Table index 1) for deposits < Rs. 3 Cr.
        Each row starts with the tenure for that row as the first token of the first cell,
        followed by the callable rate for < 3 Cr as the second token.
        Structure: Row 2 = "7- 30 days", Row 3 = "31-45 days", ..., Row 13 = "Above 5 years"
        Senior citizen rate = general rate + 0.5%
        """
        rates = []

        try:
            tables = soup.find_all('table')
            # Table 1 is the "Less than Rs. 3 Cr / Rs. 3 Cr to Rs. 10 Cr" table
            if len(tables) < 2:
                logger.warning("Bank of Maharashtra: Could not find rates table")
                return rates

            tbl = tables[1]
            rows = tbl.find_all('tr')
            logger.info("Bank of Maharashtra: Found rates table (%d rows)" % len(rows))

            # Rows 2 onwards each represent one tenure band.
            # The first cell of each row starts with: "<tenure> <callable_rate> xx <non-callable_rate> xx ..."
            # We want the tenure and the first (callable) rate for < 3 Cr.
            tenure_pattern = re.compile(
                r'^([\w\s\-/]+?(?:days?|year[s]?|one year))\s+([\d.]+)',
                re.IGNORECASE
            )

            for row in rows[2:]:
                cells = row.find_all(['td', 'th'])
                if not cells:
                    continue
                cell_text = cells[0].get_text(separator=' ', strip=True)
                m = tenure_pattern.match(cell_text)
                if m:
                    tenure = m.group(1).strip()
                    general_rate = float(m.group(2))
                    senior_rate = round(general_rate + 0.5, 2)
                    rates.append(RateEntry(
                        tenure=tenure,
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate
                    ))
                    logger.debug("Bank of Maharashtra: %s -> %.2f%% / %.2f%%" % (tenure, general_rate, senior_rate))

            logger.info("Bank of Maharashtra: Successfully extracted %d rates" % len(rates))

        except Exception as e:
            logger.error("Bank of Maharashtra: Error parsing table: %s" % str(e))

        return rates
    
    def _parse_bank_of_baroda_table(self, soup: BeautifulSoup) -> List[RateEntry]:
        """
        Special parser for Bank of Baroda tables.
        Bank of Baroda has callable FD rates in Table 0 for deposits < Rs. 3 Crore.
        Table structure:
        - Column 0: Tenors
        - Column 1: Residents / General Public
        - Column 2: Resident Indian Sr. Citizen
        - Column 3: Resident Super Senior Citizen (we'll use column 2 for senior rates)
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            # Find all tables
            tables = soup.find_all('table')
            
            # Table 0 contains the callable FD rates for deposits < Rs. 3 Crore
            if len(tables) < 1:
                logger.warning("Bank of Baroda: Could not find the FD rates table")
                return rates
            
            fd_table = tables[0]  # First table (index 0) - Callable FD rates
            logger.info("Bank of Baroda: Found FD rates table (Callable - deposits < Rs. 3 Crore)")
            
            rows = fd_table.find_all('tr')
            
            # Skip first row (header)
            # Row 0: "Tenors" | "Residents / General Public" | "Resident Indian Sr. Citizen" | "Resident Super Senior Citizen"
            # Row 1+: Data rows
            
            for row_idx in range(1, len(rows)):
                row = rows[row_idx]
                cells = row.find_all(['td', 'th'])
                
                # Need at least 3 columns (Tenors, General, Senior)
                if len(cells) < 3:
                    continue
                
                try:
                    # Column 0: Tenors
                    tenure = cells[0].get_text().strip()
                    if not tenure or len(tenure) < 2:
                        continue
                    
                    # Skip if it's a header row
                    if 'tenor' in tenure.lower():
                        continue
                    
                    # Column 1: Residents / General Public
                    general_rate_text = cells[1].get_text().strip()
                    general_rate_text = re.sub(r'[^\d.]', '', general_rate_text)
                    if not general_rate_text:
                        continue
                    general_rate = float(general_rate_text)
                    
                    # Column 2: Resident Indian Sr. Citizen
                    senior_rate = None
                    if len(cells) >= 3:
                        senior_text = cells[2].get_text().strip()
                        senior_text = re.sub(r'[^\d.]', '', senior_text)
                        if senior_text:
                            senior_rate = float(senior_text)
                    
                    rate_entry = RateEntry(
                        tenure=tenure,
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate
                    )
                    rates.append(rate_entry)
                    logger.debug(f"Bank of Baroda: Extracted {tenure}: {general_rate}% / {senior_rate}%")
                    
                except Exception as e:
                    logger.warning(f"Bank of Baroda: Error parsing row {row_idx}: {str(e)}")
                    continue
            
            logger.info(f"Bank of Baroda: Successfully extracted {len(rates)} rates")
            
        except Exception as e:
            logger.error(f"Bank of Baroda: Error parsing table: {str(e)}")
        
        return rates
    
    def _parse_canara_bank_table(self, soup: BeautifulSoup) -> List[RateEntry]:
        """
        Special parser for Canara Bank tables.
        Canara Bank has FD rates in Table 1 for deposits < Rs. 3 Crore.
        Table structure:
        - Row 4: Headers with "General Public" and "Senior Citizen"
        - Row 5: Sub-headers with "Annualised Interest yield (% p.a.)"
        - Row 6+: Data rows with tenure and rates
        
        We extract:
        - Column 0: Tenure
        - Column 2: General Public - Annualised Interest yield (index 1 in row 5)
        - Column 4: Senior Citizen - Annualised Interest yield (index 3 in row 5)
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            # Find all tables
            tables = soup.find_all('table')
            
            # Table 1 contains the FD rates for deposits < Rs. 3 Crore
            if len(tables) < 2:
                logger.warning("Canara Bank: Could not find the FD rates table")
                return rates
            
            fd_table = tables[1]  # Second table (index 1)
            logger.info("Canara Bank: Found FD rates table (deposits < Rs. 3 Crore)")
            
            rows = fd_table.find_all('tr')
            
            # Skip first 6 rows (headers and sub-headers)
            # Row 0: Title
            # Row 1: "A. Domestic"
            # Row 2: "Less than Rs.3 Crore"
            # Row 3: "Callable" / "Non Callable"
            # Row 4: "General Public" / "Senior Citizen" headers
            # Row 5: "Annualised Interest yield" sub-headers
            # Row 6+: Data rows
            
            for row_idx in range(6, len(rows)):
                row = rows[row_idx]
                cells = row.find_all(['td', 'th'])
                
                # Need at least 5 columns (Tenure, Gen Rate, Gen Yield, Sen Rate, Sen Yield)
                if len(cells) < 5:
                    continue
                
                try:
                    # Column 0: Tenure
                    tenure = cells[0].get_text().strip()
                    if not tenure or len(tenure) < 2:
                        continue
                    
                    # Skip if it's a header or note row
                    if any(word in tenure.lower() for word in ['note', 'rate of interest', 'term deposits', 'callable', 'non callable']):
                        continue
                    
                    # Column 2: General Public - Annualised Interest yield
                    general_rate_text = cells[2].get_text().strip()
                    general_rate_text = re.sub(r'[^\d.]', '', general_rate_text)
                    if not general_rate_text or general_rate_text == 'NA':
                        continue
                    general_rate = float(general_rate_text)
                    
                    # Column 4: Senior Citizen - Annualised Interest yield
                    senior_rate = None
                    if len(cells) >= 5:
                        senior_text = cells[4].get_text().strip()
                        senior_text = re.sub(r'[^\d.]', '', senior_text)
                        if senior_text and senior_text != 'NA':
                            senior_rate = float(senior_text)
                    
                    rate_entry = RateEntry(
                        tenure=tenure,
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate
                    )
                    rates.append(rate_entry)
                    logger.debug(f"Canara Bank: Extracted {tenure}: {general_rate}% / {senior_rate}%")
                    
                except Exception as e:
                    logger.warning(f"Canara Bank: Error parsing row {row_idx}: {str(e)}")
                    continue
            
            logger.info(f"Canara Bank: Successfully extracted {len(rates)} rates")
            
        except Exception as e:
            logger.error(f"Canara Bank: Error parsing table: {str(e)}")
        
        return rates
    
    def _parse_au_small_finance_bank_table(self, soup: BeautifulSoup) -> List[RateEntry]:
        """
        Special parser for AU Small Finance Bank tables.
        AU Small Finance Bank has separate tables for:
        - Regular customers (Domestic & NRE/NRO Retail Fixed Deposit)
        - Senior Citizens
        
        Both tables have the same structure:
        - Column 0: Tenures
        - Column 1: Interest Rates (per annum)
        - Column 2: Annualized Yield
        
        We need to match tenures between both tables to create complete rate entries.
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            # Find all tables
            tables = soup.find_all('table')
            
            if len(tables) < 2:
                logger.warning("AU Small Finance Bank: Could not find enough tables")
                return rates
            
            logger.info(f"AU Small Finance Bank: Found {len(tables)} tables")
            
            # Find the regular and senior citizen tables
            regular_table = None
            senior_table = None
            
            for idx, table in enumerate(tables):
                # Look at the preceding text/headings to identify the table
                prev_text = ""
                prev_elem = table.find_previous(['h2', 'h3', 'p', 'div'])
                if prev_elem:
                    prev_text = prev_elem.get_text().upper()
                
                # Check table content as well
                table_text = table.get_text().upper()
                
                # Look for regular/domestic table (for amounts < 3 Crore)
                if ('DOMESTIC' in prev_text or 'NRE' in prev_text or 'NRO' in prev_text) and 'SENIOR' not in prev_text:
                    if '3 CRORE' in prev_text or '3 CR' in prev_text:
                        regular_table = (idx, table)
                        logger.info(f"AU Small Finance Bank: Found regular customer table at index {idx}")
                
                # Look for senior citizen table (for amounts < 3 Crore)
                if 'SENIOR CITIZEN' in prev_text:
                    if '3 CRORE' in prev_text or '3 CR' in prev_text:
                        senior_table = (idx, table)
                        logger.info(f"AU Small Finance Bank: Found senior citizen table at index {idx}")
            
            if not regular_table:
                logger.warning("AU Small Finance Bank: Regular customer table not found")
                return rates
            
            # Extract general rates from regular table
            general_rates = self._extract_au_bank_rates(regular_table[1], "Regular")
            
            # Extract senior rates from senior citizen table if available
            senior_rates = {}
            if senior_table:
                senior_rates_list = self._extract_au_bank_rates(senior_table[1], "Senior Citizen")
                # Create a dictionary for easy lookup by tenure
                senior_rates = {rate.tenure: rate.general_rate for rate in senior_rates_list}
            
            # Combine general and senior rates
            for gen_rate in general_rates:
                senior_rate = senior_rates.get(gen_rate.tenure)
                
                rate_entry = RateEntry(
                    tenure=gen_rate.tenure,
                    general_rate=gen_rate.general_rate,
                    senior_citizen_rate=senior_rate
                )
                rates.append(rate_entry)
                logger.debug(f"AU Small Finance Bank: Extracted {gen_rate.tenure}: {gen_rate.general_rate}% / {senior_rate}%")
            
            logger.info(f"AU Small Finance Bank: Successfully extracted {len(rates)} rates")
            
        except Exception as e:
            logger.error(f"AU Small Finance Bank: Error parsing tables: {str(e)}")
        
        return rates
    
    def _extract_au_bank_rates(self, table: Tag, table_type: str) -> List[RateEntry]:
        """
        Extract rates from a single AU Small Finance Bank table.
        
        Args:
            table: HTML table element
            table_type: Type of table ("Regular" or "Senior Citizen")
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            rows = table.find_all('tr')
            
            # Skip header row (row 0)
            # Data starts from row 1
            for row_idx in range(1, len(rows)):
                row = rows[row_idx]
                cells = row.find_all(['td', 'th'])
                
                # Need at least 2 columns (Tenure, Rate)
                if len(cells) < 2:
                    continue
                
                try:
                    # Column 0: Tenure
                    tenure = cells[0].get_text().strip()
                    if not tenure or len(tenure) < 2:
                        continue
                    
                    # Skip if it's a header row
                    if any(word in tenure.lower() for word in ['tenure', 'maturity', 'period', 'interest rate']):
                        continue
                    
                    # Column 1: Interest Rate (per annum)
                    rate_text = cells[1].get_text().strip()
                    rate_text = re.sub(r'[^\d.]', '', rate_text)
                    if not rate_text:
                        continue
                    rate_value = float(rate_text)
                    
                    rate_entry = RateEntry(
                        tenure=tenure,
                        general_rate=rate_value
                    )
                    rates.append(rate_entry)
                    logger.debug(f"AU Small Finance Bank ({table_type}): Extracted {tenure}: {rate_value}%")
                    
                except Exception as e:
                    logger.warning(f"AU Small Finance Bank ({table_type}): Error parsing row {row_idx}: {str(e)}")
                    continue
            
        except Exception as e:
            logger.error(f"AU Small Finance Bank ({table_type}): Error extracting rates: {str(e)}")
        
        return rates
    
    def _parse_union_bank_table(self, soup: BeautifulSoup) -> List[RateEntry]:
        """
        Special parser for Union Bank of India tables.
        Union Bank has a single table with general rates for deposits < Rs. 3 Cr.
        Senior citizen rate = General rate + 0.50%
        
        Table structure:
        - Column 0: Period
        - Column 1: Revised Interest Rate
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            # Find all tables
            tables = soup.find_all('table')
            
            # Table 0 contains the FD rates for deposits < Rs. 3 Cr
            if len(tables) < 1:
                logger.warning("Union Bank: Could not find the FD rates table")
                return rates
            
            fd_table = tables[0]  # First table
            logger.info("Union Bank: Found FD rates table (deposits < Rs. 3 Cr)")
            
            rows = fd_table.find_all('tr')
            
            # Skip first 2 rows (headers)
            # Row 0: "Period" | "Revised Interest Rate"
            # Row 1: "< Rs. 3 Cr"
            # Row 2+: Data rows
            
            for row_idx in range(2, len(rows)):
                row = rows[row_idx]
                cells = row.find_all(['td', 'th'])
                
                # Need at least 2 columns (Period, Rate)
                if len(cells) < 2:
                    continue
                
                try:
                    # Column 0: Period
                    tenure = cells[0].get_text().strip()
                    if not tenure or len(tenure) < 2:
                        continue
                    
                    # Skip if it's a header row
                    if any(word in tenure.lower() for word in ['period', 'tenure', 'maturity', 'rate']):
                        continue
                    
                    # Column 1: Revised Interest Rate
                    general_rate_text = cells[1].get_text().strip()
                    general_rate_text = re.sub(r'[^\d.]', '', general_rate_text)
                    if not general_rate_text:
                        continue
                    general_rate = float(general_rate_text)
                    
                    # Calculate senior citizen rate: General rate + 0.50%
                    senior_rate = round(general_rate + 0.50, 2)
                    
                    rate_entry = RateEntry(
                        tenure=tenure,
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate
                    )
                    rates.append(rate_entry)
                    logger.debug(f"Union Bank: Extracted {tenure}: {general_rate}% / {senior_rate}%")
                    
                except Exception as e:
                    logger.warning(f"Union Bank: Error parsing row {row_idx}: {str(e)}")
                    continue
            
            logger.info(f"Union Bank: Successfully extracted {len(rates)} rates (senior rate = general + 0.50%)")
            
        except Exception as e:
            logger.error(f"Union Bank: Error parsing table: {str(e)}")
        
        return rates
    
    def _parse_indusind_bank_table(self, soup: BeautifulSoup) -> List[RateEntry]:
        """
        Special parser for IndusInd Bank tables.
        IndusInd Bank has rates for deposits < 3 Cr.
        
        Table structure (Table 0) - current format:
        - Row 0: Main headers (< 3 Cr DOMESTIC, < 3 Cr Senior Citizen)
        - Row 1: Sub-headers (Tenure, Rate, Rate)
        - Row 2+: Data rows with 3 columns
        
        We extract:
        - Column 0: Tenure
        - Column 1: General Rate
        - Column 2: Senior Citizen Rate
        
        Also supports older 5-column format with Annualized Yield columns.
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            # Find all tables
            tables = soup.find_all('table')
            
            # Table 0 contains the FD rates for deposits < 3 Cr
            if len(tables) < 1:
                logger.warning("IndusInd Bank: Could not find the FD rates table")
                return rates
            
            fd_table = tables[0]  # First table
            logger.info("IndusInd Bank: Found FD rates table (deposits < 3 Cr)")
            
            rows = fd_table.find_all('tr')
            
            # Determine column layout from header row
            # Check if it's 5-column (with Annualized Yield) or 3-column (Rate only)
            header_cells = rows[1].find_all(['td', 'th']) if len(rows) > 1 else []
            num_cols = len(header_cells)
            
            # Column indices for general and senior rates
            if num_cols >= 5:
                # Old format: Tenure, Rate, Annualized Yield, Rate, Annualized Yield
                general_col = 2  # Annualized Yield (General)
                senior_col = 4  # Annualized Yield (Senior Citizen)
                min_cols = 5
                logger.info("IndusInd Bank: Using 5-column format (Annualized Yield)")
            else:
                # New format: Tenure, Rate (General), Rate (Senior)
                general_col = 1
                senior_col = 2
                min_cols = 3
                logger.info("IndusInd Bank: Using 3-column format (Rate)")
            
            # Skip first 2 rows (headers)
            for row_idx in range(2, len(rows)):
                row = rows[row_idx]
                cells = row.find_all(['td', 'th'])
                
                if len(cells) < min_cols:
                    continue
                
                try:
                    # Column 0: Tenure
                    tenure = cells[0].get_text().strip()
                    if not tenure or len(tenure) < 2:
                        continue
                    
                    # Skip if it's a header row
                    if any(word in tenure.lower() for word in ['tenure', 'period', 'maturity', 'rate']):
                        continue
                    
                    # General Rate
                    general_rate_text = cells[general_col].get_text().strip()
                    general_rate_text = re.sub(r'[^\d.]', '', general_rate_text)
                    if not general_rate_text:
                        continue
                    general_rate = float(general_rate_text)
                    
                    # Senior Citizen Rate
                    senior_rate_text = cells[senior_col].get_text().strip()
                    senior_rate_text = re.sub(r'[^\d.]', '', senior_rate_text)
                    if not senior_rate_text:
                        continue
                    senior_rate = float(senior_rate_text)
                    
                    rate_entry = RateEntry(
                        tenure=tenure,
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate
                    )
                    rates.append(rate_entry)
                    logger.debug(f"IndusInd Bank: Extracted {tenure}: {general_rate}% / {senior_rate}%")
                    
                except Exception as e:
                    logger.warning(f"IndusInd Bank: Error parsing row {row_idx}: {str(e)}")
                    continue
            
            logger.info(f"IndusInd Bank: Successfully extracted {len(rates)} rates")
            
        except Exception as e:
            logger.error(f"IndusInd Bank: Error parsing table: {str(e)}")
        
        return rates
    
    def _parse_idfc_first_bank_table(self, soup: BeautifulSoup) -> List[RateEntry]:
        """
        Special parser for IDFC FIRST Bank tables.
        IDFC FIRST Bank has rates for deposits < ₹3 Crore.
        
        Table structure (Table 0):
        - Row 0: Main header (Interest Rates for Domestic / NRO / NRE Fixed Deposits...)
        - Row 1: Note
        - Row 2: Column header (Tenure, Rate of Interest)
        - Row 3: Sub-headers (General, Senior Citizen)
        - Row 4+: Data rows
        
        We extract:
        - Column 0: Tenure
        - Column 1: General Rate
        - Column 2: Senior Citizen Rate
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            # Find all tables
            tables = soup.find_all('table')
            
            # Table 0 contains the FD rates for deposits < ₹3 Crore
            if len(tables) < 1:
                logger.warning("IDFC FIRST Bank: Could not find the FD rates table")
                return rates
            
            fd_table = tables[0]  # First table
            logger.info("IDFC FIRST Bank: Found FD rates table (deposits < ₹3 Crore)")
            
            rows = fd_table.find_all('tr')
            
            # Skip first 4 rows (headers)
            # Row 0: Main header
            # Row 1: Note
            # Row 2: Column header (Tenure, Rate of Interest)
            # Row 3: Sub-headers (General, Senior Citizen)
            # Row 4+: Data rows
            
            for row_idx in range(4, len(rows)):
                row = rows[row_idx]
                cells = row.find_all(['td', 'th'])
                
                # Need at least 3 columns (Tenure, General Rate, Senior Rate)
                if len(cells) < 3:
                    continue
                
                try:
                    # Column 0: Tenure
                    tenure = cells[0].get_text().strip()
                    if not tenure or len(tenure) < 2:
                        continue
                    
                    # Skip if it's a header row
                    if any(word in tenure.lower() for word in ['tenure', 'period', 'maturity', 'rate', 'general', 'senior']):
                        continue
                    
                    # Column 1: General Rate
                    general_rate_text = cells[1].get_text().strip()
                    general_rate_text = re.sub(r'[^\d.]', '', general_rate_text)
                    if not general_rate_text:
                        continue
                    general_rate = float(general_rate_text)
                    
                    # Column 2: Senior Citizen Rate
                    senior_rate_text = cells[2].get_text().strip()
                    senior_rate_text = re.sub(r'[^\d.]', '', senior_rate_text)
                    if not senior_rate_text:
                        continue
                    senior_rate = float(senior_rate_text)
                    
                    rate_entry = RateEntry(
                        tenure=tenure,
                        general_rate=general_rate,
                        senior_citizen_rate=senior_rate
                    )
                    rates.append(rate_entry)
                    logger.debug(f"IDFC FIRST Bank: Extracted {tenure}: {general_rate}% / {senior_rate}%")
                    
                except Exception as e:
                    logger.warning(f"IDFC FIRST Bank: Error parsing row {row_idx}: {str(e)}")
                    continue
            
            logger.info(f"IDFC FIRST Bank: Successfully extracted {len(rates)} rates")
            
        except Exception as e:
            logger.error(f"IDFC FIRST Bank: Error parsing table: {str(e)}")
        
        return rates
    
    def _fetch_webpage(self, url: str) -> Optional[str]:
        """
        Fetch webpage content with proper error handling and delays.
        
        Args:
            url: The URL to fetch
            
        Returns:
            HTML content as string or None if failed
        """
        try:
            # Add delay to respect rate limiting
            time.sleep(self.config.scraping.request_delay)
            
            response = self.session.get(
                url,
                timeout=self.config.scraping.request_timeout,
                allow_redirects=True
            )
            response.raise_for_status()
            
            return response.text
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch {url}: {str(e)}")
            return None
    
    def _fetch_webpage_with_retry(self, url: str, attempt: int) -> Optional[str]:
        """
        Fetch webpage content with retry logic and exponential backoff.
        
        Args:
            url: The URL to fetch
            attempt: Current attempt number (0-based)
            
        Returns:
            HTML content as string or None if failed
        """
        try:
            # Calculate delay with exponential backoff
            if attempt > 0:
                wait_time = self.config.scraping.backoff_factor ** (attempt - 1)
                wait_time = min(wait_time, self.config.scraping.max_backoff_delay)
                logger.info(f"Waiting {wait_time} seconds before attempt {attempt + 1}...")
                time.sleep(wait_time)
            else:
                # Regular delay for first attempt
                time.sleep(self.config.scraping.request_delay)
            
            response = self.session.get(
                url,
                timeout=self.config.scraping.request_timeout,
                allow_redirects=True
            )
            response.raise_for_status()
            
            return response.text
            
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to fetch {url} (attempt {attempt + 1}): {str(e)}")
            return None
    
    def _extract_bank_name_from_url(self, url: str) -> str:
        """
        Extract bank name from URL domain.
        
        Args:
            url: The URL to extract bank name from
            
        Returns:
            Extracted bank name or domain
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove common prefixes and suffixes
            domain = re.sub(r'^(www\.|m\.)', '', domain)
            domain = re.sub(r'\.(com|co\.in|org|net|in)$', '', domain)
            
            # Convert to title case
            return domain.replace('.', ' ').title()
            
        except Exception:
            return "Unknown Bank"
    
    def _identify_rate_tables(self, soup: BeautifulSoup) -> List[Tag]:
        """
        Identify HTML tables that likely contain FD rate information.
        
        Args:
            soup: BeautifulSoup object of the webpage
            
        Returns:
            List of table elements that likely contain rate data
        """
        candidate_tables = []
        
        # Find all tables
        tables = soup.find_all('table')
        
        for table in tables:
            score = self._score_table_for_rates(table)
            if score > 0:
                candidate_tables.append((table, score))
        
        # Sort by score (highest first) and return tables
        candidate_tables.sort(key=lambda x: x[1], reverse=True)
        return [table for table, score in candidate_tables]
    
    def _score_table_for_rates(self, table: Tag) -> int:
        """
        Score a table based on how likely it is to contain FD rate data.
        
        Args:
            table: HTML table element
            
        Returns:
            Score (higher means more likely to contain rates)
        """
        score = 0
        table_text = table.get_text().lower()
        
        # Check for rate-related keywords
        for indicator in self.rate_table_indicators:
            if indicator in table_text:
                score += 2
        
        # Check for percentage symbols
        if '%' in table_text:
            score += 3
        
        # Check for tenure-related patterns
        for pattern in self.tenure_patterns:
            if re.search(pattern, table_text, re.IGNORECASE):
                score += 2
        
        # Check table structure (should have multiple rows and columns)
        rows = table.find_all('tr')
        if len(rows) >= 3:  # Header + at least 2 data rows
            score += 1
        
        # Check for numeric data (rates)
        numeric_cells = len(re.findall(r'\d+\.?\d*', table_text))
        if numeric_cells >= 5:  # Should have multiple numeric values
            score += 1
        
        return score
    
    def _parse_rate_table(self, table: Tag) -> List[RateEntry]:
        """
        Parse a rate table and extract individual rate entries.
        
        Args:
            table: HTML table element containing rate data
            
        Returns:
            List of RateEntry objects
        """
        rates = []
        
        try:
            rows = table.find_all('tr')
            if len(rows) < 2:  # Need at least header + 1 data row
                return rates
            
            # Identify column structure
            header_row = rows[0]
            column_mapping = self._identify_columns(header_row)
            
            # Process data rows
            for row in rows[1:]:
                cells = row.find_all(['td', 'th'])
                if len(cells) < 2:  # Need at least 2 columns
                    continue
                
                rate_entry = self._extract_rate_from_row(cells, column_mapping)
                if rate_entry:
                    rates.append(rate_entry)
        
        except Exception as e:
            logger.warning(f"Error parsing rate table: {str(e)}")
        
        return rates
    
    def _identify_columns(self, header_row: Tag) -> Dict[str, int]:
        """
        Identify which columns contain which type of data.
        
        Args:
            header_row: The header row of the table
            
        Returns:
            Dictionary mapping column types to column indices
        """
        column_mapping = {}
        cells = header_row.find_all(['th', 'td'])
        
        for i, cell in enumerate(cells):
            cell_text = cell.get_text().lower().strip()
            
            # Identify tenure column
            if any(word in cell_text for word in ['tenure', 'period', 'term', 'maturity']):
                column_mapping['tenure'] = i
            
            # Identify general rate column (prioritize non-senior citizen rates)
            elif any(word in cell_text for word in ['rate', 'interest', '%']) and 'senior' not in cell_text:
                if 'general' not in column_mapping:
                    column_mapping['general'] = i
            
            # Identify senior citizen rate column
            elif 'senior' in cell_text and any(word in cell_text for word in ['rate', 'interest', '%']):
                column_mapping['senior'] = i
            
            # Identify amount column
            elif any(word in cell_text for word in ['amount', 'deposit', 'minimum', 'maximum']):
                column_mapping['amount'] = i
            
            # Identify conditions/terms column
            elif any(word in cell_text for word in ['condition', 'term', 'note', 'remark', 'special']):
                column_mapping['conditions'] = i
        
        return column_mapping
    
    def _extract_rate_from_row(self, cells: List[Tag], column_mapping: Dict[str, int]) -> Optional[RateEntry]:
        """
        Extract a rate entry from a table row.
        
        Args:
            cells: List of table cells in the row
            column_mapping: Mapping of column types to indices
            
        Returns:
            RateEntry object or None if extraction failed
        """
        try:
            # Extract tenure
            tenure = self._extract_tenure(cells, column_mapping)
            if not tenure:
                return None
            
            # Extract general rate
            general_rate = self._extract_rate_value(cells, column_mapping, 'general')
            if general_rate is None:
                return None
            
            # Extract senior citizen rate (optional)
            senior_rate = self._extract_rate_value(cells, column_mapping, 'senior')
            
            # Extract amount information (optional)
            min_amount, max_amount = self._extract_amount_range(cells, column_mapping)
            
            # Apply amount filtering for deposits up to 2 Crores
            if not self._is_within_amount_limit(min_amount, max_amount):
                return None
            
            # Extract special conditions and terms
            special_conditions = self._extract_special_conditions(cells, column_mapping)
            
            return RateEntry(
                tenure=tenure,
                general_rate=general_rate,
                senior_citizen_rate=senior_rate,
                min_amount=min_amount,
                max_amount=max_amount,
                special_conditions=special_conditions
            )
            
        except Exception as e:
            logger.warning(f"Error extracting rate from row: {str(e)}")
            return None
    
    def _extract_tenure(self, cells: List[Tag], column_mapping: Dict[str, int]) -> Optional[str]:
        """Extract tenure information from table cells."""
        if 'tenure' in column_mapping:
            cell_text = cells[column_mapping['tenure']].get_text().strip()
        else:
            # Try to find tenure in any cell
            cell_text = ' '.join(cell.get_text().strip() for cell in cells)
        
        # Clean and normalize tenure text
        tenure = re.sub(r'\s+', ' ', cell_text).strip()
        
        # Check if it looks like a valid tenure
        if any(re.search(pattern, tenure, re.IGNORECASE) for pattern in self.tenure_patterns):
            return tenure
        
        return None
    
    def _extract_rate_value(self, cells: List[Tag], column_mapping: Dict[str, int], rate_type: str) -> Optional[float]:
        """Extract rate value from table cells."""
        if rate_type in column_mapping:
            cell_text = cells[column_mapping[rate_type]].get_text().strip()
        else:
            # If no specific column mapping, try to find rate in any cell
            cell_text = ' '.join(cell.get_text().strip() for cell in cells)
        
        # Extract numeric rate value
        for pattern in self.rate_patterns:
            match = re.search(pattern, cell_text, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        
        return None
    
    def _extract_amount_range(self, cells: List[Tag], column_mapping: Dict[str, int]) -> Tuple[Optional[int], Optional[int]]:
        """Extract amount range information from table cells."""
        if 'amount' not in column_mapping:
            return None, None
        
        cell_text = cells[column_mapping['amount']].get_text().strip()
        
        # Look for amount patterns (in lakhs, crores, or rupees)
        amount_patterns = [
            r'(\d+(?:\.\d+)?)\s*(?:lakh|lac)s?',
            r'(\d+(?:\.\d+)?)\s*crores?',
            r'(\d+(?:,\d+)*)\s*(?:rupees?|rs\.?|₹)?'
        ]
        
        min_amount = None
        max_amount = None
        
        for pattern in amount_patterns:
            matches = re.findall(pattern, cell_text, re.IGNORECASE)
            if matches:
                try:
                    amounts = []
                    for match in matches:
                        amount_str = match.replace(',', '')
                        amount = float(amount_str)
                        
                        # Convert to rupees
                        if 'lakh' in cell_text.lower() or 'lac' in cell_text.lower():
                            amount *= 100000
                        elif 'crore' in cell_text.lower():
                            amount *= 10000000
                        
                        amounts.append(int(amount))
                    
                    if amounts:
                        min_amount = min(amounts)
                        max_amount = max(amounts) if len(amounts) > 1 else None
                        
                except ValueError:
                    continue
        
        return min_amount, max_amount
    
    def _is_within_amount_limit(self, min_amount: Optional[int], max_amount: Optional[int]) -> bool:
        """
        Check if the amount range is within the 2 Crore limit.
        
        Args:
            min_amount: Minimum deposit amount
            max_amount: Maximum deposit amount
            
        Returns:
            True if within limit, False otherwise
        """
        # If no amount information, assume it's within limit
        if min_amount is None and max_amount is None:
            return True
        
        # If minimum amount exceeds 2 Crores, exclude this rate
        if min_amount and min_amount > self.config.extraction.max_deposit_amount:
            return False
        
        # If maximum amount is specified and exceeds 2 Crores, 
        # we still include it as it covers amounts up to 2 Crores
        return True
    
    def _extract_special_conditions(self, cells: List[Tag], column_mapping: Dict[str, int]) -> Optional[str]:
        """
        Extract special conditions and terms from table cells.
        
        Args:
            cells: List of table cells in the row
            column_mapping: Mapping of column types to indices
            
        Returns:
            Special conditions text or None
        """
        conditions_text = ""
        
        # Check if there's a dedicated conditions column
        if 'conditions' in column_mapping:
            conditions_text = cells[column_mapping['conditions']].get_text().strip()
        
        # Also check all cells for common condition indicators
        all_text = ' '.join(cell.get_text().strip() for cell in cells)
        
        # Look for common condition patterns
        condition_patterns = [
            r'minimum\s+(?:deposit|amount)?\s*:?\s*[₹\d,.\s]+',
            r'maximum\s+(?:deposit|amount)?\s*:?\s*[₹\d,.\s]+',
            r'(?:subject\s+to|conditions?\s*:)',
            r'(?:terms?\s+(?:and|&)\s+conditions?)',
            r'(?:special\s+(?:rate|offer|condition))',
            r'(?:additional\s+(?:benefit|rate))',
            r'(?:penalty|premature\s+withdrawal)',
            r'(?:auto\s+renewal|reinvestment)'
        ]
        
        found_conditions = []
        for pattern in condition_patterns:
            matches = re.findall(pattern, all_text, re.IGNORECASE)
            found_conditions.extend(matches)
        
        # Combine conditions from dedicated column and pattern matching
        if conditions_text and found_conditions:
            combined_conditions = f"{conditions_text}; {'; '.join(found_conditions)}"
        elif conditions_text:
            combined_conditions = conditions_text
        elif found_conditions:
            combined_conditions = '; '.join(found_conditions)
        else:
            combined_conditions = None
        
        # Clean up and return
        if combined_conditions:
            # Remove excessive whitespace and normalize
            combined_conditions = re.sub(r'\s+', ' ', combined_conditions).strip()
            # Limit length to avoid extremely long conditions
            if len(combined_conditions) > 500:
                combined_conditions = combined_conditions[:497] + "..."
            return combined_conditions
        
        return None
    
    def categorize_rates_by_type(self, rates: List[RateEntry]) -> Dict[str, List[RateEntry]]:
        """
        Categorize rates by type (general vs senior citizen).
        
        Args:
            rates: List of rate entries to categorize
            
        Returns:
            Dictionary with 'general' and 'senior_citizen' keys containing respective rates
        """
        categorized = {
            'general': [],
            'senior_citizen': [],
            'both': []  # Rates that have both general and senior citizen information
        }
        
        for rate in rates:
            if rate.senior_citizen_rate is not None:
                if rate.general_rate != rate.senior_citizen_rate:
                    categorized['both'].append(rate)
                else:
                    # If rates are the same, treat as general
                    categorized['general'].append(rate)
            else:
                categorized['general'].append(rate)
        
        return categorized
    
    def filter_rates_by_amount(self, rates: List[RateEntry], max_amount: int = None) -> List[RateEntry]:
        """
        Filter rates to include only those within the specified amount limit.
        
        Args:
            rates: List of rate entries to filter
            max_amount: Maximum amount limit (defaults to config value)
            
        Returns:
            Filtered list of rate entries
        """
        if max_amount is None:
            max_amount = self.config.extraction.max_deposit_amount
        
        filtered_rates = []
        for rate in rates:
            if self._is_within_amount_limit(rate.min_amount, rate.max_amount):
                # If the rate has a max_amount that exceeds our limit,
                # adjust it to our limit
                if rate.max_amount and rate.max_amount > max_amount:
                    # Create a new rate entry with adjusted max_amount
                    adjusted_rate = RateEntry(
                        tenure=rate.tenure,
                        general_rate=rate.general_rate,
                        senior_citizen_rate=rate.senior_citizen_rate,
                        min_amount=rate.min_amount,
                        max_amount=max_amount,
                        special_conditions=rate.special_conditions
                    )
                    filtered_rates.append(adjusted_rate)
                else:
                    filtered_rates.append(rate)
        
        return filtered_rates
    
    def _try_parsing_strategies(self, html_content: str, result: FDRateData) -> bool:
        """
        Try different parsing strategies to extract rates from HTML content.
        
        Args:
            html_content: HTML content to parse
            result: FDRateData object to populate with extracted rates
            
        Returns:
            True if any strategy succeeded, False otherwise
        """
        strategies = [
            self._strategy_table_parsing,
            self._strategy_div_parsing,
            self._strategy_list_parsing,
            self._strategy_text_pattern_parsing
        ]
        
        for i, strategy in enumerate(strategies):
            try:
                logger.info(f"Trying parsing strategy {i + 1}: {strategy.__name__}")
                rates = strategy(html_content)
                
                if rates:
                    result.rates.extend(rates)
                    logger.info(f"Strategy {i + 1} succeeded: extracted {len(rates)} rates")
                    return True
                else:
                    logger.info(f"Strategy {i + 1} found no rates")
                    
            except Exception as e:
                logger.warning(f"Strategy {i + 1} failed: {str(e)}")
                continue
        
        return False
    
    def _strategy_table_parsing(self, html_content: str) -> List[RateEntry]:
        """
        Strategy 1: Traditional table parsing (existing method).
        
        Args:
            html_content: HTML content to parse
            
        Returns:
            List of extracted rate entries
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Check if this is Central Bank and use special parser
        if hasattr(self, '_current_url') and self._is_central_bank(self._current_url):
            logger.info("Using Central Bank-specific table parser")
            return self._parse_central_bank_table(soup)
        
        # Check if this is Federal Bank and use special parser
        if hasattr(self, '_current_url') and self._is_federal_bank(self._current_url):
            logger.info("Using Federal Bank-specific table parser")
            return self._parse_federal_bank_table(soup)
        
        # Check if this is PNB and use special parser
        if hasattr(self, '_current_url') and self._is_pnb_bank(self._current_url):
            logger.info("Using PNB-specific table parser")
            return self._parse_pnb_bank_table(soup)
        
        # Check if this is UCO Bank and use special parser
        if hasattr(self, '_current_url') and self._is_uco_bank(self._current_url):
            logger.info("Using UCO Bank-specific table parser")
            return self._parse_uco_bank_table(soup)
        
        # Check if this is HDFC Bank and use special parser
        if hasattr(self, '_current_url') and self._is_hdfc_bank(self._current_url):
            logger.info("Using HDFC Bank-specific table parser")
            return self._parse_hdfc_bank_table(soup)
        
        # Check if this is Bank of Maharashtra and use special parser
        if hasattr(self, '_current_url') and self._is_bank_of_maharashtra(self._current_url):
            logger.info("Using Bank of Maharashtra-specific table parser")
            return self._parse_bank_of_maharashtra_table(soup)
        
        # Check if this is Bank of Baroda and use special parser
        if hasattr(self, '_current_url') and self._is_bank_of_baroda(self._current_url):
            logger.info("Using Bank of Baroda-specific table parser")
            return self._parse_bank_of_baroda_table(soup)
        
        # Check if this is Canara Bank and use special parser
        if hasattr(self, '_current_url') and self._is_canara_bank(self._current_url):
            logger.info("Using Canara Bank-specific table parser")
            return self._parse_canara_bank_table(soup)
        
        # Check if this is AU Small Finance Bank and use special parser
        if hasattr(self, '_current_url') and self._is_au_small_finance_bank(self._current_url):
            logger.info("Using AU Small Finance Bank-specific table parser")
            return self._parse_au_small_finance_bank_table(soup)
        
        # Check if this is Union Bank and use special parser
        if hasattr(self, '_current_url') and self._is_union_bank(self._current_url):
            logger.info("Using Union Bank-specific table parser")
            return self._parse_union_bank_table(soup)
        
        # Check if this is Shivalik Bank and use special parser
        if hasattr(self, '_current_url') and self._is_shivalik_bank(self._current_url):
            logger.info("Using Shivalik Bank-specific table parser")
            return self._parse_shivalik_bank_table(soup)
        
        # Check if this is IndusInd Bank and use special parser
        if hasattr(self, '_current_url') and self._is_indusind_bank(self._current_url):
            logger.info("Using IndusInd Bank-specific table parser")
            return self._parse_indusind_bank_table(soup)
        
        # Check if this is IDFC FIRST Bank and use special parser
        if hasattr(self, '_current_url') and self._is_idfc_first_bank(self._current_url):
            logger.info("Using IDFC FIRST Bank-specific table parser")
            return self._parse_idfc_first_bank_table(soup)
        
        rate_tables = self._identify_rate_tables(soup)
        
        rates = []
        for table in rate_tables:
            # Check if this is SBI bank and use special parser
            if hasattr(self, '_current_url') and self._is_sbi_bank(self._current_url):
                logger.info("Using SBI-specific table parser")
                extracted_rates = self._parse_sbi_table(table)
            else:
                extracted_rates = self._parse_rate_table(table)
            rates.extend(extracted_rates)
        
        return rates
    
    def _strategy_div_parsing(self, html_content: str) -> List[RateEntry]:
        """
        Strategy 2: Parse rates from div-based layouts (common in modern websites).
        
        Args:
            html_content: HTML content to parse
            
        Returns:
            List of extracted rate entries
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        rates = []
        
        # Look for div containers that might contain rate information
        rate_containers = soup.find_all('div', class_=re.compile(r'rate|deposit|fd|interest', re.I))
        
        for container in rate_containers:
            container_text = container.get_text()
            
            # Check if this container has rate-like content
            if any(indicator in container_text.lower() for indicator in self.rate_table_indicators):
                rate_entry = self._extract_rate_from_text(container_text)
                if rate_entry:
                    rates.append(rate_entry)
        
        return rates
    
    def _strategy_list_parsing(self, html_content: str) -> List[RateEntry]:
        """
        Strategy 3: Parse rates from list structures (ul, ol, li).
        
        Args:
            html_content: HTML content to parse
            
        Returns:
            List of extracted rate entries
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        rates = []
        
        # Look for lists that might contain rate information
        lists = soup.find_all(['ul', 'ol'])
        
        for list_elem in lists:
            list_text = list_elem.get_text().lower()
            
            # Check if this list contains rate information
            if any(indicator in list_text for indicator in self.rate_table_indicators):
                list_items = list_elem.find_all('li')
                
                for item in list_items:
                    item_text = item.get_text()
                    rate_entry = self._extract_rate_from_text(item_text)
                    if rate_entry:
                        rates.append(rate_entry)
        
        return rates
    
    def _strategy_text_pattern_parsing(self, html_content: str) -> List[RateEntry]:
        """
        Strategy 4: Parse rates using text patterns and regex (fallback method).
        
        Args:
            html_content: HTML content to parse
            
        Returns:
            List of extracted rate entries
        """
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text()
        rates = []
        
        # Look for patterns like "1 Year: 6.5%" or "12 months - 7.25%"
        pattern = r'(\d+\s*(?:year|yr|month|mon|day)s?)\s*[:\-–]\s*(\d+\.?\d*)\s*%'
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        for tenure_text, rate_text in matches:
            try:
                rate_value = float(rate_text)
                
                # Create a basic rate entry
                rate_entry = RateEntry(
                    tenure=tenure_text.strip(),
                    general_rate=rate_value
                )
                
                # Check if it's within our amount limits (assume it is if no amount specified)
                if self._is_within_amount_limit(None, None):
                    rates.append(rate_entry)
                    
            except ValueError:
                continue
        
        return rates
    
    def _extract_rate_from_text(self, text: str) -> Optional[RateEntry]:
        """
        Extract a rate entry from plain text using pattern matching.
        
        Args:
            text: Text content to parse
            
        Returns:
            RateEntry object or None if extraction failed
        """
        # Look for tenure patterns
        tenure = None
        for pattern in self.tenure_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                tenure = match.group(0).strip()
                break
        
        if not tenure:
            return None
        
        # Look for rate patterns
        general_rate = None
        senior_rate = None
        
        for pattern in self.rate_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    rates_found = [float(match) for match in matches]
                    
                    # If we find multiple rates, try to distinguish general vs senior
                    if len(rates_found) == 1:
                        general_rate = rates_found[0]
                    elif len(rates_found) == 2:
                        # Assume first is general, second is senior citizen
                        general_rate = rates_found[0]
                        senior_rate = rates_found[1]
                    else:
                        # Take the first rate as general
                        general_rate = rates_found[0]
                    
                    break
                    
                except ValueError:
                    continue
        
        if general_rate is None:
            return None
        
        # Extract special conditions if present
        special_conditions = None
        if any(word in text.lower() for word in ['condition', 'term', 'minimum', 'maximum', 'special']):
            # Limit the conditions text to avoid too much noise
            if len(text) <= 200:
                special_conditions = text.strip()
        
        return RateEntry(
            tenure=tenure,
            general_rate=general_rate,
            senior_citizen_rate=senior_rate,
            special_conditions=special_conditions
        )