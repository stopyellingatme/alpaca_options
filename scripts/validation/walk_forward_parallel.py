#!/usr/bin/env python3
"""Parallelized Walk-Forward Validation for Vertical Spread Strategy.

This version runs ALL symbol/window combinations concurrently for maximum speedup.

Performance Improvement:
- Sequential: Each symbol processes 4 windows sequentially (~6-8 hours per symbol)
- Parallel: All symbol/window combinations run concurrently (~2-3 hours total)

Walk-Forward Windows:
- Train: 2019-2020 → Test: 2021
- Train: 2020-2021 → Test: 2022
- Train: 2021-2022 → Test: 2023
- Train: 2022-2023 → Test: 2024

Usage:
    uv run python scripts/validation/walk_forward_parallel.py
    uv run python scripts/validation/walk_forward_parallel.py --quick  # Single symbol test
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

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


async def optimize_and_test_window(
    symbol: str,
    window_num: int,
    train_start: datetime,
    train_end: datetime,
    test_start: datetime,
    test_end: datetime,
    initial_capital: float = 10000.0,
) -> Dict:
    """Optimize on training data and test on out-of-sample data for one window.

    Args:
        symbol: Stock symbol
        window_num: Window number (1-4)
        train_start: Training period start
        train_end: Training period end
        test_start: Test period start
        test_end: Test period end
        initial_capital: Starting capital

    Returns:
        Dict with in-sample and out-of-sample results
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

        # Parameter grid (reduced for speed)
        delta_values = [0.20, 0.25, 0.30]
        dte_configs = [
            (14, 30, 7),   # Current optimized
            (21, 45, 14),  # Baseline
        ]

        # PHASE 1: Optimize on training data
        # Fetch training data
        train_underlying = alpaca_fetcher.fetch_underlying_bars(
            symbol=symbol,
            start_date=train_start,
            end_date=train_end,
            timeframe="1Hour",
        )

        if train_underlying.empty:
            return {
                "symbol": symbol,
                "window": window_num,
                "error": "No training underlying data"
            }

        data_loader = BacktestDataLoader(settings.backtesting.data)
        train_underlying = data_loader.add_technical_indicators(train_underlying)

        # Fetch training options chains
        train_options = {}
        daily_timestamps = train_underlying.resample('1D').last().dropna(subset=['close']).index

        for timestamp in daily_timestamps:
            chain = dolthub_fetcher.fetch_option_chain(
                underlying=symbol,
                as_of_date=timestamp,
            )
            if chain:
                train_options[timestamp] = chain

        if not train_options:
            return {
                "symbol": symbol,
                "window": window_num,
                "error": "No training options data"
            }

        # Test all parameter combinations to find best
        best_sharpe = -999
        best_params = (0.25, 14, 30, 7)

        for delta in delta_values:
            for min_dte, max_dte, close_dte in dte_configs:
                strategy = VerticalSpreadStrategy()

                config = {
                    "underlyings": [symbol],
                    "delta_target": delta,
                    "min_dte": min_dte,
                    "max_dte": max_dte,
                    "close_dte": close_dte,
                    "spread_width": 5.0,
                    "min_iv_rank": 0,
                    "min_open_interest": 0,
                    "max_spread_percent": 15.0,
                    "min_return_on_risk": 0.08,
                    "rsi_oversold": 45.0,
                    "rsi_overbought": 55.0,
                    "min_credit": 15.0,
                    "profit_target_pct": 0.50,
                    "stop_loss_multiplier": 2.0,
                }

                await strategy.initialize(config)

                engine = BacktestEngine(settings.backtesting, settings.risk)

                result = await engine.run(
                    strategy=strategy,
                    underlying_data=train_underlying,
                    options_data=train_options,
                    start_date=train_start,
                    end_date=train_end,
                )

                if result.metrics.sharpe_ratio > best_sharpe:
                    best_sharpe = result.metrics.sharpe_ratio
                    best_params = (delta, min_dte, max_dte, close_dte)

        best_delta, best_min_dte, best_max_dte, best_close_dte = best_params

        # PHASE 2: Test optimized parameters on in-sample (training) data
        strategy_in = VerticalSpreadStrategy()
        config_in = {
            "underlyings": [symbol],
            "delta_target": best_delta,
            "min_dte": best_min_dte,
            "max_dte": best_max_dte,
            "close_dte": best_close_dte,
            "spread_width": 5.0,
            "min_iv_rank": 0,
            "min_open_interest": 0,
            "max_spread_percent": 15.0,
            "min_return_on_risk": 0.08,
            "rsi_oversold": 45.0,
            "rsi_overbought": 55.0,
            "min_credit": 15.0,
            "profit_target_pct": 0.50,
            "stop_loss_multiplier": 2.0,
        }

        await strategy_in.initialize(config_in)

        engine_in = BacktestEngine(settings.backtesting, settings.risk)

        result_in = await engine_in.run(
            strategy=strategy_in,
            underlying_data=train_underlying,
            options_data=train_options,
            start_date=train_start,
            end_date=train_end,
        )

        # PHASE 3: Test optimized parameters on out-of-sample (test) data
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
                "in_sample": {
                    "metrics": result_in.metrics,
                    "trades": len(result_in.trades),
                    "delta": best_delta,
                    "min_dte": best_min_dte,
                    "max_dte": best_max_dte,
                    "close_dte": best_close_dte,
                },
                "out_of_sample": {"error": "No test underlying data"},
            }

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
                "in_sample": {
                    "metrics": result_in.metrics,
                    "trades": len(result_in.trades),
                    "delta": best_delta,
                    "min_dte": best_min_dte,
                    "max_dte": best_max_dte,
                    "close_dte": best_close_dte,
                },
                "out_of_sample": {"error": "No test options data"},
            }

        strategy_out = VerticalSpreadStrategy()
        await strategy_out.initialize(config_in)  # Use same config as in-sample

        engine_out = BacktestEngine(settings.backtesting, settings.risk)

        result_out = await engine_out.run(
            strategy=strategy_out,
            underlying_data=test_underlying,
            options_data=test_options,
            start_date=test_start,
            end_date=test_end,
        )

        return {
            "symbol": symbol,
            "window": window_num,
            "in_sample": {
                "metrics": result_in.metrics,
                "trades": len(result_in.trades),
                "delta": best_delta,
                "min_dte": best_min_dte,
                "max_dte": best_max_dte,
                "close_dte": best_close_dte,
            },
            "out_of_sample": {
                "metrics": result_out.metrics,
                "trades": len(result_out.trades),
            },
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "window": window_num,
            "error": str(e),
        }


