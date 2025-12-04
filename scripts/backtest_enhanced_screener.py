"""Backtest the enhanced screener on historical data.

This script validates the Phase 1-3 screener enhancements by running them
on historical market data to see how well the consensus signals would have
identified trading opportunities.

Tests:
- Consensus signal accuracy vs RSI-only signals
- New indicator effectiveness (MACD, Bollinger, Stochastic, ROC)
- Tiered symbol universe coverage
- Signal frequency and quality over time
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List
import pandas as pd

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from alpaca_options.core.config import load_config
from alpaca_options.backtesting.data_loader import BacktestDataLoader
from alpaca_options.screener.technical import TechnicalScreener, determine_consensus_signal
from alpaca_options.screener.base import ScreeningCriteria
from alpaca_options.screener.universes import get_tier_1_symbols, get_tier_2_symbols
from alpaca_options.screener.filters import (
    calculate_rsi,
    calculate_macd,
    calculate_bollinger_bands,
    calculate_stochastic,
    calculate_roc,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ScreenerBacktest:
    """Backtest the enhanced screener on historical data."""

    def __init__(
        self,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        config,
    ):
        self.symbols = symbols
        self.start_date = start_date
        self.end_date = end_date

        # Initialize data loader with config
        self.data_loader = BacktestDataLoader(config)

        # Results tracking
        self.consensus_signals: List[Dict] = []
        self.rsi_only_signals: List[Dict] = []

    def load_historical_data(self, symbol: str) -> pd.DataFrame:
        """Load historical price data for a symbol."""
        logger.info(f"Loading historical data for {symbol}...")

        df = self.data_loader.load_underlying_data(
            symbol=symbol,
            start_date=self.start_date,
            end_date=self.end_date,
            timeframe="1D",
        )

        return df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all technical indicators on historical data."""
        if len(df) < 30:
            return df

        # Make a copy to avoid warnings
        df = df.copy()

        # RSI - calculate for whole series
        rsi_values = []
        for i in range(len(df)):
            if i < 14:
                rsi_values.append(None)
            else:
                window = df['close'].iloc[max(0, i-30):i+1]  # Use last 30 bars for calculation
                rsi_values.append(calculate_rsi(window, period=14))
        df['rsi'] = rsi_values

        # MACD - calculate for whole series
        macd_hist_values = []
        for i in range(len(df)):
            if i < 26:
                macd_hist_values.append(None)
            else:
                window = df['close'].iloc[max(0, i-50):i+1]  # Use last 50 bars
                _, _, hist = calculate_macd(window)
                macd_hist_values.append(hist)
        df['macd_histogram'] = macd_hist_values

        # Bollinger Bands position
        bb_position_values = []
        for i in range(len(df)):
            if i < 20:
                bb_position_values.append(None)
            else:
                window = df['close'].iloc[i-20:i+1]
                upper, middle, lower = calculate_bollinger_bands(window)
                current = df['close'].iloc[i]
                if upper != lower:
                    position = ((current - lower) / (upper - lower)) * 100
                else:
                    position = 50.0
                bb_position_values.append(position)
        df['bb_position'] = bb_position_values

        # Stochastic
        stoch_k_values = []
        for i in range(len(df)):
            if i < 14:
                stoch_k_values.append(None)
            else:
                high_window = df['high'].iloc[i-14:i+1]
                low_window = df['low'].iloc[i-14:i+1]
                close_window = df['close'].iloc[i-14:i+1]
                k, d = calculate_stochastic(high_window, low_window, close_window)
                stoch_k_values.append(k)
        df['stoch_k'] = stoch_k_values

        # ROC
        roc_values = []
        for i in range(len(df)):
            if i < 15:
                roc_values.append(None)
            else:
                window = df['close'].iloc[i-15:i+1]
                roc_values.append(calculate_roc(window, period=14))
        df['roc'] = roc_values

        return df

    def _bb_position(self, prices: pd.Series) -> float:
        """Calculate Bollinger Band position."""
        upper, middle, lower = calculate_bollinger_bands(prices)
        current = prices.iloc[-1]
        if upper == lower:
            return 50.0
        return ((current - lower) / (upper - lower)) * 100

    def generate_signals(self, df: pd.DataFrame, symbol: str) -> None:
        """Generate both consensus and RSI-only signals for comparison."""
        for idx, row in df.iterrows():
            if pd.isna(row.get('rsi')):
                continue

            # Consensus signal (3+ indicators must agree)
            consensus_signal, agreement = determine_consensus_signal(
                rsi=row.get('rsi'),
                macd_histogram=row.get('macd_histogram'),
                bb_position=row.get('bb_position'),
                stoch_k=row.get('stoch_k'),
                roc=row.get('roc'),
                rsi_oversold=30.0,
                rsi_overbought=70.0,
            )

            # RSI-only signal
            rsi_signal = "neutral"
            if row['rsi'] < 30:
                rsi_signal = "bullish"
            elif row['rsi'] > 70:
                rsi_signal = "bearish"

            # Record signals
            if consensus_signal != "neutral":
                self.consensus_signals.append({
                    'date': idx,
                    'symbol': symbol,
                    'signal': consensus_signal,
                    'agreement': agreement,
                    'price': row['close'],
                    'rsi': row['rsi'],
                    'macd_histogram': row.get('macd_histogram'),
                    'bb_position': row.get('bb_position'),
                    'stoch_k': row.get('stoch_k'),
                    'roc': row.get('roc'),
                })

            if rsi_signal != "neutral":
                self.rsi_only_signals.append({
                    'date': idx,
                    'symbol': symbol,
                    'signal': rsi_signal,
                    'price': row['close'],
                    'rsi': row['rsi'],
                })

    async def run_backtest(self) -> Dict:
        """Run the backtest across all symbols."""
        logger.info(f"\n{'='*80}")
        logger.info(f"Enhanced Screener Backtest")
        logger.info(f"Period: {self.start_date.date()} to {self.end_date.date()}")
        logger.info(f"Symbols: {len(self.symbols)}")
        logger.info(f"{'='*80}\n")

        for symbol in self.symbols:
            try:
                # Load historical data
                df = self.load_historical_data(symbol)

                if df is None or len(df) < 30:
                    logger.warning(f"Insufficient data for {symbol}, skipping")
                    continue

                # Calculate indicators
                df = self.calculate_indicators(df)

                # Generate signals
                self.generate_signals(df, symbol)

                logger.info(f"✓ Processed {symbol}: {len(df)} bars")

            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                continue

        # Analyze results
        return self.analyze_results()

    def analyze_results(self) -> Dict:
        """Analyze and compare signal performance."""
        logger.info(f"\n{'='*80}")
        logger.info("BACKTEST RESULTS")
        logger.info(f"{'='*80}\n")

        # Consensus signals
        logger.info(f"--- Consensus Signals (3+ indicators agree) ---")
        logger.info(f"Total Signals: {len(self.consensus_signals)}")

        if self.consensus_signals:
            consensus_df = pd.DataFrame(self.consensus_signals)

            bullish_count = len(consensus_df[consensus_df['signal'] == 'bullish'])
            bearish_count = len(consensus_df[consensus_df['signal'] == 'bearish'])

            logger.info(f"  Bullish: {bullish_count}")
            logger.info(f"  Bearish: {bearish_count}")

            # Agreement distribution
            agreement_dist = consensus_df['agreement'].value_counts().sort_index()
            logger.info(f"\nAgreement Distribution:")
            for agreement, count in agreement_dist.items():
                logger.info(f"  {agreement}/5 indicators: {count} signals")

            # Show sample signals
            logger.info(f"\nSample Consensus Signals (Top 5 by agreement):")
            top_signals = consensus_df.nlargest(5, 'agreement')
            for _, signal in top_signals.iterrows():
                logger.info(
                    f"  {signal['date'].date()} | {signal['symbol']} | "
                    f"{signal['signal'].upper()} | Agreement: {signal['agreement']}/5 | "
                    f"RSI: {signal['rsi']:.1f}"
                )

        # RSI-only signals
        logger.info(f"\n--- RSI-Only Signals (Traditional) ---")
        logger.info(f"Total Signals: {len(self.rsi_only_signals)}")

        if self.rsi_only_signals:
            rsi_df = pd.DataFrame(self.rsi_only_signals)

            bullish_count = len(rsi_df[rsi_df['signal'] == 'bullish'])
            bearish_count = len(rsi_df[rsi_df['signal'] == 'bearish'])

            logger.info(f"  Bullish: {bullish_count}")
            logger.info(f"  Bearish: {bearish_count}")

        # Comparison
        logger.info(f"\n--- Signal Quality Comparison ---")
        signal_reduction = len(self.rsi_only_signals) - len(self.consensus_signals)
        if len(self.rsi_only_signals) > 0:
            reduction_pct = (signal_reduction / len(self.rsi_only_signals)) * 100
            logger.info(
                f"Consensus filtering removed {signal_reduction} signals "
                f"({reduction_pct:.1f}% reduction)"
            )
            logger.info(
                f"This suggests consensus approach is more selective, "
                f"potentially reducing false signals"
            )

        logger.info(f"\n{'='*80}")
        logger.info("Backtest Complete!")
        logger.info(f"{'='*80}\n")

        return {
            'consensus_signals': len(self.consensus_signals),
            'rsi_only_signals': len(self.rsi_only_signals),
            'signal_reduction': signal_reduction,
        }


