"""Test script for enhanced screener functionality.

This script validates the Phase 1-3 enhancements:
1. New technical indicators (MACD, Bollinger Bands, Stochastic, ROC)
2. Consensus signal logic
3. Expanded symbol universe
4. Enhanced screening results

Tests run:
- Technical screener with consensus signals
- Comparison of RSI-only vs consensus signals
- Multiple symbols from expanded universe
- Display of all new indicator values
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alpaca_options.core.config import load_config
from alpaca_options.alpaca.client import AlpacaClient
from alpaca_options.screener.technical import TechnicalScreener
from alpaca_options.screener.base import ScreeningCriteria
from alpaca_options.screener.universes import (
    get_tier_1_symbols,
    get_tier_2_symbols,
    get_expanded_options,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def print_result_details(result, show_all_indicators=True):
    """Print detailed screener result including new indicators."""
    print(f"\n{'='*80}")
    print(f"Symbol: {result.symbol}")
    print(f"Passed: {result.passed} | Score: {result.score:.1f}/100")
    print(f"Signal: {result.signal} | Price: ${result.price:.2f}" if result.price else "")

    print(f"\n--- Core Indicators ---")
    if result.rsi:
        print(f"  RSI: {result.rsi:.2f}")
    if result.sma_50:
        print(f"  SMA 50: ${result.sma_50:.2f}")
    if result.atr_percent:
        print(f"  ATR %: {result.atr_percent:.2f}%")

    if show_all_indicators:
        print(f"\n--- New Indicators (Phase 2) ---")
        if result.macd_line is not None:
            print(f"  MACD Line: {result.macd_line:.4f}")
            print(f"  MACD Signal: {result.macd_signal:.4f}")
            print(f"  MACD Histogram: {result.macd_histogram:.4f} {'(Bullish ↗)' if result.macd_histogram > 0 else '(Bearish ↘)'}")

        if result.bb_upper is not None:
            print(f"  Bollinger Bands:")
            print(f"    Upper: ${result.bb_upper:.2f}")
            print(f"    Middle: ${result.bb_middle:.2f}")
            print(f"    Lower: ${result.bb_lower:.2f}")
            if result.bb_position is not None:
                position_desc = "Near Lower" if result.bb_position < 30 else "Near Upper" if result.bb_position > 70 else "Mid-Range"
                print(f"    Position: {result.bb_position:.1f}% ({position_desc})")

        if result.stoch_k is not None:
            print(f"  Stochastic:")
            print(f"    %K: {result.stoch_k:.2f}")
            print(f"    %D: {result.stoch_d:.2f}")
            stoch_desc = "Oversold" if result.stoch_k < 20 else "Overbought" if result.stoch_k > 80 else "Neutral"
            print(f"    Status: {stoch_desc}")

        if result.roc is not None:
            print(f"  ROC (14-day): {result.roc:+.2f}%")

    # Consensus results
    if 'consensus_signal' in result.filter_results:
        print(f"\n--- Consensus Analysis ---")
        print(f"  Consensus Signal: {result.filter_results['consensus_signal'].upper()}")
        print(f"  Agreement Count: {result.filter_results['consensus_agreement']}/5 indicators")

    print(f"{'='*80}")


async def test_enhanced_technical_screener():
    """Test the enhanced technical screener."""
    logger.info("="*80)
    logger.info("Enhanced Screener Test - Phase 1-3 Validation")
    logger.info("="*80)

    # Load config and initialize Alpaca client
    settings = load_config(Path("config/paper_trading.yaml"))
    settings.alpaca.paper = True

    logger.info("\n1. Initializing Alpaca client...")
    client = AlpacaClient(settings)

    # Initialize technical screener with criteria for signals
    criteria = ScreeningCriteria(
        min_price=10.0,
        max_price=1000.0,
        min_volume=500_000,
        rsi_oversold=30.0,
        rsi_overbought=70.0,
    )

    logger.info("\n2. Initializing Enhanced Technical Screener...")
    screener = TechnicalScreener(
        data_client=client.stock_data,
        criteria=criteria,
        lookback_days=60,
    )

    # Test with symbols from different tiers
    logger.info("\n3. Testing with Tiered Symbol Universe (Phase 3)...")
    tier1 = get_tier_1_symbols()[:5]  # Test 5 from Tier 1
    tier2 = get_tier_2_symbols()[:5]  # Test 5 from Tier 2

    test_symbols = list(set(tier1 + tier2))  # Combine and deduplicate
    logger.info(f"   Testing {len(test_symbols)} symbols from expanded universe")
    logger.info(f"   Tier 1 samples: {tier1}")
    logger.info(f"   Tier 2 samples: {tier2[:3]}...")

    # Screen all test symbols
    logger.info("\n4. Running enhanced screener...")
    results = []
    for symbol in test_symbols:
        logger.info(f"   Screening {symbol}...")
        result = await screener.screen_symbol(symbol)
        results.append(result)
        await asyncio.sleep(0.5)  # Rate limiting

    # Separate by signal
    bullish = [r for r in results if r.signal == "bullish"]
    bearish = [r for r in results if r.signal == "bearish"]
    neutral = [r for r in results if r.signal == "neutral"]

    logger.info(f"\n5. Screening Results Summary:")
    logger.info(f"   Total Scanned: {len(results)}")
    logger.info(f"   Bullish Signals: {len(bullish)}")
    logger.info(f"   Bearish Signals: {len(bearish)}")
    logger.info(f"   Neutral Signals: {len(neutral)}")

    # Show detailed results for bullish signals
    if bullish:
        logger.info(f"\n6. Bullish Opportunities (Consensus-Based):")
        for result in sorted(bullish, key=lambda x: x.score, reverse=True)[:3]:
            print_result_details(result, show_all_indicators=True)

    # Show detailed results for bearish signals
    if bearish:
        logger.info(f"\n7. Bearish Opportunities (Consensus-Based):")
        for result in sorted(bearish, key=lambda x: x.score, reverse=True)[:3]:
            print_result_details(result, show_all_indicators=True)

    # Show consensus statistics
    logger.info(f"\n8. Consensus Signal Statistics:")
    consensus_agreements = [r.filter_results.get('consensus_agreement', 0) for r in results]
    if consensus_agreements:
        avg_agreement = sum(consensus_agreements) / len(consensus_agreements)
        max_agreement = max(consensus_agreements)
        logger.info(f"   Average Agreement: {avg_agreement:.1f}/5 indicators")
        logger.info(f"   Maximum Agreement: {max_agreement}/5 indicators")

        # Count by agreement level
        strong_signals = len([a for a in consensus_agreements if a >= 4])
        moderate_signals = len([a for a in consensus_agreements if a == 3])
        logger.info(f"   Strong Signals (4-5 agree): {strong_signals}")
        logger.info(f"   Moderate Signals (3 agree): {moderate_signals}")

    logger.info("\n" + "="*80)
    logger.info("Enhanced Screener Test Complete!")
    logger.info("="*80)

    return results


async def main():
    """Run all tests."""
    try:
        results = await test_enhanced_technical_screener()

        print(f"\n\n{'='*80}")
        print("FINAL SUMMARY")
        print(f"{'='*80}")
        print(f"Total symbols screened: {len(results)}")
        print(f"Symbols with signals: {len([r for r in results if r.signal != 'neutral'])}")
        print(f"Average score: {sum(r.score for r in results) / len(results):.1f}/100")
        print(f"{'='*80}")

    except Exception as e:
        logger.error(f"Test failed with error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
