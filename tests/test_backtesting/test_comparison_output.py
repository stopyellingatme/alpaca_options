"""Tests for backtest comparison output formatting."""

import numpy as np
import pandas as pd
import pytest

from alpaca_options.utils.strategy_comparator import compare_strategies


class TestComparisonReportGeneration:
    """Tests for comparison report generation and formatting."""

    @pytest.fixture
    def mock_strategy_a_results(self) -> pd.DataFrame:
        """Mock backtest results for strategy A (better performer)."""
        np.random.seed(42)
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        returns = np.random.normal(0.5, 1.0, 100)  # Mean 0.5, std 1.0
        equity = np.cumsum(returns) + 10000

        return pd.DataFrame({"returns": returns, "equity": equity}, index=dates)

    @pytest.fixture
    def mock_strategy_b_results(self) -> pd.DataFrame:
        """Mock backtest results for strategy B (worse performer)."""
        np.random.seed(43)
        dates = pd.date_range("2024-01-01", periods=100, freq="D")
        returns = np.random.normal(0.2, 1.2, 100)  # Mean 0.2, std 1.2
        equity = np.cumsum(returns) + 10000

        return pd.DataFrame({"returns": returns, "equity": equity}, index=dates)

    def test_comparison_structure(
        self, mock_strategy_a_results: pd.DataFrame, mock_strategy_b_results: pd.DataFrame
    ) -> None:
        """Test that comparison output has all required fields."""
        comparison = compare_strategies(
            mock_strategy_a_results,
            mock_strategy_b_results,
            strategy_a_name="Debit Spreads",
            strategy_b_name="Credit Spreads",
            capital_a=5000,
            capital_b=5000,
        )

        # Verify structure
        assert "strategy_a" in comparison
        assert "strategy_b" in comparison
        assert "statistical_tests" in comparison
        assert "winner" in comparison

        # Verify strategy A details
        assert comparison["strategy_a"]["name"] == "Debit Spreads"
        assert "metrics" in comparison["strategy_a"]

        # Verify strategy B details
        assert comparison["strategy_b"]["name"] == "Credit Spreads"
        assert "metrics" in comparison["strategy_b"]

    def test_metrics_included(
        self, mock_strategy_a_results: pd.DataFrame, mock_strategy_b_results: pd.DataFrame
    ) -> None:
        """Test that all required metrics are calculated."""
        comparison = compare_strategies(
            mock_strategy_a_results,
            mock_strategy_b_results,
            capital_a=5000,
            capital_b=5000,
        )

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
            assert metric in comparison["strategy_a"]["metrics"]
            assert metric in comparison["strategy_b"]["metrics"]

    def test_statistical_tests_included(
        self, mock_strategy_a_results: pd.DataFrame, mock_strategy_b_results: pd.DataFrame
    ) -> None:
        """Test that statistical tests are performed."""
        comparison = compare_strategies(
            mock_strategy_a_results,
            mock_strategy_b_results,
            capital_a=5000,
            capital_b=5000,
        )

        # Mann-Whitney U test
        assert "mann_whitney_u" in comparison["statistical_tests"]
        assert "statistic" in comparison["statistical_tests"]["mann_whitney_u"]
        assert "p_value" in comparison["statistical_tests"]["mann_whitney_u"]

        # Effect size
        assert "effect_size" in comparison["statistical_tests"]
        assert "cohens_d" in comparison["statistical_tests"]["effect_size"]
        assert "interpretation" in comparison["statistical_tests"]["effect_size"]

    def test_bootstrap_ci_optional(
        self, mock_strategy_a_results: pd.DataFrame, mock_strategy_b_results: pd.DataFrame
    ) -> None:
        """Test that bootstrap confidence intervals are optionally included."""
        # Without bootstrap CI
        comparison_without = compare_strategies(
            mock_strategy_a_results,
            mock_strategy_b_results,
            capital_a=5000,
            capital_b=5000,
            include_bootstrap_ci=False,
        )
        assert "confidence_intervals" not in comparison_without

        # With bootstrap CI
        comparison_with = compare_strategies(
            mock_strategy_a_results,
            mock_strategy_b_results,
            capital_a=5000,
            capital_b=5000,
            include_bootstrap_ci=True,
            n_bootstrap=1000,  # Smaller for faster testing
        )
        assert "confidence_intervals" in comparison_with
        assert "strategy_a_mean_return_ci" in comparison_with["confidence_intervals"]
        assert "strategy_b_mean_return_ci" in comparison_with["confidence_intervals"]

    def test_winner_determination(
        self, mock_strategy_a_results: pd.DataFrame, mock_strategy_b_results: pd.DataFrame
    ) -> None:
        """Test that winner is determined correctly."""
        comparison = compare_strategies(
            mock_strategy_a_results,
            mock_strategy_b_results,
            strategy_a_name="Debit Spreads",
            strategy_b_name="Credit Spreads",
            capital_a=5000,
            capital_b=5000,
            significance_level=0.05,
        )

        assert "winner" in comparison
        assert "strategy" in comparison["winner"]
        assert "reason" in comparison["winner"]

        # Winner should be one of the strategies or "Inconclusive"
        assert comparison["winner"]["strategy"] in [
            "Debit Spreads",
            "Credit Spreads",
            "Inconclusive",
        ]

    def test_bonferroni_correction(
        self, mock_strategy_a_results: pd.DataFrame, mock_strategy_b_results: pd.DataFrame
    ) -> None:
        """Test Bonferroni multiple comparison correction."""
        comparison = compare_strategies(
            mock_strategy_a_results,
            mock_strategy_b_results,
            capital_a=5000,
            capital_b=5000,
            apply_bonferroni=True,
            num_comparisons=7,  # 7 metrics being compared
        )

        assert "multiple_comparison_correction" in comparison
        correction = comparison["multiple_comparison_correction"]

        assert correction["method"] == "bonferroni"
        assert correction["num_comparisons"] == 7
        assert correction["original_alpha"] == 0.05
        # Adjusted alpha should be 0.05 / 7 ≈ 0.00714
        assert pytest.approx(correction["adjusted_alpha"], abs=0.001) == 0.00714


