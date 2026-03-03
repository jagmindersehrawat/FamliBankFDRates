"""Data formatting utilities for the FD Rates Tool."""

import json
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import logging

from .models import FDRateData, RateEntry, ExtractionSummary


logger = logging.getLogger(__name__)


class DataFormatter:
    """Handles formatting and validation of extracted FD rate data."""
    
    def __init__(self):
        """Initialize the data formatter."""
        self.required_fields = {
            'bank_name', 'source_url', 'extraction_timestamp', 
            'extraction_success', 'rates'
        }
        self.required_rate_fields = {
            'tenure', 'general_rate'
        }
    
    def validate_fd_data(self, fd_data: FDRateData) -> bool:
        """
        Validate that FD rate data contains all required fields.
        
        Args:
            fd_data: The FD rate data to validate
            
        Returns:
            bool: True if data is valid, False otherwise
        """
        try:
            # Check required fields exist and are not None/empty
            if not fd_data.bank_name or not fd_data.bank_name.strip():
                logger.error(f"Invalid bank name: {fd_data.bank_name}")
                return False
            
            if not fd_data.source_url or not fd_data.source_url.strip():
                logger.error(f"Invalid source URL: {fd_data.source_url}")
                return False
            
            if not isinstance(fd_data.extraction_timestamp, datetime):
                logger.error(f"Invalid extraction timestamp: {fd_data.extraction_timestamp}")
                return False
            
            if not isinstance(fd_data.extraction_success, bool):
                logger.error(f"Invalid extraction success flag: {fd_data.extraction_success}")
                return False
            
            # If extraction was successful, validate rates
            if fd_data.extraction_success:
                if not fd_data.rates:
                    logger.error(f"No rates found for successful extraction: {fd_data.bank_name}")
                    return False
                
                for i, rate in enumerate(fd_data.rates):
                    if not self._validate_rate_entry(rate, i):
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating FD data: {e}")
            return False
    
    def _validate_rate_entry(self, rate: RateEntry, index: int) -> bool:
        """
        Validate a single rate entry.
        
        Args:
            rate: The rate entry to validate
            index: Index of the rate entry for error reporting
            
        Returns:
            bool: True if rate entry is valid, False otherwise
        """
        try:
            # Check tenure
            if not rate.tenure or not rate.tenure.strip():
                logger.error(f"Invalid tenure at index {index}: {rate.tenure}")
                return False
            
            # Check general rate
            if not isinstance(rate.general_rate, (int, float)) or rate.general_rate < 0:
                logger.error(f"Invalid general rate at index {index}: {rate.general_rate}")
                return False
            
            # Check senior citizen rate if present
            if rate.senior_citizen_rate is not None:
                if not isinstance(rate.senior_citizen_rate, (int, float)) or rate.senior_citizen_rate < 0:
                    logger.error(f"Invalid senior citizen rate at index {index}: {rate.senior_citizen_rate}")
                    return False
            
            # Check amount ranges if present
            if rate.min_amount is not None and rate.min_amount < 0:
                logger.error(f"Invalid minimum amount at index {index}: {rate.min_amount}")
                return False
            
            if rate.max_amount is not None and rate.max_amount < 0:
                logger.error(f"Invalid maximum amount at index {index}: {rate.max_amount}")
                return False
            
            if (rate.min_amount is not None and rate.max_amount is not None and 
                rate.min_amount > rate.max_amount):
                logger.error(f"Min amount greater than max amount at index {index}: {rate.min_amount} > {rate.max_amount}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating rate entry at index {index}: {e}")
            return False
    
    def format_to_json(self, fd_data_list: List[FDRateData]) -> str:
        """
        Format FD rate data to JSON string.
        
        Args:
            fd_data_list: List of FD rate data to format
            
        Returns:
            str: JSON formatted string
        """
        try:
            formatted_data = []
            
            for fd_data in fd_data_list:
                if not self.validate_fd_data(fd_data):
                    logger.warning(f"Skipping invalid data for bank: {fd_data.bank_name}")
                    continue
                
                bank_data = {
                    'bank_name': fd_data.bank_name,
                    'source_url': fd_data.source_url,
                    'extraction_timestamp': fd_data.extraction_timestamp.isoformat(),
                    'extraction_success': fd_data.extraction_success,
                    'error_message': fd_data.error_message,
                    'rates': []
                }
                
                for rate in fd_data.rates:
                    rate_data = {
                        'tenure': rate.tenure,
                        'general_rate': rate.general_rate,
                        'senior_citizen_rate': rate.senior_citizen_rate,
                        'min_amount': rate.min_amount,
                        'max_amount': rate.max_amount,
                        'special_conditions': rate.special_conditions
                    }
                    bank_data['rates'].append(rate_data)
                
                formatted_data.append(bank_data)
            
            return json.dumps(formatted_data, indent=2, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Error formatting data to JSON: {e}")
            raise
    
    def format_to_csv(self, fd_data_list: List[FDRateData]) -> str:
        """
        Format FD rate data to CSV string.
        
        Args:
            fd_data_list: List of FD rate data to format
            
        Returns:
            str: CSV formatted string
        """
        try:
            import io
            
            output = io.StringIO()
            fieldnames = [
                'bank_name', 'source_url', 'extraction_timestamp', 'extraction_success',
                'error_message', 'tenure', 'general_rate', 'senior_citizen_rate',
                'min_amount', 'max_amount', 'special_conditions'
            ]
            
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            
            for fd_data in fd_data_list:
                if not self.validate_fd_data(fd_data):
                    logger.warning(f"Skipping invalid data for bank: {fd_data.bank_name}")
                    continue
                
                if fd_data.rates:
                    # Write one row per rate entry
                    for rate in fd_data.rates:
                        row = {
                            'bank_name': fd_data.bank_name,
                            'source_url': fd_data.source_url,
                            'extraction_timestamp': fd_data.extraction_timestamp.isoformat(),
                            'extraction_success': fd_data.extraction_success,
                            'error_message': fd_data.error_message,
                            'tenure': rate.tenure,
                            'general_rate': rate.general_rate,
                            'senior_citizen_rate': rate.senior_citizen_rate,
                            'min_amount': rate.min_amount,
                            'max_amount': rate.max_amount,
                            'special_conditions': rate.special_conditions
                        }
                        writer.writerow(row)
                else:
                    # Write one row for failed extraction
                    row = {
                        'bank_name': fd_data.bank_name,
                        'source_url': fd_data.source_url,
                        'extraction_timestamp': fd_data.extraction_timestamp.isoformat(),
                        'extraction_success': fd_data.extraction_success,
                        'error_message': fd_data.error_message,
                        'tenure': None,
                        'general_rate': None,
                        'senior_citizen_rate': None,
                        'min_amount': None,
                        'max_amount': None,
                        'special_conditions': None
                    }
                    writer.writerow(row)
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Error formatting data to CSV: {e}")
            raise
    
    def format_summary_to_json(self, summary: ExtractionSummary) -> str:
        """
        Format extraction summary to JSON string.
        
        Args:
            summary: The extraction summary to format
            
        Returns:
            str: JSON formatted summary
        """
        try:
            return json.dumps(summary.to_dict(), indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error formatting summary to JSON: {e}")
            raise
    
    def ensure_data_consistency(self, fd_data_list: List[FDRateData]) -> List[FDRateData]:
        """
        Ensure data consistency across all FD rate data entries.
        
        Args:
            fd_data_list: List of FD rate data to check
            
        Returns:
            List[FDRateData]: Cleaned and consistent data list
        """
        try:
            consistent_data = []
            
            for fd_data in fd_data_list:
                # Clean and normalize bank name
                if fd_data.bank_name:
                    fd_data.bank_name = fd_data.bank_name.strip()
                
                # Clean and normalize source URL
                if fd_data.source_url:
                    fd_data.source_url = fd_data.source_url.strip()
                
                # Ensure rates are sorted by tenure for consistency
                if fd_data.rates:
                    # Sort rates by tenure (attempt to parse numeric values)
                    fd_data.rates.sort(key=self._tenure_sort_key)
                
                # Remove duplicate rates (same tenure and amount range)
                fd_data.rates = self._remove_duplicate_rates(fd_data.rates)
                
                consistent_data.append(fd_data)
            
            return consistent_data
            
        except Exception as e:
            logger.error(f"Error ensuring data consistency: {e}")
            return fd_data_list
    
    def _tenure_sort_key(self, rate: RateEntry) -> tuple:
        """
        Generate sort key for tenure ordering.
        
        Args:
            rate: Rate entry to generate key for
            
        Returns:
            tuple: Sort key (numeric_value, unit, original_string)
        """
        try:
            tenure = rate.tenure.lower().strip()
            
            # Extract numeric value and unit
            import re
            match = re.search(r'(\d+(?:\.\d+)?)\s*(day|month|year)', tenure)
            
            if match:
                value = float(match.group(1))
                unit = match.group(2)
                
                # Convert to days for consistent sorting
                if unit == 'year':
                    value *= 365
                elif unit == 'month':
                    value *= 30
                
                return (value, unit, tenure)
            else:
                # Fallback to alphabetical sorting
                return (float('inf'), 'unknown', tenure)
                
        except Exception:
            return (float('inf'), 'unknown', rate.tenure.lower())
    
    def _remove_duplicate_rates(self, rates: List[RateEntry]) -> List[RateEntry]:
        """
        Remove duplicate rate entries based on tenure and amount range.
        
        Args:
            rates: List of rate entries
            
        Returns:
            List[RateEntry]: Deduplicated rate entries
        """
        try:
            seen = set()
            unique_rates = []
            
            for rate in rates:
                # Create a key based on tenure and amount range
                key = (
                    rate.tenure.lower().strip(),
                    rate.min_amount,
                    rate.max_amount
                )
                
                if key not in seen:
                    seen.add(key)
                    unique_rates.append(rate)
                else:
                    logger.debug(f"Removing duplicate rate: {rate.tenure}")
            
            return unique_rates
            
        except Exception as e:
            logger.error(f"Error removing duplicate rates: {e}")
            return rates