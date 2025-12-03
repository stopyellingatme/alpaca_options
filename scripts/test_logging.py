#!/usr/bin/env python3
"""Test backtest with logging to trace signal flow."""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Set up logging first - DEBUG level to see everything
logging.basicConfig(
    level=logging.DEBUG,
    format='%(name)s - %(levelname)s - %(message)s'
)

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import pandas as pd

from alpaca_options.backtesting import BacktestDataLoader, BacktestEngine
from alpaca_options.core.config import load_config, BacktestConfig
from alpaca_options.strategies import VerticalSpreadStrategy


async def run():
    settings = load_config(project_root / 'config' / 'default.yaml')

    strat = VerticalSpreadStrategy()
    config = {
        'underlyings': ['QQQ'],
        'rsi_oversold': 45,
        'rsi_overbought': 55,
        'min_open_interest': 50,
        'max_spread_percent': 15.0,
        'min_credit': 10,
        'min_iv_rank': 0,
    }
    await strat.initialize(config)

    data_loader = BacktestDataLoader(
        settings.backtesting.data,
        api_key=os.environ.get('ALPACA_API_KEY'),
        api_secret=os.environ.get('ALPACA_SECRET_KEY'),
    )

    # Use shorter period for testing
    start_date = datetime(2024, 10, 1)
    end_date = datetime(2024, 10, 15)

    underlying_data = data_loader.load_underlying_data('QQQ', start_date, end_date, '1h')
    underlying_data = data_loader.add_technical_indicators(underlying_data)
    print(f'Loaded {len(underlying_data)} bars')

    options_data = data_loader.load_options_data_hybrid(
        underlying_data=underlying_data,
        symbol='QQQ',
        start_date=start_date,
        end_date=end_date,
    )
    print(f'Loaded {len(options_data)} option chains')

    modified_backtesting = BacktestConfig(
        default_start_date=settings.backtesting.default_start_date,
        default_end_date=settings.backtesting.default_end_date,
        initial_capital=5000,
        execution=settings.backtesting.execution,
        data=settings.backtesting.data,
    )

    engine = BacktestEngine(modified_backtesting, settings.risk, settings.trading)
    # Debug: check what's in the first chain
    first_ts = list(options_data.keys())[0]
    first_chain = options_data[first_ts]
    print(f"\nFirst chain underlying: '{first_chain.underlying}'")
    print(f"Strategy underlyings: {strat._underlyings}")
    print(f"Chain has {len(first_chain.contracts)} contracts")

    # Check if RSI is being passed properly
    first_bar = underlying_data.iloc[0]
    print(f"First bar RSI: {first_bar.get('rsi_14', 'N/A')}")

    # Check RSI across all bars
    rsi_valid = underlying_data['rsi_14'].dropna()
    print(f"\nRSI valid count: {len(rsi_valid)} / {len(underlying_data)}")
    if len(rsi_valid) > 0:
        print(f"RSI range: {rsi_valid.min():.1f} - {rsi_valid.max():.1f}")
        oversold = (rsi_valid <= 45).sum()
        overbought = (rsi_valid >= 55).sum()
        print(f"Oversold (<=45): {oversold}, Overbought (>=55): {overbought}")

    # Check first bar with valid RSI
    valid_rsi_mask = ~underlying_data['rsi_14'].isna()
    first_valid_idx = valid_rsi_mask.idxmax()
    print(f"\nFirst valid RSI at: {first_valid_idx}")
    first_valid_bar = underlying_data.loc[first_valid_idx]
    print(f"First valid RSI value: {first_valid_bar['rsi_14']:.1f}")

    # Manually test the strategy with a bar that HAS valid RSI
    from alpaca_options.strategies.base import MarketData

    # Use the bar with first valid RSI
    test_bar = first_valid_bar
    test_ts = first_valid_idx

    # Need to get the options chain for this timestamp
    test_chain = options_data.get(test_ts)
    if test_chain is None:
        print(f"No options chain for {test_ts}, looking for closest...")
        # Find closest chain
        for ts in sorted(options_data.keys()):
            if ts >= test_ts:
                test_chain = options_data[ts]
                test_ts = ts
                break

    print(f"\nUsing timestamp: {test_ts}")
    print(f"Test bar close: {test_bar['close']:.2f}")
    print(f"Test bar RSI: {test_bar['rsi_14']:.1f}")

    test_md = MarketData(
        symbol='QQQ',
        timestamp=test_ts,
        open=float(test_bar['open']),
        high=float(test_bar['high']),
        low=float(test_bar['low']),
        close=float(test_bar['close']),
        volume=int(test_bar.get('volume', 0)),
        rsi_14=float(test_bar['rsi_14']) if not pd.isna(test_bar['rsi_14']) else None,
    )
    print(f"Test MarketData RSI: {test_md.rsi_14}")

    await strat.on_market_data(test_md)

    # Check direction determination
    direction = strat._determine_direction('QQQ')
    print(f"Direction determined: {direction}")

    test_signal = await strat.on_option_chain(test_chain)
    print(f"Test signal: {test_signal}")

    result = await engine.run(
        strategy=strat,
        underlying_data=underlying_data,
        options_data=options_data,
        start_date=start_date,
        end_date=end_date,
    )

    print(f'\nTotal trades: {result.metrics.total_trades}')
    print(f'Total return: ${result.metrics.total_return:.2f}')


if __name__ == "__main__":
    asyncio.run(run())
