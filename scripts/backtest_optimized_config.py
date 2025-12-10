#!/usr/bin/env python3
"""Comprehensive Backtest of Optimized Configuration.

This script validates the optimized parameters by running a full backtest
across all configured symbols using the actual paper_trading.yaml config.

Tests:
- Symbol-specific delta targets (AGGRESSIVE approach)
- Optimized DTE parameters (14-30 entry, 7 exit)
- All 4 symbols: SPY, AAPL, MSFT, NVDA
- 6-year period: 2019-2024

Usage:
    uv run python scripts/backtest_optimized_config.py
    uv run python scripts/backtest_optimized_config.py --quick  # 2023-2024 only
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich import box

console = Console()

# Set INFO level for cleaner output
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)-8s [%(name)s] %(message)s',
)


async def run_symbol_backtest(
    symbol: str,
    start_dt: datetime,
    end_dt: datetime,
    initial_capital: float,
    config: dict,
) -> Dict:
    """Run backtest for a single symbol using optimized config.

    Args:
        symbol: Stock symbol to test
        start_dt: Start date
        end_dt: End date
        initial_capital: Starting capital
        config: Strategy configuration dict

    Returns:
        Dict with results and metrics
    """
    from alpaca_options.backtesting import BacktestEngine
    from alpaca_options.backtesting.alpaca_options_fetcher import AlpacaOptionsDataFetcher
    from alpaca_options.backtesting.dolthub_options_fetcher import DoltHubOptionsDataFetcher
    from alpaca_options.core.config import load_config
    from alpaca_options.strategies import VerticalSpreadStrategy

    # Load configuration
    settings = load_config(project_root / "config" / "paper_trading.yaml")
    settings.backtesting.initial_capital = initial_capital

    # Initialize fetchers
    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    alpaca_fetcher = AlpacaOptionsDataFetcher(
        api_key=api_key,
        api_secret=api_secret,
    )

    dolthub_fetcher = DoltHubOptionsDataFetcher()

    # Fetch underlying data from Alpaca
    underlying_data = alpaca_fetcher.fetch_underlying_bars(
        symbol=symbol,
        start_date=start_dt,
        end_date=end_dt,
        timeframe="1Hour",
    )

    if underlying_data.empty:
        return {
            "symbol": symbol,
            "error": "No underlying data"
        }

    # Add technical indicators
    from alpaca_options.backtesting.data_loader import BacktestDataLoader
    data_loader = BacktestDataLoader(settings.backtesting.data)
    underlying_data = data_loader.add_technical_indicators(underlying_data)

    # Fetch options chains from DoltHub
    options_data = {}
    daily_timestamps = underlying_data.resample('1D').last().dropna(subset=['close']).index

    for timestamp in daily_timestamps:
        chain = dolthub_fetcher.fetch_option_chain(
            underlying=symbol,
            as_of_date=timestamp,
        )
        if chain:
            options_data[timestamp] = chain

    if not options_data:
        return {
            "symbol": symbol,
            "error": "No options data"
        }

    # Create strategy instance
    strategy = VerticalSpreadStrategy()

    # Initialize strategy with OPTIMIZED CONFIG
    await strategy.initialize(config)

    # Log which delta is being used
    delta_used = strategy._get_delta_for_symbol(symbol)
    console.print(f"[dim]  {symbol}: Using delta {delta_used:.2f}[/dim]")

    # Create backtest engine
    engine = BacktestEngine(settings.backtesting, settings.risk)

    # Run backtest
    result = await engine.run(
        strategy=strategy,
        underlying_data=underlying_data,
        options_data=options_data,
        start_date=start_dt,
        end_date=end_dt,
    )

    m = result.metrics

    return {
        "symbol": symbol,
        "metrics": m,
        "trades": result.trades,
        "chains_loaded": len(options_data),
        "delta_used": delta_used,
    }


async def main():
    """Run comprehensive backtest validation."""
    import argparse

    parser = argparse.ArgumentParser(description="Backtest optimized configuration")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use 2023-2024 only for faster testing"
    )
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]Optimized Configuration Backtest[/bold cyan]\n"
        "Validating Phase 1 Optimization Results\n"
        "Symbol-specific deltas + Optimized DTE (14-30 entry, 7 exit)",
        border_style="cyan"
    ))

    # Parameters
    symbols = ["SPY", "AAPL", "MSFT", "NVDA"]

    if args.quick:
        start_dt = datetime(2023, 1, 1)
        end_dt = datetime(2024, 12, 31)
        console.print("[yellow]Quick mode: Testing 2023-2024 only (2 years)[/yellow]\n")
    else:
        start_dt = datetime(2019, 2, 9)
        end_dt = datetime(2024, 12, 31)
        console.print("[dim]Full mode: Testing 2019-2024 (~6 years)[/dim]\n")

    initial_capital = 10000.0

    console.print(f"[dim]Symbols: {', '.join(symbols)}[/dim]")
    console.print(f"[dim]Period: {start_dt.date()} to {end_dt.date()}[/dim]")
    console.print(f"[dim]Initial Capital: ${initial_capital:,.2f}[/dim]\n")

    # Check credentials
    if not os.environ.get("ALPACA_API_KEY") or not os.environ.get("ALPACA_SECRET_KEY"):
        console.print("[red]ERROR: Alpaca credentials required![/red]")
        console.print("[yellow]Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables[/yellow]")
        return

    # Load configuration
    from alpaca_options.core.config import load_config
    settings = load_config(project_root / "config" / "paper_trading.yaml")

    vertical_config = settings.strategies.get("vertical_spread")
    if not vertical_config:
        console.print("[red]ERROR: Vertical spread strategy not found in configuration[/red]")
        return

    # Display configuration being tested
    console.print("[bold]Configuration:[/bold]")
    console.print(f"  DTE Entry: {vertical_config.config['min_dte']}-{vertical_config.config['max_dte']}")
    console.print(f"  DTE Exit: {vertical_config.config['close_dte']}")

    symbol_configs = vertical_config.config.get("symbol_configs", {})
    if symbol_configs:
        console.print("\n[bold]Symbol-Specific Deltas:[/bold]")
        for sym in symbols:
            delta = symbol_configs.get(sym, {}).get("delta_target", "N/A")
            console.print(f"  {sym}: {delta:.2f}" if isinstance(delta, float) else f"  {sym}: {delta}")

    console.print("\n")

    # Run backtests
    all_results = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "[cyan]Running backtests...",
            total=len(symbols)
        )

        for symbol in symbols:
            progress.update(
                task,
                description=f"[cyan]Running backtest for {symbol}..."
            )

            try:
                result = await run_symbol_backtest(
                    symbol=symbol,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    initial_capital=initial_capital,
                    config=vertical_config.config,
                )
                all_results[symbol] = result
            except Exception as e:
                console.print(f"\n[red]Error testing {symbol}: {e}[/red]")
                import traceback
                traceback.print_exc()
                all_results[symbol] = {
                    "symbol": symbol,
                    "error": str(e)
                }

            progress.update(task, advance=1)

        progress.update(task, description="[green]✓ All backtests complete")

    # Display results
    console.print("\n\n")
    console.print(Panel.fit(
        "[bold green]BACKTEST RESULTS[/bold green]",
        border_style="green"
    ))

    # Individual symbol results
    console.print("\n[bold cyan]Individual Symbol Performance:[/bold cyan]\n")

    # Calculate years for annualized returns
    years = (end_dt - start_dt).days / 365.25

    results_table = Table(title="Symbol Performance Summary", box=box.ROUNDED)
    results_table.add_column("Symbol", style="cyan", width=8)
    results_table.add_column("Delta", justify="right", width=8)
    results_table.add_column("Total Return", justify="right", width=12)
    results_table.add_column("Annualized", justify="right", width=12)
    results_table.add_column("Sharpe", justify="right", width=8)
    results_table.add_column("Win Rate", justify="right", width=10)
    results_table.add_column("Trades", justify="right", width=8)
    results_table.add_column("Max DD", justify="right", width=10)

    valid_results = []
    for symbol in symbols:
        result = all_results.get(symbol, {})

        if "error" in result:
            results_table.add_row(
                symbol,
                "[red]ERROR[/red]",
                "[red]ERROR[/red]",
                "[red]ERROR[/red]",
                "[red]ERROR[/red]",
                "[red]ERROR[/red]",
                "[red]ERROR[/red]",
                "[red]ERROR[/red]",
            )
        else:
            m = result["metrics"]
            delta_used = result.get("delta_used", 0.20)

            # Calculate annualized return
            total_return_decimal = m.total_return_percent / 100.0
            annualized_return = (((1 + total_return_decimal) ** (1 / years)) - 1) * 100

            return_style = "green" if m.total_return_percent > 0 else "red"

            results_table.add_row(
                symbol,
                f"{delta_used:.2f}",
                f"[{return_style}]{m.total_return_percent:+.2f}%[/{return_style}]",
                f"[{return_style}]{annualized_return:+.2f}%[/{return_style}]",
                f"{m.sharpe_ratio:.2f}",
                f"{m.win_rate:.1f}%",
                str(m.total_trades),
                f"{m.max_drawdown_percent:.2f}%",
            )

            valid_results.append(result)

    console.print(results_table)

    # Aggregate statistics
    if valid_results:
        console.print("\n[bold cyan]Portfolio Aggregate:[/bold cyan]\n")

        total_trades = sum(r["metrics"].total_trades for r in valid_results)
        avg_return = sum(r["metrics"].total_return_percent for r in valid_results) / len(valid_results)
        avg_sharpe = sum(r["metrics"].sharpe_ratio for r in valid_results) / len(valid_results)
        avg_win_rate = sum(r["metrics"].win_rate for r in valid_results) / len(valid_results)
        avg_max_dd = sum(r["metrics"].max_drawdown_percent for r in valid_results) / len(valid_results)

        # Calculate average annualized return
        avg_annualized = (((1 + avg_return/100) ** (1/years)) - 1) * 100

        agg_table = Table(show_header=False, box=box.SIMPLE)
        agg_table.add_column("Metric", style="cyan")
        agg_table.add_column("Value", style="white")

        agg_table.add_row("Total Trades", f"{total_trades}")
        agg_table.add_row("Average Total Return", f"{avg_return:+.2f}%")
        agg_table.add_row("Average Annualized Return", f"{avg_annualized:+.2f}%")
        agg_table.add_row("Average Sharpe Ratio", f"{avg_sharpe:.2f}")
        agg_table.add_row("Average Win Rate", f"{avg_win_rate:.1f}%")
        agg_table.add_row("Average Max Drawdown", f"{avg_max_dd:.2f}%")

        console.print(agg_table)

        # Best performers
        console.print("\n[bold cyan]Top Performers:[/bold cyan]\n")

        best_return = max(valid_results, key=lambda r: r["metrics"].total_return_percent)
        best_sharpe = max(valid_results, key=lambda r: r["metrics"].sharpe_ratio)
        best_winrate = max(valid_results, key=lambda r: r["metrics"].win_rate)

        console.print(f"  [green]Best Return:[/green] {best_return['symbol']} "
                     f"({best_return['metrics'].total_return_percent:+.2f}%)")
        console.print(f"  [green]Best Sharpe:[/green] {best_sharpe['symbol']} "
                     f"({best_sharpe['metrics'].sharpe_ratio:.2f})")
        console.print(f"  [green]Best Win Rate:[/green] {best_winrate['symbol']} "
                     f"({best_winrate['metrics'].win_rate:.1f}%)")

        # Expected vs Actual
        console.print("\n[bold cyan]Validation vs Expected Results:[/bold cyan]\n")

        expected = {
            "SPY": {"return": 373.08, "sharpe": 8.45, "win_rate": 100.0},
            "AAPL": {"return": 186.84, "sharpe": 2.99, "win_rate": 78.5},
            "MSFT": {"return": 178.89, "sharpe": 3.04, "win_rate": 77.5},
            "NVDA": {"return": 163.93, "sharpe": 1.73, "win_rate": 75.0},
        }

        validation_table = Table(title="Expected vs Actual", box=box.ROUNDED)
        validation_table.add_column("Symbol", style="cyan", width=8)
        validation_table.add_column("Metric", style="white", width=12)
        validation_table.add_column("Expected", justify="right", width=12)
        validation_table.add_column("Actual", justify="right", width=12)
        validation_table.add_column("Diff", justify="right", width=12)

        for symbol in symbols:
            result = all_results.get(symbol, {})
            if "error" not in result and symbol in expected:
                m = result["metrics"]
                exp = expected[symbol]

                # Return comparison
                return_diff = m.total_return_percent - exp["return"]
                return_diff_style = "green" if abs(return_diff) < 20 else "yellow"
                validation_table.add_row(
                    symbol,
                    "Return",
                    f"{exp['return']:+.2f}%",
                    f"{m.total_return_percent:+.2f}%",
                    f"[{return_diff_style}]{return_diff:+.2f}%[/{return_diff_style}]"
                )

                # Sharpe comparison
                sharpe_diff = m.sharpe_ratio - exp["sharpe"]
                sharpe_diff_style = "green" if abs(sharpe_diff) < 0.5 else "yellow"
                validation_table.add_row(
                    "",
                    "Sharpe",
                    f"{exp['sharpe']:.2f}",
                    f"{m.sharpe_ratio:.2f}",
                    f"[{sharpe_diff_style}]{sharpe_diff:+.2f}[/{sharpe_diff_style}]"
                )

                # Win rate comparison
                wr_diff = m.win_rate - exp["win_rate"]
                wr_diff_style = "green" if abs(wr_diff) < 5 else "yellow"
                validation_table.add_row(
                    "",
                    "Win Rate",
                    f"{exp['win_rate']:.1f}%",
                    f"{m.win_rate:.1f}%",
                    f"[{wr_diff_style}]{wr_diff:+.1f}%[/{wr_diff_style}]"
                )

                validation_table.add_row("", "", "", "", "")  # Separator

        console.print(validation_table)

    # Summary
    console.print("\n" + "="*60)
    console.print(Panel.fit(
        "[bold green]✓ BACKTEST VALIDATION COMPLETE[/bold green]\n\n"
        "Configuration tested successfully:\n"
        f"• {len(valid_results)}/{len(symbols)} symbols validated\n"
        f"• Total trades: {total_trades if valid_results else 0}\n"
        f"• Backtest period: {years:.1f} years ({start_dt.year}-{end_dt.year})\n"
        f"• Average total return: {avg_return:+.2f}%\n"
        f"• Average annualized return: {avg_annualized:+.2f}%\n"
        f"• Average Sharpe: {avg_sharpe:.2f}\n"
        f"• Average win rate: {avg_win_rate:.1f}%",
        border_style="green"
    ))

    console.print("\n[dim]Backtest complete.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
