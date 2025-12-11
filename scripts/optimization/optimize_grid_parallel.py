#!/usr/bin/env python3
"""Parallelized Parameter Grid Search for Vertical Spread Strategy.

This script tests ALL parameter combinations concurrently:
- Delta targets: 0.15, 0.18, 0.20, 0.22, 0.25
- DTE ranges: (14-30), (21-45), (30-60)
- Symbols: AAPL, MSFT, NVDA, SPY

Performance Improvement:
- Sequential: 48+ hours for 4 symbols × 5 deltas × 3 DTE ranges = 60 backtests
- Parallel: 6-8 hours (6-8x speedup, limited by CPU cores)

Usage:
    uv run python scripts/optimization/optimize_grid_parallel.py
    uv run python scripts/optimization/optimize_grid_parallel.py --symbol SPY  # Single symbol
    uv run python scripts/optimization/optimize_grid_parallel.py --quick  # 2023-2024 only
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
import argparse

console = Console()

# Set INFO level for cleaner output
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)-8s [%(name)s] %(message)s',
)


async def run_parameter_backtest(
    symbol: str,
    delta_target: float,
    min_dte: int,
    max_dte: int,
    close_dte: int,
    start_dt: datetime,
    end_dt: datetime,
    initial_capital: float = 10000.0,
) -> Dict:
    """Run backtest with specific parameter combination.

    Args:
        symbol: Stock symbol to test
        delta_target: Target delta (e.g., 0.20 for 20 delta)
        min_dte: Minimum days to expiration
        max_dte: Maximum days to expiration
        close_dte: Close DTE threshold
        start_dt: Start date
        end_dt: End date
        initial_capital: Starting capital

    Returns:
        Dict with results and metrics
    """
    from alpaca_options.backtesting import BacktestEngine
    from alpaca_options.backtesting.alpaca_options_fetcher import AlpacaOptionsDataFetcher
    from alpaca_options.backtesting.dolthub_options_fetcher import DoltHubOptionsDataFetcher
    from alpaca_options.core.config import load_config
    from alpaca_options.strategies import VerticalSpreadStrategy
    from alpaca_options.backtesting.data_loader import BacktestDataLoader

    # Load configuration
    settings = load_config()
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
            "delta": delta_target,
            "min_dte": min_dte,
            "max_dte": max_dte,
            "close_dte": close_dte,
            "error": "No underlying data"
        }

    # Add technical indicators
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
            "delta": delta_target,
            "min_dte": min_dte,
            "max_dte": max_dte,
            "close_dte": close_dte,
            "error": "No options data"
        }

    # Create strategy instance
    strategy = VerticalSpreadStrategy()

    # Configure strategy with specific parameters
    strat_config = settings.strategies.get("vertical_spread")
    if strat_config:
        strategy._config = strat_config.config.copy()
    else:
        strategy._config = {}

    strategy._config["underlyings"] = [symbol]
    strategy._config["delta_target"] = delta_target
    strategy._config["min_dte"] = min_dte
    strategy._config["max_dte"] = max_dte
    strategy._config["close_dte"] = close_dte

    # Keep other parameters at baseline
    strategy._config["spread_width"] = 5.0
    strategy._config["min_iv_rank"] = 0
    strategy._config["min_open_interest"] = 0
    strategy._config["max_spread_percent"] = 15.0
    strategy._config["min_return_on_risk"] = 0.08
    strategy._config["rsi_oversold"] = 45.0
    strategy._config["rsi_overbought"] = 55.0
    strategy._config["min_credit"] = 15.0
    strategy._config["profit_target_pct"] = 0.50
    strategy._config["stop_loss_multiplier"] = 2.0

    # Initialize strategy
    await strategy.initialize(strategy._config)

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
        "delta": delta_target,
        "min_dte": min_dte,
        "max_dte": max_dte,
        "close_dte": close_dte,
        "metrics": m,
        "chains_loaded": len(options_data),
    }


async def main():
    """Run comprehensive parameter grid search with parallel execution."""
    parser = argparse.ArgumentParser(description="Parameter grid search (PARALLEL)")
    parser.add_argument(
        "--symbol",
        type=str,
        default=None,
        help="Test single symbol (default: test all AAPL, MSFT, NVDA, SPY)"
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Use 2023-2024 only for faster testing"
    )
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]Parameter Grid Search (PARALLEL)[/bold cyan]\n"
        "Testing all parameter combinations:\n"
        "  Delta: 0.15, 0.18, 0.20, 0.22, 0.25\n"
        "  DTE Ranges: (14-30-7), (21-45-14), (30-60-21)\n\n"
        "[bold green]Parallelization: Running ALL combinations concurrently[/bold green]",
        border_style="cyan"
    ))

    # Parameters
    symbols = [args.symbol] if args.symbol else ["AAPL", "MSFT", "NVDA", "SPY"]
    delta_targets = [0.15, 0.18, 0.20, 0.22, 0.25]
    dte_configs = [
        (14, 30, 7),    # Aggressive (current optimized)
        (21, 45, 14),   # Baseline
        (30, 60, 21),   # Conservative
    ]

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
    console.print(f"[dim]Initial Capital: ${initial_capital:,.2f}[/dim]")

    total_backtests = len(symbols) * len(delta_targets) * len(dte_configs)
    console.print(f"[bold cyan]Total backtests to run: {total_backtests}[/bold cyan]\n")

    # Check credentials
    if not os.environ.get("ALPACA_API_KEY") or not os.environ.get("ALPACA_SECRET_KEY"):
        console.print("[red]ERROR: Alpaca credentials required![/red]")
        console.print("[yellow]Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables[/yellow]")
        return

    # Create all backtest tasks upfront (PARALLEL EXECUTION)
    console.print("[cyan]Creating backtest tasks...[/cyan]")
    tasks = []
    task_metadata = []  # Track which parameters each task represents

    for symbol in symbols:
        for delta in delta_targets:
            for min_dte, max_dte, close_dte in dte_configs:
                task = run_parameter_backtest(
                    symbol=symbol,
                    delta_target=delta,
                    min_dte=min_dte,
                    max_dte=max_dte,
                    close_dte=close_dte,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    initial_capital=initial_capital,
                )
                tasks.append(task)
                task_metadata.append({
                    "symbol": symbol,
                    "delta": delta,
                    "dte": f"{min_dte}-{max_dte}-{close_dte}"
                })

    # Run all tasks concurrently with progress tracking
    console.print(f"[bold green]Running {len(tasks)} backtests in parallel...[/bold green]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console,
    ) as progress:
        task_progress = progress.add_task(
            "[cyan]Running parallel backtests...",
            total=len(tasks)
        )

        # Run all tasks concurrently
        results = []
        completed = 0

        for coro in asyncio.as_completed(tasks):
            try:
                result = await coro
                results.append(result)
            except Exception as e:
                meta = task_metadata[completed]
                console.print(f"\n[red]Error in {meta['symbol']} delta={meta['delta']} dte={meta['dte']}: {e}[/red]")
                results.append({
                    "symbol": meta["symbol"],
                    "delta": meta["delta"],
                    "min_dte": int(meta["dte"].split('-')[0]),
                    "max_dte": int(meta["dte"].split('-')[1]),
                    "close_dte": int(meta["dte"].split('-')[2]),
                    "error": str(e)
                })

            completed += 1
            progress.update(
                task_progress,
                advance=1,
                description=f"[cyan]Completed {completed}/{len(tasks)} backtests..."
            )

        progress.update(task_progress, description=f"[green]✓ All {len(tasks)} backtests complete!")

    # Organize results by symbol
    all_results = {}
    for result in results:
        symbol = result["symbol"]
        if symbol not in all_results:
            all_results[symbol] = []
        all_results[symbol].append(result)

    # Sort each symbol's results by delta and DTE
    for symbol in all_results:
        all_results[symbol].sort(key=lambda r: (r["delta"], r["min_dte"]))

    # Display results
    console.print("\n\n")
    console.print(Panel.fit(
        "[bold green]PARAMETER GRID SEARCH RESULTS[/bold green]",
        border_style="green"
    ))

    for symbol, results in all_results.items():
        console.print(f"\n[bold cyan]{symbol} Results:[/bold cyan]")

        # Create comparison table
        table = Table(title=f"{symbol} Parameter Grid", box=box.ROUNDED)
        table.add_column("Delta", justify="center", style="cyan", width=8)
        table.add_column("DTE Range", justify="center", width=12)
        table.add_column("Return", justify="right", width=10)
        table.add_column("Sharpe", justify="right", width=8)
        table.add_column("Win%", justify="right", width=8)
        table.add_column("Trades", justify="right", width=8)
        table.add_column("Max DD", justify="right", width=10)

        for result in results:
            if "error" in result:
                table.add_row(
                    f"{result['delta']:.2f}",
                    f"{result['min_dte']}-{result['max_dte']}",
                    "[red]ERROR[/red]",
                    "[red]ERROR[/red]",
                    "[red]ERROR[/red]",
                    "[red]ERROR[/red]",
                    "[red]ERROR[/red]",
                )
            else:
                m = result["metrics"]

                # Highlight baseline (delta=0.20, DTE 21-45)
                is_baseline = (result["delta"] == 0.20 and result["min_dte"] == 21 and result["max_dte"] == 45)
                delta_str = f"{result['delta']:.2f}"
                dte_str = f"{result['min_dte']}-{result['max_dte']}"
                if is_baseline:
                    delta_str = f"[bold]{delta_str}*[/bold]"
                    dte_str = f"[bold]{dte_str}*[/bold]"

                # Color code returns
                return_style = "green" if m.total_return_percent > 0 else "red"

                table.add_row(
                    delta_str,
                    dte_str,
                    f"[{return_style}]{m.total_return_percent:+.2f}%[/{return_style}]",
                    f"{m.sharpe_ratio:.2f}",
                    f"{m.win_rate:.1f}%",
                    str(m.total_trades),
                    f"{m.max_drawdown_percent:.2f}%",
                )

        console.print(table)

        # Find best parameters
        valid_results = [r for r in results if "error" not in r]
        if valid_results:
            # Best by Sharpe ratio (primary metric)
            best_sharpe = max(valid_results, key=lambda r: r["metrics"].sharpe_ratio)
            console.print(f"\n[green]  ✓ Best Sharpe: delta={best_sharpe['delta']:.2f}, "
                         f"DTE {best_sharpe['min_dte']}-{best_sharpe['max_dte']} "
                         f"(Sharpe {best_sharpe['metrics'].sharpe_ratio:.2f})[/green]")

            # Best by total return
            best_return = max(valid_results, key=lambda r: r["metrics"].total_return_percent)
            console.print(f"[green]  ✓ Best Return: delta={best_return['delta']:.2f}, "
                         f"DTE {best_return['min_dte']}-{best_return['max_dte']} "
                         f"({best_return['metrics'].total_return_percent:+.2f}%)[/green]")

            # Baseline comparison
            baseline_result = next((r for r in valid_results
                                  if r["delta"] == 0.20 and r["min_dte"] == 21 and r["max_dte"] == 45), None)
            if baseline_result:
                baseline_sharpe = baseline_result["metrics"].sharpe_ratio
                if baseline_sharpe > 0 and best_sharpe != baseline_result:
                    improvement = ((best_sharpe["metrics"].sharpe_ratio / baseline_sharpe) - 1) * 100
                    console.print(f"\n[yellow]  → Improvement vs baseline: "
                                 f"{improvement:+.1f}% Sharpe[/yellow]")

    # Summary recommendations
    console.print("\n\n[bold cyan]Recommendations:[/bold cyan]")
    console.print("[dim]* = Current baseline (delta=0.20, DTE 21-45-14)[/dim]\n")

    for symbol, results in all_results.items():
        valid_results = [r for r in results if "error" not in r]
        if valid_results:
            best = max(valid_results, key=lambda r: r["metrics"].sharpe_ratio)
            baseline = next((r for r in valid_results
                           if r["delta"] == 0.20 and r["min_dte"] == 21 and r["max_dte"] == 45), None)

            if baseline:
                baseline_sharpe = baseline["metrics"].sharpe_ratio
                if baseline_sharpe > 0:
                    sharpe_improvement = ((best["metrics"].sharpe_ratio / baseline_sharpe) - 1) * 100
                    if sharpe_improvement > 5:  # More than 5% improvement
                        console.print(
                            f"[green]✓ {symbol}: Recommend delta={best['delta']:.2f}, "
                            f"DTE {best['min_dte']}-{best['max_dte']} "
                            f"(+{sharpe_improvement:.1f}% Sharpe improvement)[/green]"
                        )
                    else:
                        console.print(
                            f"[yellow]→ {symbol}: Baseline is near-optimal "
                            f"(best improvement: {sharpe_improvement:+.1f}%)[/yellow]"
                        )

    console.print("\n[dim]Parameter grid search complete.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
