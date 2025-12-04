"""Reusable filter functions for screening criteria."""

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    """Calculate the Relative Strength Index (RSI).

    Args:
        prices: Series of closing prices.
        period: RSI period (default 14).

    Returns:
        Current RSI value (0-100).
    """
    if len(prices) < period + 1:
        return 50.0  # Neutral if not enough data

    delta = prices.diff()
    gains = delta.where(delta > 0, 0.0)
    losses = (-delta).where(delta < 0, 0.0)

    avg_gain = gains.rolling(window=period, min_periods=period).mean()
    avg_loss = losses.rolling(window=period, min_periods=period).mean()

    # Use Wilder's smoothing method
    for i in range(period, len(gains)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gains.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + losses.iloc[i]) / period

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else 50.0


def calculate_sma(prices: pd.Series, period: int) -> float:
    """Calculate Simple Moving Average.

    Args:
        prices: Series of closing prices.
        period: SMA period.

    Returns:
        Current SMA value.
    """
    if len(prices) < period:
        return float(prices.mean())

    return float(prices.rolling(window=period).mean().iloc[-1])


def calculate_ema(prices: pd.Series, period: int) -> float:
    """Calculate Exponential Moving Average.

    Args:
        prices: Series of closing prices.
        period: EMA period.

    Returns:
        Current EMA value.
    """
    if len(prices) < period:
        return float(prices.mean())

    return float(prices.ewm(span=period, adjust=False).mean().iloc[-1])


def calculate_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> float:
    """Calculate Average True Range (ATR).

    Args:
        high: Series of high prices.
        low: Series of low prices.
        close: Series of closing prices.
        period: ATR period.

    Returns:
        Current ATR value.
    """
    if len(close) < period + 1:
        return float(high.iloc[-1] - low.iloc[-1])

    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = abs(high - prev_close)
    tr3 = abs(low - prev_close)

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()

    return float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else float(true_range.iloc[-1])


def calculate_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
) -> float:
    """Calculate Volume Weighted Average Price (VWAP).

    Args:
        high: Series of high prices.
        low: Series of low prices.
        close: Series of closing prices.
        volume: Series of volume.

    Returns:
        VWAP value.
    """
    typical_price = (high + low + close) / 3
    vwap = (typical_price * volume).cumsum() / volume.cumsum()
    return float(vwap.iloc[-1])


