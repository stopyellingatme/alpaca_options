"""Screener-integrated backtest runner.

This module provides functionality to:
1. Take screener-discovered opportunities
2. Fetch historical data for those opportunities
3. Run backtests to validate the opportunities
4. Report on which opportunities would have been profitable historically
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import pandas as pd

from alpaca_options.screener.integration import Opportunity, OpportunityType
from alpaca_options.backtesting.engine import BacktestEngine, BacktestResult, BacktestMetrics
from alpaca_options.core.config import BacktestConfig, RiskConfig, TradingConfig
from alpaca_options.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


@dataclass
class OpportunityBacktestResult:
    """Result of backtesting a screener opportunity."""

    opportunity: Opportunity
    backtest_result: Optional[BacktestResult]
    validation_passed: bool
    recommendation: str
    confidence: float
    metrics_summary: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "symbol": self.opportunity.symbol,
            "opportunity_type": self.opportunity.opportunity_type.value,
            "opportunity_score": self.opportunity.score,
            "validation_passed": self.validation_passed,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "metrics": self.metrics_summary,
            "error": self.error,
        }


@dataclass
class BacktestValidationConfig:
    """Configuration for opportunity validation via backtest."""

    # Backtest period
    lookback_days: int = 60  # How far back to test

    # Validation thresholds
    min_win_rate: float = 50.0  # Minimum win rate %
    min_profit_factor: float = 1.2  # Minimum profit factor
    max_drawdown_percent: float = 20.0  # Maximum acceptable drawdown
    min_sharpe_ratio: float = 0.5  # Minimum Sharpe ratio
    min_trades: int = 3  # Minimum trades to validate

    # Strategy assignment
    bullish_strategy: str = "wheel"  # Strategy for bullish opportunities
    bearish_strategy: str = "vertical_spread"  # Strategy for bearish
    high_iv_strategy: str = "iron_condor"  # Strategy for high IV


class ScreenerBacktestRunner:
    """Runs backtests on screener-discovered opportunities.

    Validates opportunities by running historical backtests
    to see if similar setups would have been profitable.
    """

    def __init__(
        self,
        backtest_config: Optional[BacktestConfig] = None,
        risk_config: Optional[RiskConfig] = None,
        trading_config: Optional[TradingConfig] = None,
        validation_config: Optional[BacktestValidationConfig] = None,
        data_fetcher=None,
    ) -> None:
        """Initialize the backtest runner.

        Args:
            backtest_config: Backtest engine configuration.
            risk_config: Risk management configuration.
            trading_config: Trading configuration.
            validation_config: Validation thresholds.
            data_fetcher: Data fetcher for historical data.
        """
        self._backtest_config = backtest_config or BacktestConfig()
        self._risk_config = risk_config or RiskConfig()
        self._trading_config = trading_config or TradingConfig()
        self._validation_config = validation_config or BacktestValidationConfig()
        self._data_fetcher = data_fetcher

        # Cache of backtest results
        self._results_cache: dict[str, OpportunityBacktestResult] = {}

        # Strategy instances (lazily loaded)
        self._strategies: dict[str, BaseStrategy] = {}

    async def validate_opportunity(
        self,
        opportunity: Opportunity,
        strategy: Optional[BaseStrategy] = None,
    ) -> OpportunityBacktestResult:
        """Validate an opportunity via backtesting.

        Args:
            opportunity: The screener opportunity to validate.
            strategy: Optional specific strategy to use.

        Returns:
            OpportunityBacktestResult with validation status.
        """
        symbol = opportunity.symbol
        cache_key = f"{symbol}_{opportunity.opportunity_type.value}"

        # Check cache
        if cache_key in self._results_cache:
            cached = self._results_cache[cache_key]
            # Cache valid for 1 hour
            if (datetime.now() - cached.opportunity.discovered_at).seconds < 3600:
                return cached

        try:
            # Get or create strategy
            if strategy is None:
                strategy = await self._get_strategy_for_opportunity(opportunity)

            if strategy is None:
                return OpportunityBacktestResult(
                    opportunity=opportunity,
                    backtest_result=None,
                    validation_passed=False,
                    recommendation="SKIP",
                    confidence=0.0,
                    error="No suitable strategy found",
                )

            # Fetch historical data
            underlying_data, options_data = await self._fetch_historical_data(symbol)

            if underlying_data is None or len(underlying_data) < 20:
                return OpportunityBacktestResult(
                    opportunity=opportunity,
                    backtest_result=None,
                    validation_passed=False,
                    recommendation="SKIP",
                    confidence=0.0,
                    error="Insufficient historical data",
                )

            # Create backtest engine
            engine = BacktestEngine(
                config=self._backtest_config,
                risk_config=self._risk_config,
                trading_config=self._trading_config,
            )

            # Determine date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self._validation_config.lookback_days)

            # Run backtest
            backtest_result = await engine.run(
                strategy=strategy,
                underlying_data=underlying_data,
                options_data=options_data,
                start_date=start_date,
                end_date=end_date,
            )

            # Validate results
            validation_passed, confidence, recommendation = self._validate_backtest_results(
                backtest_result, opportunity
            )

            result = OpportunityBacktestResult(
                opportunity=opportunity,
                backtest_result=backtest_result,
                validation_passed=validation_passed,
                recommendation=recommendation,
                confidence=confidence,
                metrics_summary={
                    "win_rate": backtest_result.metrics.win_rate,
                    "profit_factor": backtest_result.metrics.profit_factor,
                    "sharpe_ratio": backtest_result.metrics.sharpe_ratio,
                    "max_drawdown_percent": backtest_result.metrics.max_drawdown_percent,
                    "total_trades": backtest_result.metrics.total_trades,
                    "total_return_percent": backtest_result.metrics.total_return_percent,
                },
            )

            # Cache result
            self._results_cache[cache_key] = result

            return result

        except Exception as e:
            logger.error(f"Error validating opportunity {symbol}: {e}")
            return OpportunityBacktestResult(
                opportunity=opportunity,
                backtest_result=None,
                validation_passed=False,
                recommendation="ERROR",
                confidence=0.0,
                error=str(e),
            )

    async def validate_opportunities(
        self,
        opportunities: list[Opportunity],
        max_concurrent: int = 5,
    ) -> list[OpportunityBacktestResult]:
        """Validate multiple opportunities in parallel.

        Args:
            opportunities: List of opportunities to validate.
            max_concurrent: Maximum concurrent backtests.

        Returns:
            List of validation results.
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def validate_with_semaphore(opp):
            async with semaphore:
                return await self.validate_opportunity(opp)

        tasks = [validate_with_semaphore(opp) for opp in opportunities]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                valid_results.append(OpportunityBacktestResult(
                    opportunity=opportunities[i],
                    backtest_result=None,
                    validation_passed=False,
                    recommendation="ERROR",
                    confidence=0.0,
                    error=str(result),
                ))
            else:
                valid_results.append(result)

        return valid_results

    def _validate_backtest_results(
        self,
        result: BacktestResult,
        opportunity: Opportunity,
    ) -> tuple[bool, float, str]:
        """Validate backtest results against thresholds.

        Args:
            result: Backtest result to validate.
            opportunity: Original opportunity.

        Returns:
            Tuple of (validation_passed, confidence, recommendation).
        """
        metrics = result.metrics
        config = self._validation_config

        # Check minimum trades
        if metrics.total_trades < config.min_trades:
            return False, 0.2, "INSUFFICIENT_DATA"

        # Calculate pass/fail for each metric
        checks = {
            "win_rate": metrics.win_rate >= config.min_win_rate,
            "profit_factor": metrics.profit_factor >= config.min_profit_factor,
            "max_drawdown": metrics.max_drawdown_percent <= config.max_drawdown_percent,
            "sharpe_ratio": metrics.sharpe_ratio >= config.min_sharpe_ratio,
        }

        passed_checks = sum(checks.values())
        total_checks = len(checks)

        # Calculate confidence based on how many checks passed
        base_confidence = passed_checks / total_checks

        # Boost confidence if metrics are significantly better than thresholds
        confidence_boost = 0.0
        if metrics.win_rate > config.min_win_rate * 1.2:
            confidence_boost += 0.1
        if metrics.profit_factor > config.min_profit_factor * 1.5:
            confidence_boost += 0.1
        if metrics.sharpe_ratio > config.min_sharpe_ratio * 2:
            confidence_boost += 0.1

        confidence = min(base_confidence + confidence_boost, 1.0)

        # Determine recommendation
        if passed_checks == total_checks:
            recommendation = "STRONG_BUY" if opportunity.opportunity_type == OpportunityType.BULLISH else "STRONG_SELL"
        elif passed_checks >= total_checks - 1:
            recommendation = "BUY" if opportunity.opportunity_type == OpportunityType.BULLISH else "SELL"
        elif passed_checks >= total_checks // 2:
            recommendation = "HOLD"
        else:
            recommendation = "AVOID"

        validation_passed = passed_checks >= total_checks - 1

        return validation_passed, confidence, recommendation

    async def _get_strategy_for_opportunity(
        self,
        opportunity: Opportunity,
    ) -> Optional[BaseStrategy]:
        """Get appropriate strategy for opportunity type.

        Args:
            opportunity: The opportunity to match.

        Returns:
            Strategy instance or None.
        """
        from alpaca_options.strategies.wheel import WheelStrategy
        from alpaca_options.strategies.vertical_spread import VerticalSpreadStrategy
        from alpaca_options.strategies.iron_condor import IronCondorStrategy

        opp_type = opportunity.opportunity_type
        config = self._validation_config

        strategy_map = {
            OpportunityType.BULLISH: (config.bullish_strategy, WheelStrategy),
            OpportunityType.BEARISH: (config.bearish_strategy, VerticalSpreadStrategy),
            OpportunityType.HIGH_IV: (config.high_iv_strategy, IronCondorStrategy),
            OpportunityType.GENERAL: (config.bullish_strategy, WheelStrategy),
        }

        strategy_name, strategy_class = strategy_map.get(
            opp_type, (config.bullish_strategy, WheelStrategy)
        )

        # Check cache
        if strategy_name in self._strategies:
            return self._strategies[strategy_name]

        # Create strategy
        try:
            strategy = strategy_class()
            await strategy.initialize({
                "underlyings": [opportunity.symbol],
                "allocation": 0.1,
            })
            self._strategies[strategy_name] = strategy
            return strategy
        except Exception as e:
            logger.error(f"Failed to create strategy {strategy_name}: {e}")
            return None

    async def _fetch_historical_data(
        self,
        symbol: str,
    ) -> tuple[Optional[pd.DataFrame], dict[datetime, Any]]:
        """Fetch historical data for backtesting.

        Args:
            symbol: Symbol to fetch data for.

        Returns:
            Tuple of (underlying_data, options_data).
        """
        if self._data_fetcher is None:
            logger.warning("No data fetcher configured")
            return None, {}

        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self._validation_config.lookback_days)

            underlying_data = await self._data_fetcher.get_stock_bars(
                symbol, start_date, end_date
            )

            options_data = await self._data_fetcher.get_options_history(
                symbol, start_date, end_date
            )

            return underlying_data, options_data

        except Exception as e:
            logger.error(f"Failed to fetch historical data for {symbol}: {e}")
            return None, {}

    def get_validation_summary(
        self,
        results: list[OpportunityBacktestResult],
    ) -> dict[str, Any]:
        """Get summary of validation results.

        Args:
            results: List of validation results.

        Returns:
            Summary dictionary.
        """
        total = len(results)
        passed = sum(1 for r in results if r.validation_passed)
        failed = total - passed

        by_recommendation = {}
        by_type = {}

        for r in results:
            # By recommendation
            rec = r.recommendation
            if rec not in by_recommendation:
                by_recommendation[rec] = []
            by_recommendation[rec].append(r.opportunity.symbol)

            # By type
            opp_type = r.opportunity.opportunity_type.value
            if opp_type not in by_type:
                by_type[opp_type] = {"passed": 0, "failed": 0}
            if r.validation_passed:
                by_type[opp_type]["passed"] += 1
            else:
                by_type[opp_type]["failed"] += 1

        avg_confidence = sum(r.confidence for r in results) / total if total > 0 else 0

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": (passed / total * 100) if total > 0 else 0,
            "avg_confidence": avg_confidence,
            "by_recommendation": by_recommendation,
            "by_type": by_type,
            "validated_symbols": [r.opportunity.symbol for r in results if r.validation_passed],
        }

    def clear_cache(self) -> None:
        """Clear the results cache."""
        self._results_cache.clear()


async def validate_screener_opportunities(
    opportunities: list[Opportunity],
    backtest_config: Optional[BacktestConfig] = None,
    risk_config: Optional[RiskConfig] = None,
    validation_config: Optional[BacktestValidationConfig] = None,
    data_fetcher=None,
) -> tuple[list[OpportunityBacktestResult], dict[str, Any]]:
    """Convenience function to validate opportunities.

    Args:
        opportunities: Opportunities to validate.
        backtest_config: Backtest configuration.
        risk_config: Risk configuration.
        validation_config: Validation thresholds.
        data_fetcher: Data fetcher instance.

    Returns:
        Tuple of (results, summary).
    """
    runner = ScreenerBacktestRunner(
        backtest_config=backtest_config,
        risk_config=risk_config,
        validation_config=validation_config,
        data_fetcher=data_fetcher,
    )

    results = await runner.validate_opportunities(opportunities)
    summary = runner.get_validation_summary(results)

    return results, summary
