"""Excel reader component for the FD Rates Tool."""

import os
import logging
from typing import List, Optional
import pandas as pd
from pathlib import Path

from .models import BankInfo
from ..config import Config


logger = logging.getLogger(__name__)


class ExcelReaderError(Exception):
    """Custom exception for Excel reading errors."""
    pass


class ExcelReader:
    """Handles reading bank information from Excel files."""
    
    def __init__(self, config: Optional[Config] = None):
        """Initialize the Excel reader with configuration."""
        self.config = config or Config()
        self.excel_file_path = self.config.extraction.excel_file_path
        self.bank_name_column = self.config.extraction.bank_name_column
        self.fd_rates_url_column = "G"  # Column G contains FD_Rates_URL
    
    def read_bank_data(self, file_path: Optional[str] = None) -> List[BankInfo]:
        """
        Read bank data from the Excel file.
        
        Args:
            file_path: Optional path to Excel file. Uses config default if not provided.
            
        Returns:
            List of BankInfo objects containing bank names and URLs.
            
        Raises:
            ExcelReaderError: If file cannot be read or is invalid.
        """
        target_file = file_path or self.excel_file_path
        
        logger.info(f"Reading bank data from: {target_file}")
        
        # Validate file exists and is accessible
        if not self.validate_file_structure(target_file):
            raise ExcelReaderError(f"File validation failed for: {target_file}")
        
        try:
            # Read Excel file with read-only access
            # Using engine='openpyxl' for .xlsx files
            # Read columns: bank_name (C), website (F), FD_Rates_URL (G)
            
            df = pd.read_excel(
                target_file,
                engine='openpyxl',
                header=0,  # First row contains headers
                dtype=str  # Read as strings to preserve data integrity
            )
            
            logger.info(f"Successfully read Excel file with {len(df)} rows")
            
            # Extract bank information from the DataFrame
            bank_data = self._extract_bank_info(df)
            
            logger.info(f"Extracted {len(bank_data)} valid bank entries")
            return bank_data
            
        except FileNotFoundError:
            error_msg = f"Excel file not found: {target_file}"
            logger.error(error_msg)
            raise ExcelReaderError(error_msg)
            
        except PermissionError:
            error_msg = f"Permission denied accessing file: {target_file}"
            logger.error(error_msg)
            raise ExcelReaderError(error_msg)
            
        except pd.errors.EmptyDataError:
            error_msg = f"Excel file is empty: {target_file}"
            logger.error(error_msg)
            raise ExcelReaderError(error_msg)
            
        except Exception as e:
            error_msg = f"Error reading Excel file {target_file}: {str(e)}"
            logger.error(error_msg)
            raise ExcelReaderError(error_msg)
    
    def validate_file_structure(self, file_path: str) -> bool:
        """
        Validate that the Excel file exists and has the expected structure.
        
        Args:
            file_path: Path to the Excel file to validate.
            
        Returns:
            True if file is valid, False otherwise.
        """
        try:
            # Check if file exists
            if not os.path.exists(file_path):
                logger.error(f"File does not exist: {file_path}")
                return False
            
            # Check if file is readable
            if not os.access(file_path, os.R_OK):
                logger.error(f"File is not readable: {file_path}")
                return False
            
            # Check file extension
            file_ext = Path(file_path).suffix.lower()
            if file_ext not in ['.xlsx', '.xls']:
                logger.error(f"Invalid file extension: {file_ext}. Expected .xlsx or .xls")
                return False
            
            # Try to read just the header to validate structure
            try:
                df_header = pd.read_excel(
                    file_path,
                    engine='openpyxl' if file_ext == '.xlsx' else 'xlrd',
                    nrows=0  # Read only headers
                )
                
                # Check if we have enough columns (Column F should exist)
                if len(df_header.columns) < 6:  # F is the 6th column (0-indexed: 5)
                    logger.error(f"File does not have enough columns. Expected at least 6, found {len(df_header.columns)}")
                    return False
                
                logger.debug(f"File validation successful for: {file_path}")
                return True
                
            except Exception as e:
                logger.error(f"Error validating file structure: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"Unexpected error during file validation: {str(e)}")
            return False
    
    def _extract_bank_info(self, df: pd.DataFrame) -> List[BankInfo]:
        """
        Extract bank information from the DataFrame.
        
        Args:
            df: DataFrame containing bank data.
            
        Returns:
            List of BankInfo objects.
        """
        bank_data = []
        
        # Check if required columns exist
        if 'bank_name' not in df.columns:
            logger.error("Column 'bank_name' not found in Excel file")
            return bank_data
        
        if 'website' not in df.columns:
            logger.error("Column 'website' not found in Excel file")
            return bank_data
        
        has_fd_url_column = 'FD_Rates_URL' in df.columns
        
        for index, row in df.iterrows():
            try:
                bank_name = row.get('bank_name', '')
                website = row.get('website', '')
                fd_rates_url = row.get('FD_Rates_URL', '') if has_fd_url_column else ''
                
                # Skip if bank name is empty
                if pd.isna(bank_name) or not str(bank_name).strip():
                    logger.debug(f"Skipping row {index + 2}: empty bank name")
                    continue
                
                # Clean values
                bank_name = str(bank_name).strip()
                website = str(website).strip() if not pd.isna(website) else ''
                fd_rates_url = str(fd_rates_url).strip() if not pd.isna(fd_rates_url) else ''
                
                # Skip banks without FD_Rates_URL (as per requirement)
                if not fd_rates_url:
                    logger.debug(f"Skipping {bank_name}: no FD_Rates_URL provided")
                    continue
                
                # Create BankInfo object
                bank_info = BankInfo(
                    name=bank_name,
                    base_url=website,
                    fd_rates_url=fd_rates_url
                )
                
                bank_data.append(bank_info)
                logger.debug(f"Added bank: {bank_info.name} -> FD URL: {bank_info.fd_rates_url}")
                
            except Exception as e:
                logger.warning(f"Error processing row {index + 2}: {str(e)}")
                continue
        
        return bank_data
    
    def _parse_bank_cell(self, cell_value: str, row_number: int) -> Optional[BankInfo]:
        """
        Parse a cell value to extract bank name and URL.
        
        This method handles different formats that might be present in Column F:
        - Just a URL: "https://www.bankname.com"
        - Bank name with URL: "Bank Name - https://www.bankname.com"
        - Bank name only: "Bank Name"
        
        Args:
            cell_value: The raw cell value as string.
            row_number: Row number for logging purposes.
            
        Returns:
            BankInfo object if parsing successful, None otherwise.
        """
        try:
            # Check if cell contains a URL (basic check for http/https)
            if 'http' in cell_value.lower():
                # Try to separate bank name and URL
                if ' - ' in cell_value:
                    parts = cell_value.split(' - ', 1)
                    bank_name = parts[0].strip()
                    base_url = parts[1].strip()
                elif '\t' in cell_value:
                    parts = cell_value.split('\t', 1)
                    bank_name = parts[0].strip()
                    base_url = parts[1].strip()
                else:
                    # Assume the whole value is a URL, extract bank name from domain
                    base_url = cell_value.strip()
                    bank_name = self._extract_bank_name_from_url(base_url)
            else:
                # No URL found, treat as bank name only
                bank_name = cell_value.strip()
                base_url = ""
                logger.warning(f"Row {row_number}: No URL found for bank '{bank_name}'")
            
            # Validate that we have at least a bank name
            if not bank_name:
                logger.warning(f"Row {row_number}: Could not extract bank name from '{cell_value}'")
                return None
            
            # Create BankInfo object (it will handle URL formatting in __post_init__)
            return BankInfo(name=bank_name, base_url=base_url)
            
        except Exception as e:
            logger.warning(f"Row {row_number}: Error parsing cell value '{cell_value}': {str(e)}")
            return None
    
    def _extract_bank_name_from_url(self, url: str) -> str:
        """
        Extract a bank name from a URL by parsing the domain.
        
        Args:
            url: The URL to extract bank name from.
            
        Returns:
            Extracted bank name or the domain if extraction fails.
        """
        try:
            from urllib.parse import urlparse
            
            parsed = urlparse(url if url.startswith(('http://', 'https://')) else f'https://{url}')
            domain = parsed.netloc.lower()
            
            # Remove common prefixes
            if domain.startswith('www.'):
                domain = domain[4:]
            
            # Remove common suffixes and extract bank name
            if domain.endswith('.com'):
                domain = domain[:-4]
            elif domain.endswith('.co.in'):
                domain = domain[:-5]
            elif domain.endswith('.in'):
                domain = domain[:-3]
            
            # Capitalize first letter of each word
            bank_name = domain.replace('.', ' ').replace('-', ' ').title()
            
            return bank_name if bank_name else url
            
        except Exception:
            return url