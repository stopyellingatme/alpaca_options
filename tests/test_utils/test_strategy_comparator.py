"""Tests for the StrategyComparator utility."""

import numpy as np
import pandas as pd
import pytest

from alpaca_options.utils.strategy_comparator import (
    StrategyComparator,
    bootstrap_confidence_interval,
    calculate_capital_efficiency,
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    cohens_d,
    compare_strategies,
)


class TestMetricCalculations:
    """Tests for individual metric calculation functions."""

    def test_sharpe_ratio_calculation(self) -> None:
        """Test Sharpe ratio calculation."""
        returns = pd.Series([0.01, 0.02, -0.01, 0.03, 0.01, 0.02])
        sharpe = calculate_sharpe_ratio(returns, risk_free_rate=0.0)

        assert isinstance(sharpe, float)
        assert sharpe > 0  # Positive returns should give positive Sharpe

    def test_sharpe_ratio_with_risk_free_rate(self) -> None:
        """Test Sharpe ratio with non-zero risk-free rate."""
        returns = pd.Series([0.05, 0.06, 0.04, 0.07, 0.05])
        sharpe_no_rf = calculate_sharpe_ratio(returns, risk_free_rate=0.0)
        sharpe_with_rf = calculate_sharpe_ratio(returns, risk_free_rate=0.02)

        assert sharpe_with_rf < sharpe_no_rf  # Risk-free rate reduces Sharpe

    def test_sharpe_ratio_negative_returns(self) -> None:
        """Test Sharpe ratio with negative returns."""
        returns = pd.Series([-0.01, -0.02, -0.03, -0.01, -0.02])
        sharpe = calculate_sharpe_ratio(returns)

        assert sharpe < 0  # Negative returns should give negative Sharpe

    def test_profit_factor_calculation(self) -> None:
        """Test profit factor calculation."""
        returns = pd.Series([0.5, 0.3, -0.2, 0.6, -0.1, 0.4, -0.3])
        pf = calculate_profit_factor(returns)

        assert isinstance(pf, float)
        assert pf > 0  # Should always be positive
        # Total gains = 0.5+0.3+0.6+0.4 = 1.8
        # Total losses = 0.2+0.1+0.3 = 0.6
        # PF = 1.8/0.6 = 3.0
        assert pytest.approx(pf, abs=0.01) == 3.0

    def test_profit_factor_no_losses(self) -> None:
        """Test profit factor with no losses (infinite profit factor)."""
        returns = pd.Series([0.1, 0.2, 0.3, 0.4])
        pf = calculate_profit_factor(returns)

        assert pf == float("inf")  # No losses = infinite PF

    def test_profit_factor_no_gains(self) -> None:
        """Test profit factor with no gains."""
        returns = pd.Series([-0.1, -0.2, -0.3])
        pf = calculate_profit_factor(returns)

        assert pf == 0.0  # No gains = zero PF

    def test_max_drawdown_calculation(self) -> None:
        """Test maximum drawdown calculation."""
        equity_curve = pd.Series([100, 110, 105, 120, 100, 110, 115])
        max_dd = calculate_max_drawdown(equity_curve)

        assert isinstance(max_dd, float)
        assert 0 <= max_dd <= 1  # Drawdown as percentage
        # Peak at 120, trough at 100 = 20% drawdown
        assert pytest.approx(max_dd, abs=0.01) == 0.1667

    def test_max_drawdown_no_drawdown(self) -> None:
        """Test max drawdown with monotonically increasing equity."""
        equity_curve = pd.Series([100, 110, 120, 130, 140])
        max_dd = calculate_max_drawdown(equity_curve)

        assert max_dd == 0.0  # No drawdown

    def test_capital_efficiency_calculation(self) -> None:
        """Test capital efficiency (return per $1000 deployed)."""
        total_return = 500.0  # $500 profit
        capital_deployed = 5000.0  # $5000 deployed
        efficiency = calculate_capital_efficiency(total_return, capital_deployed)

        # $500 / $5000 * 1000 = 100 (return per $1000)
        assert pytest.approx(efficiency, abs=0.01) == 100.0

    def test_capital_efficiency_negative_return(self) -> None:
        """Test capital efficiency with losses."""
        total_return = -200.0  # $200 loss
        capital_deployed = 2000.0
        efficiency = calculate_capital_efficiency(total_return, capital_deployed)

        # -$200 / $2000 * 1000 = -100
        assert pytest.approx(efficiency, abs=0.01) == -100.0


