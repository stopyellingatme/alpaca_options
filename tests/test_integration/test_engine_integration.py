"""Integration tests for strategy registration and engine interaction."""

import pytest

from alpaca_options.strategies.debit_spread import DebitSpreadStrategy


class TestDebitSpreadStrategyRegistration:
    """Tests for DebitSpreadStrategy integration with the trading engine."""

    @pytest.fixture
    def sample_config(self) -> dict:
        """Sample configuration for debit spread strategy."""
        return {
            "underlyings": ["QQQ", "SPY"],
            "long_delta_min": 0.60,
            "long_delta_max": 0.70,
            "short_delta_min": 0.30,
            "short_delta_max": 0.40,
            "min_dte": 30,
            "max_dte": 45,
            "close_dte": 21,
            "min_iv_rank": 20.0,
            "max_spread_percent": 5.0,
            "min_open_interest": 100,
            "rsi_oversold": 45.0,
            "rsi_overbought": 55.0,
            "max_debit_to_width_ratio": 0.60,
            "min_debit": 30.0,
            "profit_target_pct": 0.50,
            "stop_loss_pct": 2.0,
        }

    @pytest.mark.asyncio
    async def test_strategy_initialization(self, sample_config: dict) -> None:
        """Test that DebitSpreadStrategy initializes correctly with configuration."""
        strategy = DebitSpreadStrategy()

        # Should not be initialized yet
        assert not strategy._is_initialized

        # Initialize with config
        await strategy.initialize(sample_config)

        # Should now be initialized
        assert strategy._is_initialized
        assert strategy._underlyings == ["QQQ", "SPY"]
        assert strategy._long_delta_min == 0.60
        assert strategy._long_delta_max == 0.70
        assert strategy._short_delta_min == 0.30
        assert strategy._short_delta_max == 0.40

    @pytest.mark.asyncio
    async def test_strategy_properties(self, sample_config: dict) -> None:
        """Test strategy name and description properties."""
        strategy = DebitSpreadStrategy()
        await strategy.initialize(sample_config)

        assert strategy.name == "debit_spread"
        assert isinstance(strategy.description, str)
        assert len(strategy.description) > 0

    @pytest.mark.asyncio
    async def test_strategy_cleanup(self, sample_config: dict) -> None:
        """Test strategy cleanup releases resources."""
        strategy = DebitSpreadStrategy()
        await strategy.initialize(sample_config)

        # Add some cached market data
        from alpaca_options.strategies.base import MarketData

        market_data = MarketData(
            symbol="QQQ",
            timestamp="2024-01-01T10:00:00",
            close=400.0,
            rsi_14=40.0,
        )
        await strategy.on_market_data(market_data)

        # Verify data was cached
        assert "QQQ" in strategy._market_data

        # Cleanup
        await strategy.cleanup()

        # Should clear cache and reset initialization
        assert len(strategy._market_data) == 0
        assert not strategy._is_initialized

    @pytest.mark.asyncio
    async def test_strategy_receives_market_data(self, sample_config: dict) -> None:
        """Test that strategy correctly receives and caches market data."""
        strategy = DebitSpreadStrategy()
        await strategy.initialize(sample_config)

        from alpaca_options.strategies.base import MarketData

        # Send market data for tracked underlying
        market_data = MarketData(
            symbol="QQQ",
            timestamp="2024-01-01T10:00:00",
            close=400.0,
            rsi_14=40.0,
            sma_20=395.0,
            sma_50=390.0,
            volume=50000000,
            iv_rank=25.0,
        )

        result = await strategy.on_market_data(market_data)

        # Market data alone doesn't generate signals
        assert result is None

        # But it should be cached
        assert "QQQ" in strategy._market_data
        assert strategy._market_data["QQQ"].rsi_14 == 40.0

    @pytest.mark.asyncio
    async def test_strategy_ignores_untracked_symbols(self, sample_config: dict) -> None:
        """Test that strategy ignores market data for symbols not in config."""
        strategy = DebitSpreadStrategy()
        await strategy.initialize(sample_config)

        from alpaca_options.strategies.base import MarketData

        # Send market data for untracked symbol
        market_data = MarketData(
            symbol="AAPL",  # Not in underlyings list
            timestamp="2024-01-01T10:00:00",
            close=150.0,
            rsi_14=40.0,
        )

        result = await strategy.on_market_data(market_data)

        # Should return None (ignored)
        assert result is None

        # Should not be cached
        assert "AAPL" not in strategy._market_data

    @pytest.mark.asyncio
    async def test_strategy_filters_low_iv_rank(self, sample_config: dict) -> None:
        """Test that strategy filters out market data when IV rank is too low."""
        strategy = DebitSpreadStrategy()
        await strategy.initialize(sample_config)

        from alpaca_options.strategies.base import MarketData

        # Send market data with IV rank below threshold (config has min_iv_rank=20.0)
        market_data = MarketData(
            symbol="QQQ",
            timestamp="2024-01-01T10:00:00",
            close=400.0,
            rsi_14=40.0,
            iv_rank=15.0,  # Below threshold
        )

        result = await strategy.on_market_data(market_data)

        # Should return None due to low IV rank
        assert result is None

    @pytest.mark.asyncio
    async def test_strategy_criteria(self, sample_config: dict) -> None:
        """Test that strategy returns correct criteria for filtering."""
        strategy = DebitSpreadStrategy()
        await strategy.initialize(sample_config)

        criteria = strategy.get_criteria()

        # Verify criteria matches configuration
        assert criteria.min_iv_rank == 20.0
        assert criteria.min_days_to_expiry == 30
        assert criteria.max_days_to_expiry == 45
        assert criteria.max_bid_ask_spread_percent == 5.0
        assert criteria.min_open_interest == 100
        assert criteria.trading_hours_only is True

    @pytest.mark.asyncio
    async def test_strategy_handles_option_chain_without_market_data(
        self, sample_config: dict
    ) -> None:
        """Test that strategy handles option chain when no market data is cached."""
        strategy = DebitSpreadStrategy()
        await strategy.initialize(sample_config)

        from datetime import datetime, timedelta

        from alpaca_options.strategies.base import OptionChain, OptionContract

        # Create a minimal option chain
        expiration = datetime.now() + timedelta(days=35)
        contracts = [
            OptionContract(
                symbol="QQQ240115C00400000",
                underlying="QQQ",
                option_type="call",
                strike=400.0,
                expiration=expiration,
                bid=10.0,
                ask=10.5,
                last=10.2,
                volume=1000,
                open_interest=5000,
                implied_volatility=0.25,
                delta=0.65,
                gamma=0.05,
                theta=-0.10,
                vega=0.15,
                days_to_expiry=35,
                bid_size=10,
                ask_size=10,
            )
        ]

        chain = OptionChain(
            underlying="QQQ",
            underlying_price=400.0,
            timestamp=datetime.now(),
            contracts=contracts,
        )

        # Should return None because no market data cached (no direction)
        result = await strategy.on_option_chain(chain)
        assert result is None
