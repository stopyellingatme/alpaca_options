"""Options-specific API operations for chains, quotes, and contracts."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.live.option import OptionDataStream
from alpaca.data.requests import (
    OptionBarsRequest,
    OptionChainRequest,
    OptionLatestQuoteRequest,
    OptionLatestTradeRequest,
    OptionSnapshotRequest,
    OptionTradesRequest,
)
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest
from alpaca.trading.enums import ContractType, ExerciseStyle

from alpaca_options.strategies.base import OptionChain, OptionContract

logger = logging.getLogger(__name__)


@dataclass
class OptionQuote:
    """Options quote data."""

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
class OptionSnapshot:
    """Options snapshot with quote and greeks."""

    symbol: str
    timestamp: datetime
    underlying_price: float

    # Quote data
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int

    # Greeks
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    implied_volatility: Optional[float] = None


class OptionsDataManager:
    """Manages options-specific data operations.

    Provides:
    - Options chain retrieval
    - Options quotes and snapshots
    - Contract discovery and filtering
    - Real-time options streaming
    """

    def __init__(
        self,
        trading_client: TradingClient,
        data_client: OptionHistoricalDataClient,
        stream_client: Optional[OptionDataStream] = None,
    ) -> None:
        self._trading_client = trading_client
        self._data_client = data_client
        self._stream_client = stream_client

        # Cache
        self._chain_cache: dict[str, OptionChain] = {}
        self._snapshot_cache: dict[str, OptionSnapshot] = {}

    def get_option_contracts(
        self,
        underlying: str,
        expiration_date: Optional[datetime] = None,
        expiration_date_gte: Optional[datetime] = None,
        expiration_date_lte: Optional[datetime] = None,
        strike_price_gte: Optional[float] = None,
        strike_price_lte: Optional[float] = None,
        option_type: Optional[str] = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Get option contracts from the trading API.

        Args:
            underlying: Underlying symbol (e.g., "AAPL").
            expiration_date: Exact expiration date.
            expiration_date_gte: Minimum expiration date.
            expiration_date_lte: Maximum expiration date.
            strike_price_gte: Minimum strike price.
            strike_price_lte: Maximum strike price.
            option_type: "call" or "put".
            limit: Maximum contracts to return.

        Returns:
            List of contract dictionaries.
        """
        contract_type = None
        if option_type:
            contract_type = ContractType.CALL if option_type.lower() == "call" else ContractType.PUT

        request = GetOptionContractsRequest(
            underlying_symbols=[underlying],
            expiration_date=expiration_date,
            expiration_date_gte=expiration_date_gte,
            expiration_date_lte=expiration_date_lte,
            strike_price_gte=strike_price_gte,
            strike_price_lte=strike_price_lte,
            type=contract_type,
            limit=limit,
        )

        try:
            contracts = self._trading_client.get_option_contracts(request)
            return [
                {
                    "symbol": c.symbol,
                    "underlying": c.underlying_symbol,
                    "option_type": c.type.value if hasattr(c.type, 'value') else str(c.type) if c.type else "unknown",
                    "strike": float(c.strike_price),
                    "expiration": datetime.combine(c.expiration_date, datetime.min.time()) if hasattr(c.expiration_date, 'year') else c.expiration_date,
                    "style": c.style.value if hasattr(c.style, 'value') else str(c.style) if c.style else "american",
                    "root_symbol": c.root_symbol,
                    "status": c.status.value if hasattr(c.status, 'value') else str(c.status) if c.status else "active",
                }
                for c in contracts.option_contracts if contracts.option_contracts
            ]
        except Exception as e:
            logger.error(f"Failed to get option contracts for {underlying}: {e}")
            return []

    def get_option_chain(
        self,
        underlying: str,
        underlying_price: Optional[float] = None,
        min_dte: int = 0,
        max_dte: int = 60,
        min_strike_distance: float = 0.0,
        max_strike_distance: float = 0.3,
    ) -> Optional[OptionChain]:
        """Get a complete option chain for an underlying.

        Args:
            underlying: Underlying symbol.
            underlying_price: Current underlying price (for strike filtering).
            min_dte: Minimum days to expiration.
            max_dte: Maximum days to expiration.
            min_strike_distance: Min distance from ATM as % (0.0 = ATM).
            max_strike_distance: Max distance from ATM as % (0.3 = 30%).

        Returns:
            OptionChain object or None on failure.
        """
        from datetime import date
        today = date.today()
        exp_gte = today + timedelta(days=min_dte)
        exp_lte = today + timedelta(days=max_dte)

        # Get contracts
        contracts = self.get_option_contracts(
            underlying=underlying,
            expiration_date_gte=exp_gte,
            expiration_date_lte=exp_lte,
        )

        if not contracts:
            return None

        # If no price provided, we can't filter by strike
        if underlying_price and max_strike_distance < 1.0:
            min_strike = underlying_price * (1 - max_strike_distance)
            max_strike = underlying_price * (1 + max_strike_distance)
            contracts = [
                c for c in contracts
                if min_strike <= c["strike"] <= max_strike
            ]

        if not contracts:
            return None

        # Get snapshots for all contracts
        contract_symbols = [c["symbol"] for c in contracts]
        snapshots = self.get_option_snapshots(contract_symbols)

        # Build OptionContract objects
        option_contracts = []
        for contract in contracts:
            symbol = contract["symbol"]
            snapshot = snapshots.get(symbol)

            if snapshot:
                option_contracts.append(
                    OptionContract(
                        symbol=symbol,
                        underlying=underlying,
                        option_type=contract["option_type"],
                        strike=contract["strike"],
                        expiration=contract["expiration"],
                        bid=snapshot.bid,
                        ask=snapshot.ask,
                        last=snapshot.last,
                        volume=snapshot.volume,
                        open_interest=snapshot.open_interest,
                        delta=snapshot.delta,
                        gamma=snapshot.gamma,
                        theta=snapshot.theta,
                        vega=snapshot.vega,
                        rho=snapshot.rho,
                        implied_volatility=snapshot.implied_volatility,
                    )
                )
            else:
                # Create contract without snapshot data
                option_contracts.append(
                    OptionContract(
                        symbol=symbol,
                        underlying=underlying,
                        option_type=contract["option_type"],
                        strike=contract["strike"],
                        expiration=contract["expiration"],
                        bid=0.0,
                        ask=0.0,
                        last=0.0,
                        volume=0,
                        open_interest=0,
                    )
                )

        chain = OptionChain(
            underlying=underlying,
            underlying_price=underlying_price or 0.0,
            timestamp=datetime.now(),
            contracts=option_contracts,
        )

        self._chain_cache[underlying] = chain
        return chain

    def get_option_snapshots(
        self,
        symbols: list[str],
    ) -> dict[str, OptionSnapshot]:
        """Get option snapshots with quotes and greeks.

        Args:
            symbols: List of option contract symbols.

        Returns:
            Dictionary mapping symbols to OptionSnapshots.
        """
        if not symbols:
            return {}

        # Batch into chunks of 100 (API limit)
        results = {}
        chunk_size = 100

        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i + chunk_size]

            try:
                request = OptionSnapshotRequest(symbol_or_symbols=chunk)
                snapshots = self._data_client.get_option_snapshot(request)

                for symbol in chunk:
                    snap = snapshots.get(symbol)
                    if snap:
                        # Extract quote data
                        quote = snap.latest_quote
                        trade = snap.latest_trade
                        greeks = snap.greeks

                        # Get volume from trade if available
                        volume = 0
                        if trade and hasattr(trade, 'size') and trade.size:
                            volume = int(trade.size)

                        results[symbol] = OptionSnapshot(
                            symbol=symbol,
                            timestamp=datetime.now(),
                            underlying_price=0.0,  # Not available in Alpaca OptionsSnapshot
                            bid=float(quote.bid_price) if quote and quote.bid_price else 0.0,
                            ask=float(quote.ask_price) if quote and quote.ask_price else 0.0,
                            last=float(trade.price) if trade and trade.price else 0.0,
                            volume=volume,
                            open_interest=0,  # Not available in Alpaca OptionsSnapshot
                            delta=float(greeks.delta) if greeks and greeks.delta else None,
                            gamma=float(greeks.gamma) if greeks and greeks.gamma else None,
                            theta=float(greeks.theta) if greeks and greeks.theta else None,
                            vega=float(greeks.vega) if greeks and greeks.vega else None,
                            rho=float(greeks.rho) if greeks and greeks.rho else None,
                            implied_volatility=float(snap.implied_volatility) if snap.implied_volatility else None,
                        )
                        self._snapshot_cache[symbol] = results[symbol]

            except Exception as e:
                logger.error(f"Failed to get option snapshots: {e}")

        return results

    def get_option_latest_quote(self, symbol: str) -> Optional[OptionQuote]:
        """Get the latest quote for an option contract.

        Args:
            symbol: Option contract symbol.

        Returns:
            OptionQuote or None on failure.
        """
        try:
            request = OptionLatestQuoteRequest(symbol_or_symbols=[symbol])
            quotes = self._data_client.get_option_latest_quote(request)
            quote = quotes.get(symbol)

            if quote:
                return OptionQuote(
                    symbol=symbol,
                    timestamp=quote.timestamp,
                    bid=float(quote.bid_price) if quote.bid_price else 0.0,
                    bid_size=int(quote.bid_size) if quote.bid_size else 0,
                    ask=float(quote.ask_price) if quote.ask_price else 0.0,
                    ask_size=int(quote.ask_size) if quote.ask_size else 0,
                )

            return None

        except Exception as e:
            logger.error(f"Failed to get option quote for {symbol}: {e}")
            return None

    def get_option_latest_quotes(
        self,
        symbols: list[str],
    ) -> dict[str, OptionQuote]:
        """Get latest quotes for multiple option contracts.

        Args:
            symbols: List of option contract symbols.

        Returns:
            Dictionary mapping symbols to OptionQuotes.
        """
        results = {}
        chunk_size = 100

        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i + chunk_size]

            try:
                request = OptionLatestQuoteRequest(symbol_or_symbols=chunk)
                quotes = self._data_client.get_option_latest_quote(request)

                for symbol in chunk:
                    quote = quotes.get(symbol)
                    if quote:
                        results[symbol] = OptionQuote(
                            symbol=symbol,
                            timestamp=quote.timestamp,
                            bid=float(quote.bid_price) if quote.bid_price else 0.0,
                            bid_size=int(quote.bid_size) if quote.bid_size else 0,
                            ask=float(quote.ask_price) if quote.ask_price else 0.0,
                            ask_size=int(quote.ask_size) if quote.ask_size else 0,
                        )

            except Exception as e:
                logger.error(f"Failed to get option quotes: {e}")

        return results

    def get_option_latest_trade(self, symbol: str) -> Optional[dict]:
        """Get the latest trade for an option contract.

        Args:
            symbol: Option contract symbol.

        Returns:
            Dictionary with trade data or None on failure.

        Example:
            {
                "symbol": "SPY240315C00500000",
                "timestamp": datetime(...),
                "price": 5.25,
                "size": 10,
                "exchange": "CBOE"
            }
        """
        try:
            request = OptionLatestTradeRequest(symbol_or_symbols=[symbol])
            trades = self._data_client.get_option_latest_trade(request)
            trade = trades.get(symbol)

            if trade:
                return {
                    "symbol": symbol,
                    "timestamp": trade.timestamp,
                    "price": float(trade.price) if trade.price else 0.0,
                    "size": int(trade.size) if trade.size else 0,
                    "exchange": trade.exchange if hasattr(trade, 'exchange') else "unknown",
                }

            return None

        except Exception as e:
            logger.error(f"Failed to get option trade for {symbol}: {e}")
            return None

    def get_option_latest_trades(
        self,
        symbols: list[str],
    ) -> dict[str, dict]:
        """Get latest trades for multiple option contracts.

        Args:
            symbols: List of option contract symbols.

        Returns:
            Dictionary mapping symbols to trade data.
        """
        results = {}
        chunk_size = 100

        for i in range(0, len(symbols), chunk_size):
            chunk = symbols[i:i + chunk_size]

            try:
                request = OptionLatestTradeRequest(symbol_or_symbols=chunk)
                trades = self._data_client.get_option_latest_trade(request)

                for symbol in chunk:
                    trade = trades.get(symbol)
                    if trade:
                        results[symbol] = {
                            "symbol": symbol,
                            "timestamp": trade.timestamp,
                            "price": float(trade.price) if trade.price else 0.0,
                            "size": int(trade.size) if trade.size else 0,
                            "exchange": trade.exchange if hasattr(trade, 'exchange') else "unknown",
                        }

            except Exception as e:
                logger.error(f"Failed to get option trades: {e}")

        return results

    def get_option_trades(
        self,
        symbols: list[str],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> dict[str, list[dict]]:
        """Get historical trades for option contracts.

        This is useful for backtesting and analyzing actual execution prices.

        Args:
            symbols: List of option contract symbols.
            start: Start datetime (default: 1 day ago).
            end: End datetime (default: now).
            limit: Maximum trades per symbol.

        Returns:
            Dictionary mapping symbols to list of trade dicts.

        Example:
            {
                "SPY240315C00500000": [
                    {
                        "timestamp": datetime(...),
                        "price": 5.25,
                        "size": 10,
                        "exchange": "CBOE"
                    },
                    ...
                ]
            }
        """
        if start is None:
            start = datetime.now() - timedelta(days=1)
        if end is None:
            end = datetime.now()

        results = {}

        try:
            request = OptionTradesRequest(
                symbol_or_symbols=symbols,
                start=start,
                end=end,
                limit=limit,
            )
            trades_data = self._data_client.get_option_trades(request)

            for symbol in symbols:
                symbol_trades = trades_data.get(symbol, [])
                results[symbol] = [
                    {
                        "timestamp": trade.timestamp,
                        "price": float(trade.price) if trade.price else 0.0,
                        "size": int(trade.size) if trade.size else 0,
                        "exchange": trade.exchange if hasattr(trade, 'exchange') else "unknown",
                    }
                    for trade in symbol_trades
                ]

        except Exception as e:
            logger.error(f"Failed to get option trades: {e}")

        return results

    def get_option_quotes(
        self,
        symbols: list[str],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> dict[str, list[dict]]:
        """Get historical quotes for option contracts.

        NOTE: Historical option quotes API is not available in alpaca-py v0.43.2.
        This method will estimate quotes from option bars as a fallback.

        For real-time quotes, use get_option_latest_quote() instead.

        Args:
            symbols: List of option contract symbols.
            start: Start datetime (default: 1 day ago).
            end: End datetime (default: now).
            limit: Maximum quotes per symbol.

        Returns:
            Dictionary mapping symbols to list of quote dicts (estimated from bars).
        """
        logger.warning(
            "Historical option quotes not available in current alpaca-py version. "
            "Estimating from option bars. Use get_option_latest_quote() for real-time data."
        )

        if start is None:
            start = datetime.now() - timedelta(days=1)
        if end is None:
            end = datetime.now()

        results = {}

        try:
            # Fallback: Get bars and estimate bid/ask from OHLC
            bars_data = self.get_option_bars(
                symbols=symbols,
                timeframe="1h",
                start=start,
                end=end,
                limit=limit,
            )

            for symbol in symbols:
                if symbol in bars_data:
                    symbol_quotes = []
                    for bar in bars_data[symbol]:
                        # Estimate bid/ask from high/low
                        mid = (bar['high'] + bar['low']) / 2
                        spread = (bar['high'] - bar['low']) / 2
                        symbol_quotes.append({
                            "timestamp": bar['timestamp'],
                            "bid_price": mid - spread,
                            "ask_price": mid + spread,
                            "bid_size": 0,  # Not available
                            "ask_size": 0,  # Not available
                        })
                    results[symbol] = symbol_quotes

        except Exception as e:
            logger.error(f"Failed to estimate option quotes from bars: {e}")

        return results

    def get_option_bars(
        self,
        symbols: list[str],
        timeframe: str = "1d",
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> dict[str, list[dict]]:
        """Get historical bar data for option contracts.

        Args:
            symbols: List of option contract symbols.
            timeframe: Bar timeframe (e.g., "1h", "1d").
            start: Start datetime.
            end: End datetime.
            limit: Maximum bars per symbol.

        Returns:
            Dictionary mapping symbols to list of bar dicts.
        """
        if start is None:
            start = datetime.now() - timedelta(days=30)
        if end is None:
            end = datetime.now()

        tf_map = {
            "1min": TimeFrame(1, TimeFrameUnit.Minute),
            "5min": TimeFrame(5, TimeFrameUnit.Minute),
            "15min": TimeFrame(15, TimeFrameUnit.Minute),
            "1h": TimeFrame(1, TimeFrameUnit.Hour),
            "1d": TimeFrame(1, TimeFrameUnit.Day),
        }
        tf = tf_map.get(timeframe.lower(), TimeFrame(1, TimeFrameUnit.Day))

        results = {}

        try:
            request = OptionBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=tf,
                start=start,
                end=end,
                limit=limit,
            )
            bars_data = self._data_client.get_option_bars(request)

            for symbol in symbols:
                symbol_bars = bars_data.get(symbol, [])
                results[symbol] = [
                    {
                        "timestamp": bar.timestamp,
                        "open": float(bar.open),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": int(bar.volume),
                        "vwap": float(bar.vwap) if bar.vwap else None,
                    }
                    for bar in symbol_bars
                ]

        except Exception as e:
            logger.error(f"Failed to get option bars: {e}")

        return results

    def get_expirations(
        self,
        underlying: str,
        min_dte: int = 0,
        max_dte: int = 365,
    ) -> list[datetime]:
        """Get available expiration dates for an underlying.

        Args:
            underlying: Underlying symbol.
            min_dte: Minimum days to expiration.
            max_dte: Maximum days to expiration.

        Returns:
            Sorted list of expiration dates.
        """
        now = datetime.now()
        contracts = self.get_option_contracts(
            underlying=underlying,
            expiration_date_gte=now + timedelta(days=min_dte),
            expiration_date_lte=now + timedelta(days=max_dte),
        )

        expirations = set()
        for contract in contracts:
            exp = contract.get("expiration")
            if exp:
                expirations.add(exp)

        return sorted(list(expirations))

    def get_strikes(
        self,
        underlying: str,
        expiration: datetime,
        option_type: Optional[str] = None,
    ) -> list[float]:
        """Get available strike prices for an underlying and expiration.

        Args:
            underlying: Underlying symbol.
            expiration: Expiration date.
            option_type: Optional filter for "call" or "put".

        Returns:
            Sorted list of strike prices.
        """
        contracts = self.get_option_contracts(
            underlying=underlying,
            expiration_date=expiration,
            option_type=option_type,
        )

        strikes = set()
        for contract in contracts:
            strike = contract.get("strike")
            if strike:
                strikes.add(strike)

        return sorted(list(strikes))

    def calculate_iv_rank(
        self,
        underlying: str,
        current_iv: float,
        lookback_days: int = 252,
    ) -> Optional[float]:
        """Calculate IV rank for an underlying.

        IV Rank = (Current IV - 52w Low IV) / (52w High IV - 52w Low IV) * 100

        Args:
            underlying: Underlying symbol.
            current_iv: Current implied volatility.
            lookback_days: Number of days to look back.

        Returns:
            IV rank as percentage (0-100) or None.
        """
        # This would require historical IV data
        # For now, return None - will be implemented with data storage
        logger.warning("IV rank calculation requires historical IV data storage")
        return None

    # Streaming methods

    async def subscribe_option_quotes(self, symbols: list[str]) -> None:
        """Subscribe to real-time option quote updates."""
        if self._stream_client is None:
            logger.warning("Option stream client not configured")
            return

        try:
            self._stream_client.subscribe_quotes(self._handle_quote, *symbols)
            logger.info(f"Subscribed to option quotes: {symbols}")
        except Exception as e:
            logger.error(f"Failed to subscribe to option quotes: {e}")

    async def subscribe_option_trades(self, symbols: list[str]) -> None:
        """Subscribe to real-time option trade updates."""
        if self._stream_client is None:
            logger.warning("Option stream client not configured")
            return

        try:
            self._stream_client.subscribe_trades(self._handle_trade, *symbols)
            logger.info(f"Subscribed to option trades: {symbols}")
        except Exception as e:
            logger.error(f"Failed to subscribe to option trades: {e}")

    async def _handle_quote(self, quote_data) -> None:
        """Handle incoming option quote from stream."""
        logger.debug(f"Option quote: {quote_data.symbol} bid={quote_data.bid_price} ask={quote_data.ask_price}")

    async def _handle_trade(self, trade_data) -> None:
        """Handle incoming option trade from stream."""
        logger.debug(f"Option trade: {trade_data.symbol} price={trade_data.price} size={trade_data.size}")
