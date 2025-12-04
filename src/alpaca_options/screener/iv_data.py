"""Historical implied volatility data management for IV rank calculations."""

import asyncio
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

import pandas as pd
from alpaca.data.requests import OptionSnapshotRequest
from alpaca.trading.requests import GetOptionContractsRequest

logger = logging.getLogger(__name__)


class IVDataManager:
    """Manages historical implied volatility data for IV rank calculations.

    This class handles:
    - Fetching historical IV data from Alpaca
    - Caching IV data to disk (CSV files)
    - Calculating IV rank from historical data
    - Daily updates of IV cache

    IV Rank Formula:
        IV Rank = ((Current IV - 52w Low IV) / (52w High IV - 52w Low IV)) × 100

    Cache Structure:
        data/iv_cache/{symbol}.csv
        Columns: date, implied_volatility, strike, expiration, days_to_expiry
    """

    def __init__(
        self,
        trading_client,
        options_data_client,
        cache_dir: str = "./data/iv_cache",
        min_history_days: int = 252,  # 1 year of trading days
    ):
        """Initialize IV data manager.

        Args:
            trading_client: Alpaca TradingClient for contract lookup.
            options_data_client: Alpaca OptionHistoricalDataClient for snapshots.
            cache_dir: Directory to store IV cache files.
            min_history_days: Minimum days of history required for IV rank.
        """
        self._trading_client = trading_client
        self._options_client = options_data_client
        self._cache_dir = Path(cache_dir)
        self._min_history_days = min_history_days

        # In-memory cache: symbol → DataFrame
        self._iv_history: dict[str, pd.DataFrame] = {}

        # Ensure cache directory exists
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"IV Data Manager initialized with cache dir: {self._cache_dir}")

    def _get_cache_path(self, symbol: str) -> Path:
        """Get cache file path for a symbol."""
        return self._cache_dir / f"{symbol}.csv"

    def _load_from_cache(self, symbol: str) -> Optional[pd.DataFrame]:
        """Load IV history from cache file.

        Args:
            symbol: Stock symbol.

        Returns:
            DataFrame with IV history or None if not cached.
        """
        cache_file = self._get_cache_path(symbol)
        if not cache_file.exists():
            return None

        try:
            df = pd.read_csv(cache_file, parse_dates=['date'])
            logger.debug(f"Loaded {len(df)} IV records from cache for {symbol}")
            return df
        except Exception as e:
            logger.warning(f"Failed to load cache for {symbol}: {e}")
            return None

    def _save_to_cache(self, symbol: str, df: pd.DataFrame) -> None:
        """Save IV history to cache file.

        Args:
            symbol: Stock symbol.
            df: DataFrame with IV history.
        """
        cache_file = self._get_cache_path(symbol)
        try:
            df.to_csv(cache_file, index=False)
            logger.debug(f"Saved {len(df)} IV records to cache for {symbol}")
        except Exception as e:
            logger.error(f"Failed to save cache for {symbol}: {e}")

    async def _fetch_atm_contract(
        self,
        symbol: str,
        target_date: date,
        days_to_expiry: int = 30,
    ) -> Optional[str]:
        """Find ATM contract for a given date.

        Args:
            symbol: Underlying symbol.
            target_date: Date to find contract for.
            days_to_expiry: Target DTE (default: 30).

        Returns:
            Option contract symbol or None.
        """
        try:
            # Calculate expiration window (target_date + DTE ± 7 days)
            exp_min = target_date + timedelta(days=days_to_expiry - 7)
            exp_max = target_date + timedelta(days=days_to_expiry + 7)

            request = GetOptionContractsRequest(
                underlying_symbols=[symbol],
                expiration_date_gte=exp_min,
                expiration_date_lte=exp_max,
                limit=100,
            )

            result = self._trading_client.get_option_contracts(request)
            contracts = result.option_contracts

            if not contracts:
                return None

            # Find ATM call (closest to current price)
            # Note: We don't have historical prices here, so we approximate
            # by taking the middle strike
            strikes = sorted([float(c.strike_price) for c in contracts])
            if not strikes:
                return None

            atm_strike = strikes[len(strikes) // 2]

            # Find call contract with this strike
            for contract in contracts:
                if (
                    float(contract.strike_price) == atm_strike
                    and contract.type.value == "call"
                ):
                    return contract.symbol

            return None

        except Exception as e:
            logger.debug(f"Failed to fetch ATM contract for {symbol} on {target_date}: {e}")
            return None

    async def _fetch_iv_for_date(
        self,
        contract_symbol: str,
    ) -> Optional[float]:
        """Fetch IV for a specific contract.

        Args:
            contract_symbol: Option contract symbol.

        Returns:
            Implied volatility or None.
        """
        try:
            request = OptionSnapshotRequest(symbol_or_symbols=[contract_symbol])
            snapshots = self._options_client.get_option_snapshot(request)

            snap = snapshots.get(contract_symbol)
            if snap and snap.implied_volatility:
                return float(snap.implied_volatility)

            return None

        except Exception as e:
            logger.debug(f"Failed to fetch IV for {contract_symbol}: {e}")
            return None

    async def fetch_historical_iv(
        self,
        symbol: str,
        days: int = 365,
        sample_frequency: int = 7,  # Weekly sampling
    ) -> pd.DataFrame:
        """Fetch historical IV data for a symbol.

        This fetches ATM option IV at regular intervals (weekly by default)
        to build a historical IV dataset.

        Args:
            symbol: Stock symbol.
            days: Number of days of history to fetch.
            sample_frequency: Days between samples (7 = weekly).

        Returns:
            DataFrame with columns: date, implied_volatility
        """
        logger.info(f"Fetching {days} days of IV history for {symbol} (sampling every {sample_frequency} days)")

        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        records = []
        current_date = start_date

        while current_date <= end_date:
            # Find ATM contract for this date
            contract_symbol = await self._fetch_atm_contract(symbol, current_date)

            if contract_symbol:
                # Fetch IV for this contract
                iv = await self._fetch_iv_for_date(contract_symbol)

                if iv is not None:
                    records.append({
                        'date': current_date,
                        'implied_volatility': iv,
                    })
                    logger.debug(f"{symbol} {current_date}: IV = {iv:.3f}")

            # Move to next sample date
            current_date += timedelta(days=sample_frequency)

            # Rate limiting: small delay between requests
            await asyncio.sleep(0.1)

        df = pd.DataFrame(records)
        logger.info(f"Fetched {len(df)} IV data points for {symbol}")

        return df

    async def load_or_fetch_iv_history(self, symbol: str) -> pd.DataFrame:
        """Load IV history from cache or fetch if not available.

        Args:
            symbol: Stock symbol.

        Returns:
            DataFrame with IV history.
        """
        # Try loading from cache first
        df = self._load_from_cache(symbol)

        if df is not None and len(df) >= self._min_history_days / 7:
            # Cache hit and sufficient data
            self._iv_history[symbol] = df
            return df

        # Cache miss or insufficient data - fetch from API
        logger.info(f"IV cache miss for {symbol}, fetching from API")
        df = await self.fetch_historical_iv(symbol, days=365, sample_frequency=7)

        if not df.empty:
            # Save to cache
            self._save_to_cache(symbol, df)
            self._iv_history[symbol] = df

        return df

    def calculate_iv_rank(self, symbol: str, current_iv: float) -> Optional[float]:
        """Calculate IV rank for a symbol.

        IV Rank = ((Current IV - 52w Low) / (52w High - 52w Low)) × 100

        Args:
            symbol: Stock symbol.
            current_iv: Current implied volatility (e.g., 0.32 for 32%).

        Returns:
            IV rank (0-100) or None if insufficient data.
        """
        # Get IV history
        history = self._iv_history.get(symbol)

        if history is None or len(history) < self._min_history_days / 7:
            logger.debug(f"Insufficient IV history for {symbol} to calculate IV rank")
            return None

        # Calculate min/max over the period
        iv_values = history['implied_volatility']
        iv_min = iv_values.min()
        iv_max = iv_values.max()

        # Edge case: no variation in IV
        if iv_max == iv_min:
            return 50.0

        # Calculate IV rank
        iv_rank = ((current_iv - iv_min) / (iv_max - iv_min)) * 100

        # Clamp to 0-100
        iv_rank = max(0.0, min(100.0, iv_rank))

        logger.debug(
            f"{symbol} IV Rank: {iv_rank:.1f} "
            f"(current: {current_iv:.3f}, min: {iv_min:.3f}, max: {iv_max:.3f})"
        )

        return iv_rank

    async def update_iv_cache(self, symbols: list[str]) -> None:
        """Update IV cache for symbols (run daily).

        This fetches the latest IV for each symbol and appends to the cache.

        Args:
            symbols: List of symbols to update.
        """
        logger.info(f"Updating IV cache for {len(symbols)} symbols")

        today = date.today()

        for symbol in symbols:
            try:
                # Load existing cache
                df = self._load_from_cache(symbol)
                if df is None:
                    df = pd.DataFrame(columns=['date', 'implied_volatility'])

                # Check if already updated today
                if not df.empty and df['date'].max() >= pd.Timestamp(today):
                    logger.debug(f"{symbol} IV cache already up to date")
                    continue

                # Fetch today's ATM IV
                contract_symbol = await self._fetch_atm_contract(symbol, today)
                if contract_symbol:
                    iv = await self._fetch_iv_for_date(contract_symbol)

                    if iv is not None:
                        # Append new record
                        new_record = pd.DataFrame([{
                            'date': today,
                            'implied_volatility': iv,
                        }])
                        df = pd.concat([df, new_record], ignore_index=True)

                        # Prune data older than 1 year
                        cutoff = today - timedelta(days=365)
                        df = df[df['date'] >= pd.Timestamp(cutoff)]

                        # Save back to cache
                        self._save_to_cache(symbol, df)

                        # Update in-memory cache
                        self._iv_history[symbol] = df

                        logger.info(f"Updated IV cache for {symbol}: IV = {iv:.3f}")

                # Rate limiting
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Failed to update IV cache for {symbol}: {e}")

        logger.info("IV cache update complete")

    async def backfill_iv_data(
        self,
        symbols: list[str],
        max_concurrent: int = 5,
    ) -> None:
        """Backfill IV data for multiple symbols (run once on setup).

        This is an expensive operation that fetches 1 year of IV data for each symbol.
        Use with caution due to API rate limits.

        Args:
            symbols: List of symbols to backfill.
            max_concurrent: Maximum concurrent requests (default: 5).
        """
        logger.info(f"Backfilling IV data for {len(symbols)} symbols (max {max_concurrent} concurrent)")

        async def backfill_one(symbol: str):
            try:
                await self.load_or_fetch_iv_history(symbol)
            except Exception as e:
                logger.error(f"Failed to backfill IV data for {symbol}: {e}")

        # Process in batches to respect rate limits
        for i in range(0, len(symbols), max_concurrent):
            batch = symbols[i:i + max_concurrent]
            await asyncio.gather(*[backfill_one(sym) for sym in batch])

            # Pause between batches
            if i + max_concurrent < len(symbols):
                logger.info(f"Processed {i + max_concurrent}/{len(symbols)}, pausing...")
                await asyncio.sleep(5)

        logger.info("IV data backfill complete")

    def get_cached_symbols(self) -> list[str]:
        """Get list of symbols with cached IV data."""
        return [f.stem for f in self._cache_dir.glob("*.csv")]

    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """Clear IV cache.

        Args:
            symbol: If provided, clear only this symbol. Otherwise clear all.
        """
        if symbol:
            cache_file = self._get_cache_path(symbol)
            if cache_file.exists():
                cache_file.unlink()
                self._iv_history.pop(symbol, None)
                logger.info(f"Cleared IV cache for {symbol}")
        else:
            for cache_file in self._cache_dir.glob("*.csv"):
                cache_file.unlink()
            self._iv_history.clear()
            logger.info("Cleared all IV cache")

    def get_iv_summary(self, symbol: str) -> Optional[dict]:
        """Get summary statistics for a symbol's IV history.

        Args:
            symbol: Stock symbol.

        Returns:
            Dict with min, max, mean, std, current IV if available.
        """
        history = self._iv_history.get(symbol)
        if history is None or history.empty:
            return None

        iv_values = history['implied_volatility']

        return {
            'symbol': symbol,
            'data_points': len(history),
            'min_iv': float(iv_values.min()),
            'max_iv': float(iv_values.max()),
            'mean_iv': float(iv_values.mean()),
            'std_iv': float(iv_values.std()),
            'latest_date': history['date'].max(),
            'oldest_date': history['date'].min(),
        }
