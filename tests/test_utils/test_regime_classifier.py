"""Tests for the RegimeClassifier utility."""

import pandas as pd
import pytest

from alpaca_options.utils.regime_classifier import (
    MarketRegime,
    RegimeClassifier,
    analyze_regime_performance,
    classify_regime,
)


class TestRegimeClassification:
    """Tests for VIX-based regime classification."""

    def test_classify_low_volatility(self) -> None:
        """Test classification of low volatility regime (VIX < 15)."""
        assert classify_regime(10.0) == MarketRegime.LOW_VOLATILITY
        assert classify_regime(12.5) == MarketRegime.LOW_VOLATILITY
        assert classify_regime(14.99) == MarketRegime.LOW_VOLATILITY

    def test_classify_normal_volatility(self) -> None:
        """Test classification of normal volatility regime (VIX 15-20)."""
        assert classify_regime(15.0) == MarketRegime.NORMAL
        assert classify_regime(17.5) == MarketRegime.NORMAL
        assert classify_regime(19.99) == MarketRegime.NORMAL

    def test_classify_elevated_volatility(self) -> None:
        """Test classification of elevated volatility regime (VIX 20-30)."""
        assert classify_regime(20.0) == MarketRegime.ELEVATED
        assert classify_regime(25.0) == MarketRegime.ELEVATED
        assert classify_regime(29.99) == MarketRegime.ELEVATED

    def test_classify_high_volatility(self) -> None:
        """Test classification of high volatility regime (VIX > 30)."""
        assert classify_regime(30.0) == MarketRegime.HIGH_VOLATILITY
        assert classify_regime(40.0) == MarketRegime.HIGH_VOLATILITY
        assert classify_regime(80.0) == MarketRegime.HIGH_VOLATILITY

    def test_classify_edge_cases(self) -> None:
        """Test edge cases for regime classification."""
        # Exactly on boundaries
        assert classify_regime(15.0) == MarketRegime.NORMAL
        assert classify_regime(20.0) == MarketRegime.ELEVATED
        assert classify_regime(30.0) == MarketRegime.HIGH_VOLATILITY

        # Very low VIX
        assert classify_regime(0.0) == MarketRegime.LOW_VOLATILITY
        assert classify_regime(5.0) == MarketRegime.LOW_VOLATILITY

        # Extreme VIX (market crash scenarios)
        assert classify_regime(100.0) == MarketRegime.HIGH_VOLATILITY


class TestRegimeClassifier:
    """Tests for RegimeClassifier class."""

    @pytest.fixture
    def sample_vix_data(self) -> pd.Series:
        """Create sample VIX time series data."""
        return pd.Series(
            [12.0, 14.0, 16.0, 18.0, 22.0, 25.0, 28.0, 35.0, 40.0, 38.0],
            index=pd.date_range("2024-01-01", periods=10, freq="D"),
            name="vix",
        )

    @pytest.fixture
    def sample_returns_data(self) -> pd.DataFrame:
        """Create sample returns data with VIX for regime analysis."""
        data = {
            "date": pd.date_range("2024-01-01", periods=20, freq="D"),
            "vix": [
                12,
                14,
                13,
                15,
                17,
                19,
                16,
                22,
                25,
                28,  # Various regimes
                26,
                32,
                35,
                38,
                33,
                20,
                18,
                15,
                14,
                12,
            ],
            "returns": [
                0.5,
                0.3,
                0.7,
                -0.2,
                0.4,
                0.6,
                0.3,
                -1.0,
                -1.5,
                -2.0,
                -1.2,
                -3.0,
                -2.5,
                -2.8,
                -1.5,
                0.8,
                1.0,
                0.5,
                0.4,
                0.6,
            ],
        }
        return pd.DataFrame(data).set_index("date")

    def test_classifier_initialization(self) -> None:
        """Test RegimeClassifier initialization."""
        classifier = RegimeClassifier()
        assert isinstance(classifier, RegimeClassifier)

    def test_classify_series(self, sample_vix_data: pd.Series) -> None:
        """Test classifying a pandas Series of VIX values."""
        classifier = RegimeClassifier()
        regimes = classifier.classify_series(sample_vix_data)

        assert len(regimes) == len(sample_vix_data)
        assert regimes.iloc[0] == MarketRegime.LOW_VOLATILITY  # VIX = 12
        assert regimes.iloc[4] == MarketRegime.ELEVATED  # VIX = 22
        assert regimes.iloc[-1] == MarketRegime.HIGH_VOLATILITY  # VIX = 38

    def test_get_regime_statistics(self, sample_vix_data: pd.Series) -> None:
        """Test getting regime statistics from VIX data."""
        classifier = RegimeClassifier()
        stats = classifier.get_regime_statistics(sample_vix_data)

        assert "LOW_VOLATILITY" in stats
        assert "NORMAL" in stats
        assert "ELEVATED" in stats
        assert "HIGH_VOLATILITY" in stats

        # Check structure of statistics
        assert "count" in stats["LOW_VOLATILITY"]
        assert "percentage" in stats["LOW_VOLATILITY"]

        # Verify totals add up to 100%
        total_pct = sum(s["percentage"] for s in stats.values())
        assert pytest.approx(total_pct, abs=0.1) == 100.0


