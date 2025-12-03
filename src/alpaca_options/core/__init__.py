"""Core module for the trading engine."""

from alpaca_options.core.config import Settings, load_config
from alpaca_options.core.engine import TradingEngine
from alpaca_options.core.events import Event, EventBus, EventType
from alpaca_options.core.capital_manager import (
    CapitalManager,
    CapitalTier,
    StrategyCapitalRequirements,
    STRATEGY_CAPITAL_REQUIREMENTS,
    recommend_strategies_for_capital,
)

__all__ = [
    "Settings",
    "load_config",
    "TradingEngine",
    "Event",
    "EventBus",
    "EventType",
    "CapitalManager",
    "CapitalTier",
    "StrategyCapitalRequirements",
    "STRATEGY_CAPITAL_REQUIREMENTS",
    "recommend_strategies_for_capital",
]
