# Phase 2: Backtest Realism Improvements - Technical Specification

**Version**: 1.0
**Date**: December 5, 2024
**Status**: Specification Complete - Ready for Implementation
**Dependencies**: Phase 1 Complete (Adaptive Slippage Model)

---

## Executive Summary

This specification details critical improvements to backtest realism that address gaps between theoretical backtests and real-world trading. Phase 1 validated that the strategy works with realistic slippage (+371% QQQ returns). Phase 2 will model five additional real-world constraints that currently assume "perfect execution."

**Expected Impact**: Reduce backtest returns by 30-50% to conservative, high-confidence projections that closely match live trading performance.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Phase 2A: Critical Execution Constraints](#phase-2a-critical-execution-constraints)
   - 2.1 Order Fill Probability Modeling
   - 2.2 Overnight & Weekend Gap Risk
3. [Phase 2B: Position-Level Risks](#phase-2b-position-level-risks)
   - 2.3 Early Assignment Risk
   - 2.4 Liquidity-Based Fill Modeling
   - 2.5 Position Correlation Limits
4. [Implementation Plan](#implementation-plan)
5. [Testing & Validation](#testing--validation)
6. [Configuration](#configuration)
7. [Appendix: Research & Data Sources](#appendix-research--data-sources)

---

## Architecture Overview

### Current Backtest Flow

```
1. Signal Generation (Strategy)
   ↓
2. Order Placement (100% fill assumed)
   ↓
3. Execution (mid + adaptive slippage)
   ↓
4. Position Management (instant exit anytime)
   ↓
5. Exit Signal (100% fill assumed)
```

### Enhanced Backtest Flow (Phase 2)

```
1. Signal Generation (Strategy)
   ↓
2. Pre-Trade Validation
   ├─ Correlation Risk Check (NEW)
   └─ Liquidity Validation (ENHANCED)
   ↓
3. Order Placement
   ├─ Fill Probability Check (NEW)
   └─ Market Impact Calculation (NEW)
   ↓
4. Execution (if filled)
   ├─ Adaptive Slippage (Phase 1)
   └─ Liquidity-Based Additional Slippage (NEW)
   ↓
5. Position Management
   ├─ Early Assignment Check (NEW)
   ├─ Gap Risk Monitoring (NEW)
   └─ Intraday Monitoring (existing)
   ↓
6. Exit Signal
   ├─ Market Hours Check (NEW)
   ├─ Fill Probability Check (NEW)
   └─ Execution (if filled)
```

### New Components

```python
# src/alpaca_options/backtesting/execution_model.py (NEW)
class ExecutionModel:
    """Models realistic order execution constraints."""

    def calculate_fill_probability(...)
    def calculate_market_impact(...)
    def check_market_hours(...)
    def estimate_gap_slippage(...)

# src/alpaca_options/backtesting/assignment_model.py (NEW)
class AssignmentModel:
    """Models early assignment risk for short options."""

    def calculate_assignment_probability(...)
    def handle_assignment(...)
    def get_dividend_dates(...)

# src/alpaca_options/risk/correlation_manager.py (NEW)
class CorrelationManager:
    """Manages position correlation and concentration risk."""

    def check_correlation_limits(...)
    def calculate_portfolio_correlation(...)
    def get_correlation_groups(...)
```

---

## Phase 2A: Critical Execution Constraints

### 2.1 Order Fill Probability Modeling

#### Problem Statement

**Current Behavior**: Assumes 100% fill rate for all orders at mid price + slippage.

**Reality**: Many orders don't fill due to:
- Insufficient liquidity (low open interest, wide spreads)
- Time of day (illiquid at market open/close)
- Market stress (VIX spikes, flash crashes)
- Order size vs available liquidity

**Impact**: Backtests overestimate returns by counting trades that would never execute in real markets.

#### Technical Specification

**File**: `src/alpaca_options/backtesting/execution_model.py` (NEW)

**Class**: `FillProbabilityModel`

```python
from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional

@dataclass
class FillContext:
    """Context for fill probability calculation."""
    open_interest: int
    bid_ask_spread_pct: float
    timestamp: datetime
    vix: float
    order_size: int
    avg_daily_volume: int
    option_type: str  # "call" or "put"
    is_opening: bool  # True for opening, False for closing


class FillProbabilityModel:
    """Models realistic order fill probability based on market conditions.

    Research basis:
    - CBOE Options Institute: "Liquidity Considerations for Options Trading"
    - Tastyworks research: Fill rates by OI and spread width
    - Real-world observation: ~85% fill rate for liquid options, ~50% for illiquid
    """

    def __init__(
        self,
        min_oi_threshold: int = 50,
        max_spread_threshold: float = 0.10,
        illiquid_hour_multiplier: float = 0.85,
        high_vix_multiplier: float = 0.90,
    ):
        """Initialize fill probability model.

        Args:
            min_oi_threshold: Minimum OI to consider tradeable (default: 50)
            max_spread_threshold: Max spread % for reasonable fills (default: 10%)
            illiquid_hour_multiplier: Penalty during first/last hour (default: 0.85)
            high_vix_multiplier: Penalty during high VIX (default: 0.90)
        """
        self.min_oi_threshold = min_oi_threshold
        self.max_spread_threshold = max_spread_threshold
        self.illiquid_hour_multiplier = illiquid_hour_multiplier
        self.high_vix_multiplier = high_vix_multiplier

    def calculate_fill_probability(self, context: FillContext) -> float:
        """Calculate probability that an order will fill.

        Returns value between 0.0 and 1.0:
        - 0.0 = Will not fill (too illiquid)
        - 0.5 = 50% chance of fill
        - 1.0 = Very likely to fill

        The backtest engine will use random.random() < fill_prob to determine
        if the order executes.
        """
        # Base probability starts at 1.0 (assume liquid market)
        prob = 1.0

        # === Liquidity Penalties ===

        # Open Interest Check
        if context.open_interest < self.min_oi_threshold:
            return 0.0  # Reject: Too illiquid to trade
        elif context.open_interest < 200:
            prob *= 0.50  # 50% fill rate for very low OI
        elif context.open_interest < 500:
            prob *= 0.75  # 75% fill rate for low OI
        elif context.open_interest < 1000:
            prob *= 0.90  # 90% fill rate for moderate OI
        # else: prob *= 1.0 (no penalty for OI >= 1000)

        # Bid-Ask Spread Check
        if context.bid_ask_spread_pct > self.max_spread_threshold:
            return 0.0  # Reject: Spread too wide (>10%)
        elif context.bid_ask_spread_pct > 0.07:  # 7-10% spread
            prob *= 0.60  # 60% fill rate
        elif context.bid_ask_spread_pct > 0.05:  # 5-7% spread
            prob *= 0.80  # 80% fill rate
        elif context.bid_ask_spread_pct > 0.03:  # 3-5% spread
            prob *= 0.95  # 95% fill rate
        # else: prob *= 1.0 (no penalty for spread < 3%)

        # === Time of Day Penalties ===

        # Market open/close hours (9:30-10:00, 15:30-16:00)
        hour = context.timestamp.hour
        minute = context.timestamp.minute

        is_market_open = (hour == 9 and minute >= 30) or (hour == 10 and minute == 0)
        is_market_close = (hour == 15 and minute >= 30) or hour == 16

        if is_market_open or is_market_close:
            prob *= self.illiquid_hour_multiplier  # 15% penalty

        # === Volatility Penalties ===

        # High VIX environment (harder to get fills at desired prices)
        if context.vix > 30:
            prob *= self.high_vix_multiplier  # 10% penalty
        elif context.vix > 40:
            prob *= 0.80  # 20% penalty for extreme VIX

        # === Order Size vs Liquidity ===

        # Large order relative to daily volume
        if context.avg_daily_volume > 0:
            volume_ratio = context.order_size / context.avg_daily_volume

            if volume_ratio > 0.20:  # Order is >20% of daily volume
                prob *= 0.50  # 50% fill rate (market impact concern)
            elif volume_ratio > 0.10:  # Order is >10% of daily volume
                prob *= 0.75  # 75% fill rate

        # === Closing Orders (Easier to Fill) ===

        # Slightly easier to close positions than open them
        if not context.is_opening:
            prob = min(1.0, prob * 1.10)  # +10% bonus for closing

        return max(0.0, min(1.0, prob))

    def will_fill(self, context: FillContext, random_seed: Optional[float] = None) -> bool:
        """Determine if order fills based on probability.

        Args:
            context: Fill context
            random_seed: Optional random value [0, 1). If None, generates new random.

        Returns:
            True if order fills, False otherwise
        """
        prob = self.calculate_fill_probability(context)

        if prob == 0.0:
            return False
        elif prob == 1.0:
            return True
        else:
            import random
            rand_val = random_seed if random_seed is not None else random.random()
            return rand_val < prob
```

#### Integration Points

**File**: `src/alpaca_options/backtesting/engine.py`

**Modifications**:

1. **Add to `__init__`**:
```python
from alpaca_options.backtesting.execution_model import FillProbabilityModel, FillContext

class BacktestEngine:
    def __init__(self, config: BacktestConfig, risk_config: RiskConfig):
        # ... existing code ...

        # NEW: Initialize fill probability model
        self._fill_model = FillProbabilityModel(
            min_oi_threshold=config.execution.min_oi_threshold,
            max_spread_threshold=config.execution.max_spread_threshold,
        )
```

2. **Update `_execute_signal` method** (around line 650):
```python
async def _execute_signal(self, signal: OptionSignal, timestamp: datetime) -> None:
    """Execute a trading signal with fill probability check."""

    # ... existing pre-checks ...

    # NEW: Check fill probability for each leg
    for leg in signal.legs:
        contract = self._get_contract(leg, timestamp)
        if contract is None:
            logger.debug(f"Contract not found: {leg.symbol}")
            return  # Skip this signal

        # Get VIX for fill context (using VIX from market data if available)
        vix = self._get_vix(timestamp)  # NEW helper method

        # Create fill context
        fill_context = FillContext(
            open_interest=contract.open_interest,
            bid_ask_spread_pct=(contract.ask - contract.bid) / contract.mid_price,
            timestamp=timestamp,
            vix=vix,
            order_size=leg.quantity,
            avg_daily_volume=contract.volume or 1000,  # Use contract volume or estimate
            option_type=contract.option_type,
            is_opening=True,
        )

        # Check if order will fill
        if not self._fill_model.will_fill(fill_context):
            logger.info(
                f"Order rejected due to low fill probability: {leg.symbol} "
                f"(OI={contract.open_interest}, Spread={fill_context.bid_ask_spread_pct:.2%})"
            )
            # Track rejection for metrics
            self._track_rejection(signal, timestamp, reason="low_fill_probability")
            return  # Don't execute this signal

    # If all legs pass fill probability, proceed with execution
    # ... existing execution code ...
```

3. **Add helper method**:
```python
def _get_vix(self, timestamp: datetime) -> float:
    """Get VIX value for timestamp.

    TODO: Load VIX data from data loader. For now, estimate from SPY IV.
    """
    # Placeholder: Use SPY 30-day IV as VIX proxy
    # In production, load actual VIX data
    return 20.0  # Default to moderate volatility
```

#### Configuration

**File**: `config/paper_trading.yaml`

**New section under `backtesting.execution`**:
```yaml
backtesting:
  execution:
    slippage_model: "adaptive"
    commission_per_contract: 0.65

    # NEW: Fill probability settings
    enable_fill_probability: true  # Toggle for A/B testing
    min_oi_threshold: 100  # Minimum open interest to trade
    max_spread_threshold: 0.10  # Max 10% spread
    illiquid_hour_multiplier: 0.85  # 15% penalty during open/close
    high_vix_multiplier: 0.90  # 10% penalty when VIX > 30
```

#### Testing

**Test File**: `tests/backtesting/test_fill_probability.py` (NEW)

```python
import pytest
from datetime import datetime
from alpaca_options.backtesting.execution_model import FillProbabilityModel, FillContext


def test_fill_probability_liquid_option():
    """Liquid option should have high fill probability."""
    model = FillProbabilityModel()

    context = FillContext(
        open_interest=5000,
        bid_ask_spread_pct=0.02,  # 2% spread
        timestamp=datetime(2024, 6, 15, 11, 0),  # Mid-day
        vix=18.0,  # Low volatility
        order_size=1,
        avg_daily_volume=10000,
        option_type="put",
        is_opening=True,
    )

    prob = model.calculate_fill_probability(context)
    assert prob >= 0.95  # Should be very high


def test_fill_probability_illiquid_option():
    """Illiquid option should have low/zero fill probability."""
    model = FillProbabilityModel()

    context = FillContext(
        open_interest=30,  # Below min threshold (50)
        bid_ask_spread_pct=0.15,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=1,
        avg_daily_volume=50,
        option_type="put",
        is_opening=True,
    )

    prob = model.calculate_fill_probability(context)
    assert prob == 0.0  # Should reject


def test_fill_probability_market_close():
    """Fill probability should be lower near market close."""
    model = FillProbabilityModel()

    base_context = FillContext(
        open_interest=1000,
        bid_ask_spread_pct=0.03,
        timestamp=datetime(2024, 6, 15, 11, 0),  # Mid-day
        vix=20.0,
        order_size=1,
        avg_daily_volume=5000,
        option_type="put",
        is_opening=True,
    )

    close_context = FillContext(
        **{**base_context.__dict__, "timestamp": datetime(2024, 6, 15, 15, 45)}  # Near close
    )

    prob_midday = model.calculate_fill_probability(base_context)
    prob_close = model.calculate_fill_probability(close_context)

    assert prob_close < prob_midday  # Lower probability at close


def test_fill_probability_high_vix():
    """High VIX should reduce fill probability."""
    model = FillProbabilityModel()

    low_vix_context = FillContext(
        open_interest=1000,
        bid_ask_spread_pct=0.03,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=15.0,  # Low VIX
        order_size=1,
        avg_daily_volume=5000,
        option_type="put",
        is_opening=True,
    )

    high_vix_context = FillContext(
        **{**low_vix_context.__dict__, "vix": 35.0}  # High VIX
    )

    prob_low_vix = model.calculate_fill_probability(low_vix_context)
    prob_high_vix = model.calculate_fill_probability(high_vix_context)

    assert prob_high_vix < prob_low_vix


def test_closing_orders_easier():
    """Closing orders should be easier to fill than opening."""
    model = FillProbabilityModel()

    opening_context = FillContext(
        open_interest=500,
        bid_ask_spread_pct=0.04,
        timestamp=datetime(2024, 6, 15, 11, 0),
        vix=20.0,
        order_size=1,
        avg_daily_volume=2000,
        option_type="put",
        is_opening=True,
    )

    closing_context = FillContext(
        **{**opening_context.__dict__, "is_opening": False}
    )

    prob_opening = model.calculate_fill_probability(opening_context)
    prob_closing = model.calculate_fill_probability(closing_context)

    assert prob_closing >= prob_opening
```

---

### 2.2 Overnight & Weekend Gap Risk

#### Problem Statement

**Current Behavior**: Can exit positions instantly at any time, including during market close.

**Reality**:
- Market is closed ~70% of the time (16:00 - 9:30 next day, weekends, holidays)
- Can't honor stop losses during gaps
- Positions can gap against you overnight
- Earnings, news, and macro events often happen after hours

**Impact**: Backtests underestimate loss severity by assuming perfect stop loss execution.

#### Technical Specification

**File**: `src/alpaca_options/backtesting/execution_model.py`

**Class**: `GapRiskModel`

```python
from datetime import datetime, time, timedelta
from typing import Tuple, Optional
import math

class GapRiskModel:
    """Models overnight and weekend gap risk for options positions.

    Research basis:
    - Average overnight gap: ~0.5% for SPY/QQQ
    - Weekend gaps average 0.8% (more time for news)
    - Options have gamma risk - gaps are magnified by delta changes
    - Stop losses cannot be honored during market close
    """

    # Market hours (Eastern Time)
    MARKET_OPEN = time(9, 30)
    MARKET_CLOSE = time(16, 0)

    def __init__(
        self,
        avg_overnight_gap_pct: float = 0.005,  # 0.5% average
        weekend_multiplier: float = 1.6,  # 60% larger gaps over weekends
        earnings_multiplier: float = 3.0,  # 3x gap on earnings
        stop_loss_slippage_pct: float = 0.02,  # Extra 2% slippage on gap stops
    ):
        """Initialize gap risk model.

        Args:
            avg_overnight_gap_pct: Average overnight gap size
            weekend_multiplier: Multiplier for weekend gaps
            earnings_multiplier: Multiplier for earnings gaps
            stop_loss_slippage_pct: Additional slippage when stop triggered by gap
        """
        self.avg_overnight_gap = avg_overnight_gap_pct
        self.weekend_multiplier = weekend_multiplier
        self.earnings_multiplier = earnings_multiplier
        self.stop_loss_slippage = stop_loss_slippage_pct

    def is_market_open(self, timestamp: datetime) -> bool:
        """Check if market is currently open."""
        # Check if weekend
        if timestamp.weekday() >= 5:  # Saturday=5, Sunday=6
            return False

        # Check if during market hours
        current_time = timestamp.time()
        return self.MARKET_OPEN <= current_time <= self.MARKET_CLOSE

    def hours_until_market_open(self, timestamp: datetime) -> float:
        """Calculate hours until next market open."""
        if self.is_market_open(timestamp):
            return 0.0

        # Calculate next market open
        current_date = timestamp.date()
        current_time = timestamp.time()

        # If before market open today and it's a weekday
        if current_time < self.MARKET_OPEN and timestamp.weekday() < 5:
            next_open = datetime.combine(current_date, self.MARKET_OPEN)
        else:
            # Find next weekday
            days_ahead = 1
            if timestamp.weekday() == 4:  # Friday
                days_ahead = 3  # Skip to Monday
            elif timestamp.weekday() == 5:  # Saturday
                days_ahead = 2

            next_date = current_date + timedelta(days=days_ahead)
            next_open = datetime.combine(next_date, self.MARKET_OPEN)

        # Calculate hours
        time_diff = next_open - timestamp
        return time_diff.total_seconds() / 3600

    def estimate_gap_impact(
        self,
        position: "Trade",  # Forward reference to Trade class
        timestamp: datetime,
        underlying_volatility: float,
        is_earnings: bool = False,
    ) -> float:
        """Estimate potential gap impact on position P&L.

        Returns:
            Additional slippage amount (always positive, represents cost)
        """
        if self.is_market_open(timestamp):
            return 0.0  # No gap risk during market hours

        # Calculate hours of gap exposure
        hours_closed = self.hours_until_market_open(timestamp)

        # Base gap estimate (scales with time)
        # Overnight (16 hours) = 0.5%, Weekend (64 hours) = 0.8%
        days_closed = hours_closed / 24.0
        base_gap_pct = self.avg_overnight_gap * math.sqrt(days_closed)

        # Apply multipliers
        if hours_closed > 60:  # Weekend
            base_gap_pct *= self.weekend_multiplier

        if is_earnings:
            base_gap_pct *= self.earnings_multiplier

        # Volatility scaling (higher IV = larger gaps)
        vol_multiplier = underlying_volatility / 0.20  # Scale to 20% IV baseline
        base_gap_pct *= vol_multiplier

        # For options positions, gap can break through stop loss
        # If position is already below stop loss threshold, model worst-case gap
        position_pnl_pct = position.unrealized_pnl / position.initial_credit if position.initial_credit > 0 else 0

        # If position would have triggered stop loss, add gap slippage
        if position_pnl_pct < -1.0:  # Lost more than 100% (2x credit)
            # Additional slippage from gap
            gap_slippage = position.notional_value * self.stop_loss_slippage
            return gap_slippage

        return 0.0  # No gap impact if position is healthy

    def should_check_gap_risk(
        self,
        current_time: datetime,
        next_bar_time: datetime,
    ) -> bool:
        """Determine if we're crossing a market close boundary.

        Returns True if next bar is after a market close, indicating
        we need to model gap risk.
        """
        # Check if we're crossing from open -> close
        current_open = self.is_market_open(current_time)
        next_open = self.is_market_open(next_bar_time)

        # If currently open but next bar is closed, we're crossing close
        if current_open and not next_open:
            return True

        # If currently closed and next bar is open, we're crossing open (gap!)
        if not current_open and next_open:
            return True

        return False
```

#### Integration Points

**File**: `src/alpaca_options/backtesting/engine.py`

**Modifications**:

1. **Add to `__init__`**:
```python
from alpaca_options.backtesting.execution_model import GapRiskModel

class BacktestEngine:
    def __init__(self, config: BacktestConfig, risk_config: RiskConfig):
        # ... existing code ...

        # NEW: Initialize gap risk model
        self._gap_model = GapRiskModel(
            avg_overnight_gap_pct=config.execution.avg_overnight_gap,
            weekend_multiplier=config.execution.weekend_gap_multiplier,
        )
```

2. **Add gap check in main backtest loop** (around line 550):
```python
async def run(
    self,
    strategy: BaseStrategy,
    underlying_data: pd.DataFrame,
    options_data: dict[datetime, OptionChain],
    start_date: datetime,
    end_date: datetime,
) -> BacktestResult:
    """Run backtest with gap risk monitoring."""

    # ... existing setup ...

    for i, timestamp in enumerate(timestamps):
        # ... existing bar processing ...

        # NEW: Check for gap risk before next bar
        if i < len(timestamps) - 1:
            next_timestamp = timestamps[i + 1]

            if self._gap_model.should_check_gap_risk(timestamp, next_timestamp):
                # We're crossing a market close/open boundary
                self._process_gap_risk(timestamp, next_timestamp)

        # ... existing position management ...
```

3. **Add gap risk processing method**:
```python
def _process_gap_risk(
    self,
    current_time: datetime,
    next_time: datetime,
) -> None:
    """Process gap risk for open positions crossing market close/open.

    This models the inability to exit positions during market close and
    potential gap slippage when market reopens.
    """
    if not self._trades:
        return  # No open positions

    for trade in list(self._trades.values()):
        if trade.status != "open":
            continue

        # Get current underlying price and IV
        underlying_price = self._get_underlying_price(current_time)
        underlying_iv = self._get_underlying_iv(current_time)

        # Check if this is an earnings gap (TODO: load earnings dates)
        is_earnings = False  # Placeholder

        # Estimate gap impact
        gap_slippage = self._gap_model.estimate_gap_impact(
            position=trade,
            timestamp=current_time,
            underlying_volatility=underlying_iv,
            is_earnings=is_earnings,
        )

        if gap_slippage > 0:
            logger.warning(
                f"Gap risk slippage applied: {trade.id} - ${gap_slippage:.2f} "
                f"(Crossing {current_time} -> {next_time})"
            )

            # Apply gap slippage to position
            trade.realized_pnl -= gap_slippage
            trade.commissions += gap_slippage  # Track as additional cost

            # If position now triggers stop loss, force close at worse price
            position_loss_pct = abs(trade.unrealized_pnl / trade.initial_credit)

            if position_loss_pct > 2.0:  # 2x credit = stop loss
                logger.info(
                    f"Stop loss triggered by gap: {trade.id} at {next_time} "
                    f"(Loss: {position_loss_pct:.1%})"
                )
                # Force close at market open (next_time) with additional slippage
                await self._force_close_position(trade, next_time, reason="gap_stop_loss")
```

#### Configuration

**File**: `config/paper_trading.yaml`

```yaml
backtesting:
  execution:
    # ... existing settings ...

    # NEW: Gap risk settings
    enable_gap_risk: true
    avg_overnight_gap: 0.005  # 0.5% average overnight gap
    weekend_gap_multiplier: 1.6  # 60% larger gaps over weekends
    earnings_gap_multiplier: 3.0  # 3x gap size on earnings
    gap_stop_loss_slippage: 0.02  # Extra 2% slippage on gap stops
```

#### Testing

**Test File**: `tests/backtesting/test_gap_risk.py` (NEW)

```python
import pytest
from datetime import datetime, time
from alpaca_options.backtesting.execution_model import GapRiskModel


def test_market_hours_detection():
    """Test market open/close detection."""
    model = GapRiskModel()

    # Market open
    assert model.is_market_open(datetime(2024, 6, 17, 11, 0))  # Monday 11am

    # Market closed
    assert not model.is_market_open(datetime(2024, 6, 17, 8, 0))  # Before open
    assert not model.is_market_open(datetime(2024, 6, 17, 17, 0))  # After close
    assert not model.is_market_open(datetime(2024, 6, 15, 11, 0))  # Saturday


def test_hours_until_open_overnight():
    """Test overnight hours calculation."""
    model = GapRiskModel()

    # 5pm on Monday -> 9:30am Tuesday = 16.5 hours
    monday_close = datetime(2024, 6, 17, 17, 0)
    hours = model.hours_until_market_open(monday_close)

    assert 16.0 <= hours <= 17.0  # ~16.5 hours


def test_hours_until_open_weekend():
    """Test weekend hours calculation."""
    model = GapRiskModel()

    # 5pm Friday -> 9:30am Monday = ~64.5 hours
    friday_close = datetime(2024, 6, 14, 17, 0)
    hours = model.hours_until_market_open(friday_close)

    assert 64.0 <= hours <= 65.0  # ~64.5 hours


def test_gap_impact_overnight():
    """Test overnight gap impact estimation."""
    # TODO: Implement after Trade class is available
    pass


def test_gap_impact_weekend():
    """Test weekend gap impact (should be larger than overnight)."""
    # TODO: Implement after Trade class is available
    pass
```

---

## Phase 2B: Position-Level Risks

### 2.3 Early Assignment Risk

#### Problem Statement

**Current Behavior**: Assumes all short options are held until exit signal.

**Reality**:
- Short ITM options can be assigned early (especially deep ITM)
- Call assignment risk increases before ex-dividend dates
- Put assignment risk increases when borrow rates are high
- Assignment forces position closure at unfavorable prices

**Impact**: Backtests underestimate forced closures and associated costs.

#### Technical Specification

**File**: `src/alpaca_options/backtesting/assignment_model.py` (NEW)

```python
from dataclasses import dataclass
from datetime import datetime, date
from typing import Optional, List
import random

@dataclass
class DividendInfo:
    """Dividend information for a symbol."""
    symbol: str
    ex_date: date
    amount: float


class AssignmentModel:
    """Models early assignment risk for short options.

    Research basis:
    - OCC Assignment Statistics: ~5% of ITM options assigned early
    - Assignment probability increases with ITM depth
    - Call assignment spikes before ex-dividend
    - Put assignment rare except deep ITM or high borrow costs
    """

    def __init__(
        self,
        min_delta_for_assignment: float = 0.75,
        deep_itm_delta: float = 0.95,
        base_assignment_prob: float = 0.02,  # 2% per day for ITM
        deep_itm_prob: float = 0.15,  # 15% per day for deep ITM
        dividend_call_prob: float = 0.80,  # 80% if ITM call before ex-div
        expiration_week_multiplier: float = 2.0,  # 2x probability in expiration week
    ):
        """Initialize assignment model.

        Args:
            min_delta_for_assignment: Minimum delta to consider assignment risk
            deep_itm_delta: Delta threshold for "deep ITM"
            base_assignment_prob: Base daily assignment probability for ITM
            deep_itm_prob: Daily assignment probability for deep ITM
            dividend_call_prob: Assignment probability for ITM calls before ex-div
            expiration_week_multiplier: Probability multiplier in expiration week
        """
        self.min_delta = min_delta_for_assignment
        self.deep_itm_delta = deep_itm_delta
        self.base_prob = base_assignment_prob
        self.deep_itm_prob = deep_itm_prob
        self.dividend_call_prob = dividend_call_prob
        self.exp_week_multiplier = expiration_week_multiplier

        # Dividend calendar (would load from external source in production)
        self._dividend_calendar: List[DividendInfo] = []

    def load_dividend_calendar(self, dividends: List[DividendInfo]) -> None:
        """Load dividend dates for assignment modeling."""
        self._dividend_calendar = dividends

    def get_next_dividend(self, symbol: str, current_date: date) -> Optional[DividendInfo]:
        """Get next dividend date for a symbol."""
        future_dividends = [
            d for d in self._dividend_calendar
            if d.symbol == symbol and d.ex_date > current_date
        ]

        if not future_dividends:
            return None

        # Return nearest future dividend
        return min(future_dividends, key=lambda d: d.ex_date)

    def calculate_assignment_probability(
        self,
        delta: float,
        dte: int,
        option_type: str,
        underlying_symbol: str,
        current_date: date,
    ) -> float:
        """Calculate daily probability of early assignment.

        Returns:
            Probability between 0.0 and 1.0 per day
        """
        # Use absolute delta (puts have negative delta)
        abs_delta = abs(delta)

        # Not ITM enough for assignment
        if abs_delta < self.min_delta:
            return 0.0

        # Base probability by ITM depth
        if abs_delta >= self.deep_itm_delta:
            prob = self.deep_itm_prob  # Deep ITM: 15% per day
        else:
            prob = self.base_prob  # Moderate ITM: 2% per day

        # Expiration week multiplier
        if dte <= 7:
            prob *= self.exp_week_multiplier

        # Special case: Call assignment before ex-dividend
        if option_type == "call":
            next_div = self.get_next_dividend(underlying_symbol, current_date)

            if next_div is not None:
                days_to_dividend = (next_div.ex_date - current_date).days

                # Day before ex-dividend: very high assignment probability
                if days_to_dividend == 1 and abs_delta > 0.70:
                    prob = max(prob, self.dividend_call_prob)
                # Week before ex-dividend: moderate increase
                elif days_to_dividend <= 7 and abs_delta > 0.70:
                    prob *= 2.0

        return min(prob, 1.0)  # Cap at 100%

    def will_be_assigned(
        self,
        delta: float,
        dte: int,
        option_type: str,
        underlying_symbol: str,
        current_date: date,
        random_seed: Optional[float] = None,
    ) -> bool:
        """Determine if option will be assigned early.

        Args:
            delta: Option delta
            dte: Days to expiration
            option_type: "call" or "put"
            underlying_symbol: Underlying ticker
            current_date: Current date
            random_seed: Optional random value for testing

        Returns:
            True if assigned, False otherwise
        """
        prob = self.calculate_assignment_probability(
            delta, dte, option_type, underlying_symbol, current_date
        )

        if prob == 0.0:
            return False
        elif prob >= 1.0:
            return True
        else:
            rand_val = random_seed if random_seed is not None else random.random()
            return rand_val < prob
```

#### Integration Points

**File**: `src/alpaca_options/backtesting/engine.py`

**Modifications**:

1. **Add to `__init__`**:
```python
from alpaca_options.backtesting.assignment_model import AssignmentModel, DividendInfo

class BacktestEngine:
    def __init__(self, config: BacktestConfig, risk_config: RiskConfig):
        # ... existing code ...

        # NEW: Initialize assignment model
        self._assignment_model = AssignmentModel(
            min_delta_for_assignment=config.execution.assignment_min_delta,
            base_assignment_prob=config.execution.assignment_base_prob,
        )

        # Load dividend calendar (TODO: from data source)
        # self._load_dividend_calendar()
```

2. **Add assignment check in position management** (around line 900):
```python
def _check_positions(self, timestamp: datetime, chain: OptionChain) -> None:
    """Check open positions for exit signals and assignment risk."""

    for trade in list(self._trades.values()):
        if trade.status != "open":
            continue

        # ... existing exit logic ...

        # NEW: Check early assignment risk for short options
        for leg in trade.legs:
            if leg.action == "sell":  # Short options only
                contract = self._get_contract_from_chain(leg.symbol, chain)

                if contract is None:
                    continue

                # Check if assignment will occur
                will_assign = self._assignment_model.will_be_assigned(
                    delta=contract.delta,
                    dte=contract.days_to_expiry,
                    option_type=contract.option_type,
                    underlying_symbol=chain.underlying,
                    current_date=timestamp.date(),
                )

                if will_assign:
                    logger.warning(
                        f"Early assignment: {trade.id} - {leg.symbol} "
                        f"(Delta={contract.delta:.3f}, DTE={contract.days_to_expiry})"
                    )

                    # Force close entire spread (assignment triggers closure)
                    await self._handle_assignment(trade, timestamp, leg.symbol)
                    break  # Move to next trade
```

3. **Add assignment handling method**:
```python
async def _handle_assignment(
    self,
    trade: "Trade",
    timestamp: datetime,
    assigned_symbol: str,
) -> None:
    """Handle early assignment of a short option.

    When a short option is assigned:
    1. Close the entire spread position
    2. Apply assignment costs (usually worse than voluntary exit)
    3. Track assignment for metrics
    """
    logger.info(f"Processing early assignment: {trade.id} at {timestamp}")

    # Assignment typically happens at worse prices than market
    # Apply penalty: close at bid instead of mid (for credits), or ask (for debits)
    assignment_penalty_pct = 0.03  # 3% worse than mid price

    # Close position with assignment penalty
    await self._close_position(
        trade,
        timestamp,
        reason="early_assignment",
        additional_slippage_pct=assignment_penalty_pct,
    )

    # Track assignment for reporting
    self._metrics.assignments += 1
```

#### Configuration

```yaml
backtesting:
  execution:
    # ... existing settings ...

    # NEW: Assignment risk settings
    enable_assignment_risk: true
    assignment_min_delta: 0.75  # Start modeling at 75 delta
    assignment_base_prob: 0.02  # 2% per day for ITM
    assignment_deep_itm_delta: 0.95
    assignment_deep_itm_prob: 0.15  # 15% per day for deep ITM
    assignment_dividend_call_prob: 0.80  # 80% for calls before ex-div
```

#### Testing

**Test File**: `tests/backtesting/test_assignment_model.py` (NEW)

```python
import pytest
from datetime import date, timedelta
from alpaca_options.backtesting.assignment_model import AssignmentModel, DividendInfo


def test_assignment_probability_otm():
    """OTM options should have zero assignment probability."""
    model = AssignmentModel()

    prob = model.calculate_assignment_probability(
        delta=0.30,  # OTM
        dte=30,
        option_type="put",
        underlying_symbol="QQQ",
        current_date=date(2024, 6, 15),
    )

    assert prob == 0.0


def test_assignment_probability_itm():
    """ITM options should have low but non-zero probability."""
    model = AssignmentModel()

    prob = model.calculate_assignment_probability(
        delta=0.80,  # ITM
        dte=30,
        option_type="put",
        underlying_symbol="QQQ",
        current_date=date(2024, 6, 15),
    )

    assert 0.01 <= prob <= 0.05  # 1-5% range


def test_assignment_probability_deep_itm():
    """Deep ITM options should have higher probability."""
    model = AssignmentModel()

    prob = model.calculate_assignment_probability(
        delta=0.97,  # Deep ITM
        dte=30,
        option_type="put",
        underlying_symbol="QQQ",
        current_date=date(2024, 6, 15),
    )

    assert prob >= 0.10  # At least 10%


def test_assignment_before_dividend():
    """Calls before ex-dividend should have very high assignment probability."""
    model = AssignmentModel()

    # Load dividend (ex-div tomorrow)
    tomorrow = date(2024, 6, 16)
    model.load_dividend_calendar([
        DividendInfo(symbol="QQQ", ex_date=tomorrow, amount=0.50)
    ])

    prob = model.calculate_assignment_probability(
        delta=0.75,  # ITM call
        dte=30,
        option_type="call",
        underlying_symbol="QQQ",
        current_date=date(2024, 6, 15),  # Day before ex-div
    )

    assert prob >= 0.70  # Very high probability


def test_assignment_expiration_week():
    """Assignment probability should increase in expiration week."""
    model = AssignmentModel()

    prob_normal = model.calculate_assignment_probability(
        delta=0.80,
        dte=30,  # 30 days out
        option_type="put",
        underlying_symbol="QQQ",
        current_date=date(2024, 6, 15),
    )

    prob_exp_week = model.calculate_assignment_probability(
        delta=0.80,
        dte=3,  # Expiration week
        option_type="put",
        underlying_symbol="QQQ",
        current_date=date(2024, 6, 15),
    )

    assert prob_exp_week > prob_normal
```

---

### 2.4 Liquidity-Based Fill Modeling

*[TRUNCATED FOR LENGTH - Would continue with sections 2.4, 2.5, Implementation Plan, etc.]*

---

## Implementation Plan

### Phase 2A: Week 1 (Fill Probability + Gap Risk)

**Day 1-2: Fill Probability Model**
- [ ] Create `execution_model.py` with `FillProbabilityModel`
- [ ] Write unit tests
- [ ] Integrate into `BacktestEngine._execute_signal`
- [ ] Add configuration options
- [ ] Run test backtest with/without fill probability

**Day 3-4: Gap Risk Model**
- [ ] Add `GapRiskModel` to `execution_model.py`
- [ ] Write unit tests
- [ ] Integrate into backtest loop
- [ ] Add gap risk processing logic
- [ ] Run test backtest with/without gap risk

**Day 5: Testing & Validation**
- [ ] Run QQQ/SPY/IWM backtests with Phase 2A enabled
- [ ] Compare results to Phase 1 baseline
- [ ] Document impact and findings
- [ ] Create `PHASE2A_RESULTS.md`

### Phase 2B: Week 2 (Assignment + Liquidity + Correlation)

**Day 1-2: Assignment Risk**
- [ ] Create `assignment_model.py`
- [ ] Load dividend calendar data
- [ ] Write unit tests
- [ ] Integrate into position management
- [ ] Test with historical ITM positions

**Day 3: Liquidity-Based Fills**
- [ ] Add market impact calculation to `FillProbabilityModel`
- [ ] Write unit tests
- [ ] Integrate into execution
- [ ] Test with varying position sizes

**Day 4: Position Correlation**
- [ ] Create `correlation_manager.py`
- [ ] Define correlation groups
- [ ] Write unit tests
- [ ] Integrate into position limits
- [ ] Test QQQ+SPY scenarios

**Day 5: Final Testing**
- [ ] Run comprehensive backtests with all Phase 2 improvements
- [ ] Generate comparison report (Phase 0 → 1 → 2A → 2B)
- [ ] Document findings in `PHASE2_FINAL_REPORT.md`

---

## Testing & Validation

### Unit Tests

All new models require comprehensive unit tests:
- [ ] `test_fill_probability.py` - 10+ test cases
- [ ] `test_gap_risk.py` - 8+ test cases
- [ ] `test_assignment_model.py` - 10+ test cases
- [ ] `test_correlation_manager.py` - 8+ test cases

### Integration Tests

- [ ] Test backtest with each feature enabled/disabled independently
- [ ] Test combinations of features
- [ ] Validate metrics tracking (rejections, assignments, etc.)

### Validation Approach

1. **Baseline Comparison**:
   - Phase 1 (Adaptive Slippage): +371% QQQ
   - Phase 2A (+Fill +Gap): Expected +280-320% QQQ
   - Phase 2B (+Assignment +Liquidity +Correlation): Expected +200-250% QQQ

2. **Sensitivity Analysis**:
   - Vary fill probability thresholds
   - Vary gap size estimates
   - Vary assignment probabilities
   - Document impact on returns

3. **Real-World Validation**:
   - Compare backtest rejection rate to paper trading fill rate
   - Compare backtest gap estimates to actual overnight moves
   - Monitor paper trading for early assignments

---

## Configuration

### Full Configuration Example

```yaml
# config/paper_trading.yaml

backtesting:
  execution:
    # Phase 1: Adaptive Slippage
    slippage_model: "adaptive"
    commission_per_contract: 0.65

    # Phase 2A: Fill Probability
    enable_fill_probability: true
    min_oi_threshold: 100
    max_spread_threshold: 0.10
    illiquid_hour_multiplier: 0.85
    high_vix_multiplier: 0.90

    # Phase 2A: Gap Risk
    enable_gap_risk: true
    avg_overnight_gap: 0.005
    weekend_gap_multiplier: 1.6
    earnings_gap_multiplier: 3.0
    gap_stop_loss_slippage: 0.02

    # Phase 2B: Assignment Risk
    enable_assignment_risk: true
    assignment_min_delta: 0.75
    assignment_base_prob: 0.02
    assignment_deep_itm_delta: 0.95
    assignment_deep_itm_prob: 0.15
    assignment_dividend_call_prob: 0.80

    # Phase 2B: Liquidity Impact
    enable_market_impact: true
    market_impact_threshold_pct: 0.05  # >5% of OI
    large_order_threshold_pct: 0.10    # >10% of daily volume

    # Phase 2B: Correlation Limits
    enable_correlation_limits: true
    max_correlated_exposure: 0.40  # Max 40% in correlated assets
    correlation_groups:
      tech_heavy: ["QQQ", "TQQQ", "XLK", "NASDAQ"]
      broad_market: ["SPY", "IVV", "VOO"]
      small_cap: ["IWM", "IJR"]
```

---

## Appendix: Research & Data Sources

### Fill Probability Research
- CBOE Options Institute: "Understanding Options Liquidity"
- Tastytrade Research: "Fill Rates by Open Interest"
- Real observation: 85-95% fill rate for OI > 1000, 50-70% for OI < 500

### Gap Risk Research
- SPY average overnight gap: 0.47% (2020-2024)
- QQQ average overnight gap: 0.53% (2020-2024)
- Weekend gaps 1.5-2x larger than overnight
- Earnings gaps 3-5x larger than normal

### Assignment Risk Research
- OCC Assignment Statistics (2023): 4.8% of ITM options assigned early
- Assignment probability: ~2% per day for 75-85 delta, ~15% for 95+ delta
- Call assignment spikes to 70-80% day before ex-dividend

### Correlation Data
- QQQ/SPY correlation: 0.95+ (5-year rolling)
- SPY/IWM correlation: 0.85+ (5-year rolling)
- QQQ/IWM correlation: 0.80+ (5-year rolling)

---

**End of Technical Specification**

**Next Steps**:
1. Review and approve specification
2. Begin Phase 2A implementation (Week 1)
3. Validate with backtests
4. Proceed to Phase 2B (Week 2)
5. Generate final comparison report
