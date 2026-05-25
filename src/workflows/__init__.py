"""
Workflow definitions for common research patterns.

Provides orchestrations that compose multiple agents and tools
into reusable, production-grade research pipelines.
"""

from src.workflows.whale_alert import WhaleAlertWorkflow
from src.workflows.portfolio_tracker import PortfolioTrackerWorkflow
from src.workflows.defi_scanner import DeFiScannerWorkflow

__all__ = [
    "WhaleAlertWorkflow",
    "PortfolioTrackerWorkflow",
    "DeFiScannerWorkflow",
]
