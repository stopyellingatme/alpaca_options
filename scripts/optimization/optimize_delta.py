#!/usr/bin/env python3
"""Delta Target Optimization for Vertical Spread Strategy.

This script tests different delta targets to find the optimal balance between:
- Win rate (higher delta = lower probability)
- Premium captured (higher delta = more premium)
- Risk-adjusted returns (Sharpe ratio)

Tests delta targets: 0.15, 0.18, 0.20, 0.22, 0.25

Usage:
    uv run python scripts/optimize_delta.py
    uv run python scripts/optimize_delta.py --symbol AAPL  # Test single symbol
    uv run python scripts/optimize_delta.py --quick  # Use 2023-2024 only for faster testing
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

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


async def run_delta_backtest(
    delta_target: float,
    symbol: str,
    start_dt: datetime,
    end_dt: datetime,
    initial_capital: float = 10000.0,
) -> Dict:
    """Run backtest with specific delta target.

    Args:
        delta_target: Target delta (e.g., 0.20 for 20 delta)
        symbol: Stock symbol to test
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
    import pandas as pd

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
        return {"symbol": symbol, "delta": delta_target, "error": "No underlying data"}

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
        return {"symbol": symbol, "delta": delta_target, "error": "No options data"}

    # Create strategy instance
    strategy = VerticalSpreadStrategy()

    # Configure strategy with specific delta
    strat_config = settings.strategies.get("vertical_spread")
    if strat_config:
        strategy._config = strat_config.config.copy()
    else:
        strategy._config = {}

    strategy._config["underlyings"] = [symbol]

    # Set DELTA TARGET (optimization parameter)
    strategy._config["delta_target"] = delta_target

    # Keep other parameters at baseline
    strategy._config["spread_width"] = 5.0
    strategy._config["min_iv_rank"] = 0
    strategy._config["min_dte"] = 21
    strategy._config["max_dte"] = 45
    strategy._config["close_dte"] = 14
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
        "metrics": m,
        "chains_loaded": len(options_data),
    }


