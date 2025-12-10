#!/usr/bin/env python3
"""Walk-Forward Validation for Vertical Spread Strategy.

This script implements proper out-of-sample validation to detect overfitting:

1. Split 2019-2024 into rolling windows
2. Optimize parameters on training window (2 years)
3. Test on out-of-sample period (1 year)
4. Report average out-of-sample performance

Walk-Forward Windows:
- Train: 2019-2020 → Test: 2021
- Train: 2020-2021 → Test: 2022
- Train: 2021-2022 → Test: 2023
- Train: 2022-2023 → Test: 2024

Expected Outcome:
- If out-of-sample returns are 60-80% of in-sample → Robust strategy
- If out-of-sample returns are <50% of in-sample → Overfitting detected

Usage:
    uv run python scripts/validation/walk_forward_validation.py
    uv run python scripts/validation/walk_forward_validation.py --quick  # Single symbol test
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


async def optimize_parameters(
    symbol: str,
    start_dt: datetime,
    end_dt: datetime,
    initial_capital: float = 10000.0,
) -> Tuple[float, int, int, int]:
    """Optimize delta and DTE parameters on training data.

    Tests multiple combinations and returns best parameters based on Sharpe ratio.

    Args:
        symbol: Stock symbol to optimize
        start_dt: Training start date
        end_dt: Training end date
        initial_capital: Starting capital

    Returns:
        Tuple of (best_delta, best_min_dte, best_max_dte, best_close_dte)
    """
    from alpaca_options.backtesting import BacktestEngine
    from alpaca_options.backtesting.alpaca_options_fetcher import AlpacaOptionsDataFetcher
    from alpaca_options.backtesting.dolthub_options_fetcher import DoltHubOptionsDataFetcher
    from alpaca_options.core.config import load_config
    from alpaca_options.strategies import VerticalSpreadStrategy

    # Parameter grid (reduced for speed)
    delta_values = [0.20, 0.25, 0.30]
    dte_configs = [
        (14, 30, 7),   # Current optimized
        (21, 45, 14),  # Baseline
    ]

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

    # Fetch underlying data
    underlying_data = alpaca_fetcher.fetch_underlying_bars(
        symbol=symbol,
        start_date=start_dt,
        end_date=end_dt,
        timeframe="1Hour",
    )

    if underlying_data.empty:
        console.print(f"[red]No underlying data for {symbol}[/red]")
        return 0.25, 14, 30, 7  # Return defaults

    # Add technical indicators
    from alpaca_options.backtesting.data_loader import BacktestDataLoader
    data_loader = BacktestDataLoader(settings.backtesting.data)
    underlying_data = data_loader.add_technical_indicators(underlying_data)

    # Fetch options chains
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
        console.print(f"[red]No options data for {symbol}[/red]")
        return 0.25, 14, 30, 7

    # Test all parameter combinations
    best_sharpe = -999
    best_params = (0.25, 14, 30, 7)

    console.print(f"[dim]  Optimizing {symbol} ({start_dt.year}-{end_dt.year})...[/dim]")

    for delta in delta_values:
        for min_dte, max_dte, close_dte in dte_configs:
            # Create strategy
            strategy = VerticalSpreadStrategy()

            # Configure strategy
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

            # Create backtest engine
            engine = BacktestEngine(settings.backtesting, settings.risk)

            # Run backtest
            try:
                result = await engine.run(
                    strategy=strategy,
                    underlying_data=underlying_data,
                    options_data=options_data,
                    start_date=start_dt,
                    end_date=end_dt,
                )

                sharpe = result.metrics.sharpe_ratio

                # Track best parameters
                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_params = (delta, min_dte, max_dte, close_dte)

            except Exception as e:
                console.print(f"[dim]    Error testing delta={delta}, DTE=({min_dte},{max_dte},{close_dte}): {e}[/dim]")
                continue

    console.print(
        f"[dim]  Best params: delta={best_params[0]:.2f}, "
        f"DTE=({best_params[1]},{best_params[2]},{best_params[3]}), "
        f"Sharpe={best_sharpe:.2f}[/dim]"
    )

    return best_params


async def test_parameters(
    symbol: str,
    start_dt: datetime,
    end_dt: datetime,
    delta: float,
    min_dte: int,
    max_dte: int,
    close_dte: int,
    initial_capital: float = 10000.0,
) -> Dict:
    """Test specific parameters on out-of-sample data.

    Args:
        symbol: Stock symbol to test
        start_dt: Test start date
        end_dt: Test end date
        delta: Delta target
        min_dte: Minimum entry DTE
        max_dte: Maximum entry DTE
        close_dte: Exit DTE threshold
        initial_capital: Starting capital

    Returns:
        Dict with test results and metrics
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

    # Fetch underlying data
    underlying_data = alpaca_fetcher.fetch_underlying_bars(
        symbol=symbol,
        start_date=start_dt,
        end_date=end_dt,
        timeframe="1Hour",
    )

    if underlying_data.empty:
        return {"symbol": symbol, "error": "No underlying data"}

    # Add technical indicators
    from alpaca_options.backtesting.data_loader import BacktestDataLoader
    data_loader = BacktestDataLoader(settings.backtesting.data)
    underlying_data = data_loader.add_technical_indicators(underlying_data)

    # Fetch options chains
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
        return {"symbol": symbol, "error": "No options data"}

    # Create strategy
    strategy = VerticalSpreadStrategy()

    # Configure with test parameters
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

    return {
        "symbol": symbol,
        "metrics": result.metrics,
        "trades": len(result.trades),
        "delta": delta,
        "min_dte": min_dte,
        "max_dte": max_dte,
        "close_dte": close_dte,
    }


