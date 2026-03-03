"""Output management utilities for the FD Rates Tool."""

import os
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging
import pandas as pd

from .models import FDRateData, ExtractionSummary
from .data_formatter import DataFormatter
from ..config import Config


logger = logging.getLogger(__name__)


class OutputManager:
    """Manages output files and data organization for FD rate extraction results."""
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the output manager.
        
        Args:
            config: Configuration object, uses default if None
        """
        from ..config import default_config
        self.config = config or default_config
        self.formatter = DataFormatter()
        
        # Create output directory if it doesn't exist
        self.output_dir = Path("output")
        self.output_dir.mkdir(exist_ok=True)
        
        # Initialize file paths
        self.success_file_path = self.output_dir / self.config.extraction.success_file
        self.failure_file_path = self.output_dir / self.config.extraction.failure_file
        self.summary_file_path = self.output_dir / self.config.extraction.summary_file
    
    def separate_success_failure(self, fd_data_list: List[FDRateData]) -> Tuple[List[FDRateData], List[FDRateData]]:
        """
        Separate successful extractions from failed ones.
        
        Args:
            fd_data_list: List of all FD rate data
            
        Returns:
            Tuple[List[FDRateData], List[FDRateData]]: (successful_data, failed_data)
        """
        try:
            successful_data = []
            failed_data = []
            
            for fd_data in fd_data_list:
                if fd_data.extraction_success and fd_data.rates:
                    successful_data.append(fd_data)
                else:
                    failed_data.append(fd_data)
            
            logger.info(f"Separated {len(successful_data)} successful and {len(failed_data)} failed extractions")
            return successful_data, failed_data
            
        except Exception as e:
            logger.error(f"Error separating success/failure data: {e}")
            return [], fd_data_list
    
    def preserve_data_relationships(self, fd_data_list: List[FDRateData]) -> List[FDRateData]:
        """
        Ensure data relationships between banks and their rates are preserved.
        
        Args:
            fd_data_list: List of FD rate data
            
        Returns:
            List[FDRateData]: Data with preserved relationships
        """
        try:
            # Use the formatter to ensure consistency
            consistent_data = self.formatter.ensure_data_consistency(fd_data_list)
            
            # Group rates by bank and validate relationships
            bank_rate_map = {}
            
            for fd_data in consistent_data:
                bank_key = fd_data.bank_name.lower().strip()
                
                if bank_key in bank_rate_map:
                    # Merge rates if same bank appears multiple times
                    existing_data = bank_rate_map[bank_key]
                    existing_data.rates.extend(fd_data.rates)
                    
                    # Remove duplicates
                    existing_data.rates = self.formatter._remove_duplicate_rates(existing_data.rates)
                    
                    # Update extraction status (success if any extraction succeeded)
                    if fd_data.extraction_success:
                        existing_data.extraction_success = True
                        existing_data.error_message = None
                    
                    logger.debug(f"Merged rates for bank: {fd_data.bank_name}")
                else:
                    bank_rate_map[bank_key] = fd_data
            
            # Convert back to list
            preserved_data = list(bank_rate_map.values())
            
            logger.info(f"Preserved relationships for {len(preserved_data)} unique banks")
            return preserved_data
            
        except Exception as e:
            logger.error(f"Error preserving data relationships: {e}")
            return fd_data_list
    
    def write_success_file(self, successful_data: List[FDRateData]) -> bool:
        """
        Write successful extractions to output file.
        
        Args:
            successful_data: List of successful FD rate data
            
        Returns:
            bool: True if write was successful, False otherwise
        """
        try:
            if not successful_data:
                logger.warning("No successful data to write")
                # Create empty file to indicate no successes
                self.success_file_path.write_text("[]", encoding='utf-8')
                return True
            
            # Format data based on configuration
            if self.config.extraction.output_format.lower() == 'csv':
                formatted_data = self.formatter.format_to_csv(successful_data)
                file_path = self.success_file_path.with_suffix('.csv')
            else:
                formatted_data = self.formatter.format_to_json(successful_data)
                file_path = self.success_file_path
            
            # Write to file
            file_path.write_text(formatted_data, encoding='utf-8')
            
            logger.info(f"Successfully wrote {len(successful_data)} successful extractions to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing success file: {e}")
            return False
    
    def write_failure_file(self, failed_data: List[FDRateData]) -> bool:
        """
        Write failed extractions to output file.
        
        Args:
            failed_data: List of failed FD rate data
            
        Returns:
            bool: True if write was successful, False otherwise
        """
        try:
            if not failed_data:
                logger.info("No failed data to write")
                # Create empty file to indicate no failures
                self.failure_file_path.write_text("[]", encoding='utf-8')
                return True
            
            # Format data based on configuration
            if self.config.extraction.output_format.lower() == 'csv':
                formatted_data = self.formatter.format_to_csv(failed_data)
                file_path = self.failure_file_path.with_suffix('.csv')
            else:
                formatted_data = self.formatter.format_to_json(failed_data)
                file_path = self.failure_file_path
            
            # Write to file
            file_path.write_text(formatted_data, encoding='utf-8')
            
            logger.info(f"Successfully wrote {len(failed_data)} failed extractions to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing failure file: {e}")
            return False
    
    def generate_summary_report(self, fd_data_list: List[FDRateData], 
                              start_time: datetime, end_time: datetime) -> ExtractionSummary:
        """
        Generate a comprehensive summary report of the extraction process.
        
        Args:
            fd_data_list: List of all FD rate data
            start_time: When the extraction process started
            end_time: When the extraction process ended
            
        Returns:
            ExtractionSummary: Summary of the extraction process
        """
        try:
            successful_data, failed_data = self.separate_success_failure(fd_data_list)
            
            summary = ExtractionSummary(
                total_banks=len(fd_data_list),
                successful_extractions=len(successful_data),
                failed_extractions=len(failed_data),
                start_time=start_time,
                end_time=end_time
            )
            
            # Collect error messages from failed extractions
            for fd_data in failed_data:
                if fd_data.error_message:
                    summary.add_error(f"{fd_data.bank_name}: {fd_data.error_message}")
            
            # Add detailed statistics
            if successful_data:
                total_rates = sum(len(fd_data.rates) for fd_data in successful_data)
                banks_with_senior_rates = sum(1 for fd_data in successful_data if fd_data.has_senior_citizen_rates())
                
                summary.add_error(f"Total rates extracted: {total_rates}")
                summary.add_error(f"Banks with senior citizen rates: {banks_with_senior_rates}")
            
            logger.info(f"Generated summary: {summary.success_rate:.1f}% success rate")
            return summary
            
        except Exception as e:
            logger.error(f"Error generating summary report: {e}")
            # Return basic summary on error
            return ExtractionSummary(
                total_banks=len(fd_data_list),
                successful_extractions=0,
                failed_extractions=len(fd_data_list),
                start_time=start_time,
                end_time=end_time
            )
    
    def write_summary_file(self, summary: ExtractionSummary) -> bool:
        """
        Write extraction summary to output file.
        
        Args:
            summary: The extraction summary to write
            
        Returns:
            bool: True if write was successful, False otherwise
        """
        try:
            formatted_summary = self.formatter.format_summary_to_json(summary)
            self.summary_file_path.write_text(formatted_summary, encoding='utf-8')
            
            logger.info(f"Successfully wrote summary report to {self.summary_file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing summary file: {e}")
            return False
    
    def save_all_outputs(self, fd_data_list: List[FDRateData], 
                        start_time: datetime, end_time: datetime) -> bool:
        """
        Save all outputs: success file, failure file, summary report, and Excel file.
        
        Args:
            fd_data_list: List of all FD rate data
            start_time: When the extraction process started
            end_time: When the extraction process ended
            
        Returns:
            bool: True if all outputs were saved successfully, False otherwise
        """
        try:
            # Preserve data relationships
            preserved_data = self.preserve_data_relationships(fd_data_list)
            
            # Separate success and failure data
            successful_data, failed_data = self.separate_success_failure(preserved_data)
            
            # Write output files
            success_written = self.write_success_file(successful_data)
            failure_written = self.write_failure_file(failed_data)
            
            # Write Excel file
            excel_written = self.write_excel_file(preserved_data)
            
            # Generate and write summary
            summary = self.generate_summary_report(preserved_data, start_time, end_time)
            summary_written = self.write_summary_file(summary)
            
            all_successful = success_written and failure_written and summary_written and excel_written
            
            if all_successful:
                logger.info("All output files saved successfully")
                self._log_output_summary(summary)
            else:
                logger.error("Some output files failed to save")
            
            return all_successful
            
        except Exception as e:
            logger.error(f"Error saving all outputs: {e}")
            return False
    
    def _log_output_summary(self, summary: ExtractionSummary):
        """
        Log a summary of the output files created.
        
        Args:
            summary: The extraction summary
        """
        try:
            logger.info("=" * 50)
            logger.info("EXTRACTION SUMMARY")
            logger.info("=" * 50)
            logger.info(f"Total banks processed: {summary.total_banks}")
            logger.info(f"Successful extractions: {summary.successful_extractions}")
            logger.info(f"Failed extractions: {summary.failed_extractions}")
            logger.info(f"Success rate: {summary.success_rate:.1f}%")
            
            if summary.duration:
                logger.info(f"Total duration: {summary.duration:.2f} seconds")
            
            logger.info(f"Output files created in: {self.output_dir}")
            logger.info(f"  - Success file: {self.success_file_path.name}")
            logger.info(f"  - Failure file: {self.failure_file_path.name}")
            logger.info(f"  - Summary file: {self.summary_file_path.name}")
            logger.info(f"  - Excel file: fd_rates_results.xlsx")
            logger.info("=" * 50)
            
        except Exception as e:
            logger.error(f"Error logging output summary: {e}")
    
    def cleanup_old_outputs(self, keep_last_n: int = 5) -> bool:
        """
        Clean up old output files, keeping only the most recent ones.
        
        Args:
            keep_last_n: Number of recent output sets to keep
            
        Returns:
            bool: True if cleanup was successful, False otherwise
        """
        try:
            # Find all output files with timestamps
            output_files = list(self.output_dir.glob("*_20*.json")) + list(self.output_dir.glob("*_20*.csv"))
            
            if len(output_files) <= keep_last_n * 3:  # 3 files per extraction run
                logger.info("No old output files to clean up")
                return True
            
            # Sort by modification time
            output_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            # Keep the most recent files
            files_to_keep = output_files[:keep_last_n * 3]
            files_to_delete = output_files[keep_last_n * 3:]
            
            # Delete old files
            deleted_count = 0
            for file_path in files_to_delete:
                try:
                    file_path.unlink()
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Could not delete {file_path}: {e}")
            
            logger.info(f"Cleaned up {deleted_count} old output files")
            return True
            
        except Exception as e:
            logger.error(f"Error cleaning up old outputs: {e}")
            return False
    
    def write_excel_file(self, fd_data_list: List[FDRateData]) -> bool:
        """
        Write extraction results to an Excel file with proper formatting.
        
        Args:
            fd_data_list: List of all FD rate data
            
        Returns:
            bool: True if write was successful, False otherwise
        """
        try:
            # Import period parser
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            from period_days_converter import PeriodParser
            
            # Initialize period parser
            period_parser = PeriodParser()
            
            # Separate successful and failed extractions
            successful_data, failed_data = self.separate_success_failure(fd_data_list)
            
            if not successful_data:
                logger.warning("No successful data to write to Excel")
                return False
            
            # Prepare data for Excel
            excel_data = []
            
            for fd_data in successful_data:
                for rate in fd_data.rates:
                    # Parse tenure to get day ranges
                    # Remove amount suffixes for parsing (e.g., " (<= 1 Lakh)")
                    tenure_for_parsing = rate.tenure
                    for suffix in [' (<= 1 Lakh)', ' (> 1 Lakh)', ' (< 1 Lakh)', ' (>= 1 Lakh)']:
                        tenure_for_parsing = tenure_for_parsing.replace(suffix, '')
                    
                    parse_result = period_parser.parse_period(tenure_for_parsing)
                    
                    # Validate and extract day ranges
                    if period_parser.validate_result(parse_result):
                        from_days = parse_result.from_days
                        to_days = parse_result.to_days
                    else:
                        from_days = None
                        to_days = None
                    
                    row = {
                        'Bank Name': fd_data.bank_name,
                        'Source URL': fd_data.source_url,
                        'Tenure': rate.tenure,
                        'Duration From (Days)': from_days if from_days is not None else '',
                        'Duration To (Days)': to_days if to_days is not None else '',
                        'General Rate (%)': rate.general_rate,
                        'Senior Citizen Rate (%)': rate.senior_citizen_rate if rate.senior_citizen_rate else '',
                        'Min Amount (₹)': rate.min_amount if rate.min_amount else '',
                        'Max Amount (₹)': rate.max_amount if rate.max_amount else '',
                        'Special Conditions': rate.special_conditions if rate.special_conditions else '',
                        'Extraction Date': fd_data.extraction_timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    excel_data.append(row)
            
            # Create DataFrame
            df = pd.DataFrame(excel_data)
            
            # Sort by bank name and tenure
            df = df.sort_values(['Bank Name', 'Tenure'])
            
            # Write to Excel with formatting
            excel_file_path = self.output_dir / 'fd_rates_results.xlsx'
            
            with pd.ExcelWriter(excel_file_path, engine='openpyxl') as writer:
                # Write main data sheet
                df.to_excel(writer, sheet_name='FD Rates', index=False)
                
                # Get the workbook and worksheet
                workbook = writer.book
                worksheet = writer.sheets['FD Rates']
                
                # Auto-adjust column widths
                for idx, col in enumerate(df.columns):
                    max_length = max(
                        df[col].astype(str).apply(len).max(),
                        len(col)
                    ) + 2
                    worksheet.column_dimensions[chr(65 + idx)].width = min(max_length, 50)
                
                # Create summary sheet
                summary_data = {
                    'Metric': [
                        'Total Banks Processed',
                        'Successful Extractions',
                        'Failed Extractions',
                        'Total Rates Extracted',
                        'Banks with Senior Citizen Rates',
                        'Rates Parsed to Days'
                    ],
                    'Value': [
                        len(fd_data_list),
                        len(successful_data),
                        len(failed_data),
                        len(excel_data),
                        sum(1 for fd_data in successful_data if fd_data.has_senior_citizen_rates()),
                        sum(1 for row in excel_data if row['Duration From (Days)'] != '')
                    ]
                }
                
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
                
                # Auto-adjust summary sheet columns
                summary_sheet = writer.sheets['Summary']
                summary_sheet.column_dimensions['A'].width = 30
                summary_sheet.column_dimensions['B'].width = 20
            
            logger.info(f"Successfully wrote {len(excel_data)} rate entries to {excel_file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error writing Excel file: {e}")
            return False
    
    def get_output_file_paths(self) -> Dict[str, Path]:
        """
        Get the paths of all output files.
        
        Returns:
            Dict[str, Path]: Dictionary mapping file types to their paths
        """
        return {
            'success': self.success_file_path,
            'failure': self.failure_file_path,
            'summary': self.summary_file_path,
            'output_dir': self.output_dir
        }