class TestStatisticalTests:
    """Tests for statistical comparison methods."""

    def test_cohens_d_calculation(self) -> None:
        """Test Cohen's d effect size calculation."""
        group_a = np.array([10, 12, 14, 16, 18])
        group_b = np.array([5, 7, 9, 11, 13])

        d = cohens_d(group_a, group_b)

        assert isinstance(d, float)
        assert d > 0  # Group A has higher mean

    def test_cohens_d_no_difference(self) -> None:
        """Test Cohen's d when groups are identical."""
        group_a = np.array([10, 12, 14, 16, 18])
        group_b = np.array([10, 12, 14, 16, 18])

        d = cohens_d(group_a, group_b)

        assert pytest.approx(d, abs=0.01) == 0.0

    def test_cohens_d_interpretation(self) -> None:
        """Test Cohen's d effect size interpretation."""
        # Small effect (d ~ 0.2)
        group_a_small = np.array([10.0, 10.2, 10.1, 10.3])
        group_b_small = np.array([10.0, 10.0, 10.1, 10.1])
        d_small = cohens_d(group_a_small, group_b_small)
        assert abs(d_small) < 0.5  # Small effect

        # Large effect (d ~ 0.8+)
        group_a_large = np.array([15, 16, 17, 18])
        group_b_large = np.array([10, 11, 12, 13])
        d_large = cohens_d(group_a_large, group_b_large)
        assert abs(d_large) > 0.8  # Large effect

    def test_bootstrap_confidence_interval(self) -> None:
        """Test bootstrap CI generation with 95% confidence."""
        data = np.array([10, 12, 14, 16, 18, 20, 22])
        ci_lower, ci_upper = bootstrap_confidence_interval(
            data, statistic=np.mean, n_bootstrap=1000, confidence_level=0.95
        )

        assert isinstance(ci_lower, float)
        assert isinstance(ci_upper, float)
        assert ci_lower < ci_upper
        # Mean should be roughly in the middle
        mean_val = np.mean(data)
        assert ci_lower < mean_val < ci_upper

    def test_bootstrap_ci_with_median(self) -> None:
        """Test bootstrap CI with median statistic."""
        data = np.array([1, 2, 3, 4, 5, 100])  # Outlier
        ci_lower, ci_upper = bootstrap_confidence_interval(
            data, statistic=np.median, n_bootstrap=1000
        )

        median_val = np.median(data)
        assert ci_lower < median_val < ci_upper

    def test_bootstrap_ci_different_confidence_levels(self) -> None:
        """Test that 99% CI is wider than 95% CI."""
        data = np.array([10, 12, 14, 16, 18, 20])

        ci_95_lower, ci_95_upper = bootstrap_confidence_interval(
            data, statistic=np.mean, confidence_level=0.95, n_bootstrap=1000
        )
        ci_99_lower, ci_99_upper = bootstrap_confidence_interval(
            data, statistic=np.mean, confidence_level=0.99, n_bootstrap=1000
        )

        width_95 = ci_95_upper - ci_95_lower
        width_99 = ci_99_upper - ci_99_lower

        assert width_99 > width_95  # 99% CI should be wider


