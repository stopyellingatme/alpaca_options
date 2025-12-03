"""Strategy criteria for filtering and conditional activation."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class StrategyCriteria:
    """Defines conditions under which a strategy should be active.

    Used to filter when strategies should generate signals based on
    market conditions, underlying characteristics, and time constraints.
    """

    # Implied Volatility conditions
    min_iv_rank: Optional[float] = None  # 0-100
    max_iv_rank: Optional[float] = None
    min_iv_percentile: Optional[float] = None  # 0-100
    max_iv_percentile: Optional[float] = None

    # Underlying price conditions
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    min_volume: Optional[int] = None
    min_market_cap: Optional[float] = None

    # Options liquidity conditions
    min_open_interest: Optional[int] = None
    max_bid_ask_spread_percent: Optional[float] = None  # Max spread as % of mid

    # Days to expiration constraints
    min_days_to_expiry: Optional[int] = None
    max_days_to_expiry: Optional[int] = None

    # Time-based conditions
    trading_hours_only: bool = True
    allowed_days: list[int] = field(default_factory=lambda: [0, 1, 2, 3, 4])  # Mon-Fri
    exclude_dates: list[datetime] = field(default_factory=list)  # Holidays, earnings, etc.

    # Technical conditions
    trend_direction: Optional[str] = None  # "bullish", "bearish", "neutral"
    min_atr_percentile: Optional[float] = None
    max_atr_percentile: Optional[float] = None

    # RSI conditions
    min_rsi: Optional[float] = None
    max_rsi: Optional[float] = None

    # Moving average conditions
    price_above_sma: Optional[int] = None  # Price must be above this SMA period
    price_below_sma: Optional[int] = None  # Price must be below this SMA period

    # Greeks constraints for the strategy
    min_delta: Optional[float] = None
    max_delta: Optional[float] = None
    min_theta: Optional[float] = None

    def evaluate(
        self,
        iv_rank: Optional[float] = None,
        iv_percentile: Optional[float] = None,
        price: Optional[float] = None,
        volume: Optional[int] = None,
        open_interest: Optional[int] = None,
        bid_ask_spread_percent: Optional[float] = None,
        days_to_expiry: Optional[int] = None,
        current_time: Optional[datetime] = None,
        rsi: Optional[float] = None,
        atr_percentile: Optional[float] = None,
        price_vs_sma: Optional[dict[int, str]] = None,  # {20: "above", 50: "below"}
    ) -> tuple[bool, list[str]]:
        """Evaluate if all criteria are met.

        Args:
            iv_rank: Current IV rank (0-100)
            iv_percentile: Current IV percentile (0-100)
            price: Current underlying price
            volume: Current trading volume
            open_interest: Options open interest
            bid_ask_spread_percent: Bid-ask spread as percentage
            days_to_expiry: Days until option expiration
            current_time: Current datetime
            rsi: Current RSI value
            atr_percentile: ATR percentile
            price_vs_sma: Dict mapping SMA period to "above"/"below"

        Returns:
            Tuple of (all_criteria_met, list_of_failed_criteria)
        """
        failed_criteria: list[str] = []

        # IV Rank checks
        if self.min_iv_rank is not None and iv_rank is not None:
            if iv_rank < self.min_iv_rank:
                failed_criteria.append(f"IV rank {iv_rank:.1f} below min {self.min_iv_rank}")

        if self.max_iv_rank is not None and iv_rank is not None:
            if iv_rank > self.max_iv_rank:
                failed_criteria.append(f"IV rank {iv_rank:.1f} above max {self.max_iv_rank}")

        # IV Percentile checks
        if self.min_iv_percentile is not None and iv_percentile is not None:
            if iv_percentile < self.min_iv_percentile:
                failed_criteria.append(
                    f"IV percentile {iv_percentile:.1f} below min {self.min_iv_percentile}"
                )

        if self.max_iv_percentile is not None and iv_percentile is not None:
            if iv_percentile > self.max_iv_percentile:
                failed_criteria.append(
                    f"IV percentile {iv_percentile:.1f} above max {self.max_iv_percentile}"
                )

        # Price checks
        if self.min_price is not None and price is not None:
            if price < self.min_price:
                failed_criteria.append(f"Price ${price:.2f} below min ${self.min_price}")

        if self.max_price is not None and price is not None:
            if price > self.max_price:
                failed_criteria.append(f"Price ${price:.2f} above max ${self.max_price}")

        # Volume check
        if self.min_volume is not None and volume is not None:
            if volume < self.min_volume:
                failed_criteria.append(f"Volume {volume} below min {self.min_volume}")

        # Open interest check
        if self.min_open_interest is not None and open_interest is not None:
            if open_interest < self.min_open_interest:
                failed_criteria.append(
                    f"Open interest {open_interest} below min {self.min_open_interest}"
                )

        # Bid-ask spread check
        if self.max_bid_ask_spread_percent is not None and bid_ask_spread_percent is not None:
            if bid_ask_spread_percent > self.max_bid_ask_spread_percent:
                failed_criteria.append(
                    f"Spread {bid_ask_spread_percent:.2f}% above max "
                    f"{self.max_bid_ask_spread_percent}%"
                )

        # DTE checks
        if self.min_days_to_expiry is not None and days_to_expiry is not None:
            if days_to_expiry < self.min_days_to_expiry:
                failed_criteria.append(
                    f"DTE {days_to_expiry} below min {self.min_days_to_expiry}"
                )

        if self.max_days_to_expiry is not None and days_to_expiry is not None:
            if days_to_expiry > self.max_days_to_expiry:
                failed_criteria.append(
                    f"DTE {days_to_expiry} above max {self.max_days_to_expiry}"
                )

        # Time-based checks
        if current_time is not None:
            if self.trading_hours_only:
                # Market hours: 9:30 AM - 4:00 PM ET
                hour = current_time.hour
                minute = current_time.minute
                time_minutes = hour * 60 + minute
                market_open = 9 * 60 + 30  # 9:30 AM
                market_close = 16 * 60  # 4:00 PM

                if not (market_open <= time_minutes < market_close):
                    failed_criteria.append("Outside trading hours")

            if current_time.weekday() not in self.allowed_days:
                failed_criteria.append(f"Day {current_time.strftime('%A')} not allowed")

            if current_time in self.exclude_dates:
                failed_criteria.append(f"Date {current_time.date()} is excluded")

        # RSI checks
        if self.min_rsi is not None and rsi is not None:
            if rsi < self.min_rsi:
                failed_criteria.append(f"RSI {rsi:.1f} below min {self.min_rsi}")

        if self.max_rsi is not None and rsi is not None:
            if rsi > self.max_rsi:
                failed_criteria.append(f"RSI {rsi:.1f} above max {self.max_rsi}")

        # ATR percentile checks
        if self.min_atr_percentile is not None and atr_percentile is not None:
            if atr_percentile < self.min_atr_percentile:
                failed_criteria.append(
                    f"ATR percentile {atr_percentile:.1f} below min {self.min_atr_percentile}"
                )

        if self.max_atr_percentile is not None and atr_percentile is not None:
            if atr_percentile > self.max_atr_percentile:
                failed_criteria.append(
                    f"ATR percentile {atr_percentile:.1f} above max {self.max_atr_percentile}"
                )

        # SMA checks
        if price_vs_sma is not None:
            if self.price_above_sma is not None:
                if price_vs_sma.get(self.price_above_sma) != "above":
                    failed_criteria.append(f"Price not above SMA({self.price_above_sma})")

            if self.price_below_sma is not None:
                if price_vs_sma.get(self.price_below_sma) != "below":
                    failed_criteria.append(f"Price not below SMA({self.price_below_sma})")

        return len(failed_criteria) == 0, failed_criteria

    def merge(self, other: "StrategyCriteria") -> "StrategyCriteria":
        """Merge two criteria, taking the more restrictive values.

        Args:
            other: Another StrategyCriteria to merge with.

        Returns:
            New StrategyCriteria with merged values.
        """
        return StrategyCriteria(
            min_iv_rank=max(
                self.min_iv_rank or 0, other.min_iv_rank or 0
            ) or None,
            max_iv_rank=min(
                self.max_iv_rank or 100, other.max_iv_rank or 100
            ) if self.max_iv_rank or other.max_iv_rank else None,
            min_iv_percentile=max(
                self.min_iv_percentile or 0, other.min_iv_percentile or 0
            ) or None,
            max_iv_percentile=min(
                self.max_iv_percentile or 100, other.max_iv_percentile or 100
            ) if self.max_iv_percentile or other.max_iv_percentile else None,
            min_price=max(
                self.min_price or 0, other.min_price or 0
            ) or None,
            max_price=min(
                self.max_price or float("inf"), other.max_price or float("inf")
            ) if self.max_price or other.max_price else None,
            min_volume=max(
                self.min_volume or 0, other.min_volume or 0
            ) or None,
            min_open_interest=max(
                self.min_open_interest or 0, other.min_open_interest or 0
            ) or None,
            max_bid_ask_spread_percent=min(
                self.max_bid_ask_spread_percent or float("inf"),
                other.max_bid_ask_spread_percent or float("inf"),
            ) if self.max_bid_ask_spread_percent or other.max_bid_ask_spread_percent else None,
            min_days_to_expiry=max(
                self.min_days_to_expiry or 0, other.min_days_to_expiry or 0
            ) or None,
            max_days_to_expiry=min(
                self.max_days_to_expiry or 365, other.max_days_to_expiry or 365
            ) if self.max_days_to_expiry or other.max_days_to_expiry else None,
            trading_hours_only=self.trading_hours_only or other.trading_hours_only,
            allowed_days=list(set(self.allowed_days) & set(other.allowed_days)),
            exclude_dates=list(set(self.exclude_dates) | set(other.exclude_dates)),
        )
