#!/usr/bin/env python3
"""Diagnose IV Rank issues in real options backtest.

This script analyzes why the real options backtest generated zero trades.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from alpaca_options.backtesting.alpaca_options_fetcher import AlpacaOptionsDataFetcher
from alpaca_options.backtesting.data_loader import BacktestDataLoader
from alpaca_options.core.config import load_config

import pandas as pd

def main():
    """Analyze IV rank and technical indicators for real data."""
    print("=== Diagnosing Real Options Backtest ===\n")

    # Load configuration
    settings = load_config()

    # Parameters
    symbol = "QQQ"
    start_dt = datetime(2024, 2, 1)
    end_dt = datetime(2024, 11, 30)

    # Check for Alpaca credentials
    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if not api_key or not api_secret:
        print("ERROR: Alpaca credentials required!")
        return

    # Initialize fetcher
    fetcher = AlpacaOptionsDataFetcher(
        api_key=api_key,
        api_secret=api_secret,
    )

    print("Fetching underlying data...")
    underlying_data = fetcher.fetch_underlying_bars(
        symbol=symbol,
        start_date=start_dt,
        end_date=end_dt,
        timeframe="1Hour",
    )

    if underlying_data.empty:
        print("ERROR: No underlying data!")
        return

    print(f"Loaded {len(underlying_data)} bars\n")

    # Add technical indicators
    print("Computing technical indicators...")
    data_loader = BacktestDataLoader(settings.backtesting.data)
    underlying_data = data_loader.add_technical_indicators(underlying_data)

    # Analyze IV rank
    print("\n=== IV Rank Analysis ===")
    print(f"IV Rank Stats:")
    print(f"  Min: {underlying_data['iv_rank'].min():.2f}")
    print(f"  Max: {underlying_data['iv_rank'].max():.2f}")
    print(f"  Mean: {underlying_data['iv_rank'].mean():.2f}")
    print(f"  Median: {underlying_data['iv_rank'].median():.2f}")
    print(f"  NaN count: {underlying_data['iv_rank'].isna().sum()}")

    # Check how many days meet IV rank >= 30 threshold
    valid_iv = underlying_data['iv_rank'].dropna()
    above_30 = valid_iv[valid_iv >= 30]

    print(f"\nIV Rank >= 30 threshold:")
    print(f"  Total valid days: {len(valid_iv)}")
    print(f"  Days above 30: {len(above_30)} ({len(above_30)/len(valid_iv)*100:.1f}%)")
    print(f"  Days below 30: {len(valid_iv) - len(above_30)} ({(len(valid_iv) - len(above_30))/len(valid_iv)*100:.1f}%)")

    # Analyze RSI
    print("\n=== RSI Analysis ===")
    valid_rsi = underlying_data['rsi_14'].dropna()
    oversold = valid_rsi[valid_rsi <= 45]  # Bullish
    overbought = valid_rsi[valid_rsi >= 55]  # Bearish
    neutral = valid_rsi[(valid_rsi > 45) & (valid_rsi < 55)]

    print(f"RSI Stats:")
    print(f"  Min: {valid_rsi.min():.2f}")
    print(f"  Max: {valid_rsi.max():.2f}")
    print(f"  Mean: {valid_rsi.mean():.2f}")
    print(f"  Median: {valid_rsi.median():.2f}")

    print(f"\nRSI Conditions:")
    print(f"  Oversold (≤45): {len(oversold)} ({len(oversold)/len(valid_rsi)*100:.1f}%)")
    print(f"  Overbought (≥55): {len(overbought)} ({len(overbought)/len(valid_rsi)*100:.1f}%)")
    print(f"  Neutral: {len(neutral)} ({len(neutral)/len(valid_rsi)*100:.1f}%)")

    # Check combined conditions (IV rank >= 30 AND (RSI <= 45 OR RSI >= 55))
    print("\n=== Combined Signal Conditions ===")
    combined_df = underlying_data[['iv_rank', 'rsi_14', 'close']].dropna()

    signal_opportunities = combined_df[
        (combined_df['iv_rank'] >= 30) &
        ((combined_df['rsi_14'] <= 45) | (combined_df['rsi_14'] >= 55))
    ]

    print(f"Days meeting BOTH conditions (IV rank >= 30 AND RSI signal):")
    print(f"  Total: {len(signal_opportunities)} ({len(signal_opportunities)/len(combined_df)*100:.1f}%)")

    if len(signal_opportunities) > 0:
        print(f"\nFirst 10 signal opportunities:")
        print(signal_opportunities.head(10)[['close', 'iv_rank', 'rsi_14']])
    else:
        print("\n  ⚠️  ZERO days met both conditions! This explains why no trades were generated.")
        print("\n  Recommendations:")
        print("    1. Lower min_iv_rank threshold (try 15-20 instead of 30)")
        print("    2. Widen RSI thresholds")
        print("    3. Use different volatility regime detection")

    # Show distribution of IV rank over time
    print("\n=== IV Rank Timeline (Monthly) ===")
    monthly_iv = underlying_data['iv_rank'].resample('ME').agg(['mean', 'min', 'max'])
    print(monthly_iv)

    # Show historical volatility
    print("\n=== Historical Volatility (HV) Timeline (Monthly) ===")
    monthly_hv = underlying_data['hv_20'].resample('ME').agg(['mean', 'min', 'max'])
    print(monthly_hv * 100)  # Convert to percentage

    print("\n=== Analysis Complete ===")

if __name__ == "__main__":
    main()
