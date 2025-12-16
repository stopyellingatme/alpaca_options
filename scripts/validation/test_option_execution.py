#!/usr/bin/env python3
"""Test OPTION trade execution in paper trading account.

This script tests the ability to BUY and SELL OPTIONS (not stocks):
1. Connects to Alpaca paper trading API
2. Finds a liquid SPY option contract (put, ~30-45 DTE)
3. Places a MARKET BUY order for 1 OPTIONS CONTRACT
4. Waits for fill
5. Places a MARKET SELL order to close the OPTIONS position
6. Verifies the round-trip execution

IMPORTANT: This tests OPTION orders only. No stock orders are placed.

Run during market hours (9:30 AM - 4:00 PM ET) for full test.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta, date
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def get_alpaca_clients():
    """Initialize Alpaca trading and options data clients."""
    from alpaca.trading.client import TradingClient
    from alpaca.data.historical import OptionHistoricalDataClient

    api_key = os.environ.get("ALPACA_API_KEY")
    api_secret = os.environ.get("ALPACA_SECRET_KEY")

    if not api_key or not api_secret:
        console.print("[red]ERROR: API credentials not found in environment[/red]")
        console.print("[yellow]Please ensure .env file contains credentials[/yellow]")
        sys.exit(1)

    trading_client = TradingClient(api_key, api_secret, paper=True)
    options_client = OptionHistoricalDataClient(api_key, api_secret)

    return trading_client, options_client


def find_test_option_contract(options_client):
    """Find a liquid SPY option for testing.

    Returns an OPTION CONTRACT SYMBOL (e.g., 'SPY250117P00450000'), NOT a stock symbol.
    """
    from alpaca.data.requests import OptionChainRequest

    console.print("\n[cyan]1. Finding liquid SPY OPTION contract...[/cyan]")
    console.print("[dim]   (This will be an OPTION symbol like 'SPY250117P00450000', not 'SPY')[/dim]")

    try:
        # Get option chain for SPY
        target_exp_min = date.today() + timedelta(days=30)
        target_exp_max = date.today() + timedelta(days=45)

        request = OptionChainRequest(
            underlying_symbol="SPY",
            expiration_date_gte=target_exp_min,
            expiration_date_lte=target_exp_max,
        )

        console.print(f"[dim]   Fetching option chain for SPY (exp {target_exp_min} to {target_exp_max})...[/dim]")
        chains = options_client.get_option_chain(request)

        if not chains or not hasattr(chains, 'data') or not chains.data:
            console.print("[red]✗ No option chain data returned[/red]")
            console.print("[yellow]   This is expected outside market hours (9:30 AM - 4:00 PM ET)[/yellow]")
            return None

        # Filter for puts with reasonable properties
        candidates = []
        for contract_symbol, contract_data in chains.data.items():
            # IMPORTANT: Verify this is an OPTION symbol (contains expiration date and strike)
            if len(contract_symbol) < 15:  # Option symbols are typically 21 characters
                console.print(f"[yellow]⚠ Skipping invalid option symbol: {contract_symbol}[/yellow]")
                continue

            if contract_data.type.lower() == 'put':
                # Look for contracts with reasonable bid/ask
                if (hasattr(contract_data, 'latest_quote') and
                    contract_data.latest_quote and
                    contract_data.latest_quote.bid_price > 0.50 and
                    contract_data.latest_quote.ask_price < 10.00):

                    spread = contract_data.latest_quote.ask_price - contract_data.latest_quote.bid_price
                    spread_pct = spread / contract_data.latest_quote.ask_price

                    # Only consider contracts with tight spreads (< 20%)
                    if spread_pct < 0.20:
                        candidates.append({
                            'symbol': contract_symbol,
                            'type': contract_data.type,
                            'strike': contract_data.strike_price,
                            'expiration': contract_data.expiration_date,
                            'bid': contract_data.latest_quote.bid_price,
                            'ask': contract_data.latest_quote.ask_price,
                            'spread': spread,
                            'spread_pct': spread_pct * 100,
                        })

        if not candidates:
            console.print("[yellow]⚠ No suitable OPTION contracts found[/yellow]")
            console.print("[dim]   Try running during market hours for live option data[/dim]")
            return None

        # Sort by tightest spread
        candidates.sort(key=lambda x: x['spread_pct'])
        best = candidates[0]

        console.print(f"[green]✓ Found test OPTION contract: {best['symbol']}[/green]")
        console.print(f"[green]  Type: {best['type'].upper()} (this is an OPTION, not stock)[/green]")
        console.print(f"  Strike: ${best['strike']:.2f}")
        console.print(f"  Expiration: {best['expiration']}")
        console.print(f"  Bid/Ask: ${best['bid']:.2f} / ${best['ask']:.2f}")
        console.print(f"  Spread: ${best['spread']:.2f} ({best['spread_pct']:.1f}%)")

        return best

    except Exception as e:
        console.print(f"[red]✗ Error finding option: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return None


def place_option_buy_order(trading_client, contract_symbol, mid_price):
    """Place a MARKET BUY order for 1 OPTION CONTRACT.

    Args:
        contract_symbol: OPTION symbol (e.g., 'SPY250117P00450000')
        mid_price: Reference price for display (not used in market order)
    """
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    console.print(f"\n[cyan]2. Placing MARKET BUY order for OPTION {contract_symbol}...[/cyan]")
    console.print("[yellow]   NOTE: This is an OPTION order, NOT a stock order[/yellow]")

    try:
        # Use MARKET order for guaranteed fill
        order_request = MarketOrderRequest(
            symbol=contract_symbol,
            qty=1,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
        )

        order = trading_client.submit_order(order_request)

        console.print(f"[green]✓ OPTION order submitted: {order.id}[/green]")
        console.print(f"  Status: {order.status}")
        console.print(f"  Type: MARKET BUY for 1 OPTION contract")
        console.print(f"  Symbol: {contract_symbol}")
        console.print(f"  Expected price: ~${mid_price:.2f}")

        return order

    except Exception as e:
        console.print(f"[red]✗ Failed to place OPTION order: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return None


def wait_for_fill(trading_client, order_id, timeout_seconds=60):
    """Wait for OPTION order to fill or timeout."""
    console.print(f"\n[cyan]3. Waiting for OPTION order fill (timeout: {timeout_seconds}s)...[/cyan]")

    import time
    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        try:
            order = trading_client.get_order_by_id(order_id)

            if order.status == 'filled':
                console.print(f"[green]✓ OPTION order filled![/green]")
                console.print(f"  Filled qty: {order.filled_qty} OPTIONS contract(s)")
                console.print(f"  Filled price: ${order.filled_avg_price:.2f}")
                return order

            elif order.status in ['canceled', 'expired', 'rejected']:
                console.print(f"[red]✗ OPTION order {order.status}[/red]")
                return None

            # Still pending
            console.print(f"  Status: {order.status}... ", end='\r')
            time.sleep(2)

        except Exception as e:
            console.print(f"[red]✗ Error checking order: {e}[/red]")
            return None

    console.print(f"\n[yellow]⚠ OPTION order did not fill within {timeout_seconds}s[/yellow]")
    return None


def place_option_sell_order(trading_client, contract_symbol, mid_price):
    """Place a MARKET SELL order to close the OPTION position.

    Args:
        contract_symbol: OPTION symbol (e.g., 'SPY250117P00450000')
        mid_price: Reference price for display (not used in market order)
    """
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce

    console.print(f"\n[cyan]4. Placing MARKET SELL order to close OPTION position...[/cyan]")
    console.print("[yellow]   NOTE: This SELLS the option contract (not stock)[/yellow]")

    try:
        # Use MARKET order for guaranteed fill
        order_request = MarketOrderRequest(
            symbol=contract_symbol,
            qty=1,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )

        order = trading_client.submit_order(order_request)

        console.print(f"[green]✓ OPTION sell order submitted: {order.id}[/green]")
        console.print(f"  Status: {order.status}")
        console.print(f"  Type: MARKET SELL for 1 OPTION contract")
        console.print(f"  Symbol: {contract_symbol}")
        console.print(f"  Expected price: ~${mid_price:.2f}")

        return order

    except Exception as e:
        console.print(f"[red]✗ Failed to place OPTION sell order: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return None


def cleanup_open_orders(trading_client):
    """Cancel any open orders from this test."""
    console.print("\n[cyan]Cleaning up open orders...[/cyan]")

    try:
        from alpaca.trading.requests import GetOrdersRequest
        from alpaca.trading.enums import QueryOrderStatus

        request = GetOrdersRequest(
            status=QueryOrderStatus.OPEN,
            limit=100,
        )

        open_orders = trading_client.get_orders(request)

        if open_orders:
            console.print(f"  Found {len(open_orders)} open orders")
            for order in open_orders:
                console.print(f"  Canceling order {order.id} ({order.symbol})...")
                trading_client.cancel_order_by_id(order.id)
            console.print("[green]✓ Cleanup complete[/green]")
        else:
            console.print("  No open orders to clean up")

    except Exception as e:
        console.print(f"[yellow]⚠ Cleanup error (non-critical): {e}[/yellow]")


def main():
    """Run OPTION execution test."""
    console.print(Panel.fit(
        "[bold green]OPTION Trade Execution Test[/bold green]\n"
        "Testing BUY → FILL → SELL round-trip for OPTIONS (not stocks)",
        border_style="green"
    ))

    # Initialize clients
    console.print("\n[cyan]0. Connecting to Alpaca API...[/cyan]")
    trading_client, options_client = get_alpaca_clients()
    console.print("[green]✓ Connected to Alpaca API[/green]")

    # Find test option
    test_option = find_test_option_contract(options_client)

    if not test_option:
        console.print("\n[red]Cannot proceed without a test OPTION contract[/red]")
        console.print("[yellow]Try running during market hours (9:30 AM - 4:00 PM ET)[/yellow]")
        return 1

    # Calculate mid price for reference
    mid_price = (test_option['bid'] + test_option['ask']) / 2

    # Place OPTION buy order (MARKET order for guaranteed fill)
    buy_order = place_option_buy_order(
        trading_client,
        test_option['symbol'],
        mid_price
    )

    if not buy_order:
        console.print("\n[red]Failed to place OPTION buy order[/red]")
        return 1

    # Wait for fill
    filled_order = wait_for_fill(trading_client, buy_order.id)

    if not filled_order:
        console.print("\n[yellow]OPTION buy order did not fill - canceling...[/yellow]")
        try:
            trading_client.cancel_order_by_id(buy_order.id)
            console.print("[green]✓ Order canceled[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠ Cancel error: {e}[/yellow]")
        return 1

    # Place OPTION sell order (MARKET order for guaranteed fill)
    sell_order = place_option_sell_order(
        trading_client,
        test_option['symbol'],
        mid_price
    )

    if not sell_order:
        console.print("\n[red]Failed to place OPTION sell order[/red]")
        console.print("[yellow]⚠ You may have an open OPTION position in paper account[/yellow]")
        console.print(f"[yellow]   Symbol: {test_option['symbol']}[/yellow]")
        return 1

    # Wait for sell to fill
    sold_order = wait_for_fill(trading_client, sell_order.id, timeout_seconds=60)

    if not sold_order:
        console.print("\n[yellow]OPTION sell order did not fill - check paper account[/yellow]")
        cleanup_open_orders(trading_client)
        return 1

    # Success!
    pnl = (sold_order.filled_avg_price - filled_order.filled_avg_price) * 100
    console.print("\n" + "="*60)
    console.print(Panel.fit(
        "[bold green]✓ TEST PASSED[/bold green]\n\n"
        "OPTION trade execution validated:\n"
        f"  • Contract: {test_option['symbol']}\n"
        f"  • Type: {test_option['type'].upper()} OPTION\n"
        f"  • BUY filled at: ${filled_order.filled_avg_price:.2f}\n"
        f"  • SELL filled at: ${sold_order.filled_avg_price:.2f}\n"
        f"  • Round-trip P/L: ${pnl:.2f}\n\n"
        "[dim]This was an OPTIONS trade (1 contract), not a stock trade[/dim]",
        border_style="green"
    ))

    console.print("\n[bold cyan]Next Steps:[/bold cyan]")
    console.print("  1. OPTIONS execution is working correctly")
    console.print("  2. Ready to deploy OPTION strategies to paper trading")
    console.print("  3. Run: uv run python scripts/run_paper_trading.py --dashboard")

    return 0


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
