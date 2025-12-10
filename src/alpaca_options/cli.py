"""Command-line interface for the Alpaca Options Trading Bot."""

import asyncio
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="alpaca-options",
    help="Alpaca Options Trading Bot - Automated options trading with backtesting",
    add_completion=False,
)

console = Console()


@app.command()
def run(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
    paper: bool = typer.Option(
        True,
        "--paper/--live",
        help="Use paper trading (default) or live trading",
    ),
    strategy: Optional[list[str]] = typer.Option(
        None,
        "--strategy",
        "-s",
        help="Specific strategy to run (can be repeated)",
    ),
    capital: Optional[float] = typer.Option(
        None,
        "--capital",
        help="Maximum trading capital to use (overrides config)",
    ),
) -> None:
    """Start the trading bot."""
    from alpaca_options.core.config import load_config
    from alpaca_options.core.engine import TradingEngine
    from alpaca_options.ui.dashboard import TradingDashboard

    console.print("[bold green]Starting Alpaca Options Bot...[/bold green]")

    # Load configuration
    settings = load_config(config)
    settings.alpaca.paper = paper

    # Override max trading capital if provided
    if capital is not None:
        settings.trading.max_trading_capital = capital
        console.print(f"[yellow]Trading capital capped at ${capital:,.2f}[/yellow]")

    if strategy:
        # Enable only specified strategies
        for name in settings.strategies:
            settings.strategies[name].enabled = name in strategy

    # Create engine and dashboard
    engine = TradingEngine(settings)
    dashboard = TradingDashboard(engine, settings)

    # Run the bot
    try:
        asyncio.run(dashboard.run())
    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")


