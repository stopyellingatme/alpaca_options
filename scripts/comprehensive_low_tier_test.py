#!/usr/bin/env python3
"""Comprehensive LOW tier backtest for deployment verification.

This script runs multiple backtests across different time periods
to ensure the vertical spread strategy is working correctly before
paper trading deployment.
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from alpaca_options.backtesting import BacktestDataLoader, BacktestEngine
from alpaca_options.core.config import load_config, BacktestConfig
from alpaca_options.strategies import VerticalSpreadStrategy

console = Console()


async def run_backtest(
    settings,
    start_date: datetime,
    end_date: datetime,
    initial_capital: float,
    symbol: str,
    config_overrides: dict = None,
) -> dict:
    """Run a single backtest and return results."""
    strat = VerticalSpreadStrategy()

    # Base config from settings
    strat_config = settings.strategies.get("vertical_spread")
    config = strat_config.config.copy() if strat_config else {}
    config["underlyings"] = [symbol]

    # Apply any overrides
    if config_overrides:
        config.update(config_overrides)

    await strat.initialize(config)

    # Load data
    data_loader = BacktestDataLoader(
        settings.backtesting.data,
        api_key=os.environ.get("ALPACA_API_KEY"),
        api_secret=os.environ.get("ALPACA_SECRET_KEY"),
    )

    underlying_data = data_loader.load_underlying_data(
        symbol, start_date, end_date, "1h"
    )

    if underlying_data.empty:
        return {"error": "No underlying data"}

    underlying_data = data_loader.add_technical_indicators(underlying_data)

    # Load options data
    if data_loader.has_alpaca_credentials:
        options_data = data_loader.load_options_data_hybrid(
            underlying_data=underlying_data,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )
    else:
        options_data = data_loader.generate_synthetic_options_data(
            underlying_data, symbol
        )

    # Create backtest config
    modified_backtesting = BacktestConfig(
        default_start_date=settings.backtesting.default_start_date,
        default_end_date=settings.backtesting.default_end_date,
        initial_capital=initial_capital,
        execution=settings.backtesting.execution,
        data=settings.backtesting.data,
    )

    # Run backtest
    engine = BacktestEngine(modified_backtesting, settings.risk, settings.trading)
    result = await engine.run(
        strategy=strat,
        underlying_data=underlying_data,
        options_data=options_data,
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "period": f"{start_date.date()} to {end_date.date()}",
        "symbol": symbol,
        "capital": initial_capital,
        "total_return": result.metrics.total_return,
        "return_pct": result.metrics.total_return_percent,
        "total_trades": result.metrics.total_trades,
        "win_rate": result.metrics.win_rate,
        "avg_win": result.metrics.avg_win,
        "avg_loss": result.metrics.avg_loss,
        "max_drawdown": result.metrics.max_drawdown,
        "max_drawdown_pct": result.metrics.max_drawdown_percent,
        "sharpe": result.metrics.sharpe_ratio,
        "profit_factor": result.metrics.profit_factor,
        "trades": result.trades,
    }


async def main():
    """Run comprehensive backtests for deployment verification."""
    console.print(Panel.fit(
        "[bold]LOW Tier Deployment Verification[/bold]\n"
        "Comprehensive backtests for Vertical Spread Strategy\n"
        "Target: Paper Trading Deployment",
        border_style="blue"
    ))

    # Check credentials
    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if not (api_key and api_secret):
        console.print("[red]Alpaca credentials not found![/red]")
        console.print("Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables")
        return

    console.print("[green]Alpaca credentials found[/green]\n")

    settings = load_config(project_root / "config" / "default.yaml")

    # Test parameters
    initial_capital = 5000  # LOW tier starting capital

    # Define test periods - multiple periods for robustness
    test_periods = [
        # Recent periods (2024)
        ("Q1 2024", datetime(2024, 1, 2), datetime(2024, 3, 31)),
        ("Q2 2024", datetime(2024, 4, 1), datetime(2024, 6, 30)),
        ("Q3 2024", datetime(2024, 7, 1), datetime(2024, 9, 30)),
        ("Oct-Nov 2024", datetime(2024, 10, 1), datetime(2024, 11, 15)),
        # Full year test
        ("Full 2024", datetime(2024, 1, 2), datetime(2024, 11, 15)),
    ]

    # Symbols to test
    symbols = ["QQQ", "SPY"]

    # Strategy configurations to test
    configs = {
        "Default": {},
        "Relaxed RSI": {
            "rsi_oversold": 45,
            "rsi_overbought": 55,
        },
        "Conservative": {
            "rsi_oversold": 35,
            "rsi_overbought": 65,
            "min_credit": 40,
        },
    }

    all_results = []

    # Run backtests
    console.print("[bold]Running Backtests...[/bold]\n")

    for config_name, config_overrides in configs.items():
        console.print(f"\n[cyan]Configuration: {config_name}[/cyan]")
        if config_overrides:
            for k, v in config_overrides.items():
                console.print(f"  {k}: {v}")

        for symbol in symbols:
            console.print(f"\n  [dim]Testing {symbol}...[/dim]")

            for period_name, start, end in test_periods:
                try:
                    result = await run_backtest(
                        settings,
                        start,
                        end,
                        initial_capital,
                        symbol,
                        config_overrides,
                    )
                    result["config"] = config_name
                    result["period_name"] = period_name
                    all_results.append(result)

                    status = "[green]OK[/green]" if result["total_trades"] > 0 else "[yellow]No trades[/yellow]"
                    console.print(
                        f"    {period_name}: {result['total_trades']} trades, "
                        f"${result['total_return']:.2f} ({result['return_pct']:.1f}%) {status}"
                    )
                except Exception as e:
                    console.print(f"    [red]{period_name}: Error - {e}[/red]")
                    all_results.append({
                        "config": config_name,
                        "period_name": period_name,
                        "symbol": symbol,
                        "error": str(e),
                    })

    # Summary Report
    console.print("\n" + "=" * 80)
    console.print("[bold]COMPREHENSIVE BACKTEST SUMMARY[/bold]")
    console.print("=" * 80)

    # Results table
    table = Table(title="Backtest Results by Configuration")
    table.add_column("Config", style="cyan")
    table.add_column("Symbol", style="white")
    table.add_column("Period", style="dim")
    table.add_column("Trades", justify="right")
    table.add_column("Return $", justify="right")
    table.add_column("Return %", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("Max DD %", justify="right")

    for r in all_results:
        if "error" in r:
            table.add_row(
                r["config"], r["symbol"], r["period_name"],
                "-", "-", "-", "-", f"[red]Error[/red]"
            )
        else:
            return_color = "green" if r["total_return"] >= 0 else "red"
            table.add_row(
                r["config"],
                r["symbol"],
                r["period_name"],
                str(r["total_trades"]),
                f"[{return_color}]${r['total_return']:,.2f}[/{return_color}]",
                f"[{return_color}]{r['return_pct']:.1f}%[/{return_color}]",
                f"{r['win_rate']:.0f}%",
                f"{r['max_drawdown_pct']:.1f}%",
            )

    console.print(table)

    # Aggregate statistics
    valid_results = [r for r in all_results if "error" not in r and r["total_trades"] > 0]

    if valid_results:
        console.print("\n[bold]Aggregate Statistics:[/bold]")

        total_trades = sum(r["total_trades"] for r in valid_results)
        avg_return = sum(r["return_pct"] for r in valid_results) / len(valid_results)
        avg_win_rate = sum(r["win_rate"] for r in valid_results) / len(valid_results)
        max_dd = max(r["max_drawdown_pct"] for r in valid_results)

        profitable = sum(1 for r in valid_results if r["total_return"] > 0)

        stats_table = Table(show_header=False)
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value", justify="right")

        stats_table.add_row("Total Backtests Run", str(len(all_results)))
        stats_table.add_row("Backtests with Trades", str(len(valid_results)))
        stats_table.add_row("Total Trades Across All", str(total_trades))
        stats_table.add_row("Average Return %", f"{avg_return:.2f}%")
        stats_table.add_row("Average Win Rate", f"{avg_win_rate:.1f}%")
        stats_table.add_row("Worst Max Drawdown", f"{max_dd:.1f}%")
        stats_table.add_row("Profitable Periods", f"{profitable}/{len(valid_results)}")

        console.print(stats_table)

        # Best configuration analysis
        console.print("\n[bold]Best Configuration Analysis:[/bold]")

        by_config = {}
        for r in valid_results:
            cfg = r["config"]
            if cfg not in by_config:
                by_config[cfg] = []
            by_config[cfg].append(r)

        for cfg, results in by_config.items():
            avg_ret = sum(r["return_pct"] for r in results) / len(results)
            avg_trades = sum(r["total_trades"] for r in results) / len(results)
            console.print(f"  {cfg}: Avg Return {avg_ret:.2f}%, Avg Trades {avg_trades:.1f}")

    # Deployment Readiness Check
    console.print("\n" + "=" * 80)
    console.print("[bold]DEPLOYMENT READINESS CHECK[/bold]")
    console.print("=" * 80)

    checks = []

    # Check 1: Trades are being generated
    if valid_results:
        checks.append(("[green]PASS[/green]", "Strategy generates trades"))
    else:
        checks.append(("[red]FAIL[/red]", "No trades generated in any period"))

    # Check 2: Win rate reasonable
    if valid_results:
        avg_wr = sum(r["win_rate"] for r in valid_results) / len(valid_results)
        if avg_wr >= 40:
            checks.append(("[green]PASS[/green]", f"Win rate acceptable ({avg_wr:.0f}%)"))
        else:
            checks.append(("[yellow]WARN[/yellow]", f"Low win rate ({avg_wr:.0f}%)"))

    # Check 3: Max drawdown acceptable
    if valid_results:
        max_dd = max(r["max_drawdown_pct"] for r in valid_results)
        if max_dd <= 25:
            checks.append(("[green]PASS[/green]", f"Max drawdown acceptable ({max_dd:.1f}%)"))
        elif max_dd <= 40:
            checks.append(("[yellow]WARN[/yellow]", f"High max drawdown ({max_dd:.1f}%)"))
        else:
            checks.append(("[red]FAIL[/red]", f"Excessive max drawdown ({max_dd:.1f}%)"))

    # Check 4: Positive average return
    if valid_results:
        avg_ret = sum(r["return_pct"] for r in valid_results) / len(valid_results)
        if avg_ret > 0:
            checks.append(("[green]PASS[/green]", f"Positive avg return ({avg_ret:.1f}%)"))
        else:
            checks.append(("[yellow]WARN[/yellow]", f"Negative avg return ({avg_ret:.1f}%)"))

    # Check 5: Multiple symbols tested
    symbols_tested = set(r["symbol"] for r in valid_results)
    if len(symbols_tested) >= 2:
        checks.append(("[green]PASS[/green]", f"Multiple symbols tested ({', '.join(symbols_tested)})"))
    else:
        checks.append(("[yellow]WARN[/yellow]", "Only one symbol tested"))

    # Display checks
    for status, message in checks:
        console.print(f"  {status} {message}")

    # Final recommendation
    failures = sum(1 for s, _ in checks if "FAIL" in s)
    warnings = sum(1 for s, _ in checks if "WARN" in s)

    console.print("\n[bold]Recommendation:[/bold]")
    if failures == 0 and warnings == 0:
        console.print("[bold green]READY FOR PAPER TRADING DEPLOYMENT[/bold green]")
    elif failures == 0:
        console.print("[bold yellow]PROCEED WITH CAUTION - Review warnings before deployment[/bold yellow]")
    else:
        console.print("[bold red]NOT READY - Address failures before deployment[/bold red]")

    # Configuration recommendation
    if by_config:
        best_cfg = max(by_config.items(), key=lambda x: sum(r["return_pct"] for r in x[1]) / len(x[1]))
        console.print(f"\n[bold]Recommended Configuration:[/bold] {best_cfg[0]}")


if __name__ == "__main__":
    asyncio.run(main())
