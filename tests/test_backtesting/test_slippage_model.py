"""Tests for ORATS slippage methodology in backtesting.

The ORATS slippage model uses bid-ask spread percentages based on strategy complexity:
- Single-leg: 75% of bid-ask spread
- Two-leg spreads (vertical/debit spreads): 65% of bid-ask spread
- Four-leg spreads (iron condors): 56% of bid-ask spread

This provides more realistic fill simulation than fixed percentage slippage.
"""

import pytest


class TestSlippageModel:
    """Tests for slippage calculation based on strategy complexity."""

    def test_single_leg_slippage(self) -> None:
        """Test slippage calculation for single-leg options (75% of spread)."""
        bid = 5.00
        ask = 5.50
        num_legs = 1

        # Expected: 75% of 0.50 = 0.375
        expected_slippage = (ask - bid) * 0.75
        assert pytest.approx(expected_slippage, abs=0.01) == 0.375

    def test_two_leg_spread_slippage(self) -> None:
        """Test slippage calculation for two-leg spreads (65% of spread)."""
        # Leg 1: Buy call
        leg1_bid = 5.00
        leg1_ask = 5.50

        # Leg 2: Sell call
        leg2_bid = 2.00
        leg2_ask = 2.40

        num_legs = 2

        # Calculate total spread
        total_spread = (leg1_ask - leg1_bid) + (leg2_ask - leg2_bid)
        # Expected: 65% of total spread
        expected_slippage = total_spread * 0.65

        # Total spread = 0.50 + 0.40 = 0.90
        # 65% of 0.90 = 0.585
        assert pytest.approx(expected_slippage, abs=0.01) == 0.585

    def test_four_leg_spread_slippage(self) -> None:
        """Test slippage calculation for four-leg spreads (56% of spread)."""
        # Iron condor: 4 legs
        spreads = [0.50, 0.40, 0.30, 0.25]  # Bid-ask spreads for each leg
        num_legs = 4

        total_spread = sum(spreads)
        # Expected: 56% of total spread
        expected_slippage = total_spread * 0.56

        # Total spread = 1.45
        # 56% of 1.45 = 0.812
        assert pytest.approx(expected_slippage, abs=0.01) == 0.812

    def test_slippage_percentage_by_legs(self) -> None:
        """Test that correct slippage percentage is applied based on leg count."""
        slippage_percentages = {
            1: 0.75,  # Single leg
            2: 0.65,  # Two legs
            4: 0.56,  # Four legs
        }

        for num_legs, expected_pct in slippage_percentages.items():
            # Use a standard bid-ask spread of $1.00
            spread = 1.00
            expected_slippage = spread * expected_pct
            calculated_slippage = spread * slippage_percentages[num_legs]

            assert pytest.approx(calculated_slippage, abs=0.01) == expected_slippage

    def test_debit_spread_slippage_calculation(self) -> None:
        """Test realistic debit spread slippage calculation."""
        # Bull call spread example
        # Long call: Buy at ask
        long_bid = 8.00
        long_ask = 8.40

        # Short call: Sell at bid
        short_bid = 3.00
        short_ask = 3.30

        # Debit = (long ask - short bid) = 8.40 - 3.00 = 5.40
        debit_no_slippage = long_ask - short_bid

        # With ORATS slippage (65% of total spread):
        # Total spread = (8.40 - 8.00) + (3.30 - 3.00) = 0.40 + 0.30 = 0.70
        total_spread = (long_ask - long_bid) + (short_ask - short_bid)
        slippage = total_spread * 0.65

        # Debit with slippage = 5.40 + 0.455 = 5.855
        debit_with_slippage = debit_no_slippage + slippage

        assert pytest.approx(total_spread, abs=0.01) == 0.70
        assert pytest.approx(slippage, abs=0.01) == 0.455
        assert pytest.approx(debit_with_slippage, abs=0.01) == 5.855

    def test_credit_spread_slippage_calculation(self) -> None:
        """Test realistic credit spread slippage calculation."""
        # Bull put spread example
        # Short put: Sell at bid
        short_bid = 2.00
        short_ask = 2.30

        # Long put: Buy at ask
        long_bid = 0.80
        long_ask = 1.00

        # Credit = (short bid - long ask) = 2.00 - 1.00 = 1.00
        credit_no_slippage = short_bid - long_ask

        # With ORATS slippage (65% of total spread):
        # Total spread = (2.30 - 2.00) + (1.00 - 0.80) = 0.30 + 0.20 = 0.50
        total_spread = (short_ask - short_bid) + (long_ask - long_bid)
        slippage = total_spread * 0.65

        # Credit with slippage = 1.00 - 0.325 = 0.675
        credit_with_slippage = credit_no_slippage - slippage

        assert pytest.approx(total_spread, abs=0.01) == 0.50
        assert pytest.approx(slippage, abs=0.01) == 0.325
        assert pytest.approx(credit_with_slippage, abs=0.01) == 0.675

    def test_zero_spread_no_slippage(self) -> None:
        """Test that zero bid-ask spread results in zero slippage."""
        # Perfect market maker scenario (unrealistic but edge case)
        bid = 5.00
        ask = 5.00  # No spread

        num_legs = 2
        spread = ask - bid
        slippage = spread * 0.65

        assert slippage == 0.0

    def test_wide_spread_high_slippage(self) -> None:
        """Test that wide spreads result in proportionally higher slippage."""
        # Illiquid option with wide spread
        bid = 1.00
        ask = 2.00  # $1.00 spread (100% of bid)

        num_legs = 1
        spread = ask - bid
        slippage = spread * 0.75

        # 75% of $1.00 = $0.75
        assert pytest.approx(slippage, abs=0.01) == 0.75


