"""Tests for the Wheel Strategy."""

from datetime import datetime, timedelta

import pytest

from alpaca_options.strategies.base import MarketData, OptionChain, OptionContract
from alpaca_options.strategies.wheel import WheelStrategy


@pytest.fixture
def wheel_strategy() -> WheelStrategy:
    """Create a wheel strategy instance."""
    return WheelStrategy()


@pytest.fixture
def sample_config() -> dict:
    """Sample configuration for wheel strategy."""
    return {
        "underlyings": ["AAPL", "MSFT"],
        "delta_target": 0.30,
        "min_premium": 50,
        "min_dte": 21,
        "max_dte": 45,
        "min_iv_rank": 20,
    }


@pytest.fixture
def sample_option_chain() -> OptionChain:
    """Create a sample option chain for testing."""
    expiration = datetime.now() + timedelta(days=30)

    contracts = [
        # OTM Puts
        OptionContract(
            symbol="AAPL240119P00170000",
            underlying="AAPL",
            option_type="put",
            strike=170.0,
            expiration=expiration,
            bid=2.50,
            ask=2.60,
            last=2.55,
            volume=1000,
            open_interest=5000,
            delta=-0.25,
            gamma=0.02,
            theta=-0.05,
            vega=0.10,
            implied_volatility=0.25,
        ),
        OptionContract(
            symbol="AAPL240119P00175000",
            underlying="AAPL",
            option_type="put",
            strike=175.0,
            expiration=expiration,
            bid=3.50,
            ask=3.65,
            last=3.55,
            volume=800,
            open_interest=4000,
            delta=-0.32,
            gamma=0.025,
            theta=-0.06,
            vega=0.12,
            implied_volatility=0.26,
        ),
        # OTM Calls
        OptionContract(
            symbol="AAPL240119C00190000",
            underlying="AAPL",
            option_type="call",
            strike=190.0,
            expiration=expiration,
            bid=2.00,
            ask=2.10,
            last=2.05,
            volume=1200,
            open_interest=6000,
            delta=0.28,
            gamma=0.02,
            theta=-0.04,
            vega=0.09,
            implied_volatility=0.24,
        ),
    ]

    return OptionChain(
        underlying="AAPL",
        underlying_price=182.50,
        timestamp=datetime.now(),
        contracts=contracts,
    )


class TestWheelStrategy:
    """Tests for WheelStrategy."""

    def test_strategy_properties(self, wheel_strategy: WheelStrategy) -> None:
        """Test strategy name and description."""
        assert wheel_strategy.name == "wheel"
        assert "income" in wheel_strategy.description.lower()

    @pytest.mark.asyncio
    async def test_initialize(
        self, wheel_strategy: WheelStrategy, sample_config: dict
    ) -> None:
        """Test strategy initialization."""
        await wheel_strategy.initialize(sample_config)

        assert wheel_strategy.is_initialized
        assert wheel_strategy._underlyings == ["AAPL", "MSFT"]
        assert wheel_strategy._delta_target == 0.30

    @pytest.mark.asyncio
    async def test_csp_signal_generation(
        self,
        wheel_strategy: WheelStrategy,
        sample_config: dict,
        sample_option_chain: OptionChain,
    ) -> None:
        """Test cash-secured put signal generation."""
        await wheel_strategy.initialize(sample_config)

        signal = await wheel_strategy.on_option_chain(sample_option_chain)

        assert signal is not None
        assert signal.signal_type.value == "sell_put"
        assert signal.underlying == "AAPL"
        assert len(signal.legs) == 1
        assert signal.legs[0].option_type == "put"
        assert signal.legs[0].side == "sell"

    @pytest.mark.asyncio
    async def test_cc_signal_generation(
        self,
        wheel_strategy: WheelStrategy,
        sample_config: dict,
        sample_option_chain: OptionChain,
    ) -> None:
        """Test covered call signal generation when holding stock."""
        await wheel_strategy.initialize(sample_config)

        # Set state to stock (simulating assignment)
        wheel_strategy.set_state("AAPL", "stock")

        signal = await wheel_strategy.on_option_chain(sample_option_chain)

        assert signal is not None
        assert signal.signal_type.value == "sell_call"
        assert signal.underlying == "AAPL"
        assert len(signal.legs) == 1
        assert signal.legs[0].option_type == "call"
        assert signal.legs[0].side == "sell"

    @pytest.mark.asyncio
    async def test_ignores_non_configured_underlying(
        self,
        wheel_strategy: WheelStrategy,
        sample_config: dict,
    ) -> None:
        """Test that strategy ignores underlyings not in config."""
        await wheel_strategy.initialize(sample_config)

        # Create chain for non-configured underlying
        chain = OptionChain(
            underlying="TSLA",
            underlying_price=250.0,
            timestamp=datetime.now(),
            contracts=[],
        )

        signal = await wheel_strategy.on_option_chain(chain)
        assert signal is None

    def test_get_criteria(self, wheel_strategy: WheelStrategy) -> None:
        """Test strategy criteria."""
        criteria = wheel_strategy.get_criteria()

        assert criteria.min_iv_rank is not None
        assert criteria.min_open_interest == 100
        assert criteria.max_bid_ask_spread_percent == 5.0
        assert criteria.trading_hours_only is True

    @pytest.mark.asyncio
    async def test_cleanup(
        self, wheel_strategy: WheelStrategy, sample_config: dict
    ) -> None:
        """Test strategy cleanup."""
        await wheel_strategy.initialize(sample_config)
        wheel_strategy.set_state("AAPL", "stock")

        await wheel_strategy.cleanup()

        assert not wheel_strategy.is_initialized
        assert len(wheel_strategy._state) == 0