async def main():
    """Run delta optimization across multiple values."""
    parser = argparse.ArgumentParser(description="Optimize delta target for vertical spreads")
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
        "[bold cyan]Delta Target Optimization[/bold cyan]\n"
        "Testing delta values: 0.15, 0.18, 0.20, 0.22, 0.25\n"
        "Baseline: 0.20 (20 delta)",
        border_style="cyan"
    ))

    # Parameters
    symbols = [args.symbol] if args.symbol else ["AAPL", "MSFT", "NVDA", "SPY"]
    delta_targets = [0.15, 0.18, 0.20, 0.22, 0.25]

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

    # Run optimization for each symbol
    all_results = {}

    for symbol in symbols:
        console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
        console.print(f"[bold cyan]Optimizing {symbol}[/bold cyan]")
        console.print(f"[bold cyan]{'='*60}[/bold cyan]\n")

        symbol_results = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[cyan]Testing delta values for {symbol}...",
                total=len(delta_targets)
            )

            for delta in delta_targets:
                progress.update(task, description=f"[cyan]Testing delta={delta:.2f}...")

                try:
                    result = await run_delta_backtest(
                        delta_target=delta,
                        symbol=symbol,
                        start_dt=start_dt,
                        end_dt=end_dt,
                        initial_capital=initial_capital,
                    )
                    symbol_results.append(result)
                except Exception as e:
                    console.print(f"\n[red]Error testing delta {delta} for {symbol}: {e}[/red]")
                    symbol_results.append({
                        "symbol": symbol,
                        "delta": delta,
                        "error": str(e)
                    })

                progress.update(task, advance=1)

            progress.update(task, description=f"[green]✓ {symbol} complete")

        all_results[symbol] = symbol_results

    # Display results
    console.print("\n\n")
    console.print(Panel.fit(
        "[bold green]DELTA OPTIMIZATION RESULTS[/bold green]",
        border_style="green"
    ))

    for symbol, results in all_results.items():
        console.print(f"\n[bold cyan]{symbol} Results:[/bold cyan]")

        # Create comparison table
        table = Table(title=f"{symbol} Delta Optimization", box=box.ROUNDED)
        table.add_column("Delta", justify="center", style="cyan", width=8)
        table.add_column("Total Return", justify="right", width=12)
        table.add_column("Sharpe", justify="right", width=8)
        table.add_column("Win Rate", justify="right", width=10)
        table.add_column("Trades", justify="right", width=8)
        table.add_column("Max DD", justify="right", width=10)
        table.add_column("Profit Factor", justify="right", width=12)

        for result in results:
            if "error" in result:
                table.add_row(
                    f"{result['delta']:.2f}",
                    "[red]ERROR[/red]",
                    "[red]ERROR[/red]",
                    "[red]ERROR[/red]",
                    "[red]ERROR[/red]",
                    "[red]ERROR[/red]",
                    "[red]ERROR[/red]",
                )
            else:
                m = result["metrics"]
                baseline = (result["delta"] == 0.20)

                # Highlight baseline
                delta_str = f"{result['delta']:.2f}"
                if baseline:
                    delta_str = f"[bold]{delta_str}*[/bold]"

                # Color code returns
                return_style = "green" if m.total_return_percent > 0 else "red"

                table.add_row(
                    delta_str,
                    f"[{return_style}]{m.total_return_percent:+.2f}%[/{return_style}]",
                    f"{m.sharpe_ratio:.2f}",
                    f"{m.win_rate:.1f}%",
                    str(m.total_trades),
                    f"{m.max_drawdown_percent:.2f}%",
                    f"{m.profit_factor:.2f}" if m.profit_factor != float('inf') else "N/A",
                )

        console.print(table)

        # Find best delta
        valid_results = [r for r in results if "error" not in r]
        if valid_results:
            # Best by Sharpe ratio (primary metric)
            best_sharpe = max(valid_results, key=lambda r: r["metrics"].sharpe_ratio)
            console.print(f"\n[green]  ✓ Best Sharpe: delta={best_sharpe['delta']:.2f} "
                         f"(Sharpe {best_sharpe['metrics'].sharpe_ratio:.2f})[/green]")

            # Best by win rate
            best_winrate = max(valid_results, key=lambda r: r["metrics"].win_rate)
            console.print(f"[green]  ✓ Best Win Rate: delta={best_winrate['delta']:.2f} "
                         f"({best_winrate['metrics'].win_rate:.1f}%)[/green]")

            # Best by total return
            best_return = max(valid_results, key=lambda r: r["metrics"].total_return_percent)
            console.print(f"[green]  ✓ Best Return: delta={best_return['delta']:.2f} "
                         f"({best_return['metrics'].total_return_percent:+.2f}%)[/green]")

            # Baseline comparison
            baseline_result = next((r for r in valid_results if r["delta"] == 0.20), None)
            if baseline_result and best_sharpe["delta"] != 0.20:
                baseline_sharpe = baseline_result["metrics"].sharpe_ratio
                if baseline_sharpe > 0:
                    improvement = ((best_sharpe["metrics"].sharpe_ratio / baseline_sharpe) - 1) * 100
                    console.print(f"\n[yellow]  → Improvement vs baseline (delta=0.20): "
                                 f"{improvement:+.1f}% Sharpe[/yellow]")
                else:
                    console.print(f"\n[yellow]  → Baseline Sharpe is 0, cannot calculate improvement[/yellow]")

    # Summary recommendations
    console.print("\n\n[bold cyan]Recommendations:[/bold cyan]")
    console.print("[dim]* = Current baseline (delta=0.20)[/dim]\n")

    for symbol, results in all_results.items():
        valid_results = [r for r in results if "error" not in r]
        if valid_results:
            best = max(valid_results, key=lambda r: r["metrics"].sharpe_ratio)
            baseline = next((r for r in valid_results if r["delta"] == 0.20), None)

            if baseline and best["delta"] != 0.20:
                baseline_sharpe = baseline["metrics"].sharpe_ratio
                if baseline_sharpe > 0:
                    sharpe_improvement = ((best["metrics"].sharpe_ratio / baseline_sharpe) - 1) * 100
                    if sharpe_improvement > 5:  # More than 5% improvement
                        console.print(
                            f"[green]✓ {symbol}: Consider delta={best['delta']:.2f} "
                            f"(+{sharpe_improvement:.1f}% Sharpe improvement)[/green]"
                        )
                    else:
                        console.print(
                            f"[yellow]→ {symbol}: Current delta=0.20 is near-optimal "
                            f"(best is {best['delta']:.2f} with {sharpe_improvement:+.1f}% improvement)[/yellow]"
                        )
                else:
                    console.print(
                        f"[yellow]→ {symbol}: Baseline Sharpe is 0, recommending best delta={best['delta']:.2f}[/yellow]"
                    )
            else:
                console.print(
                    f"[green]✓ {symbol}: Current delta=0.20 is optimal[/green]"
                )

    console.print("\n[dim]Delta optimization complete.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
