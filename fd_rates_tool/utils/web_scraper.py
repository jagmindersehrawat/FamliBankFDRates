"""
Web scraping infrastructure with ethical scraping practices.

This module provides the WebScraper class that implements:
- Request delays and rate limiting
- Robots.txt compliance checking
- Proper user agent and headers
- Timeout handling
- Network error handling
- CAPTCHA and anti-bot detection
"""

import time
import logging
import requests
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from typing import Optional, Dict, Any
from dataclasses import dataclass
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import ScrapingConfig
from .logging_setup import get_logger, ErrorTracker


@dataclass
class ScrapingResult:
    """Result of a web scraping operation."""
    success: bool
    content: Optional[str] = None
    status_code: Optional[int] = None
    url: Optional[str] = None
    error_message: Optional[str] = None
    response_time: Optional[float] = None
    is_captcha_detected: bool = False
    is_rate_limited: bool = False


class WebScraper:
    """
    Ethical web scraper with comprehensive error handling and resilience.
    
    Implements requirements:
    - 6.1: Request delays and rate limiting
    - 6.2: Robots.txt compliance checking  
    - 6.3: Proper user agent and headers
    - 5.3: Timeout handling
    - 5.1: Network error handling
    - 5.4: CAPTCHA and anti-bot detection
    """
    
    def __init__(self, config: Optional[ScrapingConfig] = None, 
                 error_tracker: Optional[ErrorTracker] = None):
        """
        Initialize the WebScraper with configuration.
        
        Args:
            config: Scraping configuration. If None, uses default settings.
            error_tracker: Error tracking instance. If None, creates a new one.
        """
        self.config = config or ScrapingConfig()
        self.logger = get_logger(__name__)
        self.error_tracker = error_tracker or ErrorTracker()
        self.session = self._create_session()
        self.robots_cache: Dict[str, RobotFileParser] = {}
        self.last_request_time: Dict[str, float] = {}
        
        self.logger.info(f"WebScraper initialized with timeout={self.config.request_timeout}s, "
                        f"delay={self.config.request_delay}s")
    
    def _create_session(self) -> requests.Session:
        """
        Create a requests session with proper configuration.
        
        Returns:
            Configured requests session.
        """
        session = requests.Session()
        
        # Set headers
        session.headers.update(self.config.headers)
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=self.config.backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _get_domain(self, url: str) -> str:
        """
        Extract domain from URL for rate limiting purposes.
        
        Args:
            url: The URL to extract domain from.
            
        Returns:
            Domain string.
        """
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    
    def _enforce_rate_limit(self, url: str) -> None:
        """
        Enforce rate limiting by adding delays between requests to the same domain.
        
        Args:
            url: The URL being requested.
        """
        domain = self._get_domain(url)
        current_time = time.time()
        
        if domain in self.last_request_time:
            time_since_last = current_time - self.last_request_time[domain]
            if time_since_last < self.config.request_delay:
                sleep_time = self.config.request_delay - time_since_last
                self.logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s for {domain}")
                time.sleep(sleep_time)
        
        self.last_request_time[domain] = time.time()
    
    def _check_robots_txt(self, url: str) -> bool:
        """
        Check if the URL is allowed according to robots.txt.
        
        Args:
            url: The URL to check.
            
        Returns:
            True if allowed, False if disallowed.
        """
        if not self.config.respect_robots_txt:
            return True
        
        domain = self._get_domain(url)
        
        # Check cache first
        if domain not in self.robots_cache:
            robots_url = urljoin(domain, '/robots.txt')
            rp = RobotFileParser()
            rp.set_url(robots_url)
            
            try:
                rp.read()
                self.robots_cache[domain] = rp
                self.logger.debug(f"Loaded robots.txt for {domain}")
            except Exception as e:
                self.logger.warning(f"Could not load robots.txt for {domain}: {e}")
                # If we can't load robots.txt, assume it's allowed
                return True
        
        rp = self.robots_cache[domain]
        user_agent = self.config.user_agent
        
        is_allowed = rp.can_fetch(user_agent, url)
        if not is_allowed:
            self.logger.warning(f"robots.txt disallows access to {url} for {user_agent}")
        
        return is_allowed
    
    def _detect_captcha_or_blocking(self, content: str, status_code: int) -> tuple[bool, bool]:
        """
        Detect if the response indicates CAPTCHA or rate limiting.
        
        Args:
            content: Response content.
            status_code: HTTP status code.
            
        Returns:
            Tuple of (is_captcha_detected, is_rate_limited).
        """
        content_lower = content.lower() if content else ""
        
        # CAPTCHA detection patterns
        captcha_indicators = [
            'captcha',
            'recaptcha',
            'verify you are human',
            'security check',
            'prove you are not a robot',
            'cloudflare',
            'access denied'
        ]
        
        is_captcha = any(indicator in content_lower for indicator in captcha_indicators)
        
        # Rate limiting detection
        is_rate_limited = (
            status_code == 429 or
            status_code == 503 or
            'rate limit' in content_lower or
            'too many requests' in content_lower or
            'temporarily blocked' in content_lower
        )
        
        return is_captcha, is_rate_limited
    
    def fetch_page(self, url: str, **kwargs) -> ScrapingResult:
        """
        Fetch a web page with ethical scraping practices.
        
        Args:
            url: The URL to fetch.
            **kwargs: Additional arguments to pass to requests.get().
            
        Returns:
            ScrapingResult containing the response data and metadata.
        """
        start_time = time.time()
        
        try:
            # Check robots.txt compliance
            if not self._check_robots_txt(url):
                return ScrapingResult(
                    success=False,
                    url=url,
                    error_message="Access disallowed by robots.txt"
                )
            
            # Enforce rate limiting
            self._enforce_rate_limit(url)
            
            # Set default timeout if not provided
            if 'timeout' not in kwargs:
                kwargs['timeout'] = self.config.request_timeout
            
            self.logger.debug(f"Fetching: {url}")
            
            # Make the request
            response = self.session.get(url, **kwargs)
            response_time = time.time() - start_time
            
            # Check for CAPTCHA or rate limiting
            is_captcha, is_rate_limited = self._detect_captcha_or_blocking(
                response.text, response.status_code
            )
            
            if is_captcha:
                self.logger.warning(f"CAPTCHA detected for {url}")
                self.error_tracker.log_captcha_detection(url, f"Status: {response.status_code}")
                return ScrapingResult(
                    success=False,
                    url=url,
                    status_code=response.status_code,
                    error_message="CAPTCHA or anti-bot protection detected",
                    response_time=response_time,
                    is_captcha_detected=True
                )
            
            if is_rate_limited:
                self.logger.warning(f"Rate limiting detected for {url}")
                retry_after = response.headers.get('Retry-After')
                self.error_tracker.log_rate_limiting(url, response.status_code, retry_after)
                return ScrapingResult(
                    success=False,
                    url=url,
                    status_code=response.status_code,
                    error_message="Rate limiting detected",
                    response_time=response_time,
                    is_rate_limited=True
                )
            
            # Check if request was successful
            response.raise_for_status()
            
            self.logger.debug(f"Successfully fetched {url} in {response_time:.2f}s")
            
            return ScrapingResult(
                success=True,
                content=response.text,
                status_code=response.status_code,
                url=url,
                response_time=response_time
            )
            
        except requests.exceptions.Timeout:
            error_msg = f"Request timeout after {self.config.request_timeout}s"
            self.logger.error(f"{error_msg} for {url}")
            self.error_tracker.log_timeout_error(url, self.config.request_timeout)
            return ScrapingResult(
                success=False,
                url=url,
                error_message=error_msg,
                response_time=time.time() - start_time
            )
            
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Connection error: {str(e)}"
            self.logger.error(f"{error_msg} for {url}")
            self.error_tracker.log_network_error(url, e)
            return ScrapingResult(
                success=False,
                url=url,
                error_message=error_msg,
                response_time=time.time() - start_time
            )
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP error: {str(e)}"
            self.logger.error(f"{error_msg} for {url}")
            self.error_tracker.log_network_error(url, e)
            return ScrapingResult(
                success=False,
                url=url,
                status_code=e.response.status_code if e.response else None,
                error_message=error_msg,
                response_time=time.time() - start_time
            )
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(f"{error_msg} for {url}")
            self.error_tracker.log_network_error(url, e)
            return ScrapingResult(
                success=False,
                url=url,
                error_message=error_msg,
                response_time=time.time() - start_time
            )
    
    def fetch_with_exponential_backoff(self, url: str, max_attempts: Optional[int] = None) -> ScrapingResult:
        """
        Fetch a page with exponential backoff on rate limiting.
        
        Args:
            url: The URL to fetch.
            max_attempts: Maximum number of attempts. If None, uses config.max_retries.
            
        Returns:
            ScrapingResult from the final attempt.
        """
        if max_attempts is None:
            max_attempts = self.config.max_retries
        
        for attempt in range(max_attempts):
            result = self.fetch_page(url)
            
            if result.success or not result.is_rate_limited:
                return result
            
            if attempt < max_attempts - 1:  # Don't sleep on the last attempt
                backoff_delay = min(
                    self.config.request_delay * (self.config.backoff_factor ** attempt),
                    self.config.max_backoff_delay
                )
                self.logger.info(f"Rate limited, backing off for {backoff_delay:.2f}s (attempt {attempt + 1}/{max_attempts})")
                time.sleep(backoff_delay)
        
        return result
    
    def get_error_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive error summary from the error tracker.
        
        Returns:
            Dictionary containing error statistics and details.
        """
        return self.error_tracker.get_error_summary()
    
    def log_error_summary(self) -> None:
        """Log a summary of all errors encountered during scraping."""
        self.error_tracker.log_summary()
    
    def close(self):
        """Close the session and clean up resources."""
        if self.session:
            self.session.close()
            self.logger.debug("WebScraper session closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()