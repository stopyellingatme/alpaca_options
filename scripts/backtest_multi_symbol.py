#!/usr/bin/env python3
"""Multi-Symbol Backtest with DoltHub Historical Options Data.

This script runs backtests on multiple symbols using real historical data:
- Real underlying price data from Alpaca
- Real historical options chains from DoltHub (2019-2024)
- Vertical spread strategy (credit spreads)

Symbols tested: SPY, AAPL, MSFT, NVDA

Usage:
    uv run python scripts/backtest_multi_symbol.py
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
) -> Dict:
    """Run backtest for a single symbol.

    Args:
        symbol: Stock symbol to backtest.
        start_dt: Start date.
        end_dt: End date.
        initial_capital: Starting capital.

    Returns:
        Dict with results and metrics.
    """
    from alpaca_options.backtesting import BacktestEngine
    from alpaca_options.backtesting.alpaca_options_fetcher import AlpacaOptionsDataFetcher
    from alpaca_options.backtesting.dolthub_options_fetcher import DoltHubOptionsDataFetcher
    from alpaca_options.core.config import load_config
    from alpaca_options.strategies import VerticalSpreadStrategy
    import pandas as pd

    console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
    console.print(f"[bold cyan]Backtesting {symbol}[/bold cyan]")
    console.print(f"[bold cyan]{'='*60}[/bold cyan]")

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
    console.print(f"\n[bold]Loading Underlying Data for {symbol}...[/bold]")
    with console.status(f"[cyan]Fetching {symbol} price bars..."):
        underlying_data = alpaca_fetcher.fetch_underlying_bars(
            symbol=symbol,
            start_date=start_dt,
            end_date=end_dt,
            timeframe="1Hour",
        )

    if underlying_data.empty:
        console.print(f"[red]✗ Failed to load underlying data for {symbol}![/red]")
        return {"symbol": symbol, "error": "No underlying data"}

    console.print(f"[green]✓ Loaded {len(underlying_data):,} price bars[/green]")

    # Show price stats
    price_start = underlying_data['close'].iloc[0]
    price_end = underlying_data['close'].iloc[-1]
    price_return = ((price_end/price_start)-1)*100

    console.print(f"[dim]Start: ${price_start:.2f} -> End: ${price_end:.2f} ({price_return:+.1f}%)[/dim]")

    # Add technical indicators
    with console.status("[cyan]Computing technical indicators..."):
        from alpaca_options.backtesting.data_loader import BacktestDataLoader
        data_loader = BacktestDataLoader(settings.backtesting.data)
        underlying_data = data_loader.add_technical_indicators(underlying_data)

    console.print("[green]✓ Technical indicators computed[/green]")

    # Fetch options chains from DoltHub
    console.print(f"\n[bold]Fetching Options Chains for {symbol}...[/bold]")

    options_data = {}
    # Use dropna(subset=['close']) to only require close price (not all indicators)
    daily_timestamps = underlying_data.resample('1D').last().dropna(subset=['close']).index

    with console.status(f"[cyan]Fetching DoltHub chains for {symbol}...") as status:
        total = len(daily_timestamps)
        chains_loaded = 0

        for i, timestamp in enumerate(daily_timestamps):
            status.update(f"[cyan]Fetching chain {i+1}/{total} ({timestamp.date()})...")

            chain = dolthub_fetcher.fetch_option_chain(
                underlying=symbol,
                as_of_date=timestamp,
            )

            if chain:
                options_data[timestamp] = chain
                chains_loaded += 1

    if not options_data:
        console.print(f"[red]✗ No DoltHub options data for {symbol}![/red]")
        return {"symbol": symbol, "error": "No options data"}

    console.print(f"[green]✓ Loaded {chains_loaded:,} option chains ({chains_loaded/total*100:.1f}% coverage)[/green]")

    # Create strategy instance
    strategy = VerticalSpreadStrategy()

    # Configure strategy
    strat_config = settings.strategies.get("vertical_spread")
    if strat_config:
        strategy._config = strat_config.config.copy()
    else:
        strategy._config = {}

    strategy._config["underlyings"] = [symbol]

    # OPTIMIZED filters for DoltHub (validated via diagnostic)
    strategy._config["spread_width"] = 5.0
    strategy._config["min_iv_rank"] = 0  # DoltHub has good IV data, but no rank calc
    strategy._config["min_dte"] = 21
    strategy._config["max_dte"] = 45
    strategy._config["close_dte"] = 14
    strategy._config["min_open_interest"] = 0  # CRITICAL: DoltHub has OI=0
    strategy._config["max_spread_percent"] = 15.0  # Allow wider spreads
    strategy._config["min_return_on_risk"] = 0.08  # 8% minimum ROR
    strategy._config["rsi_oversold"] = 45.0
    strategy._config["rsi_overbought"] = 55.0
    strategy._config["min_credit"] = 15.0  # Minimum $15 credit

    # Initialize strategy
    await strategy.initialize(strategy._config)

    # Create backtest engine
    engine = BacktestEngine(settings.backtesting, settings.risk)

    # Run backtest
    console.print(f"\n[bold]Running Backtest...[/bold]")

    with console.status("[cyan]Processing trades..."):
        result = await engine.run(
            strategy=strategy,
            underlying_data=underlying_data,
            options_data=options_data,
            start_date=start_dt,
            end_date=end_dt,
        )

    m = result.metrics

    # Display results
    console.print(f"\n[bold green]✓ {symbol} Backtest Complete[/bold green]")

    results_table = Table(title=f"{symbol} Results", box=box.SIMPLE)
    results_table.add_column("Metric", style="cyan")
    results_table.add_column("Value", justify="right", style="white")

    results_table.add_row("Total Return", f"{m.total_return_percent:.2f}%")
    results_table.add_row("Annualized Return", f"{m.annualized_return:.2f}%")
    results_table.add_row("Max Drawdown", f"{m.max_drawdown_percent:.2f}%")
    results_table.add_row("Sharpe Ratio", f"{m.sharpe_ratio:.2f}")
    results_table.add_row("Win Rate", f"{m.win_rate:.1f}%")
    results_table.add_row("Total Trades", str(m.total_trades))
    results_table.add_row("Profit Factor", f"{m.profit_factor:.2f}" if m.profit_factor != float('inf') else "N/A")

    console.print(results_table)

    return {
        "symbol": symbol,
        "metrics": m,
        "underlying_return": price_return,
        "chains_loaded": chains_loaded,
        "total_days": total,
        "coverage": chains_loaded/total*100,
    }


async def main():
    """Run backtests on multiple symbols."""
    console.print(Panel.fit(
        "[bold cyan]Multi-Symbol Backtest[/bold cyan]\n"
        "Vertical Spread Strategy with DoltHub Data\n"
        "Symbols: AAPL, MSFT, NVDA, SPY",
        border_style="cyan"
    ))

    # Backtest parameters
    symbols = ["AAPL", "MSFT", "NVDA", "SPY"]
    start_dt = datetime(2019, 2, 9)   # Extended backtest: DoltHub earliest date
    end_dt = datetime(2024, 12, 31)   # Extended backtest: DoltHub latest date
    initial_capital = 10000.0

    console.print(f"\n[dim]Period: {start_dt.date()} to {end_dt.date()} (~6 years)[/dim]")
    console.print(f"[dim]Initial Capital: ${initial_capital:,.2f}[/dim]")
    console.print(f"[dim]Strategy: Vertical Spread (Credit Spreads)[/dim]")
    console.print(f"[dim]Filters: DoltHub-optimized (validated via diagnostic)[/dim]")

    # Check credentials
    if not os.environ.get("ALPACA_API_KEY") or not os.environ.get("ALPACA_SECRET_KEY"):
        console.print("\n[red]ERROR: Alpaca credentials required![/red]")
        console.print("[yellow]Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables[/yellow]")
        return

    # Run backtests for each symbol
    results = []

    for symbol in symbols:
        try:
            result = await run_symbol_backtest(
                symbol=symbol,
                start_dt=start_dt,
                end_dt=end_dt,
                initial_capital=initial_capital,
            )
            results.append(result)
        except Exception as e:
            console.print(f"\n[red]✗ Error backtesting {symbol}: {e}[/red]")
            results.append({"symbol": symbol, "error": str(e)})

    # Display comparison table
    console.print("\n")
    console.print(Panel.fit(
        "[bold green]BACKTEST RESULTS COMPARISON[/bold green]",
        border_style="green"
    ))

    comparison_table = Table(title="Performance Comparison", box=box.ROUNDED)
    comparison_table.add_column("Symbol", style="cyan", width=8)
    comparison_table.add_column("Total Return", justify="right", width=12)
    comparison_table.add_column("Annual Return", justify="right", width=12)
    comparison_table.add_column("Max DD", justify="right", width=10)
    comparison_table.add_column("Sharpe", justify="right", width=8)
    comparison_table.add_column("Win Rate", justify="right", width=10)
    comparison_table.add_column("Trades", justify="right", width=8)
    comparison_table.add_column("Coverage", justify="right", width=10)

    for result in results:
        if "error" in result:
            comparison_table.add_row(
                result["symbol"],
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

            # Color code returns
            total_return_style = "green" if m.total_return_percent > 0 else "red"
            annual_return_style = "green" if m.annualized_return > 0 else "red"

            comparison_table.add_row(
                result["symbol"],
                f"[{total_return_style}]{m.total_return_percent:+.2f}%[/{total_return_style}]",
                f"[{annual_return_style}]{m.annualized_return:+.2f}%[/{annual_return_style}]",
                f"{m.max_drawdown_percent:.2f}%",
                f"{m.sharpe_ratio:.2f}",
                f"{m.win_rate:.1f}%",
                str(m.total_trades),
                f"{result['coverage']:.1f}%",
            )

    console.print(comparison_table)

    # Best performers
    valid_results = [r for r in results if "error" not in r]

    if valid_results:
        console.print("\n[bold cyan]Key Insights:[/bold cyan]")

        # Best total return
        best_return = max(valid_results, key=lambda r: r["metrics"].total_return_percent)
        console.print(f"[green]  ✓ Best Total Return: {best_return['symbol']} ({best_return['metrics'].total_return_percent:+.2f}%)[/green]")

        # Best Sharpe
        best_sharpe = max(valid_results, key=lambda r: r["metrics"].sharpe_ratio)
        console.print(f"[green]  ✓ Best Risk-Adjusted: {best_sharpe['symbol']} (Sharpe: {best_sharpe['metrics'].sharpe_ratio:.2f})[/green]")

        # Best win rate
        best_winrate = max(valid_results, key=lambda r: r["metrics"].win_rate)
        console.print(f"[green]  ✓ Best Win Rate: {best_winrate['symbol']} ({best_winrate['metrics'].win_rate:.1f}%)[/green]")

        # Most trades
        most_trades = max(valid_results, key=lambda r: r["metrics"].total_trades)
        console.print(f"[green]  ✓ Most Active: {most_trades['symbol']} ({most_trades['metrics'].total_trades} trades)[/green]")

        # Average metrics
        avg_return = sum(r["metrics"].total_return_percent for r in valid_results) / len(valid_results)
        avg_sharpe = sum(r["metrics"].sharpe_ratio for r in valid_results) / len(valid_results)
        avg_winrate = sum(r["metrics"].win_rate for r in valid_results) / len(valid_results)

        console.print(f"\n[bold]Average Performance:[/bold]")
        console.print(f"[dim]  Total Return: {avg_return:+.2f}%[/dim]")
        console.print(f"[dim]  Sharpe Ratio: {avg_sharpe:.2f}[/dim]")
        console.print(f"[dim]  Win Rate: {avg_winrate:.1f}%[/dim]")

    console.print("\n[bold green]Data Source:[/bold green]")
    console.print("[green]  ✓ Underlying: Alpaca API (REAL)[/green]")
    console.print("[green]  ✓ Options: DoltHub Database (REAL 2019-2024)[/green]")
    console.print("[green]  ✓ Greeks & IV: From DoltHub (REAL)[/green]")

    console.print("\n[dim]Multi-symbol backtest completed successfully.[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
