#!/usr/bin/env python3
"""Backtest with REAL Alpaca Options Data (No Synthetic Data).

This script runs a backtest using ONLY real historical data from Alpaca:
- Real underlying price data from Alpaca
- Real options data from Alpaca (available from Feb 2024)
- No synthetic data generation

Usage:
    uv run python scripts/backtest_real_options.py
"""

import asyncio
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
from rich.panel import Panel
from rich import box

console = Console()


async def run_real_options_backtest():
    """Run backtest with REAL Alpaca options data."""
    from alpaca_options.backtesting import BacktestEngine
    from alpaca_options.backtesting.alpaca_options_fetcher import AlpacaOptionsDataFetcher
    from alpaca_options.core.config import load_config
    from alpaca_options.strategies import VerticalSpreadStrategy
    from alpaca_options.strategies.base import OptionChain
    import pandas as pd

    console.print(Panel.fit(
        "[bold cyan]Real Options Data Backtest[/bold cyan]\n"
        "Using REAL Alpaca options data (no synthetic)\n"
        "Period: 2024-02-01 to 2024-11-30",
        border_style="cyan"
    ))

    # Load configuration
    settings = load_config()

    # Backtest parameters - MUST be Feb 2024 or later for real options data
    symbol = "QQQ"
    start_dt = datetime(2024, 2, 1)
    end_dt = datetime(2024, 11, 30)  # Recent data
    initial_capital = 5000.0

    settings.backtesting.initial_capital = initial_capital

    console.print(f"\n[dim]Initial Capital: ${initial_capital:,.2f}[/dim]")
    console.print(f"[dim]Period: {start_dt.date()} to {end_dt.date()} (10 months)[/dim]")
    console.print(f"[dim]Symbol: {symbol}[/dim]")

    # Check for Alpaca credentials (REQUIRED for real options data)
    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if not api_key or not api_secret:
        console.print("[red]ERROR: Alpaca credentials required for real options data![/red]")
        console.print("[yellow]Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables[/yellow]")
        return

    console.print("[green]✓ Alpaca credentials found - using REAL options data[/green]")

    # Initialize Alpaca options data fetcher
    fetcher = AlpacaOptionsDataFetcher(
        api_key=api_key,
        api_secret=api_secret,
    )

    console.print("\n[bold]Loading Real Data from Alpaca...[/bold]")

    # Fetch real underlying data
    with console.status("[cyan]Fetching underlying price data..."):
        underlying_data = fetcher.fetch_underlying_bars(
            symbol=symbol,
            start_date=start_dt,
            end_date=end_dt,
            timeframe="1Hour",
        )

    if underlying_data.empty:
        console.print("[red]Failed to load underlying data![/red]")
        return

    console.print(f"[green]✓ Loaded {len(underlying_data):,} underlying price bars[/green]")

    # Show price range
    price_min = underlying_data['close'].min()
    price_max = underlying_data['close'].max()
    price_start = underlying_data['close'].iloc[0]
    price_end = underlying_data['close'].iloc[-1]

    console.print(f"[dim]Price Range: ${price_min:.2f} - ${price_max:.2f}[/dim]")
    console.print(f"[dim]Start Price: ${price_start:.2f} -> End Price: ${price_end:.2f} ({((price_end/price_start)-1)*100:+.1f}%)[/dim]")

    # Add technical indicators
    with console.status("[cyan]Computing technical indicators..."):
        from alpaca_options.backtesting.data_loader import BacktestDataLoader
        data_loader = BacktestDataLoader(settings.backtesting.data)
        underlying_data = data_loader.add_technical_indicators(underlying_data)

    console.print("[green]✓ Technical indicators computed (RSI, SMA, ATR, HV)[/green]")

    # Fetch REAL options chains from Alpaca
    console.print("\n[bold yellow]Fetching REAL Options Chains from Alpaca...[/bold yellow]")
    console.print("[dim]This may take a few minutes as we fetch historical option data...[/dim]")

    options_data = {}

    with console.status("[cyan]Fetching options chains (this will take time)...") as status:
        # Fetch chains for each timestamp in underlying data
        # For performance, fetch at daily intervals
        daily_timestamps = underlying_data.resample('1D').last().dropna().index

        total = len(daily_timestamps)
        for i, timestamp in enumerate(daily_timestamps):
            status.update(f"[cyan]Fetching chain {i+1}/{total} ({timestamp.date()})...")

            chain = fetcher.fetch_option_chain(
                underlying=symbol,
                as_of_date=timestamp,
            )

            if chain:
                options_data[timestamp] = chain
                console.print(f"[dim]  {timestamp.date()}: {len(chain.contracts)} contracts[/dim]")
            else:
                console.print(f"[yellow]  {timestamp.date()}: No data (may be cached or unavailable)[/yellow]")

            # Throttle API calls
            if i < total - 1:
                await asyncio.sleep(0.5)  # Rate limiting

    if not options_data:
        console.print("[red]ERROR: No real options data available for this period![/red]")
        console.print("[yellow]Try a more recent date range or check Alpaca data availability[/yellow]")
        return

    console.print(f"\n[green]✓ Loaded {len(options_data):,} REAL options chain snapshots[/green]")

    # Create strategy instance
    strategy = VerticalSpreadStrategy()

    # Configure strategy
    strat_config = settings.strategies.get("vertical_spread")
    if strat_config:
        strategy._config = strat_config.config.copy()
    else:
        strategy._config = {}

    strategy._config["underlyings"] = [symbol]

    # Use real IV rank since we have real data
    strategy._config["min_iv_rank"] = 30  # Standard IV rank filter
    strategy._config["min_dte"] = 21
    strategy._config["max_dte"] = 45
    strategy._config["close_dte"] = 14

    # CRITICAL FIX: Alpaca historical snapshots have zero open interest
    # Disable OI filter for historical backtesting
    strategy._config["min_open_interest"] = 0  # Historical data doesn't have OI

    # CRITICAL FIX: Relax bid-ask spread requirement for historical data
    # Real options can have wider spreads than live trading
    strategy._config["max_spread_percent"] = 15.0  # Allow up to 15% spread

    # CRITICAL FIX: Lower return on risk threshold for real market data
    # Real spreads typically offer 10-12% ROR, not 15%+
    strategy._config["min_return_on_risk"] = 0.10  # 10% minimum (was 0.25/0.33)

    # Adjust spread width for real options (strike spacing is ~$1, not $5)
    strategy._config["spread_width"] = 5.0  # Dollar amount, not strike count

    # CRITICAL: Initialize strategy with config to apply settings
    await strategy.initialize(strategy._config)

    console.print(f"\n[bold]Strategy Configuration:[/bold]")
    console.print(f"[dim]  Delta Target: {strategy._config.get('delta_target', 0.20)}[/dim]")
    console.print(f"[dim]  Min IV Rank: {strategy._config.get('min_iv_rank', 30)}[/dim]")
    console.print(f"[dim]  RSI Oversold: {strategy._config.get('rsi_oversold', 45)}[/dim]")
    console.print(f"[dim]  RSI Overbought: {strategy._config.get('rsi_overbought', 55)}[/dim]")
    console.print(f"[dim]  Min DTE: {strategy._config.get('min_dte', 21)}[/dim]")
    console.print(f"[dim]  Max DTE: {strategy._config.get('max_dte', 45)}[/dim]")

    console.print(f"\n[bold cyan]CRITICAL FIXES FOR REAL DATA:[/bold cyan]")
    console.print(f"[green]  Min Open Interest: {strategy._config.get('min_open_interest', 100)}[/green]")
    console.print(f"[green]  Max Spread %: {strategy._config.get('max_spread_percent', 5.0)}[/green]")
    console.print(f"[green]  Min Return on Risk: {strategy._config.get('min_return_on_risk', 0.25)*100:.1f}%[/green]")

    # Create backtest engine
    engine = BacktestEngine(settings.backtesting, settings.risk)

    # Run backtest
    console.print("\n[bold]Running Backtest with REAL Options Data...[/bold]")

    with console.status("[cyan]Processing trades..."):
        result = await engine.run(
            strategy=strategy,
            underlying_data=underlying_data,
            options_data=options_data,
            start_date=start_dt,
            end_date=end_dt,
        )

    # Display results
    console.print("\n")
    console.print(Panel.fit(
        "[bold green]BACKTEST COMPLETE[/bold green]",
        border_style="green"
    ))

    m = result.metrics

    # Performance Summary Table
    perf_table = Table(title="Performance Summary (REAL Data)", box=box.ROUNDED)
    perf_table.add_column("Metric", style="cyan", width=25)
    perf_table.add_column("Value", style="white", justify="right", width=15)

    perf_table.add_row("Starting Equity", f"${m.starting_equity:,.2f}")
    perf_table.add_row("Ending Equity", f"${m.ending_equity:,.2f}")
    perf_table.add_row("Total Return ($)", f"${m.total_return:,.2f}")
    perf_table.add_row("Total Return (%)", f"{m.total_return_percent:.2f}%")
    perf_table.add_row("[bold]Annualized Return[/bold]", f"[bold]{m.annualized_return:.2f}%[/bold]")

    console.print(perf_table)

    # Risk Metrics Table
    risk_table = Table(title="Risk Metrics", box=box.ROUNDED)
    risk_table.add_column("Metric", style="cyan", width=25)
    risk_table.add_column("Value", style="white", justify="right", width=15)

    risk_table.add_row("Max Drawdown ($)", f"${m.max_drawdown:,.2f}")
    risk_table.add_row("Max Drawdown (%)", f"{m.max_drawdown_percent:.2f}%")
    risk_table.add_row("Sharpe Ratio", f"{m.sharpe_ratio:.2f}")
    risk_table.add_row("Sortino Ratio", f"{m.sortino_ratio:.2f}")
    risk_table.add_row("Profit Factor", f"{m.profit_factor:.2f}" if m.profit_factor != float('inf') else "N/A")

    console.print(risk_table)

    # Trade Statistics Table
    trade_table = Table(title="Trade Statistics", box=box.ROUNDED)
    trade_table.add_column("Metric", style="cyan", width=25)
    trade_table.add_column("Value", style="white", justify="right", width=15)

    trade_table.add_row("Total Trades", str(m.total_trades))
    trade_table.add_row("Winning Trades", str(m.winning_trades))
    trade_table.add_row("Losing Trades", str(m.losing_trades))
    trade_table.add_row("[bold]Win Rate[/bold]", f"[bold]{m.win_rate:.1f}%[/bold]")
    trade_table.add_row("Average Win", f"${m.avg_win:,.2f}")
    trade_table.add_row("Average Loss", f"${m.avg_loss:,.2f}")
    trade_table.add_row("Avg Holding Period", f"{m.avg_holding_period_days:.1f} days")
    trade_table.add_row("Total Commissions", f"${m.total_commissions:,.2f}")

    console.print(trade_table)

    # Trade History
    if hasattr(result, 'trades') and result.trades:
        console.print(f"\n[bold]Trade History (Last {min(10, len(result.trades))} Trades):[/bold]")

        trades_table = Table(box=box.SIMPLE)
        trades_table.add_column("Entry Date", style="dim")
        trades_table.add_column("Exit Date", style="dim")
        trades_table.add_column("Type", style="cyan")
        trades_table.add_column("P/L", justify="right")

        for trade in result.trades[-10:]:
            pnl = trade.pnl if hasattr(trade, 'pnl') else 0
            pnl_style = "green" if pnl >= 0 else "red"
            entry_date = trade.entry_time.strftime("%Y-%m-%d") if hasattr(trade, 'entry_time') and trade.entry_time else "N/A"
            exit_date = trade.exit_time.strftime("%Y-%m-%d") if hasattr(trade, 'exit_time') and trade.exit_time else "Open"
            trade_type = trade.signal_type.name if hasattr(trade, 'signal_type') else "spread"

            trades_table.add_row(
                entry_date,
                exit_date,
                trade_type,
                f"[{pnl_style}]${pnl:+,.2f}[/{pnl_style}]",
            )

        console.print(trades_table)

    # Data Source Info
    console.print("\n[bold green]Data Sources:[/bold green]")
    console.print(f"[green]  ✓ Underlying Data: Alpaca API (REAL)[/green]")
    console.print(f"[green]  ✓ Options Data: Alpaca API (REAL - Feb 2024+)[/green]")
    console.print(f"[green]  ✓ Greeks: From Alpaca snapshots (REAL)[/green]")
    console.print(f"[green]  ✓ Implied Volatility: From Alpaca snapshots (REAL)[/green]")

    console.print("\n[bold cyan]Key Insights:[/bold cyan]")
    console.print(f"[cyan]  • This backtest uses 100% REAL market data from Alpaca[/cyan]")
    console.print(f"[cyan]  • Results should be more accurate than synthetic backtests[/cyan]")
    console.print(f"[cyan]  • Still expect 10-20% slippage in live trading vs backtest[/cyan]")

    console.print("\n[dim]Backtest with real options data completed successfully.[/dim]")

    return result


if __name__ == "__main__":
    asyncio.run(run_real_options_backtest())
