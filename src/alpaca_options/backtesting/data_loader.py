"""Data loading utilities for backtesting.

This module provides:
- Historical options data loading and caching
- Synthetic options chain generation for backtesting
- Integration with Alpaca historical options data (Feb 2024+)
- Data validation and preprocessing
"""

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from alpaca_options.core.config import BacktestDataConfig
from alpaca_options.strategies.base import OptionChain, OptionContract
from alpaca_options.utils.greeks import BlackScholes, OptionType

logger = logging.getLogger(__name__)

# Alpaca options data availability
ALPACA_OPTIONS_DATA_START = datetime(2024, 2, 1)


class BacktestDataLoader:
    """Loads and manages historical data for backtesting.

    Supports:
    - Loading from CSV/Parquet files
    - Real Alpaca historical options data (Feb 2024+)
    - Synthetic options chain generation (fallback)
    - Data caching
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

    def generate_synthetic_options_data(
        self,
        underlying_data: pd.DataFrame,
        symbol: str,
        risk_free_rate: float = 0.05,
        dividend_yield: float = 0.01,
        base_iv: float = 0.25,
    ) -> dict[datetime, OptionChain]:
        """Generate synthetic options chains from underlying data.

        Creates realistic options data for backtesting when real
        options data is not available. Includes market regime awareness
        for IV dynamics.

        Args:
            underlying_data: DataFrame with underlying OHLCV data.
            symbol: The underlying symbol.
            risk_free_rate: Annual risk-free rate.
            dividend_yield: Annual dividend yield.
            base_iv: Base implied volatility.

        Returns:
            Dict mapping timestamp to OptionChain.
        """
        options_data: dict[datetime, OptionChain] = {}

        for timestamp, row in underlying_data.iterrows():
            underlying_price = row["close"]

            # Generate chain for this timestamp, passing market data for IV regime
            chain = self._generate_chain_at_timestamp(
                timestamp=timestamp,
                symbol=symbol,
                underlying_price=underlying_price,
                risk_free_rate=risk_free_rate,
                dividend_yield=dividend_yield,
                base_iv=base_iv,
                market_data=row,  # Pass row for regime-aware IV
            )

            options_data[timestamp] = chain

        logger.info(
            f"Generated synthetic options data for {symbol}: "
            f"{len(options_data)} snapshots"
        )

        return options_data

    def _generate_chain_at_timestamp(
        self,
        timestamp: datetime,
        symbol: str,
        underlying_price: float,
        risk_free_rate: float,
        dividend_yield: float,
        base_iv: float,
        market_data: Optional[pd.Series] = None,
    ) -> OptionChain:
        """Generate a single options chain snapshot."""
        contracts = []

        # Generate strikes around ATM (±20%)
        atm_strike = round(underlying_price / 5) * 5  # Round to nearest 5
        strike_range = int(underlying_price * 0.20 / 5)
        strikes = [
            atm_strike + (i * 5) for i in range(-strike_range, strike_range + 1)
        ]

        # Generate expirations (weekly for near-term, monthly for far)
        expirations = self._generate_expirations(timestamp)

        for expiration in expirations:
            dte = (expiration - timestamp).days
            if dte <= 0:
                continue

            for strike in strikes:
                # Calculate IV with smile and market regime
                iv = self._calculate_iv_with_smile(
                    base_iv, underlying_price, strike, dte, market_data
                )

                # Generate call contract
                call = self._create_contract(
                    symbol=symbol,
                    underlying_price=underlying_price,
                    strike=strike,
                    expiration=expiration,
                    option_type="call",
                    iv=iv,
                    risk_free_rate=risk_free_rate,
                    dividend_yield=dividend_yield,
                    as_of_date=timestamp,
                )
                if call:
                    contracts.append(call)

                # Generate put contract
                put = self._create_contract(
                    symbol=symbol,
                    underlying_price=underlying_price,
                    strike=strike,
                    expiration=expiration,
                    option_type="put",
                    iv=iv,
                    risk_free_rate=risk_free_rate,
                    dividend_yield=dividend_yield,
                    as_of_date=timestamp,
                )
                if put:
                    contracts.append(put)

        return OptionChain(
            underlying=symbol,
            underlying_price=underlying_price,
            timestamp=timestamp,
            contracts=contracts,
        )

    def _generate_expirations(self, current_date: datetime) -> list[datetime]:
        """Generate realistic expiration dates."""
        expirations = []

        # Weekly expirations for next 4 weeks
        for weeks in range(1, 5):
            # Find next Friday
            days_until_friday = (4 - current_date.weekday()) % 7
            if days_until_friday == 0:
                days_until_friday = 7
            exp = current_date + timedelta(days=days_until_friday + (weeks - 1) * 7)
            expirations.append(
                datetime(exp.year, exp.month, exp.day, 16, 0)
            )

        # Monthly expirations for next 3 months (3rd Friday)
        for months_out in range(1, 4):
            month = current_date.month + months_out
            year = current_date.year

            while month > 12:
                month -= 12
                year += 1

            # Find 3rd Friday
            first_day = datetime(year, month, 1)
            days_until_friday = (4 - first_day.weekday()) % 7
            third_friday = first_day + timedelta(days=days_until_friday + 14)
            expirations.append(
                datetime(third_friday.year, third_friday.month, third_friday.day, 16, 0)
            )

        return sorted(set(expirations))

    def _calculate_iv_with_smile(
        self,
        base_iv: float,
        underlying_price: float,
        strike: float,
        dte: int,
        market_data: Optional[pd.Series] = None,
    ) -> float:
        """Calculate IV with volatility smile/skew and market regime awareness.

        Incorporates:
        - Volatility smile (OTM puts have higher IV)
        - Term structure
        - Market regime: IV spikes during downturns
        - Recent price action: gaps/drops increase IV
        """
        moneyness = strike / underlying_price

        # Volatility smile parameters
        # Higher IV for OTM puts (crash protection) and far OTM calls
        smile_factor = 1.0

        if moneyness < 0.95:
            # OTM puts: higher IV (steeper skew in stressed markets)
            smile_factor = 1.0 + (0.95 - moneyness) * 0.5
        elif moneyness > 1.05:
            # OTM calls: slightly higher IV
            smile_factor = 1.0 + (moneyness - 1.05) * 0.2

        # Term structure: longer dated = slightly higher IV
        term_factor = 1.0 + (dte / 365) * 0.1

        # === MARKET REGIME ADJUSTMENT ===
        # IV should spike during market stress / downturns
        regime_factor = 1.0

        if market_data is not None:
            # Check RSI for oversold conditions (market fear)
            rsi = market_data.get("rsi_14")
            if rsi is not None and not pd.isna(rsi):
                if rsi < 30:
                    # Extreme fear: IV spikes 40-80%
                    regime_factor = 1.4 + (30 - rsi) / 30 * 0.4
                elif rsi < 40:
                    # Elevated fear: IV up 10-40%
                    regime_factor = 1.1 + (40 - rsi) / 10 * 0.3

            # Check historical volatility for recent turbulence
            hv = market_data.get("hv_20")
            if hv is not None and not pd.isna(hv) and hv > 0:
                # If realized vol is high, IV should be elevated
                if hv > 0.35:  # High volatility regime
                    hv_boost = min((hv - 0.35) / 0.35, 0.5)  # Up to 50% boost
                    regime_factor = max(regime_factor, 1.0 + hv_boost)

        # Add some random daily variation (IV isn't perfectly predictable)
        import random
        noise = 0.95 + random.random() * 0.10  # ±5% daily noise

        final_iv = base_iv * smile_factor * term_factor * regime_factor * noise

        # Clamp to reasonable range
        return max(0.10, min(1.50, final_iv))

    def _create_contract(
        self,
        symbol: str,
        underlying_price: float,
        strike: float,
        expiration: datetime,
        option_type: str,
        iv: float,
        risk_free_rate: float,
        dividend_yield: float,
        as_of_date: Optional[datetime] = None,
    ) -> Optional[OptionContract]:
        """Create a single option contract with calculated Greeks.

        Uses realistic bid-ask spread modeling based on:
        - Option price level (penny-wide for expensive, wider for cheap)
        - Moneyness (tighter spreads ATM, wider OTM)
        - Time to expiry (wider spreads near expiry)
        - Open interest (proxy for liquidity)
        """
        reference_date = as_of_date if as_of_date else datetime.now()
        dte = max(1, (expiration - reference_date).days)
        time_to_expiry = dte / 365.0

        opt_type = OptionType.CALL if option_type == "call" else OptionType.PUT

        # Calculate theoretical price using static method
        price = BlackScholes.price(
            option_type=opt_type,
            spot=underlying_price,
            strike=strike,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=iv,
            dividend_yield=dividend_yield,
        )

        if price < 0.01:
            return None

        # Calculate Greeks using static method
        greeks = BlackScholes.calculate_greeks(
            option_type=opt_type,
            spot=underlying_price,
            strike=strike,
            time_to_expiry=time_to_expiry,
            risk_free_rate=risk_free_rate,
            volatility=iv,
            dividend_yield=dividend_yield,
        )

        # Generate realistic volume and OI based on moneyness FIRST
        # (we need OI to calculate spread)
        moneyness = abs(underlying_price - strike) / underlying_price
        moneyness_ratio = strike / underlying_price

        # Base open interest - higher for liquid underlyings
        # Assume SPY/QQQ are liquid, single stocks less so
        base_oi = 10000 if symbol in ("SPY", "QQQ", "IWM") else 2000

        # OI peaks near ATM and drops off for deep OTM/ITM
        if moneyness < 0.05:  # Near ATM (within 5%)
            oi_factor = 1.0
        elif moneyness < 0.10:
            oi_factor = 0.6
        elif moneyness < 0.20:
            oi_factor = 0.3
        else:
            oi_factor = 0.1

        # Add some randomness
        open_interest = int(base_oi * oi_factor * (0.5 + np.random.random()))
        volume = int(open_interest * 0.05 * (0.2 + np.random.random() * 0.8))

        # Generate REALISTIC bid/ask spread
        # Real options spreads are based on multiple factors:
        spread = self._calculate_realistic_spread(
            price=price,
            moneyness=moneyness,
            dte=dte,
            open_interest=open_interest,
            iv=iv,
        )

        bid = max(0.01, price - spread / 2)
        ask = price + spread / 2

        # Round to tick size (penny for options > $3, nickel for cheaper)
        if price >= 3.0:
            bid = round(bid, 2)
            ask = round(ask, 2)
        else:
            bid = round(bid * 20) / 20  # Round to nearest 0.05
            ask = round(ask * 20) / 20

        # Ensure minimum spread
        if ask - bid < 0.01:
            ask = bid + 0.01

        # Generate symbol (simplified OCC format)
        exp_str = expiration.strftime("%y%m%d")
        type_char = "C" if option_type == "call" else "P"
        contract_symbol = f"{symbol}{exp_str}{type_char}{int(strike * 1000):08d}"

        return OptionContract(
            symbol=contract_symbol,
            underlying=symbol,
            option_type=option_type,
            strike=strike,
            expiration=expiration,
            bid=bid,
            ask=ask,
            last=price,
            volume=volume,
            open_interest=open_interest,
            delta=greeks.delta,
            gamma=greeks.gamma,
            theta=greeks.theta,
            vega=greeks.vega,
            rho=greeks.rho,
            implied_volatility=iv,
            _as_of_date=as_of_date,
        )

    def _calculate_realistic_spread(
        self,
        price: float,
        moneyness: float,
        dte: int,
        open_interest: int,
        iv: float,
    ) -> float:
        """Calculate realistic bid-ask spread for an option.

        Based on empirical observations:
        - Liquid ETF options (SPY): 1-5% spreads near ATM
        - Single stocks: 3-10% spreads
        - Deep OTM options: 10-30% spreads
        - Near expiry: Wider spreads due to gamma risk
        - Low OI: Wider spreads due to illiquidity

        Returns:
            Spread in dollars.
        """
        # Base spread as percentage (starts at 3% for liquid options)
        base_spread_pct = 0.03

        # Factor 1: Moneyness impact
        # ATM options have tightest spreads, OTM/ITM have wider
        if moneyness < 0.02:
            moneyness_factor = 1.0  # ATM
        elif moneyness < 0.05:
            moneyness_factor = 1.2
        elif moneyness < 0.10:
            moneyness_factor = 1.5
        elif moneyness < 0.20:
            moneyness_factor = 2.5
        else:
            moneyness_factor = 4.0  # Deep OTM/ITM

        # Factor 2: Time to expiry impact
        # Near expiry = wider spreads (gamma/pin risk)
        if dte <= 3:
            dte_factor = 2.5
        elif dte <= 7:
            dte_factor = 1.8
        elif dte <= 14:
            dte_factor = 1.3
        elif dte <= 30:
            dte_factor = 1.1
        else:
            dte_factor = 1.0

        # Factor 3: Open interest (liquidity) impact
        if open_interest > 10000:
            liquidity_factor = 0.8  # Very liquid
        elif open_interest > 5000:
            liquidity_factor = 0.9
        elif open_interest > 1000:
            liquidity_factor = 1.0
        elif open_interest > 500:
            liquidity_factor = 1.3
        elif open_interest > 100:
            liquidity_factor = 1.8
        else:
            liquidity_factor = 3.0  # Very illiquid

        # Factor 4: IV impact (higher IV = wider spreads due to uncertainty)
        iv_factor = 1.0 + max(0, (iv - 0.20)) * 0.5

        # Calculate final spread percentage
        spread_pct = (
            base_spread_pct
            * moneyness_factor
            * dte_factor
            * liquidity_factor
            * iv_factor
        )

        # Cap spread at reasonable levels
        spread_pct = min(spread_pct, 0.50)  # Max 50% spread

        # Calculate dollar spread
        spread = price * spread_pct

        # Minimum spreads based on price
        if price >= 3.0:
            min_spread = 0.02  # Penny pilot, minimum 2 cents
        elif price >= 0.50:
            min_spread = 0.05  # Nickel minimum
        else:
            min_spread = 0.05  # Still nickel for cheap options

        # Maximum spread for cheap options (don't want $0.10 option with $0.50 spread)
        max_spread = max(price * 0.30, min_spread)

        return max(min_spread, min(spread, max_spread))

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
                f"Use generate_synthetic_options_data() instead."
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

    def load_options_data_hybrid(
        self,
        underlying_data: pd.DataFrame,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
    ) -> dict[datetime, OptionChain]:
        """Load options data using hybrid approach.

        Uses real Alpaca data for dates after Feb 2024, and synthetic
        data for earlier dates. This provides the best of both worlds:
        realistic recent data with longer backtest periods.

        Args:
            underlying_data: DataFrame with underlying OHLCV data.
            symbol: The underlying symbol.
            start_date: Start date.
            end_date: End date.

        Returns:
            Dict mapping timestamp to OptionChain.
        """
        options_data: dict[datetime, OptionChain] = {}

        # Try to load real Alpaca data for the applicable period
        alpaca_start = max(start_date, ALPACA_OPTIONS_DATA_START)

        if self._alpaca_fetcher and end_date >= ALPACA_OPTIONS_DATA_START:
            logger.info(
                f"Loading real Alpaca options data for {symbol} "
                f"({alpaca_start.date()} to {end_date.date()})"
            )
            try:
                real_data = self._alpaca_fetcher.fetch_option_chains_for_period(
                    underlying=symbol,
                    start_date=alpaca_start,
                    end_date=end_date,
                )
                options_data.update(real_data)
                logger.info(f"Loaded {len(real_data)} real option chains")
            except Exception as e:
                logger.warning(f"Could not load Alpaca options data: {e}")

        # Generate synthetic data for dates without real data
        synthetic_needed = []
        for timestamp, row in underlying_data.iterrows():
            if timestamp not in options_data:
                synthetic_needed.append((timestamp, row))

        if synthetic_needed:
            logger.info(
                f"Generating {len(synthetic_needed)} synthetic option chains "
                f"(no real data available)"
            )
            for timestamp, row in synthetic_needed:
                underlying_price = row["close"]

                # Use historical volatility if available, else default
                base_iv = row.get("hv_20", 0.25)
                if pd.isna(base_iv) or base_iv <= 0:
                    base_iv = 0.25

                chain = self._generate_chain_at_timestamp(
                    timestamp=timestamp,
                    symbol=symbol,
                    underlying_price=underlying_price,
                    risk_free_rate=0.05,
                    dividend_yield=0.01,
                    base_iv=base_iv,
                )
                options_data[timestamp] = chain

        logger.info(
            f"Total options data: {len(options_data)} snapshots "
            f"(real: {len(options_data) - len(synthetic_needed)}, "
            f"synthetic: {len(synthetic_needed)})"
        )

        return options_data

    @property
    def has_alpaca_credentials(self) -> bool:
        """Check if Alpaca credentials are available."""
        return self._alpaca_fetcher is not None

    def get_data_source_info(self, date: datetime) -> str:
        """Get information about data source for a given date.

        Args:
            date: Date to check.

        Returns:
            String describing data source.
        """
        if date >= ALPACA_OPTIONS_DATA_START and self._alpaca_fetcher:
            return "alpaca"
        return "synthetic"
