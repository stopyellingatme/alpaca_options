#!/usr/bin/env python3
"""Run backtests across different capital tiers.

This script simulates how different capital levels would perform
with appropriate strategies for each tier:
- Low Capital ($5,000): Vertical Spreads only
- Medium Capital ($25,000): Vertical Spreads + Iron Condors
- High Capital ($75,000): All strategies including Wheel

Uses real Alpaca options data when available.
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
from alpaca_options.core.config import load_config, BacktestConfig, BacktestExecutionConfig, BacktestDataConfig
from alpaca_options.core.capital_manager import CapitalManager, recommend_strategies_for_capital
from alpaca_options.strategies import (
    IronCondorStrategy,
    VerticalSpreadStrategy,
    WheelStrategy,
)

console = Console()


# Capital tier configurations
CAPITAL_TIERS = {
    "low": {
        "capital": 5000,
        "description": "Low Capital - Vertical Spreads Only",
        "strategies": [
            ("Vertical_Spread", VerticalSpreadStrategy, "QQQ"),
        ],
    },
    "medium": {
        "capital": 25000,
        "description": "Medium Capital - Spreads + Iron Condors",
        "strategies": [
            ("Vertical_Spread", VerticalSpreadStrategy, "QQQ"),
            ("Iron_Condor", IronCondorStrategy, "SPY"),
        ],
    },
    "high": {
        "capital": 75000,
        "description": "High Capital - Full Strategy Suite",
        "strategies": [
            ("Vertical_Spread", VerticalSpreadStrategy, "QQQ"),
            ("Iron_Condor", IronCondorStrategy, "SPY"),
            ("Wheel", WheelStrategy, "AAPL"),
        ],
    },
}


async def run_single_backtest(
    strategy_name: str,
    strategy_class,
    symbol: str,
    settings,
    start_date: datetime,
    end_date: datetime,
    initial_capital: float,
):
    """Run a single backtest and return results."""
    console.print(f"  [dim]Running {strategy_name} on {symbol}...[/dim]")

    # Create strategy instance
    strat = strategy_class()

    # Configure strategy
    strat_config = settings.strategies.get(strategy_name.lower().replace(" ", "_"))
    if strat_config:
        config = strat_config.config.copy()
    else:
        config = {}

    config["underlyings"] = [symbol]

    # Properly initialize the strategy with config
    await strat.initialize(config)

    # Load data with Alpaca credentials
    data_loader = BacktestDataLoader(
        settings.backtesting.data,
        api_key=os.environ.get("ALPACA_API_KEY"),
        api_secret=os.environ.get("ALPACA_SECRET_KEY"),
    )

    underlying_data = data_loader.load_underlying_data(
        symbol, start_date, end_date, "1h"
    )

    if underlying_data.empty:
        console.print(f"    [red]No data found for {symbol}[/red]")
        return None

    # Add technical indicators if not present
    if "rsi_14" not in underlying_data.columns:
        underlying_data = data_loader.add_technical_indicators(underlying_data)

    # Load hybrid options data
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

    # Create modified settings with the specific capital
    # Override the initial capital for this backtest
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

    return result


async def run_tier_backtest(
    tier_name: str,
    tier_config: dict,
    settings,
    start_date: datetime,
    end_date: datetime,
) -> dict:
    """Run all backtests for a single capital tier."""
    capital = tier_config["capital"]
    description = tier_config["description"]

    console.print(f"\n[bold cyan]{'='*60}[/bold cyan]")
    console.print(f"[bold cyan]{description}[/bold cyan]")
    console.print(f"[bold cyan]Starting Capital: ${capital:,.0f}[/bold cyan]")
    console.print(f"[bold cyan]{'='*60}[/bold cyan]")

    tier_results = {
        "tier": tier_name,
        "capital": capital,
        "description": description,
        "strategies": {},
        "total_return": 0.0,
        "total_return_percent": 0.0,
    }

    for strategy_name, strategy_class, symbol in tier_config["strategies"]:
        try:
            result = await run_single_backtest(
                strategy_name,
                strategy_class,
                symbol,
                settings,
                start_date,
                end_date,
                capital,
            )

            if result:
                tier_results["strategies"][f"{strategy_name} ({symbol})"] = result
                tier_results["total_return"] += result.metrics.total_return

        except Exception as e:
            console.print(f"    [red]Error in {strategy_name}: {e}[/red]")
            import traceback
            traceback.print_exc()

    # Calculate total return percent
    if capital > 0:
        tier_results["total_return_percent"] = (tier_results["total_return"] / capital) * 100

    return tier_results


def display_tier_comparison(all_results: dict):
    """Display comparison across all capital tiers."""
    console.print("\n\n")
    console.print(Panel.fit(
        "[bold green]CAPITAL TIER COMPARISON[/bold green]",
        border_style="green"
    ))

    # Summary table
    summary_table = Table(title="Performance by Capital Tier", show_header=True)
    summary_table.add_column("Tier", style="cyan", width=15)
    summary_table.add_column("Capital", justify="right", width=12)
    summary_table.add_column("Total Return", justify="right", width=15)
    summary_table.add_column("Return %", justify="right", width=12)
    summary_table.add_column("Strategies", width=30)

    for tier_name, results in all_results.items():
        strategies_str = ", ".join(results["strategies"].keys())
        return_style = "green" if results["total_return"] > 0 else "red"

        summary_table.add_row(
            tier_name.upper(),
            f"${results['capital']:,.0f}",
            f"[{return_style}]${results['total_return']:,.2f}[/{return_style}]",
            f"[{return_style}]{results['total_return_percent']:.1f}%[/{return_style}]",
            strategies_str[:30] + "..." if len(strategies_str) > 30 else strategies_str,
        )

    console.print(summary_table)

    # Detailed results per tier
    for tier_name, results in all_results.items():
        console.print(f"\n[bold]{results['description']}[/bold]")

        if not results["strategies"]:
            console.print("  [yellow]No strategies executed[/yellow]")
            continue

        detail_table = Table(show_header=True, show_lines=True)
        detail_table.add_column("Strategy", style="cyan")
        detail_table.add_column("Return $", justify="right")
        detail_table.add_column("Return %", justify="right")
        detail_table.add_column("Trades", justify="right")
        detail_table.add_column("Win Rate", justify="right")
        detail_table.add_column("Avg Win", justify="right")

        for strat_name, result in results["strategies"].items():
            if result:
                m = result.metrics
                return_style = "green" if m.total_return > 0 else "red"
                detail_table.add_row(
                    strat_name,
                    f"[{return_style}]${m.total_return:,.2f}[/{return_style}]",
                    f"[{return_style}]{m.total_return_percent:.1f}%[/{return_style}]",
                    str(m.total_trades),
                    f"{m.win_rate:.1f}%",
                    f"${m.avg_win:,.2f}",
                )

        console.print(detail_table)


def display_capital_recommendations():
    """Display capital recommendations for each tier."""
    console.print("\n")
    console.print(Panel.fit(
        "[bold blue]CAPITAL RECOMMENDATIONS[/bold blue]",
        border_style="blue"
    ))

    for tier_name, tier_config in CAPITAL_TIERS.items():
        capital = tier_config["capital"]
        manager = CapitalManager(capital)
        summary = manager.get_capital_summary()

        console.print(f"\n[bold]{tier_name.upper()} TIER (${capital:,})[/bold]")
        console.print(f"  Tier: {summary['tier'].upper()}")
        console.print(f"  {summary['tier_description']}")
        console.print(f"  Recommended Strategies: {', '.join(summary['recommended_strategies'])}")

        if summary["optimal_allocations"]:
            console.print("  Optimal Allocations:")
            for strat, alloc in summary["optimal_allocations"].items():
                dollar_amount = capital * (alloc / 100)
                console.print(f"    - {strat}: {alloc:.1f}% (${dollar_amount:,.0f})")


async def main():
    """Run backtests across all capital tiers."""
    console.print(Panel.fit(
        "[bold]Alpaca Options Bot - Capital Tier Backtesting[/bold]\n"
        "Comparing strategy performance across different capital levels",
        border_style="blue"
    ))

    # Check for Alpaca credentials
    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if api_key and api_secret:
        console.print("[green]Alpaca credentials found - will use real options data[/green]")
    else:
        console.print("[yellow]No Alpaca credentials - using synthetic data[/yellow]")

    # Load configuration
    settings = load_config(project_root / "config" / "default.yaml")

    # Backtest period - use recent data for best results
    start_date = datetime(2024, 2, 15)  # After Alpaca data availability
    end_date = datetime(2024, 11, 15)

    console.print(f"\n[bold]Backtest Period:[/bold] {start_date.date()} to {end_date.date()}")

    # Display capital recommendations
    display_capital_recommendations()

    # Run backtests for each tier
    all_results = {}

    for tier_name, tier_config in CAPITAL_TIERS.items():
        results = await run_tier_backtest(
            tier_name,
            tier_config,
            settings,
            start_date,
            end_date,
        )
        all_results[tier_name] = results

    # Display comparison
    display_tier_comparison(all_results)

    # Save results
    output_dir = project_root / "data" / "backtest_results" / f"capital_tiers_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)

    for tier_name, results in all_results.items():
        tier_dir = output_dir / tier_name
        tier_dir.mkdir(exist_ok=True)

        for strat_name, result in results["strategies"].items():
            if result:
                safe_name = strat_name.replace(" ", "_").replace("(", "").replace(")", "")
                result.save(tier_dir / safe_name)

    console.print(f"\n[green]Results saved to: {output_dir}[/green]")

    # Final recommendation
    console.print("\n")
    console.print(Panel.fit(
        "[bold]RECOMMENDATION[/bold]\n\n"
        "Based on the backtest results:\n"
        "- [cyan]$5,000 account[/cyan]: Focus on Vertical Spreads (QQQ/SPY)\n"
        "- [cyan]$25,000 account[/cyan]: Add Iron Condors for diversification\n"
        "- [cyan]$75,000+ account[/cyan]: Can include Wheel strategy on quality stocks\n\n"
        "Start conservative and scale up as your account grows!",
        border_style="green"
    ))


if __name__ == "__main__":
    asyncio.run(main())