@app.command()
def backtest(
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
    strategy: str = typer.Option(
        ...,
        "--strategy",
        "-s",
        help="Strategy to backtest",
    ),
    symbol: str = typer.Option(
        "SPY",
        "--symbol",
        help="Underlying symbol for backtest",
    ),
    start_date: str = typer.Option(
        None,
        "--start",
        help="Start date (YYYY-MM-DD)",
    ),
    end_date: str = typer.Option(
        None,
        "--end",
        help="End date (YYYY-MM-DD)",
    ),
    capital: float = typer.Option(
        100000,
        "--capital",
        help="Initial capital",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for results",
    ),
    synthetic: bool = typer.Option(
        True,
        "--synthetic/--real",
        help="Use synthetic options data (default) or real data",
    ),
) -> None:
    """Run a backtest on historical data."""
    from datetime import datetime

    from rich.progress import Progress, SpinnerColumn, TextColumn
    from rich.table import Table

    from alpaca_options.backtesting import BacktestDataLoader, BacktestEngine
    from alpaca_options.core.config import load_config
    from alpaca_options.strategies import (
        DebitSpreadStrategy,
        IronCondorStrategy,
        VerticalSpreadStrategy,
        WheelStrategy,
    )

    console.print(f"[bold blue]Running backtest for {strategy}...[/bold blue]")

    settings = load_config(config)

    # Override backtest settings
    start = start_date or settings.backtesting.default_start_date
    end = end_date or settings.backtesting.default_end_date
    settings.backtesting.initial_capital = capital

    # Parse dates
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)

    console.print(f"[dim]Period: {start} to {end}[/dim]")
    console.print(f"[dim]Initial Capital: ${capital:,.2f}[/dim]")
    console.print(f"[dim]Symbol: {symbol}[/dim]")

    # Create strategy instance
    strategy_map = {
        "debit_spread": DebitSpreadStrategy,
        "wheel": WheelStrategy,
        "iron_condor": IronCondorStrategy,
        "vertical_spread": VerticalSpreadStrategy,
    }

    if strategy not in strategy_map:
        console.print(f"[red]Unknown strategy: {strategy}[/red]")
        console.print(f"Available: {', '.join(strategy_map.keys())}")
        raise typer.Exit(1)

    strat_class = strategy_map[strategy]
    strat_instance = strat_class()

    # Get strategy config
    strat_config = settings.strategies.get(strategy)
    if strat_config:
        strat_instance._config = strat_config.config
        strat_instance._config["underlyings"] = [symbol]
    else:
        strat_instance._config = {"underlyings": [symbol]}

    # Initialize data loader with Alpaca credentials for real options data
    # The fetcher will only initialize if credentials are available
    data_loader = BacktestDataLoader(
        settings.backtesting.data,
        api_key=settings.alpaca.api_key,
        api_secret=settings.alpaca.api_secret,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # Load underlying data
        progress.add_task("Loading underlying data...", total=None)
        underlying_data = data_loader.load_underlying_data(
            symbol, start_dt, end_dt, settings.backtesting.data.underlying_timeframe
        )

        if underlying_data.empty:
            console.print(
                f"[yellow]No underlying data found. Generating synthetic data...[/yellow]"
            )
            # Generate simple synthetic price data for demo
            import numpy as np
            import pandas as pd

            dates = pd.date_range(start=start_dt, end=end_dt, freq="1h")
            dates = dates[dates.dayofweek < 5]  # Weekdays only
            dates = dates[(dates.hour >= 9) & (dates.hour <= 16)]  # Market hours

            np.random.seed(42)
            returns = np.random.normal(0.0001, 0.01, len(dates))
            prices = 400 * np.exp(np.cumsum(returns))  # Start around $400

            underlying_data = pd.DataFrame(
                {
                    "open": prices * (1 + np.random.uniform(-0.002, 0.002, len(dates))),
                    "high": prices * (1 + np.random.uniform(0, 0.01, len(dates))),
                    "low": prices * (1 - np.random.uniform(0, 0.01, len(dates))),
                    "close": prices,
                    "volume": np.random.randint(1000000, 5000000, len(dates)),
                    "symbol": symbol,
                },
                index=dates,
            )

        # Add technical indicators
        underlying_data = data_loader.add_technical_indicators(underlying_data)

        # Load options data (synthetic generation removed - use only real data)
        progress.add_task("Loading options chains...", total=None)
        if synthetic:
            console.print(
                "[red]ERROR: Synthetic data generation has been removed.[/red]\n"
                "[yellow]Only real historical data is supported.[/yellow]\n"
                "[dim]Available data: AAPL, MSFT, NVDA, SPY (Feb-Nov 2024)[/dim]\n"
                "[dim]Use scripts/backtest_multi_symbol.py for real data backtests.[/dim]"
            )
            raise typer.Exit(code=1)

        options_data = data_loader.load_options_data(symbol, start_dt, end_dt)
        if not options_data:
            console.print(
                f"[red]ERROR: No real options data found for {symbol}[/red]\n"
                "[yellow]Synthetic data generation has been removed.[/yellow]\n"
                "[dim]Available symbols: AAPL, MSFT, NVDA, SPY (Feb-Nov 2024)[/dim]\n"
                "[dim]Use DoltHub or Alpaca data sources only.[/dim]"
            )
            raise typer.Exit(code=1)

        # Create backtest engine
        engine = BacktestEngine(settings.backtesting, settings.risk)

        # Run backtest
        progress.add_task("Running backtest...", total=None)
        result = asyncio.run(
            engine.run(
                strategy=strat_instance,
                underlying_data=underlying_data,
                options_data=options_data,
                start_date=start_dt,
                end_date=end_dt,
            )
        )

    # Display results
    console.print("\n[bold green]Backtest Complete![/bold green]\n")

    # Metrics table
    metrics_table = Table(title="Performance Metrics")
    metrics_table.add_column("Metric", style="cyan")
    metrics_table.add_column("Value", style="white")

    m = result.metrics
    metrics_table.add_row("Total Return", f"${m.total_return:,.2f}")
    metrics_table.add_row("Total Return %", f"{m.total_return_percent:.2f}%")
    metrics_table.add_row("Annualized Return", f"{m.annualized_return:.2f}%")
    metrics_table.add_row("Sharpe Ratio", f"{m.sharpe_ratio:.2f}")
    metrics_table.add_row("Sortino Ratio", f"{m.sortino_ratio:.2f}")
    metrics_table.add_row("Max Drawdown", f"${m.max_drawdown:,.2f}")
    metrics_table.add_row("Max Drawdown %", f"{m.max_drawdown_percent:.2f}%")
    metrics_table.add_row("Win Rate", f"{m.win_rate:.1f}%")
    metrics_table.add_row("Profit Factor", f"{m.profit_factor:.2f}")
    metrics_table.add_row("Total Trades", str(m.total_trades))
    metrics_table.add_row("Winning Trades", str(m.winning_trades))
    metrics_table.add_row("Losing Trades", str(m.losing_trades))
    metrics_table.add_row("Avg Win", f"${m.avg_win:,.2f}")
    metrics_table.add_row("Avg Loss", f"${m.avg_loss:,.2f}")
    metrics_table.add_row("Avg Holding Period", f"{m.avg_holding_period_days:.1f} days")
    metrics_table.add_row("Total Commissions", f"${m.total_commissions:,.2f}")
    metrics_table.add_row("Starting Equity", f"${m.starting_equity:,.2f}")
    metrics_table.add_row("Ending Equity", f"${m.ending_equity:,.2f}")

    console.print(metrics_table)

    # Save results if output specified
    if output:
        output_path = Path(output)
        result.save(output_path)
        console.print(f"\n[green]Results saved to {output_path}[/green]")


@app.command()
def strategies() -> None:
    """List all available strategies."""
    from rich.table import Table

    from alpaca_options.strategies import (
        DebitSpreadStrategy,
        IronCondorStrategy,
        VerticalSpreadStrategy,
        WheelStrategy,
    )
    from alpaca_options.strategies.registry import get_registry

    registry = get_registry()

    # Register built-in strategies
    for strat_class in [DebitSpreadStrategy, WheelStrategy, IronCondorStrategy, VerticalSpreadStrategy]:
        try:
            registry.register(strat_class)
        except ValueError:
            pass  # Already registered

    table = Table(title="Available Strategies")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Class", style="dim")

    for info in registry.get_strategy_info():
        table.add_row(info["name"], info["description"], info["class"])

    if not registry.list_strategies():
        console.print("[yellow]No strategies registered yet.[/yellow]")
    else:
        console.print(table)


@app.command()
def config(
    output: Path = typer.Option(
        Path("config/my_config.yaml"),
        "--output",
        "-o",
        help="Output path for configuration file",
    ),
) -> None:
    """Generate a sample configuration file."""
    import shutil

    default_config = Path(__file__).parent.parent.parent / "config" / "default.yaml"

    if default_config.exists():
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(default_config, output)
        console.print(f"[green]Configuration saved to {output}[/green]")
    else:
        console.print("[red]Default configuration file not found[/red]")


@app.command()
def status() -> None:
    """Check connection status and account info."""
    from alpaca_options.core.config import load_config

    settings = load_config()

    if not settings.alpaca.api_key:
        console.print("[red]API key not configured![/red]")
        console.print("Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables.")
        raise typer.Exit(1)

    console.print("[bold]Checking Alpaca connection...[/bold]")

    # TODO: Implement Alpaca connection check
    console.print(f"[dim]Paper Trading: {settings.alpaca.paper}[/dim]")
    console.print(f"[dim]Data Feed: {settings.alpaca.data_feed}[/dim]")


@app.command()
def version() -> None:
    """Show version information."""
    from alpaca_options import __version__

    console.print(f"[bold]Alpaca Options Bot[/bold] v{__version__}")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
