#!/usr/bin/env python3
"""Test DoltHub fetcher with real database."""

import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from alpaca_options.backtesting.dolthub_options_fetcher import DoltHubOptionsDataFetcher

def main():
    """Test DoltHub fetcher."""
    print("=== Testing DoltHub Options Fetcher ===\n")

    # Initialize fetcher
    print("Initializing fetcher...")
    fetcher = DoltHubOptionsDataFetcher()
    print("✓ Fetcher initialized\n")

    # Test symbols
    symbols = ["SPY", "AAPL", "MSFT", "NVDA"]
    test_date = datetime(2024, 3, 15)

    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"Testing {symbol}")
        print(f"{'='*60}")

        # Get available dates
        print(f"\nChecking available dates for {symbol}...")
        dates = fetcher.get_available_dates(
            symbol,
            datetime(2024, 2, 1),
            datetime(2024, 11, 30)
        )

        if dates:
            print(f"✓ Found {len(dates)} dates with data")
            print(f"  First date: {dates[0].date()}")
            print(f"  Last date: {dates[-1].date()}")

            # Fetch a sample chain
            sample_date = dates[10] if len(dates) > 10 else dates[0]
            print(f"\nFetching option chain for {sample_date.date()}...")
            chain = fetcher.fetch_option_chain(symbol, sample_date)

            if chain:
                print(f"✓ Fetched chain with {len(chain.contracts)} contracts")

                # Show stats
                puts = [c for c in chain.contracts if c.option_type.upper() == "PUT"]
                calls = [c for c in chain.contracts if c.option_type.upper() == "CALL"]

                print(f"  Puts: {len(puts)}")
                print(f"  Calls: {len(calls)}")

                # Show expirations
                expirations = sorted(set(c.expiration.date() for c in chain.contracts))
                print(f"  Expirations: {len(expirations)}")
                print(f"  Next 3 expirations: {expirations[:3]}")

                # Show sample contract
                if puts:
                    sample = puts[0]
                    print(f"\n  Sample Put Contract:")
                    print(f"    Symbol: {sample.symbol}")
                    print(f"    Strike: ${sample.strike:.2f}")
                    print(f"    Bid/Ask: ${sample.bid:.2f} / ${sample.ask:.2f}")
                    print(f"    Delta: {sample.delta:.3f}" if sample.delta else "    Delta: None")
                    print(f"    IV: {sample.implied_volatility:.2%}" if sample.implied_volatility else "    IV: None")
                    print(f"    Volume: {sample.volume} (always 0 in DoltHub)")
                    print(f"    OI: {sample.open_interest} (always 0 in DoltHub)")

            else:
                print(f"✗ Failed to fetch chain for {sample_date.date()}")

        else:
            print(f"✗ No data found for {symbol}")

    print("\n" + "="*60)
    print("✓ DoltHub fetcher test complete!")
    print("="*60)


if __name__ == "__main__":
    main()
