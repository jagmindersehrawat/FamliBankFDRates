"""Data models for the FD Rates Tool."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class BankInfo:
    """Information about a bank from the Excel file."""
    
    name: str
    base_url: str
    fd_rates_url: Optional[str] = None  # Direct FD rates URL from Excel column G
    discovered_fd_url: Optional[str] = None
    extraction_status: str = "pending"
    
    def __post_init__(self):
        """Validate and clean bank information."""
        self.name = self.name.strip() if self.name else ""
        self.base_url = self.base_url.strip() if self.base_url else ""
        
        # Ensure URL has protocol
        if self.base_url and not self.base_url.startswith(('http://', 'https://')):
            self.base_url = f"https://{self.base_url}"
        
        # Clean and validate fd_rates_url if provided
        if self.fd_rates_url:
            self.fd_rates_url = self.fd_rates_url.strip()
            if self.fd_rates_url and not self.fd_rates_url.startswith(('http://', 'https://')):
                self.fd_rates_url = f"https://{self.fd_rates_url}"


@dataclass
class RateEntry:
    """A single FD rate entry for a specific tenure and amount range."""
    
    tenure: str  # e.g., "1 Year", "18 Months"
    general_rate: float
    senior_citizen_rate: Optional[float] = None
    min_amount: Optional[int] = None
    max_amount: Optional[int] = None
    special_conditions: Optional[str] = None
    
    def __post_init__(self):
        """Validate rate entry data."""
        if self.general_rate < 0:
            raise ValueError("General rate cannot be negative")
        
        if self.senior_citizen_rate is not None and self.senior_citizen_rate < 0:
            raise ValueError("Senior citizen rate cannot be negative")
        
        if self.min_amount is not None and self.min_amount < 0:
            raise ValueError("Minimum amount cannot be negative")
        
        if self.max_amount is not None and self.max_amount < 0:
            raise ValueError("Maximum amount cannot be negative")
        
        if (self.min_amount is not None and 
            self.max_amount is not None and 
            self.min_amount > self.max_amount):
            raise ValueError("Minimum amount cannot be greater than maximum amount")


@dataclass
class FDRateData:
    """Complete FD rate data for a bank."""
    
    bank_name: str
    source_url: str
    extraction_timestamp: datetime
    rates: List[RateEntry] = field(default_factory=list)
    extraction_success: bool = True
    error_message: Optional[str] = None
    
    def add_rate(self, rate_entry: RateEntry):
        """Add a rate entry to the data."""
        self.rates.append(rate_entry)
    
    def get_rates_by_tenure(self, tenure: str) -> List[RateEntry]:
        """Get all rate entries for a specific tenure."""
        return [rate for rate in self.rates if rate.tenure.lower() == tenure.lower()]
    
    def has_senior_citizen_rates(self) -> bool:
        """Check if any rates have senior citizen information."""
        return any(rate.senior_citizen_rate is not None for rate in self.rates)


@dataclass
class ExtractionSummary:
    """Summary of the extraction process."""
    
    total_banks: int
    successful_extractions: int
    failed_extractions: int
    start_time: datetime
    end_time: Optional[datetime] = None
    errors: List[str] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """Calculate the success rate as a percentage."""
        if self.total_banks == 0:
            return 0.0
        return (self.successful_extractions / self.total_banks) * 100
    
    @property
    def duration(self) -> Optional[float]:
        """Calculate the total duration in seconds."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds()
    
    def add_error(self, error: str):
        """Add an error to the summary."""
        self.errors.append(error)
    
    def to_dict(self) -> dict:
        """Convert summary to dictionary for JSON serialization."""
        return {
            'total_banks': self.total_banks,
            'successful_extractions': self.successful_extractions,
            'failed_extractions': self.failed_extractions,
            'success_rate': self.success_rate,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat() if self.end_time else None,
            'duration_seconds': self.duration,
            'errors': self.errors
        }