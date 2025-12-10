"""Test script to verify real Alpaca options data fetching.

This script diagnoses the Phase 1 data source issue by:
1. Loading Alpaca credentials from .env
2. Initializing data loader with credentials
3. Fetching a small sample of real options data
4. Analyzing data quality (bid-ask spreads, IV, liquidity)
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

from alpaca_options.backtesting.data_loader import BacktestDataLoader
from alpaca_options.core.config import load_config


def load_env_file(env_path: Path = Path(".env")):
    """Manually load .env file into environment variables."""
    if not env_path.exists():
        return

    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                # Remove quotes if present
                value = value.strip().strip('"').strip("'")
                os.environ[key.strip()] = value


def main():
    """Test real options data fetching."""
    print("=" * 80)
    print("PHASE 1 DIAGNOSTIC: Real vs Synthetic Options Data")
    print("=" * 80)

    # Load .env file into environment variables
    print("\n0. Loading .env file...")
    load_env_file()
    if os.environ.get("ALPACA_API_KEY"):
        print("   ✅ .env file loaded successfully")
    else:
        print("   ⚠️  No .env file found or no ALPACA_API_KEY in it")

    # Load config (will get credentials from .env via environment variables)
    print("\n1. Loading configuration...")
    config = load_config(Path("config/paper_trading.yaml"))

    # Check credentials
    api_key = config.alpaca.api_key
    api_secret = config.alpaca.api_secret

    if api_key and api_secret:
        print(f"   ✅ API Key found ({len(api_key)} chars)")
        print(f"   ✅ API Secret found ({len(api_secret)} chars)")
    else:
        print("   ❌ No credentials found!")
        print("   Please ensure .env file has ALPACA_API_KEY and ALPACA_SECRET_KEY")
        return

    # Initialize data loader WITH credentials
    print("\n2. Initializing BacktestDataLoader with credentials...")
    data_loader = BacktestDataLoader(
        config.backtesting.data,
        api_key=api_key,
        api_secret=api_secret,
    )

    # Check if AlpacaOptionsDataFetcher was initialized
    if data_loader._alpaca_fetcher is not None:
        print("   ✅ AlpacaOptionsDataFetcher successfully initialized!")
        print(f"   ✅ Cache directory: {data_loader._alpaca_fetcher._cache_dir}")
    else:
        print("   ❌ AlpacaOptionsDataFetcher NOT initialized")
        print("   This means real data cannot be fetched")
        return

    # Test fetching a small sample of underlying data
    print("\n3. Fetching sample underlying data (QQQ, 1 week)...")
    try:
        start_date = datetime(2024, 10, 1)
        end_date = datetime(2024, 10, 7)

        underlying_data = data_loader.load_underlying_data(
            symbol="QQQ",
            start_date=start_date,
            end_date=end_date,
            timeframe="1h",
        )

        print(f"   ✅ Fetched {len(underlying_data)} bars")
        print(f"   ✅ Date range: {underlying_data.index[0]} to {underlying_data.index[-1]}")
    except Exception as e:
        print(f"   ❌ Error fetching underlying data: {e}")
        return

    # Test fetching options data (hybrid: real + synthetic)
    print("\n4. Fetching options chains (hybrid: real Alpaca + synthetic fallback)...")
    try:
        options_data = data_loader.load_options_data_hybrid(
            underlying_data=underlying_data,
            symbol="QQQ",
            start_date=start_date,
            end_date=end_date,
        )

        print(f"   ✅ Total option chains: {len(options_data)}")

        # Count how many are from real Alpaca data
        # (This is approximate - chains from Feb 2024+ are likely real)
        real_count = sum(1 for ts in options_data.keys() if ts >= datetime(2024, 2, 1))
        synthetic_count = len(options_data) - real_count

        print(f"   ✅ Likely REAL chains: {real_count}")
        print(f"   ✅ Likely SYNTHETIC chains: {synthetic_count}")

        # Analyze one real chain in detail
        if options_data:
            sample_ts = list(options_data.keys())[0]
            sample_chain = options_data[sample_ts]

            print(f"\n5. Analyzing sample option chain ({sample_ts})...")
            print(f"   Underlying: {sample_chain.underlying}")
            print(f"   Underlying price: ${sample_chain.underlying_price:.2f}")
            print(f"   Total contracts: {len(sample_chain.contracts)}")

            # Analyze calls vs puts
            calls = [c for c in sample_chain.contracts if c.option_type == "call"]
            puts = [c for c in sample_chain.contracts if c.option_type == "put"]
            print(f"   Calls: {len(calls)}, Puts: {len(puts)}")

            # Sample a few contracts to check bid-ask spreads
            print(f"\n6. Sample contracts (checking bid-ask spreads)...")
            for i, contract in enumerate(sample_chain.contracts[:5]):
                spread = contract.ask - contract.bid if contract.ask and contract.bid else 0
                spread_pct = (spread / contract.mid_price * 100) if contract.mid_price > 0 else 0

                print(f"\n   Contract {i+1}: {contract.symbol}")
                print(f"     Type: {contract.option_type}, Strike: ${contract.strike}")
                print(f"     DTE: {contract.days_to_expiry}")
                print(f"     Bid: ${contract.bid:.2f}, Ask: ${contract.ask:.2f}")
                print(f"     Spread: ${spread:.2f} ({spread_pct:.1f}%)")
                print(f"     IV: {contract.implied_volatility:.1%}")
                print(f"     OI: {contract.open_interest}")
                print(f"     Delta: {contract.delta:.3f}, Theta: {contract.theta:.3f}")

        print("\n" + "=" * 80)
        print("DIAGNOSTIC COMPLETE")
        print("=" * 80)

        if real_count > 0:
            print("\n✅ SUCCESS: Real Alpaca options data is being fetched!")
            print("   Future backtests will use real market data for Feb 2024+")
        else:
            print("\n⚠️  WARNING: Only synthetic data was returned")
            print("   This might be because the date range is before Feb 2024")
            print("   Or there was an issue fetching real data")

    except Exception as e:
        print(f"\n❌ Error fetching options data: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
