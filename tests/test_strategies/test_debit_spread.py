"""Tests for the Debit Spread Strategy."""

from datetime import datetime, timedelta
from typing import Any

import pytest

from alpaca_options.strategies.base import MarketData, OptionChain, OptionContract
from alpaca_options.strategies.debit_spread import DebitSpreadStrategy


@pytest.fixture
def debit_spread_strategy() -> DebitSpreadStrategy:
    """Create a debit spread strategy instance."""
    return DebitSpreadStrategy()


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """Sample configuration for debit spread strategy."""
    return {
        "underlyings": ["QQQ", "SPY"],
        "long_delta_min": 0.60,
        "long_delta_max": 0.70,
        "short_delta_min": 0.30,
        "short_delta_max": 0.40,
        "min_dte": 30,
        "max_dte": 45,
        "min_iv_rank": 20,
        "rsi_oversold": 45,
        "rsi_overbought": 55,
        "max_debit_to_width_ratio": 0.60,
        "min_debit": 30,
        "max_spread_percent": 5.0,
        "min_open_interest": 100,
        "profit_target_pct": 0.50,
        "stop_loss_pct": 2.0,
        "close_dte": 21,
    }


@pytest.fixture
def bullish_market_data() -> MarketData:
    """Create market data with bullish RSI signal (oversold)."""
    return MarketData(
        symbol="QQQ",
        timestamp=datetime.now(),
        price=380.50,
        volume=50000000,
        rsi=42.0,  # Below 45 = oversold = bullish
        sma_20=378.0,
        sma_50=375.0,
        iv_rank=35.0,
    )


@pytest.fixture
def bearish_market_data() -> MarketData:
    """Create market data with bearish RSI signal (overbought)."""
    return MarketData(
        symbol="QQQ",
        timestamp=datetime.now(),
        price=380.50,
        volume=50000000,
        rsi=58.0,  # Above 55 = overbought = bearish
        sma_20=378.0,
        sma_50=375.0,
        iv_rank=35.0,
    )


@pytest.fixture
def neutral_market_data() -> MarketData:
    """Create market data with neutral RSI (no signal)."""
    return MarketData(
        symbol="QQQ",
        timestamp=datetime.now(),
        price=380.50,
        volume=50000000,
        rsi=50.0,  # Between 45-55 = neutral = no signal
        sma_20=378.0,
        sma_50=375.0,
        iv_rank=35.0,
    )


@pytest.fixture
def bull_call_option_chain() -> OptionChain:
    """Create an option chain suitable for bull call spread.

    Bull call spread:
    - Buy 60-70 delta call (ITM or near-money)
    - Sell 30-40 delta call (OTM)
    """
    expiration = datetime.now() + timedelta(days=35)

    contracts = [
        # Long leg candidate: 65 delta call (ITM)
        OptionContract(
            symbol="QQQ250117C00375000",
            underlying="QQQ",
            option_type="call",
            strike=375.0,
            expiration=expiration,
            bid=8.50,
            ask=8.70,
            last=8.60,
            volume=2000,
            open_interest=5000,
            delta=0.65,
            gamma=0.03,
            theta=-0.08,
            vega=0.15,
            implied_volatility=0.22,
        ),
        # Short leg candidate: 35 delta call (OTM)
        OptionContract(
            symbol="QQQ250117C00385000",
            underlying="QQQ",
            option_type="call",
            strike=385.0,
            expiration=expiration,
            bid=3.80,
            ask=3.95,
            last=3.90,
            volume=1800,
            open_interest=4500,
            delta=0.35,
            gamma=0.025,
            theta=-0.06,
            vega=0.12,
            implied_volatility=0.21,
        ),
        # Additional contracts for variety
        OptionContract(
            symbol="QQQ250117C00380000",
            underlying="QQQ",
            option_type="call",
            strike=380.0,
            expiration=expiration,
            bid=6.20,
            ask=6.35,
            last=6.25,
            volume=2500,
            open_interest=6000,
            delta=0.50,
            gamma=0.035,
            theta=-0.09,
            vega=0.18,
            implied_volatility=0.22,
        ),
    ]

    return OptionChain(
        underlying="QQQ",
        underlying_price=380.50,
        timestamp=datetime.now(),
        contracts=contracts,
    )


