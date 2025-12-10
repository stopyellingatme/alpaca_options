#!/usr/bin/env python3
"""Deep debug to find exactly why no signals are generated."""

import asyncio
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
from alpaca_options.backtesting.data_loader import BacktestDataLoader
from alpaca_options.core.config import load_config
from alpaca_options.strategies import VerticalSpreadStrategy
from alpaca_options.strategies.base import MarketData

async def main():
    """Run deep debug."""
    print("=== DEEP DEBUG BACKTEST ===\n")

    settings = load_config()

    symbol = "QQQ"
    test_date = datetime(2024, 3, 15)  # Single day from earlier analysis
    start_date = datetime(2024, 3, 14)
    end_date = datetime(2024, 3, 16)

    api_key = os.environ.get("ALPACA_API_KEY", "")
    api_secret = os.environ.get("ALPACA_SECRET_KEY", "")

    if not api_key or not api_secret:
        print("ERROR: Alpaca credentials required!")
        return

    fetcher = AlpacaOptionsDataFetcher(api_key=api_key, api_secret=api_secret)

    # Fetch underlying data
    print(f"Fetching underlying data for {start_date.date()} to {end_date.date()}...")
    underlying_data = fetcher.fetch_underlying_bars(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        timeframe="1Hour",
    )

    if underlying_data.empty:
        print("ERROR: No underlying data!")
        return

    # Add technical indicators
    data_loader = BacktestDataLoader(settings.backtesting.data)
    underlying_data = data_loader.add_technical_indicators(underlying_data)

    # Get market data for test date (find closest to test_date)
    idx = underlying_data.index.get_indexer([test_date], method="nearest")[0]
    row = underlying_data.iloc[idx]
    actual_timestamp = underlying_data.index[idx]
    print(f"Using data from: {actual_timestamp}")
    market_data = MarketData(
        symbol=symbol,
        timestamp=actual_timestamp,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=int(row.get("volume", 0)),
        vwap=float(row.get("vwap")) if "vwap" in row and not pd.isna(row["vwap"]) else None,
        sma_20=float(row.get("sma_20")) if "sma_20" in row and not pd.isna(row["sma_20"]) else None,
        sma_50=float(row.get("sma_50")) if "sma_50" in row and not pd.isna(row["sma_50"]) else None,
        rsi_14=float(row.get("rsi_14")) if "rsi_14" in row and not pd.isna(row["rsi_14"]) else None,
        iv_rank=float(row.get("iv_rank")) if "iv_rank" in row and not pd.isna(row["iv_rank"]) else None,
    )

    print(f"\nMarket Data:")
    print(f"  Price: ${market_data.close:.2f}")
    print(f"  RSI: {market_data.rsi_14:.2f}" if market_data.rsi_14 else "  RSI: None")
    print(f"  IV Rank: {market_data.iv_rank:.2f}" if market_data.iv_rank else "  IV Rank: None")

    # Fetch options chain
    print(f"\nFetching options chain for {test_date.date()}...")
    chain = fetcher.fetch_option_chain(
        underlying=symbol,
        as_of_date=test_date,
    )

    if not chain or not chain.contracts:
        print("ERROR: No options chain!")
        return

    print(f"✓ Loaded {len(chain.contracts)} contracts")

    # Analyze contracts
    puts = [c for c in chain.contracts if c.option_type.lower() == "put"]
    calls = [c for c in chain.contracts if c.option_type.lower() == "call"]

    # Filter for 21-45 DTE
    puts_dte = [c for c in puts if 21 <= c.days_to_expiry <= 45]
    calls_dte = [c for c in calls if 21 <= c.days_to_expiry <= 45]

    print(f"\nDTE Filter (21-45):")
    print(f"  Puts: {len(puts_dte)}")
    print(f"  Calls: {len(calls_dte)}")

    # Filter for delta
    puts_delta = [c for c in puts_dte if c.delta is not None and 0.15 <= abs(c.delta) <= 0.25]
    calls_delta = [c for c in calls_dte if c.delta is not None and 0.15 <= abs(c.delta) <= 0.25]

    print(f"\nDelta Filter (15-25):")
    print(f"  Puts with target delta: {len(puts_delta)}")
    print(f"  Calls with target delta: {len(calls_delta)}")

    if len(puts_delta) == 0:
        print("\n⚠️  No puts with target delta!")
        return

    # Create strategy
    strategy = VerticalSpreadStrategy()
    strategy._config = {
        "underlyings": [symbol],
        "min_iv_rank": 30,
        "min_dte": 21,
        "max_dte": 45,
        "close_dte": 14,
        "min_open_interest": 0,  # FIX: Historical data
        "max_spread_percent": 15.0,  # FIX: Historical data
        "spread_width": 5.0,
        "min_credit": 20.0,
        "min_return_on_risk": 0.15,
        "delta_target": 0.20,
        "rsi_oversold": 45,
        "rsi_overbought": 55,
    }
    await strategy.initialize(strategy._config)

    # Pass market data to strategy
    print(f"\n=== Testing Strategy Logic ===")
    print(f"Passing market data to strategy...")
    await strategy.on_market_data(market_data)

    # Check if market data was cached
    if symbol in strategy._market_data:
        cached = strategy._market_data[symbol]
        print(f"✓ Market data cached")
        print(f"  RSI: {cached.rsi_14}")
        print(f"  IV Rank: {cached.iv_rank}")

        # Determine direction
        is_oversold = cached.rsi_14 is not None and cached.rsi_14 <= strategy._rsi_oversold
        is_overbought = cached.rsi_14 is not None and cached.rsi_14 >= strategy._rsi_overbought

        print(f"\nDirection Logic:")
        print(f"  RSI {cached.rsi_14:.2f} <= {strategy._rsi_oversold} (oversold/bullish): {is_oversold}")
        print(f"  RSI {cached.rsi_14:.2f} >= {strategy._rsi_overbought} (overbought/bearish): {is_overbought}")

        if is_oversold:
            print(f"  → BULLISH signal expected (Bull Put Spread)")
        elif is_overbought:
            print(f"  → BEARISH signal expected (Bear Call Spread)")
        else:
            print(f"  → NEUTRAL (no signal)")
    else:
        print("✗ Market data NOT cached!")

    # Now test signal generation
    print(f"\n=== Calling strategy.on_option_chain() ===")
    signal = await strategy.on_option_chain(chain)

    if signal:
        print(f"✓ SIGNAL GENERATED!")
        print(f"  Type: {signal.signal_type.name}")
        print(f"  Legs: {len(signal.legs)}")
        for leg in signal.legs:
            print(f"    - {leg.side} {leg.contract_symbol}")
    else:
        print(f"✗ NO SIGNAL GENERATED")
        print(f"\nLet me manually test the spread building logic...")

        # Manually test bull put spread building
        print(f"\n=== Manual Bull Put Spread Test ===")

        # Filter puts for 21-45 DTE with delta
        test_puts = [c for c in chain.contracts
                     if c.option_type.lower() == "put"
                     and 21 <= c.days_to_expiry <= 45
                     and c.delta is not None]

        print(f"Puts in DTE range with delta: {len(test_puts)}")

        # Try to find a 20-delta short put
        candidates = []
        for put in test_puts:
            delta_diff = abs(abs(put.delta) - 0.20)
            if delta_diff < 0.10:  # Within 10 delta
                candidates.append((put, delta_diff))

        candidates.sort(key=lambda x: x[1])

        if not candidates:
            print("✗ No puts near 20 delta")
        else:
            print(f"\nFound {len(candidates)} candidate short puts near 20 delta:")
            for put, diff in candidates[:5]:
                spread_pct = ((put.ask - put.bid) / ((put.bid + put.ask) / 2) * 100) if (put.bid + put.ask) > 0 else 999
                print(f"  Strike {put.strike:7.2f}: delta={abs(put.delta):.3f}, "
                      f"bid={put.bid:.2f}, ask={put.ask:.2f}, spread={spread_pct:.1f}%, "
                      f"OI={put.open_interest or 0}, DTE={put.days_to_expiry}")

            # Take best short put
            short_put = candidates[0][0]

            print(f"\n  Selected short put expiration: {short_put.expiration.date()}")

            # Try to find long put 5 strikes lower WITH SAME EXPIRATION
            target_long_strike = short_put.strike - 5.0
            long_candidates = []
            for put in test_puts:
                # CRITICAL: Must be same expiration!
                if put.expiration.date() != short_put.expiration.date():
                    continue
                strike_diff = abs(put.strike - target_long_strike)
                if strike_diff < 2.0:  # Within $2
                    long_candidates.append((put, strike_diff))

            long_candidates.sort(key=lambda x: x[1])

            if not long_candidates:
                print(f"\n✗ No long put found near ${target_long_strike:.2f}")
                print(f"  Available strikes: {sorted(set(p.strike for p in test_puts))[:20]}")
            else:
                long_put = long_candidates[0][0]
                print(f"\n✓ Found potential spread:")
                print(f"  Short: ${short_put.strike:.2f} put, {abs(short_put.delta):.3f} delta, bid/ask: {short_put.bid:.2f}/{short_put.ask:.2f}, exp: {short_put.expiration.date()}, DTE: {short_put.days_to_expiry}")
                print(f"  Long:  ${long_put.strike:.2f} put, {abs(long_put.delta):.3f} delta, bid/ask: {long_put.bid:.2f}/{long_put.ask:.2f}, exp: {long_put.expiration.date()}, DTE: {long_put.days_to_expiry}")

                # Calculate credit
                credit = (short_put.bid - long_put.ask) * 100
                spread_width = (short_put.strike - long_put.strike) * 100
                max_risk = spread_width - credit

                print(f"\n  Credit: ${credit:.2f}")
                print(f"  Spread Width: ${spread_width:.2f}")
                print(f"  Max Risk: ${max_risk:.2f}")
                print(f"  Return on Risk: {(credit / spread_width * 100):.1f}%")

                # Check filters
                print(f"\n  Filter Checks:")
                print(f"    Credit >= ${strategy._min_credit:.2f}: {credit >= strategy._min_credit}")
                print(f"    Return on Risk >= {strategy._min_return_on_risk*100:.1f}%: {(credit/spread_width) >= strategy._min_return_on_risk}")

                if credit < strategy._min_credit:
                    print(f"\n  ✗ REJECTED: Credit ${credit:.2f} < min ${strategy._min_credit:.2f}")
                elif (credit / spread_width) < strategy._min_return_on_risk:
                    print(f"\n  ✗ REJECTED: Return on risk {(credit/spread_width)*100:.1f}% < min {strategy._min_return_on_risk*100:.1f}%")
                else:
                    print(f"\n  ✓ PASSES all filters - should generate signal!")

    print("\n=== Debug Complete ===")

if __name__ == "__main__":
    import pandas as pd
    asyncio.run(main())