async def main():
    """Run walk-forward validation with parallel execution."""
    import argparse

    parser = argparse.ArgumentParser(description="Walk-forward validation (PARALLEL)")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: test single symbol (SPY only)"
    )
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]Walk-Forward Validation (PARALLEL)[/bold cyan]\n"
        "Out-of-Sample Performance Testing\n\n"
        "Method:\n"
        "1. Train on 2 years → Optimize parameters\n"
        "2. Test on 1 year → Apply optimized parameters\n"
        "3. Repeat with rolling windows\n"
        "4. Report average out-of-sample performance\n\n"
        "[bold green]Parallelization: Running ALL symbol/window combinations concurrently[/bold green]",
        border_style="cyan"
    ))

    # Symbols to test
    symbols = ["SPY"] if args.quick else ["SPY", "AAPL", "MSFT", "NVDA"]

    # Walk-forward windows
    windows = [
        # (window_num, train_start, train_end, test_start, test_end)
        (1, datetime(2019, 2, 9), datetime(2020, 12, 31), datetime(2021, 1, 1), datetime(2021, 12, 31)),
        (2, datetime(2020, 1, 1), datetime(2021, 12, 31), datetime(2022, 1, 1), datetime(2022, 12, 31)),
        (3, datetime(2021, 1, 1), datetime(2022, 12, 31), datetime(2023, 1, 1), datetime(2023, 12, 31)),
        (4, datetime(2022, 1, 1), datetime(2023, 12, 31), datetime(2024, 1, 1), datetime(2024, 12, 31)),
    ]

    total_tasks = len(symbols) * len(windows)
    console.print(f"\n[bold]Testing {len(symbols)} symbol(s) across {len(windows)} windows[/bold]")
    console.print(f"[dim]Symbols: {', '.join(symbols)}[/dim]")
    console.print(f"[bold cyan]Total tasks: {total_tasks}[/bold cyan]\n")

    # Check credentials
    if not os.environ.get("ALPACA_API_KEY") or not os.environ.get("ALPACA_SECRET_KEY"):
        console.print("[red]ERROR: Alpaca credentials required![/red]")
        console.print("[yellow]Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables[/yellow]")
        return

    # Create all tasks upfront (PARALLEL EXECUTION)
    console.print("[cyan]Creating walk-forward tasks...[/cyan]")
    tasks = []

    for symbol in symbols:
        for window_num, train_start, train_end, test_start, test_end in windows:
            task = optimize_and_test_window(
                symbol=symbol,
                window_num=window_num,
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                initial_capital=10000.0,
            )
            tasks.append(task)

    # Run all tasks concurrently with progress tracking
    console.print(f"[bold green]Running {len(tasks)} window tests in parallel...[/bold green]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task_progress = progress.add_task(
            "[cyan]Running parallel window tests...",
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
                description=f"[cyan]Completed {completed}/{len(tasks)} window tests..."
            )

        progress.update(task_progress, description=f"[green]✓ All {len(tasks)} window tests complete!")

    # Organize results by symbol
    symbol_results = {symbol: {"in_sample": [], "out_of_sample": []} for symbol in symbols}

    for result in results:
        if "error" in result and "in_sample" not in result:
            # Complete failure
            console.print(f"[red]Window {result['window']} for {result['symbol']}: {result['error']}[/red]")
            continue

        symbol = result["symbol"]

        if "in_sample" in result:
            symbol_results[symbol]["in_sample"].append(result["in_sample"])

        if "out_of_sample" in result and "error" not in result["out_of_sample"]:
            symbol_results[symbol]["out_of_sample"].append(result["out_of_sample"])

    # Display results
    console.print("\n\n")
    console.print(Panel.fit(
        "[bold green]WALK-FORWARD VALIDATION RESULTS[/bold green]",
        border_style="green"
    ))

    for symbol in symbols:
        in_sample_results = symbol_results[symbol]["in_sample"]
        out_of_sample_results = symbol_results[symbol]["out_of_sample"]

        if not in_sample_results or not out_of_sample_results:
            console.print(f"\n[yellow]{symbol}: Insufficient data for validation[/yellow]")
            continue

        console.print(f"\n[bold cyan]{symbol} Walk-Forward Results:[/bold cyan]\n")

        # Create summary table
        table = Table(title=f"{symbol} Out-of-Sample Performance", box=box.ROUNDED)
        table.add_column("Window", justify="center", width=10)
        table.add_column("In-Sample", justify="right", width=15)
        table.add_column("Out-of-Sample", justify="right", width=15)
        table.add_column("Efficiency", justify="right", width=12)
        table.add_column("Assessment", justify="left", width=20)

        total_efficiency = 0
        valid_windows = 0

        for i, (in_res, out_res) in enumerate(zip(in_sample_results, out_of_sample_results), 1):
            in_return = in_res["metrics"].total_return_percent
            out_return = out_res["metrics"].total_return_percent

            efficiency = (out_return / in_return * 100) if in_return != 0 else 0
            total_efficiency += efficiency
            valid_windows += 1

            # Color code efficiency
            if efficiency > 80:
                efficiency_str = f"[green]{efficiency:.1f}%[/green]"
                assessment = "[green]Excellent[/green]"
            elif efficiency > 60:
                efficiency_str = f"[yellow]{efficiency:.1f}%[/yellow]"
                assessment = "[yellow]Good[/yellow]"
            else:
                efficiency_str = f"[red]{efficiency:.1f}%[/red]"
                assessment = "[red]Poor[/red]"

            table.add_row(
                f"Window {i}",
                f"{in_return:+.2f}%",
                f"{out_return:+.2f}%",
                efficiency_str,
                assessment,
            )

        console.print(table)

        # Calculate averages
        if valid_windows > 0:
            avg_efficiency = total_efficiency / valid_windows

            avg_in_return = sum(r["metrics"].total_return_percent for r in in_sample_results) / len(in_sample_results)
            avg_out_return = sum(r["metrics"].total_return_percent for r in out_of_sample_results) / len(out_of_sample_results)

            console.print(f"\n[bold]Average Performance:[/bold]")
            console.print(f"  In-Sample:     {avg_in_return:+.2f}%")
            console.print(f"  Out-of-Sample: {avg_out_return:+.2f}%")
            console.print(f"  Efficiency:    {avg_efficiency:.1f}%")

            if avg_efficiency > 80:
                console.print(f"\n[green]✓ {symbol}: Strategy is ROBUST - holds up well out-of-sample[/green]")
            elif avg_efficiency > 60:
                console.print(f"\n[yellow]⚠ {symbol}: Strategy is DECENT - some degradation expected[/yellow]")
            else:
                console.print(f"\n[red]✗ {symbol}: Strategy may be OVERFIT - poor out-of-sample performance[/red]")

    console.print("\n[dim]Walk-forward validation complete.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
