"""Debit Spread Strategy - Directional Limited Risk Strategy with Lower Capital Requirements.

Debit Spreads are directional strategies optimized for smaller accounts:

Bull Call Spread (Debit):
- Buy lower strike call (60-70 delta, ITM/near-money)
- Sell higher strike call (30-40 delta, OTM)
- Bullish bias, profits if price rises
- Lower capital requirement than credit spreads ($50-$250 vs $500)

Bear Put Spread (Debit):
- Buy higher strike put (60-70 delta, ITM/near-money)
- Sell lower strike put (30-40 delta, OTM)
- Bearish bias, profits if price drops
- Better risk/reward ratio than credit spreads (150% vs 25%)

Key Advantages:
- 60-80% less capital required vs credit spreads
- Higher probability of profit with ITM long legs
- Better suited for low IV environments (IV rank > 20 vs 30)
- Simplified direction logic: RSI-based only (no MA confirmation needed)
"""

from enum import Enum
from typing import Any

from alpaca_options.strategies.base import (
    BaseStrategy,
    MarketData,
    OptionChain,
    OptionContract,
    OptionLeg,
    OptionSignal,
    SignalType,
)
from alpaca_options.strategies.criteria import StrategyCriteria


class SpreadDirection(Enum):
    """Direction of the debit spread."""

    BULLISH = "bullish"
    BEARISH = "bearish"


