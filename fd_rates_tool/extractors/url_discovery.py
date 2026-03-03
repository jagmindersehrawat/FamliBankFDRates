"""URL Discovery Engine for finding FD rates pages on bank websites."""

import logging
import re
import time
from typing import List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse, parse_qs
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from ..config import Config
from ..core.models import BankInfo
from ..utils.cache_manager import CacheManager


logger = logging.getLogger(__name__)


class URLDiscoveryEngine:
    """Engine for discovering FD rates URLs on bank websites."""
    
    def __init__(self, config: Config):
        """Initialize the URL discovery engine.
        
        Args:
            config: Configuration object containing scraping settings
        """
        self.config = config
        self.cache_manager = CacheManager(config)
        self.session = requests.Session()
        self.session.headers.update(config.scraping.headers)
        
        # Compile FD-related patterns for efficiency
        self.fd_patterns = [
            re.compile(pattern, re.IGNORECASE) 
            for pattern in config.extraction.fd_url_patterns
        ]
        
        # Keywords to look for in page content
        self.fd_keywords = [
            'fixed deposit', 'fd rates', 'term deposit', 'deposit rates',
            'interest rates', 'deposit scheme', 'time deposit'
        ]
        
        # Compiled regex for finding rate tables
        self.rate_table_indicators = [
            re.compile(r'rate.*table', re.IGNORECASE),
            re.compile(r'interest.*rate', re.IGNORECASE),
            re.compile(r'deposit.*rate', re.IGNORECASE),
            re.compile(r'tenure.*rate', re.IGNORECASE)
        ]
    
    def discover_fd_urls(self, base_url: str, bank_name: str = None) -> List[str]:
        """Discover FD rates URLs for a given bank website.
        
        Args:
            base_url: The base URL of the bank website
            bank_name: Optional bank name for caching purposes
            
        Returns:
            List of discovered FD URLs, prioritized by relevance
        """
        logger.info(f"Starting URL discovery for: {base_url}")
        
        # Check cache first if bank name is provided
        if bank_name:
            cached_url = self.get_cached_url(bank_name)
            if cached_url:
                return [cached_url]
        
        discovered_urls = set()
        
        try:
            # Check robots.txt compliance
            if not self._check_robots_txt(base_url):
                logger.warning(f"Robots.txt disallows crawling for {base_url}")
                return []
            
            # Strategy 1: Pattern-based URL construction
            pattern_urls = self._discover_by_patterns(base_url)
            discovered_urls.update(pattern_urls)
            
            # Strategy 2: Sitemap analysis
            sitemap_urls = self._discover_from_sitemap(base_url)
            discovered_urls.update(sitemap_urls)
            
            # Strategy 3: Navigation crawling
            nav_urls = self._discover_from_navigation(base_url)
            discovered_urls.update(nav_urls)
            
            # Convert to list and prioritize
            url_list = list(discovered_urls)
            prioritized_urls = self._prioritize_urls(url_list)
            
            # Cache the best URL if bank name is provided and URLs were found
            if bank_name and prioritized_urls:
                self.cache_manager.cache_url(bank_name, base_url, prioritized_urls[0])
            
            logger.info(f"Discovered {len(prioritized_urls)} FD URLs for {base_url}")
            return prioritized_urls
            
        except Exception as e:
            logger.error(f"Error discovering URLs for {base_url}: {str(e)}")
            return []
    
    def get_cached_url(self, bank_name: str) -> Optional[str]:
        """Get cached FD URL for a bank.
        
        Args:
            bank_name: Name of the bank
            
        Returns:
            Cached URL if found and valid, None otherwise
        """
        return self.cache_manager.get_cached_url(bank_name)
    
    def validate_fd_page(self, url: str) -> bool:
        """Validate if a URL contains FD rate information.
        
        Args:
            url: URL to validate
            
        Returns:
            True if the page likely contains FD rates, False otherwise
        """
        try:
            response = self._make_request(url)
            if not response:
                return False
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Check for rate tables
            if self._has_rate_tables(soup):
                return True
            
            # Check for FD-related keywords in content
            text_content = soup.get_text().lower()
            keyword_count = sum(1 for keyword in self.fd_keywords if keyword in text_content)
            
            # Consider valid if multiple FD keywords are present
            return keyword_count >= 2
            
        except Exception as e:
            logger.error(f"Error validating FD page {url}: {str(e)}")
            return False
    
    def _check_robots_txt(self, base_url: str) -> bool:
        """Check if robots.txt allows crawling.
        
        Args:
            base_url: Base URL to check
            
        Returns:
            True if crawling is allowed, False otherwise
        """
        if not self.config.scraping.respect_robots_txt:
            return True
        
        try:
            parsed_url = urlparse(base_url)
            robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"
            
            rp = RobotFileParser()
            rp.set_url(robots_url)
            rp.read()
            
            user_agent = self.config.scraping.user_agent
            return rp.can_fetch(user_agent, base_url)
            
        except Exception as e:
            logger.warning(f"Could not check robots.txt for {base_url}: {str(e)}")
            return True  # Allow crawling if robots.txt check fails
    
    def _discover_by_patterns(self, base_url: str) -> Set[str]:
        """Discover URLs by constructing them from common patterns.
        
        Args:
            base_url: Base URL of the bank website
            
        Returns:
            Set of URLs constructed from patterns
        """
        discovered = set()
        
        for pattern in self.config.extraction.fd_url_patterns:
            # Try direct pattern match
            candidate_url = urljoin(base_url, pattern)
            if self._url_exists(candidate_url):
                discovered.add(candidate_url)
            
            # Try with .html extension
            html_url = urljoin(base_url, f"{pattern}.html")
            if self._url_exists(html_url):
                discovered.add(html_url)
            
            # Try with .php extension
            php_url = urljoin(base_url, f"{pattern}.php")
            if self._url_exists(php_url):
                discovered.add(php_url)
        
        return discovered
    
    def _discover_from_sitemap(self, base_url: str) -> Set[str]:
        """Discover URLs from sitemap.xml.
        
        Args:
            base_url: Base URL of the bank website
            
        Returns:
            Set of FD-related URLs from sitemap
        """
        discovered = set()
        
        try:
            parsed_url = urlparse(base_url)
            sitemap_url = f"{parsed_url.scheme}://{parsed_url.netloc}/sitemap.xml"
            
            response = self._make_request(sitemap_url)
            if not response:
                return discovered
            
            soup = BeautifulSoup(response.content, 'xml')
            
            # Extract all URLs from sitemap
            urls = soup.find_all('loc')
            for url_tag in urls:
                url = url_tag.get_text().strip()
                
                # Check if URL matches FD patterns
                for pattern in self.fd_patterns:
                    if pattern.search(url):
                        discovered.add(url)
                        break
            
        except Exception as e:
            logger.debug(f"Could not parse sitemap for {base_url}: {str(e)}")
        
        return discovered
    
    def _discover_from_navigation(self, base_url: str) -> Set[str]:
        """Discover URLs by following navigation links.
        
        Args:
            base_url: Base URL of the bank website
            
        Returns:
            Set of FD-related URLs from navigation
        """
        discovered = set()
        
        try:
            response = self._make_request(base_url)
            if not response:
                return discovered
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find navigation elements
            nav_selectors = [
                'nav a', 'header a', '.navigation a', '.menu a',
                '.navbar a', '#menu a', '#navigation a'
            ]
            
            links = []
            for selector in nav_selectors:
                links.extend(soup.select(selector))
            
            # Also check regular links that might be in main content
            links.extend(soup.find_all('a', href=True))
            
            for link in links:
                href = link.get('href')
                if not href:
                    continue
                
                # Convert relative URLs to absolute
                full_url = urljoin(base_url, href)
                
                # Check if link text or URL contains FD-related terms
                link_text = link.get_text().lower()
                
                # Check URL pattern
                url_matches = any(pattern.search(full_url) for pattern in self.fd_patterns)
                
                # Check link text for FD keywords
                text_matches = any(keyword in link_text for keyword in self.fd_keywords)
                
                if url_matches or text_matches:
                    discovered.add(full_url)
            
        except Exception as e:
            logger.debug(f"Could not parse navigation for {base_url}: {str(e)}")
        
        return discovered
    
    def _prioritize_urls(self, urls: List[str]) -> List[str]:
        """Prioritize discovered URLs based on relevance indicators.
        
        Args:
            urls: List of discovered URLs
            
        Returns:
            List of URLs sorted by priority (highest first)
        """
        def calculate_priority(url: str) -> int:
            """Calculate priority score for a URL."""
            score = 0
            url_lower = url.lower()
            
            # Higher priority for exact pattern matches
            priority_patterns = [
                ('fd-rates', 10), ('fixed-deposit', 9), ('deposit-rates', 8),
                ('interest-rates', 7), ('deposits', 6), ('term-deposit', 5)
            ]
            
            for pattern, points in priority_patterns:
                if pattern in url_lower:
                    score += points
                    break
            
            # Bonus for shorter, cleaner URLs
            if len(url.split('/')) <= 5:
                score += 2
            
            # Penalty for query parameters (often dynamic pages)
            if '?' in url:
                score -= 1
            
            return score
        
        # Sort by priority score (descending)
        prioritized = sorted(urls, key=calculate_priority, reverse=True)
        
        # Validate top candidates and reorder if needed
        validated_urls = []
        for url in prioritized:
            if self.validate_fd_page(url):
                validated_urls.append(url)
        
        # Add remaining URLs that weren't validated
        for url in prioritized:
            if url not in validated_urls:
                validated_urls.append(url)
        
        return validated_urls
    
    def _url_exists(self, url: str) -> bool:
        """Check if a URL exists and returns a successful response.
        
        Args:
            url: URL to check
            
        Returns:
            True if URL exists and is accessible, False otherwise
        """
        try:
            response = self._make_request(url, method='HEAD')
            return response is not None and response.status_code == 200
        except Exception:
            return False
    
    def _has_rate_tables(self, soup: BeautifulSoup) -> bool:
        """Check if the page contains rate tables.
        
        Args:
            soup: BeautifulSoup object of the page
            
        Returns:
            True if rate tables are found, False otherwise
        """
        # Look for tables
        tables = soup.find_all('table')
        
        for table in tables:
            table_text = table.get_text().lower()
            
            # Check for rate-related indicators
            for indicator in self.rate_table_indicators:
                if indicator.search(table_text):
                    return True
            
            # Check for common table headers
            headers = table.find_all(['th', 'td'])
            header_text = ' '.join([h.get_text().lower() for h in headers[:10]])  # First 10 cells
            
            rate_indicators = ['rate', 'interest', 'tenure', 'period', 'deposit', 'amount']
            if sum(1 for indicator in rate_indicators if indicator in header_text) >= 2:
                return True
        
        return False
    
    def _make_request(self, url: str, method: str = 'GET') -> Optional[requests.Response]:
        """Make an HTTP request with proper error handling and delays.
        
        Args:
            url: URL to request
            method: HTTP method (GET or HEAD)
            
        Returns:
            Response object if successful, None otherwise
        """
        try:
            # Implement delay between requests
            time.sleep(self.config.scraping.request_delay)
            
            if method.upper() == 'HEAD':
                response = self.session.head(
                    url, 
                    timeout=self.config.scraping.request_timeout,
                    allow_redirects=True
                )
            else:
                response = self.session.get(
                    url, 
                    timeout=self.config.scraping.request_timeout,
                    allow_redirects=True
                )
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            logger.debug(f"Request failed for {url}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error requesting {url}: {str(e)}")
            return None