class TestComparisonOutputFormatting:
    """Tests for formatted output generation."""

    @pytest.fixture
    def sample_comparison(self) -> dict:
        """Sample comparison result for formatting tests."""
        return {
            "strategy_a": {
                "name": "Debit Spreads",
                "metrics": {
                    "total_return": 500.0,
                    "annualized_return": 25.0,
                    "sharpe_ratio": 1.5,
                    "win_rate": 65.0,
                    "max_drawdown": 0.10,
                    "profit_factor": 2.5,
                    "capital_efficiency": 100.0,
                },
            },
            "strategy_b": {
                "name": "Credit Spreads",
                "metrics": {
                    "total_return": 300.0,
                    "annualized_return": 15.0,
                    "sharpe_ratio": 1.2,
                    "win_rate": 60.0,
                    "max_drawdown": 0.15,
                    "profit_factor": 2.0,
                    "capital_efficiency": 60.0,
                },
            },
            "statistical_tests": {
                "mann_whitney_u": {"statistic": 1234.5, "p_value": 0.03},
                "effect_size": {"cohens_d": 0.65, "interpretation": "medium"},
            },
            "winner": {
                "strategy": "Debit Spreads",
                "reason": "Statistically significant difference (p=0.03, effect size=0.65)",
            },
        }

    def test_comparison_dict_structure(self, sample_comparison: dict) -> None:
        """Test that comparison dict has proper structure for formatting."""
        assert isinstance(sample_comparison, dict)
        assert all(
            key in sample_comparison
            for key in ["strategy_a", "strategy_b", "statistical_tests", "winner"]
        )

    @pytest.mark.skip(reason="Requires Rich table formatter implementation")
    def test_format_as_table(self, sample_comparison: dict) -> None:
        """Test formatting comparison as Rich table."""
        # This would test the Rich table generation functionality
        # from the comparison_output.py module (to be implemented in S019)
        pass

    @pytest.mark.skip(reason="Requires formatter implementation")
    def test_format_with_visual_indicators(self, sample_comparison: dict) -> None:
        """Test that visual indicators (✓, ✗, ⚠) are included."""
        # This would test that the formatter adds visual indicators
        # for better/worse performance
        pass