class TestRegimePerformanceAnalysis:
    """Tests for regime performance analysis functionality."""

    @pytest.fixture
    def sample_strategy_results(self) -> pd.DataFrame:
        """Create sample strategy results with regime information."""
        data = {
            "date": pd.date_range("2024-01-01", periods=30, freq="D"),
            "vix": [
                # 10 low volatility days
                12,
                13,
                14,
                13,
                12,
                14,
                13,
                12,
                14,
                13,
                # 10 normal volatility days
                16,
                17,
                18,
                19,
                18,
                17,
                16,
                18,
                19,
                17,
                # 10 elevated volatility days
                22,
                24,
                26,
                28,
                25,
                23,
                24,
                26,
                27,
                25,
            ],
            "strategy_returns": [
                # Low volatility: modest positive returns
                0.3,
                0.4,
                0.5,
                0.2,
                0.4,
                0.3,
                0.5,
                0.4,
                0.3,
                0.4,
                # Normal volatility: mixed returns
                0.6,
                0.8,
                -0.3,
                0.5,
                0.7,
                -0.2,
                0.4,
                0.6,
                0.5,
                0.7,
                # Elevated volatility: higher variance
                1.2,
                -1.0,
                1.5,
                -0.5,
                1.8,
                1.0,
                -0.8,
                1.3,
                -0.6,
                1.1,
            ],
        }
        return pd.DataFrame(data).set_index("date")

    def test_analyze_regime_performance_basic(self, sample_strategy_results: pd.DataFrame) -> None:
        """Test basic regime performance analysis."""
        analysis = analyze_regime_performance(
            sample_strategy_results, vix_column="vix", returns_column="strategy_returns"
        )

        # Check that all regimes are analyzed
        assert "LOW_VOLATILITY" in analysis
        assert "NORMAL" in analysis
        assert "ELEVATED" in analysis

        # Check structure of analysis results
        for regime_stats in analysis.values():
            assert "count" in regime_stats
            assert "mean_return" in regime_stats
            assert "std_return" in regime_stats
            assert "total_return" in regime_stats

    def test_analyze_regime_performance_statistics(
        self, sample_strategy_results: pd.DataFrame
    ) -> None:
        """Test that regime performance statistics are calculated correctly."""
        analysis = analyze_regime_performance(
            sample_strategy_results, vix_column="vix", returns_column="strategy_returns"
        )

        # Low volatility should have 10 observations
        assert analysis["LOW_VOLATILITY"]["count"] == 10

        # Low volatility mean should be positive (all returns > 0)
        assert analysis["LOW_VOLATILITY"]["mean_return"] > 0

        # Elevated volatility should have higher std (more variance)
        assert analysis["ELEVATED"]["std_return"] > analysis["LOW_VOLATILITY"]["std_return"]

    def test_analyze_regime_performance_with_anova(
        self, sample_strategy_results: pd.DataFrame
    ) -> None:
        """Test ANOVA test for statistical significance across regimes."""
        analysis = analyze_regime_performance(
            sample_strategy_results,
            vix_column="vix",
            returns_column="strategy_returns",
            include_anova=True,
        )

        # Check ANOVA results are included
        assert "anova_test" in analysis
        assert "f_statistic" in analysis["anova_test"]
        assert "p_value" in analysis["anova_test"]

        # ANOVA p-value should be between 0 and 1
        p_value = analysis["anova_test"]["p_value"]
        assert 0 <= p_value <= 1

    def test_analyze_regime_performance_empty_regime(self) -> None:
        """Test handling of regimes with no data."""
        # Create data with only low volatility
        data = {
            "date": pd.date_range("2024-01-01", periods=5, freq="D"),
            "vix": [10, 11, 12, 13, 14],
            "strategy_returns": [0.5, 0.3, 0.4, 0.6, 0.5],
        }
        df = pd.DataFrame(data).set_index("date")

        analysis = analyze_regime_performance(
            df, vix_column="vix", returns_column="strategy_returns"
        )

        # Should only have LOW_VOLATILITY regime
        assert "LOW_VOLATILITY" in analysis
        assert analysis["LOW_VOLATILITY"]["count"] == 5

        # Other regimes should either be missing or have count 0
        if "NORMAL" in analysis:
            assert analysis["NORMAL"]["count"] == 0
        if "ELEVATED" in analysis:
            assert analysis["ELEVATED"]["count"] == 0
        if "HIGH_VOLATILITY" in analysis:
            assert analysis["HIGH_VOLATILITY"]["count"] == 0


