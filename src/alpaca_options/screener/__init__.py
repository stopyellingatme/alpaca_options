"""Stock screener module for dynamic symbol discovery."""

from alpaca_options.screener.base import (
    BaseScreener,
    ScreenerResult,
    ScreeningCriteria,
)
from alpaca_options.screener.scanner import Scanner
from alpaca_options.screener.technical import TechnicalScreener
from alpaca_options.screener.options import OptionsScreener
from alpaca_options.screener.universes import (
    SymbolUniverse,
    get_sp500_symbols,
    get_nasdaq100_symbols,
    get_options_friendly_symbols,
)
from alpaca_options.screener.integration import (
    ScreenerIntegration,
    IntegrationConfig,
    Opportunity,
    OpportunityType,
    OpportunityPriority,
    create_integration_from_clients,
)

__all__ = [
    "BaseScreener",
    "ScreenerResult",
    "ScreeningCriteria",
    "Scanner",
    "TechnicalScreener",
    "OptionsScreener",
    "SymbolUniverse",
    "get_sp500_symbols",
    "get_nasdaq100_symbols",
    "get_options_friendly_symbols",
    # Integration
    "ScreenerIntegration",
    "IntegrationConfig",
    "Opportunity",
    "OpportunityType",
    "OpportunityPriority",
    "create_integration_from_clients",
]
