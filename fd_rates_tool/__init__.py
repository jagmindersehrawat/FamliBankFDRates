"""
Bank FD Rates Tool - A web scraping tool for extracting Fixed Deposit rates from bank websites.

This package provides functionality to:
- Read bank information from Excel files
- Discover FD rate pages on bank websites
- Extract structured rate data
- Output results in structured formats
"""

__version__ = "1.0.0"
__author__ = "FD Rates Tool Team"

# Import main classes for easy access
from .fd_rate_extractor import FDRateExtractor
from .config import Config
from .core.models import BankInfo, FDRateData, RateEntry, ExtractionSummary

__all__ = [
    'FDRateExtractor',
    'Config', 
    'BankInfo',
    'FDRateData',
    'RateEntry',
    'ExtractionSummary'
]