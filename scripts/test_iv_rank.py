"""Test script for IV Rank calculation.

This script demonstrates the IV data manager functionality:
1. Initialize the IVDataManager
2. Fetch historical IV data for a few symbols
3. Calculate IV rank
4. Display results
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alpaca_options.core.config import load_config
from alpaca_options.alpaca.client import AlpacaClient
from alpaca_options.screener.iv_data import IVDataManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Test IV rank calculation."""
    logger.info("=" * 70)
    logger.info("IV Rank Test - Phase 1 Enhancement Verification")
    logger.info("=" * 70)

    # Load config and initialize Alpaca client
    settings = load_config(Path("config/paper_trading.yaml"))
    settings.alpaca.paper = True

    logger.info("\n1. Initializing Alpaca client...")
    client = AlpacaClient(settings)

    # Initialize IV data manager
    logger.info("\n2. Initializing IV Data Manager...")
    iv_manager = IVDataManager(
        trading_client=client.trading,
        options_data_client=client.option_data,
        cache_dir="./data/iv_cache",
        min_history_days=252,
    )

    # Test symbols
    test_symbols = ["QQQ", "SPY", "AAPL"]
    logger.info(f"\n3. Testing with symbols: {test_symbols}")

    # Load or fetch IV history for each symbol
    for symbol in test_symbols:
        logger.info(f"\n--- Processing {symbol} ---")

        # Load or fetch IV history
        logger.info(f"Loading IV history for {symbol}...")
        df = await iv_manager.load_or_fetch_iv_history(symbol)

        if df.empty:
            logger.warning(f"No IV data available for {symbol}")
            continue

        # Get summary stats
        summary = iv_manager.get_iv_summary(symbol)
        if summary:
            logger.info(f"  Data points: {summary['data_points']}")
            logger.info(f"  Date range: {summary['oldest_date']} to {summary['latest_date']}")
            logger.info(f"  IV range: {summary['min_iv']:.3f} - {summary['max_iv']:.3f}")
            logger.info(f"  Mean IV: {summary['mean_iv']:.3f}")
            logger.info(f"  Std IV: {summary['std_iv']:.3f}")

            # Test IV rank calculation with different IV values
            test_ivs = [
                summary['min_iv'],
                summary['mean_iv'],
                summary['max_iv'],
                summary['mean_iv'] * 0.9,  # Below mean
                summary['mean_iv'] * 1.1,  # Above mean
            ]

            logger.info(f"\n  IV Rank calculations:")
            for iv in test_ivs:
                iv_rank = iv_manager.calculate_iv_rank(symbol, iv)
                if iv_rank is not None:
                    logger.info(f"    IV {iv:.3f} → IV Rank: {iv_rank:.1f}")

    # Show cached symbols
    cached = iv_manager.get_cached_symbols()
    logger.info(f"\n4. Cached symbols: {cached}")

    logger.info("\n" + "=" * 70)
    logger.info("Test Complete!")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
