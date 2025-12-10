#!/usr/bin/env python3
"""Diagnostic Backtest - Verbose logging to identify trade blockers."""

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

from rich.console import Console

console = Console()

# Enable DEBUG logging for the strategy
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)-8s [%(name)s] %(message)s',
)

# Set strategy logger to DEBUG
logging.getLogger("alpaca_options.strategies.vertical_spread").setLevel(logging.DEBUG)


async def main():
    """Run diagnostic backtest on SPY only."""
    from alpaca_options.backtesting import BacktestEngine
    from alpaca_options.backtesting.alpaca_options_fetcher import AlpacaOptionsDataFetcher
    from alpaca_options.backtesting.dolthub_options_fetcher import DoltHubOptionsDataFetcher
    from alpaca_options.core.config import load_config
    from alpaca_options.strategies import VerticalSpreadStrategy

    console.print("\n[bold cyan]DIAGNOSTIC BACKTEST - AAPL ONLY[/bold cyan]")
    console.print("[dim]Period: 2024-03-01 to 2024-03-15 (2 weeks)[/dim]")
    console.print("[dim]Verbose logging enabled[/dim]\n")

    # Short test period
    symbol = "AAPL"
    start_dt = datetime(2024, 3, 1)
    end_dt = datetime(2024, 3, 15)
    initial_capital = 5000.0

    # Load configuration
    settings = load_config()
    settings.backtesting.initial_capital = initial_capital

    # Initialize fetchers
    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    alpaca_fetcher = AlpacaOptionsDataFetcher(
        api_key=api_key,
        api_secret=api_secret,
    )

    dolthub_fetcher = DoltHubOptionsDataFetcher()

    # Fetch underlying data
    console.print(f"[bold]Loading underlying data for {symbol}...[/bold]")
    underlying_data = alpaca_fetcher.fetch_underlying_bars(
        symbol=symbol,
        start_date=start_dt,
        end_date=end_dt,
        timeframe="1Hour",
    )

    if underlying_data.empty:
        console.print(f"[red]✗ Failed to load underlying data![/red]")
        return

    console.print(f"[green]✓ Loaded {len(underlying_data):,} price bars[/green]")

    # Add technical indicators
    from alpaca_options.backtesting.data_loader import BacktestDataLoader
    data_loader = BacktestDataLoader(settings.backtesting.data)
    underlying_data = data_loader.add_technical_indicators(underlying_data)

    console.print("[green]✓ Technical indicators computed[/green]")

    # DEBUG: Check underlying_data
    console.print(f"[dim]DEBUG: underlying_data shape: {underlying_data.shape}[/dim]")
    console.print(f"[dim]DEBUG: underlying_data index type: {type(underlying_data.index)}[/dim]")
    console.print(f"[dim]DEBUG: underlying_data first/last: {underlying_data.index[0]} to {underlying_data.index[-1]}[/dim]")
    console.print(f"[dim]DEBUG: underlying_data columns: {list(underlying_data.columns)[:10]}[/dim]")

    # Fetch options chains
    console.print(f"\n[bold]Fetching options chains for {symbol}...[/bold]")

    options_data = {}
    # Use dropna(subset=['close']) to only require close price (not all indicators)
    daily_timestamps = underlying_data.resample('1D').last().dropna(subset=['close']).index

    console.print(f"[dim]Total daily timestamps: {len(daily_timestamps)}[/dim]")

    # Limit to first 10 days for faster debugging
    daily_timestamps = daily_timestamps[:10]

    console.print(f"[dim]Processing {len(daily_timestamps)} days[/dim]")

    for i, timestamp in enumerate(daily_timestamps):
        console.print(f"  Fetching chain {i+1}/{len(daily_timestamps)} ({timestamp.date()})...")

        chain = dolthub_fetcher.fetch_option_chain(
            underlying=symbol,
            as_of_date=timestamp,
        )

        if chain:
            console.print(f"    [green]✓ Got chain with {len(chain.contracts)} contracts[/green]")
            options_data[timestamp] = chain
        else:
            console.print(f"    [yellow]✗ No chain returned[/yellow]")

    if not options_data:
        console.print(f"[red]✗ No options data![/red]")
        return

    console.print(f"[green]✓ Loaded {len(options_data)} option chains[/green]")

    # Create strategy with RELAXED filters for diagnostic
    strategy = VerticalSpreadStrategy()

    strategy._config = {
        "underlyings": [symbol],
        "spread_width": 5.0,
        "min_iv_rank": 0,  # Disabled
        "min_dte": 21,
        "max_dte": 45,
        "close_dte": 14,
        "min_open_interest": 0,  # Disabled (DoltHub has no OI)
        "max_spread_percent": 20.0,  # Very relaxed
        "min_return_on_risk": 0.05,  # Very relaxed (5%)
        "rsi_oversold": 45.0,
        "rsi_overbought": 55.0,
        "min_credit": 10.0,  # Very relaxed
    }

    await strategy.initialize(strategy._config)

    # Create backtest engine
    engine = BacktestEngine(settings.backtesting, settings.risk)

    # Run backtest
    console.print(f"\n[bold]Running diagnostic backtest with DEBUG logging...[/bold]\n")

    result = await engine.run(
        strategy=strategy,
        underlying_data=underlying_data,
        options_data=options_data,
        start_date=start_dt,
        end_date=end_dt,
    )

    console.print(f"\n[bold green]✓ Diagnostic Complete[/bold green]")
    console.print(f"Total Trades: {result.metrics.total_trades}")

    if result.metrics.total_trades == 0:
        console.print("\n[yellow]⚠ Still no trades generated![/yellow]")
        console.print("[yellow]Check the DEBUG logs above to see which filter is blocking.[/yellow]")
    else:
        console.print(f"\n[green]✓ SUCCESS! Generated {result.metrics.total_trades} trades[/green]")
        console.print(f"Win Rate: {result.metrics.win_rate:.1f}%")
        console.print(f"Total Return: {result.metrics.total_return_percent:.2f}%")


if __name__ == "__main__":
    asyncio.run(main())
