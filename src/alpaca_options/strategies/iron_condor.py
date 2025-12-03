"""Iron Condor Strategy - Market Neutral Income Strategy.

The Iron Condor is a market-neutral options strategy that profits from
low volatility and range-bound price action. It consists of:

1. Sell OTM Put (lower strike) - Bull Put Spread
2. Buy further OTM Put (protection)
3. Sell OTM Call (higher strike) - Bear Call Spread
4. Buy further OTM Call (protection)

Maximum profit: Net credit received
Maximum loss: Width of spread - Net credit
Best conditions: High IV, range-bound market, time decay
"""

from datetime import datetime
from typing import Any, Optional

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


class IronCondorStrategy(BaseStrategy):
    """Iron Condor Strategy for income generation in range-bound markets.

    Sells OTM put spread and OTM call spread to collect premium while
    defining maximum risk through the long wings.
    """

    def __init__(self) -> None:
        super().__init__()
        self._underlyings: list[str] = []
        self._delta_target: float = 0.16  # Delta for short strikes
        self._wing_width: int = 5  # Width between short and long strikes
        self._min_credit: float = 100.0  # Minimum total credit
        self._min_dte: int = 30
        self._max_dte: int = 45
        self._min_iv_rank: float = 30.0  # Higher IV for better premium
        self._min_iv_percentile: float = 30.0
        self._max_spread_percent: float = 3.0  # Tighter spreads for 4 legs
        self._min_open_interest: int = 500  # Higher OI for multi-leg

    @property
    def name(self) -> str:
        return "iron_condor"

    @property
    def description(self) -> str:
        return "Market neutral strategy selling OTM put and call spreads"

    async def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the iron condor strategy with configuration."""
        self._underlyings = config.get("underlyings", [])
        self._delta_target = config.get("delta_target", 0.16)
        self._wing_width = config.get("wing_width", 5)
        self._min_credit = config.get("min_credit", 100.0)
        self._min_dte = config.get("min_dte", 30)
        self._max_dte = config.get("max_dte", 45)
        self._min_iv_rank = config.get("min_iv_rank", 30.0)
        self._min_iv_percentile = config.get("min_iv_percentile", 30.0)
        self._max_spread_percent = config.get("max_spread_percent", 3.0)
        self._min_open_interest = config.get("min_open_interest", 500)

        self._config = config
        self._is_initialized = True

    async def on_market_data(self, data: MarketData) -> Optional[OptionSignal]:
        """Process market data update.

        Iron condor benefits from range-bound markets with high IV.
        """
        if data.symbol not in self._underlyings:
            return None

        # Check IV rank if available - we want elevated IV
        if data.iv_rank is not None and data.iv_rank < self._min_iv_rank:
            return None

        # Market data alone doesn't generate signals
        return None

    async def on_option_chain(self, chain: OptionChain) -> Optional[OptionSignal]:
        """Process options chain and potentially generate an iron condor signal."""
        if chain.underlying not in self._underlyings:
            return None

        return self._find_iron_condor_opportunity(chain)

    def _find_iron_condor_opportunity(
        self, chain: OptionChain
    ) -> Optional[OptionSignal]:
        """Find an iron condor opportunity in the options chain."""
        # Filter contracts by DTE
        valid_contracts = chain.filter_by_dte(self._min_dte, self._max_dte)
        if not valid_contracts:
            return None

        # Get unique expirations within our DTE range
        expirations = sorted(set(c.expiration for c in valid_contracts))
        if not expirations:
            return None

        # Try each expiration to find a valid iron condor
        for expiration in expirations:
            contracts_at_exp = [
                c for c in valid_contracts if c.expiration == expiration
            ]

            # Find the short put (sell OTM put near target delta)
            short_put = self._find_short_put(contracts_at_exp, chain.underlying_price)
            if not short_put:
                continue

            # Find the long put (buy further OTM for protection)
            long_put = self._find_long_put(contracts_at_exp, short_put)
            if not long_put:
                continue

            # Find the short call (sell OTM call near target delta)
            short_call = self._find_short_call(
                contracts_at_exp, chain.underlying_price
            )
            if not short_call:
                continue

            # Find the long call (buy further OTM for protection)
            long_call = self._find_long_call(contracts_at_exp, short_call)
            if not long_call:
                continue

            # Calculate net credit
            credit = self._calculate_credit(
                short_put, long_put, short_call, long_call
            )

            if credit < self._min_credit:
                continue

            # Calculate max risk (width of wider spread - credit)
            put_spread_width = (short_put.strike - long_put.strike) * 100
            call_spread_width = (long_call.strike - short_call.strike) * 100
            max_width = max(put_spread_width, call_spread_width)
            max_risk = max_width - credit

            # Risk/reward check - want at least 1:3 credit to max risk
            if credit / max_risk < 0.25:
                continue

            # Build the signal with all 4 legs
            legs = [
                # Sell OTM Put (short put)
                OptionLeg(
                    contract_symbol=short_put.symbol,
                    underlying=chain.underlying,
                    option_type="put",
                    strike=short_put.strike,
                    expiration=short_put.expiration,
                    side="sell",
                    quantity=1,
                    limit_price=short_put.bid,
                ),
                # Buy further OTM Put (long put / protection)
                OptionLeg(
                    contract_symbol=long_put.symbol,
                    underlying=chain.underlying,
                    option_type="put",
                    strike=long_put.strike,
                    expiration=long_put.expiration,
                    side="buy",
                    quantity=1,
                    limit_price=long_put.ask,
                ),
                # Sell OTM Call (short call)
                OptionLeg(
                    contract_symbol=short_call.symbol,
                    underlying=chain.underlying,
                    option_type="call",
                    strike=short_call.strike,
                    expiration=short_call.expiration,
                    side="sell",
                    quantity=1,
                    limit_price=short_call.bid,
                ),
                # Buy further OTM Call (long call / protection)
                OptionLeg(
                    contract_symbol=long_call.symbol,
                    underlying=chain.underlying,
                    option_type="call",
                    strike=long_call.strike,
                    expiration=long_call.expiration,
                    side="buy",
                    quantity=1,
                    limit_price=long_call.ask,
                ),
            ]

            # Calculate confidence based on IV and spread quality
            confidence = self._calculate_confidence(
                short_put, long_put, short_call, long_call, credit, max_risk
            )

            return OptionSignal(
                signal_type=SignalType.IRON_CONDOR,
                underlying=chain.underlying,
                legs=legs,
                confidence=confidence,
                strategy_name=self.name,
                metadata={
                    "net_credit": credit,
                    "max_risk": max_risk,
                    "put_spread_width": put_spread_width,
                    "call_spread_width": call_spread_width,
                    "short_put_strike": short_put.strike,
                    "long_put_strike": long_put.strike,
                    "short_call_strike": short_call.strike,
                    "long_call_strike": long_call.strike,
                    "short_put_delta": short_put.delta,
                    "short_call_delta": short_call.delta,
                    "dte": short_put.days_to_expiry,
                    "underlying_price": chain.underlying_price,
                    "return_on_risk": (credit / max_risk) * 100,
                },
            )

        return None

    def _find_short_put(
        self, contracts: list[OptionContract], underlying_price: float
    ) -> Optional[OptionContract]:
        """Find the short put strike near target delta."""
        puts = [c for c in contracts if c.option_type == "put"]

        # Filter for OTM puts (strike below current price)
        otm_puts = [p for p in puts if p.strike < underlying_price]

        candidates = []
        for put in otm_puts:
            if put.delta is None:
                continue

            # Put deltas are negative, we want absolute value near target
            delta_diff = abs(abs(put.delta) - self._delta_target)

            # Check liquidity
            if put.spread_percent > self._max_spread_percent:
                continue
            if put.open_interest < self._min_open_interest:
                continue

            candidates.append((put, delta_diff))

        if not candidates:
            return None

        # Sort by delta proximity
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    def _find_long_put(
        self, contracts: list[OptionContract], short_put: OptionContract
    ) -> Optional[OptionContract]:
        """Find the long put (protection) below short put strike."""
        puts = [c for c in contracts if c.option_type == "put"]

        # Target strike is wing_width below short put
        target_strike = short_put.strike - self._wing_width

        candidates = []
        for put in puts:
            # Must be below short put strike
            if put.strike >= short_put.strike:
                continue

            strike_diff = abs(put.strike - target_strike)

            # Check liquidity (can be more lenient for long legs)
            if put.spread_percent > self._max_spread_percent * 2:
                continue
            if put.open_interest < self._min_open_interest // 2:
                continue

            candidates.append((put, strike_diff))

        if not candidates:
            return None

        # Sort by strike proximity to target
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    def _find_short_call(
        self, contracts: list[OptionContract], underlying_price: float
    ) -> Optional[OptionContract]:
        """Find the short call strike near target delta."""
        calls = [c for c in contracts if c.option_type == "call"]

        # Filter for OTM calls (strike above current price)
        otm_calls = [c for c in calls if c.strike > underlying_price]

        candidates = []
        for call in otm_calls:
            if call.delta is None:
                continue

            # Call deltas are positive
            delta_diff = abs(call.delta - self._delta_target)

            # Check liquidity
            if call.spread_percent > self._max_spread_percent:
                continue
            if call.open_interest < self._min_open_interest:
                continue

            candidates.append((call, delta_diff))

        if not candidates:
            return None

        # Sort by delta proximity
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    def _find_long_call(
        self, contracts: list[OptionContract], short_call: OptionContract
    ) -> Optional[OptionContract]:
        """Find the long call (protection) above short call strike."""
        calls = [c for c in contracts if c.option_type == "call"]

        # Target strike is wing_width above short call
        target_strike = short_call.strike + self._wing_width

        candidates = []
        for call in calls:
            # Must be above short call strike
            if call.strike <= short_call.strike:
                continue

            strike_diff = abs(call.strike - target_strike)

            # Check liquidity (can be more lenient for long legs)
            if call.spread_percent > self._max_spread_percent * 2:
                continue
            if call.open_interest < self._min_open_interest // 2:
                continue

            candidates.append((call, strike_diff))

        if not candidates:
            return None

        # Sort by strike proximity to target
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    def _calculate_credit(
        self,
        short_put: OptionContract,
        long_put: OptionContract,
        short_call: OptionContract,
        long_call: OptionContract,
    ) -> float:
        """Calculate the net credit from all legs."""
        # Credit from short legs (sell at bid)
        credit = (short_put.bid + short_call.bid) * 100

        # Debit from long legs (buy at ask)
        debit = (long_put.ask + long_call.ask) * 100

        return credit - debit

    def _calculate_confidence(
        self,
        short_put: OptionContract,
        long_put: OptionContract,
        short_call: OptionContract,
        long_call: OptionContract,
        credit: float,
        max_risk: float,
    ) -> float:
        """Calculate signal confidence based on trade quality."""
        confidence = 0.5  # Base confidence

        # Better risk/reward improves confidence
        ror = credit / max_risk
        if ror >= 0.40:
            confidence += 0.15
        elif ror >= 0.30:
            confidence += 0.10

        # Tighter spreads improve confidence
        avg_spread = (
            short_put.spread_percent
            + short_call.spread_percent
            + long_put.spread_percent
            + long_call.spread_percent
        ) / 4
        if avg_spread < 1.0:
            confidence += 0.10
        elif avg_spread < 2.0:
            confidence += 0.05

        # Good open interest improves confidence
        min_oi = min(
            short_put.open_interest,
            short_call.open_interest,
            long_put.open_interest,
            long_call.open_interest,
        )
        if min_oi >= 1000:
            confidence += 0.10
        elif min_oi >= 500:
            confidence += 0.05

        # Cap confidence at 0.85
        return min(confidence, 0.85)

    def get_criteria(self) -> StrategyCriteria:
        """Return criteria for when this strategy is applicable."""
        return StrategyCriteria(
            min_iv_rank=self._min_iv_rank,
            min_iv_percentile=self._min_iv_percentile,
            min_price=50.0,  # Need decent price for wing width
            max_price=1000.0,
            min_volume=1000000,  # High liquidity important for 4 legs
            min_open_interest=self._min_open_interest,
            max_bid_ask_spread_percent=self._max_spread_percent,
            min_days_to_expiry=self._min_dte,
            max_days_to_expiry=self._max_dte,
            trading_hours_only=True,
        )

    async def cleanup(self) -> None:
        """Cleanup resources."""
        self._is_initialized = False
