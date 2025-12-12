#!/usr/bin/env python3
"""Download a representative sample of extended historical chains for backtesting.

This script:
1. Queries DoltHub for actual available dates
2. Samples them efficiently (weekly or monthly)
3. Downloads and caches locally

Optimized for fast download with good backtest coverage.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel
from rich.table import Table

from alpaca_options.backtesting.dolthub_options_fetcher import DoltHubOptionsDataFetcher

console = Console()


def sample_dates_weekly(dates: list[datetime]) -> list[datetime]:
    """Sample dates weekly (keep every 5th date for ~weekly sampling)."""
    if not dates:
        return []

    # Sort by date
    dates = sorted(dates)

    # Sample every 5 trading days (~weekly)
    sampled = []
    for i in range(0, len(dates), 5):
        sampled.append(dates[i])

    return sampled


async def main():
    """Download extended historical sample."""
    console.print(Panel.fit(
        "[bold cyan]Downloading Extended Historical Sample[/bold cyan]\\n"
        "Strategy: Query available dates, sample weekly, download",
        border_style="cyan"
    ))

    # Initialize fetcher
    try:
        fetcher = DoltHubOptionsDataFetcher()
    except RuntimeError as e:
        console.print(f"[red]ERROR: {e}[/red]")
        return 1

    symbols = ["AAPL", "MSFT", "NVDA", "SPY"]
    start_date = datetime(2019, 2, 9)
    end_date = datetime(2024, 12, 31)

    console.print(f"\\n[dim]Symbols: {', '.join(symbols)}[/dim]")
    console.print(f"[dim]Range: {start_date.date()} to {end_date.date()}[/dim]\\n")

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
            console.print(f"[bold cyan]Processing {symbol}[/bold cyan]")

            # Get available dates
            task_query = progress.add_task(f"[dim]Querying available dates...", total=None)
            available_dates = fetcher.get_available_dates(symbol, start_date, end_date)
            progress.remove_task(task_query)

            if not available_dates:
                console.print(f"  [yellow]No data available for {symbol}[/yellow]")
                continue

            console.print(f"  [green]Found {len(available_dates)} available dates[/green]")

            # Sample weekly
            sampled_dates = sample_dates_weekly(available_dates)
            console.print(f"  [green]Sampled to {len(sampled_dates)} weekly points[/green]")

            # Download sampled dates
            task = progress.add_task(
                f"[cyan]Downloading {symbol}...",
                total=len(sampled_dates)
            )

            for date in sampled_dates:
                # Check cache
                cache_file = fetcher._cache_dir / f"{symbol}_{date.date()}_chain.json"

                if cache_file.exists():
                    stats[symbol]["cached"] += 1
                    progress.update(task, advance=1)
                    continue

                # Fetch and cache
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
                    console.print(f"\\n[red]Error fetching {symbol} on {date.date()}: {e}[/red]")
                    stats[symbol]["failed"] += 1

                progress.update(task, advance=1)

            progress.update(task, description=f"[green]✓ {symbol} complete")

    # Display summary
    console.print("\\n")
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
    console.print(f"\\n[green]Cache location: {fetcher._cache_dir}[/green]")
    console.print(f"[green]Total chains: {total_downloaded + total_cached}[/green]")

    # Next steps
    console.print("\\n[bold cyan]Next Steps:[/bold cyan]")
    console.print("  1. Run extended backtest:")
    console.print("     [dim]uv run python scripts/backtest_multi_symbol.py[/dim]")
    console.print("  2. Compare results with 9-month backtest")
    console.print("  3. Analyze performance across market cycles")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