class DebitSpreadStrategy(BaseStrategy):
    """Debit Spread Strategy for directional trades with lower capital requirements.

    This strategy is optimized for traders with $1,500+ accounts who want directional
    exposure without the high capital requirements of credit spreads. Uses RSI-based
    direction signals to trade bull call spreads (bullish) or bear put spreads (bearish).

    Key Features:
    - 60-70 delta long legs (ITM/near-money) for higher probability
    - 30-40 delta short legs (OTM) for defined risk
    - RSI-based direction only (oversold=bullish, overbought=bearish)
    - 30-45 DTE entry, close at 21 DTE
    - IV rank > 20 filter (lower than credit spreads)
    - 50% profit target, 200% stop loss
    - Max debit capped at 60% of spread width
    """

    def __init__(self) -> None:
        super().__init__()

        # Core configuration
        self._underlyings: list[str] = []

        # Delta selection (key difference from credit spreads)
        self._long_delta_min: float = 0.60  # Buy 60-70 delta (ITM/near-money)
        self._long_delta_max: float = 0.70
        self._short_delta_min: float = 0.30  # Sell 30-40 delta (OTM)
        self._short_delta_max: float = 0.40

        # DTE parameters
        self._min_dte: int = 30
        self._max_dte: int = 45
        self._close_dte: int = 21  # Close at 21 DTE to avoid gamma risk

        # IV and liquidity filters
        self._min_iv_rank: float = 20.0  # Lower than credit spreads (20 vs 30)
        self._max_spread_percent: float = 5.0
        self._min_open_interest: int = 100

        # Direction determination (RSI-based only, simpler than credit spreads)
        self._rsi_oversold: float = 45.0  # Bullish when RSI <= 45
        self._rsi_overbought: float = 55.0  # Bearish when RSI >= 55

        # Risk/reward filters
        self._max_debit_to_width_ratio: float = 0.60  # Max debit should be 60% of width
        self._min_debit: float = 30.0  # Minimum debit to ensure meaningful profit potential

        # Position management
        self._profit_target_pct: float = 0.50  # Close at 50% of max profit
        self._stop_loss_pct: float = 2.0  # Close at 200% of debit paid

        # Cached market data
        self._market_data: dict[str, MarketData] = {}

    @property
    def name(self) -> str:
        return "debit_spread"

    @property
    def description(self) -> str:
        return "Directional debit spread strategy optimized for low capital accounts"

    async def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the debit spread strategy with configuration."""
        self._underlyings = config.get("underlyings", [])

        # Delta selection
        self._long_delta_min = config.get("long_delta_min", 0.60)
        self._long_delta_max = config.get("long_delta_max", 0.70)
        self._short_delta_min = config.get("short_delta_min", 0.30)
        self._short_delta_max = config.get("short_delta_max", 0.40)

        # DTE parameters
        self._min_dte = config.get("min_dte", 30)
        self._max_dte = config.get("max_dte", 45)
        self._close_dte = config.get("close_dte", 21)

        # IV and liquidity
        self._min_iv_rank = config.get("min_iv_rank", 20.0)
        self._max_spread_percent = config.get("max_spread_percent", 5.0)
        self._min_open_interest = config.get("min_open_interest", 100)

        # Direction thresholds
        self._rsi_oversold = config.get("rsi_oversold", 45.0)
        self._rsi_overbought = config.get("rsi_overbought", 55.0)

        # Risk/reward
        self._max_debit_to_width_ratio = config.get("max_debit_to_width_ratio", 0.60)
        self._min_debit = config.get("min_debit", 30.0)

        # Position management
        self._profit_target_pct = config.get("profit_target_pct", 0.50)
        self._stop_loss_pct = config.get("stop_loss_pct", 2.0)

        self._config = config
        self._is_initialized = True

    async def on_market_data(self, data: MarketData) -> OptionSignal | None:
        """Process market data update and cache for direction determination."""
        if data.symbol not in self._underlyings:
            return None

        # Cache market data for use in option chain processing
        self._market_data[data.symbol] = data

        # Check IV rank if available
        if data.iv_rank is not None and data.iv_rank < self._min_iv_rank:
            return None

        # Market data alone doesn't generate signals
        return None

    async def on_option_chain(self, chain: OptionChain) -> OptionSignal | None:
        """Process options chain and potentially generate a debit spread signal."""
        if chain.underlying not in self._underlyings:
            return None

        # Determine market direction based on cached RSI
        direction = self._determine_direction(chain.underlying)
        if direction is None:
            return None

        # Filter contracts by DTE
        valid_contracts = chain.filter_by_dte(self._min_dte, self._max_dte)
        if not valid_contracts:
            return None

        # Get unique expirations
        expirations = sorted(set(c.expiration for c in valid_contracts))
        if not expirations:
            return None

        # Try each expiration
        for expiration in expirations:
            contracts_at_exp = [c for c in valid_contracts if c.expiration == expiration]

            # Generate appropriate debit spread based on direction
            if direction == SpreadDirection.BULLISH:
                signal = self._build_bull_call_spread(
                    contracts_at_exp, chain.underlying, chain.underlying_price
                )
            else:  # BEARISH
                signal = self._build_bear_put_spread(
                    contracts_at_exp, chain.underlying, chain.underlying_price
                )

            if signal is not None:
                return signal

        return None

    def _determine_direction(self, symbol: str) -> SpreadDirection | None:
        """Determine trading direction based on RSI (simpler than credit spreads).

        Uses RSI only for clear directional signals:
        - RSI <= oversold threshold (45): Bullish (buy call spread)
        - RSI >= overbought threshold (55): Bearish (buy put spread)
        - Between thresholds: No signal (wait for clearer direction)
        """
        data = self._market_data.get(symbol)
        if data is None or data.rsi_14 is None:
            return None

        # RSI-based direction determination
        if data.rsi_14 <= self._rsi_oversold:
            return SpreadDirection.BULLISH  # Oversold = bullish
        elif data.rsi_14 >= self._rsi_overbought:
            return SpreadDirection.BEARISH  # Overbought = bearish

        # No clear direction signal
        return None

    def _build_bull_call_spread(
        self,
        contracts: list[OptionContract],
        underlying: str,
        underlying_price: float,
    ) -> OptionSignal | None:
        """Build a bull call spread (buy call spread for debit).

        Strategy:
        - Buy 60-70 delta call (ITM/near-money, long leg)
        - Sell 30-40 delta call (OTM, short leg for defined risk)
        """
        calls = [c for c in contracts if c.option_type == "call"]
        if not calls:
            return None

        # Find long call (buy 60-70 delta, ITM/near-money)
        long_call = self._find_long_leg(calls, underlying_price, is_call=True)
        if not long_call:
            return None

        # Find short call (sell 30-40 delta, OTM)
        short_call = self._find_short_leg(calls, long_call.strike, underlying_price, is_call=True)
        if not short_call:
            return None

        # Calculate debit and validate
        debit = (long_call.ask - short_call.bid) * 100
        if debit < self._min_debit:
            return None

        # Calculate spread width and max profit
        spread_width_dollars = (short_call.strike - long_call.strike) * 100
        max_profit = spread_width_dollars - debit

        # Validate debit-to-width ratio
        debit_to_width = debit / spread_width_dollars if spread_width_dollars > 0 else 1.0
        if debit_to_width > self._max_debit_to_width_ratio:
            return None

        return self._create_signal(
            underlying=underlying,
            underlying_price=underlying_price,
            signal_type=SignalType.BUY_CALL_SPREAD,
            long_contract=long_call,
            short_contract=short_call,
            direction=SpreadDirection.BULLISH,
            debit=debit,
            max_profit=max_profit,
        )

    def _build_bear_put_spread(
        self,
        contracts: list[OptionContract],
        underlying: str,
        underlying_price: float,
    ) -> OptionSignal | None:
        """Build a bear put spread (buy put spread for debit).

        Strategy:
        - Buy 60-70 delta put (ITM/near-money, long leg)
        - Sell 30-40 delta put (OTM, short leg for defined risk)
        """
        puts = [c for c in contracts if c.option_type == "put"]
        if not puts:
            return None

        # Find long put (buy 60-70 delta, ITM/near-money)
        long_put = self._find_long_leg(puts, underlying_price, is_call=False)
        if not long_put:
            return None

        # Find short put (sell 30-40 delta, OTM)
        short_put = self._find_short_leg(puts, long_put.strike, underlying_price, is_call=False)
        if not short_put:
            return None

        # Calculate debit and validate
        debit = (long_put.ask - short_put.bid) * 100
        if debit < self._min_debit:
            return None

        # Calculate spread width and max profit
        spread_width_dollars = (long_put.strike - short_put.strike) * 100
        max_profit = spread_width_dollars - debit

        # Validate debit-to-width ratio
        debit_to_width = debit / spread_width_dollars if spread_width_dollars > 0 else 1.0
        if debit_to_width > self._max_debit_to_width_ratio:
            return None

        return self._create_signal(
            underlying=underlying,
            underlying_price=underlying_price,
            signal_type=SignalType.BUY_PUT_SPREAD,
            long_contract=long_put,
            short_contract=short_put,
            direction=SpreadDirection.BEARISH,
            debit=debit,
            max_profit=max_profit,
        )

    def _find_long_leg(
        self,
        contracts: list[OptionContract],
        underlying_price: float,
        is_call: bool,
    ) -> OptionContract | None:
        """Find the long leg contract (60-70 delta, ITM/near-money).

        For calls: strike < underlying price (ITM)
        For puts: strike > underlying price (ITM)
        """
        candidates = []

        for contract in contracts:
            if contract.delta is None:
                continue

            # Check delta range (60-70 delta)
            abs_delta = abs(contract.delta)
            if not (self._long_delta_min <= abs_delta <= self._long_delta_max):
                continue

            # For calls: ITM means strike < price
            # For puts: ITM means strike > price
            if is_call:
                if contract.strike >= underlying_price:
                    continue
            else:  # put
                if contract.strike <= underlying_price:
                    continue

            # Check liquidity
            if contract.spread_percent > self._max_spread_percent:
                continue
            if contract.open_interest < self._min_open_interest:
                continue

            # Calculate delta distance from ideal 65 delta
            delta_distance = abs(abs_delta - 0.65)
            candidates.append((contract, delta_distance))

        if not candidates:
            return None

        # Sort by delta distance (prefer closest to 65 delta)
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    def _find_short_leg(
        self,
        contracts: list[OptionContract],
        long_strike: float,
        underlying_price: float,
        is_call: bool,
    ) -> OptionContract | None:
        """Find the short leg contract (30-40 delta, OTM).

        For calls: strike > long_strike (higher strike)
        For puts: strike < long_strike (lower strike)
        """
        candidates = []

        for contract in contracts:
            if contract.delta is None:
                continue

            # Check delta range (30-40 delta)
            abs_delta = abs(contract.delta)
            if not (self._short_delta_min <= abs_delta <= self._short_delta_max):
                continue

            # Strike relationship to long leg
            if is_call:
                # Short call strike must be higher than long call
                if contract.strike <= long_strike:
                    continue
                # Should be OTM (strike > price)
                if contract.strike <= underlying_price:
                    continue
            else:  # put
                # Short put strike must be lower than long put
                if contract.strike >= long_strike:
                    continue
                # Should be OTM (strike < price)
                if contract.strike >= underlying_price:
                    continue

            # More lenient liquidity for short legs
            if contract.spread_percent > self._max_spread_percent * 2:
                continue
            if contract.open_interest < self._min_open_interest // 2:
                continue

            # Calculate delta distance from ideal 35 delta
            delta_distance = abs(abs_delta - 0.35)
            candidates.append((contract, delta_distance))

        if not candidates:
            return None

        # Sort by delta distance (prefer closest to 35 delta)
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    def _create_signal(
        self,
        underlying: str,
        underlying_price: float,
        signal_type: SignalType,
        long_contract: OptionContract,
        short_contract: OptionContract,
        direction: SpreadDirection,
        debit: float,
        max_profit: float,
    ) -> OptionSignal:
        """Create the option signal for the debit spread."""
        legs = [
            # Long leg (bought)
            OptionLeg(
                contract_symbol=long_contract.symbol,
                underlying=underlying,
                option_type=long_contract.option_type,
                strike=long_contract.strike,
                expiration=long_contract.expiration,
                side="buy",
                quantity=1,
                limit_price=long_contract.ask,
            ),
            # Short leg (sold)
            OptionLeg(
                contract_symbol=short_contract.symbol,
                underlying=underlying,
                option_type=short_contract.option_type,
                strike=short_contract.strike,
                expiration=short_contract.expiration,
                side="sell",
                quantity=1,
                limit_price=short_contract.bid,
            ),
        ]

        # Calculate confidence based on trade quality
        confidence = self._calculate_confidence(long_contract, short_contract, debit, max_profit)

        # Calculate spread width
        spread_width_dollars = abs(short_contract.strike - long_contract.strike) * 100

        # Calculate management levels for debit spreads
        # Profit target: close when profit reaches 50% of max profit
        profit_target = max_profit * self._profit_target_pct
        # Stop loss: close when loss reaches 200% of debit paid
        stop_loss = debit * self._stop_loss_pct

        return OptionSignal(
            signal_type=signal_type,
            underlying=underlying,
            legs=legs,
            confidence=confidence,
            strategy_name=self.name,
            metadata={
                "direction": direction.value,
                "is_debit_spread": True,
                "debit": debit,
                "max_profit": max_profit,
                "long_strike": long_contract.strike,
                "short_strike": short_contract.strike,
                "long_delta": long_contract.delta,
                "short_delta": short_contract.delta,
                "dte": long_contract.days_to_expiry,
                "close_dte": self._close_dte,
                "underlying_price": underlying_price,
                "spread_width": abs(short_contract.strike - long_contract.strike),
                "spread_width_dollars": spread_width_dollars,
                "return_on_risk": (max_profit / debit) * 100 if debit > 0 else 0,
                "debit_to_width_ratio": (
                    debit / spread_width_dollars if spread_width_dollars > 0 else 0
                ),
                # Management parameters for backtest engine
                "profit_target": profit_target,
                "stop_loss": stop_loss,
                "profit_target_pct": self._profit_target_pct,
                "stop_loss_pct": self._stop_loss_pct,
            },
        )

    def _calculate_confidence(
        self,
        long_contract: OptionContract,
        short_contract: OptionContract,
        debit: float,
        max_profit: float,
    ) -> float:
        """Calculate signal confidence based on trade quality.

        Higher confidence for:
        - Better risk/reward ratio (max_profit / debit)
        - Tighter bid-ask spreads (better execution)
        - Higher open interest (more liquidity)
        - Higher delta on long leg (more intrinsic value)
        """
        confidence = 0.5  # Base confidence

        # Risk/reward ratio (key metric for debit spreads)
        if debit > 0:
            risk_reward = max_profit / debit
            if risk_reward >= 2.0:  # 200%+ return
                confidence += 0.20
            elif risk_reward >= 1.5:  # 150%+ return
                confidence += 0.15
            elif risk_reward >= 1.0:  # 100%+ return
                confidence += 0.10

        # Tight spreads improve confidence
        avg_spread = (long_contract.spread_percent + short_contract.spread_percent) / 2
        if avg_spread < 1.5:
            confidence += 0.10
        elif avg_spread < 2.5:
            confidence += 0.05

        # Good open interest improves confidence
        min_oi = min(long_contract.open_interest, short_contract.open_interest)
        if min_oi >= 1000:
            confidence += 0.10
        elif min_oi >= 500:
            confidence += 0.05

        # Higher delta on long leg = more intrinsic value
        if long_contract.delta is not None:
            abs_delta = abs(long_contract.delta)
            if abs_delta >= 0.65:
                confidence += 0.05

        return min(confidence, 0.90)

    def get_criteria(self) -> StrategyCriteria:
        """Return criteria for when this strategy is applicable."""
        return StrategyCriteria(
            min_iv_rank=self._min_iv_rank,
            min_price=20.0,
            max_price=500.0,
            min_volume=500000,
            min_open_interest=self._min_open_interest,
            max_bid_ask_spread_percent=self._max_spread_percent,
            min_days_to_expiry=self._min_dte,
            max_days_to_expiry=self._max_dte,
            trading_hours_only=True,
        )

    async def cleanup(self) -> None:
        """Cleanup resources."""
        self._market_data.clear()
        self._is_initialized = False
