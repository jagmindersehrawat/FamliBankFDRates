"""Cache manager for storing and retrieving discovered URLs."""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, Optional
from pathlib import Path

from ..config import Config


logger = logging.getLogger(__name__)


class CacheManager:
    """Manages caching of discovered URLs and other data."""
    
    def __init__(self, config: Config):
        """Initialize the cache manager.
        
        Args:
            config: Configuration object containing cache settings
        """
        self.config = config
        self.cache_dir = Path(config.cache.cache_dir)
        self.url_cache_file = self.cache_dir / config.cache.url_cache_file
        self.cache_expiry_hours = config.cache.cache_expiry_hours
        
        # Create cache directory if it doesn't exist
        if config.cache.enable_cache:
            self._ensure_cache_dir()
    
    def get_cached_url(self, bank_name: str) -> Optional[str]:
        """Get cached FD URL for a bank.
        
        Args:
            bank_name: Name of the bank
            
        Returns:
            Cached URL if found and valid, None otherwise
        """
        if not self.config.cache.enable_cache:
            return None
        
        try:
            cache_data = self._load_cache()
            if not cache_data:
                return None
            
            bank_key = self._normalize_bank_name(bank_name)
            if bank_key not in cache_data:
                return None
            
            entry = cache_data[bank_key]
            
            # Check if cache entry is still valid
            if self._is_cache_expired(entry.get('timestamp')):
                logger.debug(f"Cache expired for {bank_name}")
                return None
            
            url = entry.get('fd_url')
            if url:
                logger.info(f"Using cached URL for {bank_name}: {url}")
                return url
            
        except Exception as e:
            logger.error(f"Error retrieving cached URL for {bank_name}: {str(e)}")
        
        return None
    
    def cache_url(self, bank_name: str, base_url: str, fd_url: str) -> bool:
        """Cache a discovered FD URL for a bank.
        
        Args:
            bank_name: Name of the bank
            base_url: Base URL of the bank website
            fd_url: Discovered FD rates URL
            
        Returns:
            True if caching was successful, False otherwise
        """
        if not self.config.cache.enable_cache:
            return False
        
        try:
            cache_data = self._load_cache() or {}
            
            bank_key = self._normalize_bank_name(bank_name)
            cache_data[bank_key] = {
                'bank_name': bank_name,
                'base_url': base_url,
                'fd_url': fd_url,
                'timestamp': datetime.now().isoformat(),
                'discovery_method': 'url_discovery_engine'
            }
            
            self._save_cache(cache_data)
            logger.info(f"Cached URL for {bank_name}: {fd_url}")
            return True
            
        except Exception as e:
            logger.error(f"Error caching URL for {bank_name}: {str(e)}")
            return False
    
    def invalidate_cache(self, bank_name: Optional[str] = None) -> bool:
        """Invalidate cache entries.
        
        Args:
            bank_name: Specific bank to invalidate, or None to clear all cache
            
        Returns:
            True if invalidation was successful, False otherwise
        """
        if not self.config.cache.enable_cache:
            return False
        
        try:
            if bank_name is None:
                # Clear entire cache
                if self.url_cache_file.exists():
                    self.url_cache_file.unlink()
                logger.info("Cleared entire URL cache")
                return True
            else:
                # Remove specific bank entry
                cache_data = self._load_cache()
                if cache_data:
                    bank_key = self._normalize_bank_name(bank_name)
                    if bank_key in cache_data:
                        del cache_data[bank_key]
                        self._save_cache(cache_data)
                        logger.info(f"Invalidated cache for {bank_name}")
                        return True
                
        except Exception as e:
            logger.error(f"Error invalidating cache: {str(e)}")
        
        return False
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics.
        
        Returns:
            Dictionary containing cache statistics
        """
        stats = {
            'enabled': self.config.cache.enable_cache,
            'cache_dir': str(self.cache_dir),
            'total_entries': 0,
            'valid_entries': 0,
            'expired_entries': 0,
            'cache_file_size': 0
        }
        
        if not self.config.cache.enable_cache:
            return stats
        
        try:
            if self.url_cache_file.exists():
                stats['cache_file_size'] = self.url_cache_file.stat().st_size
                
                cache_data = self._load_cache()
                if cache_data:
                    stats['total_entries'] = len(cache_data)
                    
                    for entry in cache_data.values():
                        if self._is_cache_expired(entry.get('timestamp')):
                            stats['expired_entries'] += 1
                        else:
                            stats['valid_entries'] += 1
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {str(e)}")
        
        return stats
    
    def cleanup_expired_entries(self) -> int:
        """Remove expired entries from cache.
        
        Returns:
            Number of entries removed
        """
        if not self.config.cache.enable_cache:
            return 0
        
        try:
            cache_data = self._load_cache()
            if not cache_data:
                return 0
            
            original_count = len(cache_data)
            
            # Remove expired entries
            valid_entries = {}
            for key, entry in cache_data.items():
                if not self._is_cache_expired(entry.get('timestamp')):
                    valid_entries[key] = entry
            
            removed_count = original_count - len(valid_entries)
            
            if removed_count > 0:
                self._save_cache(valid_entries)
                logger.info(f"Cleaned up {removed_count} expired cache entries")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error cleaning up cache: {str(e)}")
            return 0
    
    def _ensure_cache_dir(self):
        """Ensure cache directory exists."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Could not create cache directory {self.cache_dir}: {str(e)}")
    
    def _load_cache(self) -> Optional[Dict]:
        """Load cache data from file.
        
        Returns:
            Cache data dictionary or None if loading fails
        """
        try:
            if not self.url_cache_file.exists():
                return {}
            
            with open(self.url_cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"Error loading cache from {self.url_cache_file}: {str(e)}")
            return None
    
    def _save_cache(self, cache_data: Dict) -> bool:
        """Save cache data to file.
        
        Args:
            cache_data: Dictionary containing cache data
            
        Returns:
            True if saving was successful, False otherwise
        """
        try:
            with open(self.url_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            return True
            
        except Exception as e:
            logger.error(f"Error saving cache to {self.url_cache_file}: {str(e)}")
            return False
    
    def _normalize_bank_name(self, bank_name: str) -> str:
        """Normalize bank name for use as cache key.
        
        Args:
            bank_name: Original bank name
            
        Returns:
            Normalized bank name suitable for use as dictionary key
        """
        return bank_name.lower().strip().replace(' ', '_').replace('-', '_')
    
    def _is_cache_expired(self, timestamp_str: Optional[str]) -> bool:
        """Check if a cache entry is expired.
        
        Args:
            timestamp_str: ISO format timestamp string
            
        Returns:
            True if expired, False if still valid
        """
        if not timestamp_str:
            return True
        
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            expiry_time = timestamp + timedelta(hours=self.cache_expiry_hours)
            return datetime.now() > expiry_time
            
        except Exception as e:
            logger.error(f"Error parsing timestamp {timestamp_str}: {str(e)}")
            return True  # Treat invalid timestamps as expired