"""Technical analysis-based stock screener."""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from alpaca_options.screener.base import (
    BaseScreener,
    ScreenerResult,
    ScreenerType,
    ScreeningCriteria,
)
from alpaca_options.screener.filters import (
    calculate_atr,
    calculate_average_volume,
    calculate_bollinger_bands,
    calculate_dollar_volume,
    calculate_macd,
    calculate_roc,
    calculate_rsi,
    calculate_sma,
    calculate_stochastic,
    is_in_price_range,
    is_overbought,
    is_oversold,
    meets_dollar_volume_threshold,
    meets_volume_threshold,
    score_technical_setup,
)

logger = logging.getLogger(__name__)


def determine_consensus_signal(
    rsi: Optional[float],
    macd_histogram: Optional[float],
    bb_position: Optional[float],
    stoch_k: Optional[float],
    roc: Optional[float],
    rsi_oversold: float = 30.0,
    rsi_overbought: float = 70.0,
) -> tuple[str, int]:
    """Determine trading signal using consensus from multiple indicators.

    Requires at least 3 out of 5 indicators to agree for a bullish/bearish signal.

    Indicator Rules:
        RSI: < 30 bullish, > 70 bearish
        MACD: histogram > 0 bullish, < 0 bearish
        Bollinger: position < 20 bullish, > 80 bearish
        Stochastic: %K < 20 bullish, > 80 bearish
        ROC: < -5% bullish, > 5% bearish

    Args:
        rsi: Current RSI value.
        macd_histogram: MACD histogram value.
        bb_position: Bollinger Band position (0-100).
        stoch_k: Stochastic %K value.
        roc: Rate of Change percentage.
        rsi_oversold: RSI oversold threshold.
        rsi_overbought: RSI overbought threshold.

    Returns:
        Tuple of (signal, agreement_count) where signal is "bullish", "bearish", or "neutral"
    """
    bullish_votes = 0
    bearish_votes = 0
    total_votes = 0

    # RSI vote
    if rsi is not None:
        total_votes += 1
        if rsi < rsi_oversold:
            bullish_votes += 1
        elif rsi > rsi_overbought:
            bearish_votes += 1

    # MACD vote
    if macd_histogram is not None:
        total_votes += 1
        if macd_histogram > 0:
            bullish_votes += 1
        elif macd_histogram < 0:
            bearish_votes += 1

    # Bollinger Bands vote
    if bb_position is not None:
        total_votes += 1
        if bb_position < 20:  # Near lower band
            bullish_votes += 1
        elif bb_position > 80:  # Near upper band
            bearish_votes += 1

    # Stochastic vote
    if stoch_k is not None:
        total_votes += 1
        if stoch_k < 20:
            bullish_votes += 1
        elif stoch_k > 80:
            bearish_votes += 1

    # ROC vote
    if roc is not None:
        total_votes += 1
        if roc < -5:  # Strong negative momentum = oversold
            bullish_votes += 1
        elif roc > 5:  # Strong positive momentum = overbought
            bearish_votes += 1

    # Determine consensus (need 3+ votes)
    if bullish_votes >= 3:
        return "bullish", bullish_votes
    elif bearish_votes >= 3:
        return "bearish", bearish_votes
    else:
        return "neutral", max(bullish_votes, bearish_votes)


