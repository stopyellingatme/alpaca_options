#!/usr/bin/env python3
"""Analyze real options chains to find why no trades were generated."""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from alpaca_options.backtesting.alpaca_options_fetcher import AlpacaOptionsDataFetcher

def main():
    """Analyze sample options chains from real Alpaca data."""
    print("=== Analyzing Real Options Chains ===\n")

    # Check for Alpaca credentials
    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if not api_key or not api_secret:
        print("ERROR: Alpaca credentials required!")
        return

    # Initialize fetcher
    fetcher = AlpacaOptionsDataFetcher(
        api_key=api_key,
        api_secret=api_secret,
    )

    # Fetch a single chain to analyze
    test_date = datetime(2024, 3, 15)  # Mid-backtest period
    symbol = "QQQ"

    print(f"Fetching options chain for {symbol} on {test_date.date()}...")
    chain = fetcher.fetch_option_chain(
        underlying=symbol,
        as_of_date=test_date,
    )

    if not chain or not chain.contracts:
        print("ERROR: No options chain data!")
        return

    print(f"✓ Loaded chain with {len(chain.contracts)} contracts\n")

    # Analyze contracts
    puts = [c for c in chain.contracts if c.option_type.lower() == "put"]
    calls = [c for c in chain.contracts if c.option_type.lower() == "call"]

    print(f"Breakdown:")
    print(f"  Puts: {len(puts)}")
    print(f"  Calls: {len(calls)}")

    # Analyze DTE distribution
    from collections import Counter
    dte_counts = Counter(c.days_to_expiry for c in chain.contracts)

    print(f"\n=== DTE Distribution ===")
    print(f"Unique DTE values: {sorted(dte_counts.keys())}")
    print(f"\nDTE histogram:")
    for dte in sorted(dte_counts.keys()):
        count = dte_counts[dte]
        bar = "█" * (count // 100)
        print(f"  {dte:3d} DTE: {count:4d} contracts {bar}")

    # Check for 21-45 DTE range (strategy requirement)
    dte_21_45 = [c for c in chain.contracts if 21 <= c.days_to_expiry <= 45]
    print(f"\nContracts in 21-45 DTE range: {len(dte_21_45)}")

    if len(dte_21_45) == 0:
        print("  ⚠️  NO contracts in 21-45 DTE range! This explains zero trades.")
        print("\n  Strategy requires 21-45 DTE, but no contracts meet this criteria.")
        print("  Recommendation: Adjust DTE range or use different data source.")
        return

    # Analyze delta distribution for 21-45 DTE puts
    puts_21_45 = [c for c in dte_21_45 if c.option_type.lower() == "put"]
    calls_21_45 = [c for c in dte_21_45 if c.option_type.lower() == "call"]

    print(f"\nBreakdown of 21-45 DTE contracts:")
    print(f"  Puts: {len(puts_21_45)}")
    print(f"  Calls: {len(calls_21_45)}")

    # Check delta values
    puts_with_delta = [c for c in puts_21_45 if c.delta is not None]
    calls_with_delta = [c for c in calls_21_45 if c.delta is not None]

    print(f"\nContracts with Greeks data:")
    print(f"  Puts with delta: {len(puts_with_delta)}")
    print(f"  Calls with delta: {len(calls_with_delta)}")

    if len(puts_with_delta) == 0:
        print("\n  ⚠️  NO puts with Greeks data in 21-45 DTE range!")
        print("  This explains why no trades were generated.")
        print("\n  Possible causes:")
        print("    1. Alpaca may not provide Greeks for historical snapshots")
        print("    2. Greeks might need to be calculated separately")
        print("    3. Data fetcher might not be populating Greeks correctly")
        return

    # Analyze delta distribution
    print(f"\n=== Delta Distribution for 21-45 DTE Puts ===")
    put_deltas = sorted([abs(c.delta) for c in puts_with_delta])

    print(f"Delta Stats:")
    print(f"  Min: {min(put_deltas):.3f}")
    print(f"  Max: {max(put_deltas):.3f}")
    print(f"  Mean: {sum(put_deltas)/len(put_deltas):.3f}")

    # Find ~20 delta puts (0.15 to 0.25 range)
    target_delta_puts = [c for c in puts_with_delta if 0.15 <= abs(c.delta) <= 0.25]
    print(f"\nPuts with 15-25 delta (target range): {len(target_delta_puts)}")

    if len(target_delta_puts) == 0:
        print("  ⚠️  NO puts with target delta range!")
        return

    # Show sample contracts
    print(f"\nSample 20-delta puts:")
    for c in sorted(target_delta_puts, key=lambda x: abs(x.delta))[:5]:
        print(f"  {c.strike:7.2f} strike, {abs(c.delta):.3f} delta, {c.days_to_expiry} DTE, bid/ask: {c.bid:.2f}/{c.ask:.2f}")

    # Check if we can build a 5-strike wide spread
    print(f"\n=== Spread Building Analysis ===")
    strikes = sorted(set(c.strike for c in target_delta_puts))
    print(f"Available strikes in target delta range: {strikes[:10]}...")

    if len(strikes) >= 2:
        # Check if 5-strike spreads are possible
        strike_diffs = [strikes[i+1] - strikes[i] for i in range(len(strikes)-1)]
        print(f"Strike spacing: {set(strike_diffs)}")

        if 5.0 in strike_diffs:
            print("  ✓ 5-strike spreads are possible!")
        else:
            print("  ⚠️  No 5-strike spacing found. Closest spacing:", min(strike_diffs))
            print("  Recommendation: Adjust spread_width configuration")

    # Check liquidity
    print(f"\n=== Liquidity Analysis ===")
    for c in target_delta_puts[:5]:
        if c.bid and c.ask:
            spread_pct = ((c.ask - c.bid) / ((c.bid + c.ask) / 2)) * 100 if c.bid + c.ask > 0 else 0
            print(f"  Strike {c.strike:.2f}: bid={c.bid:.2f}, ask={c.ask:.2f}, spread={spread_pct:.1f}%, OI={c.open_interest or 0}")

    print("\n=== Analysis Complete ===")

if __name__ == "__main__":
    main()