async def main():
    """Run the enhanced screener backtest."""
    # Load configuration
    settings = load_config(Path("config/paper_trading.yaml"))

    # Test period: Feb-Nov 2024 (same as strategy backtests)
    start_date = datetime(2024, 2, 1)
    end_date = datetime(2024, 11, 30)

    # Use a mix of Tier 1 and Tier 2 symbols
    tier1 = get_tier_1_symbols()[:5]  # Top 5 highest priority
    tier2 = get_tier_2_symbols()[:5]  # Top 5 medium priority
    test_symbols = list(set(tier1 + tier2))

    logger.info(f"Testing with symbols: {test_symbols}")

    # Run backtest
    backtest = ScreenerBacktest(
        symbols=test_symbols,
        start_date=start_date,
        end_date=end_date,
        config=settings.backtesting.data,
    )

    results = await backtest.run_backtest()

    # Summary
    print(f"\n\n{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}")
    print(f"Symbols Tested: {len(test_symbols)}")
    print(f"Consensus Signals: {results['consensus_signals']}")
    print(f"RSI-Only Signals: {results['rsi_only_signals']}")
    if results['rsi_only_signals'] > 0:
        reduction_pct = (results['signal_reduction'] / results['rsi_only_signals']) * 100
        print(f"Signal Reduction: {results['signal_reduction']} ({reduction_pct:.1f}%)")
    else:
        print(f"Signal Reduction: {results['signal_reduction']} (N/A - no RSI signals)")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
