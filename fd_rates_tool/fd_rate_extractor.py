"""Main FD Rate Extractor orchestrator class."""

import logging
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from .config import Config
from .core.models import BankInfo, FDRateData, ExtractionSummary
from .core.excel_reader import ExcelReader, ExcelReaderError
from .extractors.url_discovery import URLDiscoveryEngine
from .extractors.rate_extractor import RateExtractor
from .core.data_formatter import DataFormatter
from .core.output_manager import OutputManager
from .utils.logging_setup import setup_logging


logger = logging.getLogger(__name__)


class FDRateExtractor:
    """
    Main orchestrator class that coordinates all components to extract FD rates.
    
    This class wires together all the individual components (Excel reader, URL discovery,
    rate extraction, data formatting, and output management) to provide a complete
    FD rate extraction workflow.
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the FD Rate Extractor with configuration.
        
        Args:
            config: Configuration object. Uses default if None.
        """
        from .config import default_config
        self.config = config or default_config
        
        # Initialize all components
        self.excel_reader = ExcelReader(self.config)
        self.url_discovery = URLDiscoveryEngine(self.config)
        self.rate_extractor = RateExtractor(self.config)
        self.data_formatter = DataFormatter()
        self.output_manager = OutputManager(self.config)
        
        # Initialize extraction state
        self.banks_data: List[BankInfo] = []
        self.extraction_results: List[FDRateData] = []
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
        logger.info("FD Rate Extractor initialized successfully")
    
    def extract_all_rates(self, excel_file_path: Optional[str] = None) -> ExtractionSummary:
        """
        Execute the complete FD rate extraction workflow.
        
        Args:
            excel_file_path: Optional path to Excel file. Uses config default if None.
            
        Returns:
            ExtractionSummary: Summary of the extraction process.
        """
        self.start_time = datetime.now()
        logger.info("Starting complete FD rate extraction workflow")
        
        try:
            # Step 1: Read bank data from Excel
            self._read_bank_data(excel_file_path)
            
            # Step 2: Process each bank
            self._process_all_banks()
            
            # Step 3: Save all outputs
            self.end_time = datetime.now()
            success = self._save_outputs()
            
            # Step 4: Generate and return summary
            summary = self.output_manager.generate_summary_report(
                self.extraction_results, self.start_time, self.end_time
            )
            
            if success:
                logger.info(f"Extraction completed successfully: {summary.success_rate:.1f}% success rate")
            else:
                logger.warning("Extraction completed but some outputs failed to save")
            
            return summary
            
        except Exception as e:
            self.end_time = datetime.now()
            logger.error(f"Extraction workflow failed: {str(e)}")
            
            # Return error summary
            return ExtractionSummary(
                total_banks=len(self.banks_data),
                successful_extractions=0,
                failed_extractions=len(self.banks_data),
                start_time=self.start_time,
                end_time=self.end_time,
                errors=[f"Workflow error: {str(e)}"]
            )
    
    def extract_single_bank(self, bank_info: BankInfo) -> FDRateData:
        """
        Extract FD rates for a single bank.
        
        Args:
            bank_info: Information about the bank to process.
            
        Returns:
            FDRateData: Extraction results for the bank.
        """
        logger.info(f"Processing bank: {bank_info.name}")
        
        try:
            # Check if FD rates URL is already provided in Excel
            if bank_info.fd_rates_url:
                logger.info(f"Using provided FD URL for {bank_info.name}: {bank_info.fd_rates_url}")
                target_url = bank_info.fd_rates_url
                bank_info.discovered_fd_url = target_url
                bank_info.extraction_status = "url_provided"
            else:
                # Step 1: Discover FD URLs
                discovered_urls = self.url_discovery.discover_fd_urls(
                    bank_info.base_url, bank_info.name
                )
                
                if not discovered_urls:
                    logger.warning(f"No FD URLs found for {bank_info.name}")
                    return FDRateData(
                        bank_name=bank_info.name,
                        source_url=bank_info.base_url,
                        extraction_timestamp=datetime.now(),
                        extraction_success=False,
                        error_message="No FD rates page found"
                    )
                
                # Update bank info with discovered URL
                target_url = discovered_urls[0]
                bank_info.discovered_fd_url = target_url
                bank_info.extraction_status = "url_discovered"
            
            # Step 2: Extract rates from the target URL
            fd_data = self.rate_extractor.extract_rates(target_url)
            
            # Update extraction status
            if fd_data.extraction_success:
                bank_info.extraction_status = "completed"
                logger.info(f"Successfully extracted {len(fd_data.rates)} rates for {bank_info.name}")
            else:
                bank_info.extraction_status = "failed"
                logger.warning(f"Rate extraction failed for {bank_info.name}: {fd_data.error_message}")
            
            return fd_data
            
        except Exception as e:
            logger.error(f"Error processing bank {bank_info.name}: {str(e)}")
            bank_info.extraction_status = "error"
            
            return FDRateData(
                bank_name=bank_info.name,
                source_url=bank_info.base_url,
                extraction_timestamp=datetime.now(),
                extraction_success=False,
                error_message=f"Processing error: {str(e)}"
            )
    
    def get_extraction_progress(self) -> dict:
        """
        Get current extraction progress information.
        
        Returns:
            dict: Progress information including counts and percentages.
        """
        total_banks = len(self.banks_data)
        processed_banks = len(self.extraction_results)
        
        if total_banks == 0:
            return {
                'total_banks': 0,
                'processed_banks': 0,
                'progress_percentage': 0.0,
                'successful_extractions': 0,
                'failed_extractions': 0
            }
        
        successful = sum(1 for result in self.extraction_results if result.extraction_success)
        failed = processed_banks - successful
        
        return {
            'total_banks': total_banks,
            'processed_banks': processed_banks,
            'progress_percentage': (processed_banks / total_banks) * 100,
            'successful_extractions': successful,
            'failed_extractions': failed
        }
    
    def read_bank_data(self, excel_file_path: Optional[str] = None):
        """
        Read bank data from Excel file.
        
        Args:
            excel_file_path: Optional path to Excel file.
            
        Raises:
            ExcelReaderError: If Excel reading fails.
        """
        try:
            logger.info("Reading bank data from Excel file")
            self.banks_data = self.excel_reader.read_bank_data(excel_file_path)
            
            if not self.banks_data:
                raise ExcelReaderError("No valid bank data found in Excel file")
            
            logger.info(f"Successfully loaded {len(self.banks_data)} banks from Excel")
            
            # Log some sample bank data for verification
            for i, bank in enumerate(self.banks_data[:3]):  # Log first 3 banks
                logger.debug(f"Bank {i+1}: {bank.name} -> {bank.base_url}")
            
            if len(self.banks_data) > 3:
                logger.debug(f"... and {len(self.banks_data) - 3} more banks")
                
        except ExcelReaderError:
            raise
        except Exception as e:
            raise ExcelReaderError(f"Unexpected error reading Excel file: {str(e)}")
    
    def _read_bank_data(self, excel_file_path: Optional[str] = None):
        """
        Read bank data from Excel file (internal method for backward compatibility).
        
        Args:
            excel_file_path: Optional path to Excel file.
            
        Raises:
            ExcelReaderError: If Excel reading fails.
        """
        return self.read_bank_data(excel_file_path)
    
    def _process_all_banks(self):
        """
        Process all banks to extract FD rates.
        """
        logger.info(f"Starting to process {len(self.banks_data)} banks")
        
        for i, bank_info in enumerate(self.banks_data, 1):
            try:
                logger.info(f"Processing bank {i}/{len(self.banks_data)}: {bank_info.name}")
                
                # Extract rates for this bank
                fd_data = self.extract_single_bank(bank_info)
                self.extraction_results.append(fd_data)
                
                # Log progress periodically
                if i % 10 == 0 or i == len(self.banks_data):
                    progress = self.get_extraction_progress()
                    logger.info(f"Progress: {i}/{len(self.banks_data)} banks processed "
                              f"({progress['progress_percentage']:.1f}%) - "
                              f"{progress['successful_extractions']} successful, "
                              f"{progress['failed_extractions']} failed")
                
            except Exception as e:
                logger.error(f"Critical error processing bank {bank_info.name}: {str(e)}")
                
                # Create error result
                error_result = FDRateData(
                    bank_name=bank_info.name,
                    source_url=bank_info.base_url,
                    extraction_timestamp=datetime.now(),
                    extraction_success=False,
                    error_message=f"Critical processing error: {str(e)}"
                )
                self.extraction_results.append(error_result)
        
        logger.info(f"Completed processing all {len(self.banks_data)} banks")
    
    def _save_outputs(self) -> bool:
        """
        Save all extraction outputs.
        
        Returns:
            bool: True if all outputs saved successfully, False otherwise.
        """
        try:
            logger.info("Saving extraction outputs")
            
            success = self.output_manager.save_all_outputs(
                self.extraction_results, self.start_time, self.end_time
            )
            
            if success:
                logger.info("All outputs saved successfully")
                
                # Log output file paths
                output_paths = self.output_manager.get_output_file_paths()
                logger.info(f"Output files created in: {output_paths['output_dir']}")
                logger.info(f"  - Success file: {output_paths['success'].name}")
                logger.info(f"  - Failure file: {output_paths['failure'].name}")
                logger.info(f"  - Summary file: {output_paths['summary'].name}")
            else:
                logger.error("Failed to save some outputs")
            
            return success
            
        except Exception as e:
            logger.error(f"Error saving outputs: {str(e)}")
            return False
    
    def validate_configuration(self) -> bool:
        """
        Validate the current configuration.
        
        Returns:
            bool: True if configuration is valid, False otherwise.
        """
        try:
            # Check Excel file exists
            excel_path = Path(self.config.extraction.excel_file_path)
            if not excel_path.exists():
                logger.error(f"Excel file not found: {excel_path}")
                return False
            
            # Check output directory is writable
            output_dir = Path("output")
            try:
                output_dir.mkdir(exist_ok=True)
                test_file = output_dir / "test_write.tmp"
                test_file.write_text("test")
                test_file.unlink()
            except Exception as e:
                logger.error(f"Output directory not writable: {e}")
                return False
            
            # Validate configuration values
            if self.config.scraping.request_timeout <= 0:
                logger.error("Request timeout must be positive")
                return False
            
            if self.config.scraping.request_delay < 0:
                logger.error("Request delay must be non-negative")
                return False
            
            if self.config.extraction.max_deposit_amount <= 0:
                logger.error("Max deposit amount must be positive")
                return False
            
            logger.info("Configuration validation passed")
            return True
            
        except Exception as e:
            logger.error(f"Configuration validation error: {str(e)}")
            return False
    
    def get_statistics(self) -> dict:
        """
        Get detailed statistics about the extraction process.
        
        Returns:
            dict: Detailed statistics.
        """
        if not self.extraction_results:
            return {
                'total_banks': len(self.banks_data),
                'processed_banks': 0,
                'successful_extractions': 0,
                'failed_extractions': 0,
                'total_rates_extracted': 0,
                'banks_with_senior_rates': 0,
                'average_rates_per_bank': 0.0
            }
        
        successful_results = [r for r in self.extraction_results if r.extraction_success]
        failed_results = [r for r in self.extraction_results if not r.extraction_success]
        
        total_rates = sum(len(r.rates) for r in successful_results)
        banks_with_senior_rates = sum(1 for r in successful_results if r.has_senior_citizen_rates())
        
        avg_rates_per_bank = total_rates / len(successful_results) if successful_results else 0.0
        
        return {
            'total_banks': len(self.banks_data),
            'processed_banks': len(self.extraction_results),
            'successful_extractions': len(successful_results),
            'failed_extractions': len(failed_results),
            'total_rates_extracted': total_rates,
            'banks_with_senior_rates': banks_with_senior_rates,
            'average_rates_per_bank': round(avg_rates_per_bank, 2)
        }