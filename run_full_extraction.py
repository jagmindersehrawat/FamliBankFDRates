#!/usr/bin/env python3
"""
Run full FD rates extraction for all banks.
"""

import sys
sys.path.insert(0, '.')

from fd_rates_tool.fd_rate_extractor import FDRateExtractor
from fd_rates_tool.config import Config
from fd_rates_tool.utils.logging_setup import setup_logging
import logging

def main():
    print("=" * 80)
    print("FD RATES EXTRACTION - ALL BANKS")
    print("=" * 80)
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # Initialize configuration
    config = Config()
    config.extraction.excel_file_path = "List_of_Banksv1.xlsx"  # Use updated Excel file
    
    print(f"\n📖 Reading banks from: {config.extraction.excel_file_path}")
    print(f"💾 Output directory: output/")
    print(f"⏱️  Request delay: {config.scraping.request_delay}s between banks")
    print(f"🔄 Max retries: {config.scraping.max_retries}")
    
    # Initialize extractor
    extractor = FDRateExtractor(config)
    
    print("\n🚀 Starting extraction...\n")
    
    # Run extraction
    summary = extractor.extract_all_rates()
    
    # Display summary
    print("\n" + "=" * 80)
    print("EXTRACTION SUMMARY")
    print("=" * 80)
    
    print(f"\n📊 Overall Statistics:")
    print(f"   Total banks processed: {summary.total_banks}")
    print(f"   Successful extractions: {summary.successful_extractions}")
    print(f"   Failed extractions: {summary.failed_extractions}")
    print(f"   Success rate: {summary.success_rate:.1f}%")
    
    print(f"\n⏱️  Timing:")
    print(f"   Start time: {summary.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    if summary.end_time:
        print(f"   End time: {summary.end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   Duration: {summary.duration/60:.1f} minutes")
    
    if summary.failed_extractions > 0:
        print(f"\n❌ Failed Banks:")
        # The summary should have failed bank details
        print(f"   {summary.failed_extractions} banks failed to extract")
    
    print("\n💾 Output Files:")
    print(f"   Success: output/fd_rates_success.json")
    print(f"   Failures: output/fd_rates_failures.json")
    print(f"   Summary: output/extraction_summary.json")
    
    print("\n" + "=" * 80)
    print("✅ Extraction completed!")
    print("=" * 80)
    
    return summary

if __name__ == "__main__":
    try:
        summary = main()
        sys.exit(0 if summary.success_rate > 0 else 1)
    except Exception as e:
        print(f"\n💥 ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
