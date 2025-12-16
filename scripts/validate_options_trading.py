#!/usr/bin/env python3
"""
Validation script to verify options trading capabilities on Alpaca paper account.

Tests:
1. Account connectivity and status
2. Option contracts retrieval
3. Placing a simple option order
4. Retrieving open positions
5. Canceling/closing positions
"""

import asyncio
import os
from datetime import date, timedelta
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import OptionHistoricalDataClient

# Load environment variables
load_dotenv()

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")


def print_section(title: str):
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


async def validate_account_status():
    """Validate account connectivity and check if options trading is enabled."""
    print_section("1. Validating Account Status")

    try:
        trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
        account = trading_client.get_account()

        print(f"✅ Account Status: {account.status}")
        print(f"✅ Account ID: {account.id}")
        print(f"✅ Buying Power: ${float(account.buying_power):,.2f}")
        print(f"✅ Cash: ${float(account.cash):,.2f}")
        print(f"✅ Portfolio Value: ${float(account.portfolio_value):,.2f}")
        print(f"✅ Options Trading Approved: {account.options_approved_level if hasattr(account, 'options_approved_level') else 'N/A'}")

        return True
    except Exception as e:
        print(f"❌ Account validation failed: {e}")
        return False


async def validate_option_contracts():
    """Validate ability to retrieve option contracts."""
    print_section("2. Validating Option Contracts Retrieval")

    try:
        trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)

        # Try to get option contracts for SPY (most liquid)
        exp_date = date.today() + timedelta(days=30)

        # Search for SPY option contracts
        from alpaca.trading.requests import GetOptionContractsRequest

        request = GetOptionContractsRequest(
            underlying_symbols=["SPY"],
            expiration_date_gte=date.today(),
            expiration_date_lte=exp_date,
            limit=10
        )

        contracts_response = trading_client.get_option_contracts(request)

        # Access the option_contracts attribute from the response
        contracts = contracts_response.option_contracts if hasattr(contracts_response, 'option_contracts') else []

        if contracts:
            print(f"✅ Found {len(contracts)} SPY option contracts")
            print("\nSample contracts:")
            for i, contract in enumerate(contracts[:3], 1):
                print(f"  {i}. {contract.symbol}")
                print(f"     Strike: ${contract.strike_price}, Expiry: {contract.expiration_date}")
                print(f"     Type: {contract.type}, Status: {contract.status}")

            # Return a sample contract for testing
            return contracts[0] if contracts else None
        else:
            print("❌ No option contracts found")
            return None

    except Exception as e:
        print(f"❌ Option contracts retrieval failed: {e}")
        return None


async def validate_option_order_placement(contract_symbol: str):
    """Validate ability to place an option order."""
    print_section("3. Validating Option Order Placement")

    try:
        trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)

        # Place a simple market order to buy 1 contract
        order_request = MarketOrderRequest(
            symbol=contract_symbol,
            qty=1,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY
        )

        order = trading_client.submit_order(order_request)

        print(f"✅ Order placed successfully!")
        print(f"   Order ID: {order.id}")
        print(f"   Symbol: {order.symbol}")
        print(f"   Qty: {order.qty}")
        print(f"   Side: {order.side}")
        print(f"   Status: {order.status}")

        # Wait a moment for order to process
        await asyncio.sleep(2)

        # Check order status
        order_status = trading_client.get_order_by_id(order.id)
        print(f"   Updated Status: {order_status.status}")

        return order.id

    except Exception as e:
        print(f"❌ Option order placement failed: {e}")
        return None


async def validate_positions():
    """Validate ability to retrieve open positions."""
    print_section("4. Validating Positions Retrieval")

    try:
        trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
        positions = trading_client.get_all_positions()

        if positions:
            print(f"✅ Found {len(positions)} open position(s)")
            for pos in positions:
                print(f"\n   Symbol: {pos.symbol}")
                print(f"   Qty: {pos.qty}")
                print(f"   Avg Entry: ${float(pos.avg_entry_price):.2f}")
                print(f"   Current Price: ${float(pos.current_price):.2f}")
                print(f"   Market Value: ${float(pos.market_value):.2f}")
                print(f"   P&L: ${float(pos.unrealized_pl):.2f} ({float(pos.unrealized_plpc)*100:.2f}%)")
        else:
            print("ℹ️  No open positions")

        return True

    except Exception as e:
        print(f"❌ Positions retrieval failed: {e}")
        return False


async def validate_order_cancellation(order_id: str):
    """Validate ability to cancel orders."""
    print_section("5. Validating Order Cancellation")

    try:
        trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)

        # Try to cancel the order
        trading_client.cancel_order_by_id(order_id)
        print(f"✅ Order {order_id} canceled successfully")

        return True

    except Exception as e:
        print(f"❌ Order cancellation failed: {e}")
        return False


async def validate_position_closing():
    """Validate ability to close positions."""
    print_section("6. Validating Position Closing")

    try:
        trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
        positions = trading_client.get_all_positions()

        if positions:
            # Close the first position
            pos = positions[0]
            trading_client.close_position(pos.symbol)
            print(f"✅ Position {pos.symbol} closed successfully")
            return True
        else:
            print("ℹ️  No positions to close")
            return True

    except Exception as e:
        print(f"❌ Position closing failed: {e}")
        return False


async def main():
    """Run all validation tests."""
    print("\n" + "="*60)
    print("  ALPACA OPTIONS TRADING VALIDATION")
    print("="*60)

    results = []

    # Test 1: Account Status
    result = await validate_account_status()
    results.append(("Account Status", result))

    if not result:
        print("\n❌ Cannot proceed without valid account connection")
        return

    # Test 2: Option Contracts
    sample_contract = await validate_option_contracts()
    results.append(("Option Contracts", sample_contract is not None))

    if not sample_contract:
        print("\n❌ Cannot proceed without valid option contracts")
        return

    # Test 3: Order Placement
    order_id = await validate_option_order_placement(sample_contract.symbol)
    results.append(("Order Placement", order_id is not None))

    # Test 4: Positions Retrieval
    result = await validate_positions()
    results.append(("Positions Retrieval", result))

    # Test 5: Order Cancellation (if order was placed)
    if order_id:
        result = await validate_order_cancellation(order_id)
        results.append(("Order Cancellation", result))

    # Test 6: Position Closing (if positions exist)
    result = await validate_position_closing()
    results.append(("Position Closing", result))

    # Print Summary
    print_section("VALIDATION SUMMARY")

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")

    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{total} tests passed")
    print(f"{'='*60}\n")

    if passed == total:
        print("🎉 All options trading capabilities validated successfully!")
        return True
    else:
        print("⚠️  Some tests failed. Please review the output above.")
        return False


if __name__ == "__main__":
    asyncio.run(main())
