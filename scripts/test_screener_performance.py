#!/usr/bin/env python3
"""Test screener performance with batching and parallel processing.

Compares sequential vs parallel scanning performance.
"""

import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.trading.client import TradingClient
from alpaca_options.screener.technical import TechnicalScreener
from alpaca_options.screener.base import ScreeningCriteria
from alpaca_options.screener.universes import get_options_friendly_symbols

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_performance():
    """Test sequential vs parallel scanning performance."""

    # Initialize clients
    trading_client = TradingClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET_KEY"],
        paper=True
    )

    stock_data_client = StockHistoricalDataClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET_KEY"]
    )

    # Get test symbols (use smaller subset for testing)
    all_symbols = get_options_friendly_symbols()
    test_symbols = all_symbols[:50]  # Test with 50 symbols

    logger.info(f"Testing with {len(test_symbols)} symbols")
    logger.info(f"Symbols: {', '.join(test_symbols[:10])}...")

    # Create screener
    criteria = ScreeningCriteria(
        min_price=10.0,
        max_price=500.0,
        min_volume=500_000,
        rsi_oversold=45.0,
        rsi_overbought=55.0,
    )

    screener = TechnicalScreener(
        data_client=stock_data_client,
        criteria=criteria,
        cache_ttl_seconds=300,
        lookback_days=60
    )

    # Test 1: Sequential scanning
    logger.info("\n" + "=" * 70)
    logger.info("TEST 1: Sequential Scanning (original)")
    logger.info("=" * 70)

    screener.clear_cache()
    start = time.time()

    results_sequential = await screener.scan(
        test_symbols,
        max_results=None,
        use_parallel=False  # Sequential mode
    )

    sequential_duration = time.time() - start

    logger.info(f"✅ Sequential scan complete:")
    logger.info(f"   Duration: {sequential_duration:.2f}s")
    logger.info(f"   Passed: {results_sequential.total_passed}/{results_sequential.total_scanned}")
    logger.info(f"   Speed: {len(test_symbols)/sequential_duration:.1f} symbols/sec")

    # Get cache stats
    cache_stats_seq = screener.get_cache_stats()
    logger.info(f"   Cache hit rate: {cache_stats_seq['bars_cache']['hit_rate']:.1f}%")

    # Test 2: Parallel scanning (fresh cache)
    logger.info("\n" + "=" * 70)
    logger.info("TEST 2: Parallel Scanning with Batching (optimized)")
    logger.info("=" * 70)

    screener.clear_cache()
    start = time.time()

    results_parallel = await screener.scan(
        test_symbols,
        max_results=None,
        use_parallel=True,  # Parallel mode with prefetching
        max_concurrent=50
    )

    parallel_duration = time.time() - start

    logger.info(f"✅ Parallel scan complete:")
    logger.info(f"   Duration: {parallel_duration:.2f}s")
    logger.info(f"   Passed: {results_parallel.total_passed}/{results_parallel.total_scanned}")
    logger.info(f"   Speed: {len(test_symbols)/parallel_duration:.1f} symbols/sec")

    # Get cache stats
    cache_stats_par = screener.get_cache_stats()
    logger.info(f"   Cache hit rate: {cache_stats_par['bars_cache']['hit_rate']:.1f}%")

    # Test 3: Second parallel scan (with warm cache)
    logger.info("\n" + "=" * 70)
    logger.info("TEST 3: Parallel Scanning with Warm Cache")
    logger.info("=" * 70)

    start = time.time()

    results_cached = await screener.scan(
        test_symbols,
        max_results=None,
        use_parallel=True,
        max_concurrent=50
    )

    cached_duration = time.time() - start

    logger.info(f"✅ Cached scan complete:")
    logger.info(f"   Duration: {cached_duration:.2f}s")
    logger.info(f"   Passed: {results_cached.total_passed}/{results_cached.total_scanned}")
    logger.info(f"   Speed: {len(test_symbols)/cached_duration:.1f} symbols/sec")

    # Get cache stats
    cache_stats_cached = screener.get_cache_stats()
    logger.info(f"   Cache hit rate: {cache_stats_cached['bars_cache']['hit_rate']:.1f}%")

    # Performance Summary
    logger.info("\n" + "=" * 70)
    logger.info("PERFORMANCE SUMMARY")
    logger.info("=" * 70)

    speedup = sequential_duration / parallel_duration
    cache_speedup = sequential_duration / cached_duration

    logger.info(f"Sequential (baseline):  {sequential_duration:.2f}s ({len(test_symbols)/sequential_duration:.1f} sym/s)")
    logger.info(f"Parallel (cold cache):  {parallel_duration:.2f}s ({len(test_symbols)/parallel_duration:.1f} sym/s)")
    logger.info(f"Parallel (warm cache):  {cached_duration:.2f}s ({len(test_symbols)/cached_duration:.1f} sym/s)")
    logger.info("")
    logger.info(f"📊 Speedup (cold cache): {speedup:.2f}x faster")
    logger.info(f"📊 Speedup (warm cache): {cache_speedup:.2f}x faster")
    logger.info("")

    if speedup >= 2.0:
        logger.info("✅ EXCELLENT: >2x speedup achieved!")
    elif speedup >= 1.5:
        logger.info("✅ GOOD: 1.5-2x speedup achieved")
    else:
        logger.info("⚠️  MODERATE: <1.5x speedup (check API rate limits)")

    logger.info("")
    logger.info("Optimization Benefits:")
    logger.info(f"  - Batched API requests (up to 100 symbols/request)")
    logger.info(f"  - Parallel async processing (50 concurrent)")
    logger.info(f"  - Multi-level caching with TTL expiration")
    logger.info(f"  - Prefetch data before screening")

    # Extrapolate to 300 symbols
    logger.info("\n" + "=" * 70)
    logger.info("EXTRAPOLATION TO 300 SYMBOLS")
    logger.info("=" * 70)

    scale_factor = 300 / len(test_symbols)
    est_sequential = sequential_duration * scale_factor
    est_parallel = parallel_duration * scale_factor

    logger.info(f"Estimated time for 300 symbols:")
    logger.info(f"  Sequential: ~{est_sequential:.1f}s ({est_sequential/60:.1f} min)")
    logger.info(f"  Parallel:   ~{est_parallel:.1f}s ({est_parallel/60:.1f} min)")
    logger.info(f"  Time saved: ~{(est_sequential - est_parallel):.1f}s per scan")


if __name__ == "__main__":
    try:
        asyncio.run(test_performance())
    except KeyboardInterrupt:
        logger.info("\nTest interrupted by user")
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        sys.exit(1)
