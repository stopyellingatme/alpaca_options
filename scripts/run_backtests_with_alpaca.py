#!/usr/bin/env python3
"""Run backtests using real Alpaca historical options data.

This script runs backtests using:
- Real Alpaca options chain data (available from Feb 2024)
- Hybrid loading: real data when available, synthetic fallback

Requires ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from alpaca_options.backtesting import (
    BacktestDataLoader,
    BacktestEngine,
    ALPACA_OPTIONS_DATA_START,
)
from alpaca_options.core.config import load_config
from alpaca_options.strategies import (
    IronCondorStrategy,
    VerticalSpreadStrategy,
    WheelStrategy,
)

console = Console()


async def run_single_backtest(
    strategy_name: str,
    strategy_class,
    symbol: str,
    settings,
    start_date: datetime,
    end_date: datetime,
    use_hybrid: bool = True,
):
    """Run a single backtest and return results."""
    console.print(f"\n[bold blue]{'='*60}[/bold blue]")
    console.print(f"[bold blue]Backtesting: {strategy_name} on {symbol}[/bold blue]")
    console.print(f"[bold blue]{'='*60}[/bold blue]")

    # Create strategy instance
    strat = strategy_class()

    # Configure strategy
    strat_config = settings.strategies.get(strategy_name.lower().replace(" ", "_"))
    if strat_config:
        config = strat_config.config.copy()
    else:
        config = {}

    config["underlyings"] = [symbol]

    # Properly initialize the strategy with config
    await strat.initialize(config)

    # Load data with Alpaca credentials
    data_loader = BacktestDataLoader(
        settings.backtesting.data,
        api_key=os.environ.get("ALPACA_API_KEY"),
        api_secret=os.environ.get("ALPACA_SECRET_KEY"),
    )

    console.print(f"[dim]Loading {symbol} data...[/dim]")
    underlying_data = data_loader.load_underlying_data(
        symbol, start_date, end_date, "1h"
    )

    if underlying_data.empty:
        console.print(f"[red]No data found for {symbol}[/red]")
        return None

    console.print(f"[dim]Loaded {len(underlying_data)} bars[/dim]")

    # Add technical indicators if not present
    if "rsi_14" not in underlying_data.columns:
        underlying_data = data_loader.add_technical_indicators(underlying_data)

    # Load options data - use hybrid mode if available
    if use_hybrid and data_loader.has_alpaca_credentials:
        console.print(f"[dim]Loading hybrid options data (real + synthetic)...[/dim]")
        options_data = data_loader.load_options_data_hybrid(
            underlying_data=underlying_data,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

        # Count real vs synthetic
        real_count = sum(
            1 for ts in options_data.keys()
            if ts >= ALPACA_OPTIONS_DATA_START
        )
        synthetic_count = len(options_data) - real_count
        console.print(
            f"[dim]Loaded {len(options_data)} chains "
            f"({real_count} real Alpaca, {synthetic_count} synthetic)[/dim]"
        )
    else:
        console.print(f"[dim]Generating synthetic options chains...[/dim]")
        options_data = data_loader.generate_synthetic_options_data(
            underlying_data, symbol
        )
        console.print(f"[dim]Generated {len(options_data)} option chain snapshots[/dim]")

    # Run backtest
    console.print(f"[dim]Running backtest...[/dim]")
    engine = BacktestEngine(settings.backtesting, settings.risk, settings.trading)

    result = await engine.run(
        strategy=strat,
        underlying_data=underlying_data,
        options_data=options_data,
        start_date=start_date,
        end_date=end_date,
    )

    return result


def display_results(results: dict):
    """Display comparison of all backtest results."""
    console.print("\n\n")
    console.print(Panel.fit(
        "[bold green]BACKTEST RESULTS COMPARISON[/bold green]",
        border_style="green"
    ))

    # Create comparison table
    table = Table(title="Strategy Performance Comparison", show_header=True)
    table.add_column("Metric", style="cyan", width=25)

    for name in results.keys():
        table.add_column(name, style="white", justify="right", width=18)

    # Metrics to compare
    metrics = [
        ("Total Return", lambda m: f"${m.total_return:,.2f}"),
        ("Return %", lambda m: f"{m.total_return_percent:.2f}%"),
        ("Annualized Return", lambda m: f"{m.annualized_return:.2f}%"),
        ("Sharpe Ratio", lambda m: f"{m.sharpe_ratio:.2f}"),
        ("Sortino Ratio", lambda m: f"{m.sortino_ratio:.2f}"),
        ("Max Drawdown", lambda m: f"${m.max_drawdown:,.2f}"),
        ("Max Drawdown %", lambda m: f"{m.max_drawdown_percent:.2f}%"),
        ("Win Rate", lambda m: f"{m.win_rate:.1f}%"),
        ("Profit Factor", lambda m: f"{m.profit_factor:.2f}"),
        ("Total Trades", lambda m: str(m.total_trades)),
        ("Winning Trades", lambda m: str(m.winning_trades)),
        ("Losing Trades", lambda m: str(m.losing_trades)),
        ("Avg Win", lambda m: f"${m.avg_win:,.2f}"),
        ("Avg Loss", lambda m: f"${m.avg_loss:,.2f}"),
        ("Avg Holding Days", lambda m: f"{m.avg_holding_period_days:.1f}"),
        ("Total Commissions", lambda m: f"${m.total_commissions:,.2f}"),
        ("Starting Equity", lambda m: f"${m.starting_equity:,.2f}"),
        ("Ending Equity", lambda m: f"${m.ending_equity:,.2f}"),
    ]

    for metric_name, formatter in metrics:
        row = [metric_name]
        for name, result in results.items():
            if result is not None:
                row.append(formatter(result.metrics))
            else:
                row.append("N/A")
        table.add_row(*row)

    console.print(table)

    # Display individual trade summaries
    for name, result in results.items():
        if result is None:
            continue

        console.print(f"\n[bold]{name} - Trade Summary:[/bold]")
        if result.trades:
            trade_table = Table(show_header=True, show_lines=True)
            trade_table.add_column("Trade ID", style="dim")
            trade_table.add_column("Type")
            trade_table.add_column("Entry")
            trade_table.add_column("Exit")
            trade_table.add_column("P&L", justify="right")
            trade_table.add_column("Status")

            # Show first 10 trades
            for trade in result.trades[:10]:
                pnl_style = "green" if trade.net_pnl > 0 else "red"
                trade_table.add_row(
                    trade.trade_id,
                    trade.signal_type.value,
                    trade.entry_time.strftime("%Y-%m-%d"),
                    trade.exit_time.strftime("%Y-%m-%d") if trade.exit_time else "-",
                    f"[{pnl_style}]${trade.net_pnl:,.2f}[/{pnl_style}]",
                    trade.status.value,
                )

            if len(result.trades) > 10:
                trade_table.add_row("...", "...", "...", "...", "...", "...")
                trade_table.add_row(
                    f"({len(result.trades)} total trades)",
                    "", "", "", "", ""
                )

            console.print(trade_table)
        else:
            console.print("[yellow]No trades executed[/yellow]")


async def main():
    """Run all backtests with real Alpaca data."""
    console.print(Panel.fit(
        "[bold]Alpaca Options Bot - Backtesting with Real Data[/bold]\n"
        "Using Alpaca historical options data (Feb 2024+)",
        border_style="blue"
    ))

    # Check for Alpaca credentials
    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if not api_key or not api_secret:
        console.print("[red]Warning: ALPACA_API_KEY and ALPACA_SECRET_KEY not set[/red]")
        console.print("[yellow]Will use synthetic data only[/yellow]")
    else:
        console.print("[green]Alpaca credentials found - will use real options data[/green]")

    # Load configuration
    settings = load_config(project_root / "config" / "default.yaml")

    # Backtest period - from 2021 to present
    # Note: Alpaca only has options data from Feb 2024
    # Earlier periods will use synthetic options data
    start_date = datetime(2021, 1, 1)
    end_date = datetime(2024, 11, 15)

    console.print(f"\n[bold]Backtest Period:[/bold] {start_date.date()} to {end_date.date()}")
    console.print(f"[bold]Alpaca Data Available:[/bold] From {ALPACA_OPTIONS_DATA_START.date()}")
    console.print(f"[bold]Initial Capital:[/bold] ${settings.backtesting.initial_capital:,.2f}")

    results = {}

    # 1. Wheel Strategy on AAPL
    try:
        result = await run_single_backtest(
            "Wheel",
            WheelStrategy,
            "AAPL",
            settings,
            start_date,
            end_date,
        )
        results["Wheel (AAPL)"] = result
    except Exception as e:
        console.print(f"[red]Error in Wheel backtest: {e}[/red]")
        import traceback
        traceback.print_exc()
        results["Wheel (AAPL)"] = None

    # 2. Iron Condor Strategy on SPY
    try:
        result = await run_single_backtest(
            "Iron_Condor",
            IronCondorStrategy,
            "SPY",
            settings,
            start_date,
            end_date,
        )
        results["Iron Condor (SPY)"] = result
    except Exception as e:
        console.print(f"[red]Error in Iron Condor backtest: {e}[/red]")
        import traceback
        traceback.print_exc()
        results["Iron Condor (SPY)"] = None

    # 3. Vertical Spread Strategy on QQQ
    try:
        result = await run_single_backtest(
            "Vertical_Spread",
            VerticalSpreadStrategy,
            "QQQ",
            settings,
            start_date,
            end_date,
        )
        results["Vertical Spread (QQQ)"] = result
    except Exception as e:
        console.print(f"[red]Error in Vertical Spread backtest: {e}[/red]")
        import traceback
        traceback.print_exc()
        results["Vertical Spread (QQQ)"] = None

    # Display comparison
    display_results(results)

    # Save results
    output_dir = project_root / "data" / "backtest_results" / f"alpaca_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, result in results.items():
        if result is not None:
            safe_name = name.replace(" ", "_").replace("(", "").replace(")", "")
            result.save(output_dir / safe_name)

    console.print(f"\n[green]Results saved to: {output_dir}[/green]")


if __name__ == "__main__":
    asyncio.run(main())