def calculate_bollinger_bands(
    prices: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[float, float, float]:
    """Calculate Bollinger Bands.

    Args:
        prices: Series of closing prices.
        period: SMA period for middle band.
        num_std: Number of standard deviations for bands.

    Returns:
        Tuple of (upper_band, middle_band, lower_band).
    """
    if len(prices) < period:
        mid = float(prices.mean())
        std = float(prices.std())
        return mid + num_std * std, mid, mid - num_std * std

    middle = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()

    upper = middle + (std * num_std)
    lower = middle - (std * num_std)

    return (
        float(upper.iloc[-1]),
        float(middle.iloc[-1]),
        float(lower.iloc[-1]),
    )


def calculate_macd(
    prices: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[float, float, float]:
    """Calculate MACD indicator.

    Args:
        prices: Series of closing prices.
        fast_period: Fast EMA period.
        slow_period: Slow EMA period.
        signal_period: Signal line period.

    Returns:
        Tuple of (macd_line, signal_line, histogram).
    """
    if len(prices) < slow_period:
        return 0.0, 0.0, 0.0

    fast_ema = prices.ewm(span=fast_period, adjust=False).mean()
    slow_ema = prices.ewm(span=slow_period, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line

    return (
        float(macd_line.iloc[-1]),
        float(signal_line.iloc[-1]),
        float(histogram.iloc[-1]),
    )


def calculate_stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[float, float]:
    """Calculate Stochastic Oscillator.

    Args:
        high: Series of high prices.
        low: Series of low prices.
        close: Series of closing prices.
        k_period: %K period.
        d_period: %D smoothing period.

    Returns:
        Tuple of (%K, %D).
    """
    if len(close) < k_period:
        return 50.0, 50.0

    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()

    k = 100 * (close - lowest_low) / (highest_high - lowest_low)
    d = k.rolling(window=d_period).mean()

    k_val = float(k.iloc[-1]) if not pd.isna(k.iloc[-1]) else 50.0
    d_val = float(d.iloc[-1]) if not pd.isna(d.iloc[-1]) else 50.0

    return k_val, d_val


def calculate_average_volume(volume: pd.Series, period: int = 20) -> float:
    """Calculate average volume over a period.

    Args:
        volume: Series of volume data.
        period: Averaging period.

    Returns:
        Average volume.
    """
    if len(volume) < period:
        return float(volume.mean())

    return float(volume.rolling(window=period).mean().iloc[-1])


def calculate_dollar_volume(price: float, volume: int) -> float:
    """Calculate dollar volume.

    Args:
        price: Current price.
        volume: Current volume.

    Returns:
        Dollar volume (price * volume).
    """
    return price * volume


def calculate_price_change_percent(
    prices: pd.Series,
    period: int = 1,
) -> float:
    """Calculate percentage price change over period.

    Args:
        prices: Series of closing prices.
        period: Number of periods to look back.

    Returns:
        Percentage change.
    """
    if len(prices) <= period:
        return 0.0

    old_price = prices.iloc[-period - 1]
    new_price = prices.iloc[-1]

    if old_price == 0:
        return 0.0

    return ((new_price - old_price) / old_price) * 100


def calculate_volatility(
    prices: pd.Series,
    period: int = 20,
    annualize: bool = True,
) -> float:
    """Calculate historical volatility (standard deviation of returns).

    Args:
        prices: Series of closing prices.
        period: Period for calculation.
        annualize: Whether to annualize (assume 252 trading days).

    Returns:
        Volatility as decimal (e.g., 0.25 = 25%).
    """
    if len(prices) < period + 1:
        return 0.0

    returns = prices.pct_change().dropna()
    volatility = returns.rolling(window=period).std().iloc[-1]

    if annualize:
        volatility *= np.sqrt(252)

    return float(volatility) if not pd.isna(volatility) else 0.0


def calculate_roc(
    prices: pd.Series,
    period: int = 14,
) -> float:
    """Calculate Rate of Change (ROC) indicator.

    ROC = ((Current Price - Price N periods ago) / Price N periods ago) * 100

    Args:
        prices: Series of closing prices.
        period: Number of periods to look back.

    Returns:
        ROC percentage.
    """
    if len(prices) <= period:
        return 0.0

    old_price = prices.iloc[-period - 1]
    current_price = prices.iloc[-1]

    if old_price == 0:
        return 0.0

    roc = ((current_price - old_price) / old_price) * 100
    return float(roc)


def is_above_sma(price: float, sma: float) -> bool:
    """Check if price is above SMA."""
    return price > sma


def is_below_sma(price: float, sma: float) -> bool:
    """Check if price is below SMA."""
    return price < sma


def is_oversold(rsi: float, threshold: float = 30.0) -> bool:
    """Check if RSI indicates oversold condition."""
    return rsi < threshold


def is_overbought(rsi: float, threshold: float = 70.0) -> bool:
    """Check if RSI indicates overbought condition."""
    return rsi > threshold


def is_in_price_range(
    price: float,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
) -> bool:
    """Check if price is within specified range."""
    if min_price is not None and price < min_price:
        return False
    if max_price is not None and price > max_price:
        return False
    return True


def meets_volume_threshold(
    volume: int,
    min_volume: Optional[int] = None,
) -> bool:
    """Check if volume meets minimum threshold."""
    if min_volume is None:
        return True
    return volume >= min_volume


def meets_dollar_volume_threshold(
    dollar_volume: float,
    min_dollar_volume: Optional[float] = None,
) -> bool:
    """Check if dollar volume meets minimum threshold."""
    if min_dollar_volume is None:
        return True
    return dollar_volume >= min_dollar_volume


def calculate_bid_ask_spread_percent(bid: float, ask: float) -> float:
    """Calculate bid-ask spread as percentage of mid price.

    Args:
        bid: Bid price.
        ask: Ask price.

    Returns:
        Spread as percentage.
    """
    if bid <= 0 or ask <= 0:
        return 100.0  # Invalid spread

    mid = (bid + ask) / 2
    if mid == 0:
        return 100.0

    return ((ask - bid) / mid) * 100


def is_tight_spread(
    bid: float,
    ask: float,
    max_spread_percent: float = 5.0,
) -> bool:
    """Check if bid-ask spread is tight enough."""
    spread_pct = calculate_bid_ask_spread_percent(bid, ask)
    return spread_pct <= max_spread_percent


def calculate_iv_rank(
    current_iv: float,
    iv_low: float,
    iv_high: float,
) -> float:
    """Calculate IV Rank.

    IV Rank = (Current IV - 52w Low IV) / (52w High IV - 52w Low IV) * 100

    Args:
        current_iv: Current implied volatility.
        iv_low: 52-week low IV.
        iv_high: 52-week high IV.

    Returns:
        IV Rank (0-100).
    """
    if iv_high == iv_low:
        return 50.0

    return ((current_iv - iv_low) / (iv_high - iv_low)) * 100


def calculate_iv_percentile(
    current_iv: float,
    historical_ivs: list[float],
) -> float:
    """Calculate IV Percentile.

    Percentage of days in past year when IV was lower than current.

    Args:
        current_iv: Current implied volatility.
        historical_ivs: List of historical IV values.

    Returns:
        IV Percentile (0-100).
    """
    if not historical_ivs:
        return 50.0

    below_count = sum(1 for iv in historical_ivs if iv < current_iv)
    return (below_count / len(historical_ivs)) * 100


def score_technical_setup(
    rsi: Optional[float] = None,
    price_vs_sma50: Optional[float] = None,  # % above/below SMA50
    price_vs_sma200: Optional[float] = None,
    volume_ratio: Optional[float] = None,  # Current vol / avg vol
    atr_percent: Optional[float] = None,
) -> float:
    """Calculate a composite technical score (0-100).

    Higher scores indicate better setups for options trading.

    Args:
        rsi: Current RSI value.
        price_vs_sma50: Percentage above/below 50 SMA.
        price_vs_sma200: Percentage above/below 200 SMA.
        volume_ratio: Current volume / average volume.
        atr_percent: ATR as percentage of price.

    Returns:
        Composite score (0-100).
    """
    score = 50.0  # Start neutral
    weights_sum = 0

    # RSI extremes are good for mean reversion plays
    if rsi is not None:
        weights_sum += 1
        if rsi < 30:
            score += 15  # Oversold - bullish opportunity
        elif rsi > 70:
            score += 15  # Overbought - bearish opportunity
        elif 40 <= rsi <= 60:
            score += 5  # Neutral - good for non-directional

    # Price relative to moving averages
    if price_vs_sma50 is not None:
        weights_sum += 0.5
        # Prefer stocks near (not far from) their averages
        distance = abs(price_vs_sma50)
        if distance < 3:
            score += 10  # Very close to SMA
        elif distance < 10:
            score += 5

    # Volume confirmation
    if volume_ratio is not None:
        weights_sum += 0.5
        if volume_ratio > 1.5:
            score += 10  # Higher than normal volume
        elif volume_ratio > 1.0:
            score += 5

    # Volatility (ATR) - we want some but not too much
    if atr_percent is not None:
        weights_sum += 0.5
        if 1.0 <= atr_percent <= 4.0:
            score += 10  # Good volatility range
        elif 0.5 <= atr_percent <= 6.0:
            score += 5

    # Normalize to 0-100 range
    if weights_sum > 0:
        max_possible = 50 + (35 * weights_sum / 2.5)  # Rough max
        score = min(100, (score / max_possible) * 100)

    return max(0, min(100, score))


def score_options_setup(
    iv_rank: Optional[float] = None,
    open_interest: Optional[int] = None,
    bid_ask_spread_pct: Optional[float] = None,
    num_expirations: Optional[int] = None,
) -> float:
    """Calculate a composite options score (0-100).

    Higher scores indicate better options trading conditions.

    Args:
        iv_rank: IV Rank (0-100).
        open_interest: Total open interest.
        bid_ask_spread_pct: Average bid-ask spread percentage.
        num_expirations: Number of available expirations.

    Returns:
        Composite score (0-100).
    """
    score = 50.0
    factors = 0

    # IV Rank - high IV good for selling premium
    if iv_rank is not None:
        factors += 1
        if iv_rank > 50:
            score += (iv_rank - 50) * 0.3  # Up to +15 for high IV
        else:
            score += 5  # Low IV still tradeable

    # Open Interest - liquidity
    if open_interest is not None:
        factors += 1
        if open_interest > 10000:
            score += 15
        elif open_interest > 5000:
            score += 10
        elif open_interest > 1000:
            score += 5

    # Bid-ask spread - tighter is better
    if bid_ask_spread_pct is not None:
        factors += 1
        if bid_ask_spread_pct < 1:
            score += 15  # Very tight
        elif bid_ask_spread_pct < 3:
            score += 10
        elif bid_ask_spread_pct < 5:
            score += 5
        elif bid_ask_spread_pct > 10:
            score -= 10  # Too wide

    # Number of expirations - more flexibility
    if num_expirations is not None:
        factors += 0.5
        if num_expirations >= 8:
            score += 10  # Many expirations (weeklies)
        elif num_expirations >= 4:
            score += 5

    # Normalize
    if factors > 0:
        score = min(100, max(0, score))

    return score
