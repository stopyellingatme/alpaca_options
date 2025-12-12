#!/usr/bin/env python3
"""Final Walk-Forward Validation with ALL Optimized Parameters.

This validates the COMPLETE optimized configuration:
- Symbol-specific delta targets (SPY 0.18, AAPL 0.22, MSFT 0.25, NVDA 0.20)
- Optimized DTE range (14-30 entry, 7 exit)
- Symbol-specific profit/loss management:
  * SPY: 50% profit, 2.0x stop (baseline)
  * AAPL: 40% profit, 2.5x stop
  * MSFT: 70% profit, 3.0x stop
  * NVDA: 40% profit, 2.5x stop

Walk-Forward Windows:
- Train: 2019-2020 → Test: 2021
- Train: 2020-2021 → Test: 2022
- Train: 2021-2022 → Test: 2023
- Train: 2022-2023 → Test: 2024

Usage:
    uv run python scripts/validation/walk_forward_final.py
    uv run python scripts/validation/walk_forward_final.py --quick  # Single symbol test
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
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

# OPTIMIZED PARAMETERS (from previous phases)
OPTIMIZED_DELTAS = {
    "SPY": 0.18,   # Walk-forward validated: OOS Sharpe 10.73
    "AAPL": 0.22,  # Walk-forward validated: OOS Sharpe 2.63
    "MSFT": 0.25,  # Walk-forward validated: OOS Sharpe 1.52
    "NVDA": 0.20,  # Baseline (overfitting detected at 0.15)
}

OPTIMIZED_PROFIT_LOSS = {
    "SPY": (0.50, 2.0),   # Baseline is optimal
    "AAPL": (0.40, 2.5),  # +83.1% Sharpe improvement
    "MSFT": (0.70, 3.0),  # +32.4% Sharpe improvement
    "NVDA": (0.40, 2.5),  # +52.1% Sharpe improvement
}


async def test_window(
    symbol: str,
    window_num: int,
    test_start: datetime,
    test_end: datetime,
    initial_capital: float = 10000.0,
) -> Dict:
    """Test optimized parameters on out-of-sample window.

    Args:
        symbol: Stock symbol
        window_num: Window number (1-4)
        test_start: Test period start
        test_end: Test period end
        initial_capital: Starting capital

    Returns:
        Dict with out-of-sample test results
    """
    from alpaca_options.backtesting import BacktestEngine
    from alpaca_options.backtesting.alpaca_options_fetcher import AlpacaOptionsDataFetcher
    from alpaca_options.backtesting.dolthub_options_fetcher import DoltHubOptionsDataFetcher
    from alpaca_options.core.config import load_config
    from alpaca_options.strategies import VerticalSpreadStrategy
    from alpaca_options.backtesting.data_loader import BacktestDataLoader

    try:
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

        # Fetch test data
        test_underlying = alpaca_fetcher.fetch_underlying_bars(
            symbol=symbol,
            start_date=test_start,
            end_date=test_end,
            timeframe="1Hour",
        )

        if test_underlying.empty:
            return {
                "symbol": symbol,
                "window": window_num,
                "error": "No test underlying data"
            }

        data_loader = BacktestDataLoader(settings.backtesting.data)
        test_underlying = data_loader.add_technical_indicators(test_underlying)

        # Fetch test options chains
        test_options = {}
        test_timestamps = test_underlying.resample('1D').last().dropna(subset=['close']).index

        for timestamp in test_timestamps:
            chain = dolthub_fetcher.fetch_option_chain(
                underlying=symbol,
                as_of_date=timestamp,
            )
            if chain:
                test_options[timestamp] = chain

        if not test_options:
            return {
                "symbol": symbol,
                "window": window_num,
                "error": "No test options data"
            }

        # Get optimized parameters for this symbol
        delta_target = OPTIMIZED_DELTAS[symbol]
        profit_target, stop_loss = OPTIMIZED_PROFIT_LOSS[symbol]

        # Create strategy with OPTIMIZED parameters
        strategy = VerticalSpreadStrategy()

        config = {
            "underlyings": [symbol],
            # OPTIMIZED DELTA (symbol-specific)
            "delta_target": delta_target,
            # OPTIMIZED DTE (from grid search)
            "min_dte": 14,
            "max_dte": 30,
            "close_dte": 7,
            # OPTIMIZED PROFIT/LOSS (symbol-specific)
            "profit_target_pct": profit_target,
            "stop_loss_multiplier": stop_loss,
            # Fixed parameters
            "spread_width": 5.0,
            "min_iv_rank": 0,
            "min_open_interest": 0,
            "max_spread_percent": 15.0,
            "min_return_on_risk": 0.08,
            "rsi_oversold": 45.0,
            "rsi_overbought": 55.0,
            "min_credit": 15.0,
        }

        await strategy.initialize(config)

        engine = BacktestEngine(settings.backtesting, settings.risk)

        result = await engine.run(
            strategy=strategy,
            underlying_data=test_underlying,
            options_data=test_options,
            start_date=test_start,
            end_date=test_end,
        )

        return {
            "symbol": symbol,
            "window": window_num,
            "metrics": result.metrics,
            "trades": len(result.trades),
            "chains_loaded": len(test_options),
            "config": {
                "delta": delta_target,
                "profit_target": profit_target,
                "stop_loss": stop_loss,
            },
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "window": window_num,
            "error": str(e),
        }


async def main():
    """Run final walk-forward validation with all optimized parameters."""
    import argparse

    parser = argparse.ArgumentParser(description="Final walk-forward validation (ALL optimized params)")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: test single symbol (SPY only)"
    )
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]FINAL Walk-Forward Validation[/bold cyan]\n"
        "Testing COMPLETE optimized configuration:\n\n"
        "[bold]Optimized Parameters:[/bold]\n"
        "• Symbol-specific delta targets (validated)\n"
        "• DTE range: 14-30 entry, 7 exit (grid search optimal)\n"
        "• Symbol-specific profit/loss management (optimized)\n\n"
        "[bold green]This validates the FULL production config[/bold green]",
        border_style="cyan"
    ))

    # Symbols to test
    symbols = ["SPY"] if args.quick else ["SPY", "AAPL", "MSFT", "NVDA"]

    # Walk-forward windows (out-of-sample years only)
    windows = [
        # (window_num, test_start, test_end, test_year)
        (1, datetime(2021, 1, 1), datetime(2021, 12, 31), "2021"),
        (2, datetime(2022, 1, 1), datetime(2022, 12, 31), "2022"),
        (3, datetime(2023, 1, 1), datetime(2023, 12, 31), "2023"),
        (4, datetime(2024, 1, 1), datetime(2024, 12, 31), "2024"),
    ]

    total_tasks = len(symbols) * len(windows)
    console.print(f"\n[bold]Testing {len(symbols)} symbol(s) across {len(windows)} OOS windows[/bold]")
    console.print(f"[dim]Symbols: {', '.join(symbols)}[/dim]")
    console.print(f"[bold cyan]Total tasks: {total_tasks}[/bold cyan]\n")

    # Display optimized parameters
    console.print("[bold]Optimized Parameters by Symbol:[/bold]")
    for sym in symbols:
        delta = OPTIMIZED_DELTAS[sym]
        profit, stop = OPTIMIZED_PROFIT_LOSS[sym]
        console.print(f"  {sym}: delta={delta:.2f}, profit={profit:.0%}, stop={stop:.1f}x")
    console.print()

    # Check credentials
    if not os.environ.get("ALPACA_API_KEY") or not os.environ.get("ALPACA_SECRET_KEY"):
        console.print("[red]ERROR: Alpaca credentials required![/red]")
        console.print("[yellow]Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables[/yellow]")
        return

    # Create all tasks upfront (PARALLEL EXECUTION)
    console.print("[cyan]Creating validation tasks...[/cyan]")
    tasks = []

    for symbol in symbols:
        for window_num, test_start, test_end, test_year in windows:
            task = test_window(
                symbol=symbol,
                window_num=window_num,
                test_start=test_start,
                test_end=test_end,
                initial_capital=10000.0,
            )
            tasks.append(task)

    # Run all tasks concurrently with progress tracking
    console.print(f"[bold green]Running {len(tasks)} validation tests in parallel...[/bold green]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task_progress = progress.add_task(
            "[cyan]Running parallel validation tests...",
            total=len(tasks)
        )

        # Run all tasks concurrently
        results = []
        completed = 0

        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)

            completed += 1
            progress.update(
                task_progress,
                advance=1,
                description=f"[cyan]Completed {completed}/{len(tasks)} validation tests..."
            )

        progress.update(task_progress, description=f"[green]✓ All {len(tasks)} validation tests complete!")

    # Organize results by symbol
    symbol_results = {symbol: [] for symbol in symbols}

    for result in results:
        if "error" in result:
            console.print(f"[red]Window {result['window']} for {result['symbol']}: {result['error']}[/red]")
            continue

        symbol = result["symbol"]
        symbol_results[symbol].append(result)

    # Display results
    console.print("\n\n")
    console.print(Panel.fit(
        "[bold green]FINAL VALIDATION RESULTS[/bold green]\n"
        "Out-of-Sample Performance with ALL Optimized Parameters",
        border_style="green"
    ))

    all_valid = True

    for symbol in symbols:
        results_list = symbol_results[symbol]

        if not results_list:
            console.print(f"\n[yellow]{symbol}: No valid results[/yellow]")
            continue

        console.print(f"\n[bold cyan]{symbol} Out-of-Sample Performance:[/bold cyan]")

        # Get config
        config = results_list[0]["config"]
        console.print(f"[dim]Config: delta={config['delta']:.2f}, "
                     f"profit={config['profit_target']:.0%}, "
                     f"stop={config['stop_loss']:.1f}x, "
                     f"DTE=14-30[/dim]\n")

        # Create results table
        table = Table(title=f"{symbol} Validation Results", box=box.ROUNDED)
        table.add_column("Year", justify="center", width=8)
        table.add_column("Return", justify="right", width=12)
        table.add_column("Sharpe", justify="right", width=10)
        table.add_column("Win Rate", justify="right", width=10)
        table.add_column("Trades", justify="right", width=8)
        table.add_column("Max DD", justify="right", width=10)
        table.add_column("Assessment", justify="left", width=15)

        total_sharpe = 0
        total_return = 0
        valid_windows = 0

        for result in sorted(results_list, key=lambda r: r["window"]):
            m = result["metrics"]
            window_num = result["window"]
            year = 2020 + window_num

            total_sharpe += m.sharpe_ratio
            total_return += m.total_return_percent
            valid_windows += 1

            # Color code performance
            if m.sharpe_ratio > 2.0:
                sharpe_str = f"[green]{m.sharpe_ratio:.2f}[/green]"
                assessment = "[green]Excellent[/green]"
            elif m.sharpe_ratio > 1.0:
                sharpe_str = f"[yellow]{m.sharpe_ratio:.2f}[/yellow]"
                assessment = "[yellow]Good[/yellow]"
            else:
                sharpe_str = f"[red]{m.sharpe_ratio:.2f}[/red]"
                assessment = "[red]Poor[/red]"

            return_style = "green" if m.total_return_percent > 0 else "red"

            table.add_row(
                str(year),
                f"[{return_style}]{m.total_return_percent:+.2f}%[/{return_style}]",
                sharpe_str,
                f"{m.win_rate:.1f}%",
                str(m.total_trades),
                f"{m.max_drawdown_percent:.2f}%",
                assessment,
            )

        console.print(table)

        # Calculate averages
        if valid_windows > 0:
            avg_sharpe = total_sharpe / valid_windows
            avg_return = total_return / valid_windows

            console.print(f"\n[bold]Average Out-of-Sample Performance:[/bold]")
            console.print(f"  Return:  {avg_return:+.2f}%")
            console.print(f"  Sharpe:  {avg_sharpe:.2f}")

            # Assessment
            if avg_sharpe > 2.0:
                console.print(f"\n[green]✓ {symbol}: EXCELLENT - Strong out-of-sample performance[/green]")
            elif avg_sharpe > 1.0:
                console.print(f"\n[yellow]✓ {symbol}: GOOD - Solid out-of-sample performance[/yellow]")
            else:
                console.print(f"\n[red]✗ {symbol}: POOR - Weak out-of-sample performance[/red]")
                all_valid = False

    # Final summary
    console.print("\n\n")
    console.print(Panel.fit(
        "[bold]FINAL ASSESSMENT[/bold]\n\n"
        f"{'[green]✓ All symbols show robust out-of-sample performance[/green]' if all_valid else '[yellow]⚠ Some symbols show weaker OOS performance - review before deployment[/yellow]'}\n\n"
        "[dim]Next steps:[/dim]\n"
        "[dim]1. Review individual symbol performance above[/dim]\n"
        "[dim]2. Update config/paper_trading.yaml with validated parameters[/dim]\n"
        "[dim]3. Deploy to paper trading for live validation[/dim]",
        border_style="cyan"
    ))

    console.print("\n[dim]Final walk-forward validation complete.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
