"""Statistical comparison tools for evaluating strategy performance.

This module provides comprehensive statistical analysis for comparing two trading strategies,
including:
- Performance metrics (Sharpe ratio, profit factor, max drawdown, capital efficiency)
- Statistical significance testing (Mann-Whitney U test)
- Effect size calculation (Cohen's d)
- Bootstrap confidence intervals
- Multiple comparison correction (Bonferroni)

Usage:
    # Compare two strategies
    comparison = compare_strategies(
        strategy_a_results,
        strategy_b_results,
        strategy_a_name="Debit Spreads",
        strategy_b_name="Credit Spreads",
        capital_a=5000,
        capital_b=5000,
        include_bootstrap_ci=True,
    )

    # Check if difference is statistically significant
    if comparison["statistical_tests"]["mann_whitney_u"]["p_value"] < 0.05:
        print(f"Winner: {comparison['winner']['strategy']}")
"""

from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats


def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> float:
    """Calculate annualized Sharpe ratio.

    Args:
        returns: Series of returns
        risk_free_rate: Annual risk-free rate (default 0.0)
        periods_per_year: Number of periods in a year (default 252 for daily)

    Returns:
        Annualized Sharpe ratio
    """
    if len(returns) == 0 or returns.std() == 0:
        return 0.0

    excess_returns = returns - (risk_free_rate / periods_per_year)
    return float((excess_returns.mean() / excess_returns.std()) * np.sqrt(periods_per_year))


def calculate_profit_factor(returns: pd.Series) -> float:
    """Calculate profit factor (gross profits / gross losses).

    Args:
        returns: Series of returns

    Returns:
        Profit factor (inf if no losses, 0 if no gains)
    """
    gains = returns[returns > 0].sum()
    losses = abs(returns[returns < 0].sum())

    if losses == 0:
        return float("inf") if gains > 0 else 0.0

    return float(gains / losses)


def calculate_max_drawdown(equity_curve: pd.Series) -> float:
    """Calculate maximum drawdown as a percentage.

    Args:
        equity_curve: Series of equity values

    Returns:
        Maximum drawdown as decimal (0.0 to 1.0)
    """
    if len(equity_curve) == 0:
        return 0.0

    # Calculate running maximum
    running_max = equity_curve.expanding().max()

    # Calculate drawdown at each point
    drawdown = (equity_curve - running_max) / running_max

    # Return maximum drawdown (most negative value)
    return float(abs(drawdown.min()))


def calculate_capital_efficiency(total_return: float, capital_deployed: float) -> float:
    """Calculate return per $1000 of capital deployed.

    Args:
        total_return: Total profit/loss
        capital_deployed: Total capital deployed

    Returns:
        Return per $1000 deployed

    Raises:
        ValueError: If capital_deployed is zero
    """
    if capital_deployed == 0:
        raise ValueError("Capital deployed cannot be zero")

    return float((total_return / capital_deployed) * 1000)


