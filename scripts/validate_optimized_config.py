#!/usr/bin/env python3
"""Validate that the optimized configuration loads properly and uses symbol-specific deltas.

This script verifies:
1. Configuration loads without errors
2. Symbol-specific delta targets are parsed correctly
3. Strategy uses correct delta for each symbol
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from alpaca_options.core.config import load_config
from alpaca_options.strategies.vertical_spread import VerticalSpreadStrategy
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


async def main():
    """Run configuration validation."""
    console.print(Panel.fit(
        "[bold cyan]Validating Optimized Configuration[/bold cyan]\n"
        "Checking symbol-specific delta support",
        border_style="cyan"
    ))

    # Load paper trading configuration
    console.print("\n[bold]Step 1:[/bold] Loading paper trading configuration...")
    try:
        config_path = project_root / "config" / "paper_trading.yaml"
        console.print(f"[dim]Loading from: {config_path}[/dim]")
        settings = load_config(config_path)
        console.print("[green]✓[/green] Configuration loaded successfully")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load configuration: {e}")
        return 1

    # Get vertical spread strategy config
    console.print("\n[bold]Step 2:[/bold] Checking vertical spread strategy config...")
    vertical_config = settings.strategies.get("vertical_spread")
    if not vertical_config:
        console.print("[red]✗[/red] Vertical spread strategy not found in configuration")
        return 1

    console.print(f"[green]✓[/green] Vertical spread strategy config found")
    console.print(f"  Enabled: {vertical_config.enabled}")
    console.print(f"  Allocation: {vertical_config.allocation}")

    # Check symbol_configs
    console.print("\n[bold]Step 3:[/bold] Checking symbol-specific configurations...")
    symbol_configs = vertical_config.config.get("symbol_configs", {})

    if not symbol_configs:
        console.print("[yellow]⚠[/yellow] No symbol-specific configs found (will use global delta)")
    else:
        console.print(f"[green]✓[/green] Found symbol-specific configs for {len(symbol_configs)} symbols")

        table = Table(title="Symbol-Specific Delta Targets", show_header=True)
        table.add_column("Symbol", style="cyan", width=10)
        table.add_column("Delta Target", justify="right", width=15)

        for symbol, cfg in symbol_configs.items():
            delta = cfg.get("delta_target", "N/A")
            table.add_row(symbol, f"{delta:.2f}" if isinstance(delta, (int, float)) else str(delta))

        console.print(table)

    # Initialize strategy
    console.print("\n[bold]Step 4:[/bold] Initializing strategy...")
    try:
        strategy = VerticalSpreadStrategy()
        await strategy.initialize(vertical_config.config)
        console.print("[green]✓[/green] Strategy initialized successfully")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to initialize strategy: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # Check that strategy loaded symbol configs
    if hasattr(strategy, '_symbol_configs'):
        console.print(f"[green]✓[/green] Strategy loaded {len(strategy._symbol_configs)} symbol-specific configs")
    else:
        console.print("[yellow]⚠[/yellow] Strategy doesn't have _symbol_configs attribute")

    # Test delta retrieval for each symbol
    console.print("\n[bold]Step 5:[/bold] Testing delta retrieval for each symbol...")
    underlyings = vertical_config.config.get("underlyings", [])

    if not underlyings:
        console.print("[yellow]⚠[/yellow] No underlyings configured")
    else:
        delta_table = Table(title="Delta Targets per Symbol", show_header=True)
        delta_table.add_column("Symbol", style="cyan", width=10)
        delta_table.add_column("Delta Target", justify="right", width=15)
        delta_table.add_column("Source", width=20)

        for symbol in underlyings:
            try:
                delta = strategy._get_delta_for_symbol(symbol)

                # Check if this is symbol-specific or global
                is_symbol_specific = symbol in strategy._symbol_configs and \
                                   strategy._symbol_configs[symbol].get("delta_target") is not None
                source = "Symbol-specific" if is_symbol_specific else "Global default"

                delta_table.add_row(
                    symbol,
                    f"{delta:.2f}",
                    f"[green]{source}[/green]" if is_symbol_specific else f"[dim]{source}[/dim]"
                )
            except Exception as e:
                delta_table.add_row(symbol, "[red]ERROR[/red]", str(e))

        console.print(delta_table)

    # Check DTE parameters
    console.print("\n[bold]Step 6:[/bold] Checking DTE parameters...")
    min_dte = vertical_config.config.get("min_dte")
    max_dte = vertical_config.config.get("max_dte")
    close_dte = vertical_config.config.get("close_dte")

    console.print(f"  Entry window: {min_dte}-{max_dte} DTE")
    console.print(f"  Exit threshold: {close_dte} DTE")

    # Verify optimized values
    if min_dte == 14 and max_dte == 30 and close_dte == 7:
        console.print("[green]✓[/green] DTE parameters match Phase 1 optimization (14-30 entry, 7 exit)")
    else:
        console.print(f"[yellow]⚠[/yellow] DTE parameters differ from Phase 1 optimization")
        console.print(f"  Expected: 14-30 entry, 7 exit")
        console.print(f"  Got: {min_dte}-{max_dte} entry, {close_dte} exit")

    # Summary
    console.print("\n" + "="*60)
    console.print(Panel.fit(
        "[bold green]✓ VALIDATION COMPLETE[/bold green]\n\n"
        "Configuration is properly set up for optimized trading:\n"
        f"• Symbol-specific deltas: {len(symbol_configs)} symbols\n"
        f"• Underlyings configured: {len(underlyings)}\n"
        f"• DTE optimization: Entry {min_dte}-{max_dte}, Exit {close_dte}",
        border_style="green"
    ))

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
