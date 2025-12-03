"""Wheel Strategy - Cash Secured Puts and Covered Calls.

The Wheel Strategy is an income-focused options strategy that cycles between
selling cash-secured puts (CSP) and covered calls (CC):

1. Sell CSP on a stock you want to own
2. If assigned, you own the stock at the strike price
3. Sell covered calls on the stock
4. If assigned, you sell the stock and return to step 1
"""

from datetime import datetime
from typing import Any, Optional

from alpaca_options.strategies.base import (
    BaseStrategy,
    MarketData,
    OptionChain,
    OptionLeg,
    OptionSignal,
    SignalType,
)
from alpaca_options.strategies.criteria import StrategyCriteria


class WheelStrategy(BaseStrategy):
    """The Wheel Strategy for income generation.

    Cycles between cash-secured puts and covered calls to generate
    consistent premium income while potentially acquiring stock at
    a discount.
    """

    def __init__(self) -> None:
        super().__init__()
        self._underlyings: list[str] = []
        self._delta_target: float = 0.30
        self._min_premium: float = 50.0
        self._min_dte: int = 21
        self._max_dte: int = 45
        self._min_iv_rank: float = 20.0

        # Track current state per underlying
        self._state: dict[str, str] = {}  # "cash" or "stock"

    @property
    def name(self) -> str:
        return "wheel"

    @property
    def description(self) -> str:
        return "Income strategy cycling between CSP and covered calls"

    async def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the wheel strategy with configuration."""
        self._underlyings = config.get("underlyings", [])
        self._delta_target = config.get("delta_target", 0.30)
        self._min_premium = config.get("min_premium", 50.0)
        self._min_dte = config.get("min_dte", 21)
        self._max_dte = config.get("max_dte", 45)
        self._min_iv_rank = config.get("min_iv_rank", 20.0)

        # Initialize state - assume we start with cash
        for underlying in self._underlyings:
            self._state[underlying] = "cash"

        self._config = config
        self._is_initialized = True

    async def on_market_data(self, data: MarketData) -> Optional[OptionSignal]:
        """Process market data update.

        The wheel strategy primarily reacts to options chain data,
        but we use market data to validate conditions.
        """
        if data.symbol not in self._underlyings:
            return None

        # Check IV rank if available
        if data.iv_rank is not None and data.iv_rank < self._min_iv_rank:
            return None

        # Market data alone doesn't generate signals for this strategy
        return None

    async def on_option_chain(self, chain: OptionChain) -> Optional[OptionSignal]:
        """Process options chain and potentially generate a signal."""
        if chain.underlying not in self._underlyings:
            return None

        current_state = self._state.get(chain.underlying, "cash")

        if current_state == "cash":
            return self._find_csp_opportunity(chain)
        else:
            return self._find_cc_opportunity(chain)

    def _find_csp_opportunity(self, chain: OptionChain) -> Optional[OptionSignal]:
        """Find a cash-secured put opportunity."""
        # Filter puts by DTE
        puts = [
            c for c in chain.get_puts()
            if self._min_dte <= c.days_to_expiry <= self._max_dte
        ]

        if not puts:
            return None

        # Find puts near our target delta
        candidates = []
        for put in puts:
            if put.delta is None:
                continue

            delta_diff = abs(abs(put.delta) - self._delta_target)
            premium = put.mid_price * 100  # Premium per contract

            # Check minimum premium
            if premium < self._min_premium:
                continue

            # Check liquidity
            if put.spread_percent > 5:  # Max 5% spread
                continue

            if put.open_interest < 100:
                continue

            candidates.append((put, delta_diff, premium))

        if not candidates:
            return None

        # Sort by delta proximity, then by premium
        candidates.sort(key=lambda x: (x[1], -x[2]))
        best_put = candidates[0][0]

        # Create the signal
        leg = OptionLeg(
            contract_symbol=best_put.symbol,
            underlying=chain.underlying,
            option_type="put",
            strike=best_put.strike,
            expiration=best_put.expiration,
            side="sell",
            quantity=1,
            limit_price=best_put.bid,  # Sell at bid for conservative fill
        )

        return OptionSignal(
            signal_type=SignalType.SELL_PUT,
            underlying=chain.underlying,
            legs=[leg],
            confidence=0.7,
            strategy_name=self.name,
            metadata={
                "premium": best_put.mid_price * 100,
                "delta": best_put.delta,
                "iv": best_put.implied_volatility,
                "dte": best_put.days_to_expiry,
            },
        )

    def _find_cc_opportunity(self, chain: OptionChain) -> Optional[OptionSignal]:
        """Find a covered call opportunity."""
        # Filter calls by DTE
        calls = [
            c for c in chain.get_calls()
            if self._min_dte <= c.days_to_expiry <= self._max_dte
        ]

        if not calls:
            return None

        # Find calls near our target delta (OTM calls)
        candidates = []
        for call in calls:
            if call.delta is None:
                continue

            # For covered calls, we want OTM (delta < 0.5)
            if call.delta > 0.5:
                continue

            delta_diff = abs(call.delta - self._delta_target)
            premium = call.mid_price * 100

            if premium < self._min_premium:
                continue

            if call.spread_percent > 5:
                continue

            if call.open_interest < 100:
                continue

            candidates.append((call, delta_diff, premium))

        if not candidates:
            return None

        candidates.sort(key=lambda x: (x[1], -x[2]))
        best_call = candidates[0][0]

        leg = OptionLeg(
            contract_symbol=best_call.symbol,
            underlying=chain.underlying,
            option_type="call",
            strike=best_call.strike,
            expiration=best_call.expiration,
            side="sell",
            quantity=1,
            limit_price=best_call.bid,
        )

        return OptionSignal(
            signal_type=SignalType.SELL_CALL,
            underlying=chain.underlying,
            legs=[leg],
            confidence=0.7,
            strategy_name=self.name,
            metadata={
                "premium": best_call.mid_price * 100,
                "delta": best_call.delta,
                "iv": best_call.implied_volatility,
                "dte": best_call.days_to_expiry,
            },
        )

    def get_criteria(self) -> StrategyCriteria:
        """Return criteria for when this strategy is applicable."""
        return StrategyCriteria(
            min_iv_rank=self._min_iv_rank,
            min_price=10.0,  # Avoid penny stocks
            max_price=500.0,  # Avoid very expensive stocks
            min_volume=500000,  # Ensure liquidity
            min_open_interest=100,
            max_bid_ask_spread_percent=5.0,
            min_days_to_expiry=self._min_dte,
            max_days_to_expiry=self._max_dte,
            trading_hours_only=True,
        )

    def set_state(self, underlying: str, state: str) -> None:
        """Update the state for an underlying.

        Called when assignment occurs or position is closed.

        Args:
            underlying: The underlying symbol.
            state: Either "cash" or "stock".
        """
        if state not in ("cash", "stock"):
            raise ValueError(f"Invalid state: {state}")
        self._state[underlying] = state

    async def cleanup(self) -> None:
        """Cleanup resources."""
        self._state.clear()
        self._is_initialized = False
