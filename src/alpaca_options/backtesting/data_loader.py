"""Data loading utilities for backtesting.

This module provides:
- Historical options data loading and caching
- Integration with Alpaca historical options data (Feb 2024+)
- Data validation and preprocessing

NOTE: Synthetic data generation has been removed. Use only real historical data.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from alpaca_options.core.config import BacktestDataConfig
from alpaca_options.strategies.base import OptionChain, OptionContract

logger = logging.getLogger(__name__)

# Alpaca options data availability
ALPACA_OPTIONS_DATA_START = datetime(2024, 2, 1)


class BacktestDataLoader:
    """Loads and manages historical data for backtesting.

    Supports:
    - Loading from CSV/Parquet files
    - Real Alpaca historical options data (Feb 2024+)
    - Data caching

    NOTE: Synthetic options data generation has been removed.
    Only real historical data is supported.
    """

    def __init__(
        self,
        config: BacktestDataConfig,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
    ) -> None:
        self._config = config
        self._cache_dir = Path(config.cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Alpaca credentials for real data
        self._api_key = api_key or os.environ.get("ALPACA_API_KEY", "")
        self._api_secret = api_secret or os.environ.get("ALPACA_SECRET_KEY", "")
        self._alpaca_fetcher = None

        # Try to initialize Alpaca fetcher if credentials available
        if self._api_key and self._api_secret:
            try:
                from alpaca_options.backtesting.alpaca_options_fetcher import (
                    AlpacaOptionsDataFetcher,
                )
                self._alpaca_fetcher = AlpacaOptionsDataFetcher(
                    api_key=self._api_key,
                    api_secret=self._api_secret,
                    cache_dir=self._cache_dir / "alpaca",
                )
                logger.info("Alpaca options data fetcher initialized")
            except Exception as e:
                logger.warning(f"Could not initialize Alpaca fetcher: {e}")

    def load_underlying_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1h",
    ) -> pd.DataFrame:
        """Load historical price data for an underlying.

        Uses Alpaca API if credentials available, otherwise falls back
        to local CSV files.

        Args:
            symbol: The stock symbol.
            start_date: Start date for data.
            end_date: End date for data.
            timeframe: Bar timeframe.

        Returns:
            DataFrame with OHLCV data indexed by datetime.
        """
        # Try Alpaca first if available
        if self._alpaca_fetcher:
            try:
                tf_map = {"1h": "1Hour", "1d": "1Day", "1m": "1Min"}
                alpaca_tf = tf_map.get(timeframe.lower(), "1Hour")

                df = self._alpaca_fetcher.fetch_underlying_bars(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    timeframe=alpaca_tf,
                )
                if not df.empty:
                    logger.info(f"Loaded {len(df)} bars for {symbol} from Alpaca")
                    return df
            except Exception as e:
                logger.warning(f"Could not fetch from Alpaca: {e}")

        # Fall back to local data file
        data_file = self._cache_dir / f"{symbol}.csv"
        if data_file.exists():
            logger.info(f"Loading data from {data_file}")
            df = pd.read_csv(data_file, parse_dates=["timestamp"])
            df.set_index("timestamp", inplace=True)

            # Make index timezone-naive for comparison
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            # Make start/end dates timezone-naive
            start_naive = start_date.replace(tzinfo=None) if start_date.tzinfo else start_date
            end_naive = end_date.replace(tzinfo=None) if end_date.tzinfo else end_date

            # Filter by date range
            df = df[(df.index >= start_naive) & (df.index <= end_naive)]

            logger.info(f"Loaded {len(df)} bars for {symbol}")
            return df

        logger.warning(
            f"No data found for {symbol}. "
            f"Please add data file to {self._cache_dir}"
        )
        return pd.DataFrame()

    def load_options_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[datetime, OptionChain]:
        """Load historical options data from files.

        Args:
            symbol: The underlying symbol.
            start_date: Start date.
            end_date: End date.

        Returns:
            Dict mapping timestamp to OptionChain.
        """
        options_dir = self._cache_dir / "options" / symbol

        if not options_dir.exists():
            logger.warning(
                f"No options data directory found at {options_dir}. "
                f"Only real historical data is supported."
            )
            return {}

        options_data: dict[datetime, OptionChain] = {}

        for file in sorted(options_dir.glob("*.parquet")):
            try:
                df = pd.read_parquet(file)

                # Parse timestamp from filename
                timestamp = datetime.strptime(file.stem, "%Y%m%d_%H%M%S")

                if not (start_date <= timestamp <= end_date):
                    continue

                # Convert DataFrame to OptionChain
                contracts = []
                for _, row in df.iterrows():
                    contract = OptionContract(
                        symbol=row["symbol"],
                        underlying=symbol,
                        option_type=row["option_type"],
                        strike=row["strike"],
                        expiration=pd.to_datetime(row["expiration"]),
                        bid=row["bid"],
                        ask=row["ask"],
                        last=row["last"],
                        volume=int(row.get("volume", 0)),
                        open_interest=int(row.get("open_interest", 0)),
                        delta=row.get("delta"),
                        gamma=row.get("gamma"),
                        theta=row.get("theta"),
                        vega=row.get("vega"),
                        implied_volatility=row.get("implied_volatility"),
                    )
                    contracts.append(contract)

                underlying_price = df["underlying_price"].iloc[0]

                options_data[timestamp] = OptionChain(
                    underlying=symbol,
                    underlying_price=underlying_price,
                    timestamp=timestamp,
                    contracts=contracts,
                )

            except Exception as e:
                logger.error(f"Error loading {file}: {e}")
                continue

        logger.info(f"Loaded {len(options_data)} options snapshots for {symbol}")
        return options_data

    def add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators to underlying data.

        Args:
            df: DataFrame with OHLCV data.

        Returns:
            DataFrame with added technical indicators.
        """
        df = df.copy()

        # Simple Moving Averages
        df["sma_20"] = df["close"].rolling(window=20).mean()
        df["sma_50"] = df["close"].rolling(window=50).mean()

        # RSI
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["rsi_14"] = 100 - (100 / (1 + rs))

        # ATR
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift()).abs()
        low_close = (df["low"] - df["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr_14"] = tr.rolling(window=14).mean()

        # Historical Volatility (20-day)
        df["hv_20"] = df["close"].pct_change().rolling(window=20).std() * np.sqrt(252)

        # IV Rank (simulated based on HV)
        hv_min = df["hv_20"].rolling(window=252).min()
        hv_max = df["hv_20"].rolling(window=252).max()
        df["iv_rank"] = ((df["hv_20"] - hv_min) / (hv_max - hv_min)) * 100

        return df

    @property
    def has_alpaca_credentials(self) -> bool:
        """Check if Alpaca credentials are available."""
        return self._alpaca_fetcher is not None
