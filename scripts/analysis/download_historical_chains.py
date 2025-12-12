#!/usr/bin/env python3
"""Download historical options chains from DoltHub for extended backtesting.

This script downloads real historical options data from DoltHub's free database
and caches it locally for faster backtesting.

DoltHub Coverage: 2019-2024 (6 years), 2,098 symbols

Usage:
    # Download 2 years for AAPL, MSFT, NVDA, SPY
    uv run python scripts/download_historical_chains.py

    # Download custom symbols and date range
    uv run python scripts/download_historical_chains.py --symbols AAPL TSLA --start 2022-01-01 --end 2024-12-31

    # Download with custom frequency (weekly instead of daily)
    uv run python scripts/download_historical_chains.py --frequency weekly
"""

import asyncio
import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.table import Table

console = Console()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)-8s [%(name)s] %(message)s',
)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Download historical options chains from DoltHub"
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["AAPL", "MSFT", "NVDA", "SPY"],
        help="Symbols to download (default: AAPL MSFT NVDA SPY)",
    )
    parser.add_argument(
        "--start",
        type=str,
        default=(datetime.now() - timedelta(days=730)).strftime("%Y-%m-%d"),  # 2 years ago
        help="Start date (YYYY-MM-DD, default: 2 years ago)",
    )
    parser.add_argument(
        "--end",
        type=str,
        default=datetime.now().strftime("%Y-%m-%d"),
        help="End date (YYYY-MM-DD, default: today)",
    )
    parser.add_argument(
        "--frequency",
        type=str,
        choices=["daily", "weekly", "monthly"],
        default="daily",
        help="Download frequency (default: daily)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing cached data",
    )
    return parser.parse_args()


def get_date_range(start_date: datetime, end_date: datetime, frequency: str):
    """Generate list of dates based on frequency.

    Args:
        start_date: Start date
        end_date: End date
        frequency: 'daily', 'weekly', or 'monthly'

    Returns:
        List of datetime objects
    """
    dates = []
    current = start_date

    while current <= end_date:
        # Only include weekdays (Mon-Fri)
        if current.weekday() < 5:
            dates.append(current)

        # Increment based on frequency
        if frequency == "daily":
            current += timedelta(days=1)
        elif frequency == "weekly":
            current += timedelta(weeks=1)
        else:  # monthly
            # Move to next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

    return dates