class TechnicalScreener(BaseScreener):
    """Screen stocks based on technical analysis criteria.

    Uses price, volume, and technical indicators to find opportunities.
    Requires access to Alpaca market data client.
    """

    def __init__(
        self,
        data_client,
        criteria: Optional[ScreeningCriteria] = None,
        cache_ttl_seconds: int = 300,
        lookback_days: int = 60,
    ) -> None:
        """Initialize the technical screener.

        Args:
            data_client: Alpaca StockHistoricalDataClient instance.
            criteria: Screening criteria to apply.
            cache_ttl_seconds: Cache TTL in seconds.
            lookback_days: Days of historical data to fetch.
        """
        super().__init__(criteria, cache_ttl_seconds)
        self._data_client = data_client
        self._lookback_days = lookback_days

    @property
    def screener_type(self) -> ScreenerType:
        return ScreenerType.TECHNICAL

    async def screen_symbol(self, symbol: str) -> ScreenerResult:
        """Screen a single symbol using technical analysis.

        Args:
            symbol: Stock symbol to screen.

        Returns:
            ScreenerResult with pass/fail and metrics.
        """
        try:
            # Fetch historical data
            bars = await self._fetch_bars(symbol)
            if bars is None or len(bars) < 20:
                return ScreenerResult(
                    symbol=symbol,
                    passed=False,
                    score=0.0,
                    filter_results={"data_available": False},
                )

            # Extract price and volume data
            close_prices = pd.Series([float(bar.close) for bar in bars])
            high_prices = pd.Series([float(bar.high) for bar in bars])
            low_prices = pd.Series([float(bar.low) for bar in bars])
            volumes = pd.Series([int(bar.volume) for bar in bars])

            current_price = float(close_prices.iloc[-1])
            current_volume = int(volumes.iloc[-1])

            # Calculate technical indicators
            rsi = calculate_rsi(close_prices, self.criteria.rsi_period)
            sma_50 = calculate_sma(close_prices, 50) if len(close_prices) >= 50 else None
            sma_200 = calculate_sma(close_prices, 200) if len(close_prices) >= 200 else None
            atr = calculate_atr(high_prices, low_prices, close_prices)
            avg_volume = calculate_average_volume(volumes, 20)
            dollar_volume = calculate_dollar_volume(current_price, int(avg_volume))

            # New indicators (Phase 2 Enhancement)
            macd_line, macd_signal, macd_histogram = calculate_macd(close_prices)
            bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(close_prices)
            stoch_k, stoch_d = calculate_stochastic(high_prices, low_prices, close_prices)
            roc = calculate_roc(close_prices, period=14)

            # Calculate Bollinger Band position (0-100, where 50 = middle)
            bb_position = None
            if bb_upper and bb_lower and bb_upper != bb_lower:
                bb_position = ((current_price - bb_lower) / (bb_upper - bb_lower)) * 100

            # Calculate ATR as percentage of price
            atr_percent = (atr / current_price * 100) if current_price > 0 else 0

            # Apply filters
            filter_results = {}

            # Price filter
            price_ok = is_in_price_range(
                current_price,
                self.criteria.min_price,
                self.criteria.max_price,
            )
            filter_results["price_range"] = price_ok

            # Volume filter
            volume_ok = meets_volume_threshold(int(avg_volume), self.criteria.min_volume)
            filter_results["min_volume"] = volume_ok

            # Dollar volume filter
            dollar_vol_ok = meets_dollar_volume_threshold(
                dollar_volume,
                self.criteria.min_dollar_volume,
            )
            filter_results["min_dollar_volume"] = dollar_vol_ok

            # Determine signal using consensus from all indicators (Phase 2 Enhancement)
            signal, agreement_count = determine_consensus_signal(
                rsi=rsi,
                macd_histogram=macd_histogram,
                bb_position=bb_position,
                stoch_k=stoch_k,
                roc=roc,
                rsi_oversold=self.criteria.rsi_oversold or 30.0,
                rsi_overbought=self.criteria.rsi_overbought or 70.0,
            )

            # RSI filters (optional) - still check for backwards compatibility
            rsi_ok = True

            if self.criteria.rsi_oversold is not None:
                if is_oversold(rsi, self.criteria.rsi_oversold):
                    filter_results["rsi_oversold"] = True
                else:
                    filter_results["rsi_oversold"] = False

            if self.criteria.rsi_overbought is not None:
                if is_overbought(rsi, self.criteria.rsi_overbought):
                    filter_results["rsi_overbought"] = True
                else:
                    filter_results["rsi_overbought"] = False

            # If both RSI thresholds set, must hit one of them
            if (
                self.criteria.rsi_oversold is not None
                and self.criteria.rsi_overbought is not None
            ):
                rsi_ok = (
                    filter_results.get("rsi_oversold", False)
                    or filter_results.get("rsi_overbought", False)
                )
            elif self.criteria.rsi_oversold is not None:
                rsi_ok = filter_results.get("rsi_oversold", True)
            elif self.criteria.rsi_overbought is not None:
                rsi_ok = filter_results.get("rsi_overbought", True)

            filter_results["rsi_filter"] = rsi_ok
            filter_results["consensus_signal"] = signal
            filter_results["consensus_agreement"] = agreement_count

            # SMA filters (optional)
            sma_ok = True

            if self.criteria.above_sma is not None and sma_50 is not None:
                above = current_price > sma_50
                filter_results[f"above_sma_{self.criteria.above_sma}"] = above
                if not above:
                    sma_ok = False

            if self.criteria.below_sma is not None and sma_50 is not None:
                below = current_price < sma_50
                filter_results[f"below_sma_{self.criteria.below_sma}"] = below
                if not below:
                    sma_ok = False

            # ATR filters (optional)
            atr_ok = True

            if self.criteria.min_atr_percent is not None:
                if atr_percent < self.criteria.min_atr_percent:
                    atr_ok = False
                filter_results["min_atr"] = atr_percent >= self.criteria.min_atr_percent

            if self.criteria.max_atr_percent is not None:
                if atr_percent > self.criteria.max_atr_percent:
                    atr_ok = False
                filter_results["max_atr"] = atr_percent <= self.criteria.max_atr_percent

            # Determine if passed all required filters
            passed = all([
                price_ok,
                volume_ok,
                dollar_vol_ok,
                rsi_ok,
                sma_ok,
                atr_ok,
            ])

            # Calculate score
            price_vs_sma50 = None
            if sma_50:
                price_vs_sma50 = ((current_price - sma_50) / sma_50) * 100

            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

            score = score_technical_setup(
                rsi=rsi,
                price_vs_sma50=price_vs_sma50,
                price_vs_sma200=None,
                volume_ratio=volume_ratio,
                atr_percent=atr_percent,
            )

            return ScreenerResult(
                symbol=symbol,
                passed=passed,
                score=score,
                timestamp=datetime.now(),
                price=current_price,
                volume=current_volume,
                dollar_volume=dollar_volume,
                rsi=rsi,
                sma_50=sma_50,
                sma_200=sma_200,
                atr=atr,
                atr_percent=atr_percent,
                # New indicators (Phase 2 Enhancement)
                macd_line=macd_line,
                macd_signal=macd_signal,
                macd_histogram=macd_histogram,
                bb_upper=bb_upper,
                bb_middle=bb_middle,
                bb_lower=bb_lower,
                bb_position=bb_position,
                stoch_k=stoch_k,
                stoch_d=stoch_d,
                roc=roc,
                filter_results=filter_results,
                signal=signal,
            )

        except Exception as e:
            logger.error(f"Error screening {symbol}: {e}")
            return ScreenerResult(
                symbol=symbol,
                passed=False,
                score=0.0,
                filter_results={"error": str(e)},
            )

    async def _fetch_bars(self, symbol: str) -> Optional[list]:
        """Fetch historical bar data for a symbol.

        Args:
            symbol: Stock symbol.

        Returns:
            List of bar objects or None on failure.
        """
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        try:
            end = datetime.now()
            start = end - timedelta(days=self._lookback_days)

            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame.Day,
                start=start,
                end=end,
            )

            bars_data = self._data_client.get_stock_bars(request)

            # BarSet uses dict-like [] access, not .get()
            try:
                bars = bars_data[symbol]
                return list(bars) if bars else None
            except (KeyError, TypeError):
                return None

        except Exception as e:
            logger.warning(f"Failed to fetch bars for {symbol}: {e}")
            return None

    async def scan_for_oversold(
        self,
        symbols: list[str],
        rsi_threshold: float = 30.0,
        max_results: int = 10,
    ) -> list[ScreenerResult]:
        """Scan for oversold stocks (bullish opportunities).

        Args:
            symbols: List of symbols to scan.
            rsi_threshold: RSI threshold for oversold.
            max_results: Maximum results to return.

        Returns:
            List of ScreenerResults sorted by RSI (lowest first).
        """
        # Temporarily update criteria
        original_oversold = self.criteria.rsi_oversold
        original_overbought = self.criteria.rsi_overbought
        self.criteria.rsi_oversold = rsi_threshold
        self.criteria.rsi_overbought = None

        try:
            results = await self.scan(symbols, max_results=None)

            # Filter and sort by RSI
            oversold = [
                r for r in results.results
                if r.passed and r.rsi is not None and r.rsi < rsi_threshold
            ]
            oversold.sort(key=lambda x: x.rsi or 100)

            return oversold[:max_results]

        finally:
            # Restore original criteria
            self.criteria.rsi_oversold = original_oversold
            self.criteria.rsi_overbought = original_overbought

    async def scan_for_overbought(
        self,
        symbols: list[str],
        rsi_threshold: float = 70.0,
        max_results: int = 10,
    ) -> list[ScreenerResult]:
        """Scan for overbought stocks (bearish opportunities).

        Args:
            symbols: List of symbols to scan.
            rsi_threshold: RSI threshold for overbought.
            max_results: Maximum results to return.

        Returns:
            List of ScreenerResults sorted by RSI (highest first).
        """
        original_oversold = self.criteria.rsi_oversold
        original_overbought = self.criteria.rsi_overbought
        self.criteria.rsi_oversold = None
        self.criteria.rsi_overbought = rsi_threshold

        try:
            results = await self.scan(symbols, max_results=None)

            overbought = [
                r for r in results.results
                if r.passed and r.rsi is not None and r.rsi > rsi_threshold
            ]
            overbought.sort(key=lambda x: x.rsi or 0, reverse=True)

            return overbought[:max_results]

        finally:
            self.criteria.rsi_oversold = original_oversold
            self.criteria.rsi_overbought = original_overbought

    async def scan_high_volume(
        self,
        symbols: list[str],
        volume_multiplier: float = 2.0,
        max_results: int = 10,
    ) -> list[ScreenerResult]:
        """Scan for stocks with unusually high volume.

        Args:
            symbols: List of symbols to scan.
            volume_multiplier: Volume must be this multiple of average.
            max_results: Maximum results to return.

        Returns:
            List of ScreenerResults sorted by volume ratio.
        """
        results = await self.scan(symbols, max_results=None)

        high_volume = []
        for r in results.results:
            if r.passed and r.volume is not None:
                # Need to recalculate volume ratio if not stored
                bars = await self._fetch_bars(r.symbol)
                if bars and len(bars) > 20:
                    volumes = pd.Series([int(bar.volume) for bar in bars])
                    avg_vol = calculate_average_volume(volumes, 20)
                    current_vol = int(volumes.iloc[-1])
                    ratio = current_vol / avg_vol if avg_vol > 0 else 0

                    if ratio >= volume_multiplier:
                        r.filter_results["volume_ratio"] = ratio
                        high_volume.append(r)

        high_volume.sort(
            key=lambda x: x.filter_results.get("volume_ratio", 0),
            reverse=True,
        )

        return high_volume[:max_results]