class TestStrategyComparator:
    """Tests for StrategyComparator class."""

    @pytest.fixture
    def strategy_a_results(self) -> pd.DataFrame:
        """Sample results for strategy A (better performer)."""
        return pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=20, freq="D"),
                "returns": [0.5, 0.3, 0.4, -0.1, 0.6, 0.4, 0.5, -0.2, 0.7, 0.3] * 2,
                "equity": np.cumsum([0.5, 0.3, 0.4, -0.1, 0.6, 0.4, 0.5, -0.2, 0.7, 0.3] * 2)
                + 1000,
            }
        ).set_index("date")

    @pytest.fixture
    def strategy_b_results(self) -> pd.DataFrame:
        """Sample results for strategy B (worse performer)."""
        return pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=20, freq="D"),
                "returns": [0.2, 0.1, -0.1, 0.3, -0.2, 0.2, 0.1, -0.3, 0.2, 0.1] * 2,
                "equity": np.cumsum([0.2, 0.1, -0.1, 0.3, -0.2, 0.2, 0.1, -0.3, 0.2, 0.1] * 2)
                + 1000,
            }
        ).set_index("date")

    def test_comparator_initialization(self) -> None:
        """Test StrategyComparator initialization."""
        comparator = StrategyComparator()
        assert isinstance(comparator, StrategyComparator)

    def test_calculate_all_metrics(
        self, strategy_a_results: pd.DataFrame, strategy_b_results: pd.DataFrame
    ) -> None:
        """Test calculating all metrics for both strategies."""
        comparator = StrategyComparator()
        metrics_a = comparator.calculate_all_metrics(strategy_a_results, capital_deployed=5000)
        metrics_b = comparator.calculate_all_metrics(strategy_b_results, capital_deployed=5000)

        # Check all required metrics are present
        required_metrics = [
            "total_return",
            "annualized_return",
            "sharpe_ratio",
            "win_rate",
            "max_drawdown",
            "profit_factor",
            "capital_efficiency",
        ]
        for metric in required_metrics:
            assert metric in metrics_a
            assert metric in metrics_b

        # Strategy A should outperform Strategy B
        assert metrics_a["total_return"] > metrics_b["total_return"]
        assert metrics_a["sharpe_ratio"] > metrics_b["sharpe_ratio"]

    def test_compare_strategies_mann_whitney(
        self, strategy_a_results: pd.DataFrame, strategy_b_results: pd.DataFrame
    ) -> None:
        """Test Mann-Whitney U test for strategy comparison."""
        comparison = compare_strategies(
            strategy_a_results,
            strategy_b_results,
            strategy_a_name="Strategy A",
            strategy_b_name="Strategy B",
            capital_a=5000,
            capital_b=5000,
        )

        # Check comparison structure
        assert "strategy_a" in comparison
        assert "strategy_b" in comparison
        assert "statistical_tests" in comparison

        # Check Mann-Whitney U test results
        assert "mann_whitney_u" in comparison["statistical_tests"]
        mw_test = comparison["statistical_tests"]["mann_whitney_u"]
        assert "statistic" in mw_test
        assert "p_value" in mw_test
        assert 0 <= mw_test["p_value"] <= 1

    def test_compare_strategies_effect_size(
        self, strategy_a_results: pd.DataFrame, strategy_b_results: pd.DataFrame
    ) -> None:
        """Test effect size calculation in strategy comparison."""
        comparison = compare_strategies(
            strategy_a_results,
            strategy_b_results,
            capital_a=5000,
            capital_b=5000,
        )

        # Check effect size
        assert "effect_size" in comparison["statistical_tests"]
        effect_size = comparison["statistical_tests"]["effect_size"]
        assert "cohens_d" in effect_size
        assert "interpretation" in effect_size

        # Interpretation should be one of: "negligible", "small", "medium", "large"
        assert effect_size["interpretation"] in ["negligible", "small", "medium", "large"]

    def test_compare_strategies_confidence_intervals(
        self, strategy_a_results: pd.DataFrame, strategy_b_results: pd.DataFrame
    ) -> None:
        """Test bootstrap confidence intervals in comparison."""
        comparison = compare_strategies(
            strategy_a_results,
            strategy_b_results,
            capital_a=5000,
            capital_b=5000,
            include_bootstrap_ci=True,
            n_bootstrap=1000,
        )

        # Check CI for key metrics
        assert "confidence_intervals" in comparison
        ci = comparison["confidence_intervals"]

        assert "strategy_a_mean_return_ci" in ci
        assert "strategy_b_mean_return_ci" in ci

        # Each CI should have lower and upper bounds
        for key, value in ci.items():
            assert len(value) == 2  # (lower, upper)
            assert value[0] < value[1]  # lower < upper

    def test_compare_strategies_winner_determination(
        self, strategy_a_results: pd.DataFrame, strategy_b_results: pd.DataFrame
    ) -> None:
        """Test winner determination with statistical significance."""
        comparison = compare_strategies(
            strategy_a_results,
            strategy_b_results,
            strategy_a_name="Strategy A",
            strategy_b_name="Strategy B",
            capital_a=5000,
            capital_b=5000,
            significance_level=0.05,
        )

        # Check winner determination
        assert "winner" in comparison
        winner = comparison["winner"]

        assert "strategy" in winner
        assert winner["strategy"] in ["Strategy A", "Strategy B", "Inconclusive"]

        assert "reason" in winner
        assert isinstance(winner["reason"], str)

    def test_compare_strategies_with_bonferroni_correction(
        self, strategy_a_results: pd.DataFrame, strategy_b_results: pd.DataFrame
    ) -> None:
        """Test Bonferroni correction for multiple comparisons."""
        comparison = compare_strategies(
            strategy_a_results,
            strategy_b_results,
            capital_a=5000,
            capital_b=5000,
            apply_bonferroni=True,
            num_comparisons=5,  # Simulating 5 metrics compared
        )

        assert "multiple_comparison_correction" in comparison
        correction = comparison["multiple_comparison_correction"]

        assert "method" in correction
        assert correction["method"] == "bonferroni"
        assert "adjusted_alpha" in correction

        # Adjusted alpha should be 0.05 / 5 = 0.01
        assert pytest.approx(correction["adjusted_alpha"], abs=0.001) == 0.01


