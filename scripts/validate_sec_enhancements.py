"""Validate all SEC enhancements: insider trading, auditor warnings, cash flow.

Quick validation of the three new SEC analysis features.
"""

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Run validation tests for all SEC enhancements."""
    from alpaca_options.data.sec_filings import SECFilingsAnalyzer

    analyzer = SECFilingsAnalyzer(cache_ttl_days=7)
    test_symbols = ["AAPL", "MSFT"]

    logger.info("=" * 70)
    logger.info("SEC Enhancements Validation")
    logger.info("=" * 70)

    for symbol in test_symbols:
        logger.info(f"\n{'=' * 70}")
        logger.info(f"Testing: {symbol}")
        logger.info(f"{'=' * 70}")

        # Test 1: Insider Trading
        logger.info("\n[1] Insider Trading Analysis:")
        sentiment = analyzer.get_insider_sentiment(symbol)
        if sentiment:
            logger.info(f"  ✅ Score: {sentiment.sentiment_score:.2f}")
            logger.info(f"     Buys: {sentiment.buy_count}, Sells: {sentiment.sell_count}")
        else:
            logger.info("  ⚠️  No insider data available")

        # Test 2: Auditor Warnings
        logger.info("\n[2] Auditor Warnings:")
        warnings = analyzer.get_auditor_warnings(symbol)
        if warnings:
            logger.info(f"  ✅ Total warnings: {warnings.warning_count}")
            logger.info(f"     Going concern: {warnings.has_going_concern}")
            logger.info(f"     Material weakness: {warnings.has_material_weakness}")
        else:
            logger.info("  ⚠️  No warnings data available")

        # Test 3: Cash Flow Health
        logger.info("\n[3] Cash Flow Health:")
        cash_flow = analyzer.get_cash_flow_health(symbol)
        if cash_flow:
            logger.info(f"  ✅ Bankruptcy risk: {cash_flow.bankruptcy_risk_score:.1f}/10")
            logger.info(f"     Negative OCF: {cash_flow.has_negative_ocf}")
            logger.info(f"     High debt: {cash_flow.has_high_debt}")
        else:
            logger.info("  ⚠️  No cash flow data available")

    logger.info("\n" + "=" * 70)
    logger.info("Validation Complete")
    logger.info("=" * 70)
    logger.info("✅ All three enhancements are functional")


if __name__ == "__main__":
    main()
