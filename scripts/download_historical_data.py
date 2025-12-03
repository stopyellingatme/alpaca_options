#!/usr/bin/env python3
"""Download historical data from Alpaca for backtesting.

This script downloads:
- OHLCV data for specified symbols
- Adds technical indicators

Usage:
    python scripts/download_historical_data.py
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Load environment variables
load_dotenv(project_root / ".env")

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Configuration
SYMBOLS = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "GOOGL", "AMZN"]
START_DATE = datetime(2023, 1, 1)
END_DATE = datetime(2024, 11, 1)
OUTPUT_DIR = project_root / "data" / "historical"


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add technical indicators to the dataframe."""
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

    # IV Rank (approximated from HV)
    hv_min = df["hv_20"].rolling(window=252, min_periods=20).min()
    hv_max = df["hv_20"].rolling(window=252, min_periods=20).max()
    df["iv_rank"] = ((df["hv_20"] - hv_min) / (hv_max - hv_min)) * 100
    df["iv_rank"] = df["iv_rank"].fillna(50)  # Default to 50 if not enough data

    # VWAP (daily)
    df["vwap"] = (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()

    return df


def download_symbol_data(client: StockHistoricalDataClient, symbol: str) -> pd.DataFrame:
    """Download historical data for a single symbol."""
    print(f"  Downloading {symbol}...")

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=TimeFrame.Hour,
        start=START_DATE,
        end=END_DATE,
    )

    try:
        bars = client.get_stock_bars(request)
        df = bars.df

        if df.empty:
            print(f"  ⚠ No data returned for {symbol}")
            return pd.DataFrame()

        # Reset index and clean up
        df = df.reset_index()

        # Handle multi-index if present
        if "symbol" in df.columns:
            df = df[df["symbol"] == symbol].copy()
            df = df.drop(columns=["symbol"])

        # Set timestamp as index
        if "timestamp" in df.columns:
            df.set_index("timestamp", inplace=True)
        elif df.index.name != "timestamp":
            # The index might already be the timestamp
            pass

        # Ensure we have the required columns
        required_cols = ["open", "high", "low", "close", "volume"]
        for col in required_cols:
            if col not in df.columns:
                print(f"  ⚠ Missing column {col} for {symbol}")
                return pd.DataFrame()

        # Add symbol column
        df["symbol"] = symbol

        print(f"  ✓ Downloaded {len(df)} bars for {symbol}")
        return df

    except Exception as e:
        print(f"  ✗ Error downloading {symbol}: {e}")
        return pd.DataFrame()


def main():
    """Main function to download all historical data."""
    print("=" * 60)
    print("Alpaca Historical Data Downloader")
    print("=" * 60)

    # Check for API keys
    api_key = os.environ.get("ALPACA_API_KEY")
    api_secret = os.environ.get("ALPACA_SECRET_KEY")

    if not api_key or not api_secret:
        print("✗ Error: ALPACA_API_KEY and ALPACA_SECRET_KEY must be set")
        sys.exit(1)

    print(f"\nDate range: {START_DATE.date()} to {END_DATE.date()}")
    print(f"Symbols: {', '.join(SYMBOLS)}")
    print(f"Output directory: {OUTPUT_DIR}")
    print()

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize Alpaca client
    print("Connecting to Alpaca...")
    client = StockHistoricalDataClient(api_key, api_secret)
    print("✓ Connected\n")

    # Download data for each symbol
    print("Downloading historical data...")
    for symbol in SYMBOLS:
        df = download_symbol_data(client, symbol)

        if df.empty:
            continue

        # Add technical indicators
        print(f"  Adding technical indicators for {symbol}...")
        df = add_technical_indicators(df)

        # Save to CSV
        output_file = OUTPUT_DIR / f"{symbol}.csv"
        df.to_csv(output_file)
        print(f"  ✓ Saved to {output_file}")

        # Try to save as parquet for faster loading (optional)
        try:
            parquet_file = OUTPUT_DIR / f"{symbol}.parquet"
            df.to_parquet(parquet_file)
            print(f"  ✓ Saved to {parquet_file}")
        except ImportError:
            pass  # pyarrow not installed, skip parquet
        print()

    print("=" * 60)
    print("Download complete!")
    print("=" * 60)

    # Summary
    print("\nFiles created:")
    for f in sorted(OUTPUT_DIR.glob("*.csv")):
        size = f.stat().st_size / 1024
        print(f"  {f.name}: {size:.1f} KB")


if __name__ == "__main__":
    main()
