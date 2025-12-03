#!/usr/bin/env python3
"""Comprehensive Backtest Script with Real Alpaca Underlying Data.

This script runs a detailed backtest using:
- Real historical underlying price data from Alpaca
- Synthetic options data with realistic bid-ask spreads (for pre-Feb 2024)
- Full metrics including trade-by-trade analysis

Usage:
    uv run python scripts/comprehensive_backtest.py
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


async def run_comprehensive_backtest():
    """Run comprehensive backtest with detailed output."""
    from alpaca_options.backtesting import BacktestDataLoader, BacktestEngine
    from alpaca_options.core.config import load_config
    from alpaca_options.strategies import VerticalSpreadStrategy

    console.print(Panel.fit(
        "[bold cyan]Comprehensive Backtest[/bold cyan]\n"
        "Vertical Spread Strategy on QQQ\n"
        "Period: 2022-01-01 to 2023-12-31",
        border_style="cyan"
    ))

    # Load configuration
    settings = load_config()

    # Backtest parameters
    symbol = "QQQ"
    start_dt = datetime(2022, 1, 1)
    end_dt = datetime(2023, 12, 31)
    initial_capital = 5000.0

    settings.backtesting.initial_capital = initial_capital

    console.print(f"\n[dim]Initial Capital: ${initial_capital:,.2f}[/dim]")
    console.print(f"[dim]Period: {start_dt.date()} to {end_dt.date()} (2 years)[/dim]")
    console.print(f"[dim]Symbol: {symbol}[/dim]")

    # Check for Alpaca credentials
    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if api_key and api_secret:
        console.print("[green]Alpaca credentials found - fetching real underlying data[/green]")
    else:
        console.print("[yellow]No Alpaca credentials - using generated data[/yellow]")

    # Initialize data loader with Alpaca credentials
    data_loader = BacktestDataLoader(
        settings.backtesting.data,
        api_key=api_key,
        api_secret=api_secret,
    )

    # Load underlying data (will use Alpaca if credentials available)
    console.print("\n[bold]Loading Data...[/bold]")

    with console.status("[cyan]Fetching underlying price data from Alpaca..."):
        underlying_data = data_loader.load_underlying_data(
            symbol, start_dt, end_dt, "1h"
        )

    if underlying_data.empty:
        console.print("[red]Failed to load underlying data![/red]")
        return

    console.print(f"[green]Loaded {len(underlying_data):,} price bars[/green]")

    # Show price range
    price_min = underlying_data['close'].min()
    price_max = underlying_data['close'].max()
    price_start = underlying_data['close'].iloc[0]
    price_end = underlying_data['close'].iloc[-1]

    console.print(f"[dim]Price Range: ${price_min:.2f} - ${price_max:.2f}[/dim]")
    console.print(f"[dim]Start Price: ${price_start:.2f} -> End Price: ${price_end:.2f} ({((price_end/price_start)-1)*100:+.1f}%)[/dim]")

    # Add technical indicators
    with console.status("[cyan]Computing technical indicators..."):
        underlying_data = data_loader.add_technical_indicators(underlying_data)

    console.print("[green]Technical indicators computed (RSI, SMA, ATR, HV)[/green]")

    # Generate synthetic options data with realistic spreads
    # Note: For 2022-2023, Alpaca doesn't have historical options data
    # so we use synthetic data based on real underlying prices
    with console.status("[cyan]Generating synthetic options chains (realistic spreads)..."):
        # Use historical volatility from the data for more realistic IV
        avg_hv = underlying_data['hv_20'].dropna().mean()
        base_iv = max(0.20, min(0.50, avg_hv if avg_hv > 0 else 0.25))

        console.print(f"[dim]Using base IV: {base_iv*100:.1f}% (from historical volatility)[/dim]")

        options_data = data_loader.generate_synthetic_options_data(
            underlying_data,
            symbol,
            risk_free_rate=0.04,  # Approximate 2022-2023 rates
            dividend_yield=0.005,  # QQQ dividend yield
            base_iv=base_iv,
        )

    console.print(f"[green]Generated {len(options_data):,} options chain snapshots[/green]")

    # Create strategy instance
    strategy = VerticalSpreadStrategy()

    # Configure strategy from settings
    strat_config = settings.strategies.get("vertical_spread")
    if strat_config:
        strategy._config = strat_config.config.copy()
    else:
        strategy._config = {}

    strategy._config["underlyings"] = [symbol]

    # Override IV rank filter for backtesting (synthetic data doesn't have real IV rank)
    # but keep all other improved parameters
    strategy._config["min_iv_rank"] = 0  # Disable IV rank filter for synthetic data
    strategy._config["min_dte"] = 21  # Allow 21+ DTE for more opportunities
    strategy._config["close_dte"] = 14  # Close at 14 DTE

    console.print(f"\n[bold]Strategy Configuration:[/bold]")
    console.print(f"[dim]  Delta Target: {strategy._config.get('delta_target', 0.20)}[/dim]")
    console.print(f"[dim]  RSI Oversold: {strategy._config.get('rsi_oversold', 45)}[/dim]")
    console.print(f"[dim]  RSI Overbought: {strategy._config.get('rsi_overbought', 55)}[/dim]")
    console.print(f"[dim]  Min DTE: {strategy._config.get('min_dte', 21)}[/dim]")
    console.print(f"[dim]  Max DTE: {strategy._config.get('max_dte', 45)}[/dim]")
    console.print(f"[dim]  Close DTE: {strategy._config.get('close_dte', 14)}[/dim]")
    console.print(f"[dim]  Spread Width: {strategy._config.get('spread_width', 5)} strikes[/dim]")
    console.print(f"[dim]  Min Return on Risk: {strategy._config.get('min_return_on_risk', 0.25) * 100:.0f}%[/dim]")
    console.print(f"[dim]  Profit Target: {strategy._config.get('profit_target_pct', 0.50) * 100:.0f}%[/dim]")
    console.print(f"[dim]  Stop Loss: {strategy._config.get('stop_loss_multiplier', 2.0)}x credit[/dim]")

    # Create backtest engine
    engine = BacktestEngine(settings.backtesting, settings.risk)

    # Run backtest
    console.print("\n[bold]Running Backtest...[/bold]")

    with console.status("[cyan]Processing trades..."):
        result = await engine.run(
            strategy=strategy,
            underlying_data=underlying_data,
            options_data=options_data,
            start_date=start_dt,
            end_date=end_dt,
        )

    # Display comprehensive results
    console.print("\n")
    console.print(Panel.fit(
        "[bold green]BACKTEST COMPLETE[/bold green]",
        border_style="green"
    ))

    m = result.metrics

    # Performance Summary Table
    perf_table = Table(title="Performance Summary", box=box.ROUNDED)
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
    risk_table.add_row("Profit Factor", f"{m.profit_factor:.2f}" if m.profit_factor != float('inf') else "N/A (no losses)")

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

    # Trade-by-Trade Analysis (if trades available)
    if hasattr(result, 'trades') and result.trades:
        console.print("\n[bold]Trade History (Last 10 Trades):[/bold]")

        trades_table = Table(box=box.SIMPLE)
        trades_table.add_column("Entry Date", style="dim")
        trades_table.add_column("Exit Date", style="dim")
        trades_table.add_column("Type", style="cyan")
        trades_table.add_column("P/L", justify="right")

        for trade in result.trades[-10:]:
            # BacktestTrade is a dataclass, access attributes directly
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

    # Equity Curve Summary
    if hasattr(result, 'equity_curve') and len(result.equity_curve) > 0:
        console.print("\n[bold]Equity Curve Summary:[/bold]")
        eq = result.equity_curve
        console.print(f"[dim]  Data Points: {len(eq)}[/dim]")
        try:
            # Handle both numeric and string equity curves
            eq_values = [float(v) for v in eq]
            console.print(f"[dim]  Peak Equity: ${max(eq_values):,.2f}[/dim]")
            console.print(f"[dim]  Trough Equity: ${min(eq_values):,.2f}[/dim]")
        except (ValueError, TypeError):
            console.print(f"[dim]  (Equity curve data available)[/dim]")

    # Data Source Info
    console.print("\n[bold]Data Sources:[/bold]")
    console.print(f"[dim]  Underlying Data: {'Alpaca API (real)' if api_key else 'Synthetic'}[/dim]")
    console.print(f"[dim]  Options Data: Synthetic (Black-Scholes with realistic spreads)[/dim]")
    console.print(f"[dim]  Note: Alpaca options data only available from Feb 2024[/dim]")

    # Key Insights
    console.print("\n[bold yellow]Key Insights:[/bold yellow]")

    if m.win_rate == 100.0:
        console.print("[yellow]  - 100% win rate suggests synthetic data may be too favorable[/yellow]")
        console.print("[yellow]  - Real trading will have losing trades due to gap risk, early assignment[/yellow]")

    if m.annualized_return > 30:
        console.print(f"[yellow]  - {m.annualized_return:.0f}% annualized return is exceptionally high[/yellow]")
        console.print("[yellow]  - Expect 10-30% lower returns in live trading due to slippage/fills[/yellow]")

    if m.max_drawdown_percent < 10:
        console.print(f"[yellow]  - {m.max_drawdown_percent:.1f}% max drawdown may be understated[/yellow]")
        console.print("[yellow]  - Real drawdowns could be 2-3x higher in volatile markets[/yellow]")

    console.print("\n[dim]Backtest completed successfully.[/dim]")

    return result


if __name__ == "__main__":
    asyncio.run(run_comprehensive_backtest())
