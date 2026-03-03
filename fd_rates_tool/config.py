"""Configuration settings for the FD Rates Tool."""

import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ScrapingConfig:
    """Configuration for web scraping behavior."""
    
    # Request settings
    request_timeout: int = 30
    request_delay: float = 1.0  # Delay between requests in seconds
    max_retries: int = 3
    
    # User agent and headers
    user_agent: str = "FD-Rates-Tool/1.0 (Educational Purpose)"
    headers: dict = None
    
    # Rate limiting
    respect_robots_txt: bool = True
    max_concurrent_requests: int = 5
    
    # Backoff settings
    backoff_factor: float = 2.0
    max_backoff_delay: int = 300  # 5 minutes
    
    def __post_init__(self):
        if self.headers is None:
            self.headers = {
                'User-Agent': self.user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }


@dataclass
class ExtractionConfig:
    """Configuration for data extraction."""
    
    # Excel file settings
    excel_file_path: str = "List_of_Banks.xlsx"
    bank_name_column: str = "F"
    
    # URL discovery patterns
    fd_url_patterns: List[str] = None
    
    # Rate extraction settings
    max_deposit_amount: int = 20000000  # 2 Crores in rupees
    
    # Output settings
    output_format: str = "json"  # json or csv
    success_file: str = "fd_rates_success.json"
    failure_file: str = "fd_rates_failures.json"
    summary_file: str = "extraction_summary.json"
    
    def __post_init__(self):
        if self.fd_url_patterns is None:
            self.fd_url_patterns = [
                "/fixed-deposit",
                "/fd-rates",
                "/deposits",
                "/interest-rates",
                "/retail-banking/deposits",
                "/personal/fixed-deposit",
                "/deposit-rates",
                "/term-deposit",
                "/savings-deposit"
            ]


@dataclass
class CacheConfig:
    """Configuration for caching."""
    
    enable_cache: bool = True
    cache_dir: str = ".cache"
    url_cache_file: str = "discovered_urls.json"
    cache_expiry_hours: int = 24


@dataclass
class LoggingConfig:
    """Configuration for logging."""
    
    log_level: str = "INFO"
    log_file: str = "fd_rates_tool.log"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    max_log_size: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5


class Config:
    """Main configuration class that combines all settings."""
    
    def __init__(self):
        self.scraping = ScrapingConfig()
        self.extraction = ExtractionConfig()
        self.cache = CacheConfig()
        self.logging = LoggingConfig()
    
    @classmethod
    def from_env(cls) -> 'Config':
        """Create configuration from environment variables."""
        config = cls()
        
        # Override with environment variables if present
        if os.getenv('FD_TOOL_REQUEST_TIMEOUT'):
            config.scraping.request_timeout = int(os.getenv('FD_TOOL_REQUEST_TIMEOUT'))
        
        if os.getenv('FD_TOOL_REQUEST_DELAY'):
            config.scraping.request_delay = float(os.getenv('FD_TOOL_REQUEST_DELAY'))
        
        if os.getenv('FD_TOOL_EXCEL_FILE'):
            config.extraction.excel_file_path = os.getenv('FD_TOOL_EXCEL_FILE')
        
        if os.getenv('FD_TOOL_LOG_LEVEL'):
            config.logging.log_level = os.getenv('FD_TOOL_LOG_LEVEL')
        
        return config


# Global configuration instance
default_config = Config()