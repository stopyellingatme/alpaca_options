#!/usr/bin/env python3
"""Paper Trading Launch Script with Screener Integration.

This script starts the paper trading bot with optional screener integration
to dynamically discover trading opportunities.

Requires Alpaca API credentials in environment variables:
  - ALPACA_API_KEY
  - ALPACA_SECRET_KEY

Usage:
    uv run python scripts/run_paper_trading.py
    uv run python scripts/run_paper_trading.py --screener  # Enable dynamic screener
    uv run python scripts/run_paper_trading.py --screener --universe options_friendly
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

# Load .env file automatically
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def check_prerequisites() -> bool:
    """Check that all prerequisites are met before starting."""
    errors = []

    # Check API keys
    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if not api_key:
        errors.append("ALPACA_API_KEY environment variable not set")
    if not api_secret:
        errors.append("ALPACA_SECRET_KEY environment variable not set")

    # Check config file exists
    config_path = project_root / "config" / "paper_trading.yaml"
    if not config_path.exists():
        errors.append(f"Config file not found: {config_path}")

    # Check logs directory
    logs_dir = project_root / "data" / "logs"
    if not logs_dir.exists():
        logs_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"[dim]Created logs directory: {logs_dir}[/dim]")

    if errors:
        console.print("[bold red]Prerequisites Check Failed:[/bold red]")
        for error in errors:
            console.print(f"  [red]- {error}[/red]")
        return False

    return True


def display_startup_info(screener_enabled: bool = False, universe: str = "options_friendly"):
    """Display startup information."""
    title = "[bold green]Paper Trading Bot[/bold green]"
    if screener_enabled:
        title += "\n[cyan]Screener Integration Enabled[/cyan]"
    else:
        title += "\nVertical Spread Strategy - LOW Tier"

    console.print(Panel.fit(
        f"{title}\n"
        f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        border_style="green"
    ))

    # Strategy info
    table = Table(title="Configuration Summary", show_header=False)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Mode", "[green]PAPER TRADING[/green]")

    if screener_enabled:
        table.add_row("Screener", "[green]ENABLED[/green]")
        table.add_row("Universe", universe)
        table.add_row("Scan Mode", "Hybrid (Technical + Options)")
        table.add_row("Discovery", "Bullish, Bearish, High IV")
    else:
        table.add_row("Strategy", "Vertical Spread")
        table.add_row("Underlying", "QQQ")
        table.add_row("RSI Thresholds", "40 (oversold) / 60 (overbought)")

    table.add_row("Max Concurrent Positions", "3")  # Updated to match validated config
    table.add_row("Max Contracts per Trade", "2")  # Updated to match validated config
    table.add_row("Daily Loss Limit", "$500")  # Updated to match validated config

    console.print(table)
    console.print()


async def run_paper_trading(screener_enabled: bool = False, universe: str = "options_friendly"):
    """Run the paper trading bot."""
    from alpaca_options.core.config import load_config
    from alpaca_options.core.engine import TradingEngine

    # Load configuration
    config_path = project_root / "config" / "paper_trading.yaml"
    settings = load_config(config_path)

    # Ensure paper trading mode
    settings.alpaca.paper = True

    # Enable screener if requested
    if screener_enabled:
        settings.screener.enabled = True
        settings.screener.mode = "hybrid"
        settings.screener.universe = universe
        settings.screener.auto_refresh_seconds = 300  # 5 minute scans
        settings.screener.min_combined_score = 60.0  # Match config
        console.print(f"[cyan]Screener enabled with {universe} universe[/cyan]")

    # Create engine
    engine = TradingEngine(settings)

    # Handle shutdown gracefully
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        console.print("\n[yellow]Shutdown signal received...[/yellow]")
        shutdown_event.set()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Start the engine
        console.print("[dim]Starting trading engine...[/dim]")
        await engine.start()

        console.print("[bold green]Engine started successfully![/bold green]")
        console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        # Get and display account info
        account = engine.get_account_info()
        if account:
            console.print(f"[cyan]Account Equity:[/cyan] ${float(account.get('equity', 0)):,.2f}")
            console.print(f"[cyan]Buying Power:[/cyan] ${float(account.get('buying_power', 0)):,.2f}")
            console.print()

        # Display active strategies
        strategies = engine.get_active_strategies()
        if strategies:
            console.print(f"[green]Active Strategies:[/green] {', '.join(strategies)}")
        else:
            console.print("[yellow]No strategies active[/yellow]")

        # Display screener status if enabled
        if screener_enabled:
            console.print(f"[cyan]Screener Universe:[/cyan] {universe}")
            console.print("[cyan]Screener Mode:[/cyan] Hybrid (Technical + Options)")
            console.print("[dim]Screener will discover opportunities automatically[/dim]")

        console.print("\n[bold]Monitoring for trading signals...[/bold]\n")

        # Periodic status updates
        last_status_time = datetime.now()
        status_interval = 60  # Print status every 60 seconds

        while not shutdown_event.is_set():
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                # Check if it's time to print status
                if (datetime.now() - last_status_time).seconds >= status_interval:
                    last_status_time = datetime.now()

                    # Print screener status
                    if screener_enabled:
                        stats = engine.get_screener_stats()
                        if stats:
                            console.print(
                                f"[dim][{datetime.now().strftime('%H:%M:%S')}] "
                                f"Screener: {stats.get('scan_count', 0)} scans, "
                                f"Trading queue: {stats.get('trading_queue_size', 0)}, "
                                f"Total found: {stats.get('total_opportunities_found', 0)}[/dim]"
                            )

                        screener_symbols = engine.get_screener_symbols()
                        if screener_symbols:
                            console.print(
                                f"[dim]Discovered symbols: {', '.join(screener_symbols[:5])}"
                                f"{'...' if len(screener_symbols) > 5 else ''}[/dim]"
                            )

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logging.exception("Error in paper trading")
        raise
    finally:
        # Stop the engine
        console.print("[dim]Stopping trading engine...[/dim]")
        await engine.stop()
        console.print("[green]Engine stopped.[/green]")


async def run_with_dashboard(screener_enabled: bool = False, universe: str = "options_friendly"):
    """Run the paper trading bot with the TUI dashboard."""
    from alpaca_options.core.config import load_config
    from alpaca_options.core.engine import TradingEngine
    from alpaca_options.ui.dashboard import TradingDashboard

    # Load configuration
    config_path = project_root / "config" / "paper_trading.yaml"
    settings = load_config(config_path)

    # Ensure paper trading mode
    settings.alpaca.paper = True

    # Enable screener if requested
    if screener_enabled:
        settings.screener.enabled = True
        settings.screener.mode = "hybrid"
        settings.screener.universe = universe  # Correct field name
        settings.screener.auto_refresh_seconds = 300  # 5 minute scans
        settings.screener.min_combined_score = 60.0  # Match config (was 50.0)
        console.print(f"[cyan]Screener enabled with {universe} universe[/cyan]")

    # Create engine and dashboard
    engine = TradingEngine(settings)
    dashboard = TradingDashboard(engine, settings)

    try:
        await dashboard.run()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logging.exception("Error in paper trading")
        raise


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Paper Trading Bot with Screener")
    parser.add_argument(
        "--dashboard", "-d",
        action="store_true",
        help="Run with TUI dashboard (requires terminal)"
    )
    parser.add_argument(
        "--screener", "-s",
        action="store_true",
        help="Enable dynamic screener to discover opportunities"
    )
    parser.add_argument(
        "--universe", "-u",
        choices=["sp500", "nasdaq100", "options_friendly", "etfs", "sector_etfs"],
        default="options_friendly",
        help="Symbol universe for screener (default: options_friendly)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    # Setup logging - avoid StreamHandler when using dashboard to prevent output conflicts
    log_level = logging.DEBUG if args.debug else logging.INFO
    handlers = [
        logging.FileHandler(project_root / "data" / "logs" / "paper_trading.log"),
    ]
    # Only add StreamHandler if NOT using dashboard (Rich Live conflicts with stdout logging)
    if not args.dashboard:
        handlers.append(logging.StreamHandler())

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )

    # Check prerequisites
    if not check_prerequisites():
        sys.exit(1)

    # Display startup info
    display_startup_info(
        screener_enabled=args.screener,
        universe=args.universe,
    )

    # Run the bot
    try:
        if args.dashboard:
            asyncio.run(run_with_dashboard(
                screener_enabled=args.screener,
                universe=args.universe,
            ))
        else:
            asyncio.run(run_paper_trading(
                screener_enabled=args.screener,
                universe=args.universe,
            ))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Fatal error: {e}[/red]")
        sys.exit(1)

    console.print("\n[green]Paper trading session ended.[/green]")


if __name__ == "__main__":
    main()
