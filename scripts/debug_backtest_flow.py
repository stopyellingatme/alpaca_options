#!/usr/bin/env python3
"""Debug backtest flow to find where signals are being rejected.

This script traces the exact path a signal takes through the backtest engine
to identify why trades aren't being executed.
"""

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

import pandas as pd
from rich.console import Console
from rich.panel import Panel

from alpaca_options.backtesting import BacktestDataLoader
from alpaca_options.core.config import load_config, BacktestConfig
from alpaca_options.risk.manager import RiskManager
from alpaca_options.strategies import VerticalSpreadStrategy
from alpaca_options.strategies.base import MarketData

console = Console()


async def debug_backtest_flow():
    """Trace the exact flow of signals through the backtest engine."""
    console.print(Panel.fit(
        "[bold]Backtest Flow Debug[/bold]\n"
        "Tracing signal generation through risk checks",
        border_style="blue"
    ))

    # Load config
    settings = load_config(project_root / "config" / "default.yaml")

    # Create strategy with relaxed config
    strategy = VerticalSpreadStrategy()
    config = {
        "underlyings": ["QQQ"],
        "rsi_oversold": 45,
        "rsi_overbought": 55,
        "min_open_interest": 50,
        "max_spread_percent": 15.0,
        "min_credit": 10,
        "min_iv_rank": 0,
    }
    await strategy.initialize(config)

    console.print("\n[cyan]Strategy Config:[/cyan]")
    console.print(f"  RSI oversold: {strategy._rsi_oversold}")
    console.print(f"  RSI overbought: {strategy._rsi_overbought}")
    console.print(f"  Min OI: {strategy._min_open_interest}")
    console.print(f"  Max spread %: {strategy._max_spread_percent}")
    console.print(f"  Min credit: {strategy._min_credit}")

    # Load data
    data_loader = BacktestDataLoader(
        settings.backtesting.data,
        api_key=os.environ.get("ALPACA_API_KEY"),
        api_secret=os.environ.get("ALPACA_SECRET_KEY"),
    )

    start_date = datetime(2024, 10, 1)
    end_date = datetime(2024, 10, 31)

    console.print(f"\n[dim]Loading QQQ data for {start_date.date()} to {end_date.date()}...[/dim]")
    underlying_data = data_loader.load_underlying_data("QQQ", start_date, end_date, "1h")
    underlying_data = data_loader.add_technical_indicators(underlying_data)

    console.print(f"[dim]Loading options data...[/dim]")
    options_data = data_loader.load_options_data_hybrid(
        underlying_data=underlying_data,
        symbol="QQQ",
        start_date=start_date,
        end_date=end_date,
    )

    console.print(f"Loaded {len(underlying_data)} bars, {len(options_data)} option chains")

    # Setup risk manager like backtest engine does
    risk_manager = RiskManager(settings.risk)

    # Backtest state simulation
    initial_capital = 5000
    equity = initial_capital
    cash = initial_capital
    buying_power = initial_capital
    min_buying_power_reserve = settings.trading.min_buying_power_reserve
    max_concurrent = settings.trading.max_concurrent_positions

    console.print(f"\n[cyan]Backtest Settings:[/cyan]")
    console.print(f"  Initial capital: ${initial_capital:,.2f}")
    console.print(f"  Min BP reserve: {min_buying_power_reserve:.1%}")
    console.print(f"  Max concurrent positions: {max_concurrent}")

    console.print(f"\n[cyan]Risk Config:[/cyan]")
    console.print(f"  Min DTE: {settings.risk.min_days_to_expiry}")
    console.print(f"  Max DTE: {settings.risk.max_days_to_expiry}")
    console.print(f"  Max single position %: {settings.risk.max_single_position_percent}")
    console.print(f"  Daily loss limit: ${settings.risk.daily_loss_limit}")
    console.print(f"  Max portfolio delta: {settings.risk.max_portfolio_delta}")

    # Track stats
    stats = {
        "total_chains": 0,
        "no_market_data": 0,
        "no_direction": 0,
        "signal_generated": 0,
        "rejected_max_positions": 0,
        "rejected_buying_power": 0,
        "rejected_risk_manager": 0,
        "rejected_contract_not_found": 0,
        "trades_executed": 0,
    }

    risk_rejection_reasons = []
    open_positions = 0

    console.print("\n[bold]Processing Option Chains...[/bold]\n")

    for timestamp, chain in options_data.items():
        stats["total_chains"] += 1

        # Get market data
        try:
            idx = underlying_data.index.get_indexer([timestamp], method="ffill")[0]
            if idx < 0:
                stats["no_market_data"] += 1
                continue
            row = underlying_data.iloc[idx]
        except Exception:
            stats["no_market_data"] += 1
            continue

        # Create market data
        def safe_float(col):
            if col not in row:
                return None
            val = row[col]
            if pd.isna(val):
                return None
            return float(val)

        market_data = MarketData(
            symbol="QQQ",
            timestamp=timestamp,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row.get("volume", 0)),
            rsi_14=safe_float("rsi_14"),
            sma_20=safe_float("sma_20"),
            sma_50=safe_float("sma_50"),
        )

        # Update risk manager like backtest does
        risk_manager.update_account(
            equity=equity,
            buying_power=cash,
            daily_pnl=0.0,
        )

        # Pass to strategy
        await strategy.on_market_data(market_data)

        # Check direction
        direction = strategy._determine_direction("QQQ")
        if direction is None:
            stats["no_direction"] += 1
            continue

        # Get signal
        signal = await strategy.on_option_chain(chain)

        if signal is None:
            continue

        stats["signal_generated"] += 1

        # Now trace through backtest engine checks

        # Check 1: Max concurrent positions
        if open_positions >= max_concurrent:
            stats["rejected_max_positions"] += 1
            if stats["signal_generated"] <= 3:
                console.print(f"  [yellow]Signal #{stats['signal_generated']} rejected: max positions ({open_positions}/{max_concurrent})[/yellow]")
            continue

        # Check 2: Build contract map
        contracts = {}
        for leg in signal.legs:
            for contract in chain.contracts:
                if contract.symbol == leg.contract_symbol:
                    contracts[leg.contract_symbol] = contract
                    break

        if len(contracts) != len(signal.legs):
            stats["rejected_contract_not_found"] += 1
            if stats["signal_generated"] <= 3:
                console.print(f"  [yellow]Signal #{stats['signal_generated']} rejected: contracts not found in chain[/yellow]")
                console.print(f"    Looking for: {[leg.contract_symbol for leg in signal.legs]}")
                console.print(f"    Found: {list(contracts.keys())}")
            continue

        # Check 3: Calculate required buying power
        trade_risk = risk_manager._calculate_trade_risk(signal, contracts)
        min_reserve = equity * min_buying_power_reserve
        available_bp = buying_power - min_reserve

        if trade_risk > available_bp:
            stats["rejected_buying_power"] += 1
            if stats["signal_generated"] <= 3:
                console.print(f"  [yellow]Signal #{stats['signal_generated']} rejected: buying power[/yellow]")
                console.print(f"    Trade risk: ${trade_risk:.2f}")
                console.print(f"    Available BP: ${available_bp:.2f} (total: ${buying_power:.2f}, reserve: ${min_reserve:.2f})")
            continue

        # Check 4: Risk manager
        risk_check = risk_manager.check_signal_risk(signal, contracts)

        if not risk_check.passed:
            stats["rejected_risk_manager"] += 1
            risk_rejection_reasons.extend(risk_check.violations)
            if stats["signal_generated"] <= 5:
                console.print(f"  [yellow]Signal #{stats['signal_generated']} rejected by risk manager:[/yellow]")
                for violation in risk_check.violations:
                    console.print(f"    - {violation}")
            continue

        # Trade would execute!
        stats["trades_executed"] += 1
        console.print(f"  [green]Signal #{stats['signal_generated']} PASSED ALL CHECKS - Would execute![/green]")
        console.print(f"    Type: {signal.signal_type.value}")
        console.print(f"    Trade risk: ${trade_risk:.2f}")
        for leg in signal.legs:
            console.print(f"    Leg: {leg.side} {leg.contract_symbol}")

        # Simulate position opening
        open_positions += 1
        buying_power -= trade_risk

        if stats["trades_executed"] >= 5:
            console.print("\n  [dim](Stopping after 5 successful trades)[/dim]")
            break

    # Summary
    console.print("\n" + "=" * 60)
    console.print("[bold]FLOW ANALYSIS SUMMARY[/bold]")
    console.print("=" * 60)

    console.print(f"\nTotal option chains processed: {stats['total_chains']}")
    console.print(f"  - No market data: {stats['no_market_data']}")
    console.print(f"  - No direction (RSI): {stats['no_direction']}")
    console.print(f"  - Signals generated: {stats['signal_generated']}")

    if stats["signal_generated"] > 0:
        console.print(f"\nSignal rejection breakdown:")
        console.print(f"  - Max positions limit: {stats['rejected_max_positions']}")
        console.print(f"  - Contract not found: {stats['rejected_contract_not_found']}")
        console.print(f"  - Insufficient buying power: {stats['rejected_buying_power']}")
        console.print(f"  - Risk manager: {stats['rejected_risk_manager']}")
        console.print(f"  - [green]Trades executed: {stats['trades_executed']}[/green]")

    if risk_rejection_reasons:
        console.print(f"\n[yellow]Risk Manager Rejection Reasons:[/yellow]")
        # Count unique reasons
        from collections import Counter
        reason_counts = Counter(risk_rejection_reasons)
        for reason, count in reason_counts.most_common():
            console.print(f"  - {reason}: {count}x")


if __name__ == "__main__":
    asyncio.run(debug_backtest_flow())
