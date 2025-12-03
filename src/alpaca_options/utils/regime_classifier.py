"""Market Regime Classification based on VIX levels.

This module provides tools for classifying market regimes based on VIX (volatility index)
levels and analyzing strategy performance across different regimes. Understanding regime
performance is critical for knowing when to use different options strategies.

Market Regimes (VIX-based):
- LOW_VOLATILITY: VIX < 15 (calm markets, good for debit spreads)
- NORMAL: VIX 15-20 (typical markets, most strategies work)
- ELEVATED: VIX 20-30 (higher volatility, good for credit spreads)
- HIGH_VOLATILITY: VIX >= 30 (stressed markets, reduce exposure)

Usage:
    # Classify a single VIX value
    regime = classify_regime(vix_value=18.5)

    # Classify a time series
    classifier = RegimeClassifier()
    regimes = classifier.classify_series(vix_series)

    # Analyze strategy performance by regime
    analysis = analyze_regime_performance(
        backtest_results,
        vix_column="vix",
        returns_column="returns",
        include_anova=True
    )
"""

from enum import Enum
from typing import Any

import pandas as pd
from scipy import stats


class MarketRegime(Enum):
    """Market regime classifications based on VIX levels."""

    LOW_VOLATILITY = "LOW_VOLATILITY"
    NORMAL = "NORMAL"
    ELEVATED = "ELEVATED"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"


def classify_regime(vix_value: float) -> MarketRegime:
    """Classify market regime based on VIX value.

    Args:
        vix_value: Current VIX level

    Returns:
        MarketRegime enum value

    VIX Thresholds:
        < 15: Low volatility (calm markets)
        15-20: Normal volatility (typical markets)
        20-30: Elevated volatility (higher than normal)
        >= 30: High volatility (stressed/crisis markets)
    """
    if vix_value < 15.0:
        return MarketRegime.LOW_VOLATILITY
    elif vix_value < 20.0:
        return MarketRegime.NORMAL
    elif vix_value < 30.0:
        return MarketRegime.ELEVATED
    else:
        return MarketRegime.HIGH_VOLATILITY


class RegimeClassifier:
    """Classifier for analyzing market regimes over time.

    This class provides methods for:
    - Classifying VIX time series into regimes
    - Computing regime statistics (time spent in each regime)
    - Analyzing strategy performance by regime
    """

    def __init__(self) -> None:
        """Initialize the regime classifier."""
        pass

    def classify_series(self, vix_series: pd.Series) -> pd.Series:
        """Classify a pandas Series of VIX values into regimes.

        Args:
            vix_series: Time series of VIX values

        Returns:
            Series of MarketRegime values with same index as input
        """
        return vix_series.apply(classify_regime)

    def get_regime_statistics(self, vix_series: pd.Series) -> dict[str, dict[str, Any]]:
        """Get statistics about time spent in each regime.

        Args:
            vix_series: Time series of VIX values

        Returns:
            Dict mapping regime name to statistics:
                - count: Number of observations in this regime
                - percentage: Percentage of time spent in this regime
        """
        regimes = self.classify_series(vix_series)
        total_count = len(regimes)

        stats_dict: dict[str, dict[str, Any]] = {}

        for regime in MarketRegime:
            count = (regimes == regime).sum()
            percentage = (count / total_count * 100) if total_count > 0 else 0.0

            stats_dict[regime.value] = {
                "count": int(count),
                "percentage": float(percentage),
            }

        return stats_dict


def analyze_regime_performance(
    df: pd.DataFrame,
    vix_column: str = "vix",
    returns_column: str = "returns",
    include_anova: bool = False,
) -> dict[str, Any]:
    """Analyze strategy performance across different market regimes.

    This function classifies each observation by regime and computes performance
    statistics for each regime. Optionally performs ANOVA test to check if
    returns are significantly different across regimes.

    Args:
        df: DataFrame containing VIX and returns data
        vix_column: Name of column containing VIX values
        returns_column: Name of column containing strategy returns
        include_anova: Whether to include ANOVA test for regime differences

    Returns:
        Dict containing:
            - For each regime: count, mean_return, std_return, total_return
            - If include_anova=True: anova_test with f_statistic and p_value

    Example:
        >>> analysis = analyze_regime_performance(
        ...     backtest_df,
        ...     vix_column="vix",
        ...     returns_column="strategy_returns",
        ...     include_anova=True
        ... )
        >>> print(f"Low volatility mean return: {analysis['LOW_VOLATILITY']['mean_return']:.2f}")
        >>> print(f"ANOVA p-value: {analysis['anova_test']['p_value']:.4f}")
    """
    # Classify regimes
    df = df.copy()
    df["regime"] = df[vix_column].apply(classify_regime)

    results: dict[str, Any] = {}

    # Group by regime and compute statistics
    for regime in MarketRegime:
        regime_data = df[df["regime"] == regime][returns_column]

        if len(regime_data) == 0:
            # No data for this regime
            results[regime.value] = {
                "count": 0,
                "mean_return": 0.0,
                "std_return": 0.0,
                "total_return": 0.0,
            }
        else:
            results[regime.value] = {
                "count": int(len(regime_data)),
                "mean_return": float(regime_data.mean()),
                "std_return": float(regime_data.std()),
                "total_return": float(regime_data.sum()),
            }

    # Optional ANOVA test
    if include_anova:
        # Group returns by regime
        regime_groups = []
        for regime in MarketRegime:
            regime_data = df[df["regime"] == regime][returns_column]
            if len(regime_data) > 0:
                regime_groups.append(regime_data.values)

        # Perform ANOVA only if we have at least 2 groups with data
        if len(regime_groups) >= 2:
            f_statistic, p_value = stats.f_oneway(*regime_groups)
            results["anova_test"] = {
                "f_statistic": float(f_statistic),
                "p_value": float(p_value),
                "interpretation": (
                    "Significant difference" if p_value < 0.05 else "No significant difference"
                ),
            }
        else:
            results["anova_test"] = {
                "f_statistic": None,
                "p_value": None,
                "interpretation": "Insufficient data for ANOVA",
            }

    return results