@pytest.fixture
def bear_put_option_chain() -> OptionChain:
    """Create an option chain suitable for bear put spread.

    Bear put spread:
    - Buy 60-70 delta put (ITM or near-money)
    - Sell 30-40 delta put (OTM)
    """
    expiration = datetime.now() + timedelta(days=35)

    contracts = [
        # Long leg candidate: 65 delta put (ITM)
        OptionContract(
            symbol="QQQ250117P00385000",
            underlying="QQQ",
            option_type="put",
            strike=385.0,
            expiration=expiration,
            bid=8.80,
            ask=9.00,
            last=8.90,
            volume=1900,
            open_interest=4800,
            delta=-0.65,
            gamma=0.03,
            theta=-0.08,
            vega=0.15,
            implied_volatility=0.23,
        ),
        # Short leg candidate: 35 delta put (OTM)
        OptionContract(
            symbol="QQQ250117P00375000",
            underlying="QQQ",
            option_type="put",
            strike=375.0,
            expiration=expiration,
            bid=4.00,
            ask=4.15,
            last=4.05,
            volume=1700,
            open_interest=4200,
            delta=-0.35,
            gamma=0.025,
            theta=-0.06,
            vega=0.12,
            implied_volatility=0.22,
        ),
        # Additional contracts
        OptionContract(
            symbol="QQQ250117P00380000",
            underlying="QQQ",
            option_type="put",
            strike=380.0,
            expiration=expiration,
            bid=6.40,
            ask=6.55,
            last=6.45,
            volume=2200,
            open_interest=5500,
            delta=-0.50,
            gamma=0.035,
            theta=-0.09,
            vega=0.18,
            implied_volatility=0.23,
        ),
    ]

    return OptionChain(
        underlying="QQQ",
        underlying_price=380.50,
        timestamp=datetime.now(),
        contracts=contracts,
    )


