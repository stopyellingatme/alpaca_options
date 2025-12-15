"""Backtesting engine for historical strategy simulation.

This module provides:
- Historical data simulation
- Strategy execution simulation
- Slippage and commission modeling
- Performance metrics calculation
- Trade logging and analysis
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from alpaca_options.core.config import BacktestConfig, RiskConfig, TradingConfig
from alpaca_options.risk.manager import RiskManager
from alpaca_options.strategies.base import (
    BaseStrategy,
    MarketData,
    OptionChain,
    OptionContract,
    OptionLeg,
    OptionSignal,
    SignalType,
)

# Phase 2A: Execution realism models
from alpaca_options.backtesting.execution_model import (
    FillProbabilityModel,
    FillContext,
    GapRiskModel,
)

logger = logging.getLogger(__name__)


class TradeStatus(Enum):
    """Status of a backtested trade."""

    OPEN = "open"
    CLOSED = "closed"
    EXPIRED = "expired"
    ASSIGNED = "assigned"


@dataclass
class BacktestTrade:
    """Represents a trade in the backtest."""

    trade_id: str
    signal_type: SignalType
    underlying: str
    legs: list[OptionLeg]
    entry_time: datetime
    entry_prices: dict[str, float]  # contract_symbol -> price
    exit_time: Optional[datetime] = None
    exit_prices: Optional[dict[str, float]] = None
    status: TradeStatus = TradeStatus.OPEN
    pnl: float = 0.0
    commissions: float = 0.0
    slippage: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.status == TradeStatus.OPEN

    @property
    def net_pnl(self) -> float:
        """P&L after commissions and slippage."""
        return self.pnl - self.commissions - self.slippage

    @property
    def holding_period_days(self) -> Optional[int]:
        """Days between entry and exit."""
        if self.exit_time is None:
            return None
        return (self.exit_time - self.entry_time).days


@dataclass
class BacktestMetrics:
    """Performance metrics from a backtest."""

    total_return: float
    total_return_percent: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_percent: float
    win_rate: float
    profit_factor: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    avg_win: float
    avg_loss: float
    avg_trade_pnl: float
    avg_holding_period_days: float
    total_commissions: float
    total_slippage: float
    starting_equity: float
    ending_equity: float
    peak_equity: float
    # Phase 2A: Execution realism metrics
    fill_rejections: int = 0
    gap_events: int = 0
    fill_rejection_rate: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "total_return": self.total_return,
            "total_return_percent": self.total_return_percent,
            "annualized_return": self.annualized_return,
            "sharpe_ratio": self.sharpe_ratio,
            "sortino_ratio": self.sortino_ratio,
            "max_drawdown": self.max_drawdown,
            "max_drawdown_percent": self.max_drawdown_percent,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "avg_win": self.avg_win,
            "avg_loss": self.avg_loss,
            "avg_trade_pnl": self.avg_trade_pnl,
            "avg_holding_period_days": self.avg_holding_period_days,
            "total_commissions": self.total_commissions,
            "total_slippage": self.total_slippage,
            "starting_equity": self.starting_equity,
            "ending_equity": self.ending_equity,
            "peak_equity": self.peak_equity,
            # Phase 2A metrics
            "fill_rejections": self.fill_rejections,
            "gap_events": self.gap_events,
            "fill_rejection_rate": self.fill_rejection_rate,
        }


@dataclass
class BacktestResult:
    """Complete result of a backtest run."""

    strategy_name: str
    start_date: datetime
    end_date: datetime
    metrics: BacktestMetrics
    trades: list[BacktestTrade]
    equity_curve: pd.DataFrame
    daily_returns: pd.Series
    config: dict[str, Any] = field(default_factory=dict)

    def save(self, path: Path) -> None:
        """Save backtest results to files."""
        path.mkdir(parents=True, exist_ok=True)

        # Save equity curve
        self.equity_curve.to_csv(path / "equity_curve.csv", index=True)

        # Save daily returns
        self.daily_returns.to_csv(path / "daily_returns.csv", header=True)

        # Save trades
        trades_data = [
            {
                "trade_id": t.trade_id,
                "signal_type": t.signal_type.value,
                "underlying": t.underlying,
                "entry_time": t.entry_time.isoformat(),
                "exit_time": t.exit_time.isoformat() if t.exit_time else None,
                "status": t.status.value,
                "pnl": t.pnl,
                "commissions": t.commissions,
                "slippage": t.slippage,
                "net_pnl": t.net_pnl,
                "holding_days": t.holding_period_days,
            }
            for t in self.trades
        ]
        pd.DataFrame(trades_data).to_csv(path / "trades.csv", index=False)

        # Save metrics summary
        with open(path / "metrics.txt", "w") as f:
            f.write(f"Backtest Results: {self.strategy_name}\n")
            f.write(f"Period: {self.start_date.date()} to {self.end_date.date()}\n")
            f.write("=" * 50 + "\n\n")

            for key, value in self.metrics.to_dict().items():
                if isinstance(value, float):
                    f.write(f"{key}: {value:.4f}\n")
                else:
                    f.write(f"{key}: {value}\n")


class SlippageModel:
    """Models realistic slippage for backtesting.

    Supported models:
    - "adaptive": Real market data-based slippage (RECOMMENDED - Phase 1 improvement)
        * Uses real Alpaca options data analysis from Oct 2024
        * Adjusts for delta (moneyness): 20-delta OTM ~3.89%, ATM ~2.97%, Deep ITM ~7.52%
        * Adjusts for DTE: wider spreads close to expiration
        * Most realistic model based on actual market conditions
    - "orats": ORATS research-based slippage (recommended for options)
        * 75% of bid-ask spread for single-leg positions
        * 65% of bid-ask spread for two-leg spreads (verticals, debits, credits)
        * 56% of bid-ask spread for four-leg spreads (iron condors)
    - "realistic": Complex model incorporating spread, volatility, size, and noise
    - "percentage": Fixed percentage of notional value
    - "fixed": Fixed dollar amount per contract
    - "volatility": Percentage scaled by implied volatility
    """

    def __init__(
        self,
        model_type: str = "realistic",
        value: float = 0.001,
    ) -> None:
        self._model_type = model_type
        self._value = value

    def calculate(
        self,
        price: float,
        quantity: int,
        is_buy: bool,
        volatility: Optional[float] = None,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        num_legs: Optional[int] = None,
        delta: Optional[float] = None,
        dte: Optional[int] = None,
    ) -> float:
        """Calculate slippage for an order.

        Args:
            price: Order price (mid price).
            quantity: Number of contracts.
            is_buy: True if buying, False if selling.
            volatility: Optional implied volatility.
            bid: Bid price for spread-based calculation.
            ask: Ask price for spread-based calculation.
            num_legs: Number of legs in the strategy (for ORATS model).
            delta: Option delta for adaptive model (optional).
            dte: Days to expiry for adaptive model (optional).

        Returns:
            Slippage amount (always positive, represents cost).
        """
        if self._model_type == "adaptive":
            # Adaptive slippage based on real Alpaca market data analysis (Oct 2024)
            # Data showed: 20-delta OTM ~3.89%, ATM ~2.97%, Deep ITM ~7.52%

            # Use delta to determine moneyness and base spread percentage
            abs_delta = abs(delta) if delta is not None else 0.20  # Default to 20-delta

            # Base spread percentage from real market data
            if abs_delta < 0.05:  # Way OTM
                base_spread_pct = 0.0705  # 7.05% (from analysis)
            elif abs_delta < 0.15:  # 10-delta OTM
                base_spread_pct = 0.0550  # 5.50% (from analysis)
            elif abs_delta < 0.25:  # 20-delta OTM (our target range)
                base_spread_pct = 0.0389  # 3.89% (from analysis)
            elif abs_delta < 0.40:  # Approaching ATM
                base_spread_pct = 0.0356  # 3.56% (ITM from analysis)
            elif abs_delta < 0.60:  # ATM
                base_spread_pct = 0.0297  # 2.97% (from analysis)
            elif abs_delta < 0.75:  # ITM
                base_spread_pct = 0.0356  # 3.56% (from analysis)
            else:  # Deep ITM (delta > 0.75)
                base_spread_pct = 0.0752  # 7.52% (from analysis)

            # Adjust for DTE - spreads widen close to expiration
            dte_multiplier = 1.0
            if dte is not None:
                if dte < 7:
                    dte_multiplier = 1.2  # 20% wider spreads in last week
                elif dte < 14:
                    dte_multiplier = 1.1  # 10% wider in last 2 weeks

            # Calculate slippage as percentage of price
            slippage_per_contract = price * base_spread_pct * dte_multiplier
            return abs(slippage_per_contract * quantity * 100)

        elif self._model_type == "orats" and bid is not None and ask is not None:
            # ORATS slippage methodology based on strategy complexity
            # Research shows slippage decreases with more legs (better pricing)
            spread = ask - bid

            # Determine slippage percentage based on leg count
            if num_legs == 1:
                slippage_pct = 0.75  # 75% of spread for single legs
            elif num_legs == 2:
                slippage_pct = 0.65  # 65% of spread for two-leg spreads
            elif num_legs == 4:
                slippage_pct = 0.56  # 56% of spread for iron condors
            else:
                slippage_pct = 0.65  # Default to two-leg percentage

            slippage_per_contract = spread * slippage_pct
            return abs(slippage_per_contract * quantity * 100)

        elif self._model_type == "realistic" and bid is not None and ask is not None:
            # Realistic model: you cross a portion of the spread + additional slippage
            spread = ask - bid
            mid = (bid + ask) / 2

            # Base: you pay ~60-80% of the half-spread (market orders cross the spread)
            # Limit orders might get better fills but have execution risk
            spread_crossing = spread * 0.35  # Pay 35% of full spread (70% of half)

            # Volatility factor: higher IV = more slippage
            vol_factor = 1.0
            if volatility is not None and volatility > 0:
                # Slippage increases with IV above 25%
                vol_factor = 1.0 + max(0, (volatility - 0.25)) * 1.5

            # Size impact: larger orders move the market
            size_factor = 1.0 + (quantity - 1) * 0.05  # 5% more slippage per additional contract

            # Random component to simulate market microstructure noise
            import random
            noise_factor = 0.9 + random.random() * 0.3  # 0.9 to 1.2

            slippage_per_contract = spread_crossing * vol_factor * size_factor * noise_factor
            return abs(slippage_per_contract * quantity * 100)

        elif self._model_type == "percentage":
            return abs(price * quantity * 100 * self._value)

        elif self._model_type == "fixed":
            return self._value * quantity

        elif self._model_type == "volatility" and volatility is not None:
            vol_factor = min(volatility / 0.30, 2.0)
            return abs(price * quantity * 100 * self._value * vol_factor)

        return abs(price * quantity * 100 * self._value)


class BacktestEngine:
    """Engine for backtesting options trading strategies.

    Simulates strategy execution on historical data with:
    - Realistic slippage and commission modeling
    - Risk management integration
    - Position limits and buying power tracking
    - Performance metrics calculation
    """

    def __init__(
        self,
        config: BacktestConfig,
        risk_config: RiskConfig,
        trading_config: Optional[TradingConfig] = None,
    ) -> None:
        self._config = config
        self._risk_manager = RiskManager(risk_config)
        self._trading_config = trading_config or TradingConfig()
        self._slippage_model = SlippageModel(
            model_type=config.execution.slippage_model,
            value=config.execution.slippage_value,
        )
        self._commission_per_contract = config.execution.commission_per_contract

        # Phase 2A: Initialize execution realism models
        # Fill probability model (enabled/disabled via config)
        self._enable_fill_probability = getattr(config.execution, 'enable_fill_probability', False)
        if self._enable_fill_probability:
            self._fill_model = FillProbabilityModel(
                min_oi_threshold=getattr(config.execution, 'min_oi_threshold', 100),
                max_spread_threshold=getattr(config.execution, 'max_spread_threshold', 0.10),
                illiquid_hour_multiplier=getattr(config.execution, 'illiquid_hour_multiplier', 0.85),
                high_vix_multiplier=getattr(config.execution, 'high_vix_multiplier', 0.90),
            )
            self._fill_rejections = 0  # Track rejections
            logger.info("Phase 2A: Fill Probability Model enabled")
        else:
            self._fill_model = None
            self._fill_rejections = 0

        # Gap risk model (enabled/disabled via config)
        self._enable_gap_risk = getattr(config.execution, 'enable_gap_risk', False)
        if self._enable_gap_risk:
            self._gap_model = GapRiskModel(
                avg_overnight_gap_pct=getattr(config.execution, 'avg_overnight_gap', 0.005),
                weekend_multiplier=getattr(config.execution, 'weekend_gap_multiplier', 1.6),
                earnings_multiplier=getattr(config.execution, 'earnings_gap_multiplier', 3.0),
                stop_loss_slippage_pct=getattr(config.execution, 'gap_stop_loss_slippage', 0.02),
            )
            self._gap_events = 0  # Track gap events
            logger.info("Phase 2A: Gap Risk Model enabled")
        else:
            self._gap_model = None
            self._gap_events = 0

        # Early assignment and gap risk parameters (for _process_positions)
        self._early_assignment_threshold = 0.80  # 80 delta = deep ITM with assignment risk
        self._gap_risk_probability = getattr(config.execution, 'gap_risk_probability', 0.015)
        self._gap_severity_min = getattr(config.execution, 'gap_severity_min', 0.3)
        self._gap_severity_max = getattr(config.execution, 'gap_severity_max', 0.7)

        # Backtest state
        self._equity: float = config.initial_capital
        self._starting_equity: float = config.initial_capital
        self._peak_equity: float = config.initial_capital
        self._cash: float = config.initial_capital
        self._buying_power: float = config.initial_capital  # Track available buying power
        self._collateral_in_use: float = 0.0  # Track collateral tied up in positions
        self._trades: list[BacktestTrade] = []
        self._open_positions: dict[str, BacktestTrade] = {}
        self._trade_counter: int = 0
        self._equity_history: list[tuple[datetime, float]] = []
        self._daily_pnl: list[float] = []

    def _initialize_backtest(
        self,
        strategy: BaseStrategy,
        options_data: dict[datetime, OptionChain],
        start_date: Optional[datetime],
        end_date: Optional[datetime],
    ) -> tuple[datetime, datetime, list[datetime]]:
        """Initialize backtest state and prepare timestamps.

        Args:
            strategy: The strategy to backtest.
            options_data: Dict mapping datetime to OptionChain snapshots.
            start_date: Optional start date override.
            end_date: Optional end date override.

        Returns:
            Tuple of (start, end, timestamps) for the backtest period.

        Raises:
            ValueError: If no options data available in date range.
        """
        # Reset state
        self._reset()

        # Parse dates with defaults
        start = start_date or datetime.fromisoformat(self._config.default_start_date)
        end = end_date or datetime.fromisoformat(self._config.default_end_date)

        logger.info(
            f"Starting backtest for {strategy.name} from {start.date()} to {end.date()}"
        )

        # Get timestamps to iterate
        timestamps = sorted(
            [ts for ts in options_data.keys() if start <= ts <= end]
        )

        if not timestamps:
            raise ValueError("No options data available in date range")

        return start, end, timestamps

    async def _process_timestamp(
        self,
        i: int,
        timestamp: datetime,
        timestamps: list[datetime],
        strategy: BaseStrategy,
        underlying_data: pd.DataFrame,
        options_data: dict[datetime, OptionChain],
        last_date: Optional[date],
    ) -> Optional[date]:
        """Process a single timestamp in the backtest simulation.

        Args:
            i: Current index in timestamps list.
            timestamp: Current timestamp to process.
            timestamps: Full list of timestamps.
            strategy: Strategy instance.
            underlying_data: Historical underlying price data.
            options_data: Historical options chain data.
            last_date: Previous day's date for tracking daily P&L.

        Returns:
            Current date for tracking daily P&L transitions.
        """
        # Get options chain first (to get the symbol)
        chain = options_data.get(timestamp)
        if chain is None:
            return last_date

        # Get market data for this timestamp, using chain's underlying symbol
        market_data = self._get_market_data(
            underlying_data, timestamp, symbol=chain.underlying
        )

        # Update chain's underlying price with actual market price
        # (DoltHub doesn't provide this, so we populate it from underlying_data)
        if market_data and market_data.close > 0:
            chain.underlying_price = market_data.close

        # Update risk manager
        self._risk_manager.update_account(
            equity=self._equity,
            buying_power=self._cash,
            daily_pnl=self._get_daily_pnl(timestamp),
        )

        # === PHASE 2A: GAP RISK MONITORING ===
        # Check if we're crossing a market close/open boundary (overnight or weekend gap)
        if self._enable_gap_risk and self._gap_model and i < len(timestamps) - 1:
            next_timestamp = timestamps[i + 1]
            if self._gap_model.should_check_gap_risk(timestamp, next_timestamp):
                await self._process_gap_risk(timestamp, next_timestamp, chain)

        # Process existing positions (check for expiration, assignment)
        await self._process_positions(timestamp, chain)

        # Pass market data to strategy first (some strategies need this for indicators)
        if market_data:
            await strategy.on_market_data(market_data)

        # Get strategy signal
        signal = await strategy.on_option_chain(chain)

        if signal is not None:
            logger.info(
                f"Signal received: {signal.signal_type.value} on {signal.underlying} "
                f"with {len(signal.legs)} legs"
            )

            # Check max concurrent positions limit FIRST
            open_position_count = len(self._open_positions)
            max_concurrent = self._trading_config.max_concurrent_positions

            if open_position_count >= max_concurrent:
                logger.info(
                    f"Signal rejected: at max concurrent positions "
                    f"({open_position_count}/{max_concurrent})"
                )
            else:
                # Build contract map for risk check
                contracts = self._build_contract_map(signal, chain)
                logger.debug(f"Contract map size: {len(contracts)} (expected {len(signal.legs)})")
                logger.debug(f"Contract symbols: {list(contracts.keys())}")

                # Calculate required buying power for this trade
                trade_risk = self._risk_manager._calculate_trade_risk(signal, contracts)
                min_reserve = self._equity * self._trading_config.min_buying_power_reserve
                available_bp = self._buying_power - min_reserve

                if trade_risk > available_bp:
                    logger.info(
                        f"Signal rejected: insufficient buying power "
                        f"(need ${trade_risk:.2f}, have ${available_bp:.2f})"
                    )
                else:
                    # Check risk manager rules
                    risk_check = self._risk_manager.check_signal_risk(signal, contracts)
                    logger.debug(f"Risk check result: {risk_check.result}, passed={risk_check.passed}, violations={len(risk_check.violations)}, warnings={len(risk_check.warnings)}")

                    # Accept both PASSED and WARNING (warnings are informational, not blocking)
                    if risk_check.passed or risk_check.has_warnings:
                        # Log warnings if present
                        if risk_check.has_warnings:
                            logger.info(f"Trade accepted with {len(risk_check.warnings)} warnings")

                        # Reserve buying power for this trade
                        self._buying_power -= trade_risk
                        self._collateral_in_use += trade_risk
                        logger.info(f"Executing trade with risk ${trade_risk:.2f}")
                        await self._execute_signal(signal, chain, timestamp, trade_risk)
                    else:
                        logger.info(
                            f"Signal rejected by risk manager: {risk_check.violations}"
                        )

        # Record equity
        current_equity = self._calculate_equity(chain)
        self._equity = current_equity
        self._peak_equity = max(self._peak_equity, current_equity)
        self._equity_history.append((timestamp, current_equity))

        # Track daily P&L
        current_date = timestamp.date()
        if last_date is not None and current_date != last_date:
            daily_pnl = self._calculate_daily_pnl(current_date)
            self._daily_pnl.append(daily_pnl)

        return current_date

    async def _finalize_backtest(
        self,
        strategy: BaseStrategy,
        start: datetime,
        end: datetime,
        timestamps: list[datetime],
        options_data: dict[datetime, OptionChain],
    ) -> BacktestResult:
        """Finalize backtest and generate results.

        Args:
            strategy: The strategy instance.
            start: Backtest start date.
            end: Backtest end date.
            timestamps: List of timestamps processed.
            options_data: Historical options chain data.

        Returns:
            BacktestResult with metrics, trades, and performance data.
        """
        # Close any remaining positions at end
        await self._close_all_positions(timestamps[-1], options_data.get(timestamps[-1]))

        # Calculate metrics
        metrics = self._calculate_metrics(start, end)

        # Build equity curve DataFrame
        equity_curve = pd.DataFrame(
            self._equity_history,
            columns=["timestamp", "equity"],
        ).set_index("timestamp")

        # Build daily returns series
        daily_returns = pd.Series(self._daily_pnl)

        return BacktestResult(
            strategy_name=strategy.name,
            start_date=start,
            end_date=end,
            metrics=metrics,
            trades=self._trades,
            equity_curve=equity_curve,
            daily_returns=daily_returns,
            config=self._config.model_dump(),
        )

    async def run(
        self,
        strategy: BaseStrategy,
        underlying_data: pd.DataFrame,
        options_data: dict[datetime, OptionChain],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> BacktestResult:
        """Run a backtest for a strategy.

        Args:
            strategy: The strategy to backtest.
            underlying_data: DataFrame with OHLCV data indexed by datetime.
            options_data: Dict mapping datetime to OptionChain snapshots.
            start_date: Optional start date override.
            end_date: Optional end date override.

        Returns:
            BacktestResult with metrics and trade history.
        """
        # Initialize backtest state
        start, end, timestamps = self._initialize_backtest(
            strategy, options_data, start_date, end_date
        )

        # Initialize strategy if needed
        if not strategy.is_initialized:
            await strategy.initialize(strategy.config)

        last_date = None

        # Run simulation for each timestamp
        for i, timestamp in enumerate(timestamps):
            last_date = await self._process_timestamp(
                i=i,
                timestamp=timestamp,
                timestamps=timestamps,
                strategy=strategy,
                underlying_data=underlying_data,
                options_data=options_data,
                last_date=last_date,
            )

        # Finalize and generate results
        return await self._finalize_backtest(strategy, start, end, timestamps, options_data)

    def _reset(self) -> None:
        """Reset backtest state."""
        self._equity = self._config.initial_capital
        self._starting_equity = self._config.initial_capital
        self._peak_equity = self._config.initial_capital
        self._cash = self._config.initial_capital
        self._buying_power = self._config.initial_capital
        self._collateral_in_use = 0.0
        self._trades = []
        self._open_positions = {}
        self._trade_counter = 0
        self._equity_history = []
        self._daily_pnl = []
        # Phase 2A: Reset execution realism counters
        self._fill_rejections = 0
        self._gap_events = 0

    def _get_market_data(
        self, underlying_data: pd.DataFrame, timestamp: datetime, symbol: str = ""
    ) -> Optional[MarketData]:
        """Get market data for a timestamp."""
        try:
            # Find closest row at or before timestamp
            idx = underlying_data.index.get_indexer([timestamp], method="ffill")[0]
            if idx < 0:
                return None

            row = underlying_data.iloc[idx]

            # Helper to get float value, returning None for NaN
            def safe_float(col: str) -> Optional[float]:
                if col not in row:
                    return None
                val = row[col]
                if pd.isna(val):
                    return None
                return float(val)

            # Use provided symbol, fall back to row data, then empty string
            market_symbol = symbol or str(row.get("symbol", ""))

            return MarketData(
                symbol=market_symbol,
                timestamp=timestamp,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row.get("volume", 0)),
                vwap=safe_float("vwap"),
                sma_20=safe_float("sma_20"),
                sma_50=safe_float("sma_50"),
                rsi_14=safe_float("rsi_14"),
                iv_rank=safe_float("iv_rank"),
            )
        except Exception as e:
            logger.debug(f"Error getting market data: {e}")
            return None

    def _build_contract_map(
        self, signal: OptionSignal, chain: OptionChain
    ) -> dict[str, OptionContract]:
        """Build map of contract symbols to contracts."""
        contracts = {}
        for leg in signal.legs:
            for contract in chain.contracts:
                if contract.symbol == leg.contract_symbol:
                    contracts[leg.contract_symbol] = contract
                    break
        return contracts

    def _check_order_fillability(
        self,
        signal: OptionSignal,
        chain: OptionChain,
        timestamp: datetime,
        collateral_required: float,
    ) -> bool:
        """Check if order will fill based on liquidity and market conditions.

        Uses either sophisticated fill probability model (Phase 2A) or legacy
        basic liquidity checks depending on configuration.

        Args:
            signal: The option signal to execute.
            chain: Current options chain.
            timestamp: Current timestamp.
            collateral_required: Collateral reserved for this order.

        Returns:
            True if order should fill, False if it should be rejected.
        """
        # === PHASE 2A: FILL PROBABILITY CHECK ===
        if self._enable_fill_probability and self._fill_model:
            # Get VIX for fill context (default to 20 if not available)
            vix = 20.0  # TODO: Load actual VIX data from market data

            for leg in signal.legs:
                contract = None
                for c in chain.contracts:
                    if c.symbol == leg.contract_symbol:
                        contract = c
                        break

                if contract is None:
                    logger.debug(f"Order rejected: contract {leg.contract_symbol} not found")
                    self._buying_power += collateral_required
                    self._collateral_in_use -= collateral_required
                    return False

                # Calculate bid-ask spread percentage
                if contract.bid > 0 and contract.ask > 0 and contract.mid_price > 0:
                    spread_pct = (contract.ask - contract.bid) / contract.mid_price
                else:
                    spread_pct = 0.20  # Assume wide spread if no data

                # Create fill context for this leg
                fill_context = FillContext(
                    open_interest=contract.open_interest,
                    bid_ask_spread_pct=spread_pct,
                    timestamp=timestamp,
                    vix=vix,
                    order_size=leg.quantity,
                    avg_daily_volume=contract.volume if contract.volume else 1000,
                    option_type=contract.option_type,
                    is_opening=True,  # This is an opening trade
                )

                # Check if order will fill
                if not self._fill_model.will_fill(fill_context):
                    logger.info(
                        f"Order rejected: low fill probability on {leg.contract_symbol} "
                        f"(OI={contract.open_interest}, Spread={spread_pct:.2%})"
                    )
                    self._fill_rejections += 1
                    self._buying_power += collateral_required
                    self._collateral_in_use -= collateral_required
                    return False

            return True

        # === LEGACY: BASIC LIQUIDITY CHECKS ===
        elif not self._enable_fill_probability:
            import random
            for leg in signal.legs:
                contract = None
                for c in chain.contracts:
                    if c.symbol == leg.contract_symbol:
                        contract = c
                        break

                if contract is None:
                    logger.debug(f"Order rejected: contract {leg.contract_symbol} not found")
                    self._buying_power += collateral_required
                    self._collateral_in_use -= collateral_required
                    return False

                # Legacy: Check liquidity - reject if spread is too wide
                if contract.bid > 0 and contract.ask > 0:
                    spread_pct = (contract.ask - contract.bid) / contract.mid_price
                    if spread_pct > 0.20:  # >20% spread = illiquid
                        if random.random() < 0.5:
                            logger.debug(f"Order rejected: spread too wide ({spread_pct:.1%})")
                            self._buying_power += collateral_required
                            self._collateral_in_use -= collateral_required
                            return False

                # Legacy: Check open interest - reject if too low
                if contract.open_interest < 50:
                    if random.random() < 0.3:
                        logger.debug(f"Order rejected: low OI ({contract.open_interest})")
                        self._buying_power += collateral_required
                        self._collateral_in_use -= collateral_required
                        return False

            return True

        # If neither path is taken, allow fill
        return True

    def _execute_and_record_trade(
        self,
        signal: OptionSignal,
        chain: OptionChain,
        timestamp: datetime,
        collateral_required: float,
    ) -> None:
        """Execute trade with slippage/commission and create trade record.

        Args:
            signal: The option signal to execute.
            chain: Current options chain.
            timestamp: Execution timestamp.
            collateral_required: Collateral reserved for this trade.
        """
        self._trade_counter += 1
        trade_id = f"BT-{self._trade_counter:06d}"

        entry_prices = {}
        total_premium = 0.0
        total_commission = 0.0
        total_slippage = 0.0

        for leg in signal.legs:
            # Find contract in chain
            contract = None
            for c in chain.contracts:
                if c.symbol == leg.contract_symbol:
                    contract = c
                    break

            if contract is None:
                logger.warning(f"Contract not found: {leg.contract_symbol}")
                # Release the buying power we reserved
                self._buying_power += collateral_required
                self._collateral_in_use -= collateral_required
                return

            # Determine execution price with slippage
            is_buy = leg.side == "buy"
            base_price = contract.ask if is_buy else contract.bid

            slippage = self._slippage_model.calculate(
                price=base_price,
                quantity=leg.quantity,
                is_buy=is_buy,
                volatility=contract.implied_volatility,
                bid=contract.bid,
                ask=contract.ask,
                num_legs=len(signal.legs),  # Pass number of legs for ORATS model
                delta=contract.delta,  # For adaptive model
                dte=contract.days_to_expiry,  # For adaptive model
            )

            # Adjust price for slippage (worse for us)
            # Buy orders: pay more (add slippage)
            # Sell orders: receive less (subtract slippage)
            slippage_per_contract = slippage / (leg.quantity * 100)
            if is_buy:
                exec_price = base_price + slippage_per_contract
            else:
                exec_price = base_price - slippage_per_contract
            entry_prices[leg.contract_symbol] = exec_price

            # Calculate premium
            premium = exec_price * leg.quantity * 100
            if is_buy:
                total_premium -= premium  # Debit
            else:
                total_premium += premium  # Credit

            # Commission
            commission = self._commission_per_contract * leg.quantity
            total_commission += commission
            total_slippage += slippage

        # Update cash
        self._cash += total_premium - total_commission

        # Create trade record with collateral info
        metadata = signal.metadata.copy()
        metadata["collateral_required"] = collateral_required

        trade = BacktestTrade(
            trade_id=trade_id,
            signal_type=signal.signal_type,
            underlying=signal.underlying,
            legs=signal.legs.copy(),
            entry_time=timestamp,
            entry_prices=entry_prices,
            commissions=total_commission,
            slippage=total_slippage,
            metadata=metadata,
        )

        self._trades.append(trade)
        self._open_positions[trade_id] = trade

        logger.debug(
            f"Executed {signal.signal_type.value} on {signal.underlying}: "
            f"premium=${total_premium:.2f}, commission=${total_commission:.2f}, "
            f"collateral=${collateral_required:.2f}"
        )

    async def _execute_signal(
        self,
        signal: OptionSignal,
        chain: OptionChain,
        timestamp: datetime,
        collateral_required: float = 0.0,
    ) -> None:
        """Execute a trading signal with realistic fill simulation.

        Includes:
        - Liquidity check (reject if spread too wide or OI too low)
        - Fill probability based on market conditions
        - Partial rejection (order not filled)
        """
        # Check if order will fill (liquidity and market conditions)
        if not self._check_order_fillability(signal, chain, timestamp, collateral_required):
            return

        # Execute trade with slippage/commission and record
        self._execute_and_record_trade(signal, chain, timestamp, collateral_required)

    async def _process_gap_risk(
        self,
        current_time: datetime,
        next_bar_time: datetime,
        chain: OptionChain,
    ) -> None:
        """Process gap risk for open positions crossing market close/open boundaries.

        When the market is closed (overnight, weekend), positions can gap against us,
        and stop losses cannot be executed. This models the additional slippage
        that occurs when a position moves significantly during market close.
        """
        if not self._open_positions:
            return

        # Get underlying volatility (default to 20% if not available)
        underlying_iv = 0.20  # TODO: Load actual IV from market data

        for trade_id, trade in list(self._open_positions.items()):
            # Calculate current P&L for this position
            current_pnl = 0.0
            position_notional = 0.0

            for leg in trade.legs:
                contract = None
                for c in chain.contracts:
                    if c.symbol == leg.contract_symbol:
                        contract = c
                        break

                if contract:
                    entry_price = trade.entry_prices.get(leg.contract_symbol, 0)
                    current_price = contract.mid_price
                    position_notional += current_price * leg.quantity * 100

                    if leg.side == "sell":
                        # Sold option: profit if current price < entry
                        current_pnl += (entry_price - current_price) * leg.quantity * 100
                    else:
                        # Bought option: profit if current price > entry
                        current_pnl += (current_price - entry_price) * leg.quantity * 100

            # Calculate P&L as percentage of initial credit/debit
            # For credit spreads, initial credit is the premium we collected
            # P&L % = current_pnl / initial_credit
            # If we're losing more than 100% of credit (2x credit stop loss), model gap slippage
            initial_value = sum(
                trade.entry_prices.get(leg.contract_symbol, 0) * leg.quantity * 100
                for leg in trade.legs
                if leg.side == "sell"
            )
            if initial_value == 0:
                initial_value = 1  # Avoid division by zero

            pnl_pct = current_pnl / initial_value

            # Estimate gap impact (only applied if position is losing badly)
            gap_slippage = self._gap_model.estimate_gap_impact(
                position_pnl_pct=pnl_pct,
                position_notional=position_notional,
                timestamp=current_time,
                underlying_volatility=underlying_iv,
                is_earnings=False,  # TODO: Detect earnings events
            )

            if gap_slippage > 0:
                # Apply gap slippage to position (will be realized on close)
                trade.metadata["gap_adjustment"] = (
                    trade.metadata.get("gap_adjustment", 0) - gap_slippage
                )
                self._gap_events += 1
                logger.info(
                    f"Gap risk event for {trade_id}: adding ${gap_slippage:.2f} slippage "
                    f"(P&L={pnl_pct:.1%}, crossing {current_time.time()} -> {next_bar_time.time()})"
                )

    def _check_profit_loss_dte_exits(
        self,
        trade: BacktestTrade,
        trade_id: str,
        timestamp: datetime,
        chain: OptionChain,
    ) -> tuple[bool, TradeStatus, float]:
        """Check if position should be closed due to profit target, stop loss, or DTE.

        Args:
            trade: The trade to check.
            trade_id: Trade identifier.
            timestamp: Current timestamp.
            chain: Current options chain.

        Returns:
            Tuple of (should_close, close_status, current_pnl).
        """
        should_close = False
        close_status = TradeStatus.CLOSED

        # Get management parameters from metadata
        profit_target = trade.metadata.get("profit_target")
        stop_loss = trade.metadata.get("stop_loss")
        close_dte = trade.metadata.get("close_dte", 7)

        # Calculate current unrealized P&L
        current_pnl = 0.0
        for leg in trade.legs:
            contract = None
            for c in chain.contracts:
                if c.symbol == leg.contract_symbol:
                    contract = c
                    break
            if contract:
                entry_price = trade.entry_prices.get(leg.contract_symbol, 0)
                current_price = contract.mid_price
                if leg.side == "sell":
                    current_pnl += (entry_price - current_price) * leg.quantity * 100
                else:
                    current_pnl += (current_price - entry_price) * leg.quantity * 100

        # Check profit target
        if profit_target is not None and current_pnl >= profit_target:
            should_close = True
            logger.info(
                f"Profit target reached for {trade_id}: "
                f"P&L ${current_pnl:.2f} >= target ${profit_target:.2f}"
            )

        # Check stop loss
        if not should_close and stop_loss is not None and current_pnl <= -stop_loss:
            should_close = True
            logger.info(
                f"Stop loss triggered for {trade_id}: "
                f"P&L ${current_pnl:.2f} <= stop -${stop_loss:.2f}"
            )

        # Check DTE-based exit
        if not should_close:
            for leg in trade.legs:
                dte = (leg.expiration - timestamp).days
                if dte <= close_dte:
                    should_close = True
                    logger.info(
                        f"DTE exit for {trade_id}: DTE={dte} <= close_dte={close_dte}"
                    )
                    break

        return should_close, close_status, current_pnl

    def _check_expiration_and_assignment(
        self,
        trade: BacktestTrade,
        timestamp: datetime,
        chain: OptionChain,
    ) -> tuple[bool, TradeStatus]:
        """Check if position should be closed due to expiration or early assignment.

        Args:
            trade: The trade to check.
            timestamp: Current timestamp.
            chain: Current options chain.

        Returns:
            Tuple of (should_close, close_status).
        """
        import random

        should_close = False
        close_status = TradeStatus.EXPIRED

        for leg in trade.legs:
            # Check expiration
            if leg.expiration.date() <= timestamp.date():
                should_close = True
                close_status = TradeStatus.EXPIRED
                break

            # Find current contract
            contract = None
            for c in chain.contracts:
                if c.symbol == leg.contract_symbol:
                    contract = c
                    break

            if contract is None:
                continue

            # Check early assignment risk for short ITM options
            if leg.side == "sell" and contract.delta is not None:
                delta_abs = abs(contract.delta)

                if delta_abs > self._early_assignment_threshold:
                    dte = (leg.expiration - timestamp).days

                    # Calculate assignment probability
                    threshold = self._early_assignment_threshold
                    daily_assignment_prob = 0.02 * (delta_abs - threshold) / (1.0 - threshold)

                    # Higher probability near expiration
                    if dte < 7:
                        daily_assignment_prob *= 2.0
                    elif dte < 14:
                        daily_assignment_prob *= 1.5

                    if random.random() < daily_assignment_prob:
                        should_close = True
                        close_status = TradeStatus.ASSIGNED
                        logger.info(
                            f"Early assignment triggered for {leg.contract_symbol} "
                            f"(delta={contract.delta:.2f}, DTE={dte})"
                        )
                        break

        return should_close, close_status

    def _calculate_gap_risk_adjustment(
        self,
        trade: BacktestTrade,
        timestamp: datetime,
        chain: OptionChain,
    ) -> float:
        """Calculate adverse P&L adjustment due to overnight gap risk.

        Args:
            trade: The trade to check.
            timestamp: Current timestamp.
            chain: Current options chain.

        Returns:
            Adverse P&L adjustment amount (negative for losses).
        """
        import random

        adverse_pnl_adjustment = 0.0

        # Check if this is a new day
        is_new_day = (
            len(self._equity_history) > 0
            and self._equity_history[-1][0].date() != timestamp.date()
        )

        if not is_new_day:
            return 0.0

        # Check for gap risk event
        if random.random() >= self._gap_risk_probability:
            return 0.0

        # Calculate gap severity
        gap_range = self._gap_severity_max - self._gap_severity_min
        gap_severity = self._gap_severity_min + random.random() * gap_range

        # Apply gap to each leg
        for leg in trade.legs:
            contract = None
            for c in chain.contracts:
                if c.symbol == leg.contract_symbol:
                    contract = c
                    break

            if contract is None:
                continue

            entry_price = trade.entry_prices.get(leg.contract_symbol, 0)
            current_mid = contract.mid_price

            if leg.side == "sell":
                # Short option moved against us
                adverse_move = (current_mid - entry_price) * gap_severity
                if adverse_move > 0:
                    adverse_pnl_adjustment -= adverse_move * leg.quantity * 100
            else:
                # Long option lost value
                adverse_move = (entry_price - current_mid) * gap_severity
                if adverse_move > 0:
                    adverse_pnl_adjustment -= adverse_move * leg.quantity * 100

        if adverse_pnl_adjustment < -50:
            logger.info(
                f"Gap risk event: adverse P&L adjustment: ${adverse_pnl_adjustment:.2f}"
            )

        return adverse_pnl_adjustment

    async def _process_positions(
        self, timestamp: datetime, chain: OptionChain
    ) -> None:
        """Process open positions for expiration/assignment/adverse moves.

        Simulates realistic scenarios:
        - Expiration at max profit/loss
        - Early assignment risk for deep ITM short options
        - Gap risk causing adverse moves
        - Overnight/weekend gaps
        """
        positions_to_close = []
        positions_with_adverse_pnl = {}

        for trade_id, trade in self._open_positions.items():
            # Check profit target, stop loss, and DTE exits
            should_close, close_status, current_pnl = self._check_profit_loss_dte_exits(
                trade, trade_id, timestamp, chain
            )

            # Check expiration and early assignment if not already closing
            if not should_close:
                should_close, close_status = self._check_expiration_and_assignment(
                    trade, timestamp, chain
                )

            # Calculate gap risk adjustment (applied even if position is closing)
            adverse_pnl_adjustment = self._calculate_gap_risk_adjustment(
                trade, timestamp, chain
            )

            # Collect positions to close and adverse P&L adjustments
            if should_close:
                positions_to_close.append((trade_id, close_status))
            elif adverse_pnl_adjustment != 0:
                positions_with_adverse_pnl[trade_id] = adverse_pnl_adjustment

        # Apply adverse P&L adjustments to trades (will be realized on close)
        for trade_id, adjustment in positions_with_adverse_pnl.items():
            if trade_id in self._open_positions:
                trade = self._open_positions[trade_id]
                # Store adverse adjustment in metadata for later
                trade.metadata["gap_adjustment"] = trade.metadata.get("gap_adjustment", 0) + adjustment

        # Close expired/assigned positions
        for trade_id, status in positions_to_close:
            await self._close_position(trade_id, timestamp, chain, status)

    async def _close_position(
        self,
        trade_id: str,
        timestamp: datetime,
        chain: Optional[OptionChain],
        status: TradeStatus = TradeStatus.CLOSED,
    ) -> None:
        """Close an open position."""
        if trade_id not in self._open_positions:
            return

        trade = self._open_positions[trade_id]

        # === PHASE 2A: FILL PROBABILITY CHECK FOR CLOSING TRADES ===
        # Check if closing order will fill (usually easier than opening, but still check)
        if self._enable_fill_probability and self._fill_model and chain:
            # Get VIX for fill context (default to 20 if not available)
            vix = 20.0  # TODO: Load actual VIX data from market data

            for leg in trade.legs:
                contract = None
                for c in chain.contracts:
                    if c.symbol == leg.contract_symbol:
                        contract = c
                        break

                if contract is None:
                    # If contract not found, assume expired/assigned - allow close
                    continue

                # Calculate bid-ask spread percentage
                if contract.bid > 0 and contract.ask > 0 and contract.mid_price > 0:
                    spread_pct = (contract.ask - contract.bid) / contract.mid_price
                else:
                    spread_pct = 0.20  # Assume wide spread if no data

                # Create fill context for closing trade
                fill_context = FillContext(
                    open_interest=contract.open_interest,
                    bid_ask_spread_pct=spread_pct,
                    timestamp=timestamp,
                    vix=vix,
                    order_size=leg.quantity,
                    avg_daily_volume=contract.volume if contract.volume else 1000,
                    option_type=contract.option_type,
                    is_opening=False,  # This is a CLOSING trade (easier to fill)
                )

                # Check if closing order will fill
                if not self._fill_model.will_fill(fill_context):
                    logger.warning(
                        f"Close order rejected for {trade_id} leg {leg.contract_symbol}: "
                        f"low fill probability (OI={contract.open_interest}, Spread={spread_pct:.2%})"
                    )
                    self._fill_rejections += 1
                    # Don't close this position - it's stuck!
                    # In real trading, this means you're holding an illiquid position
                    # Mark in metadata that we tried to close but failed
                    trade.metadata["close_rejected"] = True
                    trade.metadata["close_rejection_time"] = timestamp
                    return

        exit_prices = {}
        total_pnl = 0.0
        total_commission = 0.0

        total_slippage = 0.0
        for leg in trade.legs:
            # Find current price
            current_price = 0.0
            if chain:
                for contract in chain.contracts:
                    if contract.symbol == leg.contract_symbol:
                        is_buy_to_close = leg.side == "sell"
                        base_price = (
                            contract.ask if is_buy_to_close else contract.bid
                        )

                        # Apply slippage for closing trade
                        slippage = self._slippage_model.calculate(
                            price=base_price,
                            quantity=leg.quantity,
                            is_buy=is_buy_to_close,
                            volatility=contract.implied_volatility,
                            bid=contract.bid,
                            ask=contract.ask,
                            num_legs=len(trade.legs),
                            delta=contract.delta,  # For adaptive model
                            dte=contract.days_to_expiry,  # For adaptive model
                        )
                        total_slippage += slippage

                        # Adjust price for slippage (worse for us)
                        slippage_per_contract = slippage / (leg.quantity * 100)
                        if is_buy_to_close:
                            current_price = base_price + slippage_per_contract
                        else:
                            current_price = base_price - slippage_per_contract
                        break

            exit_prices[leg.contract_symbol] = current_price

            # Calculate P&L for this leg
            entry_price = trade.entry_prices.get(leg.contract_symbol, 0.0)
            if leg.side == "buy":
                # Long position: profit if price increased
                leg_pnl = (current_price - entry_price) * leg.quantity * 100
            else:
                # Short position: profit if price decreased
                leg_pnl = (entry_price - current_price) * leg.quantity * 100

            total_pnl += leg_pnl

            # Exit commission
            total_commission += self._commission_per_contract * leg.quantity

        # Apply any gap/adverse move adjustments accumulated during the trade
        gap_adjustment = trade.metadata.get("gap_adjustment", 0)
        total_pnl += gap_adjustment

        # Update trade record
        trade.exit_time = timestamp
        trade.exit_prices = exit_prices
        trade.status = status
        trade.pnl = total_pnl
        trade.commissions += total_commission
        trade.slippage += total_slippage  # Add exit slippage to entry slippage

        # Update cash
        self._cash += total_pnl - total_commission

        # Release buying power / collateral
        collateral = trade.metadata.get("collateral_required", 0.0)
        self._buying_power += collateral
        self._collateral_in_use -= collateral

        del self._open_positions[trade_id]

        logger.debug(
            f"Closed {trade_id}: status={status.value}, pnl=${total_pnl:.2f}, "
            f"released collateral=${collateral:.2f}"
        )

    async def _close_all_positions(
        self, timestamp: datetime, chain: Optional[OptionChain]
    ) -> None:
        """Close all open positions."""
        trade_ids = list(self._open_positions.keys())
        for trade_id in trade_ids:
            await self._close_position(trade_id, timestamp, chain, TradeStatus.CLOSED)

    def _calculate_equity(self, chain: Optional[OptionChain]) -> float:
        """Calculate current portfolio equity."""
        equity = self._cash

        # Add mark-to-market value of open positions
        for trade in self._open_positions.values():
            for leg in trade.legs:
                entry_price = trade.entry_prices.get(leg.contract_symbol, 0.0)
                current_price = entry_price  # Default to entry

                if chain:
                    for contract in chain.contracts:
                        if contract.symbol == leg.contract_symbol:
                            current_price = contract.mid_price
                            break

                # Position value
                if leg.side == "buy":
                    equity += current_price * leg.quantity * 100
                else:
                    # Short positions: liability
                    equity -= current_price * leg.quantity * 100

        return equity

    def _get_daily_pnl(self, timestamp: datetime) -> float:
        """Get P&L for the current day."""
        # Simplified: return difference from start of day
        if not self._equity_history:
            return 0.0

        today = timestamp.date()
        start_of_day_equity = self._starting_equity

        for ts, eq in self._equity_history:
            if ts.date() == today:
                start_of_day_equity = eq
                break

        return self._equity - start_of_day_equity

    def _calculate_daily_pnl(self, date) -> float:
        """Calculate P&L for a specific date."""
        # Get equity at start and end of day
        start_equity = None
        end_equity = None

        for ts, eq in self._equity_history:
            if ts.date() == date:
                if start_equity is None:
                    start_equity = eq
                end_equity = eq

        if start_equity is None or end_equity is None:
            return 0.0

        return end_equity - start_equity

    def _calculate_metrics(
        self, start_date: datetime, end_date: datetime
    ) -> BacktestMetrics:
        """Calculate performance metrics."""
        # Filter closed trades
        closed_trades = [t for t in self._trades if not t.is_open]

        # Basic stats
        total_trades = len(closed_trades)
        winning_trades = [t for t in closed_trades if t.net_pnl > 0]
        losing_trades = [t for t in closed_trades if t.net_pnl <= 0]

        total_return = self._equity - self._starting_equity
        total_return_percent = (total_return / self._starting_equity) * 100

        # Annualized return
        days = (end_date - start_date).days
        years = days / 365.25
        if years > 0 and self._equity > 0:
            annualized_return = (
                (self._equity / self._starting_equity) ** (1 / years) - 1
            ) * 100
        else:
            annualized_return = 0.0

        # Win rate
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

        # Average win/loss
        avg_win = (
            sum(t.net_pnl for t in winning_trades) / len(winning_trades)
            if winning_trades
            else 0
        )
        avg_loss = (
            sum(t.net_pnl for t in losing_trades) / len(losing_trades)
            if losing_trades
            else 0
        )

        # Profit factor
        gross_profit = sum(t.net_pnl for t in winning_trades)
        gross_loss = abs(sum(t.net_pnl for t in losing_trades))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Max drawdown
        max_drawdown = 0.0
        max_drawdown_percent = 0.0
        peak = self._starting_equity

        for _, equity in self._equity_history:
            if equity > peak:
                peak = equity
            drawdown = peak - equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_drawdown_percent = (drawdown / peak) * 100

        # Sharpe and Sortino ratios
        # FIXED: Calculate returns directly from equity_history instead of flawed _daily_pnl
        # For daily backtests, _daily_pnl incorrectly returns zeros
        if len(self._equity_history) > 1:
            # Group equity by date (take last value of each day)
            equity_by_date = {}
            for ts, eq in self._equity_history:
                date = ts.date()
                equity_by_date[date] = eq  # Last equity value for each date

            # Sort by date and calculate day-over-day returns
            sorted_dates = sorted(equity_by_date.keys())
            daily_equity = [equity_by_date[d] for d in sorted_dates]

            # Calculate percentage returns
            daily_returns = []
            for i in range(1, len(daily_equity)):
                if daily_equity[i-1] > 0:
                    ret = (daily_equity[i] - daily_equity[i-1]) / daily_equity[i-1]
                    daily_returns.append(ret)

            if len(daily_returns) > 1:
                daily_returns = pd.Series(daily_returns)
                avg_daily_return = daily_returns.mean()
                std_daily_return = daily_returns.std()

                # Sharpe (assuming 0% risk-free rate)
                sharpe_ratio = (
                    (avg_daily_return / std_daily_return) * (252**0.5)
                    if std_daily_return > 0
                    else 0
                )

                # Sortino (downside deviation)
                downside_returns = daily_returns[daily_returns < 0]
                downside_std = downside_returns.std() if len(downside_returns) > 0 else 0
                sortino_ratio = (
                    (avg_daily_return / downside_std) * (252**0.5)
                    if downside_std > 0
                    else 0
                )
            else:
                sharpe_ratio = 0.0
                sortino_ratio = 0.0
        else:
            sharpe_ratio = 0.0
            sortino_ratio = 0.0

        # Average holding period
        holding_periods = [
            t.holding_period_days for t in closed_trades if t.holding_period_days
        ]
        avg_holding_period = (
            sum(holding_periods) / len(holding_periods) if holding_periods else 0
        )

        # Costs
        total_commissions = sum(t.commissions for t in self._trades)
        total_slippage = sum(t.slippage for t in self._trades)

        # Phase 2A: Calculate fill rejection rate
        # Rejection rate = rejections / (trades + rejections)
        total_signals = total_trades + self._fill_rejections
        fill_rejection_rate = (
            (self._fill_rejections / total_signals * 100) if total_signals > 0 else 0.0
        )

        return BacktestMetrics(
            total_return=total_return,
            total_return_percent=total_return_percent,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_percent=max_drawdown_percent,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_trade_pnl=total_return / total_trades if total_trades > 0 else 0,
            avg_holding_period_days=avg_holding_period,
            total_commissions=total_commissions,
            total_slippage=total_slippage,
            starting_equity=self._starting_equity,
            ending_equity=self._equity,
            peak_equity=self._peak_equity,
            # Phase 2A metrics
            fill_rejections=self._fill_rejections,
            gap_events=self._gap_events,
            fill_rejection_rate=fill_rejection_rate,
        )
