"""Alpaca historical options data fetcher for backtesting.

This module provides:
- Fetching real historical options data from Alpaca API
- Converting Alpaca data to internal OptionChain format
- Caching to minimize API calls
- Fallback to synthetic data for dates before Feb 2024
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import json

import pandas as pd

from alpaca.data.historical.option import OptionHistoricalDataClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import (
    OptionBarsRequest,
    OptionChainRequest,
    OptionSnapshotRequest,
    StockBarsRequest,
)
from alpaca.data.timeframe import TimeFrame

from alpaca_options.strategies.base import OptionChain, OptionContract

logger = logging.getLogger(__name__)

# Alpaca only has options data from Feb 2024
ALPACA_OPTIONS_DATA_START = datetime(2024, 2, 1)


class AlpacaOptionsDataFetcher:
    """Fetches historical options data from Alpaca API.

    Features:
    - Fetches option chains with Greeks and IV
    - Caches data locally to reduce API calls
    - Handles rate limiting
    - Converts to internal OptionChain format
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        cache_dir: Optional[Path] = None,
    ) -> None:
        """Initialize the fetcher.

        Args:
            api_key: Alpaca API key.
            api_secret: Alpaca API secret.
            cache_dir: Directory for caching data.
        """
        self._api_key = api_key
        self._api_secret = api_secret

        # Initialize clients
        self._option_client = OptionHistoricalDataClient(
            api_key=api_key,
            secret_key=api_secret,
        )
        self._stock_client = StockHistoricalDataClient(
            api_key=api_key,
            secret_key=api_secret,
        )

        # Setup cache
        self._cache_dir = cache_dir or Path("./data/alpaca_cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info("AlpacaOptionsDataFetcher initialized")

    def fetch_underlying_bars(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1Hour",
    ) -> pd.DataFrame:
        """Fetch historical bars for underlying stock.

        Args:
            symbol: Stock symbol (e.g., 'SPY').
            start_date: Start date.
            end_date: End date.
            timeframe: Bar timeframe ('1Min', '1Hour', '1Day').

        Returns:
            DataFrame with OHLCV data.
        """
        cache_file = self._cache_dir / f"{symbol}_bars_{start_date.date()}_{end_date.date()}_{timeframe}.parquet"

        # Check cache
        if cache_file.exists():
            logger.info(f"Loading cached bars from {cache_file}")
            df = pd.read_parquet(cache_file)
            return df

        # Map timeframe string to TimeFrame enum
        tf_map = {
            "1Min": TimeFrame.Minute,
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day,
        }
        tf = tf_map.get(timeframe, TimeFrame.Hour)

        logger.info(f"Fetching {symbol} bars from Alpaca ({start_date.date()} to {end_date.date()})")

        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            start=start_date,
            end=end_date,
            timeframe=tf,
        )

        bars = self._stock_client.get_stock_bars(request)

        # Convert to DataFrame
        if symbol in bars.data:
            bar_list = bars.data[symbol]
            records = []
            for bar in bar_list:
                records.append({
                    "timestamp": bar.timestamp,
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": int(bar.volume),
                })

            df = pd.DataFrame(records)
            df.set_index("timestamp", inplace=True)

            # Make timezone-naive
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            # Cache the data
            df.to_parquet(cache_file)
            logger.info(f"Cached {len(df)} bars to {cache_file}")

            return df

        return pd.DataFrame()

    def fetch_option_chain(
        self,
        underlying: str,
        as_of_date: datetime,
    ) -> Optional[OptionChain]:
        """Fetch option chain for a specific date.

        Args:
            underlying: Underlying symbol (e.g., 'SPY').
            as_of_date: Date to fetch chain for.

        Returns:
            OptionChain or None if not available.
        """
        # Check if date is before Alpaca data availability
        if as_of_date < ALPACA_OPTIONS_DATA_START:
            logger.debug(f"Date {as_of_date.date()} is before Alpaca options data start")
            return None

        cache_file = self._cache_dir / "chains" / underlying / f"{as_of_date.strftime('%Y%m%d_%H%M')}.json"

        # Check cache
        if cache_file.exists():
            return self._load_chain_from_cache(cache_file, underlying)

        logger.info(f"Fetching {underlying} option chain for {as_of_date}")

        try:
            # Fetch the option chain
            request = OptionChainRequest(
                underlying_symbol=underlying,
            )

            chain_data = self._option_client.get_option_chain(request)

            if not chain_data:
                logger.warning(f"No option chain data for {underlying}")
                return None

            # Get current underlying price (from the first contract's underlying price)
            underlying_price = None
            contracts = []

            for symbol, snapshot in chain_data.items():
                # Extract underlying price from snapshot if available
                if underlying_price is None and hasattr(snapshot, 'underlying_price'):
                    underlying_price = float(snapshot.underlying_price) if snapshot.underlying_price else None

                contract = self._convert_snapshot_to_contract(
                    symbol=symbol,
                    snapshot=snapshot,
                    underlying=underlying,
                )
                if contract:
                    contracts.append(contract)

            if not contracts:
                logger.warning(f"No valid contracts in chain for {underlying}")
                return None

            # If we couldn't get underlying price from options, fetch it separately
            if underlying_price is None:
                underlying_price = self._get_underlying_price(underlying, as_of_date)

            chain = OptionChain(
                underlying=underlying,
                underlying_price=underlying_price or 0.0,
                timestamp=as_of_date,
                contracts=contracts,
            )

            # Cache the chain
            self._cache_chain(cache_file, chain)

            logger.info(f"Fetched chain with {len(contracts)} contracts")
            return chain

        except Exception as e:
            logger.error(f"Error fetching option chain: {e}")
            return None

    def fetch_option_chains_for_period(
        self,
        underlying: str,
        start_date: datetime,
        end_date: datetime,
        interval_hours: int = 1,
    ) -> dict[datetime, OptionChain]:
        """Fetch option chains for a date range.

        Note: Alpaca doesn't have true historical option chains.
        We can only get the current chain, so for backtesting we need
        to either:
        1. Fetch and cache chains in real-time going forward
        2. Use synthetic data for historical periods
        3. Use option bars/trades to reconstruct approximate chains

        Args:
            underlying: Underlying symbol.
            start_date: Start date.
            end_date: End date.
            interval_hours: Hours between snapshots.

        Returns:
            Dict mapping timestamp to OptionChain.
        """
        chains: dict[datetime, OptionChain] = {}

        # Check if the entire period is before Alpaca data availability
        if end_date < ALPACA_OPTIONS_DATA_START:
            logger.warning(
                f"Requested period ({start_date.date()} to {end_date.date()}) "
                f"is before Alpaca options data availability (Feb 2024)"
            )
            return chains

        # Adjust start date if before data availability
        effective_start = max(start_date, ALPACA_OPTIONS_DATA_START)

        # Try to load from cache first
        cache_dir = self._cache_dir / "chains" / underlying
        if cache_dir.exists():
            for cache_file in sorted(cache_dir.glob("*.json")):
                try:
                    # Parse timestamp from filename
                    timestamp = datetime.strptime(cache_file.stem, "%Y%m%d_%H%M")

                    if effective_start <= timestamp <= end_date:
                        chain = self._load_chain_from_cache(cache_file, underlying)
                        if chain:
                            chains[timestamp] = chain
                except Exception as e:
                    logger.debug(f"Error loading cache file {cache_file}: {e}")

        logger.info(f"Loaded {len(chains)} cached option chains for {underlying}")

        return chains

    def fetch_option_bars(
        self,
        contract_symbols: list[str],
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1Hour",
    ) -> pd.DataFrame:
        """Fetch historical bars for specific option contracts.

        Args:
            contract_symbols: List of option contract symbols.
            start_date: Start date.
            end_date: End date.
            timeframe: Bar timeframe.

        Returns:
            DataFrame with OHLCV data for each contract.
        """
        if start_date < ALPACA_OPTIONS_DATA_START:
            logger.warning("Requested start date before Alpaca options data availability")
            start_date = ALPACA_OPTIONS_DATA_START

        tf_map = {
            "1Min": TimeFrame.Minute,
            "1Hour": TimeFrame.Hour,
            "1Day": TimeFrame.Day,
        }
        tf = tf_map.get(timeframe, TimeFrame.Hour)

        logger.info(f"Fetching option bars for {len(contract_symbols)} contracts")

        request = OptionBarsRequest(
            symbol_or_symbols=contract_symbols,
            start=start_date,
            end=end_date,
            timeframe=tf,
        )

        bars = self._option_client.get_option_bars(request)

        records = []
        for symbol, bar_list in bars.data.items():
            for bar in bar_list:
                records.append({
                    "symbol": symbol,
                    "timestamp": bar.timestamp,
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": int(bar.volume),
                })

        df = pd.DataFrame(records)
        if not df.empty:
            df.set_index(["symbol", "timestamp"], inplace=True)

        return df

    def _convert_snapshot_to_contract(
        self,
        symbol: str,
        snapshot,
        underlying: str,
    ) -> Optional[OptionContract]:
        """Convert Alpaca option snapshot to OptionContract."""
        try:
            # Parse contract symbol to extract details
            # Format: AAPL240315C00175000
            # Symbol + YYMMDD + C/P + Strike*1000 (8 digits)

            # Find where the date starts (first digit after letters)
            date_start = 0
            for i, char in enumerate(symbol):
                if char.isdigit():
                    date_start = i
                    break

            underlying_sym = symbol[:date_start]
            date_str = symbol[date_start:date_start+6]
            option_type = "call" if symbol[date_start+6] == "C" else "put"
            strike = int(symbol[date_start+7:]) / 1000

            # Parse expiration
            expiration = datetime.strptime(date_str, "%y%m%d")
            expiration = expiration.replace(hour=16, minute=0)

            # Get quote data
            latest_quote = snapshot.latest_quote if hasattr(snapshot, 'latest_quote') else None
            latest_trade = snapshot.latest_trade if hasattr(snapshot, 'latest_trade') else None
            greeks = snapshot.greeks if hasattr(snapshot, 'greeks') else None

            bid = 0.0
            ask = 0.0
            last = 0.0
            volume = 0

            if latest_quote:
                bid = float(latest_quote.bid_price) if latest_quote.bid_price else 0.0
                ask = float(latest_quote.ask_price) if latest_quote.ask_price else 0.0

            if latest_trade:
                last = float(latest_trade.price) if latest_trade.price else 0.0
                volume = int(latest_trade.size) if latest_trade.size else 0

            # Use mid price if last is not available
            if last == 0.0 and bid > 0 and ask > 0:
                last = (bid + ask) / 2

            # Skip contracts with no pricing
            if bid == 0 and ask == 0 and last == 0:
                return None

            delta = None
            gamma = None
            theta = None
            vega = None
            iv = None

            if greeks:
                delta = float(greeks.delta) if greeks.delta else None
                gamma = float(greeks.gamma) if greeks.gamma else None
                theta = float(greeks.theta) if greeks.theta else None
                vega = float(greeks.vega) if greeks.vega else None

            if hasattr(snapshot, 'implied_volatility') and snapshot.implied_volatility:
                iv = float(snapshot.implied_volatility)

            # Get open interest if available
            open_interest = 0
            if hasattr(snapshot, 'open_interest') and snapshot.open_interest:
                open_interest = int(snapshot.open_interest)

            return OptionContract(
                symbol=symbol,
                underlying=underlying_sym,
                option_type=option_type,
                strike=strike,
                expiration=expiration,
                bid=bid,
                ask=ask,
                last=last,
                volume=volume,
                open_interest=open_interest,
                delta=delta,
                gamma=gamma,
                theta=theta,
                vega=vega,
                implied_volatility=iv,
            )

        except Exception as e:
            logger.debug(f"Error converting snapshot {symbol}: {e}")
            return None

    def _get_underlying_price(self, symbol: str, as_of_date: datetime) -> float:
        """Get underlying stock price for a given date."""
        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                start=as_of_date - timedelta(days=1),
                end=as_of_date + timedelta(days=1),
                timeframe=TimeFrame.Hour,
            )

            bars = self._stock_client.get_stock_bars(request)

            if symbol in bars.data and bars.data[symbol]:
                # Get the closest bar to our target date
                bar_list = bars.data[symbol]
                closest_bar = min(
                    bar_list,
                    key=lambda b: abs((b.timestamp.replace(tzinfo=None) - as_of_date).total_seconds())
                )
                return float(closest_bar.close)

        except Exception as e:
            logger.warning(f"Error fetching underlying price: {e}")

        return 0.0

    def _cache_chain(self, cache_file: Path, chain: OptionChain) -> None:
        """Save option chain to cache."""
        cache_file.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "underlying": chain.underlying,
            "underlying_price": chain.underlying_price,
            "timestamp": chain.timestamp.isoformat(),
            "contracts": [
                {
                    "symbol": c.symbol,
                    "underlying": c.underlying,
                    "option_type": c.option_type,
                    "strike": c.strike,
                    "expiration": c.expiration.isoformat(),
                    "bid": c.bid,
                    "ask": c.ask,
                    "last": c.last,
                    "volume": c.volume,
                    "open_interest": c.open_interest,
                    "delta": c.delta,
                    "gamma": c.gamma,
                    "theta": c.theta,
                    "vega": c.vega,
                    "implied_volatility": c.implied_volatility,
                }
                for c in chain.contracts
            ],
        }

        with open(cache_file, "w") as f:
            json.dump(data, f, indent=2)

    def _load_chain_from_cache(self, cache_file: Path, underlying: str) -> Optional[OptionChain]:
        """Load option chain from cache."""
        try:
            with open(cache_file) as f:
                data = json.load(f)

            contracts = []
            for c in data["contracts"]:
                contract = OptionContract(
                    symbol=c["symbol"],
                    underlying=c["underlying"],
                    option_type=c["option_type"],
                    strike=c["strike"],
                    expiration=datetime.fromisoformat(c["expiration"]),
                    bid=c["bid"],
                    ask=c["ask"],
                    last=c["last"],
                    volume=c.get("volume", 0),
                    open_interest=c.get("open_interest", 0),
                    delta=c.get("delta"),
                    gamma=c.get("gamma"),
                    theta=c.get("theta"),
                    vega=c.get("vega"),
                    implied_volatility=c.get("implied_volatility"),
                )
                contracts.append(contract)

            return OptionChain(
                underlying=data["underlying"],
                underlying_price=data["underlying_price"],
                timestamp=datetime.fromisoformat(data["timestamp"]),
                contracts=contracts,
            )

        except Exception as e:
            logger.debug(f"Error loading cache {cache_file}: {e}")
            return None

    def is_data_available(self, date: datetime) -> bool:
        """Check if Alpaca has options data for a given date.

        Args:
            date: Date to check.

        Returns:
            True if data should be available.
        """
        return date >= ALPACA_OPTIONS_DATA_START