async def download_chains(
    symbols: list[str],
    start_date: datetime,
    end_date: datetime,
    frequency: str,
    overwrite: bool,
):
    """Download historical option chains.

    Args:
        symbols: List of symbols to download
        start_date: Start date
        end_date: End date
        frequency: Download frequency
        overwrite: Whether to overwrite existing cache
    """
    from alpaca_options.backtesting.dolthub_options_fetcher import DoltHubOptionsDataFetcher

    console.print(Panel.fit(
        f"[bold cyan]Downloading Historical Options Chains from DoltHub[/bold cyan]\n"
        f"Symbols: {', '.join(symbols)}\n"
        f"Period: {start_date.date()} to {end_date.date()}\n"
        f"Frequency: {frequency}",
        border_style="cyan"
    ))

    # Initialize fetcher
    try:
        fetcher = DoltHubOptionsDataFetcher()
    except RuntimeError as e:
        console.print(f"\n[red]ERROR: {e}[/red]\n")
        console.print("[yellow]Install Dolt CLI:[/yellow]")
        console.print("  macOS: brew install dolt")
        console.print("  Linux: sudo bash -c 'curl -L https://github.com/dolthub/dolt/releases/latest/download/install.sh | bash'")
        console.print("  Windows: https://docs.dolthub.com/introduction/installation")
        return

    # Generate date range
    dates = get_date_range(start_date, end_date, frequency)

    console.print(f"\n[dim]Generated {len(dates)} dates to download[/dim]")

    # Download for each symbol
    stats = {symbol: {"downloaded": 0, "cached": 0, "failed": 0} for symbol in symbols}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:

        for symbol in symbols:
            task = progress.add_task(
                f"[cyan]Downloading {symbol}...",
                total=len(dates)
            )

            for date in dates:
                # Check if already cached
                cache_file = fetcher._cache_dir / f"{symbol}_{date.date()}_chain.json"

                if cache_file.exists() and not overwrite:
                    stats[symbol]["cached"] += 1
                    progress.update(task, advance=1)
                    continue

                # Fetch chain
                try:
                    chain = fetcher.fetch_option_chain(
                        underlying=symbol,
                        as_of_date=date,
                    )

                    if chain:
                        stats[symbol]["downloaded"] += 1
                    else:
                        stats[symbol]["failed"] += 1

                except Exception as e:
                    console.print(f"\n[red]Error fetching {symbol} on {date.date()}: {e}[/red]")
                    stats[symbol]["failed"] += 1

                progress.update(task, advance=1)

            progress.update(task, description=f"[green]✓ {symbol} complete")

    # Display summary
    console.print("\n")
    console.print(Panel.fit(
        "[bold green]Download Complete[/bold green]",
        border_style="green"
    ))

    summary_table = Table(title="Download Summary")
    summary_table.add_column("Symbol", style="cyan")
    summary_table.add_column("Downloaded", justify="right", style="green")
    summary_table.add_column("Cached", justify="right", style="yellow")
    summary_table.add_column("Failed", justify="right", style="red")
    summary_table.add_column("Total Files", justify="right", style="white")

    total_downloaded = 0
    total_cached = 0
    total_failed = 0

    for symbol in symbols:
        downloaded = stats[symbol]["downloaded"]
        cached = stats[symbol]["cached"]
        failed = stats[symbol]["failed"]
        total_files = downloaded + cached

        total_downloaded += downloaded
        total_cached += cached
        total_failed += failed

        summary_table.add_row(
            symbol,
            str(downloaded),
            str(cached),
            str(failed),
            str(total_files),
        )

    # Add totals row
    summary_table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_downloaded}[/bold]",
        f"[bold]{total_cached}[/bold]",
        f"[bold]{total_failed}[/bold]",
        f"[bold]{total_downloaded + total_cached}[/bold]",
    )

    console.print(summary_table)

    # Cache location
    console.print(f"\n[green]Cache location: {fetcher._cache_dir}[/green]")
    console.print(f"[dim]Total files: {total_downloaded + total_cached}[/dim]")

    # Estimate backtest capability
    trading_days_per_year = 252
    years_of_data = (end_date - start_date).days / 365.25

    console.print(f"\n[bold cyan]Backtest Capability:[/bold cyan]")
    console.print(f"  Period: {start_date.date()} to {end_date.date()}")
    console.print(f"  Duration: {years_of_data:.1f} years")
    console.print(f"  Estimated trading days: {int(years_of_data * trading_days_per_year)}")
    console.print(f"  Symbols: {', '.join(symbols)}")


def main():
    """Main entry point."""
    args = parse_args()

    # Parse dates
    try:
        start_date = datetime.strptime(args.start, "%Y-%m-%d")
        end_date = datetime.strptime(args.end, "%Y-%m-%d")
    except ValueError as e:
        console.print(f"[red]Invalid date format: {e}[/red]")
        console.print("[yellow]Use YYYY-MM-DD format[/yellow]")
        return

    # Validate date range
    if start_date >= end_date:
        console.print("[red]Start date must be before end date[/red]")
        return

    # Check DoltHub limits (2019-2024)
    dolthub_start = datetime(2019, 1, 1)
    dolthub_end = datetime(2024, 12, 31)

    if start_date < dolthub_start:
        console.print(f"[yellow]Warning: DoltHub data starts {dolthub_start.date()}, adjusting start date[/yellow]")
        start_date = dolthub_start

    if end_date > dolthub_end:
        console.print(f"[yellow]Warning: DoltHub data ends {dolthub_end.date()}, adjusting end date[/yellow]")
        end_date = dolthub_end

    # Run download
    asyncio.run(download_chains(
        symbols=args.symbols,
        start_date=start_date,
        end_date=end_date,
        frequency=args.frequency,
        overwrite=args.overwrite,
    ))


if __name__ == "__main__":
    main()
