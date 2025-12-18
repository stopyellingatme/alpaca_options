"""Market data operations for stock quotes, bars, and real-time streaming."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine, Optional

import pandas as pd
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.live.stock import StockDataStream
from alpaca.data.requests import (
    StockBarsRequest,
    StockLatestQuoteRequest,
    StockLatestTradeRequest,
    StockQuotesRequest,
    StockTradesRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from alpaca_options.strategies.base import MarketData

logger = logging.getLogger(__name__)


@dataclass
class Quote:
    """Real-time quote data."""

    symbol: str
    timestamp: datetime
    bid: float
    bid_size: int
    ask: float
    ask_size: int

    @property
    def mid(self) -> float:
        """Calculate mid price."""
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        """Calculate bid-ask spread."""
        return self.ask - self.bid


@dataclass
class Trade:
    """Real-time trade data."""

    symbol: str
    timestamp: datetime
    price: float
    size: int
    exchange: str


@dataclass
class Bar:
    """OHLCV bar data."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: Optional[float] = None
    trade_count: Optional[int] = None


# Type alias for stream handlers
StreamHandler = Callable[[Any], Coroutine[Any, Any, None]]


class MarketDataManager:
    """Manages stock market data retrieval and streaming.

    Provides:
    - Historical bar data
    - Latest quotes and trades
    - Real-time streaming subscriptions
    - Data caching for efficiency
    """

    def __init__(
        self,
        data_client: StockHistoricalDataClient,
        stream_client: Optional[StockDataStream] = None,
    ) -> None:
        self._data_client = data_client
        self._stream_client = stream_client

        # Caches
        self._quote_cache: dict[str, Quote] = {}
        self._bar_cache: dict[str, list[Bar]] = {}

        # Stream state
        self._subscribed_quotes: set[str] = set()
        self._subscribed_trades: set[str] = set()
        self._subscribed_bars: set[str] = set()

        # Handlers
        self._quote_handlers: list[StreamHandler] = []
        self._trade_handlers: list[StreamHandler] = []
        self._bar_handlers: list[StreamHandler] = []

        self._stream_running = False

    def _parse_timeframe(self, timeframe: str) -> TimeFrame:
        """Parse timeframe string to Alpaca TimeFrame.

        Args:
            timeframe: String like "1min", "5min", "1h", "1d".

        Returns:
            Alpaca TimeFrame object.
        """
        tf_map = {
            "1min": TimeFrame(1, TimeFrameUnit.Minute),
            "5min": TimeFrame(5, TimeFrameUnit.Minute),
            "15min": TimeFrame(15, TimeFrameUnit.Minute),
            "30min": TimeFrame(30, TimeFrameUnit.Minute),
            "1h": TimeFrame(1, TimeFrameUnit.Hour),
            "4h": TimeFrame(4, TimeFrameUnit.Hour),
            "1d": TimeFrame(1, TimeFrameUnit.Day),
            "1w": TimeFrame(1, TimeFrameUnit.Week),
            "1m": TimeFrame(1, TimeFrameUnit.Month),
        }
        return tf_map.get(timeframe.lower(), TimeFrame(1, TimeFrameUnit.Hour))

    def get_bars(
        self,
        symbols: list[str],
        timeframe: str = "1h",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> dict[str, list[Bar]]:
        """Get historical bar data for symbols.

        Args:
            symbols: List of symbols to fetch.
            timeframe: Bar timeframe (e.g., "1min", "1h", "1d").
            start: Start datetime. Defaults to 30 days ago.
            end: End datetime. Defaults to now.
            limit: Maximum number of bars per symbol.

        Returns:
            Dictionary mapping symbols to list of Bars.
        """
        if start is None:
            start = datetime.now() - timedelta(days=30)
        if end is None:
            end = datetime.now()

        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=self._parse_timeframe(timeframe),
            start=start,
            end=end,
            limit=limit,
        )

        try:
            bars_data = self._data_client.get_stock_bars(request)
            result: dict[str, list[Bar]] = {}

            for symbol in symbols:
                # Use [] access instead of .get() for BarSet objects
                try:
                    symbol_bars = bars_data[symbol]
                except (KeyError, TypeError):
                    symbol_bars = []

                result[symbol] = [
                    Bar(
                        symbol=symbol,
                        timestamp=bar.timestamp,
                        open=float(bar.open),
                        high=float(bar.high),
                        low=float(bar.low),
                        close=float(bar.close),
                        volume=int(bar.volume),
                        vwap=float(bar.vwap) if bar.vwap else None,
                        trade_count=bar.trade_count,
                    )
                    for bar in symbol_bars
                ]

            return result

        except Exception as e:
            logger.error(f"Failed to get bars: {e}")
            return {symbol: [] for symbol in symbols}

    def get_bars_df(
        self,
        symbols: list[str],
        timeframe: str = "1h",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Get historical bar data as a DataFrame.

        Args:
            symbols: List of symbols to fetch.
            timeframe: Bar timeframe.
            start: Start datetime.
            end: End datetime.

        Returns:
            DataFrame with multi-index (symbol, timestamp).
        """
        if start is None:
            start = datetime.now() - timedelta(days=30)
        if end is None:
            end = datetime.now()

        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=self._parse_timeframe(timeframe),
            start=start,
            end=end,
        )

        try:
            return self._data_client.get_stock_bars(request).df
        except Exception as e:
            logger.error(f"Failed to get bars DataFrame: {e}")
            return pd.DataFrame()

    def get_latest_quote(self, symbol: str) -> Optional[Quote]:
        """Get the latest quote for a symbol.

        Args:
            symbol: The symbol to fetch.

        Returns:
            Quote object or None on failure.
        """
        request = StockLatestQuoteRequest(symbol_or_symbols=[symbol])

        try:
            quotes = self._data_client.get_stock_latest_quote(request)
            # Use [] access instead of .get() for quote objects
            try:
                quote_data = quotes[symbol]
            except (KeyError, TypeError):
                quote_data = None

            if quote_data:
                quote = Quote(
                    symbol=symbol,
                    timestamp=quote_data.timestamp,
                    bid=float(quote_data.bid_price),
                    bid_size=int(quote_data.bid_size),
                    ask=float(quote_data.ask_price),
                    ask_size=int(quote_data.ask_size),
                )
                self._quote_cache[symbol] = quote
                return quote

            return None

        except Exception as e:
            logger.error(f"Failed to get latest quote for {symbol}: {e}")
            return self._quote_cache.get(symbol)

    def get_latest_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Get latest quotes for multiple symbols.

        Args:
            symbols: List of symbols to fetch.

        Returns:
            Dictionary mapping symbols to Quotes.
        """
        request = StockLatestQuoteRequest(symbol_or_symbols=symbols)

        try:
            quotes = self._data_client.get_stock_latest_quote(request)
            result = {}

            for symbol in symbols:
                # Use [] access instead of .get() for quote objects
                try:
                    quote_data = quotes[symbol]
                except (KeyError, TypeError):
                    quote_data = None

                if quote_data:
                    quote = Quote(
                        symbol=symbol,
                        timestamp=quote_data.timestamp,
                        bid=float(quote_data.bid_price),
                        bid_size=int(quote_data.bid_size),
                        ask=float(quote_data.ask_price),
                        ask_size=int(quote_data.ask_size),
                    )
                    result[symbol] = quote
                    self._quote_cache[symbol] = quote

            return result

        except Exception as e:
            logger.error(f"Failed to get latest quotes: {e}")
            return {s: self._quote_cache[s] for s in symbols if s in self._quote_cache}

    def get_latest_trade(self, symbol: str) -> Optional[Trade]:
        """Get the latest trade for a symbol.

        Args:
            symbol: The symbol to fetch.

        Returns:
            Trade object or None on failure.
        """
        request = StockLatestTradeRequest(symbol_or_symbols=[symbol])

        try:
            trades = self._data_client.get_stock_latest_trade(request)
            # Use [] access instead of .get() for trade objects
            try:
                trade_data = trades[symbol]
            except (KeyError, TypeError):
                trade_data = None

            if trade_data:
                return Trade(
                    symbol=symbol,
                    timestamp=trade_data.timestamp,
                    price=float(trade_data.price),
                    size=int(trade_data.size),
                    exchange=trade_data.exchange or "",
                )

            return None

        except Exception as e:
            logger.error(f"Failed to get latest trade for {symbol}: {e}")
            return None

    def get_market_data(self, symbol: str) -> Optional[MarketData]:
        """Get market data snapshot for strategy consumption.

        Combines latest quote with recent bar data and calculates technical indicators.

        Args:
            symbol: The symbol to fetch.

        Returns:
            MarketData object for strategy processing.
        """
        # Get latest bars for OHLC and indicators (need at least 50 bars for SMA_50)
        bars = self.get_bars([symbol], timeframe="1d", limit=60)
        symbol_bars = bars.get(symbol, [])

        if not symbol_bars:
            return None

        latest_bar = symbol_bars[-1]
        quote = self.get_latest_quote(symbol)
        current_close = quote.mid if quote else latest_bar.close

        # Calculate technical indicators
        sma_20, sma_50, rsi_14 = None, None, None

        if len(symbol_bars) >= 14:
            # Calculate RSI (need at least 14 bars)
            closes = [bar.close for bar in symbol_bars]
            rsi_14 = self._calculate_rsi(closes, period=14)

        if len(symbol_bars) >= 20:
            # Calculate SMA_20
            closes_20 = [bar.close for bar in symbol_bars[-20:]]
            sma_20 = sum(closes_20) / len(closes_20)

        if len(symbol_bars) >= 50:
            # Calculate SMA_50
            closes_50 = [bar.close for bar in symbol_bars[-50:]]
            sma_50 = sum(closes_50) / len(closes_50)

        return MarketData(
            symbol=symbol,
            timestamp=datetime.now(),
            open=latest_bar.open,
            high=latest_bar.high,
            low=latest_bar.low,
            close=current_close,
            volume=latest_bar.volume,
            vwap=latest_bar.vwap,
            sma_20=sma_20,
            sma_50=sma_50,
            rsi_14=rsi_14,
        )

    def _calculate_rsi(self, prices: list[float], period: int = 14) -> Optional[float]:
        """Calculate RSI (Relative Strength Index).

        Args:
            prices: List of closing prices.
            period: RSI period (default 14).

        Returns:
            RSI value (0-100) or None if insufficient data.
        """
        if len(prices) < period + 1:
            return None

        # Calculate price changes
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]

        # Separate gains and losses
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        # Calculate initial average gain/loss
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Smooth with remaining data
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        # Calculate RSI
        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    # Streaming methods

    def add_quote_handler(self, handler: StreamHandler) -> None:
        """Add a handler for quote stream updates."""
        self._quote_handlers.append(handler)

    def add_trade_handler(self, handler: StreamHandler) -> None:
        """Add a handler for trade stream updates."""
        self._trade_handlers.append(handler)

    def add_bar_handler(self, handler: StreamHandler) -> None:
        """Add a handler for bar stream updates."""
        self._bar_handlers.append(handler)

    async def subscribe_quotes(self, symbols: list[str]) -> None:
        """Subscribe to real-time quote updates.

        Args:
            symbols: Symbols to subscribe to.
        """
        if self._stream_client is None:
            logger.warning("Stream client not configured")
            return

        new_symbols = set(symbols) - self._subscribed_quotes

        if new_symbols:
            self._stream_client.subscribe_quotes(self._handle_quote, *new_symbols)
            self._subscribed_quotes.update(new_symbols)
            logger.info(f"Subscribed to quotes: {new_symbols}")

    async def subscribe_trades(self, symbols: list[str]) -> None:
        """Subscribe to real-time trade updates.

        Args:
            symbols: Symbols to subscribe to.
        """
        if self._stream_client is None:
            logger.warning("Stream client not configured")
            return

        new_symbols = set(symbols) - self._subscribed_trades

        if new_symbols:
            self._stream_client.subscribe_trades(self._handle_trade, *new_symbols)
            self._subscribed_trades.update(new_symbols)
            logger.info(f"Subscribed to trades: {new_symbols}")

    async def subscribe_bars(self, symbols: list[str]) -> None:
        """Subscribe to real-time bar updates.

        Args:
            symbols: Symbols to subscribe to.
        """
        if self._stream_client is None:
            logger.warning("Stream client not configured")
            return

        new_symbols = set(symbols) - self._subscribed_bars

        if new_symbols:
            self._stream_client.subscribe_bars(self._handle_bar, *new_symbols)
            self._subscribed_bars.update(new_symbols)
            logger.info(f"Subscribed to bars: {new_symbols}")

    async def unsubscribe_quotes(self, symbols: list[str]) -> None:
        """Unsubscribe from quote updates."""
        if self._stream_client is None:
            return

        to_unsub = set(symbols) & self._subscribed_quotes
        if to_unsub:
            self._stream_client.unsubscribe_quotes(*to_unsub)
            self._subscribed_quotes -= to_unsub

    async def unsubscribe_trades(self, symbols: list[str]) -> None:
        """Unsubscribe from trade updates."""
        if self._stream_client is None:
            return

        to_unsub = set(symbols) & self._subscribed_trades
        if to_unsub:
            self._stream_client.unsubscribe_trades(*to_unsub)
            self._subscribed_trades -= to_unsub

    async def start_stream(self) -> None:
        """Start the streaming connection."""
        if self._stream_client is None:
            logger.warning("Stream client not configured")
            return

        if self._stream_running:
            return

        self._stream_running = True
        asyncio.create_task(self._run_stream())
        logger.info("Market data stream started")

    async def stop_stream(self) -> None:
        """Stop the streaming connection."""
        if self._stream_client is None:
            return

        self._stream_running = False
        await self._stream_client.close()
        logger.info("Market data stream stopped")

    async def _run_stream(self) -> None:
        """Run the stream in background."""
        if self._stream_client is None:
            return

        try:
            await self._stream_client._run_forever()
        except Exception as e:
            logger.error(f"Stream error: {e}")
            self._stream_running = False

    async def _handle_quote(self, quote_data) -> None:
        """Handle incoming quote from stream."""
        quote = Quote(
            symbol=quote_data.symbol,
            timestamp=quote_data.timestamp,
            bid=float(quote_data.bid_price),
            bid_size=int(quote_data.bid_size),
            ask=float(quote_data.ask_price),
            ask_size=int(quote_data.ask_size),
        )

        self._quote_cache[quote.symbol] = quote

        for handler in self._quote_handlers:
            try:
                await handler(quote)
            except Exception as e:
                logger.error(f"Quote handler error: {e}")

    async def _handle_trade(self, trade_data) -> None:
        """Handle incoming trade from stream."""
        trade = Trade(
            symbol=trade_data.symbol,
            timestamp=trade_data.timestamp,
            price=float(trade_data.price),
            size=int(trade_data.size),
            exchange=trade_data.exchange or "",
        )

        for handler in self._trade_handlers:
            try:
                await handler(trade)
            except Exception as e:
                logger.error(f"Trade handler error: {e}")

    async def _handle_bar(self, bar_data) -> None:
        """Handle incoming bar from stream."""
        bar = Bar(
            symbol=bar_data.symbol,
            timestamp=bar_data.timestamp,
            open=float(bar_data.open),
            high=float(bar_data.high),
            low=float(bar_data.low),
            close=float(bar_data.close),
            volume=int(bar_data.volume),
            vwap=float(bar_data.vwap) if bar_data.vwap else None,
        )

        for handler in self._bar_handlers:
            try:
                await handler(bar)
            except Exception as e:
                logger.error(f"Bar handler error: {e}")
