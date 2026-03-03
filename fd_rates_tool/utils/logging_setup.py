"""Logging configuration and setup utilities."""

import logging
import logging.handlers
import os
import sys
import traceback
from typing import Optional, Dict, Any
from datetime import datetime

from ..config import LoggingConfig


def setup_logging(config: Optional[LoggingConfig] = None) -> logging.Logger:
    """
    Set up logging configuration for the FD Rates Tool.
    
    Args:
        config: Logging configuration. If None, uses default settings.
    
    Returns:
        Configured logger instance.
    """
    if config is None:
        config = LoggingConfig()
    
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(config.log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Configure root logger
    logger = logging.getLogger('fd_rates_tool')
    logger.setLevel(getattr(logging, config.log_level.upper()))
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(config.log_format)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler with rotation
    if config.log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            config.log_file,
            maxBytes=config.max_log_size,
            backupCount=config.backup_count
        )
        file_handler.setLevel(getattr(logging, config.log_level.upper()))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a specific module.
    
    Args:
        name: Logger name (typically __name__ of the module).
    
    Returns:
        Logger instance.
    """
    return logging.getLogger(f'fd_rates_tool.{name}')


# Configure logging for third-party libraries
def configure_third_party_logging():
    """Configure logging levels for third-party libraries to reduce noise."""
    
    # Reduce urllib3 logging noise
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    
    # Reduce requests logging noise
    logging.getLogger('requests.packages.urllib3').setLevel(logging.WARNING)
    
    # Reduce beautifulsoup4 logging noise
    logging.getLogger('bs4').setLevel(logging.WARNING)


class ErrorTracker:
    """
    Comprehensive error tracking and reporting system.
    
    Implements requirements:
    - 5.1: Network error handling
    - 5.4: CAPTCHA and anti-bot detection logging
    """
    
    def __init__(self):
        self.logger = get_logger(__name__)
        self.error_counts: Dict[str, int] = {}
        self.error_details: Dict[str, list] = {}
        self.start_time = datetime.now()
    
    def log_error(self, error_type: str, url: str, error_message: str, 
                  exception: Optional[Exception] = None) -> None:
        """
        Log an error with comprehensive details.
        
        Args:
            error_type: Type of error (e.g., 'network', 'parsing', 'captcha').
            url: URL where the error occurred.
            error_message: Human-readable error message.
            exception: Optional exception object for stack trace.
        """
        # Increment error count
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1
        
        # Store error details
        if error_type not in self.error_details:
            self.error_details[error_type] = []
        
        error_detail = {
            'timestamp': datetime.now().isoformat(),
            'url': url,
            'message': error_message,
            'stack_trace': None
        }
        
        if exception:
            error_detail['stack_trace'] = traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
        
        self.error_details[error_type].append(error_detail)
        
        # Log the error
        log_message = f"[{error_type.upper()}] {url}: {error_message}"
        if exception:
            self.logger.error(log_message, exc_info=True)
        else:
            self.logger.error(log_message)
    
    def log_network_error(self, url: str, error: Exception) -> None:
        """Log network-related errors."""
        error_message = f"Network error: {str(error)}"
        self.log_error('network', url, error_message, error)
    
    def log_captcha_detection(self, url: str, details: str = "") -> None:
        """Log CAPTCHA or anti-bot detection."""
        error_message = f"CAPTCHA/anti-bot protection detected. {details}".strip()
        self.log_error('captcha', url, error_message)
    
    def log_rate_limiting(self, url: str, status_code: int, retry_after: Optional[str] = None) -> None:
        """Log rate limiting incidents."""
        error_message = f"Rate limited (HTTP {status_code})"
        if retry_after:
            error_message += f", retry after: {retry_after}"
        self.log_error('rate_limit', url, error_message)
    
    def log_parsing_error(self, url: str, error: Exception, content_preview: str = "") -> None:
        """Log content parsing errors."""
        error_message = f"Parsing error: {str(error)}"
        if content_preview:
            error_message += f". Content preview: {content_preview[:100]}..."
        self.log_error('parsing', url, error_message, error)
    
    def log_timeout_error(self, url: str, timeout_duration: float) -> None:
        """Log request timeout errors."""
        error_message = f"Request timeout after {timeout_duration}s"
        self.log_error('timeout', url, error_message)
    
    def get_error_summary(self) -> Dict[str, Any]:
        """
        Get a comprehensive error summary.
        
        Returns:
            Dictionary containing error statistics and details.
        """
        runtime = datetime.now() - self.start_time
        
        return {
            'runtime_seconds': runtime.total_seconds(),
            'total_errors': sum(self.error_counts.values()),
            'error_counts_by_type': self.error_counts.copy(),
            'error_details': self.error_details.copy(),
            'most_common_error': max(self.error_counts.items(), key=lambda x: x[1])[0] if self.error_counts else None
        }
    
    def log_summary(self) -> None:
        """Log a summary of all errors encountered."""
        summary = self.get_error_summary()
        
        if summary['total_errors'] == 0:
            self.logger.info("No errors encountered during execution")
            return
        
        self.logger.info(f"Error Summary - Total: {summary['total_errors']} errors in {summary['runtime_seconds']:.1f}s")
        
        for error_type, count in summary['error_counts_by_type'].items():
            self.logger.info(f"  {error_type}: {count} errors")
        
        if summary['most_common_error']:
            self.logger.info(f"Most common error type: {summary['most_common_error']}")


class ResilientOperationManager:
    """
    Manager for resilient operations with retry logic and fallback strategies.
    
    Implements comprehensive error handling and resilience patterns.
    """
    
    def __init__(self, error_tracker: Optional[ErrorTracker] = None):
        self.logger = get_logger(__name__)
        self.error_tracker = error_tracker or ErrorTracker()
    
    def execute_with_fallback(self, primary_operation, fallback_operations: list, 
                            operation_name: str, url: str = "") -> Any:
        """
        Execute an operation with fallback strategies.
        
        Args:
            primary_operation: Primary operation to try first.
            fallback_operations: List of fallback operations to try if primary fails.
            operation_name: Name of the operation for logging.
            url: URL associated with the operation.
            
        Returns:
            Result from the first successful operation.
            
        Raises:
            Exception: If all operations fail.
        """
        operations = [primary_operation] + fallback_operations
        last_exception = None
        
        for i, operation in enumerate(operations):
            try:
                self.logger.debug(f"Attempting {operation_name} (strategy {i + 1}/{len(operations)})")
                result = operation()
                
                if i > 0:  # Fallback was used
                    self.logger.info(f"{operation_name} succeeded using fallback strategy {i + 1}")
                
                return result
                
            except Exception as e:
                last_exception = e
                strategy_type = "primary" if i == 0 else f"fallback_{i}"
                self.logger.warning(f"{operation_name} {strategy_type} strategy failed: {str(e)}")
                
                if url:
                    self.error_tracker.log_error(f"{operation_name.lower()}_failure", url, str(e), e)
        
        # All strategies failed
        error_message = f"All {operation_name} strategies failed"
        if url:
            self.error_tracker.log_error(f"{operation_name.lower()}_total_failure", url, error_message, last_exception)
        
        raise Exception(f"{error_message}. Last error: {str(last_exception)}")
    
    def execute_with_circuit_breaker(self, operation, failure_threshold: int = 5, 
                                   reset_timeout: int = 300) -> Any:
        """
        Execute operation with circuit breaker pattern.
        
        Args:
            operation: Operation to execute.
            failure_threshold: Number of failures before opening circuit.
            reset_timeout: Time in seconds before attempting to reset circuit.
            
        Returns:
            Result from the operation.
        """
        # This is a simplified circuit breaker implementation
        # In a production system, you'd want to use a more sophisticated library
        try:
            return operation()
        except Exception as e:
            self.logger.error(f"Circuit breaker: operation failed: {str(e)}")
            raise