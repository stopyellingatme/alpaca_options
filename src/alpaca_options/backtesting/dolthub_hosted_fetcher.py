"""DoltHub hosted SQL query fetcher for historical options data.

This module provides:
- Fetching real historical options data from DoltHub's hosted SQL API
- No local clone required - queries run on DoltHub's servers
- Converting DoltHub data to internal OptionChain format
- Caching to minimize API calls
- Support for 2019-2024 options data (2,098 symbols)

DoltHub Database: post-no-preference/options
Coverage: 2019-01-01 to 2024-12-31, 2,098 symbols
Source: https://www.dolthub.com/repositories/post-no-preference/options
API: https://www.dolthub.com/api/v1alpha1/
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List
import json

import pandas as pd
import requests

from alpaca_options.strategies.base import OptionChain, OptionContract

logger = logging.getLogger(__name__)

# DoltHub database info
DOLTHUB_OWNER = "post-no-preference"
DOLTHUB_DATABASE = "options"
DOLTHUB_BRANCH = "main"
DOLTHUB_API_URL = "https://www.dolthub.com/api/v1alpha1"
DOLTHUB_DATA_START = datetime(2019, 1, 1)
DOLTHUB_DATA_END = datetime(2024, 12, 31)


class DoltHubHostedOptionsDataFetcher:
    """Fetches historical options data from DoltHub's hosted SQL API.

    Features:
    - Fetches option chains with Greeks and IV from DoltHub
    - No local clone required - uses hosted API
    - Caches data locally to reduce API calls
    - Converts to internal OptionChain format
    - Supports 2019-2024 data for 2,098 symbols
    - FREE - no API key required

    No Requirements - Just works!
    """

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
    ) -> None:
        """Initialize the fetcher.

        Args:
            cache_dir: Directory for caching data.
        """
        self._cache_dir = cache_dir or Path("./data/dolthub_cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Setup session for connection pooling
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "alpaca-options-bot/1.0",
        })

        logger.info("DoltHubHostedOptionsDataFetcher initialized (using hosted API)")

    def _run_sql_query(self, query: str) -> pd.DataFrame:
        """Run SQL query on DoltHub's hosted database.

        Args:
            query: SQL query to execute.

        Returns:
            DataFrame with query results.
        """
        url = f"{DOLTHUB_API_URL}/{DOLTHUB_OWNER}/{DOLTHUB_DATABASE}/{DOLTHUB_BRANCH}"

        payload = {
            "query": query,
        }

        try:
            response = self._session.post(url, json=payload, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Parse response into DataFrame
            if "rows" in data and len(data["rows"]) > 0:
                # Convert rows to DataFrame
                df = pd.DataFrame(data["rows"])

                # Rename columns using schema if available
                if "schema" in data:
                    column_names = [col["columnName"] for col in data["schema"]]
                    if len(column_names) == len(df.columns):
                        df.columns = column_names

                return df
            else:
                return pd.DataFrame()

        except requests.exceptions.RequestException as e:
            logger.error(f"DoltHub API request failed: {e}")
            return pd.DataFrame()
        except (KeyError, ValueError) as e:
            logger.error(f"Failed to parse DoltHub response: {e}")
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
        # DoltHub schema: quote_date, underlying_symbol, expiration, strike, option_type,
        #                 bid, ask, last, volume, open_interest, implied_volatility,
        #                 delta, gamma, theta, vega, rho
        query = f"""
        SELECT
            quote_date,
            underlying_symbol,
            expiration,
            strike,
            option_type,
            bid,
            ask,
            last,
            volume,
            open_interest,
            implied_volatility,
            delta,
            gamma,
            theta,
            vega,
            rho
        FROM option_chain
        WHERE underlying_symbol = '{underlying}'
          AND quote_date = '{as_of_date.date()}'
        ORDER BY expiration, strike
        """

        df = self._run_sql_query(query)

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
                option_type = str(row["option_type"]).upper()
                contract_symbol = f"{underlying}{exp_str}{option_type[0]}{strike_str}"

                # Create contract
                contract = OptionContract(
                    contract_symbol=contract_symbol,
                    underlying_symbol=underlying,
                    expiration=expiration,
                    strike=float(row["strike"]),
                    option_type=option_type,
                    bid=float(row["bid"]) if pd.notna(row["bid"]) else 0.0,
                    ask=float(row["ask"]) if pd.notna(row["ask"]) else 0.0,
                    last=float(row["last"]) if pd.notna(row["last"]) else None,
                    volume=int(row["volume"]) if pd.notna(row["volume"]) else 0,
                    open_interest=int(row["open_interest"]) if pd.notna(row["open_interest"]) else 0,
                    implied_volatility=float(row["implied_volatility"]) if pd.notna(row["implied_volatility"]) else None,
                    delta=float(row["delta"]) if pd.notna(row["delta"]) else None,
                    gamma=float(row["gamma"]) if pd.notna(row["gamma"]) else None,
                    theta=float(row["theta"]) if pd.notna(row["theta"]) else None,
                    vega=float(row["vega"]) if pd.notna(row["vega"]) else None,
                    rho=float(row["rho"]) if pd.notna(row["rho"]) else None,
                    days_to_expiry=days_to_expiry,
                )

                contracts.append(contract)

            except Exception as e:
                logger.warning(f"Failed to parse contract row: {e}")
                continue

        if not contracts:
            return None

        return OptionChain(
            underlying=underlying,
            timestamp=as_of_date,
            contracts=contracts,
        )

    def _option_chain_to_json(self, chain: OptionChain) -> dict:
        """Convert OptionChain to JSON for caching."""
        return {
            "underlying": chain.underlying,
            "timestamp": chain.timestamp.isoformat(),
            "contracts": [
                {
                    "contract_symbol": c.contract_symbol,
                    "underlying_symbol": c.underlying_symbol,
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
                    "days_to_expiry": c.days_to_expiry,
                }
                for c in chain.contracts
            ],
        }

    def _json_to_option_chain(self, data: dict) -> OptionChain:
        """Convert cached JSON to OptionChain."""
        contracts = [
            OptionContract(
                contract_symbol=c["contract_symbol"],
                underlying_symbol=c["underlying_symbol"],
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
                days_to_expiry=c["days_to_expiry"],
            )
            for c in data["contracts"]
        ]

        return OptionChain(
            underlying=data["underlying"],
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
        SELECT DISTINCT quote_date
        FROM option_chain
        WHERE underlying_symbol = '{underlying}'
          AND quote_date >= '{start_date.date()}'
          AND quote_date <= '{end_date.date()}'
        ORDER BY quote_date
        """

        df = self._run_sql_query(query)

        if df.empty:
            return []

        return [pd.to_datetime(date).to_pydatetime() for date in df["quote_date"]]
