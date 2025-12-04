"""Base screener classes and interfaces."""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ScreenerType(Enum):
    """Types of screeners available."""

    TECHNICAL = "technical"
    OPTIONS = "options"
    HYBRID = "hybrid"


@dataclass
class ScreeningCriteria:
    """Configuration for screening filters.

    Technical Filters:
        min_price: Minimum stock price
        max_price: Maximum stock price
        min_volume: Minimum average daily volume
        min_dollar_volume: Minimum daily dollar volume (price * volume)
        rsi_oversold: RSI threshold for oversold (buy signals)
        rsi_overbought: RSI threshold for overbought (sell signals)
        rsi_period: Period for RSI calculation
        above_sma: Stock must be above this SMA (e.g., 50, 200)
        below_sma: Stock must be below this SMA
        min_atr_percent: Minimum ATR as percentage of price (volatility)
        max_atr_percent: Maximum ATR as percentage of price

    Options Filters:
        min_option_volume: Minimum daily option volume
        min_open_interest: Minimum open interest across chain
        max_bid_ask_spread_percent: Maximum bid-ask spread as percentage
        min_iv_rank: Minimum IV rank (0-100)
        max_iv_rank: Maximum IV rank (0-100)
        has_weekly_options: Must have weekly expirations
        min_expirations: Minimum number of available expirations
    """

    # Price filters
    min_price: float = 10.0
    max_price: float = 500.0

    # Volume filters
    min_volume: int = 500_000
    min_dollar_volume: float = 10_000_000.0

    # Technical filters
    rsi_oversold: Optional[float] = None  # e.g., 30 for oversold
    rsi_overbought: Optional[float] = None  # e.g., 70 for overbought
    rsi_period: int = 14
    above_sma: Optional[int] = None  # e.g., 50 or 200
    below_sma: Optional[int] = None
    min_atr_percent: Optional[float] = None
    max_atr_percent: Optional[float] = None

    # Options filters
    min_option_volume: int = 1000
    min_open_interest: int = 500
    max_bid_ask_spread_percent: float = 5.0
    min_iv_rank: Optional[float] = None
    max_iv_rank: Optional[float] = None
    has_weekly_options: bool = False
    min_expirations: int = 3

    def to_dict(self) -> dict[str, Any]:
        """Convert criteria to dictionary."""
        return {
            "min_price": self.min_price,
            "max_price": self.max_price,
            "min_volume": self.min_volume,
            "min_dollar_volume": self.min_dollar_volume,
            "rsi_oversold": self.rsi_oversold,
            "rsi_overbought": self.rsi_overbought,
            "rsi_period": self.rsi_period,
            "above_sma": self.above_sma,
            "below_sma": self.below_sma,
            "min_atr_percent": self.min_atr_percent,
            "max_atr_percent": self.max_atr_percent,
            "min_option_volume": self.min_option_volume,
            "min_open_interest": self.min_open_interest,
            "max_bid_ask_spread_percent": self.max_bid_ask_spread_percent,
            "min_iv_rank": self.min_iv_rank,
            "max_iv_rank": self.max_iv_rank,
            "has_weekly_options": self.has_weekly_options,
            "min_expirations": self.min_expirations,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScreeningCriteria":
        """Create criteria from dictionary."""
        return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})


@dataclass
class ScreenerResult:
    """Result from screening a single symbol."""

    symbol: str
    passed: bool
    score: float = 0.0  # Overall score (0-100)
    timestamp: datetime = field(default_factory=datetime.now)

    # Price data
    price: Optional[float] = None
    volume: Optional[int] = None
    dollar_volume: Optional[float] = None

    # Technical data
    rsi: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    atr: Optional[float] = None
    atr_percent: Optional[float] = None

    # MACD indicator
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None

    # Bollinger Bands
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    bb_position: Optional[float] = None  # % position within bands (0-100)

    # Stochastic Oscillator
    stoch_k: Optional[float] = None
    stoch_d: Optional[float] = None

    # Rate of Change
    roc: Optional[float] = None

    # Options data
    option_volume: Optional[int] = None
    total_open_interest: Optional[int] = None
    avg_bid_ask_spread: Optional[float] = None
    implied_volatility: Optional[float] = None
    iv_rank: Optional[float] = None
    num_expirations: Optional[int] = None
    has_weeklies: Optional[bool] = None

    # Filter results (which filters passed/failed)
    filter_results: dict[str, bool] = field(default_factory=dict)

    # Signal direction for directional screeners
    signal: Optional[str] = None  # "bullish", "bearish", "neutral"

    def __repr__(self) -> str:
        return (
            f"ScreenerResult(symbol={self.symbol}, passed={self.passed}, "
            f"score={self.score:.1f}, signal={self.signal})"
        )


