"""Vertical Spread Strategy - Directional Limited Risk Strategy.

Vertical Spreads are directional strategies with defined risk/reward:

Bull Put Spread (Credit):
- Sell higher strike put
- Buy lower strike put
- Bullish bias, profits if price stays above short strike

Bear Put Spread (Debit):
- Buy higher strike put
- Sell lower strike put
- Bearish bias, profits if price drops below long strike

Bull Call Spread (Debit):
- Buy lower strike call
- Sell higher strike call
- Bullish bias, profits if price rises above long strike

Bear Call Spread (Credit):
- Sell lower strike call
- Buy higher strike call
- Bearish bias, profits if price stays below short strike
"""

import logging
from datetime import datetime
from enum import Enum
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

logger = logging.getLogger(__name__)


class SpreadDirection(Enum):
    """Direction of the vertical spread."""

    BULL = "bull"
    BEAR = "bear"


class SpreadType(Enum):
    """Type of vertical spread based on option type."""

    CALL = "call"
    PUT = "put"


class VerticalSpreadStrategy(BaseStrategy):
    """Vertical Spread Strategy for directional trades with defined risk.

    Supports both bull and bear spreads using calls or puts.
    The strategy uses technical indicators to determine direction.

    Key improvements based on research:
    - 20 delta short strike (vs 30) for higher probability of profit
    - 30-45 DTE entry, close at 21 DTE to avoid gamma risk
    - IV rank > 30 filter for better premium
    - 50% profit target for capital efficiency
    - 2x credit stop loss to limit downside
    """

    def __init__(self) -> None:
        super().__init__()
        self._underlyings: list[str] = []
        self._spread_width: int = 5  # Strike width between legs
        self._delta_target: float = 0.20  # 20 delta = ~80% probability OTM (global default)
        self._min_credit: float = 30.0  # Minimum credit (should be ~1/3 of width)
        self._min_dte: int = 30  # Enter with 30+ DTE for theta decay
        self._max_dte: int = 45  # Cap at 45 DTE
        self._close_dte: int = 21  # Close at 21 DTE to avoid gamma risk
        self._min_iv_rank: float = 30.0  # Only sell when IV is elevated
        self._max_spread_percent: float = 5.0  # Tighter bid-ask for better fills
        self._min_open_interest: int = 100  # Ensure liquidity
        self._prefer_credit: bool = True  # Credit spreads benefit from theta

        # Profit/Loss management (key improvement from research)
        self._profit_target_pct: float = 0.50  # Close at 50% of max profit
        self._stop_loss_multiplier: float = 2.0  # Close at 2x credit received

        # Technical thresholds for direction (widened for more opportunities)
        self._rsi_oversold: float = 45.0  # Bull signal when RSI <= this
        self._rsi_overbought: float = 55.0  # Bear signal when RSI >= this

        # Minimum return on risk for trade entry
        self._min_return_on_risk: float = 0.25  # Credit should be 1/4 of width (more opportunities)

        # Symbol-specific configurations (Phase 1 optimization support)
        self._symbol_configs: dict[str, dict[str, Any]] = {}

        # Cached market data for direction determination
        self._market_data: dict[str, MarketData] = {}

    @property
    def name(self) -> str:
        return "vertical_spread"

    @property
    def description(self) -> str:
        return "Directional spread strategy with defined risk/reward"

    async def initialize(self, config: dict[str, Any]) -> None:
        """Initialize the vertical spread strategy with configuration."""
        self._underlyings = config.get("underlyings", [])
        self._spread_width = config.get("spread_width", 5)
        self._delta_target = config.get("delta_target", 0.20)  # 20 delta default (global)
        self._min_credit = config.get("min_credit", 30.0)
        self._min_dte = config.get("min_dte", 30)  # 30 DTE minimum
        self._max_dte = config.get("max_dte", 45)
        self._close_dte = config.get("close_dte", 21)  # Close at 21 DTE
        self._min_iv_rank = config.get("min_iv_rank", 30.0)  # IV rank filter
        self._max_spread_percent = config.get("max_spread_percent", 5.0)
        self._min_open_interest = config.get("min_open_interest", 100)
        self._prefer_credit = config.get("prefer_credit", True)
        self._rsi_oversold = config.get("rsi_oversold", 40.0)
        self._rsi_overbought = config.get("rsi_overbought", 60.0)

        # Profit/Loss management parameters
        self._profit_target_pct = config.get("profit_target_pct", 0.50)
        self._stop_loss_multiplier = config.get("stop_loss_multiplier", 2.0)
        self._min_return_on_risk = config.get("min_return_on_risk", 0.33)

        # Load symbol-specific configurations (Phase 1 optimization)
        self._symbol_configs = config.get("symbol_configs", {})
        if self._symbol_configs:
            logger.info(f"Loaded symbol-specific configs for: {', '.join(self._symbol_configs.keys())}")
            for symbol, cfg in self._symbol_configs.items():
                delta = cfg.get("delta_target")
                if delta:
                    logger.info(f"  {symbol}: delta_target={delta:.2f}")

        self._config = config
        self._is_initialized = True

    def _get_delta_for_symbol(self, symbol: str) -> float:
        """Get delta target for a specific symbol.

        Uses symbol-specific delta from symbol_configs if available,
        otherwise falls back to global delta_target.

        Args:
            symbol: The underlying symbol

        Returns:
            Delta target for this symbol
        """
        # Check if symbol has specific configuration
        if symbol in self._symbol_configs:
            symbol_cfg = self._symbol_configs[symbol]
            delta = symbol_cfg.get("delta_target")
            if delta is not None:
                return delta

        # Fall back to global delta
        return self._delta_target

    async def on_market_data(self, data: MarketData) -> Optional[OptionSignal]:
        """Process market data update and cache for direction determination."""
        # Accept symbols from configured underlyings OR screener discoveries
        if data.symbol not in self._underlyings and data.symbol not in self._screener_symbols:
            return None

        # Cache market data for use in option chain processing
        self._market_data[data.symbol] = data

        # Check IV rank if available
        if data.iv_rank is not None and data.iv_rank < self._min_iv_rank:
            return None

        # Market data alone doesn't generate signals
        return None

    async def on_option_chain(self, chain: OptionChain) -> Optional[OptionSignal]:
        """Process options chain and potentially generate a spread signal."""
        # Accept symbols from configured underlyings OR screener discoveries
        if chain.underlying not in self._underlyings and chain.underlying not in self._screener_symbols:
            return None

        # Check for earnings risk
        if self.has_earnings_risk(chain.underlying, self._max_dte):
            logger.info(f"[{chain.underlying}] Skipping: earnings within {self._max_dte} day window")
            return None

        # Check for SEC risk (10-K, insider trading, auditor warnings, cash flow)
        if self.has_sec_risk(chain.underlying):
            logger.info(f"[{chain.underlying}] Skipping: SEC risk detected")
            return None

        # Determine market direction based on cached data
        direction = self._determine_direction(chain.underlying)
        if direction is None:
            return None

        return self._find_spread_opportunity(chain, direction)

    def _determine_direction(self, symbol: str) -> Optional[SpreadDirection]:
        """Determine trading direction based on market data.

        Uses a combination of RSI and moving averages:
        - RSI provides short-term momentum signals
        - Moving averages provide trend confirmation
        - Either signal alone can trigger if strong enough
        """
        data = self._market_data.get(symbol)
        if data is None:
            logger.debug(f"[{symbol}] No market data available for direction")
            return None

        logger.debug(f"[{symbol}] Market data: RSI={data.rsi_14}, SMA20={data.sma_20}, SMA50={data.sma_50}, Close={data.close}")

        rsi_direction = None
        ma_direction = None

        # Check RSI for momentum signal
        if data.rsi_14 is not None:
            if data.rsi_14 <= self._rsi_oversold:
                rsi_direction = SpreadDirection.BULL  # Oversold = bullish
                logger.debug(f"[{symbol}] RSI {data.rsi_14:.1f} <= {self._rsi_oversold} -> BULLISH")
            elif data.rsi_14 >= self._rsi_overbought:
                rsi_direction = SpreadDirection.BEAR  # Overbought = bearish
                logger.debug(f"[{symbol}] RSI {data.rsi_14:.1f} >= {self._rsi_overbought} -> BEARISH")
            else:
                logger.debug(f"[{symbol}] RSI {data.rsi_14:.1f} in neutral zone ({self._rsi_oversold}-{self._rsi_overbought})")
        else:
            logger.debug(f"[{symbol}] No RSI data available")

        # Check moving average alignment for trend
        if data.sma_20 is not None and data.sma_50 is not None:
            if data.close > data.sma_20 > data.sma_50:
                ma_direction = SpreadDirection.BULL
                logger.debug(f"[{symbol}] MA alignment: Close > SMA20 > SMA50 -> BULLISH")
            elif data.close < data.sma_20 < data.sma_50:
                ma_direction = SpreadDirection.BEAR
                logger.debug(f"[{symbol}] MA alignment: Close < SMA20 < SMA50 -> BEARISH")
            else:
                logger.debug(f"[{symbol}] MA alignment not clear")
        else:
            logger.debug(f"[{symbol}] Missing SMA data (SMA20={data.sma_20}, SMA50={data.sma_50})")

        # Priority: RSI signal takes precedence (short-term momentum)
        if rsi_direction is not None:
            logger.info(f"[{symbol}] Direction: {rsi_direction.value.upper()} (RSI signal)")
            return rsi_direction

        # Fall back to MA direction if no RSI signal
        if ma_direction is not None:
            logger.info(f"[{symbol}] Direction: {ma_direction.value.upper()} (MA signal)")
            return ma_direction

        # No clear direction
        logger.debug(f"[{symbol}] No clear direction signal")
        return None

    def _find_spread_opportunity(
        self, chain: OptionChain, direction: SpreadDirection
    ) -> Optional[OptionSignal]:
        """Find a vertical spread opportunity based on direction."""
        logger.debug(f"[{chain.underlying}] Searching for {direction.value} spread, underlying_price=${chain.underlying_price:.2f}")
        logger.debug(f"[{chain.underlying}] Total contracts in chain: {len(chain.contracts)}")

        # Filter contracts by DTE
        valid_contracts = chain.filter_by_dte(self._min_dte, self._max_dte)
        logger.debug(f"[{chain.underlying}] Contracts after DTE filter ({self._min_dte}-{self._max_dte} days): {len(valid_contracts)}")

        if not valid_contracts:
            logger.warning(f"[{chain.underlying}] No contracts match DTE range {self._min_dte}-{self._max_dte}")
            return None

        # Get unique expirations
        expirations = sorted(set(c.expiration for c in valid_contracts))
        if not expirations:
            logger.warning(f"[{chain.underlying}] No expirations found in valid contracts")
            return None

        logger.debug(f"[{chain.underlying}] Valid expirations: {[exp.date() for exp in expirations]}")

        # Try each expiration
        for i, expiration in enumerate(expirations):
            contracts_at_exp = [
                c for c in valid_contracts if c.expiration == expiration
            ]

            logger.debug(f"[{chain.underlying}] Trying expiration {i+1}/{len(expirations)}: {expiration.date()} ({len(contracts_at_exp)} contracts)")

            # Choose spread type based on direction and credit preference
            if direction == SpreadDirection.BULL:
                if self._prefer_credit:
                    # Bull Put Spread (Credit)
                    logger.debug(f"[{chain.underlying}] Building bull put spread (credit)")
                    signal = self._build_bull_put_spread(
                        contracts_at_exp, chain.underlying, chain.underlying_price
                    )
                else:
                    # Bull Call Spread (Debit)
                    logger.debug(f"[{chain.underlying}] Building bull call spread (debit)")
                    signal = self._build_bull_call_spread(
                        contracts_at_exp, chain.underlying, chain.underlying_price
                    )
            else:  # BEAR
                if self._prefer_credit:
                    # Bear Call Spread (Credit)
                    logger.debug(f"[{chain.underlying}] Building bear call spread (credit)")
                    signal = self._build_bear_call_spread(
                        contracts_at_exp, chain.underlying, chain.underlying_price
                    )
                else:
                    # Bear Put Spread (Debit)
                    logger.debug(f"[{chain.underlying}] Building bear put spread (debit)")
                    signal = self._build_bear_put_spread(
                        contracts_at_exp, chain.underlying, chain.underlying_price
                    )

            if signal is not None:
                logger.info(f"[{chain.underlying}] ✓ Found valid spread signal at expiration {expiration.date()}")
                return signal
            else:
                logger.debug(f"[{chain.underlying}] No valid spread at expiration {expiration.date()}")

        logger.warning(f"[{chain.underlying}] No valid spreads found across {len(expirations)} expirations")
        return None

    def _build_bull_put_spread(
        self,
        contracts: list[OptionContract],
        underlying: str,
        underlying_price: float,
    ) -> Optional[OptionSignal]:
        """Build a bull put spread (sell put spread for credit)."""
        puts = [c for c in contracts if c.option_type == "put"]
        logger.debug(f"  Building bull put spread: {len(puts)} puts available")

        # Get symbol-specific delta target (Phase 1 optimization)
        delta_target = self._get_delta_for_symbol(underlying)

        # Find short put (sell higher strike, OTM)
        logger.debug(f"  Looking for short put (target delta={delta_target:.2f}, below price)")
        short_put = self._find_contract_by_delta(
            puts, delta_target, underlying_price, below_price=True
        )
        if not short_put:
            logger.warning(f"  ✗ No valid short put found for delta {delta_target:.2f}")
            return None

        # Find long put (buy lower strike for protection)
        target_strike = short_put.strike - self._spread_width
        logger.debug(f"  Looking for long put (target strike=${target_strike:.2f})")
        long_put = self._find_contract_by_strike(puts, target_strike)
        if not long_put:
            logger.warning(f"  ✗ No valid long put found at strike ${target_strike:.2f}")
            return None

        # Calculate credit
        credit = (short_put.bid - long_put.ask) * 100
        logger.debug(f"  Credit calculation: ({short_put.bid:.2f} - {long_put.ask:.2f}) * 100 = ${credit:.2f}")

        if credit < self._min_credit:
            logger.warning(f"  ✗ Credit ${credit:.2f} < min ${self._min_credit:.2f}")
            return None

        # Max risk is width minus credit
        spread_width = (short_put.strike - long_put.strike) * 100
        max_risk = spread_width - credit

        # Check minimum return on risk (credit should be ~1/3 of width)
        return_on_risk = credit / spread_width if spread_width > 0 else 0
        logger.debug(f"  Return on risk: ${credit:.2f} / ${spread_width:.2f} = {return_on_risk:.1%}")

        if return_on_risk < self._min_return_on_risk:
            logger.warning(f"  ✗ ROR {return_on_risk:.1%} < min {self._min_return_on_risk:.1%}")
            return None

        logger.info(f"  ✓ Valid bull put spread: short=${short_put.strike}, long=${long_put.strike}, credit=${credit:.2f}, ROR={return_on_risk:.1%}")

        return self._create_signal(
            underlying,
            underlying_price,
            SignalType.SELL_PUT_SPREAD,
            short_put,
            long_put,
            "sell",
            "buy",
            credit,
            max_risk,
            SpreadDirection.BULL,
            is_credit=True,
        )

    def _build_bull_call_spread(
        self,
        contracts: list[OptionContract],
        underlying: str,
        underlying_price: float,
    ) -> Optional[OptionSignal]:
        """Build a bull call spread (buy call spread for debit)."""
        calls = [c for c in contracts if c.option_type == "call"]

        # Find long call (buy lower strike, ATM or slightly OTM)
        long_call = self._find_contract_by_delta(
            calls, 0.50, underlying_price, below_price=False
        )
        if not long_call:
            return None

        # Find short call (sell higher strike)
        target_strike = long_call.strike + self._spread_width
        short_call = self._find_contract_by_strike(calls, target_strike)
        if not short_call:
            return None

        # Calculate debit
        debit = (long_call.ask - short_call.bid) * 100

        # Max profit is width minus debit
        max_profit = (short_call.strike - long_call.strike) * 100 - debit

        return self._create_signal(
            underlying,
            underlying_price,
            SignalType.BUY_CALL_SPREAD,
            short_call,
            long_call,
            "sell",
            "buy",
            max_profit,
            debit,
            SpreadDirection.BULL,
            is_credit=False,
        )

    def _build_bear_call_spread(
        self,
        contracts: list[OptionContract],
        underlying: str,
        underlying_price: float,
    ) -> Optional[OptionSignal]:
        """Build a bear call spread (sell call spread for credit)."""
        calls = [c for c in contracts if c.option_type == "call"]

        # Get symbol-specific delta target (Phase 1 optimization)
        delta_target = self._get_delta_for_symbol(underlying)

        # Find short call (sell lower strike, OTM)
        short_call = self._find_contract_by_delta(
            calls, delta_target, underlying_price, below_price=False
        )
        if not short_call:
            return None

        # Find long call (buy higher strike for protection)
        target_strike = short_call.strike + self._spread_width
        long_call = self._find_contract_by_strike(calls, target_strike)
        if not long_call:
            return None

        # Calculate credit
        credit = (short_call.bid - long_call.ask) * 100
        if credit < self._min_credit:
            return None

        # Max risk is width minus credit
        spread_width = (long_call.strike - short_call.strike) * 100
        max_risk = spread_width - credit

        # Check minimum return on risk (credit should be ~1/3 of width)
        return_on_risk = credit / spread_width if spread_width > 0 else 0
        if return_on_risk < self._min_return_on_risk:
            return None

        return self._create_signal(
            underlying,
            underlying_price,
            SignalType.SELL_CALL_SPREAD,
            short_call,
            long_call,
            "sell",
            "buy",
            credit,
            max_risk,
            SpreadDirection.BEAR,
            is_credit=True,
        )

    def _build_bear_put_spread(
        self,
        contracts: list[OptionContract],
        underlying: str,
        underlying_price: float,
    ) -> Optional[OptionSignal]:
        """Build a bear put spread (buy put spread for debit)."""
        puts = [c for c in contracts if c.option_type == "put"]

        # Find long put (buy higher strike, ATM or slightly OTM)
        long_put = self._find_contract_by_delta(
            puts, 0.50, underlying_price, below_price=True
        )
        if not long_put:
            return None

        # Find short put (sell lower strike)
        target_strike = long_put.strike - self._spread_width
        short_put = self._find_contract_by_strike(puts, target_strike)
        if not short_put:
            return None

        # Calculate debit
        debit = (long_put.ask - short_put.bid) * 100

        # Max profit is width minus debit
        max_profit = (long_put.strike - short_put.strike) * 100 - debit

        return self._create_signal(
            underlying,
            underlying_price,
            SignalType.BUY_PUT_SPREAD,
            short_put,
            long_put,
            "sell",
            "buy",
            max_profit,
            debit,
            SpreadDirection.BEAR,
            is_credit=False,
        )

    def _find_contract_by_delta(
        self,
        contracts: list[OptionContract],
        target_delta: float,
        underlying_price: float,
        below_price: bool,
    ) -> Optional[OptionContract]:
        """Find contract closest to target delta."""
        logger.debug(f"  Finding contract: target_delta={target_delta:.2f}, price=${underlying_price:.2f}, below_price={below_price}")
        logger.debug(f"  Searching {len(contracts)} contracts")

        no_delta_count = 0
        wrong_side_count = 0
        bad_spread_count = 0
        low_oi_count = 0

        candidates = []
        for contract in contracts:
            if contract.delta is None:
                no_delta_count += 1
                continue

            # Filter by price relationship
            if below_price and contract.strike >= underlying_price:
                wrong_side_count += 1
                continue
            if not below_price and contract.strike <= underlying_price:
                wrong_side_count += 1
                continue

            delta_diff = abs(abs(contract.delta) - target_delta)

            # Check liquidity
            if contract.spread_percent > self._max_spread_percent:
                bad_spread_count += 1
                logger.debug(f"    {contract.symbol}: spread {contract.spread_percent:.1f}% > {self._max_spread_percent}% (REJECTED)")
                continue
            if contract.open_interest < self._min_open_interest:
                low_oi_count += 1
                logger.debug(f"    {contract.symbol}: OI {contract.open_interest} < {self._min_open_interest} (REJECTED)")
                continue

            logger.debug(f"    {contract.symbol}: strike=${contract.strike}, delta={contract.delta:.3f}, diff={delta_diff:.3f} (CANDIDATE)")
            candidates.append((contract, delta_diff))

        logger.debug(f"  Filtered: {no_delta_count} no delta, {wrong_side_count} wrong side, {bad_spread_count} wide spread, {low_oi_count} low OI")
        logger.debug(f"  Found {len(candidates)} candidates")

        if not candidates:
            logger.warning(f"  No valid contracts found for delta {target_delta:.2f}")
            return None

        candidates.sort(key=lambda x: x[1])
        best = candidates[0][0]
        logger.debug(f"  ✓ Selected: {best.symbol} (strike=${best.strike}, delta={best.delta:.3f})")
        return best

    def _find_contract_by_strike(
        self, contracts: list[OptionContract], target_strike: float
    ) -> Optional[OptionContract]:
        """Find contract closest to target strike."""
        candidates = []
        for contract in contracts:
            strike_diff = abs(contract.strike - target_strike)

            # More lenient liquidity for protection legs
            if contract.spread_percent > self._max_spread_percent * 2:
                continue
            if contract.open_interest < self._min_open_interest // 2:
                continue

            candidates.append((contract, strike_diff))

        if not candidates:
            return None

        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    def _create_signal(
        self,
        underlying: str,
        underlying_price: float,
        signal_type: SignalType,
        short_contract: OptionContract,
        long_contract: OptionContract,
        short_side: str,
        long_side: str,
        potential_profit: float,
        risk_or_cost: float,
        direction: SpreadDirection,
        is_credit: bool,
    ) -> OptionSignal:
        """Create the option signal for the spread."""
        legs = [
            OptionLeg(
                contract_symbol=short_contract.symbol,
                underlying=underlying,
                option_type=short_contract.option_type,
                strike=short_contract.strike,
                expiration=short_contract.expiration,
                side=short_side,
                quantity=1,
                limit_price=short_contract.bid if short_side == "sell" else short_contract.ask,
            ),
            OptionLeg(
                contract_symbol=long_contract.symbol,
                underlying=underlying,
                option_type=long_contract.option_type,
                strike=long_contract.strike,
                expiration=long_contract.expiration,
                side=long_side,
                quantity=1,
                limit_price=long_contract.ask if long_side == "buy" else long_contract.bid,
            ),
        ]

        # Calculate confidence
        confidence = self._calculate_confidence(
            short_contract, long_contract, potential_profit, risk_or_cost, is_credit
        )

        # Calculate management levels for credit spreads
        spread_width_dollars = abs(short_contract.strike - long_contract.strike) * 100

        if is_credit:
            # For credit spreads:
            # Profit target: close when we've captured X% of credit
            profit_target = potential_profit * self._profit_target_pct
            # Stop loss: close when loss reaches X times the credit
            stop_loss = potential_profit * self._stop_loss_multiplier
        else:
            # For debit spreads, we don't use these management rules
            profit_target = None
            stop_loss = None

        return OptionSignal(
            signal_type=signal_type,
            underlying=underlying,
            legs=legs,
            confidence=confidence,
            strategy_name=self.name,
            metadata={
                "direction": direction.value,
                "is_credit_spread": is_credit,
                "potential_profit": potential_profit,
                "max_risk" if is_credit else "cost": risk_or_cost,
                "short_strike": short_contract.strike,
                "long_strike": long_contract.strike,
                "short_delta": short_contract.delta,
                "long_delta": long_contract.delta,
                "dte": short_contract.days_to_expiry,
                "close_dte": self._close_dte,  # When to close due to DTE
                "underlying_price": underlying_price,
                "spread_width": abs(short_contract.strike - long_contract.strike),
                "spread_width_dollars": spread_width_dollars,
                "return_on_risk": (potential_profit / risk_or_cost) * 100 if risk_or_cost > 0 else 0,
                # Management parameters for backtest engine
                "profit_target": profit_target,  # Close when profit reaches this
                "stop_loss": stop_loss,  # Close when loss reaches this
                "profit_target_pct": self._profit_target_pct,
                "stop_loss_multiplier": self._stop_loss_multiplier,
            },
        )

    def _calculate_confidence(
        self,
        short_contract: OptionContract,
        long_contract: OptionContract,
        potential_profit: float,
        risk_or_cost: float,
        is_credit: bool,
    ) -> float:
        """Calculate signal confidence based on trade quality."""
        confidence = 0.5  # Base confidence

        # Better risk/reward improves confidence
        if risk_or_cost > 0:
            ror = potential_profit / risk_or_cost
            if ror >= 0.50:
                confidence += 0.15
            elif ror >= 0.33:
                confidence += 0.10

        # Tighter spreads improve confidence
        avg_spread = (short_contract.spread_percent + long_contract.spread_percent) / 2
        if avg_spread < 1.5:
            confidence += 0.10
        elif avg_spread < 2.5:
            confidence += 0.05

        # Good open interest improves confidence
        min_oi = min(short_contract.open_interest, long_contract.open_interest)
        if min_oi >= 1000:
            confidence += 0.10
        elif min_oi >= 500:
            confidence += 0.05

        # Credit spreads get slight boost (theta decay in our favor)
        if is_credit:
            confidence += 0.05

        return min(confidence, 0.85)

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
