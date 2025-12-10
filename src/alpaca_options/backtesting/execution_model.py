"""Execution realism models for backtesting.

This module contains models that simulate real-world execution constraints:
- Fill Probability: Not all orders fill in real markets
- Gap Risk: Markets are closed 70% of the time
- Market Impact: Large orders get worse fills

Phase 2A Implementation (High-Priority Realism Improvements)
"""

import random
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional
import math
import logging

logger = logging.getLogger(__name__)


@dataclass
class FillContext:
    """Context for fill probability calculation.

    Contains all market conditions needed to determine if an order will fill.
    """

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

    Key Insights:
    - OI < 50: Reject (too illiquid)
    - OI 50-200: 50% fill rate
    - OI 200-500: 75% fill rate
    - OI 500-1000: 90% fill rate
    - OI > 1000: 95%+ fill rate (with spread < 5%)

    - Spread > 10%: Reject (too wide)
    - Spread 7-10%: 60% fill rate
    - Spread 5-7%: 80% fill rate
    - Spread 3-5%: 95% fill rate
    - Spread < 3%: No penalty

    - Market open/close hours: 15% penalty
    - High VIX (> 30): 10% penalty
    - Very high VIX (> 40): 20% penalty
    - Closing orders: 10% bonus (easier to fill)
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
            logger.debug(
                f"Order rejected: OI too low ({context.open_interest} < {self.min_oi_threshold})"
            )
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
            logger.debug(
                f"Order rejected: Spread too wide ({context.bid_ask_spread_pct:.1%} > {self.max_spread_threshold:.1%})"
            )
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
        if context.vix > 40:
            prob *= 0.80  # 20% penalty for extreme VIX
        elif context.vix > 30:
            prob *= self.high_vix_multiplier  # 10% penalty

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

    def will_fill(
        self, context: FillContext, random_seed: Optional[float] = None
    ) -> bool:
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
        elif prob >= 1.0:
            return True
        else:
            rand_val = random_seed if random_seed is not None else random.random()
            return rand_val < prob


class GapRiskModel:
    """Models overnight and weekend gap risk for options positions.

    Research basis:
    - Average overnight gap: ~0.5% for SPY/QQQ
    - Weekend gaps average 0.8% (more time for news)
    - Options have gamma risk - gaps are magnified by delta changes
    - Stop losses cannot be honored during market close

    Key Insights:
    - Markets closed ~70% of time (16:00 - 9:30 next day, weekends, holidays)
    - Overnight (16 hours): ~0.5% average gap
    - Weekend (64 hours): ~0.8% average gap (1.6x overnight)
    - Earnings gaps: 3x normal gaps
    - Stop losses can't execute during close -> worse fills on reopen
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
        position_pnl_pct: float,
        position_notional: float,
        timestamp: datetime,
        underlying_volatility: float,
        is_earnings: bool = False,
    ) -> float:
        """Estimate potential gap impact on position P&L.

        Args:
            position_pnl_pct: Current P&L as % of initial credit (e.g., -2.0 = lost 200%)
            position_notional: Notional value of position
            timestamp: Current timestamp
            underlying_volatility: Underlying IV (for scaling)
            is_earnings: Whether this is an earnings gap

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
        if position_pnl_pct < -1.0:  # Lost more than 100% (2x credit)
            # Additional slippage from gap
            gap_slippage = position_notional * self.stop_loss_slippage
            logger.warning(
                f"Gap risk triggered: Position P&L {position_pnl_pct:.1%}, "
                f"adding ${gap_slippage:.2f} gap slippage"
            )
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
