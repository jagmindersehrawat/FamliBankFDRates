# Bank FD Rates Extraction Tool

A Python-based web scraping tool that extracts Fixed Deposit (FD) rates from Indian bank websites. The system reads bank information from an Excel file, scrapes FD rate pages, and extracts structured rate data including tenure periods, general rates, and senior citizen rates.

## Features

- **Excel Integration**: Reads bank URLs from Excel file (`List_of_Banksv1.xlsx`)
- **Comprehensive Rate Extraction**: Extracts tenure periods, general rates, and senior citizen rates
- **Bank-Specific Parsers**: Custom parsers for banks with unique table structures (SBI, ICICI, HDFC, PNB, Federal Bank, UCO Bank, Bank of Maharashtra, etc.)
- **Duration Parsing**: Converts tenure periods to day ranges (e.g., "6 months to 1 year" → 181-365 days)
- **Excel Output**: Generates structured Excel file with all extracted rates and duration columns
- **Robust Error Handling**: Gracefully handles network errors and parsing failures
- **Caching**: Caches web pages to avoid redundant requests

## Project Structure

```
fd_rates_tool/
├── fd_rates_tool/           # Main package
│   ├── core/               # Core components
│   ├── extractors/         # Data extraction modules
│   ├── utils/              # Utility functions
│   └── config.py           # Configuration management
├── tests/                  # Test suite
├── main.py                 # CLI entry point
├── requirements.txt        # Dependencies
└── setup.py               # Package setup
```

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd bank-fd-rates-tool
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install the package in development mode:
```bash
pip install -e .
```

## Usage

### Running the Extraction

```bash
python run_full_extraction.py
```

This will:
1. Read bank information from `List_of_Banksv1.xlsx`
2. Extract FD rates from each bank's website
3. Parse tenure periods to day ranges
4. Generate output Excel file at `output/fd_rates_results.xlsx`

### Input File Format

The Excel file should contain columns:
- Bank Name
- FD Rates URL
- Other bank information

### Output File

The generated Excel file (`output/fd_rates_results.xlsx`) contains:
- Bank Name
- Tenure (original text)
- Duration From (Days)
- Duration To (Days)
- General Rate (%)
- Senior Citizen Rate (%)
- Deposit Amount
- Last Updated date

## Bank-Specific Parsers

The tool includes custom parsers for banks with unique table structures:

- **SBI**: Parses JSON API endpoint
- **ICICI**: Extracts from JSON API
- **HDFC**: 3-column table parser
- **PNB**: Parses "Domestic term deposits" section
- **Federal Bank**: 3-column table with separate senior citizen rates
- **UCO Bank**: Applies hardcoded senior citizen rate rules (+0.25% for ≤1L, +0.50% for >1L)
- **Bank of Maharashtra**: Extracts from "Regular Schemes" section
- **Central Bank**: Handles year abbreviations (yr/yrs)
- **Shivalik Bank**: Parses complex tenure formats

## Duration Parsing

The tool converts various tenure formats to day ranges:
- "7 days to 45 days" → 7-45 days
- "6 months to 1 year" → 181-365 days
- "2 years to 3 years" → 730-1095 days
- "13 months to 16 months" → 390-480 days
- And many more patterns...

## Requirements

- Python 3.8+
- pandas >= 2.0.0
- openpyxl >= 3.1.0
- requests >= 2.31.0
- beautifulsoup4 >= 4.12.0
- hypothesis >= 6.82.0 (for testing)

## Key Components

- `run_full_extraction.py`: Main script to run the extraction
- `fd_rates_tool/extractors/rate_extractor.py`: Core extraction logic with bank-specific parsers
- `period_days_converter.py`: Tenure period to day range conversion
- `fd_rates_tool/core/output_manager.py`: Excel output generation
- `fd_rates_tool/utils/web_scraper.py`: Web scraping utilities with caching
- `fd_rates_tool/core/excel_reader.py`: Excel file reading

## Ethical Considerations

This tool is designed for educational and research purposes. When using it:

- Respect website terms of service
- Use appropriate delays between requests
- Don't overload bank servers
- Consider reaching out to banks for official API access when available

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass
6. Submit a pull request

## Support

For issues and questions, please create an issue in the repository or contact the development team.