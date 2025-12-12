"""Verify Alpaca paper trading account setup."""

import asyncio
import os
from datetime import datetime

from alpaca_options.core.config import load_config


async def verify_account() -> None:
    """Verify paper trading account is properly configured."""
    print("=" * 60)
    print("ALPACA PAPER TRADING ACCOUNT VERIFICATION")
    print("=" * 60)

    # Check environment variables
    print("\n[1/4] Checking environment variables...")
    api_key = os.getenv("ALPACA_API_KEY")
    secret_key = os.getenv("ALPACA_SECRET_KEY")

    if not api_key:
        print("❌ ALPACA_API_KEY not found in environment")
        print("   Please set it in your .env file")
        return
    else:
        print(f"✅ ALPACA_API_KEY found: {api_key[:8]}...")

    if not secret_key:
        print("❌ ALPACA_SECRET_KEY not found in environment")
        print("   Please set it in your .env file")
        return
    else:
        print(f"✅ ALPACA_SECRET_KEY found: {secret_key[:8]}...")

    # Load configuration
    print("\n[2/4] Loading configuration...")
    try:
        settings = load_config()
        if settings.alpaca.paper:
            print("✅ Paper trading mode: ENABLED")
        else:
            print("⚠️  Paper trading mode: DISABLED (this will use LIVE account!)")
            print("   Make sure to use --paper flag or set alpaca.paper: true in config")
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return

    # Test API connection
    print("\n[3/4] Testing Alpaca API connection...")
    try:
        from alpaca.trading.client import TradingClient

        client = TradingClient(api_key, secret_key, paper=True)
        account = client.get_account()

        print("✅ Successfully connected to Alpaca API!")
        print(f"\n📊 Account Information:")
        print(f"   Account ID: {account.id}")
        print(f"   Status: {account.status}")
        print(f"   Currency: {account.currency}")
        print(f"   Buying Power: ${float(account.buying_power):,.2f}")
        print(f"   Cash: ${float(account.cash):,.2f}")
        print(f"   Portfolio Value: ${float(account.portfolio_value):,.2f}")
        print(f"   Equity: ${float(account.equity):,.2f}")

        # Check if account has sufficient capital
        equity = float(account.equity)
        if equity < 2000:
            print(f"\n⚠️  Warning: Account equity (${equity:,.2f}) is below recommended minimum ($2,000)")
            print("   You can still test, but may have limited trading opportunities")
        elif equity < 5000:
            print(f"\n✅ Account equity (${equity:,.2f}) meets minimum requirement ($2,000)")
            print("   Recommended: $5,000 for optimal testing")
        else:
            print(f"\n✅ Account equity (${equity:,.2f}) is sufficient for paper trading!")

    except Exception as e:
        print(f"❌ Failed to connect to Alpaca API: {e}")
        print("\n   Troubleshooting:")
        print("   1. Verify your API keys are correct")
        print("   2. Make sure you're using PAPER trading keys (not live)")
        print("   3. Check https://status.alpaca.markets/ for API status")
        return

    # Check strategy configuration
    print("\n[4/4] Verifying strategy configuration...")
    if hasattr(settings, 'strategies') and hasattr(settings.strategies, 'vertical_spread'):
        vs_config = settings.strategies.vertical_spread
        if vs_config.enabled:
            print("✅ Vertical Spread strategy: ENABLED")
            print(f"   Underlyings: {vs_config.config.underlyings}")
            print(f"   Delta target: {vs_config.config.delta_target}")
            print(f"   Min DTE: {vs_config.config.min_dte}")
            print(f"   Max DTE: {vs_config.config.max_dte}")
            print(f"   Profit target: {vs_config.config.profit_target_pct * 100}%")
        else:
            print("❌ Vertical Spread strategy: DISABLED")
            print("   Enable it in your config file")
    else:
        print("⚠️  Could not find vertical_spread strategy configuration")

    print("\n" + "=" * 60)
    print("✅ VERIFICATION COMPLETE")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Review the account information above")
    print("2. If everything looks good, start paper trading with:")
    print("   uv run alpaca-options run --paper --strategy vertical_spread")
    print("\n3. Or run a dry-run first (signals only, no orders):")
    print("   uv run alpaca-options run --paper --dry-run --strategy vertical_spread")
    print()


if __name__ == "__main__":
    asyncio.run(verify_account())
