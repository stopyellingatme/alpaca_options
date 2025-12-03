#!/usr/bin/env python3
"""Debug vertical spread strategy signal generation."""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from alpaca_options.backtesting import BacktestDataLoader
from alpaca_options.core.config import load_config
from alpaca_options.strategies import VerticalSpreadStrategy
from alpaca_options.strategies.base import MarketData

async def debug_strategy():
    """Debug why vertical spread isn't generating signals."""
    print("=== Vertical Spread Debug ===\n")

    # Load config
    settings = load_config(project_root / "config" / "default.yaml")
    print(f"Config loaded from: {project_root / 'config' / 'default.yaml'}")

    # Get strategy config
    strat_config = settings.strategies.get("vertical_spread")
    print(f"\nStrategy config from YAML:")
    print(f"  enabled: {strat_config.enabled}")
    print(f"  allocation: {strat_config.allocation}")
    print(f"  config: {strat_config.config}")

    # Create and initialize strategy
    strategy = VerticalSpreadStrategy()

    config = strat_config.config.copy()
    config["underlyings"] = ["QQQ"]

    # Add relaxed criteria
    config["rsi_oversold"] = 45
    config["rsi_overbought"] = 55
    config["min_open_interest"] = 50
    config["max_spread_percent"] = 15.0
    config["min_credit"] = 10
    config["min_iv_rank"] = 0  # Disable IV rank check

    print(f"\nInitializing strategy with config:")
    for k, v in config.items():
        print(f"  {k}: {v}")

    await strategy.initialize(config)

    print(f"\nStrategy internal values after init:")
    print(f"  _rsi_oversold: {strategy._rsi_oversold}")
    print(f"  _rsi_overbought: {strategy._rsi_overbought}")
    print(f"  _min_open_interest: {strategy._min_open_interest}")
    print(f"  _max_spread_percent: {strategy._max_spread_percent}")
    print(f"  _min_credit: {strategy._min_credit}")
    print(f"  _min_iv_rank: {strategy._min_iv_rank}")
    print(f"  _underlyings: {strategy._underlyings}")

    # Load data
    data_loader = BacktestDataLoader(
        settings.backtesting.data,
        api_key=os.environ.get("ALPACA_API_KEY"),
        api_secret=os.environ.get("ALPACA_SECRET_KEY"),
    )

    start_date = datetime(2024, 10, 1)  # Recent period
    end_date = datetime(2024, 10, 31)

    print(f"\nLoading QQQ data from {start_date.date()} to {end_date.date()}...")
    underlying_data = data_loader.load_underlying_data("QQQ", start_date, end_date, "1h")
    underlying_data = data_loader.add_technical_indicators(underlying_data)

    print(f"Loaded {len(underlying_data)} bars")

    # Load options data
    print("\nLoading options data...")
    options_data = data_loader.load_options_data_hybrid(
        underlying_data=underlying_data,
        symbol="QQQ",
        start_date=start_date,
        end_date=end_date,
    )
    print(f"Loaded {len(options_data)} option chains")

    # Test signal generation
    print("\n=== Testing Signal Generation ===\n")

    signals_generated = 0
    signals_rejected_direction = 0
    signals_rejected_spread = 0

    for i, (timestamp, chain) in enumerate(options_data.items()):
        # Get corresponding market data
        try:
            idx = underlying_data.index.get_indexer([timestamp], method="ffill")[0]
            if idx < 0:
                continue
            row = underlying_data.iloc[idx]
        except Exception:
            continue

        # Create market data
        market_data = MarketData(
            symbol="QQQ",
            timestamp=timestamp,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row.get("volume", 0)),
            rsi_14=float(row["rsi_14"]) if "rsi_14" in row and not pd.isna(row["rsi_14"]) else None,
            sma_20=float(row["sma_20"]) if "sma_20" in row and not pd.isna(row["sma_20"]) else None,
            sma_50=float(row["sma_50"]) if "sma_50" in row and not pd.isna(row["sma_50"]) else None,
        )

        # Pass market data to strategy
        await strategy.on_market_data(market_data)

        # Check direction determination
        direction = strategy._determine_direction("QQQ")

        if direction is None:
            signals_rejected_direction += 1
            if i < 5:  # Print first few for debugging
                rsi = market_data.rsi_14
                rsi_str = f"{rsi:.1f}" if rsi is not None else "None"
                print(f"  {timestamp}: RSI={rsi_str} -> No direction")
        else:
            # Try to get signal
            signal = await strategy.on_option_chain(chain)

            if signal is not None:
                signals_generated += 1
                print(f"\n  SIGNAL at {timestamp}:")
                print(f"    Direction: {direction.value}")
                print(f"    Signal type: {signal.signal_type.value}")
                print(f"    Legs: {len(signal.legs)}")
                for leg in signal.legs:
                    print(f"      {leg.side} {leg.contract_symbol} @ {leg.strike}")
            else:
                signals_rejected_spread += 1
                if signals_rejected_spread <= 5:
                    print(f"  {timestamp}: Direction={direction.value}, RSI={market_data.rsi_14:.1f} -> No spread found")

        if signals_generated >= 5:
            print("\n  (stopping after 5 signals)")
            break

    print(f"\n=== Results ===")
    print(f"Total timestamps: {len(options_data)}")
    print(f"Rejected (no direction): {signals_rejected_direction}")
    print(f"Rejected (no spread found): {signals_rejected_spread}")
    print(f"Signals generated: {signals_generated}")

import pandas as pd

if __name__ == "__main__":
    asyncio.run(debug_strategy())