async def main():
    """Run walk-forward validation."""
    import argparse

    parser = argparse.ArgumentParser(description="Walk-forward validation")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Quick mode: test single symbol (SPY only)"
    )
    args = parser.parse_args()

    console.print(Panel.fit(
        "[bold cyan]Walk-Forward Validation[/bold cyan]\n"
        "Out-of-Sample Performance Testing\n\n"
        "Method:\n"
        "1. Train on 2 years → Optimize parameters\n"
        "2. Test on 1 year → Apply optimized parameters\n"
        "3. Repeat with rolling windows\n"
        "4. Report average out-of-sample performance",
        border_style="cyan"
    ))

    # Symbols to test
    symbols = ["SPY"] if args.quick else ["SPY", "AAPL", "MSFT", "NVDA"]

    # Walk-forward windows
    windows = [
        # (train_start, train_end, test_start, test_end)
        (datetime(2019, 2, 9), datetime(2020, 12, 31), datetime(2021, 1, 1), datetime(2021, 12, 31)),
        (datetime(2020, 1, 1), datetime(2021, 12, 31), datetime(2022, 1, 1), datetime(2022, 12, 31)),
        (datetime(2021, 1, 1), datetime(2022, 12, 31), datetime(2023, 1, 1), datetime(2023, 12, 31)),
        (datetime(2022, 1, 1), datetime(2023, 12, 31), datetime(2024, 1, 1), datetime(2024, 12, 31)),
    ]

    console.print(f"\n[bold]Testing {len(symbols)} symbol(s) across {len(windows)} windows[/bold]")
    console.print(f"[dim]Symbols: {', '.join(symbols)}[/dim]\n")

    # Check credentials
    if not os.environ.get("ALPACA_API_KEY") or not os.environ.get("ALPACA_SECRET_KEY"):
        console.print("[red]ERROR: Alpaca credentials required![/red]")
        console.print("[yellow]Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables[/yellow]")
        return

    # Store results for each symbol
    symbol_results = {symbol: {"in_sample": [], "out_of_sample": []} for symbol in symbols}

    # Run walk-forward for each symbol
    for symbol in symbols:
        console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
        console.print(f"[bold cyan]Walk-Forward: {symbol}[/bold cyan]")
        console.print(f"[bold cyan]{'='*60}[/bold cyan]\n")

        for i, (train_start, train_end, test_start, test_end) in enumerate(windows, 1):
            console.print(f"\n[bold]Window {i}/4:[/bold]")
            console.print(f"  Train: {train_start.year}-{train_end.year}")
            console.print(f"  Test:  {test_start.year}-{test_end.year}")

            try:
                # Optimize on training data
                console.print(f"\n[cyan]Phase 1: Optimizing on training data...[/cyan]")
                best_delta, best_min_dte, best_max_dte, best_close_dte = await optimize_parameters(
                    symbol=symbol,
                    start_dt=train_start,
                    end_dt=train_end,
                    initial_capital=10000.0,
                )

                # Test on in-sample data (to compare)
                console.print(f"\n[cyan]Phase 2: Testing on training data (in-sample)...[/cyan]")
                in_sample_result = await test_parameters(
                    symbol=symbol,
                    start_dt=train_start,
                    end_dt=train_end,
                    delta=best_delta,
                    min_dte=best_min_dte,
                    max_dte=best_max_dte,
                    close_dte=best_close_dte,
                    initial_capital=10000.0,
                )

                # Test on out-of-sample data
                console.print(f"\n[cyan]Phase 3: Testing on test data (out-of-sample)...[/cyan]")
                out_of_sample_result = await test_parameters(
                    symbol=symbol,
                    start_dt=test_start,
                    end_dt=test_end,
                    delta=best_delta,
                    min_dte=best_min_dte,
                    max_dte=best_max_dte,
                    close_dte=best_close_dte,
                    initial_capital=10000.0,
                )

                # Store results
                if "error" not in in_sample_result:
                    symbol_results[symbol]["in_sample"].append(in_sample_result)
                if "error" not in out_of_sample_result:
                    symbol_results[symbol]["out_of_sample"].append(out_of_sample_result)

                # Display window results
                if "error" not in in_sample_result and "error" not in out_of_sample_result:
                    in_return = in_sample_result["metrics"].total_return_percent
                    out_return = out_of_sample_result["metrics"].total_return_percent
                    in_sharpe = in_sample_result["metrics"].sharpe_ratio
                    out_sharpe = out_of_sample_result["metrics"].sharpe_ratio

                    efficiency = (out_return / in_return * 100) if in_return != 0 else 0

                    console.print(f"\n[bold]Window {i} Results:[/bold]")
                    console.print(f"  In-Sample:     {in_return:+.2f}% return, {in_sharpe:.2f} Sharpe")
                    console.print(f"  Out-of-Sample: {out_return:+.2f}% return, {out_sharpe:.2f} Sharpe")
                    console.print(f"  Efficiency:    {efficiency:.1f}% (OOS/IS ratio)")

                    if efficiency > 80:
                        console.print(f"  [green]✓ Excellent - Strategy holds up well[/green]")
                    elif efficiency > 60:
                        console.print(f"  [yellow]⚠ Good - Some degradation expected[/yellow]")
                    else:
                        console.print(f"  [red]✗ Poor - Possible overfitting[/red]")

            except Exception as e:
                console.print(f"[red]Error in window {i}: {e}[/red]")
                import traceback
                traceback.print_exc()
                continue

    # Display final results
    console.print("\n\n")
    console.print(Panel.fit(
        "[bold green]WALK-FORWARD VALIDATION RESULTS[/bold green]",
        border_style="green"
    ))

    for symbol in symbols:
        in_sample = symbol_results[symbol]["in_sample"]
        out_of_sample = symbol_results[symbol]["out_of_sample"]

        if not in_sample or not out_of_sample:
            console.print(f"\n[yellow]{symbol}: Insufficient data[/yellow]")
            continue

        console.print(f"\n[bold cyan]{symbol} Summary:[/bold cyan]")

        # Calculate averages
        avg_in_return = sum(r["metrics"].total_return_percent for r in in_sample) / len(in_sample)
        avg_out_return = sum(r["metrics"].total_return_percent for r in out_of_sample) / len(out_of_sample)
        avg_in_sharpe = sum(r["metrics"].sharpe_ratio for r in in_sample) / len(in_sample)
        avg_out_sharpe = sum(r["metrics"].sharpe_ratio for r in out_of_sample) / len(out_of_sample)
        avg_in_wr = sum(r["metrics"].win_rate for r in in_sample) / len(in_sample)
        avg_out_wr = sum(r["metrics"].win_rate for r in out_of_sample) / len(out_of_sample)

        efficiency = (avg_out_return / avg_in_return * 100) if avg_in_return != 0 else 0

        # Create results table
        table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
        table.add_column("Metric", style="white")
        table.add_column("In-Sample", justify="right")
        table.add_column("Out-of-Sample", justify="right")
        table.add_column("Efficiency", justify="right")

        table.add_row(
            "Total Return",
            f"{avg_in_return:+.2f}%",
            f"{avg_out_return:+.2f}%",
            f"{efficiency:.1f}%"
        )

        table.add_row(
            "Sharpe Ratio",
            f"{avg_in_sharpe:.2f}",
            f"{avg_out_sharpe:.2f}",
            f"{(avg_out_sharpe / avg_in_sharpe * 100) if avg_in_sharpe != 0 else 0:.1f}%"
        )

        table.add_row(
            "Win Rate",
            f"{avg_in_wr:.1f}%",
            f"{avg_out_wr:.1f}%",
            f"{(avg_out_wr / avg_in_wr * 100) if avg_in_wr != 0 else 0:.1f}%"
        )

        console.print(table)

        # Assessment
        console.print(f"\n[bold]Assessment:[/bold]")
        if efficiency > 80:
            console.print(f"  [green]✓ ROBUST - Strategy generalizes well to unseen data[/green]")
            console.print(f"  [green]  Expected live returns: {avg_out_return * 0.8:.1f}% - {avg_out_return:.1f}%[/green]")
        elif efficiency > 60:
            console.print(f"  [yellow]⚠ MODERATE - Some overfitting, but acceptable[/yellow]")
            console.print(f"  [yellow]  Expected live returns: {avg_out_return * 0.7:.1f}% - {avg_out_return:.1f}%[/yellow]")
        else:
            console.print(f"  [red]✗ OVERFITTED - Strategy does not generalize[/red]")
            console.print(f"  [red]  Expected live returns: Significantly lower than {avg_out_return:.1f}%[/red]")

    # Overall conclusion
    console.print("\n" + "="*60)
    console.print(Panel.fit(
        "[bold]Next Steps:[/bold]\n\n"
        "If efficiency >80%: ✅ Proceed to paper trading\n"
        "If efficiency 60-80%: ⚠️ Proceed with caution, expect lower returns\n"
        "If efficiency <60%: 🛑 Strategy needs rework before live trading\n\n"
        "Remember: Paper trading will add another 10-20% degradation\n"
        "due to real-world execution challenges.",
        border_style="cyan"
    ))


if __name__ == "__main__":
    asyncio.run(main())