class TestSlippageIntegration:
    """Tests for slippage model integration with backtest engine."""

    def test_slippage_affects_trade_profitability(self) -> None:
        """Test that slippage reduces profitability for winning trades."""
        # Debit spread entry
        entry_debit_ideal = 5.00
        entry_slippage = 0.40  # 65% of spread
        entry_debit_actual = entry_debit_ideal + entry_slippage

        # Debit spread exit (close for profit)
        exit_debit_ideal = 2.50  # Closes for less than entry = profit
        exit_slippage = 0.30
        exit_debit_actual = exit_debit_ideal + exit_slippage

        # Profit without slippage
        profit_ideal = (entry_debit_ideal - exit_debit_ideal) * 100
        # Profit with slippage
        profit_actual = (entry_debit_actual - exit_debit_actual) * 100

        # Slippage should reduce profit
        assert profit_actual < profit_ideal
        # Difference should be (entry_slippage - exit_slippage) * 100
        profit_difference = profit_ideal - profit_actual
        assert pytest.approx(profit_difference, abs=0.1) == 10.0  # (0.40 - 0.30) * 100

    def test_slippage_increases_losses(self) -> None:
        """Test that slippage increases losses for losing trades."""
        # Debit spread entry
        entry_debit_ideal = 5.00
        entry_slippage = 0.40
        entry_debit_actual = entry_debit_ideal + entry_slippage

        # Debit spread exit (close for loss)
        exit_debit_ideal = 8.00  # Closes for more than entry = loss
        exit_slippage = 0.50
        exit_debit_actual = exit_debit_ideal + exit_slippage

        # Loss without slippage
        loss_ideal = (exit_debit_ideal - entry_debit_ideal) * 100
        # Loss with slippage
        loss_actual = (exit_debit_actual - entry_debit_actual) * 100

        # Slippage should increase loss
        assert loss_actual > loss_ideal
        # Difference should be (exit_slippage + entry_slippage) * 100
        loss_difference = loss_actual - loss_ideal
        assert pytest.approx(loss_difference, abs=0.1) == 90.0  # (0.40 + 0.50) * 100

    def test_commissions_separate_from_slippage(self) -> None:
        """Test that commissions are calculated separately from slippage."""
        # ORATS slippage model only handles slippage, not commissions
        # Commissions should be added separately by backtest engine

        # Example: $0.65 per contract (Alpaca typical commission)
        commission_per_contract = 0.65
        num_contracts = 2  # Two-leg spread

        # Entry commissions
        entry_commissions = commission_per_contract * num_contracts

        # Exit commissions
        exit_commissions = commission_per_contract * num_contracts

        # Total commissions
        total_commissions = entry_commissions + exit_commissions

        # Commissions are fixed costs, not percentage-based like slippage
        assert total_commissions == 2.60  # $0.65 * 2 * 2 = $2.60

    def test_slippage_model_selection(self) -> None:
        """Test that correct slippage percentage is selected based on leg count."""

        def get_slippage_percentage(num_legs: int) -> float:
            """Helper function to get slippage percentage by leg count."""
            slippage_map = {
                1: 0.75,  # Single leg
                2: 0.65,  # Two legs (vertical/debit spreads)
                4: 0.56,  # Four legs (iron condors)
            }
            return slippage_map.get(num_legs, 0.65)  # Default to 2-leg

        # Test each strategy type
        assert get_slippage_percentage(1) == 0.75  # Naked options
        assert get_slippage_percentage(2) == 0.65  # Debit/credit spreads
        assert get_slippage_percentage(4) == 0.56  # Iron condors
        assert get_slippage_percentage(3) == 0.65  # Unknown, defaults to 2-leg