@dataclass
class ScanResults:
    """Aggregated results from a screening scan."""

    screener_type: ScreenerType
    timestamp: datetime
    criteria: ScreeningCriteria
    total_scanned: int
    total_passed: int
    results: list[ScreenerResult]
    scan_duration_seconds: float = 0.0

    @property
    def passed_symbols(self) -> list[str]:
        """Get list of symbols that passed screening."""
        return [r.symbol for r in self.results if r.passed]

    @property
    def bullish_symbols(self) -> list[str]:
        """Get symbols with bullish signals."""
        return [r.symbol for r in self.results if r.passed and r.signal == "bullish"]

    @property
    def bearish_symbols(self) -> list[str]:
        """Get symbols with bearish signals."""
        return [r.symbol for r in self.results if r.passed and r.signal == "bearish"]

    def top_results(self, n: int = 10) -> list[ScreenerResult]:
        """Get top N results by score."""
        sorted_results = sorted(
            [r for r in self.results if r.passed],
            key=lambda x: x.score,
            reverse=True,
        )
        return sorted_results[:n]


class BaseScreener(ABC):
    """Abstract base class for stock screeners.

    Screeners scan a universe of symbols and filter them based on
    various criteria (technical, options-based, or hybrid).
    """

    def __init__(
        self,
        criteria: Optional[ScreeningCriteria] = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        """Initialize the screener.

        Args:
            criteria: Screening criteria to apply.
            cache_ttl_seconds: How long to cache results (default 5 minutes).
        """
        self.criteria = criteria or ScreeningCriteria()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[datetime, ScreenerResult]] = {}
        self._last_scan: Optional[ScanResults] = None

    @property
    @abstractmethod
    def screener_type(self) -> ScreenerType:
        """Return the type of this screener."""
        pass

    @abstractmethod
    async def screen_symbol(self, symbol: str) -> ScreenerResult:
        """Screen a single symbol.

        Args:
            symbol: Stock symbol to screen.

        Returns:
            ScreenerResult with pass/fail and metrics.
        """
        pass

    async def scan(
        self,
        symbols: list[str],
        max_results: Optional[int] = None,
    ) -> ScanResults:
        """Scan multiple symbols and return results.

        Args:
            symbols: List of symbols to scan.
            max_results: Maximum number of passing results to return.

        Returns:
            ScanResults with all screening results.
        """
        import time

        start_time = time.time()
        results: list[ScreenerResult] = []

        logger.info(
            f"Starting {self.screener_type.value} scan of {len(symbols)} symbols"
        )

        for symbol in symbols:
            try:
                # Check cache first
                cached = self._get_cached(symbol)
                if cached:
                    results.append(cached)
                    continue

                result = await self.screen_symbol(symbol)
                self._cache_result(symbol, result)
                results.append(result)

            except Exception as e:
                logger.warning(f"Error screening {symbol}: {e}")
                results.append(
                    ScreenerResult(symbol=symbol, passed=False, score=0.0)
                )

        # Sort by score and limit results
        passed_results = [r for r in results if r.passed]
        passed_results.sort(key=lambda x: x.score, reverse=True)

        if max_results:
            passed_results = passed_results[:max_results]
            # Update results to only include top N passed plus all failed
            failed_results = [r for r in results if not r.passed]
            results = passed_results + failed_results

        duration = time.time() - start_time

        scan_results = ScanResults(
            screener_type=self.screener_type,
            timestamp=datetime.now(),
            criteria=self.criteria,
            total_scanned=len(symbols),
            total_passed=len(passed_results),
            results=results,
            scan_duration_seconds=duration,
        )

        self._last_scan = scan_results

        logger.info(
            f"Scan complete: {scan_results.total_passed}/{scan_results.total_scanned} "
            f"passed in {duration:.2f}s"
        )

        return scan_results

    def _get_cached(self, symbol: str) -> Optional[ScreenerResult]:
        """Get cached result if still valid."""
        if symbol not in self._cache:
            return None

        cached_time, result = self._cache[symbol]
        age = (datetime.now() - cached_time).total_seconds()

        if age < self.cache_ttl_seconds:
            return result

        # Cache expired
        del self._cache[symbol]
        return None

    def _cache_result(self, symbol: str, result: ScreenerResult) -> None:
        """Cache a screening result."""
        self._cache[symbol] = (datetime.now(), result)

    def clear_cache(self) -> None:
        """Clear the results cache."""
        self._cache.clear()

    def update_criteria(self, criteria: ScreeningCriteria) -> None:
        """Update screening criteria and clear cache."""
        self.criteria = criteria
        self.clear_cache()

    @property
    def last_scan(self) -> Optional[ScanResults]:
        """Get the last scan results."""
        return self._last_scan