class TestStrategyComparatorEdgeCases:
    """Tests for edge cases and error handling."""

    def test_compare_identical_strategies(self) -> None:
        """Test comparison of identical strategies."""
        data = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=10, freq="D"),
                "returns": [0.3] * 10,
                "equity": np.cumsum([0.3] * 10) + 1000,
            }
        ).set_index("date")

        comparison = compare_strategies(data, data, capital_a=5000, capital_b=5000)

        # Should detect no significant difference
        assert comparison["winner"]["strategy"] == "Inconclusive"

        # Effect size should be ~0
        assert abs(comparison["statistical_tests"]["effect_size"]["cohens_d"]) < 0.1

    def test_compare_with_minimal_data(self) -> None:
        """Test comparison with very small sample sizes."""
        small_data_a = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=5, freq="D"),
                "returns": [0.5, 0.3, 0.4, 0.6, 0.5],
            }
        ).set_index("date")

        small_data_b = pd.DataFrame(
            {
                "date": pd.date_range("2024-01-01", periods=5, freq="D"),
                "returns": [0.2, 0.1, 0.3, 0.2, 0.1],
            }
        ).set_index("date")

        comparison = compare_strategies(small_data_a, small_data_b, capital_a=2000, capital_b=2000)

        # Should still compute comparison but may note insufficient sample size
        assert "strategy_a" in comparison
        assert "strategy_b" in comparison

    def test_calculate_metrics_with_zero_capital(self) -> None:
        """Test handling of zero capital (should raise error or handle gracefully)."""
        data = pd.DataFrame(
            {"date": pd.date_range("2024-01-01", periods=10, freq="D"), "returns": [0.3] * 10}
        ).set_index("date")

        comparator = StrategyComparator()

        # Should handle gracefully (capital efficiency becomes meaningless)
        with pytest.raises((ValueError, ZeroDivisionError)):
            comparator.calculate_all_metrics(data, capital_deployed=0)
