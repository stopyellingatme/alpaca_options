"""Pytest configuration and fixtures."""

import pytest

from alpaca_options.core.config import Settings
from alpaca_options.strategies.registry import StrategyRegistry


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings()


@pytest.fixture
def strategy_registry() -> StrategyRegistry:
    """Create a fresh strategy registry."""
    return StrategyRegistry()
