#!/usr/bin/env python3
"""Test Alpaca historical options data fetching.

This script tests:
1. Fetching underlying stock bars
2. Fetching current option chain
3. Hybrid data loading (real + synthetic)
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def test_alpaca_fetcher():
    """Test the AlpacaOptionsDataFetcher directly."""
    from alpaca_options.backtesting import AlpacaOptionsDataFetcher, ALPACA_OPTIONS_DATA_START

    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if not api_key or not api_secret:
        console.print("[red]Error: ALPACA_API_KEY and ALPACA_SECRET_KEY must be set[/red]")
        return False

    console.print(Panel.fit(
        "[bold]Testing Alpaca Options Data Fetcher[/bold]",
        border_style="blue"
    ))

    fetcher = AlpacaOptionsDataFetcher(
        api_key=api_key,
        api_secret=api_secret,
        cache_dir=project_root / "data" / "alpaca_test_cache",
    )

    # Test 1: Fetch underlying bars
    console.print("\n[bold]Test 1: Fetching SPY hourly bars[/bold]")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)

    bars = fetcher.fetch_underlying_bars(
        symbol="SPY",
        start_date=start_date,
        end_date=end_date,
        timeframe="1Hour",
    )

    if not bars.empty:
        console.print(f"[green]Success![/green] Fetched {len(bars)} bars")
        console.print(f"Date range: {bars.index.min()} to {bars.index.max()}")
        console.print(f"Latest close: ${bars['close'].iloc[-1]:.2f}")
    else:
        console.print("[yellow]No bars returned[/yellow]")

    # Test 2: Fetch current option chain
    console.print("\n[bold]Test 2: Fetching SPY option chain[/bold]")
    console.print(f"(Note: Alpaca options data available since {ALPACA_OPTIONS_DATA_START.date()})")

    chain = fetcher.fetch_option_chain(
        underlying="SPY",
        as_of_date=datetime.now(),
    )

    if chain:
        console.print(f"[green]Success![/green] Got chain with {len(chain.contracts)} contracts")
        console.print(f"Underlying price: ${chain.underlying_price:.2f}")

        # Show sample contracts
        table = Table(title="Sample Contracts (first 10)")
        table.add_column("Symbol", style="cyan")
        table.add_column("Type")
        table.add_column("Strike", justify="right")
        table.add_column("Expiration")
        table.add_column("Bid", justify="right")
        table.add_column("Ask", justify="right")
        table.add_column("Delta", justify="right")
        table.add_column("IV", justify="right")

        for contract in chain.contracts[:10]:
            table.add_row(
                contract.symbol,
                contract.option_type,
                f"${contract.strike:.2f}",
                contract.expiration.strftime("%Y-%m-%d"),
                f"${contract.bid:.2f}",
                f"${contract.ask:.2f}",
                f"{contract.delta:.3f}" if contract.delta else "N/A",
                f"{contract.implied_volatility:.1%}" if contract.implied_volatility else "N/A",
            )

        console.print(table)
    else:
        console.print("[yellow]No chain returned (may need OPRA subscription)[/yellow]")

    # Test 3: Check data availability
    console.print("\n[bold]Test 3: Data availability check[/bold]")
    test_dates = [
        datetime(2023, 6, 1),  # Before Alpaca data
        datetime(2024, 3, 1),  # After Alpaca data
        datetime.now(),        # Current
    ]

    for date in test_dates:
        available = fetcher.is_data_available(date)
        status = "[green]Available[/green]" if available else "[yellow]Synthetic only[/yellow]"
        console.print(f"  {date.date()}: {status}")

    return True


def test_data_loader_hybrid():
    """Test the hybrid data loader."""
    from alpaca_options.backtesting import BacktestDataLoader
    from alpaca_options.core.config import BacktestDataConfig

    console.print("\n" + "=" * 60)
    console.print(Panel.fit(
        "[bold]Testing Hybrid Data Loader[/bold]",
        border_style="blue"
    ))

    config = BacktestDataConfig(
        cache_dir=str(project_root / "data" / "historical"),
    )

    loader = BacktestDataLoader(config)

    console.print(f"Alpaca credentials available: {loader.has_alpaca_credentials}")

    # Test with recent date range (should use Alpaca if available)
    end_date = datetime.now()
    start_date = datetime(2024, 10, 1)  # Recent period

    console.print(f"\n[bold]Loading SPY data for {start_date.date()} to {end_date.date()}[/bold]")

    underlying = loader.load_underlying_data(
        symbol="SPY",
        start_date=start_date,
        end_date=end_date,
        timeframe="1h",
    )

    if not underlying.empty:
        console.print(f"[green]Loaded {len(underlying)} underlying bars[/green]")

        # Add technical indicators
        underlying = loader.add_technical_indicators(underlying)

        # Test hybrid options loading
        console.print("\n[bold]Loading hybrid options data...[/bold]")
        options = loader.load_options_data_hybrid(
            underlying_data=underlying,
            symbol="SPY",
            start_date=start_date,
            end_date=end_date,
        )

        console.print(f"Total options snapshots: {len(options)}")

        # Show data source breakdown
        if options:
            first_date = min(options.keys())
            last_date = max(options.keys())
            console.print(f"Date range: {first_date} to {last_date}")

            # Sample chain info
            sample_chain = list(options.values())[0]
            console.print(f"Sample chain contracts: {len(sample_chain.contracts)}")
    else:
        console.print("[yellow]No underlying data loaded[/yellow]")


def main():
    """Run all tests."""
    console.print(Panel.fit(
        "[bold green]Alpaca Historical Options Data Test[/bold green]\n"
        "Testing data fetching and hybrid loading",
        border_style="green"
    ))

    try:
        # Test 1: Direct fetcher
        success = test_alpaca_fetcher()

        if success:
            # Test 2: Hybrid loader
            test_data_loader_hybrid()

        console.print("\n[bold green]Tests completed![/bold green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
