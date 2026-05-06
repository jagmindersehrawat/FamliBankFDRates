#!/usr/bin/env python3
"""Test script for IndusInd Bank FD rates extraction."""

import sys
from fd_rates_tool.extractors.rate_extractor import RateExtractor
from fd_rates_tool.config import Config

def main():
    """Test IndusInd Bank extraction."""
    config = Config()
    extractor = RateExtractor(config)
    
    url = "https://www.indusind.bank.in/in/en/personal/fixed-deposit-interest-rate.html"
    
    print(f"Testing IndusInd Bank extraction from: {url}\n")
    
    result = extractor.extract_rates(url)
    
    print(f"Extraction Success: {result.extraction_success}")
    print(f"Bank Name: {result.bank_name}")
    print(f"Number of rates extracted: {len(result.rates)}")
    
    if result.error_message:
        print(f"Error: {result.error_message}")
    
    if result.rates:
        print("\n=== Extracted Rates ===")
        for i, rate in enumerate(result.rates, 1):
            print(f"{i}. {rate.tenure}: General={rate.general_rate}%, Senior={rate.senior_citizen_rate}%")
    
    return 0 if result.extraction_success else 1

if __name__ == "__main__":
    sys.exit(main())
