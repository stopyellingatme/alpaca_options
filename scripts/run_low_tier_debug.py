#!/usr/bin/env python3
"""Debug script for LOW capital tier backtesting.

Runs Vertical Spread strategy with relaxed criteria to understand
why no trades are being executed with real Alpaca data.
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

from alpaca_options.backtesting import BacktestDataLoader, BacktestEngine
from alpaca_options.core.config import load_config, BacktestConfig
from alpaca_options.strategies import VerticalSpreadStrategy

console = Console()


async def run_low_tier_backtest(
    settings,
    start_date: datetime,
    end_date: datetime,
    initial_capital: float = 5000,
    relaxed: bool = False,
):
    """Run a single LOW tier backtest with optional relaxed criteria."""
    symbol = "QQQ"

    console.print(f"\n[bold blue]{'='*60}[/bold blue]")
    console.print(f"[bold blue]LOW Tier Backtest - Vertical Spread on {symbol}[/bold blue]")
    console.print(f"[bold blue]Capital: ${initial_capital:,.0f} | Relaxed: {relaxed}[/bold blue]")
    console.print(f"[bold blue]{'='*60}[/bold blue]")

    # Create strategy instance
    strat = VerticalSpreadStrategy()

    # Get base config from settings
    strat_config = settings.strategies.get("vertical_spread")
    if strat_config:
        config = strat_config.config.copy()
    else:
        config = {}

    config["underlyings"] = [symbol]

    # Apply relaxed criteria if requested
    if relaxed:
        console.print("[yellow]Using RELAXED criteria:[/yellow]")
        config["rsi_oversold"] = 45  # Less extreme (was 30)
        config["rsi_overbought"] = 55  # Less extreme (was 70)
        config["min_open_interest"] = 50  # Lower OI requirement (was 300)
        config["max_spread_percent"] = 15.0  # Allow wider spreads (was 3%)
        config["min_credit"] = 10  # Lower min credit (was 50)
        config["min_iv_rank"] = 0  # Disable IV rank check
        console.print(f"  RSI: oversold <= {config['rsi_oversold']}, overbought >= {config['rsi_overbought']}")
        console.print(f"  Min OI: {config['min_open_interest']}")
        console.print(f"  Max spread %: {config['max_spread_percent']}")
        console.print(f"  Min credit: ${config['min_credit']}")
        console.print(f"  Min IV rank: {config['min_iv_rank']}")
    else:
        console.print("[dim]Using DEFAULT criteria from config[/dim]")

    # Initialize strategy
    await strat.initialize(config)

    # Load data with Alpaca credentials
    data_loader = BacktestDataLoader(
        settings.backtesting.data,
        api_key=os.environ.get("ALPACA_API_KEY"),
        api_secret=os.environ.get("ALPACA_SECRET_KEY"),
    )

    console.print(f"\n[dim]Loading {symbol} underlying data...[/dim]")
    underlying_data = data_loader.load_underlying_data(
        symbol, start_date, end_date, "1h"
    )

    if underlying_data.empty:
        console.print(f"[red]No data found for {symbol}[/red]")
        return None

    console.print(f"[dim]Loaded {len(underlying_data)} bars[/dim]")

    # Show RSI stats
    if "rsi_14" not in underlying_data.columns:
        underlying_data = data_loader.add_technical_indicators(underlying_data)

    rsi_values = underlying_data["rsi_14"].dropna()
    if len(rsi_values) > 0:
        console.print(f"\n[cyan]RSI Statistics:[/cyan]")
        console.print(f"  Min RSI: {rsi_values.min():.1f}")
        console.print(f"  Max RSI: {rsi_values.max():.1f}")
        console.print(f"  Mean RSI: {rsi_values.mean():.1f}")

        # Count how many times RSI meets criteria
        if relaxed:
            oversold_count = (rsi_values <= 45).sum()
            overbought_count = (rsi_values >= 55).sum()
        else:
            oversold_count = (rsi_values <= 30).sum()
            overbought_count = (rsi_values >= 70).sum()

        console.print(f"  Oversold periods: {oversold_count}")
        console.print(f"  Overbought periods: {overbought_count}")
        console.print(f"  Total signal opportunities: {oversold_count + overbought_count}")

    # Load hybrid options data
    if data_loader.has_alpaca_credentials:
        console.print(f"\n[dim]Loading hybrid options data...[/dim]")
        options_data = data_loader.load_options_data_hybrid(
            underlying_data=underlying_data,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
        console.print(f"[dim]Loaded {len(options_data)} option chains[/dim]")

        # Sample some chains to check data quality
        if options_data:
            sample_ts = list(options_data.keys())[0]
            sample_chain = options_data[sample_ts]
            console.print(f"\n[cyan]Sample Option Chain ({sample_ts.date()}):[/cyan]")
            console.print(f"  Chain underlying: {sample_chain.underlying}")
            console.print(f"  Total contracts: {len(sample_chain.contracts)}")

            # Check OI and spreads
            with_oi = [c for c in sample_chain.contracts if c.open_interest >= 50]
            console.print(f"  Contracts with OI >= 50: {len(with_oi)}")

            # Check bid-ask spreads
            tight_spread = [c for c in sample_chain.contracts if c.spread_percent <= 10]
            console.print(f"  Contracts with spread <= 10%: {len(tight_spread)}")
    else:
        console.print(f"[dim]Generating synthetic options chains...[/dim]")
        options_data = data_loader.generate_synthetic_options_data(
            underlying_data, symbol
        )

    # Create modified settings with the specific capital
    modified_backtesting = BacktestConfig(
        default_start_date=settings.backtesting.default_start_date,
        default_end_date=settings.backtesting.default_end_date,
        initial_capital=initial_capital,
        execution=settings.backtesting.execution,
        data=settings.backtesting.data,
    )

    # Run backtest
    console.print(f"\n[dim]Running backtest...[/dim]")
    engine = BacktestEngine(modified_backtesting, settings.risk, settings.trading)

    result = await engine.run(
        strategy=strat,
        underlying_data=underlying_data,
        options_data=options_data,
        start_date=start_date,
        end_date=end_date,
    )

    return result


def display_result(result, label: str):
    """Display backtest results."""
    if result is None:
        console.print(f"[red]{label}: No result[/red]")
        return

    m = result.metrics

    console.print(f"\n[bold green]{label} Results:[/bold green]")

    table = Table(show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Total Return", f"${m.total_return:,.2f}")
    table.add_row("Return %", f"{m.total_return_percent:.2f}%")
    table.add_row("Total Trades", str(m.total_trades))
    table.add_row("Win Rate", f"{m.win_rate:.1f}%")
    table.add_row("Avg Win", f"${m.avg_win:,.2f}")
    table.add_row("Avg Loss", f"${m.avg_loss:,.2f}")
    table.add_row("Max Drawdown", f"${m.max_drawdown:,.2f}")

    console.print(table)

    if result.trades:
        console.print(f"\n[bold]Trades:[/bold]")
        for i, trade in enumerate(result.trades[:5]):
            pnl_color = "green" if trade.net_pnl > 0 else "red"
            console.print(
                f"  {i+1}. {trade.entry_time.date()} -> {trade.exit_time.date() if trade.exit_time else 'Open'}: "
                f"[{pnl_color}]${trade.net_pnl:,.2f}[/{pnl_color}]"
            )
        if len(result.trades) > 5:
            console.print(f"  ... and {len(result.trades) - 5} more trades")


async def main():
    """Run LOW tier backtests with default and relaxed criteria."""
    console.print(Panel.fit(
        "[bold]LOW Capital Tier Debug - Vertical Spread Strategy[/bold]\n"
        "Testing why no trades execute with real Alpaca data",
        border_style="blue"
    ))

    # Check for Alpaca credentials
    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if api_key and api_secret:
        console.print("[green]Alpaca credentials found[/green]")
    else:
        console.print("[red]No Alpaca credentials - exiting[/red]")
        return

    # Load configuration
    settings = load_config(project_root / "config" / "default.yaml")

    # Use recent period with Alpaca data
    start_date = datetime(2024, 3, 1)  # After Alpaca options data starts
    end_date = datetime(2024, 11, 15)

    console.print(f"\n[bold]Backtest Period:[/bold] {start_date.date()} to {end_date.date()}")

    # Test 1: Default criteria
    console.print("\n" + "="*60)
    console.print("[bold]TEST 1: Default Criteria[/bold]")
    console.print("="*60)
    result_default = await run_low_tier_backtest(
        settings, start_date, end_date, relaxed=False
    )
    display_result(result_default, "Default Criteria")

    # Test 2: Relaxed criteria
    console.print("\n" + "="*60)
    console.print("[bold]TEST 2: Relaxed Criteria[/bold]")
    console.print("="*60)
    result_relaxed = await run_low_tier_backtest(
        settings, start_date, end_date, relaxed=True
    )
    display_result(result_relaxed, "Relaxed Criteria")

    # Summary
    console.print("\n" + "="*60)
    console.print("[bold]SUMMARY[/bold]")
    console.print("="*60)

    default_trades = result_default.metrics.total_trades if result_default else 0
    relaxed_trades = result_relaxed.metrics.total_trades if result_relaxed else 0

    console.print(f"Default criteria trades: {default_trades}")
    console.print(f"Relaxed criteria trades: {relaxed_trades}")

    if default_trades == 0 and relaxed_trades > 0:
        console.print("\n[yellow]Recommendation: Consider relaxing strategy criteria in config[/yellow]")
    elif default_trades == 0 and relaxed_trades == 0:
        console.print("\n[red]Issue: Even relaxed criteria produced no trades - check data quality[/red]")


if __name__ == "__main__":
    asyncio.run(main())
