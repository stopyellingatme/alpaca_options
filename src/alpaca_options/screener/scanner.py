"""Main scanner orchestrator combining multiple screeners."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, TYPE_CHECKING

from alpaca_options.screener.base import (
    ScreenerResult,
    ScreenerType,
    ScreeningCriteria,
    ScanResults,
)
from alpaca_options.screener.technical import TechnicalScreener
from alpaca_options.screener.options import OptionsScreener
from alpaca_options.screener.universes import (
    SymbolUniverse,
    UniverseType,
    get_universe,
    get_options_friendly_symbols,
)

if TYPE_CHECKING:
    from alpaca_options.screener.iv_data import IVDataManager

logger = logging.getLogger(__name__)


class ScanMode(Enum):
    """Scanning mode determining which screeners to use."""

    TECHNICAL_ONLY = "technical_only"
    OPTIONS_ONLY = "options_only"
    HYBRID = "hybrid"  # Both technical and options


@dataclass
class ScannerConfig:
    """Configuration for the scanner."""

    # Scan mode
    mode: ScanMode = ScanMode.HYBRID

    # Universe selection
    universe_type: UniverseType = UniverseType.OPTIONS_FRIENDLY
    custom_symbols: list[str] = field(default_factory=list)

    # Result limits
    max_results: int = 20
    min_combined_score: float = 50.0

    # Weights for hybrid scoring
    technical_weight: float = 0.5
    options_weight: float = 0.5

    # Filtering
    require_options: bool = True  # Must have tradeable options
    require_signal: bool = False  # Must have bullish/bearish signal

    # Refresh settings
    auto_refresh_seconds: int = 300  # 5 minutes
    cache_ttl_seconds: int = 300


@dataclass
class CombinedResult:
    """Combined result from multiple screeners."""

    symbol: str
    combined_score: float
    technical_result: Optional[ScreenerResult] = None
    options_result: Optional[ScreenerResult] = None
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def passed(self) -> bool:
        """Check if passed all required screenings."""
        if self.technical_result and not self.technical_result.passed:
            return False
        if self.options_result and not self.options_result.passed:
            return False
        return True

    @property
    def signal(self) -> Optional[str]:
        """Get signal from technical screener."""
        if self.technical_result:
            return self.technical_result.signal
        return None

    @property
    def price(self) -> Optional[float]:
        """Get current price."""
        if self.technical_result:
            return self.technical_result.price
        return None

    @property
    def rsi(self) -> Optional[float]:
        """Get RSI value."""
        if self.technical_result:
            return self.technical_result.rsi
        return None

    @property
    def implied_volatility(self) -> Optional[float]:
        """Get IV from options screener."""
        if self.options_result:
            return self.options_result.implied_volatility
        return None


class Scanner:
    """Main scanner orchestrating multiple screeners.

    Combines technical and options screening to find
    the best opportunities for options trading.
    """

    def __init__(
        self,
        trading_client,
        stock_data_client,
        options_data_client,
        config: Optional[ScannerConfig] = None,
        criteria: Optional[ScreeningCriteria] = None,
        iv_data_manager: Optional["IVDataManager"] = None,
    ) -> None:
        """Initialize the scanner.

        Args:
            trading_client: Alpaca TradingClient.
            stock_data_client: Alpaca StockHistoricalDataClient.
            options_data_client: Alpaca OptionHistoricalDataClient.
            config: Scanner configuration.
            criteria: Screening criteria to apply.
            iv_data_manager: Optional IVDataManager for IV rank calculation.
        """
        self.config = config or ScannerConfig()
        self.criteria = criteria or ScreeningCriteria()
        self.iv_data_manager = iv_data_manager

        # Initialize screeners
        self._technical_screener = TechnicalScreener(
            data_client=stock_data_client,
            criteria=self.criteria,
            cache_ttl_seconds=self.config.cache_ttl_seconds,
        )

        self._options_screener = OptionsScreener(
            trading_client=trading_client,
            options_data_client=options_data_client,
            criteria=self.criteria,
            cache_ttl_seconds=self.config.cache_ttl_seconds,
            iv_data_manager=iv_data_manager,
        )

        # Results cache
        self._last_scan_time: Optional[datetime] = None
        self._last_results: list[CombinedResult] = []
        self._is_scanning = False

        # Log IV rank capability
        if iv_data_manager:
            cached_symbols = iv_data_manager.get_cached_symbols()
            logger.info(f"Scanner initialized with IV rank support ({len(cached_symbols)} symbols cached)")
        else:
            logger.info("Scanner initialized without IV rank support")

    @property
    def is_scanning(self) -> bool:
        """Check if a scan is in progress."""
        return self._is_scanning

    def get_universe(self) -> list[str]:
        """Get the symbol universe to scan.

        Returns:
            List of symbols to scan.
        """
        if self.config.custom_symbols:
            return self.config.custom_symbols

        universe = get_universe(self.config.universe_type)
        return list(universe.symbols)

    async def scan(
        self,
        symbols: Optional[list[str]] = None,
        mode: Optional[ScanMode] = None,
    ) -> list[CombinedResult]:
        """Run a full scan across all screeners.

        Args:
            symbols: Optional custom symbols (overrides config universe).
            mode: Optional mode override.

        Returns:
            List of CombinedResults sorted by score.
        """
        if self._is_scanning:
            logger.warning("Scan already in progress")
            return self._last_results

        self._is_scanning = True
        scan_mode = mode or self.config.mode
        scan_symbols = symbols or self.get_universe()

        logger.info(
            f"Starting {scan_mode.value} scan of {len(scan_symbols)} symbols"
        )

        try:
            results: list[CombinedResult] = []

            # Run appropriate screeners based on mode
            technical_results: dict[str, ScreenerResult] = {}
            options_results: dict[str, ScreenerResult] = {}

            if scan_mode in [ScanMode.TECHNICAL_ONLY, ScanMode.HYBRID]:
                tech_scan = await self._technical_screener.scan(
                    scan_symbols, max_results=None
                )
                technical_results = {r.symbol: r for r in tech_scan.results}

            if scan_mode in [ScanMode.OPTIONS_ONLY, ScanMode.HYBRID]:
                opts_scan = await self._options_screener.scan(
                    scan_symbols, max_results=None
                )
                options_results = {r.symbol: r for r in opts_scan.results}

            # Combine results
            all_symbols = set(technical_results.keys()) | set(options_results.keys())

            for symbol in all_symbols:
                tech = technical_results.get(symbol)
                opts = options_results.get(symbol)

                # Skip if doesn't meet requirements
                if self.config.require_options and not opts:
                    continue
                if self.config.require_options and opts and not opts.passed:
                    continue
                if self.config.require_signal and tech and not tech.signal:
                    continue

                # Calculate combined score
                combined_score = self._calculate_combined_score(tech, opts)

                if combined_score >= self.config.min_combined_score:
                    results.append(CombinedResult(
                        symbol=symbol,
                        combined_score=combined_score,
                        technical_result=tech,
                        options_result=opts,
                        timestamp=datetime.now(),
                    ))

            # Sort by score and limit results
            results.sort(key=lambda x: x.combined_score, reverse=True)
            results = results[:self.config.max_results]

            self._last_scan_time = datetime.now()
            self._last_results = results

            logger.info(f"Scan complete: {len(results)} opportunities found")

            return results

        finally:
            self._is_scanning = False

    def _calculate_combined_score(
        self,
        tech: Optional[ScreenerResult],
        opts: Optional[ScreenerResult],
    ) -> float:
        """Calculate combined score from individual screener scores.

        Args:
            tech: Technical screener result.
            opts: Options screener result.

        Returns:
            Combined score (0-100).
        """
        tech_score = tech.score if tech else 0
        opts_score = opts.score if opts else 0

        # Weight the scores
        if tech and opts:
            return (
                tech_score * self.config.technical_weight +
                opts_score * self.config.options_weight
            )
        elif tech:
            return tech_score
        elif opts:
            return opts_score
        else:
            return 0

    async def scan_bullish(
        self,
        symbols: Optional[list[str]] = None,
        max_results: int = 10,
    ) -> list[CombinedResult]:
        """Scan for bullish opportunities (oversold with good options).

        Args:
            symbols: Optional symbols to scan.
            max_results: Maximum results.

        Returns:
            List of bullish opportunities.
        """
        # Temporarily adjust criteria for oversold
        original_oversold = self.criteria.rsi_oversold
        self.criteria.rsi_oversold = 40  # More lenient for scan

        try:
            results = await self.scan(symbols, ScanMode.HYBRID)

            bullish = [
                r for r in results
                if r.signal == "bullish" or (r.rsi and r.rsi < 40)
            ]

            return bullish[:max_results]

        finally:
            self.criteria.rsi_oversold = original_oversold

    async def scan_bearish(
        self,
        symbols: Optional[list[str]] = None,
        max_results: int = 10,
    ) -> list[CombinedResult]:
        """Scan for bearish opportunities (overbought with good options).

        Args:
            symbols: Optional symbols to scan.
            max_results: Maximum results.

        Returns:
            List of bearish opportunities.
        """
        original_overbought = self.criteria.rsi_overbought
        self.criteria.rsi_overbought = 60  # More lenient for scan

        try:
            results = await self.scan(symbols, ScanMode.HYBRID)

            bearish = [
                r for r in results
                if r.signal == "bearish" or (r.rsi and r.rsi > 60)
            ]

            return bearish[:max_results]

        finally:
            self.criteria.rsi_overbought = original_overbought

    async def scan_high_iv(
        self,
        symbols: Optional[list[str]] = None,
        min_iv_rank: float = 50.0,
        max_results: int = 10,
    ) -> list[CombinedResult]:
        """Scan for high IV opportunities (good for selling premium).

        Args:
            symbols: Optional symbols to scan.
            min_iv_rank: Minimum IV rank.
            max_results: Maximum results.

        Returns:
            List of high IV opportunities.
        """
        results = await self.scan(symbols, ScanMode.OPTIONS_ONLY)

        high_iv = [
            r for r in results
            if r.options_result and r.options_result.iv_rank
            and r.options_result.iv_rank >= min_iv_rank
        ]

        high_iv.sort(
            key=lambda x: x.options_result.iv_rank if x.options_result else 0,
            reverse=True,
        )

        return high_iv[:max_results]

    async def quick_scan(
        self,
        symbols: Optional[list[str]] = None,
    ) -> list[str]:
        """Quick scan returning just symbols that pass.

        Args:
            symbols: Optional symbols to scan.

        Returns:
            List of symbols that passed screening.
        """
        results = await self.scan(symbols)
        return [r.symbol for r in results if r.passed]

    def get_cached_results(self) -> list[CombinedResult]:
        """Get cached results from last scan."""
        return self._last_results

    def get_cached_symbols(self) -> list[str]:
        """Get symbols from cached results."""
        return [r.symbol for r in self._last_results]

    def clear_cache(self) -> None:
        """Clear all caches."""
        self._technical_screener.clear_cache()
        self._options_screener.clear_cache()
        self._last_results = []
        self._last_scan_time = None

    def update_criteria(self, criteria: ScreeningCriteria) -> None:
        """Update screening criteria for all screeners."""
        self.criteria = criteria
        self._technical_screener.update_criteria(criteria)
        self._options_screener.update_criteria(criteria)

    def update_config(self, config: ScannerConfig) -> None:
        """Update scanner configuration."""
        self.config = config

    async def get_symbol_analysis(self, symbol: str) -> CombinedResult:
        """Get detailed analysis for a single symbol.

        Args:
            symbol: Symbol to analyze.

        Returns:
            CombinedResult with full analysis.
        """
        tech = await self._technical_screener.screen_symbol(symbol)
        opts = await self._options_screener.screen_symbol(symbol)

        combined_score = self._calculate_combined_score(tech, opts)

        return CombinedResult(
            symbol=symbol,
            combined_score=combined_score,
            technical_result=tech,
            options_result=opts,
            timestamp=datetime.now(),
        )


async def create_scanner_from_client(alpaca_client) -> Scanner:
    """Create a scanner from an AlpacaClient instance.

    Args:
        alpaca_client: AlpacaClient instance.

    Returns:
        Configured Scanner instance.
    """
    return Scanner(
        trading_client=alpaca_client.trading,
        stock_data_client=alpaca_client.stock_data,
        options_data_client=alpaca_client.option_data,
    )
