"""DoltHub historical options data fetcher for backtesting.

This module provides:
- Fetching real historical options data from DoltHub free database
- Converting DoltHub data to internal OptionChain format
- Caching to minimize queries
- Support for 2019-2024 options data (2,098 symbols)

DoltHub Database: post-no-preference/options
Coverage: 2019-01-01 to 2024-12-31, 2,098 symbols
Source: https://www.dolthub.com/repositories/post-no-preference/options
"""

import logging
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
import json

import pandas as pd
import numpy as np

from alpaca_options.strategies.base import OptionChain, OptionContract

logger = logging.getLogger(__name__)

# DoltHub database info
DOLTHUB_REPO = "post-no-preference/options"
DOLTHUB_DATA_START = datetime(2019, 1, 1)
DOLTHUB_DATA_END = datetime(2024, 12, 31)


class DoltHubOptionsDataFetcher:
    """Fetches historical options data from DoltHub free database.

    Features:
    - Fetches option chains with Greeks and IV from DoltHub
    - Caches data locally to reduce queries
    - Converts to internal OptionChain format
    - Supports 2019-2024 data for 2,098 symbols

    Requirements:
    - Dolt CLI installed (https://docs.dolthub.com/introduction/installation)
    - Clone command: dolt clone post-no-preference/options
    """

    def __init__(
        self,
        dolt_dir: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
    ) -> None:
        """Initialize the fetcher.

        Args:
            dolt_dir: Directory where DoltHub repo is cloned.
            cache_dir: Directory for caching data.
        """
        self._dolt_dir = dolt_dir or Path("./data/dolthub/options")
        self._cache_dir = cache_dir or Path("./data/dolthub_cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Check if Dolt is installed
        if not self._check_dolt_installed():
            raise RuntimeError(
                "Dolt CLI not installed. Install from: https://docs.dolthub.com/introduction/installation"
            )

        # Check if repo is cloned
        if not self._dolt_dir.exists():
            logger.info(f"DoltHub repo not found at {self._dolt_dir}")
            logger.info(f"Cloning {DOLTHUB_REPO}...")
            self._clone_repo()

        logger.info("DoltHubOptionsDataFetcher initialized")

    def _check_dolt_installed(self) -> bool:
        """Check if Dolt CLI is installed."""
        try:
            result = subprocess.run(
                ["dolt", "version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def _clone_repo(self) -> None:
        """Clone the DoltHub options repository."""
        self._dolt_dir.parent.mkdir(parents=True, exist_ok=True)

        try:
            subprocess.run(
                ["dolt", "clone", DOLTHUB_REPO, str(self._dolt_dir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutes for clone
            )
            logger.info(f"Successfully cloned {DOLTHUB_REPO}")
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to clone DoltHub repo: {e.stderr}")

    def _run_dolt_sql(self, query: str) -> pd.DataFrame:
        """Run SQL query on DoltHub database.

        Args:
            query: SQL query to execute.

        Returns:
            DataFrame with query results.
        """
        try:
            result = subprocess.run(
                ["dolt", "sql", "-q", query, "-r", "csv"],
                cwd=self._dolt_dir,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )

            # Parse CSV output
            from io import StringIO
            df = pd.read_csv(StringIO(result.stdout))
            return df

        except subprocess.CalledProcessError as e:
            logger.error(f"Dolt SQL query failed: {e.stderr}")
            return pd.DataFrame()

    def fetch_underlying_bars(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: str = "1Hour",
    ) -> pd.DataFrame:
        """Fetch historical bars for underlying stock.

        Note: DoltHub doesn't have underlying price data, so we use Alpaca for this.
        This method is provided for compatibility but requires Alpaca API.

        Args:
            symbol: Stock symbol (e.g., 'QQQ').
            start_date: Start date.
            end_date: End date.
            timeframe: Bar timeframe.

        Returns:
            DataFrame with OHLCV data.
        """
        logger.warning(
            "DoltHub doesn't provide underlying price data. "
            "Use AlpacaOptionsDataFetcher.fetch_underlying_bars() instead."
        )
        return pd.DataFrame()

    def fetch_option_chain(
        self,
        underlying: str,
        as_of_date: datetime,
    ) -> Optional[OptionChain]:
        """Fetch historical option chain for a specific date.

        Args:
            underlying: Underlying symbol (e.g., 'QQQ').
            as_of_date: Date to fetch chain for.

        Returns:
            OptionChain with contracts, or None if no data.
        """
        # Check cache first
        cache_key = f"{underlying}_{as_of_date.date()}"
        cache_file = self._cache_dir / f"{cache_key}_chain.json"

        if cache_file.exists():
            logger.debug(f"Loading cached chain: {cache_key}")
            with open(cache_file, "r") as f:
                data = json.load(f)
                return self._json_to_option_chain(data)

        # Check if date is in DoltHub range
        if as_of_date < DOLTHUB_DATA_START or as_of_date > DOLTHUB_DATA_END:
            logger.warning(
                f"Date {as_of_date.date()} outside DoltHub range "
                f"({DOLTHUB_DATA_START.date()} to {DOLTHUB_DATA_END.date()})"
            )
            return None

        logger.info(f"Fetching DoltHub chain for {underlying} on {as_of_date.date()}")

        # Query DoltHub for option chain
        # DoltHub schema: date, act_symbol, expiration, strike, call_put,
        #                 bid, ask, vol (implied volatility),
        #                 delta, gamma, theta, vega, rho
        # Note: No last, volume, open_interest in this database
        query = f"""
        SELECT
            date,
            act_symbol,
            expiration,
            strike,
            call_put,
            bid,
            ask,
            vol,
            delta,
            gamma,
            theta,
            vega,
            rho
        FROM option_chain
        WHERE act_symbol = '{underlying}'
          AND date = '{as_of_date.date()}'
        ORDER BY expiration, strike
        """

        df = self._run_dolt_sql(query)

        if df.empty:
            logger.warning(f"No DoltHub data for {underlying} on {as_of_date.date()}")
            return None

        # Convert to OptionChain
        chain = self._dataframe_to_option_chain(df, underlying, as_of_date)

        # Cache the result
        if chain:
            with open(cache_file, "w") as f:
                json.dump(self._option_chain_to_json(chain), f)

        return chain

    def _dataframe_to_option_chain(
        self,
        df: pd.DataFrame,
        underlying: str,
        as_of_date: datetime,
    ) -> Optional[OptionChain]:
        """Convert DoltHub DataFrame to OptionChain.

        Args:
            df: DataFrame with DoltHub option data.
            underlying: Underlying symbol.
            as_of_date: Quote date.

        Returns:
            OptionChain object.
        """
        if df.empty:
            return None

        contracts = []

        for _, row in df.iterrows():
            try:
                # Parse expiration date
                expiration = pd.to_datetime(row["expiration"])

                # Calculate days to expiry
                days_to_expiry = (expiration - as_of_date).days

                # Build contract symbol (OCC format)
                # Format: SYMBOL + YY + MM + DD + C/P + STRIKE (8 digits)
                exp_str = expiration.strftime("%y%m%d")
                strike_str = f"{int(float(row['strike']) * 1000):08d}"
                # DoltHub uses "Call" / "Put" format - convert to lowercase for consistency
                option_type = str(row["call_put"]).lower()
                contract_symbol = f"{underlying}{exp_str}{option_type[0].upper()}{strike_str}"

                # Create contract
                # Note: DoltHub lacks last, volume, open_interest - setting defaults
                contract = OptionContract(
                    symbol=contract_symbol,
                    underlying=underlying,
                    expiration=expiration,
                    strike=float(row["strike"]),
                    option_type=option_type,
                    bid=float(row["bid"]) if pd.notna(row["bid"]) else 0.0,
                    ask=float(row["ask"]) if pd.notna(row["ask"]) else 0.0,
                    last=0.0,  # Not available in DoltHub
                    volume=0,  # Not available in DoltHub
                    open_interest=0,  # Not available in DoltHub
                    implied_volatility=float(row["vol"]) if pd.notna(row["vol"]) else None,
                    delta=float(row["delta"]) if pd.notna(row["delta"]) else None,
                    gamma=float(row["gamma"]) if pd.notna(row["gamma"]) else None,
                    theta=float(row["theta"]) if pd.notna(row["theta"]) else None,
                    vega=float(row["vega"]) if pd.notna(row["vega"]) else None,
                    rho=float(row["rho"]) if pd.notna(row["rho"]) else None,
                    _as_of_date=as_of_date,
                )

                contracts.append(contract)

            except Exception as e:
                logger.warning(f"Failed to parse contract row: {e}")
                continue

        if not contracts:
            return None

        return OptionChain(
            underlying=underlying,
            underlying_price=0.0,  # Not available in DoltHub, will be provided by backtest engine
            timestamp=as_of_date,
            contracts=contracts,
        )

    def _option_chain_to_json(self, chain: OptionChain) -> dict:
        """Convert OptionChain to JSON for caching."""
        return {
            "underlying": chain.underlying,
            "underlying_price": chain.underlying_price,
            "timestamp": chain.timestamp.isoformat(),
            "contracts": [
                {
                    "symbol": c.symbol,
                    "underlying": c.underlying,
                    "expiration": c.expiration.isoformat(),
                    "strike": c.strike,
                    "option_type": c.option_type,
                    "bid": c.bid,
                    "ask": c.ask,
                    "last": c.last,
                    "volume": c.volume,
                    "open_interest": c.open_interest,
                    "implied_volatility": c.implied_volatility,
                    "delta": c.delta,
                    "gamma": c.gamma,
                    "theta": c.theta,
                    "vega": c.vega,
                    "rho": c.rho,
                }
                for c in chain.contracts
            ],
        }

    def _json_to_option_chain(self, data: dict) -> OptionChain:
        """Convert cached JSON to OptionChain."""
        contracts = [
            OptionContract(
                symbol=c["symbol"],
                underlying=c["underlying"],
                expiration=pd.to_datetime(c["expiration"]),
                strike=c["strike"],
                option_type=c["option_type"],
                bid=c["bid"],
                ask=c["ask"],
                last=c["last"],
                volume=c["volume"],
                open_interest=c["open_interest"],
                implied_volatility=c["implied_volatility"],
                delta=c["delta"],
                gamma=c["gamma"],
                theta=c["theta"],
                vega=c["vega"],
                rho=c["rho"],
                _as_of_date=pd.to_datetime(data["timestamp"]),
            )
            for c in data["contracts"]
        ]

        return OptionChain(
            underlying=data["underlying"],
            underlying_price=data.get("underlying_price", 0.0),
            timestamp=pd.to_datetime(data["timestamp"]),
            contracts=contracts,
        )

    def get_available_dates(
        self,
        underlying: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[datetime]:
        """Get list of dates with available data for a symbol.

        Args:
            underlying: Underlying symbol.
            start_date: Start date.
            end_date: End date.

        Returns:
            List of dates with available data.
        """
        query = f"""
        SELECT DISTINCT date
        FROM option_chain
        WHERE act_symbol = '{underlying}'
          AND date >= '{start_date.date()}'
          AND date <= '{end_date.date()}'
        ORDER BY date
        """

        df = self._run_dolt_sql(query)

        if df.empty:
            return []

        return [pd.to_datetime(d).to_pydatetime() for d in df["date"]]
