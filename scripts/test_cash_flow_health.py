#!/usr/bin/env python3
"""Test script for cash flow health analysis.

This script demonstrates the new cash flow health functionality in the SEC filings module.
"""

import sys
from alpaca_options.data.sec_filings import SECFilingsAnalyzer


def main():
    """Test cash flow health analysis on a few symbols."""
    # Initialize analyzer
    print("Initializing SEC filings analyzer...")
    analyzer = SECFilingsAnalyzer(cache_ttl_days=7)

    # Test symbols (mix of healthy and risky companies)
    test_symbols = ["AAPL", "MSFT"]  # Start with stable companies

    print("\nTesting cash flow health analysis:\n")
    print("=" * 80)

    for symbol in test_symbols:
        print(f"\n{symbol}:")
        print("-" * 40)

        # Get cash flow health
        cash_flow = analyzer.get_cash_flow_health(symbol)
        if cash_flow:
            print(f"  Bankruptcy Risk Score: {cash_flow.bankruptcy_risk_score:.1f}/10")
            print(f"  Negative OCF: {cash_flow.has_negative_ocf}")
            print(f"  Quarters Negative: {cash_flow.ocf_quarters_negative}")
            print(f"  High Debt (D/E > 2.0): {cash_flow.has_high_debt}")
            print(f"  Low Liquidity (CR < 1.0): {cash_flow.has_low_liquidity}")
            print(f"  Filing Date: {cash_flow.filing_date.date()}")

            # Check bankruptcy risk
            has_risk = analyzer.has_bankruptcy_risk(symbol, threshold=7.0)
            print(f"\n  Has Bankruptcy Risk (>= 7.0)? {has_risk}")
        else:
            print("  [No data available]")

    print("\n" + "=" * 80)
    print("\nTest completed successfully!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
