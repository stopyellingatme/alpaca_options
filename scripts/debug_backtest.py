#!/usr/bin/env python3
"""Debug version of backtest to see why no signals are being generated."""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# Enable DEBUG logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

from alpaca_options.backtesting import BacktestEngine
from alpaca_options.backtesting.alpaca_options_fetcher import AlpacaOptionsDataFetcher
from alpaca_options.backtesting.data_loader import BacktestDataLoader
from alpaca_options.core.config import load_config
from alpaca_options.strategies import VerticalSpreadStrategy

async def main():
    """Run debug backtest."""
    print("=== DEBUG BACKTEST ===\n")

    settings = load_config()

    symbol = "QQQ"
    start_dt = datetime(2024, 3, 1)  # Shorter period for debugging
    end_dt = datetime(2024, 3, 15)
    initial_capital = 5000.0

    settings.backtesting.initial_capital = initial_capital

    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if not api_key or not api_secret:
        print("ERROR: Alpaca credentials required!")
        return

    fetcher = AlpacaOptionsDataFetcher(api_key=api_key, api_secret=api_secret)

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
    data_loader = BacktestDataLoader(settings.backtesting.data)
    underlying_data = data_loader.add_technical_indicators(underlying_data)

    # Fetch options chains (just a few for debugging)
    print("Fetching options chains...")
    daily_timestamps = underlying_data.resample('1D').last().dropna().index[:5]  # Just 5 days

    options_data = {}
    for timestamp in daily_timestamps:
        chain = fetcher.fetch_option_chain(
            underlying=symbol,
            as_of_date=timestamp,
        )
        if chain:
            options_data[timestamp] = chain
            print(f"  {timestamp.date()}: {len(chain.contracts)} contracts")

    if not options_data:
        print("ERROR: No options data!")
        return

    print(f"\nLoaded {len(options_data)} chains\n")

    # Create and configure strategy
    strategy = VerticalSpreadStrategy()
    strategy._config = {
        "underlyings": [symbol],
        "min_iv_rank": 30,
        "min_dte": 21,
        "max_dte": 45,
        "close_dte": 14,
        "min_open_interest": 0,  # Historical data fix
        "max_spread_percent": 15.0,  # Historical data fix
        "spread_width": 5.0,
        "min_credit": 20.0,  # Lower threshold
        "min_return_on_risk": 0.15,  # Lower threshold
    }

    # Initialize strategy
    await strategy.initialize(strategy._config)

    print("Creating backtest engine...")
    engine = BacktestEngine(settings.backtesting, settings.risk)

    print("\nRunning backtest with DEBUG logging...")
    print("=" * 60)

    result = await engine.run(
        strategy=strategy,
        underlying_data=underlying_data,
        options_data=options_data,
        start_date=start_dt,
        end_date=end_dt,
    )

    print("=" * 60)
    print(f"\n{result.metrics.total_trades} trades generated")

    if result.trades:
        for trade in result.trades:
            print(f"  {trade.entry_time.date()}: {trade.signal_type.name}, P/L: ${trade.net_pnl:.2f}")

if __name__ == "__main__":
    asyncio.run(main())