def cohens_d(group_a: np.ndarray, group_b: np.ndarray) -> float:
    """Calculate Cohen's d effect size.

    Cohen's d measures the standardized difference between two means:
    - Small effect: |d| ~ 0.2
    - Medium effect: |d| ~ 0.5
    - Large effect: |d| ~ 0.8

    Args:
        group_a: First group of observations
        group_b: Second group of observations

    Returns:
        Cohen's d effect size
    """
    mean_a = np.mean(group_a)
    mean_b = np.mean(group_b)

    # Pooled standard deviation
    n_a = len(group_a)
    n_b = len(group_b)
    var_a = np.var(group_a, ddof=1)
    var_b = np.var(group_b, ddof=1)

    pooled_std = np.sqrt(((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2))

    if pooled_std == 0:
        return 0.0

    return float((mean_a - mean_b) / pooled_std)


def bootstrap_confidence_interval(
    data: np.ndarray,
    statistic: Callable,
    n_bootstrap: int = 10000,
    confidence_level: float = 0.95,
    random_seed: int | None = None,
) -> tuple[float, float]:
    """Generate bootstrap confidence interval for a statistic.

    Args:
        data: Array of observations
        statistic: Function to compute statistic (e.g., np.mean, np.median)
        n_bootstrap: Number of bootstrap samples (default 10000)
        confidence_level: Confidence level (default 0.95 for 95% CI)
        random_seed: Optional random seed for reproducibility

    Returns:
        Tuple of (lower_bound, upper_bound)
    """
    if random_seed is not None:
        np.random.seed(random_seed)

    bootstrap_statistics = []

    for _ in range(n_bootstrap):
        # Resample with replacement
        sample = np.random.choice(data, size=len(data), replace=True)
        bootstrap_statistics.append(statistic(sample))

    # Calculate percentiles for CI
    alpha = 1 - confidence_level
    lower_percentile = (alpha / 2) * 100
    upper_percentile = (1 - alpha / 2) * 100

    lower_bound = np.percentile(bootstrap_statistics, lower_percentile)
    upper_bound = np.percentile(bootstrap_statistics, upper_percentile)

    return float(lower_bound), float(upper_bound)


class StrategyComparator:
    """Comprehensive strategy comparison with statistical analysis.

    This class provides methods for calculating performance metrics and
    comparing strategies using statistical tests.
    """

    def __init__(self) -> None:
        """Initialize the strategy comparator."""
        pass

    def calculate_all_metrics(
        self,
        results: pd.DataFrame,
        capital_deployed: float,
        returns_column: str = "returns",
        equity_column: str = "equity",
    ) -> dict[str, float]:
        """Calculate comprehensive performance metrics for a strategy.

        Args:
            results: DataFrame containing strategy results
            capital_deployed: Total capital deployed
            returns_column: Name of returns column (default "returns")
            equity_column: Name of equity column (default "equity")

        Returns:
            Dict containing:
                - total_return: Total profit/loss
                - annualized_return: Annualized return percentage
                - sharpe_ratio: Risk-adjusted return metric
                - win_rate: Percentage of winning trades
                - max_drawdown: Maximum drawdown percentage
                - profit_factor: Ratio of gross profits to gross losses
                - capital_efficiency: Return per $1000 deployed
        """
        returns = results[returns_column]
        equity = results[equity_column] if equity_column in results.columns else None

        total_return = float(returns.sum())
        winning_trades = (returns > 0).sum()
        total_trades = len(returns)

        # Calculate metrics
        metrics = {
            "total_return": total_return,
            "annualized_return": self._calculate_annualized_return(returns),
            "sharpe_ratio": calculate_sharpe_ratio(returns),
            "win_rate": float((winning_trades / total_trades) * 100) if total_trades > 0 else 0.0,
            "max_drawdown": calculate_max_drawdown(equity) if equity is not None else 0.0,
            "profit_factor": calculate_profit_factor(returns),
            "capital_efficiency": calculate_capital_efficiency(total_return, capital_deployed),
        }

        return metrics

    def _calculate_annualized_return(self, returns: pd.Series) -> float:
        """Calculate annualized return percentage."""
        total_return = returns.sum()
        n_periods = len(returns)

        if n_periods == 0:
            return 0.0

        # Assume daily returns, convert to annual
        periods_per_year = 252
        years = n_periods / periods_per_year

        if years == 0:
            return 0.0

        annualized = total_return / years
        return float(annualized)


def compare_strategies(
    strategy_a_results: pd.DataFrame,
    strategy_b_results: pd.DataFrame,
    strategy_a_name: str = "Strategy A",
    strategy_b_name: str = "Strategy B",
    capital_a: float = 5000.0,
    capital_b: float = 5000.0,
    returns_column: str = "returns",
    equity_column: str = "equity",
    include_bootstrap_ci: bool = False,
    n_bootstrap: int = 10000,
    significance_level: float = 0.05,
    apply_bonferroni: bool = False,
    num_comparisons: int = 1,
) -> dict[str, Any]:
    """Comprehensive statistical comparison of two strategies.

    Args:
        strategy_a_results: DataFrame with strategy A results
        strategy_b_results: DataFrame with strategy B results
        strategy_a_name: Name of strategy A
        strategy_b_name: Name of strategy B
        capital_a: Capital deployed for strategy A
        capital_b: Capital deployed for strategy B
        returns_column: Name of returns column
        equity_column: Name of equity column
        include_bootstrap_ci: Whether to include bootstrap confidence intervals
        n_bootstrap: Number of bootstrap samples for CI
        significance_level: Alpha level for hypothesis tests (default 0.05)
        apply_bonferroni: Whether to apply Bonferroni correction
        num_comparisons: Number of comparisons for Bonferroni correction

    Returns:
        Dict containing:
            - strategy_a: Metrics for strategy A
            - strategy_b: Metrics for strategy B
            - statistical_tests: Mann-Whitney U test, effect size
            - confidence_intervals (optional): Bootstrap CIs
            - winner: Winner determination with reason
            - multiple_comparison_correction (optional): Bonferroni details
    """
    comparator = StrategyComparator()

    # Calculate metrics for both strategies
    metrics_a = comparator.calculate_all_metrics(
        strategy_a_results, capital_a, returns_column, equity_column
    )
    metrics_b = comparator.calculate_all_metrics(
        strategy_b_results, capital_b, returns_column, equity_column
    )

    # Get returns for statistical tests
    returns_a = strategy_a_results[returns_column].values
    returns_b = strategy_b_results[returns_column].values

    # Mann-Whitney U test (non-parametric test for difference in distributions)
    u_statistic, p_value = stats.mannwhitneyu(returns_a, returns_b, alternative="two-sided")

    # Calculate effect size (Cohen's d)
    effect_size_d = cohens_d(returns_a, returns_b)

    # Interpret effect size
    abs_d = abs(effect_size_d)
    if abs_d < 0.2:
        effect_interpretation = "negligible"
    elif abs_d < 0.5:
        effect_interpretation = "small"
    elif abs_d < 0.8:
        effect_interpretation = "medium"
    else:
        effect_interpretation = "large"

    result: dict[str, Any] = {
        "strategy_a": {
            "name": strategy_a_name,
            "metrics": metrics_a,
        },
        "strategy_b": {
            "name": strategy_b_name,
            "metrics": metrics_b,
        },
        "statistical_tests": {
            "mann_whitney_u": {
                "statistic": float(u_statistic),
                "p_value": float(p_value),
            },
            "effect_size": {
                "cohens_d": float(effect_size_d),
                "interpretation": effect_interpretation,
            },
        },
    }

    # Optional: Bootstrap confidence intervals
    if include_bootstrap_ci:
        ci_a_lower, ci_a_upper = bootstrap_confidence_interval(
            returns_a, statistic=np.mean, n_bootstrap=n_bootstrap
        )
        ci_b_lower, ci_b_upper = bootstrap_confidence_interval(
            returns_b, statistic=np.mean, n_bootstrap=n_bootstrap
        )

        result["confidence_intervals"] = {
            "strategy_a_mean_return_ci": (ci_a_lower, ci_a_upper),
            "strategy_b_mean_return_ci": (ci_b_lower, ci_b_upper),
        }

    # Optional: Bonferroni correction
    adjusted_alpha = significance_level
    if apply_bonferroni:
        adjusted_alpha = significance_level / num_comparisons
        result["multiple_comparison_correction"] = {
            "method": "bonferroni",
            "num_comparisons": num_comparisons,
            "original_alpha": significance_level,
            "adjusted_alpha": adjusted_alpha,
        }

    # Determine winner
    is_significant = p_value < adjusted_alpha
    a_better = metrics_a["total_return"] > metrics_b["total_return"]

    if is_significant:
        winner_name = strategy_a_name if a_better else strategy_b_name
        reason = (
            f"Statistically significant difference (p={p_value:.4f}, "
            f"effect size={effect_size_d:.2f})"
        )
    else:
        winner_name = "Inconclusive"
        reason = (
            f"No statistically significant difference (p={p_value:.4f}). "
            f"Sample size may be insufficient or strategies perform similarly."
        )

    result["winner"] = {
        "strategy": winner_name,
        "reason": reason,
    }

    return result
