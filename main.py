#!/usr/bin/env python3
"""
Main entry point for the Bank FD Rates Tool.

This script provides a command-line interface for extracting Fixed Deposit rates
from bank websites based on data from an Excel file.
"""

import argparse
import sys
from pathlib import Path

from fd_rates_tool.config import Config
from fd_rates_tool.utils.logging_setup import setup_logging, configure_third_party_logging


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Extract Fixed Deposit rates from bank websites",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                          # Use default Excel file
  python main.py --excel custom_banks.xlsx
  python main.py --output-format csv
  python main.py --log-level DEBUG
  python main.py --delay 2.0 --timeout 60
  python main.py --no-cache --max-retries 5
  python main.py --banks-limit 10         # Process only first 10 banks
        """
    )
    
    # Input/Output options
    parser.add_argument(
        '--excel',
        type=str,
        default='List_of_Banks.xlsx',
        help='Path to Excel file containing bank information (default: List_of_Banks.xlsx)'
    )
    
    parser.add_argument(
        '--output-format',
        choices=['json', 'csv'],
        default='json',
        help='Output format for extracted data (default: json)'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='output',
        help='Directory to save output files (default: output)'
    )
    
    # Scraping behavior options
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='Delay between requests in seconds (default: 1.0)'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Request timeout in seconds (default: 30)'
    )
    
    parser.add_argument(
        '--max-retries',
        type=int,
        default=3,
        help='Maximum number of retries per request (default: 3)'
    )
    
    parser.add_argument(
        '--user-agent',
        type=str,
        help='Custom user agent string for requests'
    )
    
    # Cache options
    parser.add_argument(
        '--no-cache',
        action='store_true',
        help='Disable URL caching'
    )
    
    parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear existing cache before starting'
    )
    
    # Processing options
    parser.add_argument(
        '--banks-limit',
        type=int,
        help='Limit the number of banks to process (for testing)'
    )
    
    parser.add_argument(
        '--skip-banks',
        type=int,
        default=0,
        help='Skip the first N banks (default: 0)'
    )
    
    parser.add_argument(
        '--banks-filter',
        type=str,
        help='Process only banks whose names contain this text (case-insensitive)'
    )
    
    # Logging options
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )
    
    parser.add_argument(
        '--log-file',
        type=str,
        help='Custom log file path (default: fd_rates_tool.log)'
    )
    
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress progress output (only log to file)'
    )
    
    # Validation and testing options
    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Only validate configuration and Excel file, do not extract rates'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Perform a dry run without making actual web requests'
    )
    
    parser.add_argument(
        '--show-config',
        action='store_true',
        help='Show current configuration and exit'
    )
    
    return parser


def apply_arguments_to_config(config: Config, args: argparse.Namespace) -> Config:
    """
    Apply command-line arguments to configuration.
    
    Args:
        config: Base configuration object.
        args: Parsed command-line arguments.
    
    Returns:
        Updated configuration object.
    """
    # Basic settings
    config.extraction.excel_file_path = args.excel
    config.extraction.output_format = args.output_format
    config.logging.log_level = args.log_level
    
    # Scraping settings
    config.scraping.request_delay = args.delay
    config.scraping.request_timeout = args.timeout
    config.scraping.max_retries = args.max_retries
    
    # Cache settings
    config.cache.enable_cache = not args.no_cache
    
    # Optional settings
    if args.user_agent:
        config.scraping.user_agent = args.user_agent
        config.scraping.headers['User-Agent'] = args.user_agent
    
    if args.log_file:
        config.logging.log_file = args.log_file
    
    return config


def show_configuration(config: Config, args: argparse.Namespace):
    """
    Display current configuration settings.
    
    Args:
        config: Configuration object to display.
        args: Command-line arguments.
    """
    print("=" * 60)
    print("CURRENT CONFIGURATION")
    print("=" * 60)
    
    print("\nInput/Output Settings:")
    print(f"  Excel file: {config.extraction.excel_file_path}")
    print(f"  Output format: {config.extraction.output_format}")
    print(f"  Output directory: {args.output_dir}")
    
    print("\nScraping Settings:")
    print(f"  Request delay: {config.scraping.request_delay}s")
    print(f"  Request timeout: {config.scraping.request_timeout}s")
    print(f"  Max retries: {config.scraping.max_retries}")
    print(f"  User agent: {config.scraping.user_agent}")
    print(f"  Respect robots.txt: {config.scraping.respect_robots_txt}")
    
    print("\nCache Settings:")
    print(f"  Cache enabled: {config.cache.enable_cache}")
    print(f"  Cache directory: {config.cache.cache_dir}")
    print(f"  Cache expiry: {config.cache.cache_expiry_hours} hours")
    
    print("\nExtraction Settings:")
    print(f"  Max deposit amount: ₹{config.extraction.max_deposit_amount:,}")
    print(f"  Bank name column: {config.extraction.bank_name_column}")
    
    print("\nProcessing Filters:")
    if args.banks_limit:
        print(f"  Banks limit: {args.banks_limit}")
    if args.skip_banks > 0:
        print(f"  Skip banks: {args.skip_banks}")
    if args.banks_filter:
        print(f"  Banks filter: '{args.banks_filter}'")
    
    print("\nLogging Settings:")
    print(f"  Log level: {config.logging.log_level}")
    print(f"  Log file: {config.logging.log_file}")
    print(f"  Quiet mode: {args.quiet}")
    
    print("\nSpecial Modes:")
    print(f"  Validate only: {args.validate_only}")
    print(f"  Dry run: {args.dry_run}")
    print(f"  Clear cache: {args.clear_cache}")
    
    print("=" * 60)


def filter_banks_list(banks_data: list, args: argparse.Namespace) -> list:
    """
    Apply filtering options to the banks list.
    
    Args:
        banks_data: List of bank information.
        args: Command-line arguments with filtering options.
    
    Returns:
        Filtered list of banks.
    """
    filtered_banks = banks_data.copy()
    
    # Apply text filter
    if args.banks_filter:
        filter_text = args.banks_filter.lower()
        filtered_banks = [
            bank for bank in filtered_banks 
            if filter_text in bank.name.lower()
        ]
        print(f"Applied filter '{args.banks_filter}': {len(filtered_banks)} banks match")
    
    # Apply skip
    if args.skip_banks > 0:
        filtered_banks = filtered_banks[args.skip_banks:]
        print(f"Skipped first {args.skip_banks} banks: {len(filtered_banks)} banks remaining")
    
    # Apply limit
    if args.banks_limit:
        filtered_banks = filtered_banks[:args.banks_limit]
        print(f"Limited to {args.banks_limit} banks: processing {len(filtered_banks)} banks")
    
    return filtered_banks


def clear_cache_if_requested(args: argparse.Namespace, config: Config):
    """
    Clear cache if requested by user.
    
    Args:
        args: Command-line arguments.
        config: Configuration object.
    """
    if args.clear_cache:
        try:
            from fd_rates_tool.utils.cache_manager import CacheManager
            cache_manager = CacheManager(config)
            cache_manager.clear_cache()
            print("Cache cleared successfully")
        except Exception as e:
            print(f"Warning: Could not clear cache: {e}")


def setup_progress_reporting(args: argparse.Namespace) -> bool:
    """
    Setup progress reporting based on arguments.
    
    Args:
        args: Command-line arguments.
    
    Returns:
        True if progress should be shown, False if quiet mode.
    """
    return not args.quiet


def validate_arguments(args: argparse.Namespace) -> bool:
    """
    Validate command-line arguments.
    
    Args:
        args: Parsed command-line arguments.
    
    Returns:
        True if arguments are valid, False otherwise.
    """
    # Check if Excel file exists (unless it's a dry run or config show)
    if not args.dry_run and not args.show_config:
        excel_path = Path(args.excel)
        if not excel_path.exists():
            print(f"Error: Excel file '{args.excel}' not found.")
            return False
        
        if not excel_path.suffix.lower() in ['.xlsx', '.xls']:
            print(f"Error: '{args.excel}' is not a valid Excel file.")
            return False
    
    # Validate delay and timeout values
    if args.delay < 0:
        print("Error: Delay must be non-negative.")
        return False
    
    if args.timeout <= 0:
        print("Error: Timeout must be positive.")
        return False
    
    if args.max_retries < 0:
        print("Error: Max retries must be non-negative.")
        return False
    
    # Validate banks limit and skip values
    if args.banks_limit is not None and args.banks_limit <= 0:
        print("Error: Banks limit must be positive.")
        return False
    
    if args.skip_banks < 0:
        print("Error: Skip banks must be non-negative.")
        return False
    
    # Validate output directory
    try:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Test write permissions
        test_file = output_dir / "test_write.tmp"
        test_file.write_text("test")
        test_file.unlink()
    except Exception as e:
        print(f"Error: Cannot write to output directory '{args.output_dir}': {e}")
        return False
    
    return True


def main():
    """Main function to run the FD Rates Tool."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Create configuration
    config = Config.from_env()
    config = apply_arguments_to_config(config, args)
    
    # Handle special modes first
    if args.show_config:
        show_configuration(config, args)
        return
    
    # Validate arguments
    if not validate_arguments(args):
        sys.exit(1)
    
    # Setup logging
    configure_third_party_logging()
    logger = setup_logging(config.logging)
    
    # Setup progress reporting
    show_progress = setup_progress_reporting(args)
    
    if show_progress:
        print("=" * 60)
        print("BANK FD RATES EXTRACTION TOOL")
        print("=" * 60)
        print(f"Excel file: {args.excel}")
        print(f"Output format: {args.output_format}")
        print(f"Output directory: {args.output_dir}")
        if args.dry_run:
            print("MODE: DRY RUN (no actual web requests)")
        if args.validate_only:
            print("MODE: VALIDATION ONLY")
        print("=" * 60)
    
    logger.info("Starting Bank FD Rates Tool")
    logger.info(f"Excel file: {args.excel}")
    logger.info(f"Output format: {args.output_format}")
    logger.info(f"Cache enabled: {config.cache.enable_cache}")
    
    try:
        # Clear cache if requested
        clear_cache_if_requested(args, config)
        
        # Import and initialize the main extractor
        from fd_rates_tool.fd_rate_extractor import FDRateExtractor
        
        # Create and configure the extractor
        extractor = FDRateExtractor(config)
        
        # Validate configuration
        if not extractor.validate_configuration():
            logger.error("Configuration validation failed")
            if show_progress:
                print("❌ Configuration validation failed")
            sys.exit(1)
        
        if show_progress:
            print("✅ Configuration validated successfully")
        
        # Handle validate-only mode
        if args.validate_only:
            logger.info("Validation completed successfully")
            if show_progress:
                print("✅ Validation completed - Excel file and configuration are valid")
            return
        
        # Read and filter banks data
        if show_progress:
            print("📖 Reading bank data from Excel...")
        
        extractor.read_bank_data()
        original_count = len(extractor.banks_data)
        
        # Apply filters
        extractor.banks_data = filter_banks_list(extractor.banks_data, args)
        filtered_count = len(extractor.banks_data)
        
        if show_progress:
            print(f"📊 Loaded {original_count} banks from Excel")
            if filtered_count != original_count:
                print(f"🔍 Filtered to {filtered_count} banks for processing")
        
        # Handle dry run mode
        if args.dry_run:
            logger.info("Dry run mode - skipping actual extraction")
            if show_progress:
                print("🧪 Dry run completed - would process {} banks".format(filtered_count))
            return
        
        # Run the extraction workflow
        if show_progress:
            print(f"🚀 Starting extraction for {filtered_count} banks...")
            print("⏳ This may take a while depending on the number of banks...")
        
        logger.info("Starting FD rate extraction workflow")
        summary = extractor.extract_all_rates()
        
        # Display results
        if show_progress:
            print("\n" + "=" * 60)
            print("EXTRACTION COMPLETED")
            print("=" * 60)
            print(f"📊 Total banks processed: {summary.total_banks}")
            print(f"✅ Successful extractions: {summary.successful_extractions}")
            print(f"❌ Failed extractions: {summary.failed_extractions}")
            print(f"📈 Success rate: {summary.success_rate:.1f}%")
            
            if summary.duration:
                print(f"⏱️  Total duration: {summary.duration:.2f} seconds")
            
            # Get detailed statistics
            stats = extractor.get_statistics()
            print(f"📋 Total rates extracted: {stats['total_rates_extracted']}")
            print(f"👥 Banks with senior citizen rates: {stats['banks_with_senior_rates']}")
            print(f"📊 Average rates per bank: {stats['average_rates_per_bank']}")
            
            # Show output files
            output_paths = extractor.output_manager.get_output_file_paths()
            print(f"\n📁 Output files created in: {output_paths['output_dir']}")
            print(f"   ✅ Success file: {output_paths['success'].name}")
            print(f"   ❌ Failure file: {output_paths['failure'].name}")
            print(f"   📊 Summary file: {output_paths['summary'].name}")
            print(f"   📑 Excel file: fd_rates_results.xlsx")
            print("=" * 60)
        
        # Log final results
        logger.info("=" * 50)
        logger.info("EXTRACTION COMPLETED")
        logger.info("=" * 50)
        logger.info(f"Total banks processed: {summary.total_banks}")
        logger.info(f"Successful extractions: {summary.successful_extractions}")
        logger.info(f"Failed extractions: {summary.failed_extractions}")
        logger.info(f"Success rate: {summary.success_rate:.1f}%")
        
        if summary.duration:
            logger.info(f"Total duration: {summary.duration:.2f} seconds")
        
        # Get detailed statistics
        stats = extractor.get_statistics()
        logger.info(f"Total rates extracted: {stats['total_rates_extracted']}")
        logger.info(f"Banks with senior citizen rates: {stats['banks_with_senior_rates']}")
        logger.info(f"Average rates per bank: {stats['average_rates_per_bank']}")
        logger.info("=" * 50)
        
        # Exit with appropriate code
        if summary.successful_extractions > 0:
            logger.info("Extraction completed successfully")
            if show_progress:
                print("🎉 Extraction completed successfully!")
            sys.exit(0)
        else:
            logger.error("No successful extractions")
            if show_progress:
                print("⚠️  No successful extractions - check logs for details")
            sys.exit(1)
        
    except KeyboardInterrupt:
        logger.info("Process interrupted by user")
        if show_progress:
            print("\n⏹️  Process interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if show_progress:
            print(f"\n💥 Unexpected error: {e}")
            print("Check the log file for more details")
        sys.exit(1)


if __name__ == "__main__":
    main()