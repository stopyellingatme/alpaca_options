"""Alpaca API integration layer."""

from alpaca_options.alpaca.client import AlpacaClient, get_alpaca_client
from alpaca_options.alpaca.trading import TradingManager, OrderResult, Position
from alpaca_options.alpaca.data import MarketDataManager, Quote, Bar
from alpaca_options.alpaca.options import OptionsDataManager, OptionQuote, OptionSnapshot

__all__ = [
    "AlpacaClient",
    "get_alpaca_client",
    "TradingManager",
    "OrderResult",
    "Position",
    "MarketDataManager",
    "Quote",
    "Bar",
    "OptionsDataManager",
    "OptionQuote",
    "OptionSnapshot",
]
