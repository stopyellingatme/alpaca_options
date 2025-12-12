#!/usr/bin/env python3
"""Test DoltHub hosted API connection."""

import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from alpaca_options.backtesting.dolthub_hosted_fetcher import DoltHubHostedOptionsDataFetcher

def main():
    """Test DoltHub API."""
    print("=== Testing DoltHub Hosted API ===\n")

    # Initialize fetcher
    print("Initializing fetcher...")
    fetcher = DoltHubHostedOptionsDataFetcher()
    print("✓ Fetcher initialized\n")

    # Test query for available dates
    print("Testing query for available dates...")
    symbol = "QQQ"
    start = datetime(2024, 3, 1)
    end = datetime(2024, 3, 31)

    dates = fetcher.get_available_dates(symbol, start, end)

    if dates:
        print(f"✓ Found {len(dates)} dates with data for {symbol}")
        print(f"  First date: {dates[0].date()}")
        print(f"  Last date: {dates[-1].date()}")
    else:
        print(f"✗ No dates found for {symbol}")
        return

    # Test fetching a chain
    print(f"\nTesting chain fetch for {dates[0].date()}...")
    chain = fetcher.fetch_option_chain(symbol, dates[0])

    if chain:
        print(f"✓ Fetched chain with {len(chain.contracts)} contracts")

        # Show some stats
        puts = [c for c in chain.contracts if c.option_type.lower() == "put"]
        calls = [c for c in chain.contracts if c.option_type.lower() == "call"]

        print(f"  Puts: {len(puts)}")
        print(f"  Calls: {len(calls)}")

        # Show expirations
        expirations = sorted(set(c.expiration.date() for c in chain.contracts))
        print(f"  Expirations: {len(expirations)}")
        print(f"  Next 3 expirations: {expirations[:3]}")

        # Show a sample contract
        if puts:
            sample = puts[0]
            print(f"\n  Sample Put Contract:")
            print(f"    Symbol: {sample.contract_symbol}")
            print(f"    Strike: ${sample.strike:.2f}")
            print(f"    Bid/Ask: ${sample.bid:.2f} / ${sample.ask:.2f}")
            print(f"    OI: {sample.open_interest}")
            print(f"    Delta: {sample.delta:.3f}" if sample.delta else "    Delta: None")
            print(f"    IV: {sample.implied_volatility:.2%}" if sample.implied_volatility else "    IV: None")

        print("\n✓ DoltHub hosted API is working!")

    else:
        print(f"✗ Failed to fetch chain")


if __name__ == "__main__":
    main()
