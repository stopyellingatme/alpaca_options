#!/usr/bin/env python3
"""Stock Screener Test Script.

This script runs the stock screener to find options trading opportunities.

Usage:
    uv run python scripts/run_screener.py [--mode MODE] [--universe UNIVERSE] [--max N]

Options:
    --mode: Screening mode (technical, options, hybrid) [default: hybrid]
    --universe: Symbol universe (sp500, nasdaq100, options_friendly, etfs) [default: options_friendly]
    --max: Maximum results to return [default: 20]
    --bullish: Scan for bullish (oversold) opportunities only
    --bearish: Scan for bearish (overbought) opportunities only
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Load .env file
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


async def run_screener(args):
    """Run the stock screener."""
    from alpaca_options.core.config import load_config
    from alpaca_options.alpaca.client import AlpacaClient
    from alpaca_options.screener.scanner import Scanner, ScannerConfig, ScanMode
    from alpaca_options.screener.base import ScreeningCriteria
    from alpaca_options.screener.universes import UniverseType, get_universe

    # Load config
    settings = load_config()

    # Create Alpaca client
    client = AlpacaClient(settings)

    console.print(Panel.fit(
        "[bold cyan]Stock Screener[/bold cyan]\n"
        f"Mode: {args.mode} | Universe: {args.universe} | Max Results: {args.max}",
        border_style="cyan"
    ))

    # Map arguments to enums
    mode_map = {
        "technical": ScanMode.TECHNICAL_ONLY,
        "options": ScanMode.OPTIONS_ONLY,
        "hybrid": ScanMode.HYBRID,
    }

    universe_map = {
        "sp500": UniverseType.SP500,
        "nasdaq100": UniverseType.NASDAQ100,
        "options_friendly": UniverseType.OPTIONS_FRIENDLY,
        "etfs": UniverseType.ETFS,
        "sector_etfs": UniverseType.SECTOR_ETFS,
    }

    scan_mode = mode_map.get(args.mode, ScanMode.HYBRID)
    universe_type = universe_map.get(args.universe, UniverseType.OPTIONS_FRIENDLY)

    # Get universe
    universe = get_universe(universe_type)
    console.print(f"[dim]Scanning {len(universe)} symbols from {universe.name}...[/dim]\n")

    # Create scanner config
    config = ScannerConfig(
        mode=scan_mode,
        universe_type=universe_type,
        max_results=args.max,
        min_combined_score=40.0,  # Lower threshold for testing
        require_options=args.mode != "technical",
    )

    # Create screening criteria
    criteria = ScreeningCriteria(
        min_price=10.0,
        max_price=500.0,
        min_volume=100_000,  # Lower for testing
        min_dollar_volume=1_000_000,
        rsi_oversold=35.0 if args.bullish else None,
        rsi_overbought=65.0 if args.bearish else None,
    )

    # Create scanner
    scanner = Scanner(
        trading_client=client.trading,
        stock_data_client=client.stock_data,
        options_data_client=client.option_data,
        config=config,
        criteria=criteria,
    )

    # Run scan
    console.print("[yellow]Running scan...[/yellow]")

    try:
        if args.bullish:
            results = await scanner.scan_bullish(max_results=args.max)
        elif args.bearish:
            results = await scanner.scan_bearish(max_results=args.max)
        else:
            results = await scanner.scan()

        # Display results
        if not results:
            console.print("[yellow]No opportunities found matching criteria.[/yellow]")
            return

        # Create results table
        table = Table(title=f"Screening Results ({len(results)} opportunities)")

        table.add_column("Symbol", style="cyan", width=8)
        table.add_column("Score", justify="right", width=6)
        table.add_column("Price", justify="right", width=10)
        table.add_column("RSI", justify="right", width=6)
        table.add_column("Signal", width=8)
        table.add_column("IV", justify="right", width=8)
        table.add_column("Expirations", justify="right", width=11)

        for result in results:
            price = f"${result.price:.2f}" if result.price else "N/A"
            rsi = f"{result.rsi:.1f}" if result.rsi else "N/A"
            signal = result.signal or "neutral"
            iv = f"{result.implied_volatility:.1%}" if result.implied_volatility else "N/A"

            # Color signal
            if signal == "bullish":
                signal = f"[green]{signal}[/green]"
            elif signal == "bearish":
                signal = f"[red]{signal}[/red]"

            # Get expirations from options result
            exps = "N/A"
            if result.options_result and result.options_result.num_expirations:
                exps = str(result.options_result.num_expirations)

            table.add_row(
                result.symbol,
                f"{result.combined_score:.0f}",
                price,
                rsi,
                signal,
                iv,
                exps,
            )

        console.print(table)

        # Print summary
        console.print(f"\n[green]Found {len(results)} opportunities[/green]")

        bullish = [r for r in results if r.signal == "bullish"]
        bearish = [r for r in results if r.signal == "bearish"]

        if bullish:
            console.print(f"[green]Bullish signals: {', '.join(r.symbol for r in bullish[:5])}[/green]")
        if bearish:
            console.print(f"[red]Bearish signals: {', '.join(r.symbol for r in bearish[:5])}[/red]")

    except Exception as e:
        console.print(f"[red]Error during scan: {e}[/red]")
        logging.exception("Scan error")
        raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Stock Screener")
    parser.add_argument(
        "--mode", "-m",
        choices=["technical", "options", "hybrid"],
        default="hybrid",
        help="Screening mode"
    )
    parser.add_argument(
        "--universe", "-u",
        choices=["sp500", "nasdaq100", "options_friendly", "etfs", "sector_etfs"],
        default="options_friendly",
        help="Symbol universe to scan"
    )
    parser.add_argument(
        "--max", "-n",
        type=int,
        default=20,
        help="Maximum results to return"
    )
    parser.add_argument(
        "--bullish",
        action="store_true",
        help="Scan for bullish (oversold) opportunities only"
    )
    parser.add_argument(
        "--bearish",
        action="store_true",
        help="Scan for bearish (overbought) opportunities only"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.debug else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run screener
    try:
        asyncio.run(run_screener(args))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