class TestDebitSpreadStrategy:
    """Tests for DebitSpreadStrategy."""

    def test_strategy_properties(self, debit_spread_strategy: DebitSpreadStrategy) -> None:
        """Test strategy name and description."""
        assert debit_spread_strategy.name == "debit_spread"
        assert "debit" in debit_spread_strategy.description.lower()

    @pytest.mark.asyncio
    async def test_initialize(
        self, debit_spread_strategy: DebitSpreadStrategy, sample_config: dict[str, Any]
    ) -> None:
        """Test strategy initialization with config."""
        await debit_spread_strategy.initialize(sample_config)

        assert debit_spread_strategy.is_initialized
        assert debit_spread_strategy._underlyings == ["QQQ", "SPY"]
        assert debit_spread_strategy._long_delta_min == 0.60
        assert debit_spread_strategy._long_delta_max == 0.70
        assert debit_spread_strategy._short_delta_min == 0.30
        assert debit_spread_strategy._short_delta_max == 0.40

    @pytest.mark.asyncio
    async def test_direction_determination_bullish(
        self,
        debit_spread_strategy: DebitSpreadStrategy,
        sample_config: dict[str, Any],
        bullish_market_data: MarketData,
    ) -> None:
        """Test that oversold RSI (< 45) generates bullish direction."""
        await debit_spread_strategy.initialize(sample_config)

        # Process market data to cache RSI
        await debit_spread_strategy.on_market_data(bullish_market_data)

        # Access internal direction determination method
        direction = debit_spread_strategy._determine_direction("QQQ")

        assert direction is not None
        assert direction.value == "bull"

    @pytest.mark.asyncio
    async def test_direction_determination_bearish(
        self,
        debit_spread_strategy: DebitSpreadStrategy,
        sample_config: dict[str, Any],
        bearish_market_data: MarketData,
    ) -> None:
        """Test that overbought RSI (> 55) generates bearish direction."""
        await debit_spread_strategy.initialize(sample_config)

        # Process market data to cache RSI
        await debit_spread_strategy.on_market_data(bearish_market_data)

        # Access internal direction determination method
        direction = debit_spread_strategy._determine_direction("QQQ")

        assert direction is not None
        assert direction.value == "bear"

    @pytest.mark.asyncio
    async def test_direction_determination_neutral(
        self,
        debit_spread_strategy: DebitSpreadStrategy,
        sample_config: dict[str, Any],
        neutral_market_data: MarketData,
    ) -> None:
        """Test that neutral RSI (45-55) generates no signal."""
        await debit_spread_strategy.initialize(sample_config)

        # Process market data to cache RSI
        await debit_spread_strategy.on_market_data(neutral_market_data)

        # Access internal direction determination method
        direction = debit_spread_strategy._determine_direction("QQQ")

        assert direction is None

    @pytest.mark.asyncio
    async def test_bull_call_spread_signal_generation(
        self,
        debit_spread_strategy: DebitSpreadStrategy,
        sample_config: dict[str, Any],
        bullish_market_data: MarketData,
        bull_call_option_chain: OptionChain,
    ) -> None:
        """Test bull call spread signal generation with bullish RSI."""
        await debit_spread_strategy.initialize(sample_config)

        # Cache bullish market data
        await debit_spread_strategy.on_market_data(bullish_market_data)

        # Generate signal from option chain
        signal = await debit_spread_strategy.on_option_chain(bull_call_option_chain)

        assert signal is not None
        assert signal.signal_type.value == "buy_call_spread"
        assert signal.underlying == "QQQ"
        assert len(signal.legs) == 2

        # Check long leg (buy call)
        long_leg = signal.legs[0]
        assert long_leg.option_type == "call"
        assert long_leg.side == "buy"
        assert 0.60 <= long_leg.delta <= 0.70

        # Check short leg (sell call)
        short_leg = signal.legs[1]
        assert short_leg.option_type == "call"
        assert short_leg.side == "sell"
        assert 0.30 <= short_leg.delta <= 0.40

        # Check signal metadata
        assert "direction" in signal.metadata
        assert signal.metadata["direction"] == "bull"
        assert "debit_paid" in signal.metadata
        assert "max_profit" in signal.metadata
        assert "profit_target" in signal.metadata
        assert "stop_loss" in signal.metadata

    @pytest.mark.asyncio
    async def test_bear_put_spread_signal_generation(
        self,
        debit_spread_strategy: DebitSpreadStrategy,
        sample_config: dict[str, Any],
        bearish_market_data: MarketData,
        bear_put_option_chain: OptionChain,
    ) -> None:
        """Test bear put spread signal generation with bearish RSI."""
        await debit_spread_strategy.initialize(sample_config)

        # Cache bearish market data
        await debit_spread_strategy.on_market_data(bearish_market_data)

        # Generate signal from option chain
        signal = await debit_spread_strategy.on_option_chain(bear_put_option_chain)

        assert signal is not None
        assert signal.signal_type.value == "buy_put_spread"
        assert signal.underlying == "QQQ"
        assert len(signal.legs) == 2

        # Check long leg (buy put, higher strike)
        long_leg = signal.legs[0]
        assert long_leg.option_type == "put"
        assert long_leg.side == "buy"
        assert -0.70 <= long_leg.delta <= -0.60  # Negative for puts

        # Check short leg (sell put, lower strike)
        short_leg = signal.legs[1]
        assert short_leg.option_type == "put"
        assert short_leg.side == "sell"
        assert -0.40 <= short_leg.delta <= -0.30  # Negative for puts

        # Check signal metadata
        assert signal.metadata["direction"] == "bear"
        assert signal.metadata["debit_paid"] > 0
        assert signal.metadata["max_profit"] > 0

    @pytest.mark.asyncio
    async def test_delta_filtering(
        self,
        debit_spread_strategy: DebitSpreadStrategy,
        sample_config: dict[str, Any],
        bullish_market_data: MarketData,
        bull_call_option_chain: OptionChain,
    ) -> None:
        """Test that delta selection respects configured ranges."""
        await debit_spread_strategy.initialize(sample_config)
        await debit_spread_strategy.on_market_data(bullish_market_data)

        signal = await debit_spread_strategy.on_option_chain(bull_call_option_chain)

        if signal:
            long_leg = signal.legs[0]
            short_leg = signal.legs[1]

            # Verify delta ranges
            assert 0.60 <= long_leg.delta <= 0.70
            assert 0.30 <= short_leg.delta <= 0.40

    @pytest.mark.asyncio
    async def test_risk_reward_validation(
        self,
        debit_spread_strategy: DebitSpreadStrategy,
        sample_config: dict[str, Any],
        bullish_market_data: MarketData,
        bull_call_option_chain: OptionChain,
    ) -> None:
        """Test risk/reward validation (debit_to_width_ratio, min_debit)."""
        await debit_spread_strategy.initialize(sample_config)
        await debit_spread_strategy.on_market_data(bullish_market_data)

        signal = await debit_spread_strategy.on_option_chain(bull_call_option_chain)

        if signal:
            debit_paid = signal.metadata["debit_paid"]
            spread_width = signal.metadata["spread_width"]

            # Verify debit_to_width_ratio <= 0.60
            ratio = debit_paid / spread_width
            assert ratio <= 0.60

            # Verify min_debit >= $30
            assert debit_paid >= 30

    @pytest.mark.asyncio
    async def test_signal_metadata_structure(
        self,
        debit_spread_strategy: DebitSpreadStrategy,
        sample_config: dict[str, Any],
        bullish_market_data: MarketData,
        bull_call_option_chain: OptionChain,
    ) -> None:
        """Test that signal metadata includes all required fields."""
        await debit_spread_strategy.initialize(sample_config)
        await debit_spread_strategy.on_market_data(bullish_market_data)

        signal = await debit_spread_strategy.on_option_chain(bull_call_option_chain)

        if signal:
            required_fields = [
                "direction",
                "is_debit_spread",
                "debit_paid",
                "max_profit",
                "long_strike",
                "short_strike",
                "long_delta",
                "short_delta",
                "dte",
                "close_dte",
                "underlying_price",
                "spread_width",
                "debit_to_width_ratio",
                "profit_target",
                "stop_loss",
                "expiration",
            ]

            for field in required_fields:
                assert field in signal.metadata, f"Missing metadata field: {field}"

    @pytest.mark.asyncio
    async def test_ignores_non_configured_underlying(
        self,
        debit_spread_strategy: DebitSpreadStrategy,
        sample_config: dict[str, Any],
    ) -> None:
        """Test that strategy ignores underlyings not in config."""
        await debit_spread_strategy.initialize(sample_config)

        # Create chain for non-configured underlying
        chain = OptionChain(
            underlying="AAPL",
            underlying_price=180.0,
            timestamp=datetime.now(),
            contracts=[],
        )

        signal = await debit_spread_strategy.on_option_chain(chain)
        assert signal is None

    @pytest.mark.asyncio
    async def test_no_signal_without_market_data(
        self,
        debit_spread_strategy: DebitSpreadStrategy,
        sample_config: dict[str, Any],
        bull_call_option_chain: OptionChain,
    ) -> None:
        """Test that no signal is generated without cached market data."""
        await debit_spread_strategy.initialize(sample_config)

        # Don't call on_market_data - no RSI cached
        signal = await debit_spread_strategy.on_option_chain(bull_call_option_chain)

        # Should not generate signal without direction from RSI
        assert signal is None

    def test_get_criteria(
        self, debit_spread_strategy: DebitSpreadStrategy, sample_config: dict[str, Any]
    ) -> None:
        """Test strategy criteria for filtering."""
        criteria = debit_spread_strategy.get_criteria()

        assert criteria.min_iv_rank == 20
        assert criteria.min_open_interest == 100
        assert criteria.max_bid_ask_spread_percent == 5.0
        assert criteria.trading_hours_only is True

    @pytest.mark.asyncio
    async def test_cleanup(
        self, debit_spread_strategy: DebitSpreadStrategy, sample_config: dict[str, Any]
    ) -> None:
        """Test strategy cleanup."""
        await debit_spread_strategy.initialize(sample_config)

        # Cache some market data
        market_data = MarketData(
            symbol="QQQ",
            timestamp=datetime.now(),
            price=380.50,
            volume=50000000,
            rsi=42.0,
            sma_20=378.0,
            sma_50=375.0,
            iv_rank=35.0,
        )
        await debit_spread_strategy.on_market_data(market_data)

        await debit_spread_strategy.cleanup()

        assert not debit_spread_strategy.is_initialized
