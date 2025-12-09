#!/usr/bin/env python3
"""Check DoltHub data coverage for extended backtesting."""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from rich.console import Console
from rich.table import Table
from alpaca_options.backtesting.dolthub_options_fetcher import DoltHubOptionsDataFetcher

console = Console()

def main():
    """Check data availability for backtest symbols."""

    console.print("[bold cyan]Checking DoltHub Data Coverage[/bold cyan]\n")

    # Initialize fetcher
    try:
        fetcher = DoltHubOptionsDataFetcher()
    except RuntimeError as e:
        console.print(f"[red]ERROR: {e}[/red]")
        return 1

    symbols = ["AAPL", "MSFT", "NVDA", "SPY"]

    # Full DoltHub range
    start_date = datetime(2019, 1, 1)
    end_date = datetime(2024, 12, 31)

    console.print(f"[dim]Checking coverage for: {', '.join(symbols)}[/dim]")
    console.print(f"[dim]Date range: {start_date.date()} to {end_date.date()}[/dim]\n")

    # Create results table
    table = Table(title="DoltHub Data Coverage")
    table.add_column("Symbol", style="cyan")
    table.add_column("Earliest Date", style="white")
    table.add_column("Latest Date", style="white")
    table.add_column("Trading Days", justify="right", style="green")
    table.add_column("Years", justify="right", style="yellow")

    for symbol in symbols:
        console.print(f"[dim]Querying {symbol}...[/dim]")

        # Get available dates
        dates = fetcher.get_available_dates(symbol, start_date, end_date)

        if dates:
            earliest = min(dates).date()
            latest = max(dates).date()
            trading_days = len(dates)
            years = (latest.year - earliest.year) + 1

            table.add_row(
                symbol,
                str(earliest),
                str(latest),
                str(trading_days),
                str(years),
            )
        else:
            table.add_row(
                symbol,
                "[red]No data[/red]",
                "[red]No data[/red]",
                "0",
                "0",
            )

    console.print(table)

    # Summary
    console.print("\n[bold green]DoltHub Coverage: 2019-2024[/bold green]")
    console.print("[dim]Use scripts/download_historical_chains.py to cache data locally[/dim]")

    return 0

if __name__ == "__main__":
    sys.exit(main())
