#!/usr/bin/env python3
"""
Interest Period to Days Converter

This module converts textual interest period descriptions into standardized day ranges.
Handles 159+ unique period formats found in FD rates data.
"""

import pandas as pd
import re
import logging
from typing import Tuple, Optional, Dict, List
from dataclasses import dataclass
import shutil
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ConversionResult:
    """Result of converting a single period text to day range."""
    from_days: Optional[int]
    to_days: Optional[int]
    confidence: float  # 0.0 to 1.0
    pattern_matched: str
    original_text: str

@dataclass
class ConversionReport:
    """Summary report of the entire conversion process."""
    total_periods: int
    successful_conversions: int
    failed_conversions: int
    failed_periods: List[str]
    conversion_stats: Dict[str, int]

class PeriodParser:
    """Main class for parsing interest periods and converting to day ranges."""
    
    def __init__(self):
        """Initialize the parser with conversion rules and patterns."""
        # Standard conversion rules
        self.conversion_rules = {
            'month': 30,
            'year': 365
        }
        
        # Compile regex patterns for different period formats
        self.patterns = self._compile_patterns()
        
        # Statistics tracking
        self.stats = {
            'simple_day_range': 0,
            'single_day': 0,
            'month_range': 0,
            'year_range': 0,
            'mixed_period': 0,
            'special_case': 0,
            'failed': 0
        }
    
    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """Compile all regex patterns for period matching."""
        patterns = {
            # Simple day ranges: "7 to 14 Days", "46-60 days", "91 - 180 days", "7 days to 45 days"
            'simple_day_range': re.compile(
                r'(\d+)\s*(?:days?)?\s*(?:to|-|–|—)\s*(\d+)\s*(?:days?|Days?)',
                re.IGNORECASE
            ),
            
            # Single day values: "303 Days", "1895 days"
            'single_day': re.compile(
                r'^(\d+)\s*(?:days?|Days?)$',
                re.IGNORECASE
            ),
            
            # Day to year ranges: "211 days to less than 1 year", "183 days to 1 year"
            'day_to_year': re.compile(
                r'(\d+)\s*days?\s*(?:to|-|–)\s*(?:less than\s*)?(\d+)\s*(?:years?|Years?)',
                re.IGNORECASE
            ),
            
            # Days to mixed ranges: "1896 days to 10 years", "1205 days to 5 years"
            'days_to_years': re.compile(
                r'(\d+)\s*days?\s*(?:to|-|–)\s*(\d+)\s*(?:years?|Years?)',
                re.IGNORECASE
            ),
            
            # Year to days ranges: "507 Days to 2 year", "401 Days to 2 Year"
            'days_to_year_single': re.compile(
                r'(\d+)\s*(?:Days?|days?)\s*(?:to|-|–)\s*(\d+)\s*(?:year|Year)s?',
                re.IGNORECASE
            ),
            
            # Complex day ranges with special separators: "391 Days-505 Days"
            'complex_day_range': re.compile(
                r'(\d+)\s*(?:Days?|days?)\s*[-–—]\s*(\d+)\s*(?:Days?|days?)',
                re.IGNORECASE
            ),
            
            # Month ranges: "6 months to 1 year", "18 months to 36 months"
            'month_range': re.compile(
                r'(\d+)\s*(?:months?|Months?)\s*(?:to|-|–)\s*(?:less than\s*)?(\d+)\s*(?:months?|Months?)',
                re.IGNORECASE
            ),
            
            # Month to year: "6 months to less than 1 year", "9 months 1 day to < 1 Year"
            'month_to_year': re.compile(
                r'(\d+)\s*(?:months?|Months?)\s*(?:\d+\s*days?)?\s*(?:to|-|–)\s*(?:<|less than)?\s*(\d+)\s*(?:years?|Years?)',
                re.IGNORECASE
            ),
            
            # Year ranges: "1 Year to less than 2 years", "5 years and up to 10 years"
            'year_range': re.compile(
                r'(\d+)\s*(?:years?|Years?)\s*(?:and\s*)?(?:up\s*)?(?:to|-|–)\s*(?:less than\s*)?(\d+)\s*(?:years?|Years?)',
                re.IGNORECASE
            ),
            
            # Year ranges with yr/yrs abbreviation: "1 yr to less than 2 yrs", "2 yr to less than 3 years"
            'year_range_abbrev': re.compile(
                r'(\d+)\s*(?:yr|yrs)\s*(?:to|-|–)\s*(?:less than\s*)?(\d+)\s*(?:years?|yrs?|yr)',
                re.IGNORECASE
            ),
            
            # Years with "& above upto": "5 years & above upto 10 years"
            'years_above_upto': re.compile(
                r'(\d+)\s*(?:years?|yrs?)\s*(?:&|and)?\s*(?:above|&\s*above)\s*(?:upto|up\s*to)\s*(\d+)\s*(?:years?|yrs?)',
                re.IGNORECASE
            ),
            
            # Year to month ranges: "1 Year to < 15 months", "15 months to < 18 months"
            'year_to_month': re.compile(
                r'(\d+)\s*(?:Year|year)s?\s*(?:to|-|–)\s*(?:<|less than)?\s*(\d+)\s*(?:months?|Months?)',
                re.IGNORECASE
            ),
            
            # Month to month with < : "15 months to < 18 months"
            'month_to_month_less': re.compile(
                r'(\d+)\s*(?:months?|Months?)\s*(?:to|-|–)\s*(?:<|less than)\s*(\d+)\s*(?:months?|Months?)',
                re.IGNORECASE
            ),
            
            # Month with days to months: "6 months 1 day to 9 months", "12 months 1 day to 16 months"
            'month_day_to_month': re.compile(
                r'(\d+)\s*(?:months?|Months?)\s*(\d+)\s*(?:days?|Days?)\s*(?:to|-|–)\s*(\d+)\s*(?:months?|Months?)',
                re.IGNORECASE
            ),
            
            # Days to months: "91 days to 6 months"
            'days_to_months': re.compile(
                r'(\d+)\s*(?:days?|Days?)\s*(?:to|-|–)\s*(\d+)\s*(?:months?|Months?)',
                re.IGNORECASE
            ),
            
            # Mixed year-month: "1 Year 6 Months", "4 Year 7 Months"
            'mixed_year_month': re.compile(
                r'(\d+)\s*(?:Year|year)s?\s*(\d+)\s*(?:Month|month)s?',
                re.IGNORECASE
            ),
            
            # Complex year-day combinations: "2 Years 1 Day to 3 Years"
            'year_day_to_year': re.compile(
                r'(\d+)\s*(?:Years?|years?)\s*(\d+)\s*(?:Day|day)s?\s*(?:to|-|–)\s*(\d+)\s*(?:Years?|years?)',
                re.IGNORECASE
            ),
            
            # Tax saver periods: "Tax Saver (5 years)", "5Y (Tax Saver FD)", "Tax Savings Fixed Deposits (60 months)"
            'tax_saver': re.compile(
                r'(?:Tax Saver?s?|Tax Savings?|5Y).*?(?:\()?(\d+)\s*(?:years?|Y|months?)(?:\))?',
                re.IGNORECASE
            ),
            
            # Special 5Y pattern: "5Y (Tax Saver FD)"
            'five_year_tax': re.compile(
                r'^5Y\s*\(',
                re.IGNORECASE
            ),
            
            # Month with days to year: "9 months 1 day to < 1 Year"
            'month_day_to_year': re.compile(
                r'(\d+)\s*(?:months?|Months?)\s*(\d+)\s*(?:days?|Days?)\s*(?:to|-|–)\s*(?:<|less than)?\s*(\d+)\s*(?:years?|Years?)',
                re.IGNORECASE
            ),
            
            # Comparative ranges: "> 5 years to 1894 days"
            'comparative': re.compile(
                r'>\s*(\d+)\s*(?:years?|Year)s?\s*(?:to|-)\s*(\d+)\s*(?:days?|Days?)',
                re.IGNORECASE
            ),
            
            # Above/below qualifiers: "Above 3 Years up to below 61 Months"
            'above_below': re.compile(
                r'(?:Above|above)\s*(\d+)\s*(?:Years?|years?)\s*(?:up\s*to\s*)?(?:below|below)\s*(\d+)\s*(?:Months?|months?)',
                re.IGNORECASE
            ),
            
            # Special <= patterns: "90 days <= 6 months", "6 months 1 day <=9 months"
            'less_equal': re.compile(
                r'(\d+)\s*(?:days?|months?)\s*(?:\d+\s*days?)?\s*<=\s*(\d+)\s*(?:months?|years?)',
                re.IGNORECASE
            ),
            
            # Single year: "1 Year", "5 years"
            'single_year': re.compile(
                r'^(\d+)\s*(?:years?|Years?|Y)$',
                re.IGNORECASE
            ),
            
            # Single month: "6 months", "23 Months"
            'single_month': re.compile(
                r'^(\d+)\s*(?:months?|Months?)$',
                re.IGNORECASE
            )
        }
        
        return patterns
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize period text."""
        if not text:
            return text
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Standardize dashes
        text = text.replace('–', '-').replace('—', '-').replace('−', '-')
        
        # Remove parenthetical clarifications for main parsing
        # But keep the content for special cases like "Tax Saver (5 years)"
        
        return text.strip()
    
    def _convert_to_days(self, value: int, unit: str) -> int:
        """Convert a value with unit to days."""
        unit_lower = unit.lower()
        
        if 'month' in unit_lower:
            return value * self.conversion_rules['month']
        elif 'year' in unit_lower or unit_lower == 'y':
            return value * self.conversion_rules['year']
        else:  # assume days
            return value
    
    def parse_period(self, period_text: str) -> ConversionResult:
        """
        Parse a single period text and convert to day range.
        
        Args:
            period_text: The textual period description
            
        Returns:
            ConversionResult with from_days, to_days, and metadata
        """
        if not period_text:
            return ConversionResult(None, None, 0.0, 'empty', period_text)
        
        # Clean the text
        cleaned_text = self._clean_text(period_text)
        
        # Try each pattern in order of specificity
        
        # 1. Special 5Y pattern: "5Y (Tax Saver FD)"
        match = self.patterns['five_year_tax'].search(cleaned_text)
        if match:
            days = self._convert_to_days(5, 'year')  # 5Y means 5 years
            self.stats['special_case'] += 1
            return ConversionResult(days, days, 1.0, 'five_year_tax', period_text)
        
        # 2. Tax saver periods (check early due to specific format)
        match = self.patterns['tax_saver'].search(cleaned_text)
        if match:
            value = int(match.group(1))
            # Determine if it's years or months from context
            if 'month' in cleaned_text.lower():
                days = self._convert_to_days(value, 'month')
            else:
                days = self._convert_to_days(value, 'year')
            self.stats['special_case'] += 1
            return ConversionResult(days, days, 0.9, 'tax_saver', period_text)
        
        # 2. Comparative ranges: "> 5 years to 1894 days"
        match = self.patterns['comparative'].search(cleaned_text)
        if match:
            from_years = int(match.group(1))
            to_days = int(match.group(2))
            from_days = self._convert_to_days(from_years, 'year') + 1  # ">" means add 1 day
            self.stats['special_case'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'comparative', period_text)
        
        # 3. Above/below qualifiers
        match = self.patterns['above_below'].search(cleaned_text)
        if match:
            from_years = int(match.group(1))
            to_months = int(match.group(2))
            from_days = self._convert_to_days(from_years, 'year') + 1  # "above" means add 1 day
            to_days = self._convert_to_days(to_months, 'month') - 1    # "below" means subtract 1 day
            self.stats['special_case'] += 1
            return ConversionResult(from_days, to_days, 0.8, 'above_below', period_text)
        
        # 4. Complex year-day combinations: "2 Years 1 Day to 3 Years"
        match = self.patterns['year_day_to_year'].search(cleaned_text)
        if match:
            from_years = int(match.group(1))
            from_days_extra = int(match.group(2))
            to_years = int(match.group(3))
            
            from_days = self._convert_to_days(from_years, 'year') + from_days_extra
            to_days = self._convert_to_days(to_years, 'year')
            
            self.stats['mixed_period'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'year_day_to_year', period_text)
        
        # 5. Mixed year-month periods: "1 Year 6 Months"
        match = self.patterns['mixed_year_month'].search(cleaned_text)
        if match:
            years = int(match.group(1))
            months = int(match.group(2))
            days = self._convert_to_days(years, 'year') + self._convert_to_days(months, 'month')
            self.stats['mixed_period'] += 1
            return ConversionResult(days, days, 0.8, 'mixed_year_month', period_text)
        
        # 6. Day to year ranges: "211 days to less than 1 year"
        match = self.patterns['day_to_year'].search(cleaned_text)
        if match:
            from_days = int(match.group(1))
            to_years = int(match.group(2))
            to_days = self._convert_to_days(to_years, 'year')
            
            if 'less than' in cleaned_text.lower():
                to_days -= 1
            
            self.stats['mixed_period'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'day_to_year', period_text)
        
        # 7. Days to years: "1896 days to 10 years"
        match = self.patterns['days_to_years'].search(cleaned_text)
        if match:
            from_days = int(match.group(1))
            to_years = int(match.group(2))
            to_days = self._convert_to_days(to_years, 'year')
            
            self.stats['mixed_period'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'days_to_years', period_text)
        
        # 8. Days to single year: "507 Days to 2 year"
        match = self.patterns['days_to_year_single'].search(cleaned_text)
        if match:
            from_days = int(match.group(1))
            to_years = int(match.group(2))
            to_days = self._convert_to_days(to_years, 'year')
            
            self.stats['mixed_period'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'days_to_year_single', period_text)
        
        # 9. Month with days to year: "9 months 1 day to < 1 Year"
        match = self.patterns['month_day_to_year'].search(cleaned_text)
        if match:
            months = int(match.group(1))
            extra_days = int(match.group(2))
            to_years = int(match.group(3))
            
            from_days = self._convert_to_days(months, 'month') + extra_days
            to_days = self._convert_to_days(to_years, 'year')
            
            if 'less than' in cleaned_text.lower() or '<' in cleaned_text:
                to_days -= 1
            
            self.stats['mixed_period'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'month_day_to_year', period_text)
        
        # 10. Month to year: "6 months to less than 1 year"
        match = self.patterns['month_to_year'].search(cleaned_text)
        if match:
            from_months = int(match.group(1))
            to_years = int(match.group(2))
            from_days = self._convert_to_days(from_months, 'month')
            to_days = self._convert_to_days(to_years, 'year')
            
            if 'less than' in cleaned_text.lower() or '<' in cleaned_text:
                to_days -= 1
            
            self.stats['mixed_period'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'month_to_year', period_text)
        
        # 10. Month to year: "6 months to less than 1 year"
        match = self.patterns['month_to_year'].search(cleaned_text)
        if match:
            from_months = int(match.group(1))
            to_years = int(match.group(2))
            from_days = self._convert_to_days(from_months, 'month')
            to_days = self._convert_to_days(to_years, 'year')
            
            if 'less than' in cleaned_text.lower() or '<' in cleaned_text:
                to_days -= 1
            
            self.stats['mixed_period'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'month_to_year', period_text)
        
        # 11. Year to month: "1 Year to < 15 months"
        match = self.patterns['year_to_month'].search(cleaned_text)
        if match:
            from_years = int(match.group(1))
            to_months = int(match.group(2))
            from_days = self._convert_to_days(from_years, 'year')
            to_days = self._convert_to_days(to_months, 'month')
            
            if 'less than' in cleaned_text.lower() or '<' in cleaned_text:
                to_days -= 1
            
            self.stats['mixed_period'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'year_to_month', period_text)
        
        # 12. Month with days to months: "6 months 1 day to 9 months", "12 months 1 day to 16 months"
        match = self.patterns['month_day_to_month'].search(cleaned_text)
        if match:
            from_months = int(match.group(1))
            extra_days = int(match.group(2))
            to_months = int(match.group(3))
            
            from_days = self._convert_to_days(from_months, 'month') + extra_days
            to_days = self._convert_to_days(to_months, 'month')
            
            self.stats['mixed_period'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'month_day_to_month', period_text)
        
        # 13. Days to months: "91 days to 6 months"
        match = self.patterns['days_to_months'].search(cleaned_text)
        if match:
            from_days = int(match.group(1))
            to_months = int(match.group(2))
            to_days = self._convert_to_days(to_months, 'month')
            
            self.stats['mixed_period'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'days_to_months', period_text)
        
        # 14. Month to month with less than: "15 months to < 18 months"
        match = self.patterns['month_to_month_less'].search(cleaned_text)
        if match:
            from_months = int(match.group(1))
            to_months = int(match.group(2))
            from_days = self._convert_to_days(from_months, 'month')
            to_days = self._convert_to_days(to_months, 'month') - 1  # "less than" means subtract 1
            
            self.stats['month_range'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'month_to_month_less', period_text)
        
        # 15. Month ranges: "18 months to 36 months"
        match = self.patterns['month_range'].search(cleaned_text)
        if match:
            from_months = int(match.group(1))
            to_months = int(match.group(2))
            from_days = self._convert_to_days(from_months, 'month')
            to_days = self._convert_to_days(to_months, 'month')
            
            if 'less than' in cleaned_text.lower():
                to_days -= 1
            
            self.stats['month_range'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'month_range', period_text)
        
        # 16. Year ranges: "1 Year to less than 2 years"
        match = self.patterns['year_range'].search(cleaned_text)
        if match:
            from_years = int(match.group(1))
            to_years = int(match.group(2))
            from_days = self._convert_to_days(from_years, 'year')
            to_days = self._convert_to_days(to_years, 'year')
            
            if 'less than' in cleaned_text.lower():
                to_days -= 1
            
            self.stats['year_range'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'year_range', period_text)
        
        # 17. Year ranges with yr/yrs abbreviation: "1 yr to less than 2 yrs", "2 yr to less than 3 years"
        match = self.patterns['year_range_abbrev'].search(cleaned_text)
        if match:
            from_years = int(match.group(1))
            to_years = int(match.group(2))
            from_days = self._convert_to_days(from_years, 'year')
            to_days = self._convert_to_days(to_years, 'year')
            
            if 'less than' in cleaned_text.lower():
                to_days -= 1
            
            self.stats['year_range'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'year_range_abbrev', period_text)
        
        # 18. Years with "& above upto": "5 years & above upto 10 years"
        match = self.patterns['years_above_upto'].search(cleaned_text)
        if match:
            from_years = int(match.group(1))
            to_years = int(match.group(2))
            from_days = self._convert_to_days(from_years, 'year')
            to_days = self._convert_to_days(to_years, 'year')
            
            self.stats['year_range'] += 1
            return ConversionResult(from_days, to_days, 0.9, 'years_above_upto', period_text)
        
        # 19. Complex day ranges: "391 Days-505 Days"
        match = self.patterns['complex_day_range'].search(cleaned_text)
        if match:
            from_days = int(match.group(1))
            to_days = int(match.group(2))
            self.stats['simple_day_range'] += 1
            return ConversionResult(from_days, to_days, 1.0, 'complex_day_range', period_text)
        
        # 20. Simple day ranges: "7 to 14 Days", "7 days to 45 days"
        match = self.patterns['simple_day_range'].search(cleaned_text)
        if match:
            from_days = int(match.group(1))
            to_days = int(match.group(2))
            self.stats['simple_day_range'] += 1
            return ConversionResult(from_days, to_days, 1.0, 'simple_day_range', period_text)
        
        # 21. Single day values: "303 Days"
        match = self.patterns['single_day'].search(cleaned_text)
        if match:
            days = int(match.group(1))
            self.stats['single_day'] += 1
            return ConversionResult(days, days, 1.0, 'single_day', period_text)
        
        # 22. Single year: "1 Year"
        match = self.patterns['single_year'].search(cleaned_text)
        if match:
            years = int(match.group(1))
            days = self._convert_to_days(years, 'year')
            self.stats['single_day'] += 1
            return ConversionResult(days, days, 1.0, 'single_year', period_text)
        
        # 23. Single month: "6 months"
        match = self.patterns['single_month'].search(cleaned_text)
        if match:
            months = int(match.group(1))
            days = self._convert_to_days(months, 'month')
            self.stats['single_day'] += 1
            return ConversionResult(days, days, 1.0, 'single_month', period_text)
        
        # If no pattern matched, return failure
        self.stats['failed'] += 1
        logger.warning(f"Could not parse period: '{period_text}'")
        return ConversionResult(None, None, 0.0, 'failed', period_text)
    
    def validate_result(self, result: ConversionResult) -> bool:
        """Validate a conversion result for logical consistency."""
        if result.from_days is None or result.to_days is None:
            return False
        
        # Check that from_days <= to_days
        if result.from_days > result.to_days:
            logger.warning(f"Invalid range: from_days ({result.from_days}) > to_days ({result.to_days}) for '{result.original_text}'")
            return False
        
        # Check for reasonable bounds (0 to 10 years)
        max_days = 10 * 365  # 10 years
        if result.from_days < 0 or result.to_days < 0:
            logger.warning(f"Negative days found for '{result.original_text}': from={result.from_days}, to={result.to_days}")
            return False
        
        if result.from_days > max_days or result.to_days > max_days:
            logger.warning(f"Unreasonably large days found for '{result.original_text}': from={result.from_days}, to={result.to_days}")
            return False
        
        return True
    
    def convert_csv(self, input_file: str, output_file: str = None) -> ConversionReport:
        """
        Convert all periods in a CSV file and add day range columns.
        
        Args:
            input_file: Path to input CSV file
            output_file: Path to output CSV file (defaults to input_file)
            
        Returns:
            ConversionReport with statistics and failed conversions
        """
        if output_file is None:
            output_file = input_file
        
        # Create backup of original file
        backup_file = f"{input_file}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(input_file, backup_file)
        logger.info(f"Created backup: {backup_file}")
        
        # Read CSV
        try:
            df = pd.read_csv(input_file)
            logger.info(f"Loaded CSV with {len(df)} rows")
        except Exception as e:
            logger.error(f"Error reading CSV file: {e}")
            raise
        
        # Check for required column
        if 'Interest Period' not in df.columns:
            raise ValueError("CSV must contain 'Interest Period' column")
        
        # Initialize new columns
        df['Interest Period From'] = None
        df['Interest Period To'] = None
        
        # Process each period
        failed_periods = []
        successful_conversions = 0
        
        for idx, row in df.iterrows():
            period_text = row['Interest Period']
            result = self.parse_period(period_text)
            
            if self.validate_result(result):
                df.at[idx, 'Interest Period From'] = result.from_days
                df.at[idx, 'Interest Period To'] = result.to_days
                successful_conversions += 1
            else:
                failed_periods.append(period_text)
        
        # Convert to integer type where possible
        df['Interest Period From'] = df['Interest Period From'].astype('Int64')  # Nullable integer
        df['Interest Period To'] = df['Interest Period To'].astype('Int64')
        
        # Save enhanced CSV
        try:
            df.to_csv(output_file, index=False)
            logger.info(f"Saved enhanced CSV to: {output_file}")
        except Exception as e:
            logger.error(f"Error saving CSV file: {e}")
            raise
        
        # Create conversion report
        report = ConversionReport(
            total_periods=len(df),
            successful_conversions=successful_conversions,
            failed_conversions=len(failed_periods),
            failed_periods=failed_periods,
            conversion_stats=self.stats.copy()
        )
        
        return report

def main():
    """Main execution function."""
    print("=" * 70)
    print("INTEREST PERIOD TO DAYS CONVERTER")
    print("=" * 70)
    print("🎯 Goal: Convert textual periods to standardized day ranges")
    print("📊 Input: fd_rates_complete.csv")
    print("📈 Output: Enhanced CSV with 'Interest Period From' and 'Interest Period To' columns")
    print("=" * 70)
    
    # Initialize parser
    parser = PeriodParser()
    
    # Process the CSV
    input_file = 'fd_rates_complete.csv'
    output_file = 'fd_rates_with_days.csv'  # Use different output file to avoid permission issues
    
    try:
        print(f"\n🚀 Processing {input_file}...")
        report = parser.convert_csv(input_file, output_file)
        
        # Display results
        print(f"\n🎉 CONVERSION COMPLETED!")
        print(f"=" * 50)
        print(f"📊 RESULTS:")
        print(f"   Total periods processed: {report.total_periods}")
        print(f"   Successful conversions: {report.successful_conversions}")
        print(f"   Failed conversions: {report.failed_conversions}")
        print(f"   Success rate: {report.successful_conversions/report.total_periods*100:.1f}%")
        
        print(f"\n📈 CONVERSION BREAKDOWN:")
        for pattern, count in report.conversion_stats.items():
            if count > 0:
                print(f"   {pattern.replace('_', ' ').title()}: {count}")
        
        if report.failed_periods:
            print(f"\n❌ FAILED CONVERSIONS ({len(report.failed_periods)}):")
            for i, period in enumerate(report.failed_periods[:10], 1):
                print(f"   {i:2d}. {period}")
            if len(report.failed_periods) > 10:
                print(f"   ... and {len(report.failed_periods) - 10} more")
        
        print(f"\n✅ Enhanced CSV saved successfully!")
        print(f"📁 New columns added: 'Interest Period From', 'Interest Period To'")
        print("=" * 70)
        
    except Exception as e:
        print(f"💥 Error: {e}")
        logger.error(f"Conversion failed: {e}")

if __name__ == "__main__":
    main()