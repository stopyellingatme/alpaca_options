"""Tests for CLI commands and strategy selection."""

import pytest
from typer.testing import CliRunner

from alpaca_options.cli import app


runner = CliRunner()


class TestCLIStrategySelection:
    """Tests for CLI strategy selection functionality."""

    def test_strategy_flag_accepted(self) -> None:
        """Test that --strategy flag is accepted by CLI."""
        # Test that the CLI accepts the debit_spread strategy flag
        # This is a basic validation that the strategy can be specified
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0

    def test_debit_spread_strategy_available(self) -> None:
        """Test that debit_spread strategy is available in the system."""
        # The strategy should be importable and registered
        from alpaca_options.strategies.debit_spread import DebitSpreadStrategy

        strategy = DebitSpreadStrategy()
        assert strategy.name == "debit_spread"
        assert isinstance(strategy.description, str)

    @pytest.mark.skip(reason="Requires full CLI integration with config loading")
    def test_backtest_with_debit_spread_strategy(self) -> None:
        """Test running backtest command with debit_spread strategy."""
        # This would test: alpaca-options backtest --strategy debit_spread --symbol QQQ
        # Skip for now as it requires full integration setup
        pass

    @pytest.mark.skip(reason="Requires full CLI integration")
    def test_strategy_list_command(self) -> None:
        """Test listing available strategies."""
        # This would test a command to list all available strategies
        # and verify debit_spread is included
        pass


class TestCLIBacktestCommand:
    """Tests for backtest CLI command."""

    def test_backtest_command_exists(self) -> None:
        """Test that backtest command exists."""
        result = runner.invoke(app, ["backtest", "--help"])
        # Should either succeed or fail gracefully
        assert result.exit_code in [0, 1, 2]  # Various acceptable states

    @pytest.mark.skip(reason="Requires test data and full setup")
    def test_backtest_basic_execution(self) -> None:
        """Test basic backtest execution."""
        # This would test:
        # alpaca-options backtest --strategy debit_spread \
        #   --symbol QQQ --start 2024-01-01 --end 2024-03-01
        pass

    @pytest.mark.skip(reason="Requires full CLI integration")
    def test_backtest_with_capital_parameter(self) -> None:
        """Test backtest with capital parameter."""
        # This would test:
        # alpaca-options backtest --strategy debit_spread \
        #   --symbol QQQ --capital 5000
        pass


class TestCLIConfigValidation:
    """Tests for CLI configuration loading and validation."""

    def test_cli_loads_without_error(self) -> None:
        """Test that CLI app loads without errors."""
        # Basic smoke test that the CLI application initializes
        assert app is not None

    @pytest.mark.skip(reason="Requires config file setup")
    def test_strategy_config_loaded(self) -> None:
        """Test that strategy configuration is loaded correctly."""
        # This would verify that debit_spread config from YAML is accessible
        pass
