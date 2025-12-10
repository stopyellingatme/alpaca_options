#!/usr/bin/env python3
"""Full AAPL backtest using DoltHub data with optimized filters."""

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
from rich.table import Table

console = Console()

# Set INFO level for cleaner output
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)-8s [%(name)s] %(message)s',
)


async def main():
    """Run comprehensive AAPL backtest with DoltHub data."""
    from alpaca_options.backtesting import BacktestEngine
    from alpaca_options.backtesting.alpaca_options_fetcher import AlpacaOptionsDataFetcher
    from alpaca_options.backtesting.dolthub_options_fetcher import DoltHubOptionsDataFetcher
    from alpaca_options.core.config import load_config
    from alpaca_options.strategies import VerticalSpreadStrategy

    console.print("\n[bold cyan]AAPL BACKTEST - DoltHub Cached Data[/bold cyan]")
    console.print("[dim]Period: 2024-03-01 to 2024-03-31 (1 month)[/dim]")
    console.print("[dim]Strategy: Vertical Spreads (Bull Put & Bear Call)[/dim]\n")

    # Test period - March only (we have cached data for this period)
    symbol = "AAPL"
    start_dt = datetime(2024, 3, 1)
    end_dt = datetime(2024, 3, 31)
    initial_capital = 10000.0

    # Load configuration
    settings = load_config()
    settings.backtesting.initial_capital = initial_capital

    # Note: Fill probability model is disabled by default
    # DoltHub has OI=0, so liquidity checks in risk manager will issue warnings (not errors)

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

    # Fetch options chains
    console.print(f"\n[bold]Fetching options chains for {symbol}...[/bold]")

    options_data = {}
    # Daily sampling
    daily_timestamps = underlying_data.resample('1D').last().dropna(subset=['close']).index

    console.print(f"[dim]Processing {len(daily_timestamps)} days[/dim]")

    for i, timestamp in enumerate(daily_timestamps):
        if (i + 1) % 10 == 0:
            console.print(f"  Progress: {i+1}/{len(daily_timestamps)} days...")

        chain = dolthub_fetcher.fetch_option_chain(
            underlying=symbol,
            as_of_date=timestamp,
        )

        if chain:
            options_data[timestamp] = chain

    if not options_data:
        console.print(f"[red]✗ No options data![/red]")
        return

    console.print(f"[green]✓ Loaded {len(options_data)} option chains[/green]")

    # Create strategy with OPTIMIZED filters for DoltHub
    strategy = VerticalSpreadStrategy()

    strategy._config = {
        "underlyings": [symbol],
        "spread_width": 5.0,

        # Relaxed for DoltHub data
        "min_iv_rank": 0,  # DoltHub has good IV data, but no rank calc
        "min_dte": 21,
        "max_dte": 45,
        "close_dte": 14,
        "min_open_interest": 0,  # CRITICAL: DoltHub has OI=0

        # Moderately relaxed quality filters
        "max_spread_percent": 15.0,  # Allow wider spreads
        "min_return_on_risk": 0.08,  # 8% minimum ROR

        # Standard direction filters
        "rsi_oversold": 45.0,
        "rsi_overbought": 55.0,
        "min_credit": 15.0,  # Minimum $15 credit
    }

    await strategy.initialize(strategy._config)

    # Create backtest engine
    engine = BacktestEngine(settings.backtesting, settings.risk)

    # Run backtest
    console.print(f"\n[bold]Running backtest...[/bold]\n")

    result = await engine.run(
        strategy=strategy,
        underlying_data=underlying_data,
        options_data=options_data,
        start_date=start_dt,
        end_date=end_dt,
    )

    # Display results
    console.print(f"\n[bold green]✓ Backtest Complete[/bold green]\n")

    # Create results table
    table = Table(title=f"Backtest Results: {symbol}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Initial Capital", f"${initial_capital:,.2f}")
    table.add_row("Final Equity", f"${result.metrics.ending_equity:,.2f}")
    table.add_row("Total Return", f"{result.metrics.total_return_percent:.2f}%")
    table.add_row("Total Trades", f"{result.metrics.total_trades}")
    table.add_row("Winning Trades", f"{result.metrics.winning_trades}")
    table.add_row("Losing Trades", f"{result.metrics.losing_trades}")
    table.add_row("Win Rate", f"{result.metrics.win_rate:.1f}%")
    table.add_row("Avg Win", f"${result.metrics.avg_win:.2f}")
    table.add_row("Avg Loss", f"${abs(result.metrics.avg_loss):.2f}")
    table.add_row("Profit Factor", f"{result.metrics.profit_factor:.2f}")
    table.add_row("Max Drawdown", f"{result.metrics.max_drawdown_percent:.2f}%")
    table.add_row("Sharpe Ratio", f"{result.metrics.sharpe_ratio:.2f}")

    console.print(table)

    # Trade summary
    if result.metrics.total_trades > 0:
        console.print(f"\n[bold]Trade Details:[/bold]")
        console.print(f"  Average holding period: {result.metrics.avg_holding_period_days:.1f} days")
        console.print(f"  Total P&L: ${result.metrics.total_return:,.2f}")

        # Calculate max win/loss from trades
        closed_trades = [t for t in result.trades if not t.is_open]
        if closed_trades:
            max_win = max(t.net_pnl for t in closed_trades)
            max_loss = min(t.net_pnl for t in closed_trades)
            if max_win > 0:
                console.print(f"  Best trade: ${max_win:.2f}")
            if max_loss < 0:
                console.print(f"  Worst trade: ${abs(max_loss):.2f}")
    else:
        console.print("\n[yellow]⚠ No trades generated - filters may be too strict[/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