class TestRegimeClassifierIntegration:
    """Integration tests for RegimeClassifier with real-world scenarios."""

    def test_full_backtest_workflow(self) -> None:
        """Test complete workflow: classify regimes → analyze performance."""
        # Simulate a full backtest result with VIX and returns
        data = {
            "date": pd.date_range("2024-01-01", periods=100, freq="D"),
            "vix": [12] * 25 + [17] * 25 + [24] * 25 + [35] * 25,
            "strategy_returns": (
                [0.3] * 25 + [0.5] * 25 + [0.8] * 25 + [-0.5] * 25
            ),  # Different performance by regime
        }
        df = pd.DataFrame(data).set_index("date")

        # Step 1: Classify regimes
        classifier = RegimeClassifier()
        df["regime"] = classifier.classify_series(df["vix"])

        # Step 2: Analyze performance by regime
        analysis = analyze_regime_performance(
            df, vix_column="vix", returns_column="strategy_returns", include_anova=True
        )

        # Verify we can identify that performance varies by regime
        assert "LOW_VOLATILITY" in analysis
        assert "HIGH_VOLATILITY" in analysis

        # High volatility should show negative mean return
        assert analysis["HIGH_VOLATILITY"]["mean_return"] < 0

        # Low volatility should show positive mean return
        assert analysis["LOW_VOLATILITY"]["mean_return"] > 0

        # ANOVA should show significant difference (p < 0.05 likely)
        assert "anova_test" in analysis

    def test_regime_transition_analysis(self) -> None:
        """Test analyzing regime transitions over time."""
        # Create data with regime transitions
        vix_data = pd.Series(
            [12, 13, 14, 16, 18, 20, 25, 30, 35, 32, 28, 22, 18, 15, 13],
            index=pd.date_range("2024-01-01", periods=15, freq="D"),
        )

        classifier = RegimeClassifier()
        regimes = classifier.classify_series(vix_data)

        # Count regime transitions
        transitions = (regimes != regimes.shift()).sum()
        assert transitions > 0  # Should have transitions

        # Get statistics
        stats = classifier.get_regime_statistics(vix_data)
        assert len(stats) >= 2  # Should have multiple regimes
